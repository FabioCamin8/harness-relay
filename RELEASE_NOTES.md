# v0.1.0-alpha.1 candidate

This candidate provides a universal native harness bridge with optional reversible OpenCode setup, strict local worker configuration, static Codex/Claude Code/AGY/OpenCode adapters, normalized result evidence, managed worktrees, MCP `2025-11-25` stdio, bounded lifecycle handling, execution-role recursion refusal, and inference-free diagnostics.

It is an alpha candidate, not a published release. Native worker accounts and models remain user-managed. G14 passed for one live OpenCode 1.18.29 to Codex CLI 0.153.4 isolated repository edit with independently executed validation and an explicit `workspace-write` override. This does not certify Claude, AGY, browser, desktop, Apple, or cross-platform capability. Hosted CI passes at package code candidate `04c5d43`; maintainer review, merge, tag, publication, and migration remain pending.

The calling harness remains the orchestrator. No mandatory master, caller registry, queue, scheduler, database, provider router, authentication broker, automatic fallback, merge, deployment, or self-update is included. Same-harness delegation is valid, including OpenCode-to-OpenCode. The OpenCode worker uses only the native CLI and preserves native model, authentication, provider, tools, MCP, skills, permissions, and internal-agent behavior; live OpenCode worker inference remains unverified.

PR-8 adds the caller-neutral `delegate` MCP operation, `harness-relay list`, and concise native MCP registration guidance. Generic delegation requires an explicit enabled worker and always uses a retained managed worktree in alpha; compatibility `delegate_<worker>` tools remain. Caller-specific registration for Codex, Claude Code, and AGY is not claimed without installed-version evidence.
