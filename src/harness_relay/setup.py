"""Setup orchestration and ownership state for the local OpenCode integration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

from .configuration import (
    UserPaths,
    config_document,
    config_with_overrides,
    default_config,
    dump_config,
    load_config,
)
from .discovery import DetectedWorker, discover_enabled
from .jsonc import source_fragment
from .opencode import (
    INSTRUCTION_TEXT,
    MCP_ENTRY,
    OpenCodeConfigError,
    ScopeSelection,
    check_higher_precedence_conflicts,
    inspect_config,
    integrate,
    select_scope,
)


class SetupError(ValueError):
    """Raised when setup cannot safely complete."""


STATE_VERSION = 1


@dataclass(frozen=True)
class SetupOptions:
    """Non-interactive setup inputs and filesystem selection."""

    relay_config: Path | None = None
    scope: str = "global"
    opencode_config: Path | None = None
    project_dir: Path | None = None
    enabled: set[str] | None = None
    roles: Mapping[str, str] | None = None
    executables: Mapping[str, str] | None = None
    paths: Mapping[str, str] | None = None
    dry_run: bool = False
    probe: bool = True


@dataclass(frozen=True)
class SetupPlan:
    """Observable setup result, suitable for CLI output and tests."""

    config_path: Path
    opencode_path: Path
    instruction_path: Path
    enabled_workers: tuple[str, ...]
    detected_workers: dict[str, DetectedWorker]
    config_changed: bool
    opencode_changed: bool
    fragment_changed: bool
    state_changed: bool
    dry_run: bool

    @property
    def changed(self) -> bool:
        return any(
            (
                self.config_changed,
                self.opencode_changed,
                self.fragment_changed,
                self.state_changed,
            )
        )


def run_setup(
    options: SetupOptions,
    *,
    environ: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
) -> SetupPlan:
    """Validate config, inspect scopes, and apply a minimal owned integration."""
    user_paths = UserPaths.from_environment(environ, home)
    config_path = (options.relay_config or user_paths.config_file).expanduser().resolve()
    config_exists = config_path.is_file()
    config_before = _optional_bytes(config_path)
    if config_exists:
        original_config = load_config(config_path)
        config = original_config
    else:
        original_config = default_config()
        config = default_config()
    config = config_with_overrides(
        config,
        enabled=options.enabled,
        roles=options.roles,
        executables=options.executables,
        paths=options.paths,
    )

    detected = discover_enabled(
        config,
        environ=environ,
        probe=options.probe,
    )
    selection = select_scope(
        options.scope,
        user_paths,
        explicit_path=options.opencode_config,
        project_dir=options.project_dir,
        environ=environ,
    )
    instruction_path = _instruction_path(user_paths)
    try:
        check_higher_precedence_conflicts(selection, str(instruction_path))
    except OpenCodeConfigError as exc:
        raise SetupError(str(exc)) from exc

    opencode_text, _ = inspect_config(selection.path)
    opencode_before = (
        opencode_text.encode("utf-8") if selection.path.is_file() else None
    )
    try:
        new_opencode_text, mcp_created, instruction_created = integrate(
            opencode_text, str(instruction_path)
        )
    except Exception as exc:
        if isinstance(exc, SetupError):
            raise
        raise SetupError(f"cannot prepare OpenCode config {selection.path}: {exc}") from exc

    old_state = _load_state(user_paths.state_dir / "setup.json")
    state_key = _state_key(selection)
    old_record = dict(old_state.get("integrations", {}).get(state_key, {}))
    pending_path = user_paths.state_dir / "setup.pending.json"
    pending = _load_pending(pending_path)
    if pending.get("key") == state_key:
        pending_record = pending.get("record", {})
        if isinstance(pending_record, dict):
            for name, value in pending_record.items():
                old_record.setdefault(name, value)

    fragment_exists = instruction_path.exists()
    instruction_before: bytes | None = None
    fragment_text = ""
    if fragment_exists:
        try:
            fragment_text = instruction_path.read_text(encoding="utf-8")
            instruction_before = fragment_text.encode("utf-8")
        except OSError as exc:
            raise SetupError(
                f"cannot read HarnessRelay instruction fragment {instruction_path}: {exc}"
            ) from exc
        if fragment_text != INSTRUCTION_TEXT and not old_record.get(
            "instruction_fragment_owned", False
        ):
            raise SetupError(
                f"HarnessRelay instruction path already exists with different content: "
                f"{instruction_path}; move it or choose another user config home"
            )

    # Supplying an explicit override that already describes the file is a true
    # no-op; do not rewrite bytes or update mtime merely because an option was
    # supplied.
    config_changed = not config_exists or config_document(config) != config_document(
        original_config
    )
    # The relay config is user-owned input.  It is written only when it was
    # generated or explicitly changed through setup overrides.
    fragment_changed = not fragment_exists
    state = _state_with_record(
        old_state,
        state_key,
        selection,
        instruction_path,
        mcp_owned=bool(old_record.get("mcp_owned", False) or mcp_created),
        instruction_entry_owned=bool(
            old_record.get("instruction_entry_owned", False) or instruction_created
        ),
        instruction_fragment_owned=bool(
            old_record.get("instruction_fragment_owned", False) or fragment_changed
        ),
        mcp_fragment_hash=(
            _mcp_fragment_hash(new_opencode_text)
            if mcp_created
            else old_record.get("mcp_fragment_hash")
        ),
        fragment_hash=old_record.get("fragment_hash")
        or _sha256(INSTRUCTION_TEXT.encode("utf-8")),
    )
    state_changed = state != old_state

    plan = SetupPlan(
        config_path=config_path,
        opencode_path=selection.path,
        instruction_path=instruction_path,
        enabled_workers=tuple(worker.name for worker in config.enabled_workers),
        detected_workers=detected,
        config_changed=config_changed,
        opencode_changed=new_opencode_text != opencode_text,
        fragment_changed=fragment_changed,
        state_changed=state_changed,
        dry_run=options.dry_run,
    )
    if options.dry_run:
        return plan
    if not plan.changed and not pending.get("key") == state_key:
        return plan

    pending_record = state["integrations"][state_key]
    atomic_write(
        pending_path,
        (
            json.dumps(
                {"version": STATE_VERSION, "key": state_key, "record": pending_record},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )
    # Each file replacement is atomic and its parent is created only at the
    # point of applying a real setup.  A failed replacement leaves the old
    # complete file in place and a later run can safely retry the plan.
    if config_changed:
        atomic_write_checked(
            config_path, config_before, dump_config(config).encode("utf-8"), "setup"
        )
    if fragment_changed:
        atomic_write_checked(
            instruction_path, instruction_before, INSTRUCTION_TEXT.encode("utf-8"), "setup"
        )
    if plan.opencode_changed:
        atomic_write_checked(
            selection.path, opencode_before, new_opencode_text.encode("utf-8"), "setup"
        )
    if state_changed:
        atomic_write(
            user_paths.state_dir / "setup.json",
            (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    _clear_pending(pending_path)
    return plan


def atomic_write(path: Path, content: bytes) -> None:
    """Atomically replace one file, retaining mode when it already exists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode: int | None = None
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        pass
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_write_checked(
    path: Path, expected: bytes | None, content: bytes, operation: str
) -> None:
    """Replace a file only if its inspected bytes are still current."""
    current = _optional_bytes(path)
    if current != expected:
        raise SetupError(
            f"{operation} refused to replace {path}: file changed after inspection"
        )
    atomic_write(path, content)


