# Architecture

Design target, not an implementation claim. PLAN.md determines scope and order; this document defines boundaries shared by the five PRs.

## Ownership

| Concern | Owner |
| --- | --- |
| User interaction, planning, worker choice | OpenCode master and its user-selected model |
| Provider accounts, billing, native model defaults | Each harness's existing configuration |
| Worker reasoning, edits, native tools and subagents | Selected native harness |
| Typed task input, process capture, workspace records, normalized results | HarnessRelay |
| Accepting changes, merging, deployment | User or separately authorized workflow |
| Browser profiles and remote graphical state | Optional desktop host, never the local router |

HarnessRelay has no reasoning model, model catalog, provider API, authentication broker, or scoring engine. Configuration may express user preferences such as a preferred review worker. The master remains responsible for deliberately choosing a named enabled worker. A failed task is not permission to switch provider or account.

## Configuration and setup

Keep one versioned JSON file for HarnessRelay. Suggested concerns are enabled adapter names, executable paths, optional role preferences, and local storage locations. The exact schema is implemented in PR-2; do not add speculative settings. The packaged JSON Schema owns standard structural validation, while the runtime validator adds representation and cross-field rules. In particular, JSON Schema treats the numeric token `1.0` as an integer; HarnessRelay requires the decoded version to be an integer value. Both layers are required, and schema validity alone is not configuration validity.

Do not copy OpenCode's master model into this file. Retain the user's existing model selection and provider configuration. Worker model defaults also remain native. Task-level overrides are optional, explicit, and validated by the adapter.

Setup owns only its namespaced OpenCode MCP entry and marked instruction fragment. PR-4 enables the entry and upgrades the old disabled value only when the PR-2 ownership record and exact source hash agree. Equivalent user-created or edited entries remain conflicts. Setup preserves unrelated JSON/JSONC and newer user edits and uses atomic ownership records rather than whole-file restoration.

OpenCode JSONC edits use the pinned Python-native `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8` pair. Tree-sitter supplies source ranges and comments; this bounded module masks only recognized trailing commas for strict validation and rejects all other parser recovery. No external runtime, network bootstrap, or user-level parser cache is needed.

Official OpenCode documentation describes JSON/JSONC and layered merged configuration; verify the tested version before selecting an integration mechanism: [configuration](https://opencode.ai/docs/config/) and [MCP servers](https://opencode.ai/docs/mcp-servers/).

## Task boundary

A coding task identifies a supported enabled worker, objective, repository/worktree when applicable, exact starting revision when known, edit intent, constraints, acceptance criteria, evidence pointers, requested validation, and timeout. Use paths and short evidence summaries instead of copying an entire repository through the master.

The adapter constructs native argv from validated inputs; task text is data, not shell syntax. Honor supported native headless interfaces and existing authentication. Unexpected interactive/auth requirements produce blocked evidence rather than a login flow or permission escalation.

Initial local worker adapters are Codex, Claude Code, and AGY, with separate evidence levels. Do not add a second OpenCode agent merely to host another model. Later native adapters use the same small static interface; arbitrary executable discovery alone does not make an adapter supported.

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

Parse each harness's documented structured output where available. Do not classify failure by English substrings. Empty/malformed output, tool refusal, missing auth, unsupported options, cancellation, and timeout need machine-readable distinctions. Retain raw output locally for diagnosis, but return only bounded summaries and artifact references to the master.

The schema and implementation validator must agree; validate nested types, not only top-level presence. A future breaking contract change requires a version change and documented compatibility, not silently reinterpreting old runs.

## MCP and lifecycle

The alpha server uses newline-delimited JSON-RPC stdio and MCP `2025-11-25` only. It returns the supported version rather than echoing an unsupported client request. Logs cannot share protocol stdout. Typed tools expose only enabled adapters and runtime validation enforces their declared schemas.

Use the tested OpenCode client's deadlines and supported cancellation behavior. Long work must not make cancellation/status permanently inaccessible or leave unmanaged child processes after client disconnect. Prefer a small bounded subprocess implementation; this does not authorize a queue, scheduler, database, or separate persistent service. Report cancellation/timeout and any unconfirmed remote termination honestly.

The current Python MCP SDK requires Python 3.10 or newer while HarnessRelay supports Python 3.9. The alpha therefore implements only this bounded stdio lifecycle, without HTTP/auth transports or an SDK dependency. Later protocol support requires separate compatibility evidence.

## No second master

Workers must not invoke HarnessRelay to delegate onward. Avoid exposing delegation tools in worker contexts and implement a runner re-entry check. Test inherited configuration as well as prompt instructions. This is a cooperative architecture boundary, not protection against a fully privileged malicious process.

Native harness-internal tools/subagents remain enabled according to native user policy. Do not confuse those with cross-harness recursion. The master need not route every shell command through HarnessRelay; a delegated task, however, has one selected primary worker and an explicit workspace boundary.

## Optional remote capabilities

Desktop and Apple support are follow-on integrations, disabled until configured. Reuse an existing authorized remote entry point with a typed task interface; do not introduce a general SSH shell tool. Remote profiles, sessions, credentials, and unrelated GUI state remain remote.

A persistent desktop session permits one delegated interaction at a time and returns busy rather than building a queue. Verify desktop actions with harmless non-sensitive evidence. Status probes must not launch applications, capture screens, or invoke model inference. An unavailable optional host must not invalidate healthy local coding workers.
