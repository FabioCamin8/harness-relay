"""Offline G03/G04 tests using only disposable homes and fake executables."""

from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock
from importlib import resources

import harness_relay.setup as setup_module
from harness_relay.configuration import (
    ConfigurationError,
    UserPaths,
    default_config,
    load_config,
    parse_config,
)
from harness_relay.discovery import DiscoveryError, discover_enabled
from harness_relay.opencode import MCP_ENTRY, MCP_NAME, canonical, integrate
from harness_relay.setup import SetupError, SetupOptions, run_setup
from harness_relay.uninstall import UninstallOptions, run_uninstall


class Pr2Test(unittest.TestCase):
    def test_default_config_disables_every_worker(self) -> None:
        config = default_config()
        self.assertEqual(config.enabled_workers, ())
        self.assertEqual(config.roles, {})

    def test_versioned_schema_is_packaged_as_a_resource(self) -> None:
        self.assertTrue(resources.files("harness_relay.resources").joinpath("config.schema.json").is_file())

    def test_config_is_strict_and_role_must_reference_enabled_adapter(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "unsupported config version"):
            parse_config({"version": 2})
        with self.assertRaisesRegex(ConfigurationError, "unknown adapter"):
            parse_config({"version": 1, "workers": {"openai": {"enabled": True}}})
        with self.assertRaisesRegex(ConfigurationError, "must be a boolean"):
            parse_config({"version": 1, "workers": {"codex": {"enabled": 1}}})
        with self.assertRaisesRegex(ConfigurationError, "not enabled"):
            parse_config({"version": 1, "roles": {"reviewer": "codex"}})
        config = parse_config(
            {
                "version": 1,
                "workers": {"codex": {"enabled": True}},
                "roles": {"reviewer": "codex"},
            }
        )
        self.assertEqual(config.roles, {"reviewer": "codex"})

    def test_disabled_worker_is_not_path_probed(self) -> None:
        config = parse_config(
            {
                "version": 1,
                "workers": {"codex": {"enabled": False, "executable": "/does/not/exist"}},
            }
        )
        self.assertEqual(discover_enabled(config, environ={"PATH": ""}), {})

    def test_explicit_executable_and_path_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "codex"
            codex.write_text("#!/bin/sh\nprintf 'codex-cli 0.153.4\\n'\n", encoding="utf-8")
            codex.chmod(0o755)
            explicit = parse_config(
                {
                    "version": 1,
                    "workers": {"codex": {"enabled": True, "executable": str(codex)}},
                }
            )
            found = discover_enabled(explicit, environ={"PATH": ""})["codex"]
            self.assertEqual(found.version, "0.153.4")
            by_path = parse_config({"version": 1, "workers": {"codex": {"enabled": True}}})
            found = discover_enabled(by_path, environ={"PATH": str(root)})["codex"]
            self.assertEqual(found.source, "PATH")

    def test_missing_and_unknown_worker_versions_are_actionable(self) -> None:
        config = parse_config({"version": 1, "workers": {"codex": {"enabled": True}}})
        with self.assertRaisesRegex(DiscoveryError, "not found on PATH"):
            discover_enabled(config, environ={"PATH": ""})
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "codex"
            executable.write_text("#!/bin/sh\nprintf 'codex-cli future\\n'\n", encoding="utf-8")
            executable.chmod(0o755)
            config = parse_config(
                {
                    "version": 1,
                    "workers": {"codex": {"enabled": True, "executable": str(executable)}},
                }
            )
            with self.assertRaisesRegex(DiscoveryError, "semantic version"):
                discover_enabled(config)

    def test_jsonc_integration_preserves_unrelated_content(self) -> None:
        original = '{\n  // user-owned comment\n  "theme": "dark",\n  "model": "user/provider/model",\n  "provider": "user-provider",\n  "auth": {"profile": "existing-user-auth"},\n  "mcp": {"other": {"enabled": true}},\n}\n'
        integrated, _, _ = integrate(original, "/tmp/harness-relay-instructions.md")
        self.assertIn("// user-owned comment", integrated)
        self.assertIn('"theme": "dark"', integrated)
        self.assertIn('"model": "user/provider/model"', integrated)
        self.assertIn('"provider": "user-provider"', integrated)
        self.assertIn('"auth": {"profile": "existing-user-auth"}', integrated)
        self.assertIn('"other": {"enabled": true}', integrated)
        self.assertIn('"harness-relay"', integrated)
        self.assertIn('"instructions"', integrated)

    def test_setup_dry_run_does_not_write_and_repeat_is_noop(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            original = opencode.read_text(encoding="utf-8")
            state_file = root / "state" / "harness-relay" / "setup.json"
            instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"
            plan = run_setup(
                SetupOptions(
                    relay_config=relay_config,
                    scope="custom",
                    opencode_config=opencode,
                    dry_run=True,
                ),
                environ=environment,
            )
            self.assertTrue(plan.dry_run)
            self.assertEqual(opencode.read_text(encoding="utf-8"), original)
            self.assertFalse(state_file.exists())
            self.assertFalse(instruction.exists())

            applied = run_setup(
                SetupOptions(
                    relay_config=relay_config,
                    scope="custom",
                    opencode_config=opencode,
                ),
                environ=environment,
            )
            self.assertTrue(applied.changed)
            after_first = opencode.read_text(encoding="utf-8")
            repeated = run_setup(
                SetupOptions(
                    relay_config=relay_config,
                    scope="custom",
                    opencode_config=opencode,
                ),
                environ=environment,
            )
            self.assertFalse(repeated.changed)
            self.assertEqual(opencode.read_text(encoding="utf-8"), after_first)

    def test_uninstall_preserves_unrelated_and_edited_owned_content(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"
            instruction.write_text("user-edited HarnessRelay guidance\n", encoding="utf-8")
            configured = opencode.read_text(encoding="utf-8")
            configured = configured.replace('"theme":"dark"', '"theme":"light"')
            opencode.write_text(configured, encoding="utf-8")
            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertTrue(plan.changed)
            result = opencode.read_text(encoding="utf-8")
            self.assertIn("user-owned comment", result)
            self.assertIn('"theme":"light"', result)
            self.assertNotIn(MCP_NAME, result)
            self.assertNotIn(str(instruction), result)
            self.assertEqual(instruction.read_text(encoding="utf-8"), "user-edited HarnessRelay guidance\n")

    def test_uninstall_preserves_edited_mcp_entry(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            configured = opencode.read_text(encoding="utf-8").replace(
                '"enabled":true', '"enabled":false'
            )
            opencode.write_text(configured, encoding="utf-8")
            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertIn("mcp.harness-relay", " ".join(plan.preserved_user_edits))
            self.assertIn(MCP_NAME, opencode.read_text(encoding="utf-8"))

    def test_higher_precedence_scope_conflict_is_reported(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            project = root / "project"
            project.mkdir()
            (project / "opencode.json").write_text(
                '{"mcp":{"harness-relay":{"type":"remote","url":"user"}}}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SetupError, "higher-precedence"):
                run_setup(
                    SetupOptions(
                        relay_config=relay_config,
                        scope="custom",
                        opencode_config=opencode,
                        project_dir=project,
                    ),
                    environ=environment,
                )

    def test_atomic_failure_leaves_existing_config_unchanged(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            original = opencode.read_bytes()
            with mock.patch("harness_relay.setup.os.replace", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
                        ),
                        environ=environment,
                    )
            self.assertEqual(opencode.read_bytes(), original)
            self.assertFalse(list(opencode.parent.glob(".*.tmp")))

    def test_interrupted_state_write_is_recoverable_on_retry(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            real_replace = setup_module.os.replace
            calls = 0

            def fail_state_write(source, target):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("injected state interruption")
                return real_replace(source, target)

            with mock.patch.object(setup_module.os, "replace", side_effect=fail_state_write):
                with self.assertRaises(OSError):
                    run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
                        ),
                        environ=environment,
                    )
            pending = root / "state" / "harness-relay" / "setup.pending.json"
            self.assertTrue(pending.is_file())
            recovered = run_setup(
                SetupOptions(
                    relay_config=relay_config,
                    scope="custom",
                    opencode_config=opencode,
                ),
                environ=environment,
            )
            self.assertFalse(pending.exists())
            self.assertFalse(recovered.opencode_changed)
            self.assertTrue((root / "state" / "harness-relay" / "setup.json").is_file())

    def test_uninstall_can_recover_an_interrupted_setup(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            real_replace = setup_module.os.replace
            calls = 0

            def fail_state_write(source, target):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("injected state interruption")
                return real_replace(source, target)

            with mock.patch.object(setup_module.os, "replace", side_effect=fail_state_write):
                with self.assertRaises(OSError):
                    run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
                        ),
                        environ=environment,
                    )
            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertTrue(plan.changed)
            self.assertNotIn(MCP_NAME, opencode.read_text(encoding="utf-8"))
            self.assertFalse((root / "cfg" / "harness-relay" / "opencode-instructions.md").exists())

    def _workspace(self):
        context = tempfile.TemporaryDirectory()
        root = Path(context.name)
        cfg = root / "relay.json"
        cfg.write_text(
            '{"version":1,"workers":{},"roles":{},"paths":{}}\n', encoding="utf-8"
        )
        opencode = root / "opencode.jsonc"
        opencode.write_text(
            '{\n  // user-owned comment\n  "theme":"dark",\n}\n', encoding="utf-8"
        )
        environment = {
            "HOME": str(root),
            "XDG_CONFIG_HOME": str(root / "cfg"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "PATH": "",
        }
        return _Workspace(context, root, environment, cfg, opencode)


class _Workspace:
    def __init__(self, context, root, environment, config, opencode):
        self.context = context
        self.values = (root, environment, config, opencode)

    def __enter__(self):
        return self.values

    def __exit__(self, exc_type, exc, traceback):
        self.context.cleanup()
        return False


if __name__ == "__main__":
    unittest.main()