def state_path(user_paths: UserPaths) -> Path:
    """Return the user-local ownership record path."""
    return user_paths.state_dir / "setup.json"


def _instruction_path(user_paths: UserPaths) -> Path:
    return user_paths.config_file.parent / "opencode-instructions.md"


def _state_key(selection: ScopeSelection) -> str:
    return f"{selection.scope}:{selection.path}"


def _state_with_record(
    state: dict,
    key: str,
    selection: ScopeSelection,
    instruction_path: Path,
    *,
    mcp_owned: bool,
    instruction_entry_owned: bool,
    instruction_fragment_owned: bool,
    mcp_fragment_hash: str | None,
    fragment_hash: str,
) -> dict:
    updated = {"version": STATE_VERSION, "integrations": dict(state.get("integrations", {}))}
    updated["integrations"][key] = {
        "scope": selection.scope,
        "config_path": str(selection.path),
        "instruction_path": str(instruction_path),
        "mcp_name": "harness-relay",
        "mcp_value_hash": _sha256(_canonical_json(MCP_ENTRY).encode("utf-8")),
        "mcp_fragment_hash": mcp_fragment_hash,
        "mcp_owned": mcp_owned,
        "instruction_entry_owned": instruction_entry_owned,
        "instruction_fragment_owned": instruction_fragment_owned,
        "fragment_hash": fragment_hash,
    }
    return updated


def _load_state(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"version": STATE_VERSION, "integrations": {}}
    except OSError as exc:
        raise SetupError(f"cannot read setup ownership record {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SetupError(f"invalid setup ownership record {path}: {exc.msg}") from exc
    if (
        not isinstance(value, dict)
        or value.get("version") != STATE_VERSION
        or not isinstance(value.get("integrations"), dict)
    ):
        raise SetupError(f"unsupported or invalid setup ownership record: {path}")
    return value


def _load_pending(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SetupError(f"cannot read pending setup journal {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SetupError(f"invalid pending setup journal {path}: {exc.msg}") from exc
    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        raise SetupError(f"unsupported pending setup journal: {path}")
    return value


def _clear_pending(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise SetupError(f"cannot clear pending setup journal {path}: {exc}") from exc


def load_ownership(user_paths: UserPaths) -> dict:
    """Load ownership state for uninstall and diagnostics."""
    return _load_state(state_path(user_paths))


def _optional_bytes(path: Path) -> bytes | None:
    """Read a file for compare-and-swap checks, treating absence as ``None``."""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}") from exc


def _mcp_fragment_hash(text: str) -> str:
    fragment = source_fragment(text, ["mcp", "harness-relay"])
    if fragment is None:
        raise SetupError("cannot record ownership: integrated MCP fragment is missing")
    return _sha256(fragment.encode("utf-8"))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
