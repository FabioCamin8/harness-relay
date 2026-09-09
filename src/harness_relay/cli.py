"""Command-line entry point for the HarnessRelay local setup surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid
from typing import Sequence

from . import __version__
from .adapters import AdapterError, TaskRequest
from .configuration import (
    ConfigurationError,
    SUPPORTED_ADAPTERS,
    UserPaths,
    load_config,
)
from .opencode import OpenCodeConfigError
from .discovery import discover_worker
from .execution import run_task
from .doctor import diagnose
from .mcp import serve_stdio
from .results import ResultValidationError
from .setup import SetupError, SetupOptions, run_setup
from .uninstall import UninstallOptions, run_uninstall
from .workspace import reserve_worktree


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the supported public CLI surface."""
    parser = argparse.ArgumentParser(
        prog="harness-relay",
        description="Minimal, reversible setup for native HarnessRelay workers.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(dest="command")

    setup = commands.add_parser(
        "setup", help="validate workers and install the minimal OpenCode integration"
    )
    setup.add_argument(
        "--relay-config",
        "--config",
        "--file",
        dest="relay_config",
        type=Path,
        help="strict HarnessRelay JSON config (default: XDG user config)",
    )
    setup.add_argument(
        "--scope",
        choices=("global", "project", "custom"),
        default="global",
        help="OpenCode config scope to manage (default: global)",
    )
    setup.add_argument("--opencode-config", type=Path, help="custom OpenCode config path")
    setup.add_argument("--project-dir", type=Path, help="project directory for project scope")
    setup.add_argument(
        "--workers",
        help="comma-separated enabled workers; an empty value disables all workers",
    )
    setup.add_argument(
        "--role",
        action="append",
        default=[],
        metavar="ROLE=ADAPTER",
        help="optional role preference; repeatable",
    )
    setup.add_argument(
        "--executable",
        action="append",
        default=[],
        metavar="ADAPTER=PATH",
        help="explicit executable override; repeatable",
    )
    setup.add_argument("--data-path", type=str, help="user-local data path override")
    setup.add_argument("--worktrees-path", type=str, help="user-local worktree path override")
    setup.add_argument("--artifacts-path", type=str, help="user-local artifact path override")
    setup.add_argument("--dry-run", action="store_true", help="show changes without writing")
    setup.add_argument(
        "--non-interactive",
        action="store_true",
        help="do not prompt; use the supplied config and options",
    )

    uninstall = commands.add_parser(
        "uninstall", help="remove only unchanged HarnessRelay-owned integration fragments"
    )
    uninstall.add_argument(
        "--scope",
        choices=("global", "project", "custom"),
        default="global",
        help="OpenCode config scope to manage (default: global)",
    )
    uninstall.add_argument("--opencode-config", type=Path, help="custom OpenCode config path")
    uninstall.add_argument("--project-dir", type=Path, help="project directory for project scope")
    uninstall.add_argument("--dry-run", action="store_true", help="show changes without writing")

    validate = commands.add_parser("validate-config", help="validate one strict relay JSON config")
    validate.add_argument("path", type=Path, nargs="?", help="config path (default: XDG user config)")

    delegate = commands.add_parser(
        "delegate",
        aliases=("run",),
        help="run one explicitly enabled native worker and emit its normalized result",
    )
    delegate.add_argument("--relay-config", "--config", dest="relay_config", type=Path)
    delegate.add_argument("--worker", required=True, choices=SUPPORTED_ADAPTERS)
    delegate.add_argument("--prompt", required=True, help="task text passed to the native worker")
    delegate.add_argument(
        "--repository",
        type=Path,
        required=True,
        help="source Git repository; delegation always runs in a managed worktree",
    )
    delegate.add_argument(
        "--base-sha",
        required=True,
        help="exact committed base revision for the managed worktree",
    )
    delegate.add_argument(
        "--run-id",
        help="optional retained worktree identifier (generated when omitted)",
    )
    delegate.add_argument("--model")
    delegate.add_argument("--effort")
    delegate.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        help="explicit Codex sandbox override; native defaults are preserved when omitted",
    )
    delegate.add_argument("--timeout", type=float, default=300.0)

    doctor = commands.add_parser("doctor", help="read-only, inference-free diagnostics")
    doctor.add_argument("--relay-config", "--config", dest="relay_config", type=Path)
    doctor.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    mcp = commands.add_parser("mcp", help="run the bounded MCP server")
    mcp.add_argument("--relay-config", "--config", dest="relay_config", type=Path)
    mcp.add_argument("--stdio", action="store_true", help="serve newline-delimited JSON-RPC on stdio")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the supported command-line surface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            return _run_setup(args)
        if args.command == "uninstall":
            plan = run_uninstall(
                UninstallOptions(
                    scope=args.scope,
                    opencode_config=args.opencode_config,
                    project_dir=args.project_dir,
                    dry_run=args.dry_run,
                )
            )
            _print_uninstall(plan)
            return 0
        if args.command == "validate-config":
            path = args.path or UserPaths.from_environment().config_file
            config = load_config(path)
            print(
                f"valid HarnessRelay config version {config.version}; "
                f"enabled workers: {', '.join(worker.name for worker in config.enabled_workers) or 'none'}"
            )
            return 0
        if args.command in {"delegate", "run"}:
            return _run_delegate(args)
        if args.command == "doctor":
            user_paths = UserPaths.from_environment()
            report = diagnose(load_config(args.relay_config or user_paths.config_file))
            if args.json:
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            else:
                for name, item in report["workers"].items():
                    print(f"{name}: enabled={item['enabled']} detected={item['detected']} version={item['version'] or '-'}")
            return 1 if any(item["enabled"] and item["detected"] is False for item in report["workers"].values()) else 0
        if args.command == "mcp":
            if not args.stdio:
                parser.error("mcp currently requires --stdio")
            user_paths = UserPaths.from_environment()
            serve_stdio(load_config(args.relay_config or user_paths.config_file), user_paths)
            return 0
        return 0
    except (
        AdapterError,
        ConfigurationError,
        OpenCodeConfigError,
        ResultValidationError,
        SetupError,
        RuntimeError,
        OSError,
    ) as exc:
        print(f"harness-relay: error: {exc}", file=sys.stderr)
        return 2


