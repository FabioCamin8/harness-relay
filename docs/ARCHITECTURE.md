# Architecture

This document defines the universal bridge boundary. PLAN.md separates implemented behavior from planned work.

## Ownership

| Concern | Owner |
| --- | --- |
| User interaction, planning, worker choice | Calling harness |
| Provider accounts, billing, native model defaults | Each harness's existing configuration |
| Worker reasoning, edits, native tools and subagents | Selected native harness |
| Typed task input, process capture, workspace records, normalized results | HarnessRelay |
| Accepting changes, merging, deployment | User or separately authorized workflow |
| Browser profiles and remote graphical state | Optional desktop host, never the local router |

HarnessRelay has no reasoning model, model catalog, provider API, authentication broker, scoring engine, or caller registry. The caller deliberately chooses a named enabled worker. A failed task is not permission to switch worker, model, provider, or account.

## Configuration and setup

Keep one versioned JSON file for enabled workers, executable paths, and local storage. Version-1 `roles` entries remain accepted for compatibility but have no routing behavior. The packaged schema owns structural validation; runtime validation adds representation and cross-field rules.

Do not copy caller or worker model/provider state into this file. Task-level native overrides are optional, explicit, and adapter-validated.

The optional OpenCode helper owns only its namespaced MCP entry and marked instruction fragment. It preserves unrelated JSON/JSONC and newer user edits and uses atomic ownership records rather than whole-file restoration. Other callers may expose the same MCP server without entering Relay core configuration.

OpenCode JSONC edits use the pinned Python-native `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8` pair. Tree-sitter supplies source ranges and comments; this bounded module masks only recognized trailing commas for strict validation and rejects all other parser recovery. No external runtime, network bootstrap, or user-level parser cache is needed.

Official OpenCode documentation describes JSON/JSONC and layered merged configuration; verify the tested version before selecting an integration mechanism: [configuration](https://opencode.ai/docs/config/) and [MCP servers](https://opencode.ai/docs/mcp-servers/).

## Task boundary

A task identifies a supported enabled worker, prompt, source repository, exact starting revision, requested validation, native options, and timeout. MCP and direct CLI delegation reserve a retained managed worktree from that revision.

The adapter constructs native argv from validated inputs; task text is data, not shell syntax. Honor supported native headless interfaces and existing authentication. Unexpected interactive/auth requirements produce blocked evidence rather than a login flow or permission escalation.

Current workers are Codex, Claude Code, AGY, and OpenCode. OpenCode uses its native `run --format json` command. A worker always means its native process, never a provider API or another harness used as a proxy.

## Workspace ownership

Reserve each run atomically with validated identifiers and a repository identity that cannot collide merely because two repositories share a basename. Resolve paths inside managed roots and reject escapes/symlink redirection before writes or cleanup.

Writable tasks start in a newly owned worktree from a captured commit. Never silently discard, copy, stash, reset, or clean a user's dirty source checkout. A task that needs uncommitted input must receive an explicit agreed snapshot/commit boundary; otherwise describe that input as absent.

Collect both committed diff from the base and staged/unstaged/untracked changes. Capture final evidence after requested validation. Preserve incomplete work and diagnostics. Cleanup is explicit and refuses foreign paths, live writers, dirty work, unmerged results, and a clean worktree whose `HEAD` moved from the reserved base.

The read-only integrity snapshot includes `HEAD` and content hashes for tracked, untracked, and ignored files. A repository symlink is represented by its link text; target content outside the worktree is outside the declared snapshot boundary. This post-hoc check does not replace a native read-only sandbox and cannot police writes through arbitrary external paths.

Read-only is a native execution intent plus evidence, not an unconditional security guarantee. Do not rely on a porcelain status string alone: an already-dirty file can change without changing its status label, and a commit can leave a clean status. Define and test the content/revision boundary checked, including its limitations. Never restore a user's files to conceal a violation.

Git linked worktrees share repository state; they are not a sandbox. See [git-worktree](https://git-scm.com/docs/git-worktree). Host filesystem/network restrictions remain the user's native runtime policy.

## Execution and results

Keep a single versioned outer result contract. It should identify task/run, worker and relevant native version, terminal outcome, process exit/error classification, concise summary, workspace/base/result revisions, changed files, artifacts, validation evidence, unresolved items, and a suggested next action.

Separate native execution from acceptance. An exit code zero and a worker-written summary do not prove the objective or tests passed. Acceptance is explicitly passed, failed, or not checked; evidence distinguishes runner-executed validation from worker-reported claims. Non-applicable Git fields remain explicit for future non-repository capabilities.

Parse each harness's documented structured output where available. Do not classify failure by English substrings. Return bounded summaries and artifact references to the caller.

The schema and implementation validator must agree; validate nested types, not only top-level presence. A future breaking contract change requires a version change and documented compatibility, not silently reinterpreting old runs.

## MCP and lifecycle

The alpha server uses newline-delimited JSON-RPC stdio and MCP `2025-11-25` only. It returns the supported version rather than echoing an unsupported client request. Logs cannot share protocol stdout. It exposes one generic `delegate` tool that requires an explicit worker, plus `delegate_<worker>` compatibility tools for enabled adapters; runtime validation rejects missing, unknown, and disabled workers before scheduling. No tool chooses a worker or falls back to another one.

Every alpha delegation reserves a managed worktree from the requested repository and base revision. There is no direct `isolate=false` mode: keeping isolation mandatory preserves the source checkout and keeps the public contract small while direct-mode safety is not independently justified.

Use the tested OpenCode client's deadlines and supported cancellation behavior. Long work must not make cancellation/status permanently inaccessible or leave unmanaged child processes after client disconnect. Prefer a small bounded subprocess implementation; this does not authorize a queue, scheduler, database, or separate persistent service. Report cancellation/timeout and any unconfirmed remote termination honestly.

The current Python MCP SDK requires Python 3.10 or newer while HarnessRelay supports Python 3.9. The alpha therefore implements only this bounded stdio lifecycle, without HTTP/auth transports or an SDK dependency. Later protocol support requires separate compatibility evidence.

## Recursion boundary

The runner marks every Relay-spawned process with an execution-role environment value. Relay entry points reject that value. The check does not inspect harness names, so Codex-to-Codex and OpenCode-to-OpenCode are valid while worker-to-Relay recursion is refused. This is a cooperative boundary, not protection against a malicious privileged process.

Native harness-internal tools and subagents remain governed by native policy. The caller need not route its own work through Relay; a delegated task has one selected worker and an explicit workspace boundary.

## Caller integration

Any caller that supports local MCP or an equivalent native extension can launch `harness-relay mcp --stdio --config PATH` and call `delegate` with an explicit worker. OpenCode has the maintained optional `setup`/`uninstall` helper. Codex, Claude Code, and AGY retain ownership of their caller configuration; this repository provides the common process command and operation contract, not unverified caller-specific configuration files or orchestration helpers.

## Optional remote capabilities

Desktop and Apple support are follow-on integrations, disabled until configured. Reuse an existing authorized remote entry point with a typed task interface; do not introduce a general SSH shell tool. Remote profiles, sessions, credentials, and unrelated GUI state remain remote.

A persistent desktop session permits one delegated interaction at a time and returns busy rather than building a queue. Verify desktop actions with harmless non-sensitive evidence. Status probes must not launch applications, capture screens, or invoke model inference. An unavailable optional host must not invalidate healthy local coding workers.
