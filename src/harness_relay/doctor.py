"""Read-only, inference-free configuration and adapter diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .configuration import RelayConfig, SUPPORTED_ADAPTERS
from .discovery import DiscoveryError, discover_worker


def diagnose(config: RelayConfig, *, live_evidence: Path | None = None) -> dict[str, Any]:
    workers: dict[str, Any] = {}
    for name in SUPPORTED_ADAPTERS:
        worker = config.workers[name]
        item: dict[str, Any] = {
            "enabled": worker.enabled,
            "detected": None,
            "configured": bool(worker.executable),
            "version": None,
            "version_status": None,
            "error": None,
            "last_live_verified": None,
        }
        if worker.enabled:
            try:
                detected = discover_worker(worker)
                item.update(detected=True, version=detected.version, version_status=detected.version_status)
            except DiscoveryError as exc:
                item.update(detected=False, error=str(exc))
        if live_evidence is not None:
            candidate = live_evidence / f"{name}.json"
            if candidate.is_file():
                item["last_live_verified"] = datetime.fromtimestamp(candidate.stat().st_mtime, timezone.utc).isoformat()
        workers[name] = item
    return {"config_valid": True, "inference_called": False, "workers": workers}
