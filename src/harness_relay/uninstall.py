"""Ownership-checked removal of the HarnessRelay OpenCode integration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .configuration import UserPaths
from .jsonc import source_fragment
from .opencode import ScopeSelection, inspect_config, remove_owned, select_scope
from .setup import (
    SetupError,
    _clear_pending,
    _load_pending,
    _load_state,
    _sha256,
    atomic_write,
    atomic_write_checked,
    _optional_bytes,
    state_path,
)


@dataclass(frozen=True)
class UninstallOptions:
    scope: str = "global"
    opencode_config: Path | None = None
    project_dir: Path | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class UninstallPlan:
    opencode_path: Path
    instruction_path: Path
    opencode_changed: bool
    fragment_removed: bool
    state_changed: bool
    preserved_user_edits: tuple[str, ...]
    dry_run: bool

    @property
    def changed(self) -> bool:
        return self.opencode_changed or self.fragment_removed or self.state_changed


def run_uninstall(
    options: UninstallOptions,
    *,
    environ: dict[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
) -> UninstallPlan:
    """Remove only integration bytes still covered by the ownership record."""
    user_paths = UserPaths.from_environment(environ, home)
    selection = select_scope(
        options.scope,
        user_paths,
        explicit_path=options.opencode_config,
        project_dir=options.project_dir,
        environ=environ,
    )
    instruction_path = user_paths.config_file.parent / "opencode-instructions.md"
    state_file = state_path(user_paths)
    state = _load_state(state_file)
    key = f"{selection.scope}:{selection.path}"
    record = state.get("integrations", {}).get(key)
    pending_path = state_file.parent / "setup.pending.json"
    pending = _load_pending(pending_path)
    pending_matches = pending.get("key") == key
    if not record and pending_matches:
        pending_record = pending.get("record")
        record = pending_record if isinstance(pending_record, dict) else None
    if not record:
        return UninstallPlan(
            selection.path, instruction_path, False, False, False, (), options.dry_run
        )

    opencode_text, root = inspect_config(selection.path)
    opencode_before = (
        opencode_text.encode("utf-8") if selection.path.is_file() else None
    )
    if not isinstance(root, dict):
        raise SetupError(f"OpenCode config root must be an object: {selection.path}")
    expected_mcp_hash = record.get("mcp_fragment_hash")
    current_mcp_fragment = source_fragment(opencode_text, ["mcp", "harness-relay"])
    mcp_unchanged = bool(
        isinstance(expected_mcp_hash, str)
        and current_mcp_fragment is not None
        and _sha256(current_mcp_fragment.encode("utf-8")) == expected_mcp_hash
    )
    remove_mcp = bool(record.get("mcp_owned", False) and mcp_unchanged)
    if record.get("mcp_owned", False) and not mcp_unchanged:
        preserved = ["mcp.harness-relay (it was edited or is no longer present)"]
    else:
        preserved = []

    instruction_owned = bool(record.get("instruction_entry_owned", False))
    instruction_before: bytes | None = None
    try:
        instruction_text = instruction_path.read_text(encoding="utf-8")
        instruction_before = instruction_text.encode("utf-8")
    except FileNotFoundError:
        instruction_text = ""
    except OSError as exc:
        raise SetupError(f"cannot read instruction fragment {instruction_path}: {exc}") from exc
    if record.get("instruction_fragment_owned", False):
        expected_hash = record.get("fragment_hash")
        if instruction_text and _sha256(instruction_text.encode("utf-8")) != expected_hash:
            preserved.append("the edited HarnessRelay instruction fragment")
    try:
        new_text, _, _ = remove_owned(
            opencode_text,
            remove_mcp=remove_mcp,
            instruction_path=str(instruction_path) if instruction_owned else "\0never-owned\0",
        )
    except Exception as exc:
        raise SetupError(f"cannot prepare uninstall for {selection.path}: {exc}") from exc
    # remove_owned reports an instruction removal only when the ownership
    # record allowed it; a missing path is already a safe no-op.
    fragment_removed = bool(
        record.get("instruction_fragment_owned", False)
        and instruction_text
        and _sha256(instruction_text.encode("utf-8")) == record.get("fragment_hash")
    )
    state_without = {
        "version": 1,
        "integrations": {
            name: value
            for name, value in state.get("integrations", {}).items()
            if name != key
        },
    }
    state_changed = state_without != state or pending_matches
    plan = UninstallPlan(
        selection.path,
        instruction_path,
       (new_text != opencode_text),
        fragment_removed,
        state_changed,
        tuple(preserved),
        options.dry_run,
    )
    if options.dry_run:
        return plan
    if plan.opencode_changed:
        atomic_write_checked(
            selection.path, opencode_before, new_text.encode("utf-8"), "uninstall"
        )
    if fragment_removed:
        _remove_owned_fragment(instruction_path, instruction_before)
    if state_changed:
        if state_without != state:
            import json

            atomic_write(
                state_file,
                (json.dumps(state_without, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
        if pending_matches:
            _clear_pending(pending_path)
    return plan


def _remove_owned_fragment(path: Path, expected: bytes | None) -> None:
    """Unlink only the exact owned fragment; config is never restored wholesale."""
    if _optional_bytes(path) != expected:
        raise SetupError(
            f"uninstall refused to remove {path}: file changed after inspection"
        )
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SetupError(f"cannot remove owned instruction fragment {path}: {exc}") from exc
