"""Static native worker contracts and argv construction.

HarnessRelay does not emulate a model or choose a provider.  These adapters
only describe how to invoke an explicitly selected native executable while
leaving its configuration, authentication, permissions, and internal agents
under native-harness control.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .configuration import ADAPTER_REGISTRY, AdapterSpec
from .discovery import DetectedWorker


class AdapterError(ValueError):
    """Raised when a native invocation cannot be constructed safely."""


class UnsupportedOverrideError(AdapterError):
    """Raised when a requested task override is unsupported by an adapter."""


class UnsupportedVersionError(UnsupportedOverrideError):
    """Raised when a detected executable is outside the verified contract."""


@dataclass(frozen=True)
class TaskRequest:
    """Validated task inputs shared by every native adapter."""

    prompt: str
    cwd: Path
    model: str | None = None
    effort: str | None = None
    sandbox: str | None = None
    timeout: float = 300.0

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt:
            raise AdapterError("task prompt must be a non-empty string")
        if "\x00" in self.prompt:
            raise AdapterError("task prompt must not contain NUL")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not self.cwd.is_absolute():
            raise AdapterError("task cwd must be an absolute path")
        if not self.cwd.is_dir():
            raise AdapterError(f"task cwd is not a directory: {self.cwd}")
        for name, value in (("model", self.model), ("effort", self.effort)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise AdapterError(f"task {name} override must be a non-empty string")
            if isinstance(value, str) and "\x00" in value:
                raise AdapterError(f"task {name} override must not contain NUL")
        if self.sandbox is not None and self.sandbox not in {
            "read-only",
            "workspace-write",
            "danger-full-access",
        }:
            raise AdapterError(
                "unsupported Codex sandbox policy; choose read-only, workspace-write, "
                "or danger-full-access"
            )
        if self.timeout <= 0:
            raise AdapterError("task timeout must be greater than zero")


@dataclass(frozen=True)
class Invocation:
    """A shell-free native process invocation."""

    argv: tuple[str, ...]
    cwd: Path
    input_text: str | None = None


NativeAdapter = AdapterSpec
ADAPTERS_BY_NAME: Mapping[str, NativeAdapter] = {
    adapter.name: adapter for adapter in ADAPTER_REGISTRY
}


def adapter_for(name: str) -> NativeAdapter:
    """Return one statically registered adapter or reject the name."""
    try:
        return ADAPTERS_BY_NAME[name]
    except KeyError as exc:
        raise AdapterError(f"unknown native adapter {name!r}") from exc


def build_invocation(worker: DetectedWorker, task: TaskRequest) -> Invocation:
    """Construct native argv without shell interpolation or fallback."""
    adapter = adapter_for(worker.name)
    if not adapter.supports_version(worker.version):
        supported = ", ".join(adapter.supported_versions)
        raise UnsupportedVersionError(
            f"unsupported {worker.name} version {worker.version!r}; "
            f"verified versions: {supported}"
        )
    if task.effort is not None and task.effort not in adapter.effort_values:
        if not adapter.effort_values:
            raise UnsupportedOverrideError(
                f"{worker.name} does not support an effort override"
            )
        values = ", ".join(sorted(adapter.effort_values))
        raise UnsupportedOverrideError(
            f"unsupported {worker.name} effort {task.effort!r}; choose: {values}"
        )
    if task.sandbox is not None and not adapter.codex_sandbox:
        raise UnsupportedOverrideError(
            f"{worker.name} does not support a Codex sandbox override"
        )

    executable = str(worker.executable)
    if adapter.name == "codex":
        args = [executable, "exec", "--json"]
        if task.sandbox is not None:
            args.extend(("--sandbox", task.sandbox))
        if task.model is not None:
            args.extend(("--model", task.model))
        args.extend(("--cd", str(task.cwd), task.prompt))
    else:
        args = [executable, "-p", "--output-format", adapter.output_format]
        if task.model is not None:
            args.extend(("--model", task.model))
        if task.effort is not None:
            args.extend(("--effort", task.effort))
        args.append(task.prompt)
    return Invocation(tuple(args), task.cwd)


__all__ = [
    "AdapterError",
    "UnsupportedOverrideError",
    "UnsupportedVersionError",
    "TaskRequest",
    "Invocation",
    "NativeAdapter",
    "ADAPTER_REGISTRY",
    "ADAPTERS_BY_NAME",
    "adapter_for",
    "build_invocation",
    "DetectedWorker",
]
