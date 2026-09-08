# HarnessRelay

Native harness delegation for OpenCode. Bring your own orchestrator model, keep your native agents, and delegate bounded tasks with structured results.

**Status: PR-1 package foundation.** The repository contains a minimal installable package with `--help` and `--version`. Setup, adapters, MCP delegation, and the rest of the product remain planned work.

## One master, native workers

```text
User
  |
  v
OpenCode — the only master; user-selected model
  |
  v
HarnessRelay — local typed delegation, not another agent
  |
  +-- Codex CLI        -> native configuration and agent loop
  +-- Claude Code      -> native configuration and agent loop
  +-- AGY              -> native configuration and agent loop
  +-- additional explicitly supported local adapters
  `-- optional remote capabilities, when configured and verified
```

HarnessRelay standardizes task invocation, workspace handling, lifecycle, and results. It does not standardize away each harness's strengths.

OpenCode owns planning and delegation decisions. Users choose its model through OpenCode, without changing worker adapters. Each worker retains its native model defaults, authentication, permissions, MCPs, skills, and internal subagents. HarnessRelay does not manage provider credentials, subscription accounts, billing, or upstream proxies.

The first release has no mandatory GLM/Z.AI provider, second OpenCode worker, shared vault, retrieval server, desktop host, or Apple host. One supported local worker alongside OpenCode is enough. Universal means model/provider independence and a small adapter contract, not automatic support for every executable on PATH.

## Intended workflow

Setup detects supported installed harnesses; the user chooses which to enable and reviews a minimal OpenCode integration. The master delegates a bounded task to a named worker. Writable tasks use dedicated Git worktrees. The worker returns native output, which is normalized with validation evidence. Results and useful work are retained; merging is a separate explicit decision.

Available CLI surface:

```text
harness-relay --help
harness-relay --version
```

Planned CLI surface, **not available yet**:

```text
harness-relay setup --dry-run
harness-relay setup
harness-relay doctor
harness-relay uninstall
```

Setup must also support non-interactive configuration. Install the tested package artifact with standard Python tooling; no HarnessRelay setup subcommand is available yet.

## Boundaries

- No model API router, credential broker, automatic fallback, retries, or merges.
- No nested delegation through HarnessRelay. Native harness-internal subagents remain allowed.
- No scheduler, queue, database, dashboard, marketplace, or general workflow engine.
- No silent changes to native authentication, provider routes, or unattended permission policy.
- A worktree is not a security sandbox; actual restrictions remain with the native runtime.
- Remote desktop and Apple operations are optional follow-on integrations, not local-release prerequisites.

## Documentation

| Document | Purpose |
| --- | --- |
| [PLAN.md](PLAN.md) | Five incremental implementation PRs and completion gates. |
| [AGENTS.md](AGENTS.md) | Repository-wide implementation and review rules. |
| [Architecture](docs/ARCHITECTURE.md) | Ownership, configuration, invocation, results, and lifecycle. |
| [Acceptance](docs/ACCEPTANCE.md) | Offline tests, explicit live checks, and release criteria. |
| [Compatibility](docs/compatibility.md) | Evidence-based support matrix and upstream references. |
| [Development workflow](docs/WORKFLOW.md) | Astra orchestration/review and Luna implementation handoffs. |

Start implementation with PR-1 in the plan. Do not import private runtime state or install this project over a working environment during development.

## License and affiliation

HarnessRelay is licensed under the MIT License. The PR-1 implementation is original public code written for this repository; no private implementation source, history, runtime state, or other private material was imported.

HarnessRelay is an independent integration project. It is not presented as an official product of any supported harness or model provider.
