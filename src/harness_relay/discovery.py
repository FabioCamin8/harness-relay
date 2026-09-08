"""Safe discovery of explicitly enabled native worker executables."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Mapping

from .configuration import ConfigurationError, RelayConfig, WorkerConfig


class DiscoveryError(ConfigurationError):
    """Raised when an enabled worker cannot be discovered or version-checked."""


_VERSION = re.compile(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?")
_VERSION_RANGES = {
    # These are deliberately coarse major-version contracts for PR-2 setup;
    # invocation flags and output contracts belong to the adapter work package.
    "codex": {0},
    "claude": {2},
    "agy": {1},
}


@dataclass(frozen=True)
class DetectedWorker:
    name: str
    executable: Path
    version: str
    source: str


def discover_enabled(
    config: RelayConfig,
    *,
    environ: Mapping[str, str] | None = None,
    probe: bool = True,
) -> dict[str, DetectedWorker]:
    """Resolve and validate only enabled workers.

    Disabled workers are intentionally skipped, including PATH lookup and
    version subprocesses.  ``probe=False`` is useful for a pure configuration
    preview, while the normal setup path performs a harmless ``--version``
    check for each selected worker.
    """
    result: dict[str, DetectedWorker] = {}
    for worker in config.enabled_workers:
        result[worker.name] = discover_worker(
            worker, environ=environ, probe=probe
        )
    return result


def discover_worker(
    worker: WorkerConfig,
    *,
    environ: Mapping[str, str] | None = None,
    probe: bool = True,
) -> DetectedWorker:
    """Resolve one enabled worker by explicit path or PATH and inspect version."""
    if not worker.enabled:
        raise DiscoveryError(
            f"worker {worker.name!r} is disabled; disabled workers are not probed"
        )
    if worker.executable:
        candidate = Path(os.path.expanduser(worker.executable))
        source = "explicit path"
        if not candidate.is_file():
            raise DiscoveryError(
                f"enabled worker {worker.name!r} executable not found at {candidate}"
            )
        if not os.access(candidate, os.X_OK):
            raise DiscoveryError(
                f"enabled worker {worker.name!r} executable is not executable: {candidate}"
            )
    else:
        names = {"codex": "codex", "claude": "claude", "agy": "agy"}
        command = names.get(worker.name)
        if command is None:
            raise DiscoveryError(f"unknown adapter {worker.name!r}")
        search_environment = os.environ if environ is None else environ
        candidate_name = shutil.which(command, path=search_environment.get("PATH"))
        if candidate_name is None:
            raise DiscoveryError(
                f"enabled worker {worker.name!r} was not found on PATH; "
                f"set workers.{worker.name}.executable to an executable path"
            )
        candidate = Path(candidate_name)
        source = "PATH"

    if not probe:
        return DetectedWorker(worker.name, candidate, "unprobed", source)
    try:
        completed = subprocess.run(
            [str(candidate), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=5,
            env=dict(environ) if environ is not None else None,
        )
    except OSError as exc:
        raise DiscoveryError(
            f"could not run {worker.name!r} executable {candidate}: {exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DiscoveryError(
            f"{worker.name!r} executable did not return --version within 5 seconds"
        ) from exc
    if completed.returncode != 0:
        raise DiscoveryError(
            f"{worker.name!r} executable {candidate} returned {completed.returncode} "
            "for --version; check the native installation"
        )
    match = _VERSION.search(completed.stdout or "")
    if match is None:
        raise DiscoveryError(
            f"{worker.name!r} executable {candidate} did not report a supported "
            "semantic version from --version"
        )
    version = ".".join(match.groups())
    if int(match.group(1)) not in _VERSION_RANGES[worker.name]:
        expected = ", ".join(str(value) for value in sorted(_VERSION_RANGES[worker.name]))
        raise DiscoveryError(
            f"{worker.name!r} version {version} is unsupported; supported major "
            f"version(s): {expected}"
        )
    return DetectedWorker(worker.name, candidate, version, source)
