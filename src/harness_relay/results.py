"""Typed native-output classification and the versioned normalized result."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from importlib import resources
from typing import Any, Iterable, Mapping


RESULT_SCHEMA_VERSION = 1
MAX_EVIDENCE_BYTES = 256 * 1024
MAX_STRUCTURED_TEXT_BYTES = 16 * 1024
MAX_EVENT_EVIDENCE_BYTES = 128 * 1024
MAX_CLAIM_EVIDENCE_BYTES = 64 * 1024
MAX_MCP_RESULT_BYTES = 512 * 1024

_OUTCOMES = frozenset(
    (
        "success",
        "failure",
        "auth_required",
        "tool_denied",
        "canceled",
        "interrupted",
        "invalid",
        "running",
        "empty_output",
        "malformed_output",
        "timeout",
        "unknown",
    )
)
_AUTH_CODES = frozenset(
    ("authentication_error", "auth_required", "unauthorized", "unauthenticated", "invalid_api_key", "login_required")
)
_DENIAL_CODES = frozenset(
    ("permission_denied", "tool_denied", "access_denied", "forbidden", "denied")
)
_CODED_KEYS = frozenset(("code", "type", "subtype", "status", "error_type", "kind", "name"))
_SENSITIVE = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"
)


class ResultValidationError(ValueError):
    """Raised when a normalized result does not satisfy its packaged schema."""


@dataclass(frozen=True)
class NativeReport:
    """Classification and safe evidence extracted from native JSON output."""

    outcome: str
    structured: bool
    events: tuple[dict[str, Any], ...]
    claims: tuple[dict[str, str], ...]
    summary: str | None
    parse_error: str | None


def parse_native_output(
    stdout: str | bytes,
    stderr: str | bytes = b"",
    *,
    adapter: str | None = None,
) -> NativeReport:
    """Parse JSON/JSONL output and classify only typed native evidence."""
    # Native JSON is authoritative for classification. Decode only for
    # parsing here; redaction and evidence bounds apply after the event has
    # been successfully interpreted.
    stdout_text = _native_text(stdout)
    if not stdout_text.strip():
        return NativeReport("empty_output", False, (), (), None, None)

    events: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    saw_nonempty = False
    for line_number, line in enumerate(stdout_text.splitlines(), 1):
        if not line.strip():
            continue
        saw_nonempty = True
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {line_number}: {exc.msg}")
            continue
        if isinstance(value, dict):
            events.append(value)
        elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
            events.extend(value)
        else:
            parse_errors.append(f"line {line_number}: structured output must be an object")

    if not events and parse_errors:
        return NativeReport(
            "malformed_output", False, (), (), None, "; ".join(parse_errors)
        )
    if not events and saw_nonempty:
        return NativeReport("malformed_output", False, (), (), None, "no JSON events")

    claims = tuple(_claims(events))
    outcome = _classify_events(events, adapter)
    if parse_errors:
        outcome = "malformed_output"
    summary = claims[-1]["text"] if claims else None
    return NativeReport(
        outcome,
        bool(events),
        tuple(events),
        claims,
        summary,
        "; ".join(parse_errors) if parse_errors else None,
    )


def build_result(
    *,
    run_id: str,
    worker: str,
    worker_version: str,
    process: Mapping[str, Any],
    native: NativeReport,
    invocation: Mapping[str, Any],
    validation: Mapping[str, Any] | None = None,
    git: Mapping[str, Any] | None = None,
    stdout: str | bytes = b"",
    stderr: str | bytes = b"",
) -> dict[str, Any]:
    """Create one result with conservative validation and acceptance defaults."""
    validation_value = dict(
        validation
        or {
            "executed": False,
            "outcome": "not_run",
            "process": None,
            "argv": None,
            "stdout": "",
            "stderr": "",
        }
    )
    safe_claims = _bounded_items(
        native.claims,
        MAX_CLAIM_EVIDENCE_BYTES,
        _safe_claim,
        lambda omitted: {
            "kind": "worker_claim",
            "text": f"[TRUNCATED: {omitted} additional claims omitted]",
        },
    )
    safe_events = _bounded_items(
        native.events,
        MAX_EVENT_EVIDENCE_BYTES,
        _safe_event,
        lambda omitted: {
            "harness_relay_truncated": True,
            "omitted_events": omitted,
        },
    )
    result = {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "run": {
            "id": run_id,
            "worker": worker,
            "worker_version": worker_version,
        },
        "process": dict(process),
        "native": {
            "outcome": native.outcome,
            "structured": native.structured,
            "summary": (
                _safe_structured_text(native.summary)
                if native.summary is not None
                else None
            ),
            "claims": safe_claims,
        },
        "invocation": dict(invocation),
        "validation": validation_value,
        "acceptance": {
            "status": "not_checked",
            "independent": False,
            "evidence": [],
        },
        "git": dict(
            git
            or {
                "repository": False,
                "base": None,
                "after_worker": None,
                "after_validation": None,
                "errors": [],
            }
        ),
        "evidence": {
            "stdout": _safe_text(stdout),
            "stderr": _safe_text(stderr),
            "events": safe_events,
            "parse_error": (
                _safe_structured_text(native.parse_error)
                if native.parse_error is not None
                else None
            ),
        },
    }
    return _fit_mcp_result(result)


def validate_result(value: Mapping[str, Any]) -> None:
    """Validate a result against the packaged schema, raising on any defect."""
    schema = packaged_result_schema()
    try:
        import jsonschema
    except ImportError:
        _minimal_validate(value)
        return
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "result"
        raise ResultValidationError(f"{location}: {first.message}")


def packaged_result_schema() -> dict[str, Any]:
    """Load the installed result schema resource."""
    path = resources.files("harness_relay.resources").joinpath("result.schema.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResultValidationError(f"cannot load packaged result schema: {exc}") from exc


def _classify_events(
    events: Iterable[Mapping[str, Any]], adapter: str | None = None
) -> str:
    outcomes: list[str] = []
    for event in events:
        outcome = _event_outcome(event, adapter)
        if outcome is not None:
            outcomes.append(outcome)
    for preferred in (
        "auth_required",
        "tool_denied",
        "interrupted",
        "canceled",
        "invalid",
        "failure",
        "success",
        "running",
    ):
        if preferred in outcomes:
            return preferred
    return "unknown"


def _event_outcome(
    event: Mapping[str, Any], adapter: str | None = None
) -> str | None:
    codes = set(_typed_codes(event))
    if codes & _AUTH_CODES:
        return "auth_required"
    if codes & _DENIAL_CODES:
        return "tool_denied"
    permission_denials = event.get("permission_denials")
    if isinstance(permission_denials, list) and permission_denials:
        return "tool_denied"

    if adapter == "agy" and event.get("event") == "result":
        result = event.get("result")
        if isinstance(result, Mapping):
            return _event_outcome(result, adapter)

    status = event.get("status")
    if isinstance(status, str):
        status_outcome = {
            "SUCCESS": "success",
            "ERROR": "failure",
            "CANCELED": "canceled",
            "CANCELLED": "canceled",
            "INTERRUPTED": "interrupted",
            "INVALID": "invalid",
            "WAITING": "running",
            "RUNNING": "running",
        }.get(status.upper())
        if status_outcome is not None:
            return status_outcome

    event_type = event.get("type")
    subtype = event.get("subtype")
    if isinstance(event_type, str):
        if event_type in {"turn.failed", "error", "failed", "task.failed"}:
            return "failure"
        if event_type in {"turn.completed", "task.completed", "completed"}:
            return "success"
        if event_type in {"canceled", "cancelled", "task.canceled"}:
            return "canceled"
        if event_type in {"interrupted", "task.interrupted"}:
            return "interrupted"
        if event_type in {"invalid", "task.invalid"}:
            return "invalid"
        if event_type == "result" and isinstance(subtype, str):
            if subtype in {"success", "completed"}:
                return "success"
            if subtype in {"error", "failure", "failed"}:
                return "failure"
    if event.get("is_error") is True:
        return "failure"
    return None


def _typed_codes(value: Any, parent_key: str | None = None) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _CODED_KEYS and isinstance(child, str):
                yield _normalize_code(child)
            elif isinstance(child, (Mapping, list)):
                yield from _typed_codes(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _typed_codes(child, parent_key)


def _claims(events: Iterable[Mapping[str, Any]]) -> Iterable[dict[str, str]]:
    seen: set[str] = set()
    for event in events:
        for key in ("response", "result", "text", "summary"):
            value = event.get(key)
            if isinstance(value, str) and value and value not in seen:
                seen.add(value)
                yield {"kind": "worker_claim", "text": _bounded(_redact(value))}
            elif isinstance(value, Mapping):
                for claim in _claims((value,)):
                    if claim["text"] not in seen:
                        seen.add(claim["text"])
                        yield claim
        message = event.get("message")
        if isinstance(message, Mapping):
            text = message.get("content") or message.get("text")
            if isinstance(text, str) and text and text not in seen:
                seen.add(text)
                yield {"kind": "worker_claim", "text": _bounded(_redact(text))}
        item = event.get("item")
        if isinstance(item, Mapping):
            for claim in _claims((item,)):
                if claim["text"] not in seen:
                    seen.add(claim["text"])
                    yield claim


def _safe_text(value: str | bytes) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", "replace")
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    return _bounded(_redact(text))


def _native_text(value: str | bytes) -> str:
    """Decode worker output without changing bytes that affect JSON parsing."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, str):
        return value
    return str(value)


