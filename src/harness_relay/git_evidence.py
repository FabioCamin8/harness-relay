"""Read-only Git evidence capture for native task results."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any, Iterable


class GitEvidenceError(ValueError):
    """Raised when a requested Git evidence operation cannot be completed."""


def capture_base(cwd: str | Path) -> str:
    """Capture the current repository HEAD without changing repository state."""
    return _git_text(Path(cwd), ("rev-parse", "--verify", "HEAD"), "capture base revision")


def capture_snapshot(cwd: str | Path, base_sha: str | None = None) -> dict[str, Any]:
    """Capture current HEAD and all changes relative to ``base_sha``."""
    root = Path(cwd)
    head = _git_text(root, ("rev-parse", "--verify", "HEAD"), "capture HEAD")
    committed = []
    if base_sha is not None:
        committed = _name_status(root, ("diff", "--name-status", "-z", "--find-renames", f"{base_sha}..{head}"))
    staged_changes = _name_status(
        root, ("diff", "--cached", "--name-status", "-z", "--find-renames")
    )
    unstaged_changes = _name_status(
        root, ("diff", "--name-status", "-z", "--find-renames")
    )
    untracked_files = _untracked(root)
    status = _status(root)
    return {
        "head": head,
        "committed_delta": committed,
        "staged": bool(staged_changes),
        "staged_changes": staged_changes,
        "unstaged": bool(unstaged_changes),
        "unstaged_changes": unstaged_changes,
        "untracked": bool(untracked_files),
        "untracked_files": untracked_files,
        "status": status,
        "clean": not (staged_changes or unstaged_changes or untracked_files),
    }


def _git_text(cwd: Path, args: tuple[str, ...], operation: str) -> str:
    try:
        completed = subprocess.run(
            ("git", *args),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GitEvidenceError(f"cannot {operation}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise GitEvidenceError(f"cannot {operation}: {detail or 'git failed'}")
    return completed.stdout.decode("ascii", "strict").strip()


def _name_status(cwd: Path, args: tuple[str, ...]) -> list[dict[str, str | None]]:
    raw = _git_bytes(cwd, args, "capture Git name-status evidence")
    return _parse_name_status(raw)


def _untracked(cwd: Path) -> list[str]:
    raw = _git_bytes(
        cwd,
        ("ls-files", "--others", "--exclude-standard", "-z"),
        "capture untracked files",
    )
    return [_decode_path(item) for item in raw.split(b"\0") if item]


def _status(cwd: Path) -> list[dict[str, str | None]]:
    raw = _git_bytes(cwd, ("status", "--porcelain=v1", "-z"), "capture Git status")
    result: list[dict[str, str | None]] = []
    parts = [part for part in raw.split(b"\0") if part]
    index = 0
    while index < len(parts):
        token = parts[index]
        if len(token) < 3:
            raise GitEvidenceError("git returned malformed porcelain status")
        status = token[:2].decode("ascii", "replace")
        path = token[3:]
        old_path: bytes | None = None
        if "R" in status or "C" in status:
            index += 1
            if index >= len(parts):
                raise GitEvidenceError("git returned incomplete rename status")
            old_path = parts[index]
        result.append(
            {
                "status": status,
                "path": _decode_path(path),
                "old_path": _decode_path(old_path) if old_path is not None else None,
            }
        )
        index += 1
    return result


def _git_bytes(cwd: Path, args: tuple[str, ...], operation: str) -> bytes:
    try:
        completed = subprocess.run(
            ("git", *args),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GitEvidenceError(f"cannot {operation}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise GitEvidenceError(f"cannot {operation}: {detail or 'git failed'}")
    return completed.stdout


def _parse_name_status(raw: bytes) -> list[dict[str, str | None]]:
    parts = [part for part in raw.split(b"\0") if part]
    result: list[dict[str, str | None]] = []
    index = 0
    while index < len(parts):
        token = parts[index]
        if b"\t" in token:
            status_bytes, path = token.split(b"\t", 1)
        else:
            status_bytes = token
            index += 1
            if index >= len(parts):
                raise GitEvidenceError("git returned incomplete name-status evidence")
            path = parts[index]
        status = status_bytes.decode("ascii", "replace")
        old_path: bytes | None = None
        if status.startswith(("R", "C")):
            old_path = path
            index += 1
            if index >= len(parts):
                raise GitEvidenceError("git returned incomplete rename evidence")
            path = parts[index]
        result.append(
            {
                "status": status,
                "path": _decode_path(path),
                "old_path": _decode_path(old_path) if old_path is not None else None,
            }
        )
        index += 1
    return result


def _decode_path(value: bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "surrogateescape")


__all__ = ["GitEvidenceError", "capture_base", "capture_snapshot"]
