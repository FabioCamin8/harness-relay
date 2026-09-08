"""Offline G09-G13 tests for workspace, lifecycle, MCP, and doctor."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from harness_relay.adapters import DetectedWorker, TaskRequest
from harness_relay.configuration import parse_config, UserPaths
from harness_relay.doctor import diagnose
from harness_relay.execution import REENTRY_ENV, ValidationRequest, run_task
from harness_relay.mcp import McpServer, PROTOCOL_VERSION
from harness_relay.opencode import LEGACY_MCP_ENTRY, MCP_ENTRY, integrate
from harness_relay.workspace import (
    WorkspaceError,
    capture_integrity,
    cleanup_worktree,
    integrity_changed,
    repository_identity,
    reserve_worktree,
)


class Pr4Test(unittest.TestCase):
    def test_repository_identity_and_atomic_reservation_reject_collisions_and_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a" / "same"; second = root / "b" / "same"
            self._repo(first); self._repo(second)
            self.assertNotEqual(repository_identity(first), repository_identity(second))
            managed = root / "managed"
            base = self._git(first, "rev-parse", "HEAD")
            reservation = reserve_worktree(managed, first, base, "run-1")
            self.assertTrue(reservation.worktree.is_dir())
            with self.assertRaises(WorkspaceError):
                reserve_worktree(managed, first, base, "run-1")
            with self.assertRaises(WorkspaceError):
                reserve_worktree(managed, first, base, "../escape")

            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(root / "outside", target_is_directory=True)
            with self.assertRaisesRegex(WorkspaceError, "symlink"):
                reserve_worktree(linked_parent / "managed", first, base, "escaped")

    def test_cleanup_preserves_dirty_work_and_integrity_detects_dirty_file_and_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; self._repo(source)
            base = self._git(source, "rev-parse", "HEAD")
            reservation = reserve_worktree(root / "managed", source, base, "dirty")
            before = capture_integrity(reservation.worktree)
            (reservation.worktree / "tracked.txt").write_text("changed\n", encoding="utf-8")
            after = capture_integrity(reservation.worktree)
            self.assertTrue(integrity_changed(before, after))
            with self.assertRaises(WorkspaceError): cleanup_worktree(reservation)
            self.assertEqual((reservation.worktree / "tracked.txt").read_text(), "changed\n")
            self._git(reservation.worktree, "add", "tracked.txt")
            self._git(reservation.worktree, "-c", "commit.gpgsign=false", "commit", "-m", "next")
            self.assertNotEqual(after["head"], capture_integrity(reservation.worktree)["head"])
            with self.assertRaisesRegex(WorkspaceError, "committed work"):
                cleanup_worktree(reservation)

    def test_integrity_includes_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self._repo(root)
            (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            (root / "ignored.txt").write_text("before\n", encoding="utf-8")
            before = capture_integrity(root)
            (root / "ignored.txt").write_text("after\n", encoding="utf-8")
            self.assertTrue(integrity_changed(before, capture_integrity(root)))

    def test_process_group_timeout_and_recursion_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); pid_file = root / "child.pid"; fake = root / "agy"
            fake.write_text(f"#!{sys.executable}\nimport os,subprocess,time\np=subprocess.Popen(['sleep','30'])\nopen(os.environ['PID_FILE'],'w').write(str(p.pid))\nprint('{{\"status\":\"WAITING\"}}',flush=True)\ntime.sleep(30)\n", encoding="utf-8")
            fake.chmod(0o755)
            result = run_task(DetectedWorker("agy", fake, "1.1.27", "test"), TaskRequest("x", root, timeout=.15), environment={"PID_FILE": str(pid_file)})
            self.assertEqual(result["process"]["classification"], "timeout")
            child_pid = int(pid_file.read_text())
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and Path(f"/proc/{child_pid}").exists(): time.sleep(.02)
            if Path(f"/proc/{child_pid}/stat").exists():
                self.assertEqual(Path(f"/proc/{child_pid}/stat").read_text().split()[2], "Z")
            with self.assertRaisesRegex(RuntimeError, "recursion"):
                run_task(DetectedWorker("agy", fake, "1.1.27", "test"), TaskRequest("x", root), environment={REENTRY_ENV: "1"})

    def test_doctor_is_read_only_inference_free_and_skips_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); marker = root / "called"; fake = root / "codex"
            fake.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('called')\nprint('codex-cli 0.153.4')\n", encoding="utf-8"); fake.chmod(0o755)
            disabled = parse_config({"version": 1, "workers": {"codex": {"enabled": False, "executable": str(fake)}}})
            report = diagnose(disabled)
            self.assertIsNone(report["workers"]["codex"]["detected"]); self.assertFalse(marker.exists())
            enabled = parse_config({"version": 1, "workers": {"codex": {"enabled": True, "executable": str(fake)}}})
            report = diagnose(enabled)
            self.assertTrue(report["workers"]["codex"]["detected"]); self.assertFalse(report["inference_called"])

    def test_mcp_lifecycle_enabled_only_tools_schema_errors_and_version_negotiation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = parse_config({"version": 1, "workers": {"codex": {"enabled": True, "executable": "/missing"}}})
            output = io.StringIO(); server = McpServer(config, UserPaths.from_environment(home=directory), output)
            server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            server.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "unsupported"}})
            server.handle({"jsonrpc": "2.0", "id": 20, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION}})
            server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
            server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
            server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "delegate_claude", "arguments": {}}})
            server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "delegate_codex", "arguments": {"prompt": "x"}}})
            messages = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(messages[0]["error"]["code"], -32600)
            self.assertEqual(messages[1]["error"]["code"], -32602)
            self.assertEqual(messages[2]["result"]["protocolVersion"], PROTOCOL_VERSION)
            names = [tool["name"] for tool in messages[3]["result"]["tools"]]
            self.assertIn("delegate_codex", names); self.assertNotIn("delegate_claude", names)
            self.assertTrue(all(tool["inputSchema"]["type"] == "object" for tool in messages[3]["result"]["tools"]))
            self.assertEqual(messages[4]["error"]["code"], -32602)
            self.assertEqual(messages[5]["error"]["code"], -32602)
            server.handle({"jsonrpc": "2.0", "id": [], "method": "tools/list"})
            server.handle({"jsonrpc": "2.0", "id": {}, "method": "tools/list"})
            invalid_ids = [json.loads(line) for line in output.getvalue().splitlines()][-2:]
            self.assertTrue(all(item["error"]["code"] == -32600 for item in invalid_ids))
            server.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "delegate_codex", "arguments": {"prompt": "x", "repository": "/tmp/repo", "base_sha": "abcd", "validation": {"argv": ["bad\x00argument"]}}}})
            self.assertEqual(json.loads(output.getvalue().splitlines()[-1])["error"]["code"], -32602)
            server.pool.shutdown(wait=True)

    def test_mcp_status_and_cancel_remain_responsive_during_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); repo = root / "repo"; self._repo(repo); fake = root / "agy"
            fake.write_text(f"#!{sys.executable}\nimport sys,time\nif '--version' in sys.argv: print('agy 1.1.27'); raise SystemExit\nprint('{{\"status\":\"WAITING\"}}',flush=True)\ntime.sleep(30)\n", encoding="utf-8"); fake.chmod(0o755)
            config = parse_config({"version": 1, "workers": {"agy": {"enabled": True, "executable": str(fake)}}})
            output = io.StringIO(); server = McpServer(config, UserPaths.from_environment(home=root), output)
            server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION}})
            server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
            server.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "delegate_agy", "arguments": {"prompt": "x", "repository": str(repo), "base_sha": self._git(repo, "rev-parse", "HEAD"), "timeout": 5}}})
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not server.active: time.sleep(.01)
            run_id = next(iter(server.active.values()))[0]
            server.handle({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "run_status", "arguments": {"run_id": run_id}}})
            server.handle({"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "cancel_run", "arguments": {"run_id": run_id}}})
            server.pool.shutdown(wait=True)
            self.assertEqual(server.results[run_id]["state"], "canceled")
            ids = {json.loads(line).get("id") for line in output.getvalue().splitlines()}
            self.assertIn(11, ids); self.assertIn(12, ids); self.assertNotIn(10, ids)
            state_file = server.state_dir / f"{run_id}.json"
            self.assertTrue(state_file.is_file())
            restarted_output = io.StringIO(); restarted = McpServer(config, UserPaths.from_environment(home=root), restarted_output)
            restarted.initialized = restarted.ready = True
            restarted.handle({"jsonrpc": "2.0", "id": 13, "method": "tools/call", "params": {"name": "run_status", "arguments": {"run_id": run_id}}})
            self.assertEqual(json.loads(restarted_output.getvalue())["result"]["isError"], False)
            restarted.pool.shutdown(wait=True)

    def test_mcp_rejects_excess_work_instead_of_queueing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); repo = root / "repo"; self._repo(repo); fake = root / "agy"
            fake.write_text(f"#!{sys.executable}\nimport sys,time\nif '--version' in sys.argv: print('agy 1.1.27'); raise SystemExit\nprint('{{\"status\":\"WAITING\"}}',flush=True)\ntime.sleep(30)\n", encoding="utf-8"); fake.chmod(0o755)
            config = parse_config({"version": 1, "workers": {"agy": {"enabled": True, "executable": str(fake)}}})
            output = io.StringIO(); server = McpServer(config, UserPaths.from_environment(home=root), output)
            server.initialized = server.ready = True
            arguments = {"prompt": "x", "repository": str(repo), "base_sha": self._git(repo, "rev-parse", "HEAD"), "timeout": 5}
            server.handle({"jsonrpc": "2.0", "id": 20, "method": "tools/call", "params": {"name": "delegate_agy", "arguments": arguments}})
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not server.active: time.sleep(.01)
            server.handle({"jsonrpc": "2.0", "id": 21, "method": "tools/call", "params": {"name": "delegate_agy", "arguments": arguments}})
            busy = [json.loads(line) for line in output.getvalue().splitlines() if json.loads(line).get("id") == 21]
            self.assertEqual(len(busy), 1); self.assertTrue(busy[0]["result"]["isError"])
            self.assertEqual(json.loads(busy[0]["result"]["content"][0]["text"])["state"], "busy")
            next(iter(server.active.values()))[1].set()
            server.pool.shutdown(wait=True)

    def test_validation_evidence_is_redacted_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fake = root / "agy"
            fake.write_text(
                f"#!{sys.executable}\nprint('{{\"status\":\"SUCCESS\"}}')\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            result = run_task(
                DetectedWorker("agy", fake, "1.1.27", "test"),
                TaskRequest("x", root),
                validation=ValidationRequest(
                    (sys.executable, "-c", "print('token=SECRET_VALUE')"), root
                ),
            )
            self.assertNotIn("SECRET_VALUE", result["validation"]["stdout"])
            self.assertIn("[REDACTED]", result["validation"]["stdout"])

    def test_parent_disconnect_cancels_and_persists_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); repo = root / "repo"; self._repo(repo); fake = root / "agy"
            fake.write_text(
                f"#!{sys.executable}\nimport sys,time\nif '--version' in sys.argv: print('agy 1.1.27'); raise SystemExit\nprint('{{\"status\":\"WAITING\"}}', flush=True)\ntime.sleep(30)\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            config = parse_config({"version": 1, "workers": {"agy": {"enabled": True, "executable": str(fake)}}})
            request = "\n".join(
                json.dumps(item)
                for item in (
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "delegate_agy", "arguments": {"prompt": "x", "repository": str(repo), "base_sha": self._git(repo, "rev-parse", "HEAD")}}},
                )
            ).encode() + b"\n"
            server = McpServer(config, UserPaths.from_environment(home=root), io.StringIO())
            server.serve(io.BytesIO(request))
            run_id = next(iter(server.results))
            self.assertEqual(server.results[run_id]["state"], "canceled")
            stored = json.loads((server.state_dir / f"{run_id}.json").read_text())
            self.assertEqual(stored["state"], "canceled")

    def test_terminal_persist_failure_does_not_leave_running_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); repo = root / "repo"; self._repo(repo); fake = root / "agy"
            fake.write_text(
                f"#!{sys.executable}\nimport sys\nif '--version' in sys.argv: print('agy 1.1.27'); raise SystemExit\nprint('{{\"status\":\"SUCCESS\"}}')\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            config = parse_config({"version": 1, "workers": {"agy": {"enabled": True, "executable": str(fake)}}})
            server = McpServer(config, UserPaths.from_environment(home=root), io.StringIO())
            server.initialized = server.ready = True
            real_persist = server._persist
            calls = 0

            def fail_terminal(run_id: str) -> None:
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("injected terminal write failure")
                real_persist(run_id)

            with mock.patch.object(server, "_persist", side_effect=fail_terminal):
                server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "delegate_agy", "arguments": {"prompt": "x", "repository": str(repo), "base_sha": self._git(repo, "rev-parse", "HEAD")}}})
                server.pool.shutdown(wait=True)
            run_id = next(iter(server.results))
            self.assertEqual(server.results[run_id]["state"], "failed")
            stored = json.loads((server.state_dir / f"{run_id}.json").read_text())
            self.assertEqual(stored["state"], "failed")

    def test_pr2_owned_legacy_mcp_requires_explicit_upgrade_authority(self) -> None:
        source = json.dumps({"mcp": {"harness-relay": LEGACY_MCP_ENTRY}})
        with self.assertRaises(Exception): integrate(source, "/instructions")
        upgraded, _, _ = integrate(source, "/instructions", allow_legacy_upgrade=True)
        self.assertEqual(json.loads(upgraded)["mcp"]["harness-relay"], MCP_ENTRY)

    def _repo(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True); self._git(path, "init")
        (path / "tracked.txt").write_text("base\n", encoding="utf-8")
        self._git(path, "add", "tracked.txt")
        self._git(path, "-c", "commit.gpgsign=false", "commit", "-m", "base")

    @staticmethod
    def _git(path: Path, *args: str) -> str:
        identity: tuple[str, ...] = ()
        name = subprocess.run(("git", "-C", str(path), "config", "--get", "user.name"), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
        email = subprocess.run(("git", "-C", str(path), "config", "--get", "user.email"), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
        if not name or not email:
            identity = ("-c", "user.name=HarnessRelay Fixture", "-c", "user.email=fixture@example.invalid")
        return subprocess.run(("git", "-C", str(path), *identity, *args), check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


if __name__ == "__main__": unittest.main()
