"""Token-preserving integration with supported OpenCode config scopes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Mapping

from .configuration import UserPaths
from .jsonc import (
    MISSING,
    JsoncError,
    canonical,
    edit,
    remove,
    parse,
    source_fragment,
)


MCP_NAME = "harness-relay"
LEGACY_MCP_ENTRY = {
    "type": "local",
    "command": ["harness-relay", "mcp", "--stdio"],
    "enabled": False,
}
MCP_ENTRY = {**LEGACY_MCP_ENTRY, "enabled": True}
INSTRUCTION_START = "<!-- HARNESSRELAY MANAGED START -->"
INSTRUCTION_END = "<!-- HARNESSRELAY MANAGED END -->"
INSTRUCTION_TEXT = (
    f"{INSTRUCTION_START}\n"
    "Use HarnessRelay only for explicitly delegated tasks and keep OpenCode as the master.\n"
    f"{INSTRUCTION_END}\n"
)


class OpenCodeConfigError(ValueError):
    """Raised when an OpenCode config cannot be safely inspected or edited."""


@dataclass(frozen=True)
class ScopeSelection:
    scope: str
    path: Path
    higher_precedence: tuple[Path, ...]
    inline_content: str | None = None


def configured_mcp_entry(relay_config: str | Path | None = None) -> dict[str, object]:
    """Return the owned MCP entry, optionally pinned to one relay config."""
    entry = {**MCP_ENTRY, "command": list(MCP_ENTRY["command"])}
    if relay_config is not None:
        config_path = Path(relay_config).expanduser().resolve()
        entry["command"] = [
            *entry["command"],
            "--config",
            str(config_path),
        ]
    return entry


def select_scope(
    scope: str,
    user_paths: UserPaths,
    *,
    explicit_path: str | Path | None = None,
    project_dir: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ScopeSelection:
    """Resolve a supported OpenCode scope without creating any files."""
    if scope not in {"global", "project", "custom"}:
        raise OpenCodeConfigError(
            f"unsupported OpenCode scope {scope!r}; choose global, project, or custom"
        )
    project = Path(project_dir or Path.cwd()).resolve()
    if scope == "custom":
        if explicit_path is None:
            raise OpenCodeConfigError("custom OpenCode scope requires --opencode-config")
        target = Path(explicit_path).expanduser().resolve()
    elif scope == "global":
        target = _choose_existing(
            user_paths.config_home / "opencode" / "opencode.json",
            user_paths.config_home / "opencode" / "opencode.jsonc",
        )
    else:
        target = _choose_existing(
            project / "opencode.json", project / "opencode.jsonc"
        )

    env = os.environ if environ is None else environ
    config_override = env.get("OPENCODE_CONFIG")
    override_path = (
        Path(config_override).expanduser().resolve()
        if config_override is not None
        else None
    )
    inline_content = env.get("OPENCODE_CONFIG_CONTENT")
    layers = _scope_layers(
        user_paths,
        project,
        explicit_path,
        config_override=config_override,
    )
    if override_path is not None:
        if override_path != target and not override_path.is_file():
            raise OpenCodeConfigError(
                "OPENCODE_CONFIG points to an unavailable or uninspectable path: "
                f"{override_path}"
            )
    try:
        target_index = layers.index(target)
    except ValueError:
        target_index = -1
    higher = tuple(path for index, path in enumerate(layers) if index > target_index)
    if override_path is not None and override_path != target and override_path not in higher:
        higher = (*higher, override_path)
    return ScopeSelection(scope, target, higher, inline_content)


def inspect_config(path: Path) -> tuple[str, object]:
    """Read a JSONC config or an empty object when the selected file is absent."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "{}\n", parse("{}\n")
    except OSError as exc:
        raise OpenCodeConfigError(f"cannot read OpenCode config {path}: {exc}") from exc
    try:
        return text, parse(text)
    except JsoncError as exc:
        raise OpenCodeConfigError(f"invalid JSON/JSONC in {path}: {exc}") from exc


def check_higher_precedence_conflicts(
    selection: ScopeSelection,
    instruction_path: str,
    *,
    mcp_entry: Mapping[str, object] | None = None,
) -> None:
    """Reject effective-config conflicts instead of hiding them by overwrite."""
    expected = canonical(mcp_entry if mcp_entry is not None else MCP_ENTRY)
    for path in selection.higher_precedence:
        if not path.exists():
            continue
        if not path.is_file():
            raise OpenCodeConfigError(
                f"OpenCode higher-precedence config is not a regular file: {path}"
            )
        _, root = inspect_config(path)
        _check_layer_conflicts(root, str(path), instruction_path, expected)
    if selection.inline_content is not None:
        try:
            root = parse(selection.inline_content)
        except JsoncError as exc:
            raise OpenCodeConfigError(
                "OPENCODE_CONFIG_CONTENT is set but cannot be inspected: "
                f"{exc}"
            ) from exc
        _check_layer_conflicts(root, "OPENCODE_CONFIG_CONTENT", instruction_path, expected)