def _safe_event(value: Any) -> Any:
    """Sanitize retained event evidence while preserving its JSON shape."""
    if isinstance(value, str):
        return _safe_structured_text(value)
    if isinstance(value, list):
        return [_safe_event(item) for item in value]
    if isinstance(value, dict):
        return {
            _safe_structured_text(str(key)): _safe_event(child)
            for key, child in value.items()
        }
    return value


def _safe_claim(value: Mapping[str, str]) -> dict[str, str]:
    return {
        "kind": "worker_claim",
        "text": _safe_structured_text(value["text"]),
    }


def _safe_structured_text(value: str) -> str:
    return _bounded(_redact(value), MAX_STRUCTURED_TEXT_BYTES)


def _bounded_items(
    values: Iterable[Any],
    budget: int,
    sanitize: Any,
    marker: Any,
) -> list[Any]:
    """Retain a JSON-size-bounded prefix with an explicit omission marker."""
    source = list(values)
    retained: list[Any] = []
    for index, value in enumerate(source):
        candidate = sanitize(value)
        if _json_size([*retained, candidate]) <= budget:
            retained.append(candidate)
            continue
        omitted = len(source) - index
        truncated = marker(omitted)
        while retained and _json_size([*retained, truncated]) > budget:
            retained.pop()
            omitted += 1
            truncated = marker(omitted)
        if _json_size([*retained, truncated]) <= budget:
            retained.append(truncated)
        break
    return retained


