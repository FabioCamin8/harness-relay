"""Offline tests for the installed PR-1 package foundation."""

from __future__ import annotations

import contextlib
import io
import os
from importlib import metadata, resources
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import harness_relay
from harness_relay import cli


class PackageTests(unittest.TestCase):
    def test_import_and_version(self) -> None:
        self.assertEqual(harness_relay.__version__, "0.1.0a1")
        self.assertEqual(metadata.version("harness-relay"), harness_relay.__version__)

    def test_metadata_and_package_resource(self) -> None:
        package_metadata = metadata.metadata("harness-relay")
        self.assertEqual(package_metadata["Name"], "harness-relay")
        self.assertEqual(package_metadata["License-Expression"], "MIT")
        package_root = resources.files("harness_relay")
        self.assertTrue(package_root.joinpath("__init__.py").is_file())

    def test_help_and_version(self) -> None:
        help_output = io.StringIO()
        with contextlib.redirect_stdout(help_output):
            with self.assertRaises(SystemExit) as help_exit:
                cli.main(["--help"])
        self.assertEqual(help_exit.exception.code, 0)
        self.assertIn("usage: harness-relay", help_output.getvalue())

        version_output = io.StringIO()
        with contextlib.redirect_stdout(version_output):
            with self.assertRaises(SystemExit) as version_exit:
                cli.main(["--version"])
        self.assertEqual(version_exit.exception.code, 0)
        self.assertEqual(version_output.getvalue().strip(), "harness-relay 0.1.0a1")

    def test_installed_console_script_outside_checkout(self) -> None:
        executable = Path(sys.executable).with_name("harness-relay")
        self.assertTrue(executable.is_file(), "run this test in the wheel's virtual environment")

        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["HOME"] = temp_dir
            env["PYTHONNOUSERSITE"] = "1"
            env.pop("PYTHONPATH", None)
            for arguments, expected in (
                (("--help",), "usage: harness-relay"),
                (("--version",), "harness-relay 0.1.0a1"),
            ):
                result = subprocess.run(
                    [executable, *arguments],
                    cwd=temp_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
            self.assertEqual(list(Path(temp_dir).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
