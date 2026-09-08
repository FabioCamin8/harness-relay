"""Bounded shell-free native execution and result assembly."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
from typing import Any, Mapping, Sequence

from .adapters import DetectedWorker, TaskRequest, build_invocation
from .git_evidence import GitEvidenceError, capture_base, capture_snapshot
from .results import NativeReport, build_result, parse_native_output, validate_result


REENTRY_ENV = "HARNESS_RELAY_ACTIVE"


@dataclass(frozen=True)
class ValidationRequest:
    """An independently executed validation command, represented as argv."""

    argv: tuple[str, ...] | Sequence[str]
    cwd: Path
    timeout: float = 300.0

    def __post_init__(self) -> None:
        normalized = tuple(str(item) for item in self.argv)
        if not normalized or any(not item or "\x00" in item for item in normalized):
            raise ValueError("validation argv must contain non-empty NUL-free arguments")
        object.__setattr__(self, "argv", normalized)
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not self.cwd.is_absolute():
            raise ValueError("validation cwd must be an absolute path")
        if self.timeout <= 0:
            raise ValueError("validation timeout must be greater than zero")


def run_task(
    worker: DetectedWorker,
    task: TaskRequest,
    *,
    environment: Mapping[str, str] | None = None,
    cancel_event: threading.Event | None = None,
    validation: ValidationRequest | None = None,
    base_sha: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run one selected native worker and normalize all observable evidence."""
    if os.environ.get(REENTRY_ENV) == "1" or (
        environment is not None and environment.get(REENTRY_ENV) == "1"
    ):
        raise RuntimeError("HarnessRelay recursion refused")
    invocation = build_invocation(worker, task)
    run_identifier = run_id or uuid.uuid4().hex

    git_context = _git_before(task.cwd, base_sha)
    process, stdout, stderr = _run_process(
        invocation.argv,
        invocation.cwd,
        task.timeout,
        environment,
        cancel_event,
    )
    native = parse_native_output(stdout, adapter=worker.name)
    if process["classification"] == "timeout":
        native = _with_outcome(native, "timeout")
    elif process["classification"] == "canceled":
        native = _with_outcome(native, "canceled")
    elif process["classification"] == "executable_missing":
        native = _with_outcome(native, "unknown")

    after_worker = _git_after(task.cwd, git_context)
    validation_value: dict[str, Any]
    after_validation = after_worker
    if validation is None:
        validation_value = {
            "executed": False,
            "outcome": "not_run",
            "process": None,
            "argv": None,
            "stdout": "",
            "stderr": "",
        }
    else:
        validation_process, validation_stdout, validation_stderr = _run_process(
            validation.argv,
            validation.cwd,
            validation.timeout,
            environment,
            cancel_event,
        )
        validation_outcome = _validation_outcome(validation_process)
        validation_value = {
            "executed": True,
            "outcome": validation_outcome,
            "process": validation_process,
            "argv": list(validation.argv),
            "stdout": _evidence_text(validation_stdout),
            "stderr": _evidence_text(validation_stderr),
        }
        after_validation = _git_after(task.cwd, git_context)

    result = build_result(
        run_id=run_identifier,
        worker=worker.name,
        worker_version=worker.version,
        process=process,
        native=native,
        invocation={
            "argv": [
                "[TASK_PROMPT]" if item == task.prompt else item
                for item in invocation.argv
            ],
            "cwd": str(invocation.cwd),
        },
        validation=validation_value,
        git={
            "repository": git_context["repository"],
            "base": git_context["base"],
            "after_worker": after_worker,
            "after_validation": after_validation,
            "errors": list(git_context["errors"]),
        },
        stdout=stdout,
        stderr=stderr,
    )
    # This catches accidental contract drift in every execution path while
    # retaining the structured evidence in the returned value.
    validate_result(result)
    return result


def _run_process(
    argv: Sequence[str],
    cwd: Path,
    timeout: float,
    environment: Mapping[str, str] | None,
    cancel_event: threading.Event | None,
) -> tuple[dict[str, Any], bytes, bytes]:
    if cancel_event is not None and cancel_event.is_set():
        return (
            {
                "started": False,
                "completed": False,
                "exit_code": None,
                "classification": "canceled",
            },
            b"",
            b"",
        )
    env = os.environ.copy()
    if environment is not None:
        env.update({str(key): str(value) for key, value in environment.items()})
    env[REENTRY_ENV] = "1"
    try:
        process = subprocess.Popen(
            tuple(argv),
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return (
            {
                "started": False,
                "completed": False,
                "exit_code": None,
                "classification": "executable_missing",
            },
            b"",
            _error_bytes(exc),
        )
    except OSError as exc:
        return (
            {
                "started": False,
                "completed": False,
                "exit_code": None,
                "classification": "spawn_error",
            },
            b"",
            _error_bytes(exc),
        )

    deadline = time.monotonic() + timeout
    timed_out = False
    canceled = False
    stdout = b""
    stderr = b""
    while True:
        if cancel_event is not None and cancel_event.is_set():
            canceled = True
            _stop_process(process)
            stdout, stderr = process.communicate()
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            _stop_process(process)
            stdout, stderr = process.communicate()
            break
        try:
            stdout, stderr = process.communicate(timeout=min(remaining, 0.1))
            break
        except subprocess.TimeoutExpired:
            continue

    returncode = process.returncode
    if canceled:
        classification = "canceled"
        completed = False
    elif timed_out:
        classification = "timeout"
        completed = False
    elif returncode == 0:
        classification = "completed"
        completed = True
    else:
        classification = "failed"
        completed = True
    return (
        {
            "started": True,
            "completed": completed,
            "exit_code": returncode,
            "classification": classification,
        },
        stdout,
        stderr,
    )


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=0.5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=0.5)
        except ProcessLookupError:
            return


def _validation_outcome(process: Mapping[str, Any]) -> str:
    classification = process.get("classification")
    if classification == "timeout":
        return "timeout"
    if classification == "canceled":
        return "canceled"
    if classification == "completed" and process.get("exit_code") == 0:
        return "passed"
    if classification in {"completed", "failed"}:
        return "failed"
    return "error"


def _with_outcome(report: NativeReport, outcome: str) -> NativeReport:
    return NativeReport(
        outcome,
        report.structured,
        report.events,
        report.claims,
        report.summary,
        report.parse_error,
    )


def _error_bytes(exc: BaseException) -> bytes:
    return f"{type(exc).__name__}: {exc}".encode("utf-8", "replace")


def _evidence_text(value: bytes) -> str:
    return value.decode("utf-8", "replace")


def _git_before(cwd: Path, supplied_base: str | None) -> dict[str, Any]:
    try:
        base = supplied_base or capture_base(cwd)
    except GitEvidenceError:
        return {"repository": False, "base": None, "errors": []}
    return {"repository": True, "base": base, "errors": []}


def _git_after(cwd: Path, context: Mapping[str, Any]) -> dict[str, Any] | None:
    if not context.get("repository"):
        return None
    try:
        return capture_snapshot(cwd, context.get("base"))
    except GitEvidenceError as exc:
        errors = context.get("errors")
        if isinstance(errors, list):
            errors.append(str(exc))
        return None


__all__ = ["ValidationRequest", "run_task"]
