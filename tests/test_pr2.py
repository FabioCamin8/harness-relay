"""Offline G03/G04 tests using only disposable homes and fake executables."""

from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest import mock
from importlib import resources
import jsonschema

import harness_relay.setup as setup_module
import harness_relay.opencode as opencode_module
import harness_relay.uninstall as uninstall_module
from harness_relay.configuration import (
    ConfigurationError,
    UserPaths,
    default_config,
    load_config,
    parse_config,
)
from harness_relay.discovery import DiscoveryError, discover_enabled
from harness_relay.jsonc import edit as edit_jsonc
from harness_relay.jsonc import parse as parse_jsonc, remove as remove_jsonc
from harness_relay.jsonc import source_fragment
from harness_relay.opencode import MCP_ENTRY, MCP_NAME, canonical, integrate
from harness_relay.setup import SetupError, SetupOptions, run_setup
from harness_relay.uninstall import UninstallOptions, run_uninstall


class Pr2Test(unittest.TestCase):
    def test_jsonc_parser_dependencies_are_available(self) -> None:
        import tree_sitter
        import tree_sitter_json

        self.assertIsNotNone(tree_sitter)
        self.assertIsNotNone(tree_sitter_json)

    def test_default_config_disables_every_worker(self) -> None:
        config = default_config()
        self.assertEqual(config.enabled_workers, ())
        self.assertEqual(config.roles, {})

    def test_packaged_schema_validates_structural_config_rules(self) -> None:
        schema_path = resources.files("harness_relay.resources").joinpath(
            "config.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        valid = {
            "version": 1,
            "workers": {
                "codex": {"enabled": True, "executable": "/usr/local/bin/codex"}
            },
            "roles": {"implementer": "codex"},
            "paths": {"data": "~/.local/share/harness-relay"},
        }
        self.assertEqual(list(validator.iter_errors(valid)), [])
        for invalid in (
            {"version": 1, "workers": {"codex": {"enabled": 1}}},
            {"version": 1, "workers": {"unknown": {"enabled": True}}},
            {"version": 1, "paths": {"data": "bad\x00path"}},
            {"version": 1, "paths": {"data": "relative-data"}},
        ):
            with self.subTest(invalid=invalid):
                self.assertTrue(list(validator.iter_errors(invalid)))
        # JSON Schema cannot express that a role's adapter is enabled.  The
        # runtime validator owns this cross-field semantic rule.
        role_without_enabled_worker = {"version": 1, "roles": {"reviewer": "codex"}}
        self.assertEqual(list(validator.iter_errors(role_without_enabled_worker)), [])
        with self.assertRaisesRegex(ConfigurationError, "not enabled"):
            parse_config(role_without_enabled_worker)

        # JSON Schema numbers use mathematical equality, so a Python float
        # 1.0 is accepted by the standard validator despite the integer type.
        # The runtime validator retains the stricter lexical/config contract.
        self.assertEqual(list(validator.iter_errors({"version": 1.0})), [])
        with self.assertRaisesRegex(ConfigurationError, "must be an integer"):
            parse_config({"version": 1.0})

    def test_user_paths_reject_empty_home_and_relative_xdg_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                ({"HOME": ""}, "HOME"),
                ({"HOME": str(root), "XDG_CONFIG_HOME": "config"}, "XDG_CONFIG_HOME"),
                ({"HOME": str(root), "XDG_DATA_HOME": "data"}, "XDG_DATA_HOME"),
                ({"HOME": str(root), "XDG_STATE_HOME": "state"}, "XDG_STATE_HOME"),
            )
            for environment, name in cases:
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ConfigurationError, name):
                        UserPaths.from_environment(environment)

    def test_configured_paths_are_absolute_or_home_relative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user_paths = UserPaths.from_environment({"HOME": str(root)})
            config = parse_config(
                {
                    "version": 1,
                    "paths": {
                        "data": "~/data",
                        "worktrees": "/var/tmp/harness-relay-worktrees",
                    },
                }
            )
            resolved = user_paths.with_config_paths(config)
            self.assertEqual(resolved["data"], root / "data")
            self.assertEqual(
                resolved["worktrees"], Path("/var/tmp/harness-relay-worktrees")
            )
            with self.assertRaisesRegex(ConfigurationError, "absolute"):
                parse_config({"version": 1, "paths": {"data": "relative-data"}})

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
            executable.write_text("#!/bin/sh\nprintf 'codex-cli 99.0.0\\n'\n", encoding="utf-8")
            executable.chmod(0o755)
            config = parse_config(
                {
                    "version": 1,
                    "workers": {"codex": {"enabled": True, "executable": str(executable)}},
                }
            )
            found = discover_enabled(config)
            self.assertEqual(found["codex"].version, "99.0.0")
            self.assertEqual(found["codex"].version_status, "detected-unverified")

    def test_duplicate_jsonc_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate object key"):
            integrate('{"mcp": {}, "mcp": {}}', "/tmp/instructions.md")

    def test_jsonc_comments_and_nested_trailing_commas_are_supported(self) -> None:
        source = """{
          // before object member
          "outer": {
            "items": [
              1,
              /* between values */
              {"nested": true},
            ], // array trailing comma
          },
        }
        """
        self.assertEqual(
            parse_jsonc(source), {"outer": {"items": [1, {"nested": True}]}}
        )

    def test_jsonc_insert_uses_only_parent_trailing_comma(self) -> None:
        source = '{"outer": {"a": 1,}, "values": [2,]}'
        edited = edit_jsonc(source, ["added"], 3)
        self.assertEqual(
            parse_jsonc(edited),
            {"outer": {"a": 1}, "values": [2], "added": 3},
        )
        self.assertIn('"outer": {"a": 1,}', edited)
        self.assertIn('"values": [2,]', edited)

    def test_jsonc_rejects_unrecognized_error_recovery(self) -> None:
        for source in (
            "{,}",
            "[1,,]",
            '{"a": 1 "b": 2}',
            '{"a": 01}',
            '{"a": "unterminated}',
            "{/* unterminated */",
            '{"a": NaN}',
        ):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    parse_jsonc(source)

    def test_jsonc_rejects_escaped_duplicate_keys_at_any_depth(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate object key"):
            parse_jsonc('{"outer": {"\\u0061": 1, "a": 2}}')

    def test_jsonc_source_fragment_and_edits_are_utf8_byte_safe(self) -> None:
        source = '{"prefix": "é😀", "target": {"значение": "値"}, "tail": 3}'
        self.assertEqual(
            source_fragment(source, ["target"]), '"target": {"значение": "値"}'
        )
        edited = integrate(source, "/tmp/инструкции.md")[0]
        self.assertEqual(parse_jsonc(edited)["prefix"], "é😀")
        self.assertEqual(parse_jsonc(edited)["target"]["значение"], "値")

    def test_jsonc_crlf_and_comments_around_delimiters_survive_edits(self) -> None:
        source = '{\r\n  /* before */ "a": 1 /* after */,\r\n  "b": 2,\r\n}\r\n'
        removed = remove_jsonc(source, ["a"])
        self.assertEqual(parse_jsonc(removed), {"b": 2})
        self.assertIn("/* before */", removed)
        self.assertIn("/* after */", removed)
        self.assertIn("\r\n", removed)
        inserted = integrate(removed, "/tmp/instructions.md")[0]
        self.assertEqual(parse_jsonc(inserted)["b"], 2)
        self.assertIn("\r\n", inserted)

    def test_jsonc_removes_first_middle_last_object_and_array_values(self) -> None:
        object_source = '{"first": 1, /* middle */ "middle": 2, "last": 3,}'
        self.assertEqual(parse_jsonc(remove_jsonc(object_source, ["first"])),
                         {"middle": 2, "last": 3})
        self.assertEqual(parse_jsonc(remove_jsonc(object_source, ["middle"])),
                         {"first": 1, "last": 3})
        self.assertEqual(parse_jsonc(remove_jsonc(object_source, ["last"])),
                         {"first": 1, "middle": 2})
        array_source = '[1, /* middle */ 2, 3,]'
        self.assertEqual(parse_jsonc(remove_jsonc(array_source, [0])), [2, 3])
        self.assertEqual(parse_jsonc(remove_jsonc(array_source, [1])), [1, 3])
        self.assertEqual(parse_jsonc(remove_jsonc(array_source, [2])), [1, 2])

    def test_cold_dry_run_does_not_spawn_or_create_files(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            before = {path.relative_to(root) for path in root.rglob("*")}
            with mock.patch("subprocess.run", side_effect=AssertionError("process")):
                with mock.patch("socket.socket", side_effect=AssertionError("network")):
                    plan = run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
                            dry_run=True,
                            probe=False,
                        ),
                        environ=environment,
                    )
            after = {path.relative_to(root) for path in root.rglob("*")}
            self.assertTrue(plan.dry_run)
            self.assertEqual(before, after)

    def test_jsonc_integration_preserves_unrelated_content(self) -> None:
        original = '{\n  // user-owned comment\n  "theme": "dark",\n  "model": "user/provider/model",\n  "provider": "user-provider",\n  "auth": {"profile": "existing-user-auth"},\n  "mcp": {"other": {"enabled": true}},\n}\n'
        integrated, _, _ = integrate(original, "/tmp/harness-relay-instructions.md")
        self.assertIn("// user-owned comment", integrated)
        self.assertIn('"theme": "dark"', integrated)
        self.assertIn('"model": "user/provider/model"', integrated)
        self.assertIn('"provider": "user-provider"', integrated)
        self.assertIn('"auth": {"profile": "existing-user-auth"}', integrated)
        self.assertEqual(parse_jsonc(integrated)["mcp"]["other"], {"enabled": True})
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

    def test_identical_explicit_override_does_not_rewrite_config(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            before = relay_config.read_bytes()
            first = run_setup(
                SetupOptions(
                    relay_config=relay_config,
                    scope="custom",
                    opencode_config=opencode,
                    enabled=set(),
                    probe=False,
                ),
                environ=environment,
            )
            self.assertFalse(first.config_changed)
            after_first = relay_config.stat().st_mtime_ns
            second = run_setup(
                SetupOptions(
                    relay_config=relay_config,
                    scope="custom",
                    opencode_config=opencode,
                    enabled=set(),
                    probe=False,
                ),
                environ=environment,
            )
            self.assertFalse(second.config_changed)
            self.assertFalse(second.changed)
            self.assertEqual(relay_config.read_bytes(), before)
            self.assertEqual(relay_config.stat().st_mtime_ns, after_first)

    def test_setup_refuses_concurrent_opencode_edit(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            real_checked = setup_module.atomic_write_checked

            def inject_edit(path, expected, content, operation):
                if path == opencode:
                    path.write_text('{"user_changed": true}\n', encoding="utf-8")
                return real_checked(path, expected, content, operation)

            with mock.patch.object(
                setup_module, "atomic_write_checked", side_effect=inject_edit
            ):
                with self.assertRaisesRegex(SetupError, "changed after inspection"):
                    run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
                        ),
                        environ=environment,
                    )
            self.assertEqual(opencode.read_text(encoding="utf-8"), '{"user_changed": true}\n')

    def test_uninstall_refuses_concurrent_opencode_edit(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            real_checked = uninstall_module.atomic_write_checked

            def inject_edit(path, expected, content, operation):
                path.write_text('{"user_changed": true}\n', encoding="utf-8")
                return real_checked(path, expected, content, operation)

            with mock.patch.object(
                uninstall_module, "atomic_write_checked", side_effect=inject_edit
            ):
                with self.assertRaisesRegex(SetupError, "changed after inspection"):
                    run_uninstall(
                        UninstallOptions(scope="custom", opencode_config=opencode),
                        environ=environment,
                    )
            self.assertEqual(opencode.read_text(encoding="utf-8"), '{"user_changed": true}\n')

    def test_uninstall_refuses_concurrent_instruction_edit(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"
            real_remove = uninstall_module._remove_owned_fragment

            def inject_edit(path, expected):
                path.write_text("user changed instructions\n", encoding="utf-8")
                return real_remove(path, expected)

            with mock.patch.object(
                uninstall_module, "_remove_owned_fragment", side_effect=inject_edit
            ):
                with self.assertRaisesRegex(SetupError, "changed after inspection"):
                    run_uninstall(
                        UninstallOptions(scope="custom", opencode_config=opencode),
                        environ=environment,
                    )
            self.assertEqual(instruction.read_text(encoding="utf-8"), "user changed instructions\n")

    def test_uninstall_preserves_unrelated_and_edited_owned_content(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"
            instruction.write_text("user-edited HarnessRelay guidance\n", encoding="utf-8")
            configured = opencode.read_text(encoding="utf-8")
            configured = configured.replace('"theme": "dark"', '"theme": "light"')
            opencode.write_text(configured, encoding="utf-8")
            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertTrue(plan.changed)
            result = opencode.read_text(encoding="utf-8")
            self.assertIn("user-owned comment", result)
            self.assertIn('"theme": "light"', result)
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
                '"enabled": true', '"enabled": false'
            )
            opencode.write_text(configured, encoding="utf-8")
            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertIn("mcp.harness-relay", " ".join(plan.preserved_user_edits))
            self.assertIn(MCP_NAME, opencode.read_text(encoding="utf-8"))

    def test_uninstall_preserves_semantically_equal_but_byte_edited_mcp(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            configured = opencode.read_text(encoding="utf-8")
            configured = configured.replace('"type": "local"', '"type" : "local"')
            opencode.write_text(configured, encoding="utf-8")
            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertIn("mcp.harness-relay", " ".join(plan.preserved_user_edits))
            self.assertIn(MCP_NAME, opencode.read_text(encoding="utf-8"))

    def test_uninstall_preserves_escaped_byte_edited_instruction_entry(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"
            configured = opencode.read_text(encoding="utf-8")
            literal = json.dumps(str(instruction))
            escaped = literal.replace("/", "\\/", 1)
            self.assertIn(literal, configured)
            opencode.write_text(configured.replace(literal, escaped, 1), encoding="utf-8")

            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )

            self.assertIn("instruction entry", " ".join(plan.preserved_user_edits))
            result = opencode.read_text(encoding="utf-8")
            self.assertIn(escaped, result)
            self.assertIn(str(instruction), parse_jsonc(result)["instructions"])

    def test_uninstall_uses_recorded_instruction_path_after_xdg_change(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            recorded_instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"
            changed_environment = dict(
                environment, XDG_CONFIG_HOME=str(root / "replacement-config")
            )

            plan = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=changed_environment,
            )

            self.assertTrue(plan.fragment_removed)
            self.assertFalse(recorded_instruction.exists())
            self.assertNotIn(str(recorded_instruction), opencode.read_text(encoding="utf-8"))

    def test_shared_instruction_fragment_survives_until_last_integration(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            second_config = root / "second-opencode.jsonc"
            second_config.write_text('{"theme": "second"}\n', encoding="utf-8")
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=second_config),
                environ=environment,
            )
            instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"

            first = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertFalse(first.fragment_removed)
            self.assertTrue(instruction.exists())
            self.assertIn(str(instruction), second_config.read_text(encoding="utf-8"))

            last = run_uninstall(
                UninstallOptions(scope="custom", opencode_config=second_config),
                environ=environment,
            )
            self.assertTrue(last.fragment_removed)
            self.assertFalse(instruction.exists())

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

    def test_opencode_environment_config_conflict_is_reported(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            override = root / "env-opencode.json"
            override.write_text(
                '{"mcp":{"harness-relay":{"type":"remote","url":"user"}}}\n',
                encoding="utf-8",
            )
            environment = dict(environment, OPENCODE_CONFIG=str(override))
            with self.assertRaisesRegex(SetupError, "higher-precedence"):
                run_setup(
                    SetupOptions(
                        relay_config=relay_config,
                        scope="global",
                        project_dir=root / "project",
                    ),
                    environ=environment,
                )

    def test_custom_scope_environment_config_conflict_is_reported(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            override = root / "env-opencode.json"
            override.write_text(
                '{"mcp":{"harness-relay":{"type":"remote","url":"user"}}}\n',
                encoding="utf-8",
            )
            environment = dict(environment, OPENCODE_CONFIG=str(override))
            with self.assertRaisesRegex(SetupError, "higher-precedence"):
                run_setup(
                    SetupOptions(
                        relay_config=relay_config,
                        scope="custom",
                        opencode_config=opencode,
                    ),
                    environ=environment,
                )

    def test_inline_opencode_config_conflict_is_reported(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            environment = dict(
                environment,
                OPENCODE_CONFIG_CONTENT='{"instructions": ["/other.md"]}',
            )
            with self.assertRaisesRegex(SetupError, "OPENCODE_CONFIG_CONTENT"):
                run_setup(
                    SetupOptions(
                        relay_config=relay_config,
                        scope="custom",
                        opencode_config=opencode,
                    ),
                    environ=environment,
                )

    def test_managed_opencode_config_conflict_is_reported(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            managed = root / "managed"
            managed.mkdir()
            (managed / "opencode.json").write_text(
                '{"mcp":{"harness-relay":{"type":"remote","url":"managed"}}}\n',
                encoding="utf-8",
            )
            with mock.patch.object(opencode_module, "MANAGED_CONFIG_DIR", managed):
                with self.assertRaisesRegex(SetupError, "higher-precedence"):
                    run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
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
            state_file = root / "state" / "harness-relay" / "setup.json"

            def fail_state_write(source, target):
                if Path(target) == state_file:
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
            state_file = root / "state" / "harness-relay" / "setup.json"

            def fail_state_write(source, target):
                if Path(target) == state_file:
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

    def test_pending_journal_does_not_claim_user_identical_fragment(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            instruction = root / "cfg" / "harness-relay" / "opencode-instructions.md"
            real_checked = setup_module.atomic_write_checked

            def fail_fragment(path, expected, content, operation):
                if path == instruction:
                    raise OSError("injected fragment interruption")
                return real_checked(path, expected, content, operation)

            with mock.patch.object(
                setup_module, "atomic_write_checked", side_effect=fail_fragment
            ):
                with self.assertRaises(OSError):
                    run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
                        ),
                        environ=environment,
                    )
            pending = json.loads(
                (root / "state" / "harness-relay" / "setup.pending.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(pending["record"]["instruction_fragment_owned"])

            instruction.parent.mkdir(parents=True, exist_ok=True)
            instruction.write_text(setup_module.INSTRUCTION_TEXT, encoding="utf-8")
            run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            state = json.loads(
                (root / "state" / "harness-relay" / "setup.json").read_text(
                    encoding="utf-8"
                )
            )
            record = next(iter(state["integrations"].values()))
            self.assertFalse(record["instruction_fragment_owned"])

            run_uninstall(
                UninstallOptions(scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertTrue(instruction.exists())

    def test_pending_journal_records_fragment_before_mcp_write(self) -> None:
        with self._workspace() as (root, environment, relay_config, opencode):
            real_checked = setup_module.atomic_write_checked

            def fail_opencode(path, expected, content, operation):
                if path == opencode:
                    raise OSError("injected OpenCode interruption")
                return real_checked(path, expected, content, operation)

            with mock.patch.object(
                setup_module, "atomic_write_checked", side_effect=fail_opencode
            ):
                with self.assertRaises(OSError):
                    run_setup(
                        SetupOptions(
                            relay_config=relay_config,
                            scope="custom",
                            opencode_config=opencode,
                        ),
                        environ=environment,
                    )
            pending = json.loads(
                (root / "state" / "harness-relay" / "setup.pending.json").read_text(
                    encoding="utf-8"
                )
            )
            record = pending["record"]
            self.assertTrue(record["instruction_fragment_owned"])
            self.assertFalse(record["mcp_owned"])
            self.assertFalse(record["instruction_entry_owned"])

            recovered = run_setup(
                SetupOptions(relay_config=relay_config, scope="custom", opencode_config=opencode),
                environ=environment,
            )
            self.assertTrue(recovered.opencode_changed)

    def _workspace(self):
        context = tempfile.TemporaryDirectory()
        root = Path(context.name)
        cfg = root / "relay.json"
        cfg.write_text(
            '{"version":1,"workers":{},"roles":{},"paths":{}}\n', encoding="utf-8"
        )
        opencode = root / "opencode.jsonc"
        opencode.write_text(
            '{\n  // user-owned comment\n  "theme": "dark",\n}\n', encoding="utf-8"
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
