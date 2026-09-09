# HarnessRelay

HarnessRelay is a native CLI-to-CLI bridge for AI coding harnesses. The calling harness remains the orchestrator.

**Status: `v0.1.0-alpha.1` release candidate under maintainer review.** The package provides strict worker configuration, reversible setup/uninstall, offline-tested native adapters, managed worktrees, MCP stdio lifecycle handling, and read-only doctor diagnostics. G14 verified one live OpenCode-to-Codex repository edit with independent validation; broader capabilities remain unverified.

## Installation prerequisites

Install the built wheel with Python 3.9 or newer. JSONC setup uses the pinned, Python-native `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8` dependencies with no external runtime or network bootstrap. Runtime result validation uses `jsonschema>=4.23`:

```text
python -m pip install harness-relay
```

## Any caller, native workers

```text
Any calling harness
  |
  v
HarnessRelay — translate, execute, isolate, return
  |
  +-- Codex CLI        -> native configuration and agent loop
  +-- Claude Code      -> native configuration and agent loop
  +-- AGY              -> native configuration and agent loop
  `-- OpenCode         -> native configuration and agent loop
```

HarnessRelay standardizes task invocation, workspace handling, lifecycle, and results. It does not standardize away each harness's strengths.

The caller owns planning, task selection, and worker choice. Any supported harness may call any configured worker, including another instance of itself. Each worker retains its native model, authentication, provider, permissions, tools, MCPs, skills, and internal subagents. HarnessRelay does not manage those settings.

Relay has no mandatory caller, model, provider, shared service, or remote host. The tested OpenCode worker invokes its installed CLI as `opencode run --format json --dir PATH [--model VALUE] -- PROMPT`. Relay does not pass `--auto`, replace the native agent, or translate the shared effort field into OpenCode's provider-specific `--variant`; unsupported overrides fail explicitly. Universal means one small native adapter contract, not automatic support for every executable on PATH.

## Intended workflow

Configure explicit workers, then let the calling harness delegate a bounded task to one named worker. Writable tasks use dedicated Git worktrees. Relay returns normalized native output and validation evidence. Results and useful work are retained; merging remains separate.

Available CLI surface:

```text
harness-relay --help
harness-relay --version
harness-relay setup --dry-run --non-interactive --relay-config PATH --scope global
harness-relay setup --non-interactive --relay-config PATH --scope project
harness-relay validate-config PATH
harness-relay list --config PATH
harness-relay doctor --json --config PATH
harness-relay delegate --worker codex --prompt "Review this repository" \
  --repository PATH --base-sha COMMIT
harness-relay uninstall --scope global
```

`setup` supports interactive and equivalent file-driven use. It writes only the user-local relay config when needed, a namespaced enabled MCP entry, a marked instruction fragment, and its ownership record. An unchanged PR-2-owned disabled entry is safely upgraded; an equivalent user-created or edited entry is not claimed. `uninstall` removes only unchanged owned content.

`list` and `doctor` use the same read-only, inference-free discovery report. `list` shows every statically supported worker plus its enabled, detected, and version status; disabled workers are marked `not-probed`. `delegate` runs one explicitly named enabled worker and prints normalized JSON. MCP always exposes the generic `delegate` operation, while `delegate_<worker>` tools remain available for enabled workers as a compatibility surface. Every delegation requires an explicit repository/base commit and reserves a distinct retained worktree; direct mode is intentionally not part of the alpha. Its typed validation argument is shell-free argv executed independently in that worktree. Status/cancel remain responsive and timeout/cancel stop the owned process group. `doctor` probes versions only for enabled workers and never calls inference. Native settings and internal subagents remain intact; HarnessRelay recursion is refused. A writable Codex task must explicitly request `sandbox: "workspace-write"` when the user's native default is read-only.

The relay config is strict JSON, versioned at `1`, and defaults every worker to disabled:

```json
{
  "version": 1,
  "workers": {
    "codex": {"enabled": true, "executable": "/usr/local/bin/codex"}
  },
  "paths": {"data": "~/.local/share/harness-relay"}
}
```

Omit `executable` to use PATH discovery. Version-1 configs may retain validated `roles` entries for compatibility, but Relay never uses them for routing. This file has no caller, model, provider, or authentication settings.

The packaged JSON Schema checks structural types, names, and allowed values. Runtime validation also enforces representation and cross-field rules. JSON Schema treats `1.0` as an integer; Relay deliberately requires the decoded version token to be an integer.

## Boundaries

- No model API router, credential broker, automatic fallback, retries, or merges.
- A Relay-spawned worker cannot invoke Relay again. Same-harness delegation and native harness-internal subagents remain allowed.
- No scheduler, queue, database, dashboard, marketplace, or general workflow engine.
- No silent changes to native authentication, provider routes, or unattended permission policy.
- A worktree is not a security sandbox; actual restrictions remain with the native runtime.
- Read-only integrity snapshots include tracked, untracked, and ignored worktree files plus `HEAD`. They hash a symlink's link text, not content outside the worktree; native sandbox enforcement remains necessary for external targets and paths.
- Remote desktop and Apple operations are optional follow-on integrations, not local-release prerequisites.

## Reversible future adoption

Keep the current installation unchanged as rollback. Install a reviewed wheel into a separate user-owned virtual environment, point a disposable OpenCode config at its `harness-relay` executable, run `setup --dry-run`, then apply and complete G14 against a fixture repository. Only after review should the maintainer switch the normal OpenCode MCP entry to the pinned environment. Roll back by restoring the previous OpenCode selection; `harness-relay uninstall` removes only unchanged owned fragments and preserves relay config, native authentication, worktrees, and results. Migration and release publication remain separate maintainer decisions.

## Documentation

| Document | Purpose |
| --- | --- |
| [PLAN.md](PLAN.md) | Realignment, worker symmetry, and bridge-surface work. |
| [AGENTS.md](AGENTS.md) | Repository-wide implementation and review rules. |
| [Architecture](docs/ARCHITECTURE.md) | Ownership, configuration, invocation, results, and lifecycle. |
| [Acceptance](docs/ACCEPTANCE.md) | Offline tests, explicit live checks, and release criteria. |
| [Compatibility](docs/compatibility.md) | Evidence-based support matrix and upstream references. |
| [Development workflow](docs/WORKFLOW.md) | Sol coordination/review, one Luna implementation writer, and escalation boundaries. |

OpenCode setup is an optional reversible caller integration. Do not install this candidate over a working environment during review.

## Caller integrations

The caller remains the orchestrator. Register the local MCP server through the caller's own documented MCP or extension mechanism, using the installed executable and separate argv values:

```text
harness-relay mcp --stdio --config PATH
```

After the MCP handshake, call `delegate` with `worker`, `prompt`, `repository`, and `base_sha`; add only explicit timeout, validation, or native options. The selected worker must be enabled, and Relay always uses a retained worktree.

- OpenCode: `setup` can add the namespaced MCP entry and marked instructions reversibly. Its local MCP integration is the only caller setup helper maintained here.
- Codex, Claude Code, and AGY: expose the same command through each harness's native MCP or extension mechanism when supported by the installed version. HarnessRelay does not write their configuration or invent caller-specific syntax; the caller-side registration is not verified by this package.

These integrations expose one generic Relay delegation operation. They do not add planning, routing, retries, fallback, or a second orchestrator.

## License and affiliation

HarnessRelay is licensed under the MIT License. The public implementation is original code written for this repository; no private implementation source, history, runtime state, or other private material was imported.

HarnessRelay is an independent integration project. It is not presented as an official product of any supported harness or model provider.
