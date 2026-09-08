"""Strict, versioned HarnessRelay configuration.

The relay configuration intentionally contains worker selection and local
paths only.  OpenCode's model/provider configuration and native worker
authentication never belong in this file.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping


SUPPORTED_CONFIG_VERSION = 1
SUPPORTED_ADAPTERS = ("codex", "claude", "agy")
WORKER_FIELDS = frozenset(("enabled", "executable"))
PATH_FIELDS = frozenset(("data", "worktrees", "artifacts"))
ROLE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class ConfigurationError(ValueError):
    """Raised when a relay configuration violates the public contract."""


@dataclass(frozen=True)
class WorkerConfig:
    """Configuration for one statically supported native worker."""

    name: str
    enabled: bool = False
    executable: str | None = None


@dataclass(frozen=True)
class RelayConfig:
    """Validated HarnessRelay settings."""

    version: int
    workers: dict[str, WorkerConfig]
    roles: dict[str, str]
    paths: dict[str, str]

    @property
    def enabled_workers(self) -> tuple[WorkerConfig, ...]:
        """Return enabled workers in stable registry order."""
        return tuple(
            self.workers[name]
            for name in SUPPORTED_ADAPTERS
            if self.workers[name].enabled
        )


@dataclass(frozen=True)
class UserPaths:
    """XDG-derived paths used by the relay, without touching the filesystem."""

    home: Path
    config_home: Path
    data_home: Path
    state_home: Path
    config_file: Path
    state_dir: Path

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        home: str | os.PathLike[str] | None = None,
    ) -> "UserPaths":
        env = os.environ if environ is None else environ
        home_path = Path(home if home is not None else env.get("HOME", str(Path.home())))

        def xdg(name: str, default: Path) -> Path:
            value = env.get(name)
            return Path(value) if value else default

        config_home = xdg("XDG_CONFIG_HOME", home_path / ".config")
        data_home = xdg("XDG_DATA_HOME", home_path / ".local" / "share")
        state_home = xdg("XDG_STATE_HOME", home_path / ".local" / "state")
        relay_config_dir = config_home / "harness-relay"
        return cls(
            home=home_path,
            config_home=config_home,
            data_home=data_home,
            state_home=state_home,
            config_file=relay_config_dir / "config.json",
            state_dir=state_home / "harness-relay",
        )

    def with_config_paths(self, config: RelayConfig) -> dict[str, Path]:
        """Resolve configured paths, falling back to XDG user-local paths."""
        data = _path_from_config(config.paths, "data", self.data_home / "harness-relay")
        worktrees = _path_from_config(config.paths, "worktrees", data / "worktrees")
        artifacts = _path_from_config(config.paths, "artifacts", data / "artifacts")
        return {"data": data, "worktrees": worktrees, "artifacts": artifacts}


def default_config() -> RelayConfig:
    """Return safe defaults: every worker is disabled and nothing is probed."""
    return RelayConfig(
        version=SUPPORTED_CONFIG_VERSION,
        workers={name: WorkerConfig(name=name) for name in SUPPORTED_ADAPTERS},
        roles={},
        paths={},
    )


def parse_config(document: Any, source: str = "<config>") -> RelayConfig:
    """Validate a decoded JSON document and return a typed configuration."""
    if not isinstance(document, dict):
        raise ConfigurationError(f"{source}: root must be a JSON object")
    allowed = {"version", "workers", "roles", "paths"}
    _reject_unknown(document, allowed, source)
    if "version" not in document:
        raise ConfigurationError(f"{source}: missing required key 'version'")
    version = document["version"]
    if type(version) is not int:
        raise ConfigurationError(f"{source}: 'version' must be an integer")
    if version != SUPPORTED_CONFIG_VERSION:
        raise ConfigurationError(
            f"{source}: unsupported config version {version}; supported version is "
            f"{SUPPORTED_CONFIG_VERSION}"
        )

    workers_value = document.get("workers", {})
    if not isinstance(workers_value, dict):
        raise ConfigurationError(f"{source}.workers: must be an object")
    workers = {name: WorkerConfig(name=name) for name in SUPPORTED_ADAPTERS}
    for name, value in workers_value.items():
        if not isinstance(name, str) or name not in SUPPORTED_ADAPTERS:
            supported = ", ".join(SUPPORTED_ADAPTERS)
            raise ConfigurationError(
                f"{source}.workers: unknown adapter {name!r}; supported adapters: {supported}"
            )
        if not isinstance(value, dict):
            raise ConfigurationError(f"{source}.workers.{name}: must be an object")
        _reject_unknown(value, WORKER_FIELDS, f"{source}.workers.{name}")
        enabled = value.get("enabled", False)
        if type(enabled) is not bool:
            raise ConfigurationError(
                f"{source}.workers.{name}.enabled: must be a boolean"
            )
        executable = value.get("executable")
        if executable is not None:
            if not isinstance(executable, str) or not executable.strip():
                raise ConfigurationError(
                    f"{source}.workers.{name}.executable: must be a non-empty string"
                )
            if "\x00" in executable:
                raise ConfigurationError(
                    f"{source}.workers.{name}.executable: must not contain NUL"
                )
        workers[name] = WorkerConfig(name=name, enabled=enabled, executable=executable)

    roles_value = document.get("roles", {})
    if not isinstance(roles_value, dict):
        raise ConfigurationError(f"{source}.roles: must be an object")
    roles: dict[str, str] = {}
    for role, adapter in roles_value.items():
        if not isinstance(role, str) or not ROLE_NAME.fullmatch(role):
            raise ConfigurationError(
                f"{source}.roles: invalid role name {role!r}; use letters, digits, "
                "'-' or '_'"
            )
        if not isinstance(adapter, str):
            raise ConfigurationError(f"{source}.roles.{role}: must name an adapter")
        if adapter not in SUPPORTED_ADAPTERS:
            raise ConfigurationError(
                f"{source}.roles.{role}: unknown adapter {adapter!r}; supported adapters: "
                + ", ".join(SUPPORTED_ADAPTERS)
            )
        if not workers[adapter].enabled:
            raise ConfigurationError(
                f"{source}.roles.{role}: adapter {adapter!r} is not enabled"
            )
        roles[role] = adapter

    paths_value = document.get("paths", {})
    if not isinstance(paths_value, dict):
        raise ConfigurationError(f"{source}.paths: must be an object")
    _reject_unknown(paths_value, PATH_FIELDS, f"{source}.paths")
    paths: dict[str, str] = {}
    for name, value in paths_value.items():
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"{source}.paths.{name}: must be a non-empty string")
        if "\x00" in value:
            raise ConfigurationError(f"{source}.paths.{name}: must not contain NUL")
        paths[name] = value

    return RelayConfig(
        version=SUPPORTED_CONFIG_VERSION,
        workers=workers,
        roles=roles,
        paths=paths,
    )


def load_config(path: str | os.PathLike[str]) -> RelayConfig:
    """Load and strictly validate one JSON (not JSONC) relay config file."""
    config_path = Path(path)
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigurationError(f"config file not found: {config_path}") from exc
    except OSError as exc:
        raise ConfigurationError(f"cannot read config file {config_path}: {exc}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"{config_path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return parse_config(document, str(config_path))


def config_document(config: RelayConfig) -> dict[str, Any]:
    """Return the stable JSON representation used by setup and examples."""
    workers: dict[str, dict[str, Any]] = {}
    for name in SUPPORTED_ADAPTERS:
        worker = config.workers[name]
        value: dict[str, Any] = {"enabled": worker.enabled}
        if worker.executable is not None:
            value["executable"] = worker.executable
        if worker.enabled or worker.executable is not None:
            workers[name] = value
    return {
        "version": config.version,
        "workers": workers,
        "roles": dict(sorted(config.roles.items())),
        "paths": dict(sorted(config.paths.items())),
    }


def dump_config(config: RelayConfig) -> str:
    """Serialize a validated config deterministically as strict JSON."""
    return json.dumps(config_document(config), indent=2, sort_keys=False) + "\n"


def config_with_overrides(
    config: RelayConfig,
    *,
    enabled: set[str] | None = None,
    roles: Mapping[str, str] | None = None,
    executables: Mapping[str, str] | None = None,
    paths: Mapping[str, str] | None = None,
) -> RelayConfig:
    """Apply setup CLI choices, then run the same strict validation."""
    document = config_document(config)
    worker_doc = document["workers"]
    if enabled is not None:
        for name in SUPPORTED_ADAPTERS:
            worker = dict(worker_doc.get(name, {}))
            worker["enabled"] = name in enabled
            worker_doc[name] = worker
    if executables:
        for name, executable in executables.items():
            if name not in SUPPORTED_ADAPTERS:
                raise ConfigurationError(f"unknown adapter {name!r} in executable override")
            worker = dict(worker_doc.get(name, {"enabled": False}))
            worker["executable"] = executable
            worker_doc[name] = worker
    if roles is not None:
        document["roles"] = dict(roles)
    if paths:
        merged_paths = dict(document["paths"])
        merged_paths.update(paths)
        document["paths"] = merged_paths
    return parse_config(document, "setup options")


def _path_from_config(values: Mapping[str, str], key: str, default: Path) -> Path:
    value = values.get(key)
    if value is None:
        return default
    return Path(os.path.expanduser(value))


def _reject_unknown(document: Mapping[Any, Any], allowed: set[str] | frozenset[str], source: str) -> None:
    unknown = [key for key in document if key not in allowed]
    if unknown:
        raise ConfigurationError(
            f"{source}: unknown key(s): " + ", ".join(repr(key) for key in unknown)
        )