def _run_setup(args: argparse.Namespace) -> int:
    if not args.non_interactive and args.relay_config is None and args.workers is None:
        args.scope = _prompt_scope(args.scope)
        if args.scope == "custom" and args.opencode_config is None:
            custom_path = input("Custom OpenCode config path: ").strip()
            if custom_path:
                args.opencode_config = Path(custom_path)
        args.workers = input(
            f"Enabled workers ({', '.join(SUPPORTED_ADAPTERS)}; empty for none): "
        ).strip()
        role_text = input("Role preferences (role=adapter, comma-separated; optional): ").strip()
        if role_text:
            args.role.extend(part.strip() for part in role_text.split(",") if part.strip())
        user_paths = UserPaths.from_environment()
        data_default = user_paths.data_home / "harness-relay"
        data_path = input(f"Data path ({data_default}; empty for default): ").strip()
        worktrees_path = input("Worktrees path (empty for data/worktrees): ").strip()
        artifacts_path = input("Artifacts path (empty for data/artifacts): ").strip()
        if data_path:
            args.data_path = data_path
        if worktrees_path:
            args.worktrees_path = worktrees_path
        if artifacts_path:
            args.artifacts_path = artifacts_path

    enabled = _parse_workers(args.workers) if args.workers is not None else None
    roles = _parse_assignments(args.role, "role") if args.role else None
    executables = _parse_assignments(args.executable, "executable") if args.executable else None
    paths = {
        name: value
        for name, value in (
            ("data", args.data_path),
            ("worktrees", args.worktrees_path),
            ("artifacts", args.artifacts_path),
        )
        if value is not None
    }
    plan = run_setup(
        SetupOptions(
            relay_config=args.relay_config,
            scope=args.scope,
            opencode_config=args.opencode_config,
            project_dir=args.project_dir,
            enabled=enabled,
            roles=roles,
            executables=executables,
            paths=paths or None,
            dry_run=args.dry_run,
        )
    )
    _print_setup(plan)
    return 0


