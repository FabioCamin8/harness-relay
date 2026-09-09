"""Offline tests for the universal caller-neutral bridge surface."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from harness_relay import cli
from harness_relay.configuration import UserPaths, parse_config
from harness_relay.mcp import McpServer


class Pr8Test(unittest.TestCase):
    def test_list_reports_supported_enabled_and_detected_without_inference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "inference-called"
            fake = root / "codex"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "from pathlib import Path\n"
                "if '--version' in sys.argv:\n"
                "    print('codex-cli 0.153.4')\n"
                "    raise SystemExit\n"
                f"Path({str(marker)!r}).write_text('called')\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "workers": {
                            "codex": {"enabled": True, "executable": str(fake)},
                            "agy": {"enabled": False, "executable": str(fake)},
                        },
                    }
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(["list", "--json", "--config", str(config)]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(set(report), {"config_valid", "inference_called", "workers"})
            self.assertFalse(report["inference_called"])
            self.assertEqual(report["workers"]["codex"]["supported"], True)
            self.assertEqual(report["workers"]["codex"]["enabled"], True)
            self.assertEqual(report["workers"]["codex"]["detected"], True)
            self.assertEqual(report["workers"]["codex"]["version"], "0.153.4")
            self.assertEqual(report["workers"]["agy"]["supported"], True)
            self.assertEqual(report["workers"]["agy"]["enabled"], False)
            self.assertIsNone(report["workers"]["agy"]["detected"])
            self.assertFalse(marker.exists())

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(["list", "--config", str(config)]), 0)
            self.assertIn("codex: supported=true enabled=true detected=true", output.getvalue())
            self.assertIn("agy: supported=true enabled=false detected=not-probed", output.getvalue())

    def test_generic_mcp_delegate_requires_one_enabled_worker_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            self._git(repository, "init")
            (repository / "source.txt").write_text("source\n", encoding="utf-8")
            self._git(repository, "add", "source.txt")
            self._git(repository, "-c", "commit.gpgsign=false", "commit", "-m", "base")
            base = self._git(repository, "rev-parse", "HEAD")

            fake = root / "agy"
            fake.write_text(
                f"#!{sys.executable}\n"
                "import json\n"
                "import pathlib\n"
                "import sys\n"
                "if '--version' in sys.argv:\n"
                "    print('agy 1.1.27')\n"
                "    raise SystemExit\n"
                "pathlib.Path('worker.txt').write_text('delegated\\n')\n"
                "print(json.dumps({'status': 'SUCCESS'}))\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            config = parse_config(
                {
                    "version": 1,
                    "workers": {
                        "agy": {"enabled": True, "executable": str(fake)},
                        "codex": {"enabled": False},
                    },
                    "paths": {"worktrees": str(root / "worktrees")},
                }
            )
            output = io.StringIO()
            server = McpServer(config, UserPaths.from_environment(home=root), output)
            server.initialized = server.ready = True

            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                }
            )
            listing = json.loads(output.getvalue().splitlines()[-1])
            tools = {tool["name"]: tool for tool in listing["result"]["tools"]}
            self.assertIn("delegate", tools)
            self.assertIn("delegate_agy", tools)
            self.assertNotIn("delegate_codex", tools)
            self.assertIn("worker", tools["delegate"]["inputSchema"]["required"])

            for request_id, worker in ((2, "codex"), (3, "missing")):
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {
                            "name": "delegate",
                            "arguments": {
                                "worker": worker,
                                "prompt": "run once",
                                "repository": str(repository),
                                "base_sha": base,
                            },
                        },
                    }
                )
                response = json.loads(output.getvalue().splitlines()[-1])
                self.assertEqual(response["error"]["code"], -32602)
                self.assertEqual(response["error"]["message"], "unknown or disabled worker")

            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "delegate",
                        "arguments": {
                            "prompt": "missing worker",
                            "repository": str(repository),
                            "base_sha": base,
                        },
                    },
                }
            )
            response = json.loads(output.getvalue().splitlines()[-1])
            self.assertEqual(response["error"]["code"], -32602)

            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "delegate",
                        "arguments": {
                            "worker": "agy",
                            "prompt": "run once",
                            "repository": str(repository),
                            "base_sha": base,
                        },
                    },
                }
            )
            server.pool.shutdown(wait=True)
            response = json.loads(output.getvalue().splitlines()[-1])
            self.assertEqual(response["id"], 5)
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload["state"], "completed")
            workspace = Path(payload["workspace"])
            self.assertEqual((workspace / "worker.txt").read_text(encoding="utf-8"), "delegated\n")
            self.assertFalse((repository / "worker.txt").exists())
            self.assertEqual(self._git(repository, "rev-parse", "HEAD"), base)

    @staticmethod
    def _git(cwd: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
