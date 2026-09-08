"""Owned worktree reservation and content-integrity boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any


RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class WorkspaceError(ValueError):
    """Raised when an owned workspace operation would be ambiguous or unsafe."""


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise WorkspaceError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def repository_identity(repo: Path) -> str:
    """Return a collision-resistant identity for the actual Git common directory."""
    root = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    common_text = _git(root, "rev-parse", "--git-common-dir")
    common = Path(common_text)
    if not common.is_absolute():
        common = root / common
    material = f"{root}\0{common.resolve()}".encode()
    return hashlib.sha256(material).hexdigest()[:24]


def capture_integrity(repo: Path) -> dict[str, Any]:
    """Capture revision and content evidence, including pre-existing dirty files."""
    root = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    head = _git(root, "rev-parse", "HEAD")
    files = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    digest = hashlib.sha256()
    paths: list[str] = []
    for relative in sorted(filter(None, files.splitlines())):
        path = root / relative
        paths.append(relative)
        digest.update(relative.encode("utf-8", "surrogateescape") + b"\0")
        if path.is_symlink():
            digest.update(b"L" + os.readlink(path).encode("utf-8", "surrogateescape"))
        elif path.is_file():
            digest.update(b"F" + path.read_bytes())
        else:
            digest.update(b"M")
        digest.update(b"\0")
    return {"root": str(root), "head": head, "content_sha256": digest.hexdigest(), "paths": paths}


def integrity_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return before.get("head") != after.get("head") or before.get("content_sha256") != after.get("content_sha256")


@dataclass(frozen=True)
class Reservation:
    run_id: str
    repository_id: str
    source: Path
    worktree: Path
    base_sha: str
    record: Path


def reserve_worktree(root: Path, source: Path, base_sha: str, run_id: str) -> Reservation:
    """Atomically reserve and create an owned detached worktree from an explicit commit."""
    if not RUN_ID.fullmatch(run_id):
        raise WorkspaceError("invalid run id")
    source = source.expanduser().resolve()
    base = _git(source, "rev-parse", "--verify", f"{base_sha}^{{commit}}")
    repository_id = repository_identity(source)
    requested_root = root.expanduser()
    if requested_root.is_symlink():
        raise WorkspaceError("managed worktree root must not be a symlink")
    managed = requested_root.resolve()
    managed.mkdir(parents=True, exist_ok=True)
    repo_root = managed / repository_id
    if repo_root.is_symlink():
        raise WorkspaceError("managed repository directory must not be a symlink")
    repo_root.mkdir(mode=0o700, exist_ok=True)
    run_root = repo_root / run_id
    try:
        run_root.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise WorkspaceError(f"run already exists: {run_id}") from exc
    worktree = run_root / "worktree"
    record = run_root / "reservation.json"
    reservation = Reservation(run_id, repository_id, source, worktree, base, record)
    try:
        _atomic_json(record, {"run_id": run_id, "repository_id": repository_id, "source": str(source), "worktree": str(worktree), "base_sha": base, "state": "reserved"})
        _git(source, "worktree", "add", "--detach", str(worktree), base)
        _atomic_json(record, {"run_id": run_id, "repository_id": repository_id, "source": str(source), "worktree": str(worktree), "base_sha": base, "state": "ready"})
    except Exception:
        _atomic_json(record, {"run_id": run_id, "repository_id": repository_id, "source": str(source), "worktree": str(worktree), "base_sha": base, "state": "failed"})
        raise
    return reservation


def cleanup_worktree(reservation: Reservation) -> None:
    """Remove only a clean owned worktree; preserve dirty or unmerged work."""
    expected = reservation.record.parent.resolve()
    if reservation.worktree.parent.resolve() != expected or not reservation.record.is_file():
        raise WorkspaceError("workspace ownership check failed")
    if reservation.worktree.is_symlink():
        raise WorkspaceError("refusing symlink worktree")
    porcelain = _git(reservation.worktree, "status", "--porcelain=v1", "--untracked-files=all")
    unmerged = _git(reservation.worktree, "diff", "--name-only", "--diff-filter=U")
    if porcelain or unmerged:
        raise WorkspaceError("refusing to remove dirty or unmerged worktree")
    _git(reservation.source, "worktree", "remove", str(reservation.worktree))
    _atomic_json(reservation.record, {"run_id": reservation.run_id, "repository_id": reservation.repository_id, "source": str(reservation.source), "worktree": str(reservation.worktree), "base_sha": reservation.base_sha, "state": "cleaned"})


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


atomic_json = _atomic_json
