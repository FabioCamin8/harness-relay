"""Offline public-alpha and installed-process acceptance tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from harness_relay.jsonc import parse as parse_jsonc


class Pr5Test(unittest.TestCase):
    def test_jsonc_leading_comments_precede_the_document_root(self) -> None:
        for source in (
            '// leading line comment\n{"enabled": true}\n',
            '/* leading block comment */\n{"enabled": true}\n',
        ):
            with self.subTest(source=source):
                self.assertEqual(parse_jsonc(source), {"enabled": True})

    def test_direct_delegate_uses_explicit_base_worktree_instead_of_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            self._git(repository, "init")
            (repository / "fact.txt").write_text("fixture fact\n", encoding="utf-8")
            self._git(repository, "add", "fact.txt")
            self._git(repository, "-c", "commit.gpgsign=false", "commit", "-m", "base")
            base = self._git(repository, "rev-parse", "HEAD")

            fake = root / "agy"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import json, pathlib, sys\n"
                "if '--version' in sys.argv:\n"
                " print('agy 1.1.27'); raise SystemExit\n"
                "pathlib.Path('cli-worker.txt').write_text('retained\\n')\n"
                "print(json.dumps({'status': 'SUCCESS'}))\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "workers": {"agy": {"enabled": True, "executable": str(fake)}},
                        "paths": {"worktrees": str(root / "worktrees")},
                    }
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["HOME"] = str(root / "home")
            environment["XDG_CONFIG_HOME"] = str(root / "xdg-config")
            environment["XDG_DATA_HOME"] = str(root / "xdg-data")
            environment["XDG_STATE_HOME"] = str(root / "xdg-state")
            result = self._run(
                (
                    sys.executable,
                    "-m",
                    "harness_relay",
                    "delegate",
                    "--config",
                    str(config),
                    "--worker",
                    "agy",
                    "--prompt=--help",
                    "--repository",
                    str(repository),
                    "--base-sha",
                    base,
                ),
                environment,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["process"]["classification"], "completed")
            workspace = Path(payload["invocation"]["cwd"])
            self.assertTrue((workspace / "cli-worker.txt").is_file())
            self.assertFalse((repository / "cli-worker.txt").exists())
            self.assertEqual(self._git(repository, "rev-parse", "HEAD"), base)

    def test_installed_mcp_process_delegates_to_fake_worker_in_owned_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            self._git(repository, "init")
            (repository / "fact.txt").write_text("fixture fact\n", encoding="utf-8")
            self._git(repository, "add", "fact.txt")
            self._git(repository, "-c", "commit.gpgsign=false", "commit", "-m", "base")
            base = self._git(repository, "rev-parse", "HEAD")

            fake = root / "agy"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import json, pathlib, sys\n"
                "if '--version' in sys.argv:\n"
                " print('agy 1.1.27'); raise SystemExit\n"
                "pathlib.Path('worker.txt').write_text('retained work\\n')\n"
                "print(json.dumps({'status':'SUCCESS','result':{'response':'done'}}))\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            config = root / "config.json"
            config.write_text(json.dumps({"version": 1, "workers": {"agy": {"enabled": True, "executable": str(fake)}}, "paths": {"worktrees": str(root / "worktrees")}}), encoding="utf-8")

            home = root / "home"
            home.mkdir()
            opencode = root / "opencode.jsonc"
            opencode.write_text('{\n  // retained user setting\n  "model": "provider/master-a",\n  "theme": "dark"\n}\n', encoding="utf-8")
            environment = os.environ.copy()
            environment.update(
                HOME=str(home),
                XDG_CONFIG_HOME=str(root / "xdg-config"),
                XDG_DATA_HOME=str(root / "xdg-data"),
                XDG_STATE_HOME=str(root / "xdg-state"),
            )
            setup_command = (
                sys.executable, "-m", "harness_relay", "setup", "--non-interactive",
                "--relay-config", str(config), "--scope", "custom",
                "--opencode-config", str(opencode),
            )
            original_opencode = opencode.read_bytes()
            self._run((*setup_command, "--dry-run"), environment)
            self.assertEqual(opencode.read_bytes(), original_opencode)
            self._run(setup_command, environment)
            after_setup = opencode.read_bytes()
            generated_command = tuple(
                parse_jsonc(opencode.read_text(encoding="utf-8"))["mcp"][
                    "harness-relay"
                ]["command"]
            )
            self.assertEqual(generated_command[-2:], ("--config", str(config.resolve())))
            relay_before_model_change = config.read_bytes()
            repeated = self._run(setup_command, environment)
            self.assertIn("changed: none", repeated.stdout)
            self.assertEqual(opencode.read_bytes(), after_setup)

            opencode.write_text(
                opencode.read_text(encoding="utf-8").replace(
                    '"provider/master-a"', '"provider/master-b"'
                ),
                encoding="utf-8",
            )
            self.assertEqual(config.read_bytes(), relay_before_model_change)

            environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get(
                "PATH", ""
            )
            process = subprocess.Popen(
                generated_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            assert process.stdin is not None and process.stdout is not None
            self._send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
            self.assertEqual(json.loads(process.stdout.readline())["id"], 1)
            self._send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            tools = json.loads(process.stdout.readline())["result"]["tools"]
            self.assertIn("delegate_agy", [tool["name"] for tool in tools])
            validation_code = "from pathlib import Path; assert Path('worker.txt').read_text() == 'retained work\\n'; Path('validated.txt').write_text('validation passed\\n')"
            self._send(process, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "delegate_agy", "arguments": {"prompt": "fixture task", "repository": str(repository), "base_sha": base, "validation": {"argv": [sys.executable, "-c", validation_code], "timeout": 5}}}})
            response = json.loads(process.stdout.readline())
            self.assertEqual(response["id"], 3)
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload["state"], "completed")
            self.assertTrue((Path(payload["workspace"]) / "worker.txt").is_file())
            self.assertEqual(payload["result"]["validation"]["outcome"], "passed")
            self.assertTrue(payload["result"]["validation"]["executed"])
            self.assertTrue((Path(payload["workspace"]) / "validated.txt").is_file())
            self.assertEqual(self._git(repository, "rev-parse", "HEAD"), base)
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
            process.stdout.close()
            if process.stderr is not None:
                error = process.stderr.read()
                process.stderr.close()
                self.assertEqual(error, "")

            self._run(
                (
                    sys.executable, "-m", "harness_relay", "uninstall",
                    "--scope", "custom", "--opencode-config", str(opencode),
                ),
                environment,
            )
            preserved = opencode.read_text(encoding="utf-8")
            self.assertIn("retained user setting", preserved)
            self.assertIn('"model": "provider/master-b"', preserved)
            self.assertIn('"theme": "dark"', preserved)
            self.assertNotIn("harness-relay", preserved)
            self.assertTrue(Path(payload["workspace"]).is_dir())
            self.assertEqual(config.read_bytes(), relay_before_model_change)

    @staticmethod
    def _send(process: subprocess.Popen[str], value: dict[str, object]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(value) + "\n")
        process.stdin.flush()

    @staticmethod
    def _run(argv: tuple[str, ...], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )

    @staticmethod
    def _git(path: Path, *args: str) -> str:
        identity: tuple[str, ...] = ()
        name = subprocess.run(("git", "-C", str(path), "config", "--get", "user.name"), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
        email = subprocess.run(("git", "-C", str(path), "config", "--get", "user.email"), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
        if not name or not email:
            identity = ("-c", "user.name=HarnessRelay Fixture", "-c", "user.email=fixture@example.invalid")
        return subprocess.run(("git", "-C", str(path), *identity, *args), check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


if __name__ == "__main__":
    unittest.main()
