"""Token-preserving integration with supported OpenCode config scopes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .configuration import UserPaths
from .jsonc import (
    JsoncError,
    apply_edits,
    canonical,
    edit_insert_array_item,
    edit_insert_object_member,
    edit_remove_array_item,
    edit_remove_object_member,
    find_member,
    parse,
)


MCP_NAME = "harness-relay"
MCP_ENTRY = {
    "type": "local",
    "command": ["harness-relay", "mcp", "--stdio"],
    "enabled": True,
}
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


def select_scope(
    scope: str,
    user_paths: UserPaths,
    *,
    explicit_path: str | Path | None = None,
    project_dir: str | Path | None = None,
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

    layers = _scope_layers(user_paths, project, explicit_path)
    try:
        target_index = layers.index(target)
    except ValueError:
        target_index = -1
    higher = tuple(path for index, path in enumerate(layers) if index > target_index)
    return ScopeSelection(scope, target, higher)


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
    selection: ScopeSelection, instruction_path: str
) -> None:
    """Reject effective-config conflicts instead of hiding them by overwrite."""
    expected = canonical(MCP_ENTRY)
    for path in selection.higher_precedence:
        if not path.is_file():
            continue
        _, root = inspect_config(path)
        if getattr(root, "kind", None) != "object":
            raise OpenCodeConfigError(f"OpenCode config root must be an object: {path}")
        mcp_member = find_member(root, "mcp")
        if mcp_member is not None:
            if mcp_member.value.kind != "object":
                raise OpenCodeConfigError(
                    f"OpenCode config {path} has non-object 'mcp'; cannot determine conflict"
                )
            relay = find_member(mcp_member.value, MCP_NAME)
            if relay is not None and canonical(relay.value.value) != expected:
                raise OpenCodeConfigError(
                    f"OpenCode scope conflict: higher-precedence config {path} defines "
                    f"mcp.{MCP_NAME} differently"
                )
        instructions = find_member(root, "instructions")
        if instructions is not None:
            if instructions.value.kind != "array":
                raise OpenCodeConfigError(
                    f"OpenCode scope conflict: {path} has non-array 'instructions'"
                )
            if instruction_path not in instructions.value.value:
                raise OpenCodeConfigError(
                    f"OpenCode scope conflict: higher-precedence config {path} overrides "
                    "instructions without the HarnessRelay fragment"
                )


def integrate(text: str, instruction_path: str) -> tuple[str, bool, bool]:
    """Add the namespaced MCP entry and instruction path, preserving source text.

    Returns ``(new_text, mcp_was_created, instruction_path_was_created)``.
    """
    try:
        root = parse(text)
    except JsoncError as exc:
        raise OpenCodeConfigError(f"invalid JSON/JSONC: {exc}") from exc
    if root.kind != "object":
        raise OpenCodeConfigError("OpenCode config root must be an object")

    mcp_created = False
    mcp = find_member(root, "mcp")
    if mcp is None:
        text = apply_edits(text, edit_insert_object_member(text, root, "mcp", {}))
        mcp_created = True
        root = _parse_object(text)
        mcp = find_member(root, "mcp")
    assert mcp is not None
    if mcp.value.kind != "object":
        raise OpenCodeConfigError("OpenCode config key 'mcp' must be an object")
    relay = find_member(mcp.value, MCP_NAME)
    if relay is None:
        text = apply_edits(
            text,
            edit_insert_object_member(text, mcp.value, MCP_NAME, MCP_ENTRY),
        )
        mcp_created = True
    elif canonical(relay.value.value) != canonical(MCP_ENTRY):
        raise OpenCodeConfigError(
            f"OpenCode config conflict: mcp.{MCP_NAME} already has a different value"
        )

    root = _parse_object(text)
    instructions = find_member(root, "instructions")
    instruction_created = False
    if instructions is None:
        text = apply_edits(
            text,
            edit_insert_object_member(text, root, "instructions", [instruction_path]),
        )
        instruction_created = True
    else:
        if instructions.value.kind != "array":
            raise OpenCodeConfigError("OpenCode config key 'instructions' must be an array")
        if instruction_path not in instructions.value.value:
            text = apply_edits(
                text,
                edit_insert_array_item(text, instructions.value, instruction_path),
            )
            instruction_created = True
    return text, mcp_created, instruction_created


def remove_owned(
    text: str,
    *,
    remove_mcp: bool,
    instruction_path: str,
) -> tuple[str, bool, bool]:
    """Remove only owned members, leaving empty containers and user content."""
    try:
        root = parse(text)
    except JsoncError as exc:
        raise OpenCodeConfigError(f"invalid JSON/JSONC: {exc}") from exc
    if root.kind != "object":
        raise OpenCodeConfigError("OpenCode config root must be an object")
    mcp_removed = False
    if remove_mcp:
        mcp = find_member(root, "mcp")
        if mcp is not None and mcp.value.kind == "object":
            relay = find_member(mcp.value, MCP_NAME)
            if relay is not None:
                text = apply_edits(
                    text, edit_remove_object_member(text, mcp.value, MCP_NAME)
                )
                mcp_removed = True

    root = _parse_object(text)
    instruction_removed = False
    instructions = find_member(root, "instructions")
    if instructions is not None and instructions.value.kind == "array":
        for index, item in reversed(list(enumerate(instructions.value.items))):
            if item.value == instruction_path:
                text = apply_edits(
                    text, edit_remove_array_item(text, instructions.value, index)
                )
                instruction_removed = True
                break
    return text, mcp_removed, instruction_removed


def _parse_object(text: str):
    node = parse(text)
    if node.kind != "object":
        raise OpenCodeConfigError("OpenCode config root must be an object")
    return node


def _choose_existing(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()


def _scope_layers(
    user_paths: UserPaths, project: Path, custom_path: str | Path | None
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
    local_path = _choose_existing(
        project / ".opencode" / "opencode.json",
        project / ".opencode" / "opencode.jsonc",
    )
    layers.append(local_path)
    result: list[Path] = []
    for path in layers:
        if path not in result:
            result.append(path)
    return result
