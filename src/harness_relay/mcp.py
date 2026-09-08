"""Minimal bounded MCP 2025-11-25 JSON-RPC stdio server."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import uuid
from typing import Any, BinaryIO, TextIO

import jsonschema

from .adapters import TaskRequest
from .configuration import RelayConfig, UserPaths
from .discovery import discover_worker
from .execution import REENTRY_ENV, run_task
from .workspace import RUN_ID, atomic_json, capture_integrity, integrity_changed, reserve_worktree


PROTOCOL_VERSION = "2025-11-25"
MAX_MESSAGE = 1_048_576


class McpServer:
    def __init__(self, config: RelayConfig, paths: UserPaths, stdout: TextIO | None = None) -> None:
        self.config = config
        self.paths = paths
        self.stdout = stdout or sys.stdout
        self.initialized = False
        self.ready = False
        self.lock = threading.Lock()
        self.active: dict[Any, tuple[str, threading.Event]] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.capacity = max(1, len(config.enabled_workers))
        self.pool = ThreadPoolExecutor(max_workers=self.capacity)
        self.state_dir = paths.state_dir / "runs"

    def serve(self, stdin: BinaryIO | None = None) -> None:
        stream = stdin or sys.stdin.buffer
        try:
            while True:
                raw = stream.readline(MAX_MESSAGE + 2)
                if not raw:
                    break
                if len(raw) > MAX_MESSAGE or not raw.endswith(b"\n"):
                    self._write(self._error(None, -32600, "message too large or incomplete"))
                    continue
                try:
                    message = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._write(self._error(None, -32700, "parse error"))
                    continue
                self.handle(message)
        finally:
            with self.lock:
                events = [event for _, event in self.active.values()]
            for event in events:
                event.set()
            self.pool.shutdown(wait=True, cancel_futures=True)

    def handle(self, message: Any) -> None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            self._write(self._error(message.get("id") if isinstance(message, dict) else None, -32600, "invalid request"))
            return
        method, request_id = message["method"], message.get("id")
        params = message.get("params", {})
        if method == "initialize":
            if request_id is None or self.initialized or not isinstance(params, dict):
                self._write(self._error(request_id, -32600, "invalid initialize request")); return
            self.initialized = True
            self._write({"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": {"name": "harness-relay", "version": "0.1.0a1"}}})
            return
        if method == "notifications/initialized":
            if self.initialized and request_id is None:
                self.ready = True
            return
        if not self.ready:
            if request_id is not None:
                self._write(self._error(request_id, -32600, "server not initialized"))
            return
        if method == "notifications/cancelled":
            if isinstance(params, dict):
                with self.lock:
                    active = self.active.get(params.get("requestId"))
                if active:
                    active[1].set()
            return
        if request_id is None:
            return
        if method == "tools/list":
            self._write({"jsonrpc": "2.0", "id": request_id, "result": {"tools": self._tools()}})
        elif method == "tools/call":
            self._call(request_id, params)
        else:
            self._write(self._error(request_id, -32601, "method not found"))

    def _tools(self) -> list[dict[str, Any]]:
        tools = [self._tool(f"delegate_{worker.name}", "Run a bounded native worker", self._delegate_schema()) for worker in self.config.enabled_workers]
        run_schema = {"type": "object", "properties": {"run_id": {"type": "string", "pattern": RUN_ID.pattern}}, "required": ["run_id"], "additionalProperties": False}
        tools.extend((self._tool("run_status", "Inspect an in-process or retained run", run_schema), self._tool("cancel_run", "Cancel an in-process run", run_schema)))
        return tools

    @staticmethod
    def _tool(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {"name": name, "description": description, "inputSchema": schema}

    @staticmethod
    def _delegate_schema() -> dict[str, Any]:
        return {"type": "object", "properties": {"prompt": {"type": "string", "minLength": 1, "maxLength": 65536}, "repository": {"type": "string", "minLength": 1}, "base_sha": {"type": "string", "minLength": 4, "maxLength": 64}, "read_only": {"type": "boolean"}, "timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600}, "model": {"type": "string", "minLength": 1}, "effort": {"type": "string", "minLength": 1}, "sandbox": {"enum": ["read-only", "workspace-write", "danger-full-access"]}}, "required": ["prompt", "repository", "base_sha"], "additionalProperties": False}

    def _call(self, request_id: Any, params: Any) -> None:
        if not isinstance(params, dict) or not isinstance(params.get("name"), str) or not isinstance(params.get("arguments", {}), dict):
            self._write(self._error(request_id, -32602, "invalid tool call")); return
        name, arguments = params["name"], params.get("arguments", {})
        known = {tool["name"]: tool for tool in self._tools()}
        if name not in known:
            self._write(self._error(request_id, -32602, "unknown or disabled tool")); return
        try:
            jsonschema.validate(arguments, known[name]["inputSchema"])
        except jsonschema.ValidationError as exc:
            self._write(self._error(request_id, -32602, "invalid tool arguments", {"path": list(exc.absolute_path)})); return
        if name == "run_status":
            run_id = arguments["run_id"]
            result = self.results.get(run_id)
            if result is None:
                try:
                    loaded = json.loads((self.state_dir / f"{run_id}.json").read_text(encoding="utf-8"))
                    result = loaded if isinstance(loaded, dict) else None
                except (FileNotFoundError, OSError, json.JSONDecodeError):
                    result = None
            result = result or {"state": "unknown", "run_id": run_id}
            self._write(self._success(request_id, result)); return
        if name == "cancel_run":
            canceled = False
            with self.lock:
                for _, (run_id, event) in self.active.items():
                    if run_id == arguments["run_id"]:
                        event.set(); canceled = True
            self._write(self._success(request_id, {"run_id": arguments["run_id"], "cancellation_requested": canceled})); return
        worker_name = name.removeprefix("delegate_")
        run_id = uuid.uuid4().hex
        event = threading.Event()
        with self.lock:
            duplicate = request_id in self.active
            busy = len(self.active) >= self.capacity
            if not duplicate and not busy:
                self.active[request_id] = (run_id, event)
                self.results[run_id] = {"run_id": run_id, "state": "running"}
        if duplicate:
            self._write(self._error(request_id, -32600, "duplicate active request id")); return
        if busy:
            self._write(self._success(request_id, {"state": "busy", "message": "worker capacity is in use"}, error=True)); return
        self._persist(run_id)
        self.pool.submit(self._execute, request_id, run_id, worker_name, arguments, event)

    def _execute(self, request_id: Any, run_id: str, worker_name: str, arguments: dict[str, Any], event: threading.Event) -> None:
        try:
            roots = self.paths.with_config_paths(self.config)
            reservation = reserve_worktree(
                roots["worktrees"],
                Path(arguments["repository"]),
                arguments["base_sha"],
                run_id,
            )
            with self.lock:
                self.results[run_id].update(
                    workspace=str(reservation.worktree), base_sha=reservation.base_sha
                )
            self._persist(run_id)
            before = capture_integrity(reservation.worktree)
            worker = discover_worker(self.config.workers[worker_name])
            sandbox = arguments.get("sandbox")
            if arguments.get("read_only") and worker_name == "codex":
                sandbox = "read-only"
            result = run_task(worker, TaskRequest(prompt=arguments["prompt"], cwd=reservation.worktree, timeout=arguments.get("timeout", 300), model=arguments.get("model"), effort=arguments.get("effort"), sandbox=sandbox), cancel_event=event, base_sha=reservation.base_sha, run_id=run_id)
            after = capture_integrity(reservation.worktree)
            state = "canceled" if result["process"]["classification"] == "canceled" else "completed"
            stored = {"run_id": run_id, "state": state, "workspace": str(reservation.worktree), "base_sha": reservation.base_sha, "read_only": bool(arguments.get("read_only")), "integrity_changed": integrity_changed(before, after), "result": result}
            if arguments.get("read_only") and stored["integrity_changed"]:
                stored["state"] = "failed"
                stored["error"] = "read-only integrity boundary changed"
        except Exception as exc:
            stored = {"run_id": run_id, "state": "failed", "error": str(exc)[:1000]}
        with self.lock:
            self.results[run_id] = stored
            self.active.pop(request_id, None)
        self._persist(run_id)
        if not event.is_set():
            self._write(self._success(request_id, stored, error=stored["state"] == "failed"))

    def _persist(self, run_id: str) -> None:
        atomic_json(self.state_dir / f"{run_id}.json", self.results[run_id])

    @staticmethod
    def _success(request_id: Any, value: Any, error: bool = False) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}], "isError": error}}

    @staticmethod
    def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None: error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    def _write(self, value: dict[str, Any]) -> None:
        line = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(line.encode()) > MAX_MESSAGE:
            line = json.dumps(self._error(value.get("id"), -32603, "response too large"), separators=(",", ":"))
        with self.lock:
            self.stdout.write(line + "\n")
            self.stdout.flush()


def serve_stdio(config: RelayConfig, paths: UserPaths) -> None:
    if os.environ.get(REENTRY_ENV) == "1":
        raise RuntimeError("HarnessRelay recursion refused")
    McpServer(config, paths).serve()