def _run_delegate(args: argparse.Namespace) -> int:
    user_paths = UserPaths.from_environment()
    config = load_config(args.relay_config or user_paths.config_file)
    worker_config = config.workers[args.worker]
    if not worker_config.enabled:
        raise ConfigurationError(
            f"worker {args.worker!r} is disabled; enable it in the relay config before delegation"
        )
    worker = discover_worker(worker_config)
    roots = user_paths.with_config_paths(config)
    run_id = args.run_id or uuid.uuid4().hex
    reservation = reserve_worktree(
        roots["worktrees"],
        args.repository.expanduser().resolve(),
        args.base_sha,
        run_id,
    )
    result = run_task(
        worker,
        TaskRequest(
            prompt=args.prompt,
            cwd=reservation.worktree,
            model=args.model,
            effort=args.effort,
            sandbox=args.sandbox,
            timeout=args.timeout,
        ),
        base_sha=reservation.base_sha,
        run_id=run_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["process"]["classification"] == "completed" and result["native"]["outcome"] == "success" else 1


def _parse_workers(value: str) -> set[str]:
    workers = {item.strip() for item in value.split(",") if item.strip()}
    unknown = workers.difference(SUPPORTED_ADAPTERS)
    if unknown:
        raise ConfigurationError(
            "unknown worker(s): " + ", ".join(sorted(unknown)) + "; supported: "
            + ", ".join(SUPPORTED_ADAPTERS)
        )
    return workers


def _parse_assignments(values: Sequence[str], kind: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ConfigurationError(f"{kind} must use NAME=VALUE, got {value!r}")
        name, item = value.split("=", 1)
        name, item = name.strip(), item.strip()
        if not name or not item:
            raise ConfigurationError(f"{kind} must use non-empty NAME=VALUE, got {value!r}")
        if kind == "executable" and name not in SUPPORTED_ADAPTERS:
            raise ConfigurationError(f"unknown adapter {name!r} in executable override")
        if name in result:
            raise ConfigurationError(f"duplicate {kind} for {name!r}")
        result[name] = item
    return result


def _prompt_scope(default: str) -> str:
    value = input(f"OpenCode scope [global/project/custom] ({default}): ").strip()
    return value or default


def _print_setup(plan) -> None:
    prefix = "dry-run: " if plan.dry_run else ""
    print(f"{prefix}OpenCode config: {plan.opencode_path}")
    print(f"{prefix}HarnessRelay config: {plan.config_path}")
    print(f"{prefix}enabled workers: {', '.join(plan.enabled_workers) or 'none'}")
    for name, worker in plan.detected_workers.items():
        print(
            f"{prefix}detected {name}: {worker.executable} "
            f"({worker.version}, {worker.version_status}, {worker.source})"
        )
    if plan.dry_run:
        print(f"{prefix}would change: {_changes(plan)}")
    else:
        print(f"changed: {_changes(plan)}")


def _print_uninstall(plan) -> None:
    prefix = "dry-run: " if plan.dry_run else ""
    print(f"{prefix}OpenCode config: {plan.opencode_path}")
    print(f"{prefix}changes: {'yes' if plan.changed else 'no-op'}")
    for item in plan.preserved_user_edits:
        print(f"preserved: {item}")


def _changes(plan) -> str:
    names = []
    if plan.config_changed:
        names.append("relay config")
    if plan.opencode_changed:
        names.append("OpenCode integration")
    if plan.fragment_changed:
        names.append("instruction fragment")
    if plan.state_changed:
        names.append("ownership record")
    return ", ".join(names) or "none"


if __name__ == "__main__":
    raise SystemExit(main())