def _check_layer_conflicts(
    root: object, source: str, instruction_path: str, expected_mcp: str
) -> None:
    """Check one higher-precedence layer without mutating it."""
    if not isinstance(root, dict):
        raise OpenCodeConfigError(f"OpenCode config root must be an object: {source}")
    mcp = root.get("mcp", MISSING)
    if mcp is not MISSING:
        if not isinstance(mcp, dict):
            raise OpenCodeConfigError(
                f"OpenCode config {source} has non-object 'mcp'; cannot determine conflict"
            )
        relay = mcp.get(MCP_NAME, MISSING)
        if relay is not MISSING and canonical(relay) != expected_mcp:
            raise OpenCodeConfigError(
                f"OpenCode scope conflict: higher-precedence config {source} defines "
                f"mcp.{MCP_NAME} differently"
            )
    instructions = root.get("instructions", MISSING)
    if instructions is not MISSING:
        if not isinstance(instructions, list):
            raise OpenCodeConfigError(
                f"OpenCode scope conflict: {source} has non-array 'instructions'"
            )
        if instruction_path not in instructions:
            raise OpenCodeConfigError(
                f"OpenCode scope conflict: higher-precedence config {source} overrides "
                "instructions without the HarnessRelay fragment"
            )


def integrate(
    text: str,
    instruction_path: str,
    *,
    allow_legacy_upgrade: bool = False,
    mcp_entry: Mapping[str, object] | None = None,
) -> tuple[str, bool, bool]:
    """Add the namespaced MCP entry and instruction path, preserving source text.

    Returns ``(new_text, mcp_was_created, instruction_path_was_created)``.
    """
    try:
        root = parse(text)
    except JsoncError as exc:
        raise OpenCodeConfigError(f"invalid JSON/JSONC: {exc}") from exc
    if not isinstance(root, dict):
        raise OpenCodeConfigError("OpenCode config root must be an object")

    desired_mcp = dict(mcp_entry if mcp_entry is not None else MCP_ENTRY)
    mcp_created = False
    mcp = root.get("mcp", MISSING)
    if mcp is MISSING:
        text = edit(text, ["mcp"], {})
        mcp_created = True
        root = _parse_object(text)
        mcp = root["mcp"]
    if not isinstance(mcp, dict):
        raise OpenCodeConfigError("OpenCode config key 'mcp' must be an object")
    relay = mcp.get(MCP_NAME, MISSING)
    if relay is MISSING:
        text = edit(text, ["mcp", MCP_NAME], desired_mcp)
        mcp_created = True
    elif allow_legacy_upgrade:
        # The caller grants this only after the current fragment matches the
        # recorded ownership hash, so any previously generated command can be
        # updated without treating user-edited values as owned.
        text = edit(text, ["mcp", MCP_NAME], desired_mcp)
        mcp_created = True
    elif canonical(relay) != canonical(desired_mcp):
        raise OpenCodeConfigError(
            f"OpenCode config conflict: mcp.{MCP_NAME} already has a different value"
        )

    root = _parse_object(text)
    instructions = root.get("instructions", MISSING)
    instruction_created = False
    if instructions is MISSING:
        text = edit(text, ["instructions"], [instruction_path])
        instruction_created = True
    else:
        if not isinstance(instructions, list):
            raise OpenCodeConfigError("OpenCode config key 'instructions' must be an array")
        if instruction_path not in instructions:
            text = edit(text, ["instructions", len(instructions)], instruction_path)
            instruction_created = True
    return text, mcp_created, instruction_created


def remove_owned(
    text: str,
    *,
    remove_mcp: bool,
    instruction_path: str,
    instruction_entry_hash: str | None = None,
) -> tuple[str, bool, bool]:
    """Remove only owned members, leaving empty containers and user content."""
    try:
        root = parse(text)
    except JsoncError as exc:
        raise OpenCodeConfigError(f"invalid JSON/JSONC: {exc}") from exc
    if not isinstance(root, dict):
        raise OpenCodeConfigError("OpenCode config root must be an object")
    mcp_removed = False
    if remove_mcp:
        mcp = root.get("mcp", MISSING)
        if isinstance(mcp, dict) and MCP_NAME in mcp:
            text = remove(text, ["mcp", MCP_NAME])
            mcp_removed = True

    root = _parse_object(text)
    instruction_removed = False
    instructions = root.get("instructions", MISSING)
    if isinstance(instructions, list) and instruction_entry_hash is not None:
        for index in reversed(range(len(instructions))):
            if instructions[index] == instruction_path:
                fragment = source_fragment(text, ["instructions", index])
                if fragment is None or _source_hash(fragment) != instruction_entry_hash:
                    continue
                text = remove(text, ["instructions", index])
                instruction_removed = True
                break
    return text, mcp_removed, instruction_removed


def _source_hash(fragment: str) -> str:
    return hashlib.sha256(fragment.encode("utf-8")).hexdigest()


def _parse_object(text: str):
    node = parse(text)
    if not isinstance(node, dict):
        raise OpenCodeConfigError("OpenCode config root must be an object")
    return node


def _choose_existing(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def _scope_layers(
    user_paths: UserPaths,
    project: Path,
    custom_path: str | Path | None,
    *,
    config_override: str | None = None,
) -> list[Path]:
    global_path = _choose_existing(
        user_paths.config_home / "opencode" / "opencode.json",
        user_paths.config_home / "opencode" / "opencode.jsonc",
    )
    layers = [global_path]
    if custom_path is not None:
        layers.append(Path(custom_path).expanduser().resolve())
    project_path = _choose_existing(project / "opencode.json", project / "opencode.jsonc")
    layers.append(project_path)
    layers.extend(
        (
            MANAGED_CONFIG_DIR / "opencode.json",
            MANAGED_CONFIG_DIR / "opencode.jsonc",
        )
    )
    if config_override is not None:
        layers.append(Path(config_override).expanduser().resolve())
    result: list[Path] = []
    for path in layers:
        if path not in result:
            result.append(path)
    return result


MANAGED_CONFIG_DIR = Path("/etc/opencode")
