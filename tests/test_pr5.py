"""Offline public-alpha and installed-process acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class Pr5Test(unittest.TestCase):
    def test_installed_mcp_process_delegates_to_fake_worker_in_owned_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            self._git(repository, "init")
            (repository / "fact.txt").write_text("fixture fact\n", encoding="utf-8")
            self._git(repository, "add", "fact.txt")
            self._git(repository, "-c", "user.name=root", "-c", "user.email=root@agent.caminotto.it", "-c", "commit.gpgsign=false", "commit", "-m", "base")
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

            process = subprocess.Popen(
                (sys.executable, "-m", "harness_relay", "mcp", "--stdio", "--config", str(config)),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert process.stdin is not None and process.stdout is not None
            self._send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}})
            self.assertEqual(json.loads(process.stdout.readline())["id"], 1)
            self._send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            tools = json.loads(process.stdout.readline())["result"]["tools"]
            self.assertIn("delegate_agy", [tool["name"] for tool in tools])
            self._send(process, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "delegate_agy", "arguments": {"prompt": "fixture task", "repository": str(repository), "base_sha": base}}})
            response = json.loads(process.stdout.readline())
            self.assertEqual(response["id"], 3)
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload["state"], "completed")
            self.assertTrue((Path(payload["workspace"]) / "worker.txt").is_file())
            self.assertEqual(self._git(repository, "rev-parse", "HEAD"), base)
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
            process.stdout.close()
            if process.stderr is not None:
                error = process.stderr.read()
                process.stderr.close()
                self.assertEqual(error, "")

    @staticmethod
    def _send(process: subprocess.Popen[str], value: dict[str, object]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(value) + "\n")
        process.stdin.flush()

    @staticmethod
    def _git(path: Path, *args: str) -> str:
        return subprocess.run(("git", "-C", str(path), *args), check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


if __name__ == "__main__":
    unittest.main()
