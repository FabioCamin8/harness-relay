# HarnessRelay

Native harness delegation for OpenCode. Bring your own orchestrator model, keep your native agents, and delegate bounded tasks with structured results.

**Status: PR-2 configuration/setup candidate.** The package provides strict worker configuration, enabled-only executable discovery, and reversible OpenCode setup/uninstall. Native task adapters, MCP runtime delegation, worktrees, lifecycle, and doctor remain later work. The setup-created MCP entry is disabled until PR-4 supplies and verifies the runtime.

## Installation prerequisites

Install the built wheel with Python 3.9 or newer. JSONC setup uses the pinned, Python-native `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8` dependencies with no external runtime or network bootstrap. The test extra adds `jsonschema` for schema checks:

```text
python -m pip install 'harness-relay[test]'
```

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

Setup validates explicitly selected supported harnesses; the user chooses which to enable and reviews a minimal OpenCode integration. The master delegates a bounded task to a named worker. Writable tasks use dedicated Git worktrees. The worker returns native output, which is normalized with validation evidence. Results and useful work are retained; merging is a separate explicit decision.

Available CLI surface:

```text
harness-relay --help
harness-relay --version
harness-relay setup --dry-run --non-interactive --relay-config PATH --scope global
harness-relay setup --non-interactive --relay-config PATH --scope project
harness-relay validate-config PATH
harness-relay uninstall --scope global
```

`setup` supports an interactive worker/scope selection and equivalent file-driven non-interactive use. It writes only the user-local relay config when needed, a namespaced OpenCode MCP entry (currently `enabled: false` pending PR-4), a marked instruction fragment, and its ownership record. `--dry-run` performs validation and previews changes without writing. `uninstall` removes only unchanged owned integration content. `doctor`, native delegation, and live worker execution are later work.

The relay config is strict JSON, versioned at `1`, and defaults every worker to disabled:

```json
{
  "version": 1,
  "workers": {
    "codex": {"enabled": true, "executable": "/usr/local/bin/codex"}
  },
  "roles": {"implementer": "codex"},
  "paths": {"data": "~/.local/share/harness-relay"}
}
```

Omit `executable` to use PATH discovery. A role must reference an enabled `codex`, `claude`, or `agy` worker. This file has no model, provider, or authentication settings; those remain owned by OpenCode and each native worker.

The packaged JSON Schema checks structural types, names, and allowed values. Runtime validation additionally enforces cross-field rules such as a role referring to an enabled worker; JSON Schema alone intentionally accepts that structurally valid but semantically invalid intermediate document.

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
| [Development workflow](docs/WORKFLOW.md) | Sol coordination/review, one Luna implementation writer, and escalation boundaries. |

PR-1 is the merged public foundation; PR-2 is the current configuration/setup candidate. Do not import private runtime state or install this project over a working environment during development.

## License and affiliation

HarnessRelay is licensed under the MIT License. The public implementation is original code written for this repository; no private implementation source, history, runtime state, or other private material was imported.

HarnessRelay is an independent integration project. It is not presented as an official product of any supported harness or model provider.
