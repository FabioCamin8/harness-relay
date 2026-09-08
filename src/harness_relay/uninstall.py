"""Ownership-checked removal of the HarnessRelay OpenCode integration."""

from __future__ import annotations

from dataclasses import dataclass
import json
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
    recorded_instruction_path = record.get("instruction_path")
    if not isinstance(recorded_instruction_path, str) or not recorded_instruction_path:
        raise SetupError(
            f"ownership record for {key} has no valid instruction_path; refusing uninstall"
        )
    try:
        instruction_path = Path(recorded_instruction_path)
        if not instruction_path.is_absolute():
            raise SetupError(
                f"ownership record for {key} has a relative instruction_path; refusing uninstall"
            )
        instruction_path = instruction_path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SetupError(
            f"ownership record for {key} has an invalid instruction_path; refusing uninstall"
        ) from exc

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
    expected_instruction_hash = record.get("instruction_entry_hash")
    instruction_unchanged = bool(
        instruction_owned
        and isinstance(expected_instruction_hash, str)
        and _instruction_entry_matches(
            opencode_text, root, str(instruction_path), expected_instruction_hash
        )
    )
    if instruction_owned and not instruction_unchanged:
        preserved.append(
            "the edited or unverified HarnessRelay instruction entry"
        )
    instruction_before: bytes | None = None
    try:
        instruction_text = instruction_path.read_text(encoding="utf-8")
        instruction_before = instruction_text.encode("utf-8")
    except FileNotFoundError:
        instruction_text = ""
    except OSError as exc:
        raise SetupError(f"cannot read instruction fragment {instruction_path}: {exc}") from exc
    fragment_unchanged = False
    if record.get("instruction_fragment_owned", False):
        expected_hash = record.get("fragment_hash")
        fragment_unchanged = bool(
            instruction_text
            and isinstance(expected_hash, str)
            and _sha256(instruction_text.encode("utf-8")) == expected_hash
        )
        if not fragment_unchanged:
            preserved.append("the edited HarnessRelay instruction fragment")
    shared_fragment = _shared_instruction_reference(
        state, key, instruction_path, pending, pending_matches
    )
    if fragment_unchanged and shared_fragment:
        preserved.append(
            "the HarnessRelay instruction fragment (referenced by another integration)"
        )
    remove_fragment = fragment_unchanged and not shared_fragment
    try:
        new_text, _, _ = remove_owned(
            opencode_text,
            remove_mcp=remove_mcp,
            instruction_path=(
                str(instruction_path) if instruction_unchanged else "\0never-owned\0"
            ),
            instruction_entry_hash=(
                expected_instruction_hash if instruction_unchanged else None
            ),
        )
    except Exception as exc:
        raise SetupError(f"cannot prepare uninstall for {selection.path}: {exc}") from exc
    # remove_owned reports an instruction removal only when the ownership
    # record allowed it; a missing path is already a safe no-op.
    fragment_removed = bool(
        remove_fragment
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


def _instruction_entry_matches(
    text: str, root: object, instruction_path: str, expected_hash: str
) -> bool:
    if not isinstance(root, dict):
        return False
    instructions = root.get("instructions")
    if not isinstance(instructions, list):
        return False
    for index, value in enumerate(instructions):
        if value != instruction_path:
            continue
        fragment = source_fragment(text, ["instructions", index])
        if fragment is not None and _sha256(fragment.encode("utf-8")) == expected_hash:
            return True
    return False


def _shared_instruction_reference(
    state: dict,
    key: str,
    instruction_path: Path,
    pending: dict,
    pending_matches: bool,
) -> bool:
    integrations = state.get("integrations", {})
    if isinstance(integrations, dict):
        for other_key, record in integrations.items():
            if other_key == key or not isinstance(record, dict):
                continue
            if _record_uses_instruction_path(record, instruction_path):
                return True
    if not pending_matches:
        pending_record = pending.get("record")
        if isinstance(pending_record, dict) and _record_uses_instruction_path(
            pending_record, instruction_path
        ):
            return True
    return False


def _record_uses_instruction_path(record: dict, instruction_path: Path) -> bool:
    recorded = record.get("instruction_path")
    if isinstance(recorded, str):
        try:
            return Path(recorded).expanduser().resolve() == instruction_path
        except (OSError, RuntimeError, ValueError):
            return True
    return bool(
        record.get("instruction_fragment_owned", False)
        or record.get("instruction_entry_owned", False)
    )
