# HarnessRelay

Native harness delegation for OpenCode. Bring your own orchestrator model, keep your native agents, and delegate bounded tasks with structured results.

**Status: `v0.1.0-alpha.1` release candidate under maintainer review.** The package provides strict worker configuration, reversible setup/uninstall, offline-tested native adapters, managed worktrees, MCP stdio lifecycle handling, and read-only doctor diagnostics. G14 verified one live OpenCode-to-Codex repository edit with independent validation; broader capabilities remain unverified.

## Installation prerequisites

Install the built wheel with Python 3.9 or newer. JSONC setup uses the pinned, Python-native `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8` dependencies with no external runtime or network bootstrap. Runtime result validation uses `jsonschema>=4.23`:

```text
python -m pip install harness-relay
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
harness-relay doctor --json --config PATH
harness-relay delegate --worker codex --prompt "Review this repository" \
  --repository PATH --base-sha COMMIT
harness-relay uninstall --scope global
```

`setup` supports interactive and equivalent file-driven use. It writes only the user-local relay config when needed, a namespaced enabled MCP entry, a marked instruction fragment, and its ownership record. An unchanged PR-2-owned disabled entry is safely upgraded; an equivalent user-created or edited entry is not claimed. `uninstall` removes only unchanged owned content.

`delegate` runs one enabled worker directly and prints normalized JSON. MCP exposes enabled workers only and requires an explicit repository/base commit, then reserves a distinct retained worktree. Its typed validation argument is shell-free argv executed independently in that worktree. Status/cancel remain responsive and timeout/cancel stop the owned process group. `doctor` probes versions only for enabled workers and never calls inference. Native settings and internal subagents remain intact; HarnessRelay recursion is refused. A writable Codex task must explicitly request `sandbox: "workspace-write"` when the user's native default is read-only.

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

The packaged JSON Schema checks structural types, names, and allowed values. Runtime validation additionally enforces representation and cross-field rules, such as requiring the version token to decode as an integer and a role to refer to an enabled worker. JSON Schema's standard numeric model treats `1.0` as an integer; HarnessRelay's runtime deliberately rejects that representation.

## Boundaries

- No model API router, credential broker, automatic fallback, retries, or merges.
- No nested delegation through HarnessRelay. Native harness-internal subagents remain allowed.
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
| [PLAN.md](PLAN.md) | Five incremental implementation PRs and completion gates. |
| [AGENTS.md](AGENTS.md) | Repository-wide implementation and review rules. |
| [Architecture](docs/ARCHITECTURE.md) | Ownership, configuration, invocation, results, and lifecycle. |
| [Acceptance](docs/ACCEPTANCE.md) | Offline tests, explicit live checks, and release criteria. |
| [Compatibility](docs/compatibility.md) | Evidence-based support matrix and upstream references. |
| [Development workflow](docs/WORKFLOW.md) | Sol coordination/review, one Luna implementation writer, and escalation boundaries. |

PRs #2 through #5 are stacked review slices; none is automatically merged or published. Do not import private runtime state or install this candidate over a working environment during review.

## License and affiliation

HarnessRelay is licensed under the MIT License. The public implementation is original code written for this repository; no private implementation source, history, runtime state, or other private material was imported.

HarnessRelay is an independent integration project. It is not presented as an official product of any supported harness or model provider.
