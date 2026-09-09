# Implementation plan

Baseline: 2026-09-09. PR-1 through PR-5 are merged at `8d54d4b`. Their cumulative 78-test source and installed-wheel evidence remains recorded in Acceptance. PR-6 through PR-8 realign the contract, complete worker symmetry, and expose the minimum universal bridge surface.

## Product contract

HarnessRelay is a native CLI-to-CLI bridge for AI coding harnesses. The calling harness remains the orchestrator. It selects one configured worker; Relay translates, executes, optionally isolates, and returns evidence.

Any supported harness may call any configured worker, including another instance of itself. Each worker owns its native model, authentication, provider, tools, skills, permissions, MCPs, and internal subagents. A Relay-spawned worker cannot invoke Relay again. No automatic routing, fallback, or retry exists.

## Scope

The first public target is `v0.1.0-alpha.1`, not an assertion that a release already exists. Build the portable local core first: setup, configuration, native adapters, typed MCP delegation, lifecycle, worktrees, normalized results, and doctor.

Linux under a normal non-root user is the initial required platform. Other platforms and harness versions are supported only to the extent recorded in the compatibility matrix. Codex is the first adapter used to prove the path; this is implementation order, not a mandatory user subscription or a ranking of model quality. Claude Code and AGY follow the same contract and remain experimental until verified. Gemini CLI is an optional later adapter, not a first-release requirement.

Remote desktop and Apple capabilities are optional follow-on work. Preserve their design boundary but do not build generic remote infrastructure, require a particular host, or block the local core release on their availability.

## Execution model

PR-1 through PR-5 built and validated the alpha foundation. PR-6 through PR-8 are small sequential work packages. Each records base, candidate, scope, evidence, and omissions. Sol leads and reviews; one Luna XHigh worker implements substantial changes at a time. Read [the workflow](docs/WORKFLOW.md).

The documentation bootstrap may exist on main. Subsequent implementation uses branches and PRs. No automatic merging, release tagging, deployment, or edits to the maintainer's working installation are authorized by this plan alone.

### PR-1 — Portable source and public-safe foundation

Goal: establish one clean codebase with no personal infrastructure requirements.

Work:

- Inspect the current repository before starting. Reuse a maintainer-provided reference implementation only when accessible and authorized; otherwise identify the exact gap rather than claiming to have inspected it.
- Export selected, reviewed source files. Do not copy private Git history, credentials, browser profiles, logs, run outputs, backup archives, internal host details, or private knowledge repositories. Record permitted provenance without disclosing private data; preserve required notices.
- Resolve the proposed MIT license and source-reuse permissions with the maintainer before public source import as required by README. Do not invent a license grant or misrepresent a public repository as a licensed release.
- Package Python with minimal justified dependencies. Prefer a supported MCP SDK or proven parser where hand-rolled protocol/JSONC code would increase maintenance risk. Do not require zero dependencies at the expense of correctness.
- Replace personal paths with user-owned configurable config/data/worktree locations. Separate installed source from runtime data. Package schemas as resources rather than finding them in one developer's checkout.
- Remove required model/provider names, GLM-specific worker identity, default remote hosts, private-vault imports, and personal forbidden-tool policies.
- Keep orchestration outside Relay. There is no caller registry, model catalog, or provider-auth subsystem.
- Add a minimal offline test entry point and clean installation test. Do not install into the maintainer's live environment.

Acceptance: G01 and G02 in [Acceptance](docs/ACCEPTANCE.md). A built artifact installs under a temporary non-root home, imports, and exposes only the supported `--help` and `--version` commands without a personal environment. Adapter selection and configuration are later-phase work and are outside PR-1.

### PR-2 — Minimal, reversible setup

Goal: enable the user's chosen local workers without taking over existing configuration.

Work:

