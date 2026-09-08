"""Offline G05-G08 tests for native adapters, results, and Git evidence."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import unittest

import jsonschema

from harness_relay.adapters import (
    DetectedWorker,
    TaskRequest,
    UnsupportedOverrideError,
    build_invocation,
)
from harness_relay.execution import ValidationRequest, run_task
from harness_relay.git_evidence import GitEvidenceError, capture_base, capture_snapshot
from harness_relay.results import RESULT_SCHEMA_VERSION, validate_result


class Pr3Test(unittest.TestCase):
    def test_static_adapters_construct_native_argv_without_shell_syntax(self) -> None:
        prompt = "write a file named '$HOME;touch unsafe' and report it"
        with tempfile.TemporaryDirectory(prefix="work space ") as directory:
            cwd = Path(directory)
            for name, version in (
                ("codex", "0.153.4"),
                ("claude", "2.1.104"),
                ("agy", "1.1.27"),
            ):
                with self.subTest(name=name):
                    worker = DetectedWorker(name, Path(f"/bin/{name}"), version, "test")
                    task_options = {"sandbox": "workspace-write"} if name == "codex" else {}
                    invocation = build_invocation(
                        worker,
                        TaskRequest(prompt=prompt, cwd=cwd, model="model-x", **task_options),
                    )
                    self.assertEqual(invocation.cwd, cwd)
                    self.assertIn(prompt, invocation.argv)
                    self.assertEqual(invocation.argv[-1], prompt)
                    self.assertNotIn("shell=True", invocation.argv)
                    self.assertIn("--output-format", invocation.argv) if name != "codex" else self.assertIn("--json", invocation.argv)

        with self.assertRaises(UnsupportedOverrideError):
            build_invocation(
                DetectedWorker("codex", Path("/bin/codex"), "0.153.4", "test"),
                TaskRequest(prompt="x", cwd=Path("/tmp"), effort="high"),
            )
        with self.assertRaises(UnsupportedOverrideError):
            build_invocation(
                DetectedWorker("agy", Path("/bin/agy"), "99.0.0", "test"),
                TaskRequest(prompt="x", cwd=Path("/tmp")),
            )

    def test_adapter_native_flags_preserve_defaults_and_only_explicit_overrides(self) -> None:
        codex = build_invocation(
            DetectedWorker("codex", Path("/bin/codex"), "0.153.4", "test"),
            TaskRequest(prompt="x", cwd=Path("/tmp")),
        )
        self.assertEqual(
            codex.argv,
            ("/bin/codex", "exec", "--json", "--cd", "/tmp", "x"),
        )
        claude = build_invocation(
            DetectedWorker("claude", Path("/bin/claude"), "2.1.104", "test"),
            TaskRequest(prompt="x", cwd=Path("/tmp"), model="sonnet", effort="high"),
        )
        self.assertEqual(
            claude.argv,
            ("/bin/claude", "-p", "--output-format", "stream-json", "--model", "sonnet", "--effort", "high", "x"),
        )
        self.assertNotIn("--bare", claude.argv)
        self.assertNotIn("--strict-mcp-config", claude.argv)
        codex_default = build_invocation(
            DetectedWorker("codex", Path("/bin/codex"), "0.153.4", "test"),
            TaskRequest(prompt="x", cwd=Path("/tmp")),
        )
        self.assertNotIn("--sandbox", codex_default.argv)
        with self.assertRaises(UnsupportedOverrideError):
            build_invocation(
                DetectedWorker("claude", Path("/bin/claude"), "2.1.104", "test"),
                TaskRequest(prompt="x", cwd=Path("/tmp"), sandbox="workspace-write"),
            )

    def test_structured_output_classification_separates_process_and_native_outcome(self) -> None:
        cases = (
            (
                "success",
                0,
                '{"type":"thread.started"}\n{"type":"turn.completed","text":"done"}\n',
                "success",
            ),
            (
                "auth",
                1,
                '{"type":"error","error":{"code":"authentication_error"}}\n',
                "auth_required",
            ),
            (
                "denied",
                0,
                '{"status":"ERROR","error":{"code":"tool_denied"}}\n',
                "tool_denied",
            ),
            ("empty", 0, "", "empty_output"),
            ("malformed", 0, '{"type":"turn.completed"\n', "malformed_output"),
        )
        for mode, returncode, output, expected in cases:
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    fake = self._fake_worker(root, output, returncode=returncode)
                    result = run_task(
                        DetectedWorker("codex", fake, "0.153.4", "test"),
                        TaskRequest(prompt="ignored", cwd=root, timeout=1),
                    )
                    self.assertEqual(result["native"]["outcome"], expected)
                    self.assertEqual(result["process"]["exit_code"], returncode)
                    self.assertEqual(result["process"]["completed"], True)
                    self.assertEqual(result["result_schema_version"], RESULT_SCHEMA_VERSION)
                    validate_result(result)

    def test_adapter_specific_nested_events_and_stderr_are_classified(self) -> None:
        fixtures = (
            (
                "codex",
                "0.153.4",
                '{"type":"item.completed","item":{"type":"agent_message","text":"codex claim"}}\n{"type":"turn.completed"}\n',
                "success",
                "codex claim",
            ),
            (
                "claude",
                "2.1.104",
                '{"type":"result","subtype":"success","result":"claude claim"}\n',
                "success",
                "claude claim",
            ),
            (
                "agy",
                "1.1.27",
                '{"event":"result","result":{"status":"SUCCESS","response":"agy claim"}}\n',
                "success",
                "agy claim",
            ),
        )
        for name, version, output, outcome, claim in fixtures:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    fake = self._fake_worker(root, output, stderr="warning on stderr")
                    result = run_task(
                        DetectedWorker(name, fake, version, "test"),
                        TaskRequest(prompt="ignored", cwd=root, timeout=1),
                    )
                    self.assertEqual(result["native"]["outcome"], outcome)
                    self.assertIn(claim, json.dumps(result["native"]["claims"]))
                    self.assertEqual(result["evidence"]["stderr"], "warning on stderr")
                    self.assertNotEqual(result["native"]["outcome"], "malformed_output")

    def test_fake_executable_receives_argv_and_cwd_without_shell_interpolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args_file = root / "args.json"
            fake = root / "fake-worker.py"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['ARGS_FILE']).write_text(json.dumps(sys.argv[1:]))\n"
                "print(json.dumps({'status': 'SUCCESS'}))\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            worker = DetectedWorker("agy", fake, "1.1.27", "test")
            result = run_task(
                worker,
                TaskRequest(prompt="$(touch SHOULD_NOT_EXIST)", cwd=root, timeout=2),
                environment={"ARGS_FILE": str(args_file)},
            )
            self.assertEqual(result["process"]["exit_code"], 0)
            self.assertFalse((root / "SHOULD_NOT_EXIST").exists())
            self.assertEqual(json.loads(args_file.read_text(encoding="utf-8"))[-1], "$(touch SHOULD_NOT_EXIST)")

    def test_timeout_cancellation_and_missing_executable_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = self._fake_worker(root, '{"status":"SUCCESS"}', sleep=1)
            worker = DetectedWorker("agy", fake, "1.1.27", "test")
            timeout = run_task(
                worker,
                TaskRequest(prompt="ignored", cwd=root, timeout=0.01),
            )
            self.assertEqual(timeout["process"]["classification"], "timeout")
            self.assertEqual(timeout["native"]["outcome"], "timeout")

            cancel = threading.Event()
            cancel.set()
            canceled = run_task(
                worker,
                TaskRequest(prompt="ignored", cwd=root, timeout=1),
                cancel_event=cancel,
            )
            self.assertEqual(canceled["process"]["classification"], "canceled")
            self.assertFalse(canceled["process"]["started"])

            missing = run_task(
                DetectedWorker("agy", root / "does-not-exist", "1.1.27", "test"),
                TaskRequest(prompt="ignored", cwd=root, timeout=1),
            )
            self.assertEqual(missing["process"]["classification"], "executable_missing")

    def test_result_schema_is_packaged_nested_and_acceptance_is_not_inferred(self) -> None:
        schema_path = resources.files("harness_relay.resources").joinpath("result.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["result_schema_version"]["const"], 1)
        validator = jsonschema.Draft202012Validator(schema)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_task(
                DetectedWorker("agy", self._fake_worker(root, '{"status":"SUCCESS","result":"worker claim"}'), "1.1.27", "test"),
                TaskRequest(prompt="ignored", cwd=root, timeout=1),
            )
            self.assertEqual(list(validator.iter_errors(result)), [])
            self.assertEqual(result["acceptance"]["status"], "not_checked")
            self.assertFalse(result["validation"]["executed"])
            self.assertEqual(result["validation"]["outcome"], "not_run")
            self.assertTrue(result["native"]["claims"])
            result["process"]["exit_code"] = "0"
            with self.assertRaises(ValueError):
                validate_result(result)

            result = run_task(
                DetectedWorker("agy", self._fake_worker(root, '{"status":"SUCCESS"}'), "1.1.27", "test"),
                TaskRequest(prompt="ignored", cwd=root, timeout=1),
            )
            result["validation"]["process"] = {
                "started": True,
                "completed": True,
                "exit_code": "0",
                "classification": "completed",
            }
            with self.assertRaises(ValueError):
                validate_result(result)

            result = run_task(
                DetectedWorker("agy", self._fake_worker(root, '{"status":"SUCCESS"}'), "1.1.27", "test"),
                TaskRequest(prompt="ignored", cwd=root, timeout=1),
            )
            result["evidence"]["events"] = [3]
            with self.assertRaises(ValueError):
                validate_result(result)

    def test_git_evidence_tracks_committed_staged_unstaged_untracked_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._git(repo, "init", "-q")
            (repo / "base file.txt").write_text("base\n", encoding="utf-8")
            (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            self._git(repo, "add", "--", "base file.txt", "tracked.txt")
            self._git(repo, "commit", "-qm", "base")
            base = capture_base(repo)

            (repo / "base file.txt").write_text("staged\n", encoding="utf-8")
            self._git(repo, "add", "--", "base file.txt")
            (repo / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
            (repo / "untracked name.txt").write_text("new\n", encoding="utf-8")
            staged = capture_snapshot(repo, base)
            self.assertTrue(staged["staged"])
            self.assertTrue(staged["unstaged"])
            self.assertTrue(staged["untracked"])
            self.assertIn("untracked name.txt", staged["untracked_files"])

            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-qm", "worker")
            after_commit = capture_snapshot(repo, base)
            self.assertEqual(after_commit["head"], capture_base(repo))
            self.assertTrue(after_commit["committed_delta"])
            self.assertTrue(after_commit["clean"])
            self.assertIn("base file.txt", json.dumps(after_commit))

            validation = repo / "validation.py"
            validation.write_text(
                "from pathlib import Path\nPath('validation output.txt').write_text('validation\\n')\n",
                encoding="utf-8",
            )
            result = run_task(
                DetectedWorker("agy", self._fake_worker(repo, '{"status":"SUCCESS"}'), "1.1.27", "test"),
                TaskRequest(prompt="ignored", cwd=repo, timeout=2),
                validation=ValidationRequest((sys.executable, str(validation)), repo),
                base_sha=base,
            )
            self.assertTrue(result["validation"]["executed"])
            self.assertEqual(result["validation"]["outcome"], "passed")
            self.assertIn("validation output.txt", json.dumps(result["git"]["after_validation"]))

    def test_git_evidence_reports_rename_and_delete_for_status_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self._git(repo, "init", "-q")
            (repo / "old name.txt").write_text("old\n", encoding="utf-8")
            (repo / "delete me.txt").write_text("delete\n", encoding="utf-8")
            self._git(repo, "add", "--", "old name.txt", "delete me.txt")
            self._git(repo, "commit", "-qm", "base")
            base = capture_base(repo)
            self._git(repo, "mv", "old name.txt", "new name.txt")
            self._git(repo, "rm", "--", "delete me.txt")

            snapshot = capture_snapshot(repo, base)
            self.assertTrue(snapshot["staged"])
            staged = snapshot["staged_changes"]
            self.assertTrue(any(item["status"].startswith("R") and item["path"] == "new name.txt" and item["old_path"] == "old name.txt" for item in staged))
            self.assertTrue(any(item["status"].startswith("D") and item["path"] == "delete me.txt" for item in staged))
            status = snapshot["status"]
            self.assertTrue(any(item["status"].startswith("R") and item["path"] == "new name.txt" and item["old_path"] == "old name.txt" for item in status))

            self._git(repo, "commit", "-qm", "worker")
            committed = capture_snapshot(repo, base)
            self.assertTrue(any(item["status"].startswith("R") and item["path"] == "new name.txt" and item["old_path"] == "old name.txt" for item in committed["committed_delta"]))
            self.assertTrue(any(item["status"].startswith("D") and item["path"] == "delete me.txt" for item in committed["committed_delta"]))
            self.assertTrue(committed["clean"])

    def test_git_evidence_failure_is_explicit_in_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            (root / "base.txt").write_text("base\n", encoding="utf-8")
            self._git(root, "add", "--", "base.txt")
            self._git(root, "commit", "-qm", "base")
            fake = self._fake_worker(root, '{"status":"SUCCESS"}')
            from unittest import mock
            with mock.patch(
                "harness_relay.execution.capture_snapshot",
                side_effect=GitEvidenceError("capture unavailable"),
            ):
                result = run_task(
                    DetectedWorker("agy", fake, "1.1.27", "test"),
                    TaskRequest(prompt="ignored", cwd=root, timeout=1),
                )
            self.assertTrue(result["git"]["repository"])
            self.assertIsNone(result["git"]["after_worker"])
            self.assertTrue(result["git"]["errors"])

    @staticmethod
    def _git(cwd: Path, *args: str) -> None:
        subprocess.run(
            (
                "git",
                "-c",
                "user.name=root",
                "-c",
                "user.email=root@agent.caminotto.it",
                "-c",
                "commit.gpgsign=false",
                *args,
            ),
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @staticmethod
    def _fake_worker(
        root: Path, output: str, *, returncode: int = 0, sleep: float = 0, stderr: str = ""
    ) -> Path:
        worker = root / "fake-worker.py"
        worker.write_text(
            f"#!{sys.executable}\n"
            "import os, sys, time\n"
            f"time.sleep({sleep!r})\n"
            f"sys.stdout.write({output!r})\n"
            f"sys.stderr.write({stderr!r})\n"
            f"sys.exit({returncode})\n",
            encoding="utf-8",
        )
        worker.chmod(0o755)
        return worker


if __name__ == "__main__":
    unittest.main()