def _json_size(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8", "replace"
        )
    )


def _mcp_text_size(value: Any) -> int:
    """Measure a value after JSON text content and protocol string escaping."""
    content = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return len(json.dumps(content, ensure_ascii=False).encode("utf-8", "replace"))


def _fit_mcp_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep a normalized result usable when embedded in one MCP text response."""
    if _mcp_text_size(result) <= MAX_MCP_RESULT_BYTES:
        return result

    marker = "[TRUNCATED: aggregate result exceeded MCP response budget]"
    for container, key in (
        (result["evidence"], "stdout"),
        (result["evidence"], "stderr"),
        (result["validation"], "stdout"),
        (result["validation"], "stderr"),
    ):
        if container[key]:
            container[key] = _bounded(str(container[key]), MAX_STRUCTURED_TEXT_BYTES)
    result["native"]["summary"] = (
        _bounded(str(result["native"]["summary"]), MAX_STRUCTURED_TEXT_BYTES)
        if result["native"]["summary"] is not None
        else None
    )
    if _mcp_text_size(result) <= MAX_MCP_RESULT_BYTES:
        return result

    result["native"]["claims"] = [{"kind": "worker_claim", "text": marker}]
    result["native"]["summary"] = marker
    result["evidence"]["events"] = [
        {"harness_relay_truncated": True, "omitted_events": len(result["evidence"]["events"])}
    ]
    if _mcp_text_size(result) <= MAX_MCP_RESULT_BYTES:
        return result

    for snapshot_name in ("after_worker", "after_validation"):
        snapshot = result["git"].get(snapshot_name)
        if not isinstance(snapshot, dict):
            continue
        for name in (
            "committed_delta",
            "staged_changes",
            "unstaged_changes",
            "status",
        ):
            if snapshot.get(name):
                snapshot[name] = [
                    {"status": "TRUNCATED", "path": marker, "old_path": None}
                ]
        if snapshot.get("untracked_files"):
            snapshot["untracked_files"] = [marker]
    if result["git"].get("errors"):
        result["git"]["errors"] = [marker]
    if result["acceptance"].get("evidence"):
        result["acceptance"]["evidence"] = [marker]
    result["invocation"]["argv"] = [result["invocation"]["argv"][0], marker]
    if result["validation"].get("argv"):
        result["validation"]["argv"] = [result["validation"]["argv"][0], marker]
    if _mcp_text_size(result) <= MAX_MCP_RESULT_BYTES:
        return result

    result["evidence"].update(
        stdout=marker,
        stderr=marker,
        parse_error=(
            marker if result["evidence"]["parse_error"] is not None else None
        ),
    )
    result["validation"].update(stdout=marker, stderr=marker)
    result["git"].update(after_worker=None, after_validation=None, errors=[marker])
    if _mcp_text_size(result) > MAX_MCP_RESULT_BYTES:
        raise ResultValidationError("normalized result exceeds MCP response budget")
    return result


def safe_evidence_text(value: str | bytes) -> str:
    """Return bounded, redacted text suitable for persisted public evidence."""
    return _safe_text(value)


def _bounded(value: str, limit: int = MAX_EVIDENCE_BYTES) -> str:
    encoded = value.encode("utf-8", "replace")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", "replace") + "\n[TRUNCATED]"


def _redact(value: str) -> str:
    return _SENSITIVE.sub(lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]", value)


def _normalize_code(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _minimal_validate(value: Mapping[str, Any]) -> None:
    """Dependency-free guard for production installs without the test extra."""
    if not isinstance(value, Mapping):
        raise ResultValidationError("result must be an object")
    if type(value.get("result_schema_version")) is not int or value.get("result_schema_version") != RESULT_SCHEMA_VERSION:
        raise ResultValidationError("result_schema_version must be integer 1")
    for name in ("run", "process", "native", "invocation", "validation", "acceptance", "git", "evidence"):
        if not isinstance(value.get(name), Mapping):
            raise ResultValidationError(f"{name} must be an object")


__all__ = [
    "RESULT_SCHEMA_VERSION",
    "MAX_EVIDENCE_BYTES",
    "ResultValidationError",
    "NativeReport",
    "parse_native_output",
    "build_result",
    "packaged_result_schema",
    "safe_evidence_text",
    "validate_result",
]