- Detect supported executables using explicit paths or PATH. Report missing/unsupported versions; do not silently install, upgrade, authenticate, or enable them.
- Offer optional reversible OpenCode setup for enabled workers and user-owned storage paths. Do not alter OpenCode model/provider state.
- Support `setup --dry-run`, interactive setup, and equivalent file-driven non-interactive setup. Keep our configuration in one versioned JSON format with strict types and actionable errors.
- Manage only a namespaced MCP entry and a short, marked instruction block. Inspect effective configuration and respect JSON/JSONC, precedence, managed policy, and user changes.
- The setup-created MCP entry remains disabled until PR-4 implements and verifies the MCP runtime. JSONC editing uses the pinned Python Tree-sitter parser pair and has no external runtime prerequisite.
- Make writes atomic and reversible. Record ownership sufficient for a second setup to be a no-op. A conflict is a reported conflict, not permission to overwrite unrelated data.
- Uninstall removes only unchanged managed integration fragments. Preserve later user edits, credentials, native harnesses, worktrees, and task artifacts. Never restore an entire old config over newer user changes.
- Default to no enabled workers until the user selects them. Disabled components must not be probed or advertised as runnable.

Acceptance: G03 and G04. Repeated setup produces no duplicates; interrupted setup leaves recoverable state; uninstall preserves unrelated configuration and comments.

### PR-3 — Native adapters and trustworthy results

Goal: bounded native execution, not model emulation inside OpenCode.

Work:

- Implement a small static adapter registry: detect, probe, construct argv, execute, parse native output, normalize evidence. Add adapters explicitly, not via a dynamic plugin marketplace.
- Inherit native model/auth/provider configuration. Permit task-level model/effort overrides only when explicitly requested and supported by the selected adapter. Reject unsupported overrides rather than dropping them silently.
- Start with one native adapter; bring candidate Claude Code/AGY adapters under the same tests. Confirm installed help and primary upstream documentation for every claimed flag and output format.
- Keep task inputs concise: objective, named worker, workspace/base revision when relevant, constraints, acceptance criteria, requested validation, and timeout. Workers discover their own repository context.
- Separate process completion, native task outcome, validation evidence, and acceptance. Use native structured events where available. Never decide success by searching for English phrases in a summary.
- Report empty/malformed output, tool denial, auth requirements, cancellation, and timeout explicitly. Do not silently change provider, retry, authenticate, or widen permissions.
- Record both committed changes relative to the captured base and staged/unstaged/untracked changes. Include changes caused by validation; do not confuse a clean checkout after a commit with no changes.
- Keep one versioned result contract. Unknown or unverified fields remain explicit; a worker's own claim is not independent acceptance.

Acceptance: G05 through G08. Fake native CLIs cover failure and success paths without subscriptions. Real-worker support claims require separate dated evidence.

### PR-4 — MCP, workspace boundaries, lifecycle, and doctor

Goal: expose only usable bounded operations and preserve work under failure.

Work:

- Publish typed delegation tools only for configured enabled adapters, plus minimal status/worktree inspection. Validate tool arguments at runtime as well as in declared schemas.
- Use a real supported MCP lifecycle. Do not blindly echo an unsupported protocol version. Keep stdout protocol-clean; diagnostics go to stderr/files. Verify client tool deadlines and cancellation using the tested OpenCode version.
- A long worker must not make cancellation or status handling permanently inaccessible. Prefer bounded native subprocess handling over a service, queue, or durable scheduler. Stop/timeout owned process groups, retain evidence, and report any remote uncertainty honestly.
- Use validated task/run identifiers, paths confined to managed roots, atomic reservation, and a collision-resistant repository identity. No overwrite of existing runs or concurrent writers in one checkout.
- Capture an explicit base commit before creating a writable worktree. Do not silently carry dirty source changes into a new task; require an explicit snapshot/commit choice when that matters.
- Preserve dirty, failed, or unmerged work. Cleanup is explicit, ownership-checked, and refuses unsafe deletions. A read-only check must not rely solely on changed path names or a clean Git status.
- Block worker re-entry through HarnessRelay and avoid exposing its delegation tools in worker contexts. Keep harness-internal subagents intact. Document that this is a delegation boundary, not a hostile-code sandbox.
- Doctor is read-only by default and does not call model inference. Distinguish detected, enabled, config-valid, last-live-verified, and capability-specific evidence. Disabled and optional-unavailable states are intentional, not unrelated failures.
- Remove personal tool blacklists and compulsory retrieval integrations. Flag demonstrated incompatibilities, not the maintainer's preferences.

Acceptance: G09 through G13. Timeout/cancel, concurrency, dirty-state preservation, recursion refusal, and MCP error cases pass offline tests. Required enabled workers failing configuration are actionable failures; unsupported/disabled optional capabilities are represented accurately.

