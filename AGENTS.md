# Agent contract

Read README.md and PLAN.md first, then the relevant architecture, acceptance, compatibility, and workflow documents. This repository currently starts as documentation, not a shipped implementation. Verify the actual branch and files before relying on recorded status.

## Product invariants

OpenCode is the only master in the first release; its model is user-selected. HarnessRelay is a deterministic delegation layer with no model of its own. Workers are native harnesses, not different models run inside one common harness.

Native workers retain their own authentication, model defaults, upstream routes, permissions, MCPs, skills, and internal subagents. Do not replace them with API calls from OpenCode, centralize credentials, or change unattended permission policy. Model/effort overrides require explicit task intent and adapter support.

No mandatory GLM/Z.AI, extra OpenCode worker, retrieval MCP, vault, remote desktop, Apple host, private repository, root user, or maintainer-specific path. No personal blacklist of otherwise legitimate tools.

No hidden worker/provider fallback, automatic retry, automatic merge, nested delegation through HarnessRelay, scheduler, queue, database, dashboard, plugin marketplace, or generic workflow engine. Internal subagents belonging to the selected native harness are not prohibited nesting.

## Work boundaries

- Astra is the development coordinator/reviewer; Luna is the implementation worker. These are workflow roles, not product dependencies or hard-coded runtime model names.
- Implement one assigned PR work package at a time. Preserve unrelated dirty files and existing worktrees. Use isolated branches/worktrees for concurrent work.
- Inspect current main, assigned base/head SHAs, open PRs, and relevant checks before editing or reviewing. Never invent an unavailable tool, source, or test result.
- Do not modify the maintainer's installed harnesses, live OpenCode configuration, native auth, proxy services, remote hosts, or working deployments while building this package. Setup tests use temporary homes/configs by default.
- After the documentation bootstrap, use implementation branches and PRs. Publishing assigned branch changes is allowed; merging, tagging, releases, and live deployment require explicit maintainer authorization. Never force-push or rewrite shared history to resolve a conflict.
- Do not import private history or runtime state into this public repository. Resolve license/provenance before the corresponding public source import. Retain necessary third-party notices.

## Engineering standards

Prefer small functions, a static adapter registry, one configuration format, one result contract, and a few justified dependencies. Do not hand-roll a fragile protocol or JSONC rewriter merely to avoid a dependency. Do not create abstractions without a current requirement.

Validate all public inputs, config types, paths, executable selections, identifiers, and native output. Use argv-based process invocation; do not turn task text into a shell command. Advertise only supported protocol and adapter capabilities. Keep MCP stdout free of logs.

Distinguish process exit, native completion, executed validation, and acceptance. A worker saying it succeeded is not independent acceptance. Record omitted tests as not run, not passed. A tool-free smoke does not prove repository access, browser use, or desktop control.

Protect existing files, dirty changes, unmerged commits, and run evidence. A worktree is not a security sandbox. Do not claim read-only protection based only on Git status or prompt instructions. State what the native harness enforces and what the runner merely detects.

Verify current native flags/formats against the installed CLI and primary upstream documentation. Record tested versions and dates in docs/compatibility.md. Do not guess aliases, model availability, prices, subscription entitlements, or auth validity.

Use offline tests with fake CLIs and disposable repositories for normal CI. Live inference tests require available authorized accounts, bounded tasks, and explicit evidence. No credentials in CI, reports, examples, fixtures, commits, or command output.

## Evidence and handoff

For each PR provide the work-package ID, base and candidate SHA, changed files, relevant acceptance gate IDs, exact test commands/results, not-run checks, source/provenance notes, and unresolved issues. Review the entire diff, not only the implementation summary.

Astra issues a verdict against a specific candidate SHA: PASS, CHANGES_REQUIRED, or BLOCKED. Separate code defects from environmental/optional gaps. A new commit requires review of the delta; approval does not silently transfer to an unreviewed head.

The current assignment ends after its PR and handoff. Do not advance to the next work package or add features without the coordinator's next explicit packet. Keep documentation concise and update only claims supported by evidence.