### PR-5 — Public alpha, documentation, and controlled adoption

Goal: ship an honestly scoped package, then adopt it as one maintained codebase.

Work:

- Complete README with only implemented install/setup/delegate/doctor/uninstall commands. Document ownership, failure recovery, native auth boundary, support evidence, and worktrees-versus-sandbox limitations.
- Add concise license/notices, contribution guidance, compatibility matrix, generic examples, and release notes. Verify package entry points and bundled resources from an installed artifact, not only the source tree.
- Run CI with fake executables, temporary homes/repositories, schema checks, package checks, and public-data/secret scans. No account credentials or paid inference in ordinary CI.
- Run explicit low-quota live acceptance only for available authorized workers. Report absent access as not verified; do not purchase access or make authentication workarounds.
- Prove the independent-user OpenCode-caller scenario in G14. A test with no tool use is not repository/browser/desktop capability evidence.
- Prepare the `v0.1.0-alpha.1` release candidate. Publish/tag only with separate maintainer authorization. Do not move or reuse an existing release tag.
- Propose migration of the maintainer's setup to a pinned public-project release, keeping the existing installation as rollback. No parallel long-lived fork; no automatic live migration in this work package.

Acceptance: required gates pass at the exact candidate SHA, compatibility claims match evidence, license/provenance is resolved, and there are no hidden public/runtime-data leaks. Optional worker/platform limitations remain explicit and cannot be described as passed.

## Progress ledger

Update this table only with actual PR/commit evidence. PR bodies hold detailed test output; do not turn this document into a session transcript.

| Package | State | PR / reviewed candidate |
| --- | --- | --- |
| PR-1 | Reviewed PASS | [#1](https://github.com/FabioCamin8/harness-relay/pull/1) |
| PR-2 | Reviewed G03/G04 PASS at `8849e04`; evidence-only delta reviewed | [#2](https://github.com/FabioCamin8/harness-relay/pull/2) |
| PR-3 | Reviewed G05-G08 PASS; maintainer review pending | [#3](https://github.com/FabioCamin8/harness-relay/pull/3) |
| PR-4 | Cumulative G09-G13 review PASS through `04c5d43`; remediations follow the standalone PR-4 head in PR-5; maintainer review pending | [#4](https://github.com/FabioCamin8/harness-relay/pull/4), [#5](https://github.com/FabioCamin8/harness-relay/pull/5) |
| PR-5 | Reviewed PASS at `04c5d43`; 78/78 source and both installed-wheel lanes plus hosted exact-head CI pass; maintainer review pending | [#5](https://github.com/FabioCamin8/harness-relay/pull/5) |

## Stop rules and deferred work

Sol can request a narrowly justified amendment when implementation evidence contradicts an assumption. Escalate only difficult blockers or high-risk decisions to Astra Medium. Record the decision and affected acceptance gate; do not silently expand scope.

No automatic fallback/merge/retry, provider proxy, central secrets store, model ranking, token/cost optimizer, scheduler, queue, database, dashboard, shared-memory service, global skill synchronization, or self-updating harness installer.

Remote desktop, Apple tooling, additional caller helpers, Gemini and other new adapters, and broader platforms require separate evidence-driven follow-ups. Do not block the local core on optional infrastructure.

## PR-6 through PR-8

### PR-6 — Realign and simplify

Replace the mandatory-OpenCode architecture with the universal bridge contract. Keep OpenCode setup as an optional helper. Preserve version-1 `roles` parsing for compatibility but do not use or promote it as routing. Add regression proof for same-harness delegation and execution-role recursion refusal.

### PR-7 — Complete worker symmetry

Add OpenCode as a native worker through its verified non-interactive CLI. Use the existing adapter contract, fake-CLI tests, explicit version/override failure, and no fallback. Do not call a provider API or another harness as proxy.

### PR-8 — Universal bridge surface

Prefer one generic `delegate` operation across CLI and MCP while retaining adapter-specific compatibility tools if removal adds churn. Add `list`; keep `doctor`, `delegate`, and `mcp`. Keep managed-worktree isolation mandatory for alpha if direct mode weakens source preservation. Document minimal caller integrations without building orchestrators.
