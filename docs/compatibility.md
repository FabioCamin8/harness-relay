# Compatibility and evidence

Status at cumulative package code candidate `04c5d43`, 2026-09-08: 78/78 source tests pass on Debian GNU/Linux 13, and its installed wheel passes 78/78 outside the checkout on CPython 3.13.5 as UID 65534 and CPython 3.9.25. Public artifact scans, archive validation, six hosted exact-head checks, and independent review pass. Maintainer review and merge remain pending. The earlier `7afa87f` artifact supplies the separately recorded live OpenCode-to-Codex repository edit with independent validation.

## Intended support

| Component | Intended role | Initial status / boundary |
| --- | --- | --- |
| OpenCode 1.18.29 | Only master; user-selected model | Live typed delegation passed with an authorized OpenRouter master. A second authorized model returned a bounded response while the worker config hash stayed unchanged. |
| Codex CLI 0.153.4 | Native local worker | Offline adapter contract and one live isolated repository edit passed. The passing writable run explicitly selected `workspace-write`; the user's inherited read-only default correctly produced no edit and failed independent validation. |
| Claude Code 2.1.104 | Native local worker | Offline adapter contract verified for `claude -p --output-format stream-json` with optional model/effort; no live task or subscription verified. |
| AGY / Antigravity 1.1.27 | Native local worker | Offline adapter contract verified for `agy -p --output-format stream-json` with optional model/effort; no live task verified. Text-only evidence would not certify repository/browser capability. |
| Gemini CLI | Additional native worker | Deferred optional adapter, not a release prerequisite. |
| Other installed CLIs | Possible future native workers | Unsupported until a named adapter and tests exist; detection alone is insufficient. |
| Remote desktop | Optional real GUI capability | Deferred, disabled by default; no specific product/host required by core. |
| Apple tooling | Optional specialized capability | Deferred, disabled by default; no Mac required by core. |
| Linux, non-root user on Debian GNU/Linux 13 | First required platform | The exact `04c5d43` wheel passes 78/78 as UID 65534 on CPython 3.13.5 and 78/78 on CPython 3.9.25 outside the checkout without `PYTHONPATH`. Live inference used the existing authorized maintainer account with the earlier `7afa87f` artifact; no auth material was copied or permission-weakened. |
| macOS / WSL / native Windows | Additional platforms | Unverified; do not claim support without platform-specific evidence. |

OpenCode's chosen model must be capable of using the exposed tools for the intended task. Model independence does not promise equal reasoning quality or tool reliability across models. HarnessRelay does not rank them or select provider accounts.

Each local worker owns its authentication and upstream routing. An existing auth file is not proof of entitlement or a live session. Do not infer billing, subscription policy compliance, quota, or runtime capability from discovery alone. Discovery labels selected executable versions `detected-unverified`; the offline PR-3 adapter contract does not promote them to live-verified.

The source-preserving JSONC editor uses the pinned Python-native `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8` pair. The JSON grammar reports trailing commas as recovery errors; HarnessRelay accepts only a comma after a complete member/value before the matching close, after masking comments/trailing commas in a strict validation copy. Other recovery/error shapes are rejected. This parser dependency is setup implementation detail, not evidence of a native worker or MCP runtime capability.

## Evidence record

When a component is tested, record: exact component version and executable identity, OS/runtime, HarnessRelay commit, supported native invocation/format, capability exercised, date, outcome, and a sanitized evidence/PR pointer. Keep detailed logs local rather than embedding them here.

Maintain separate labels for detected, enabled, config-valid, and live-verified capabilities. Unknown/new native versions may be shown as unverified; fail only when a required interface is actually unsupported or cannot be validated safely. Never automatically upgrade a user's harness.

## Primary implementation references

Consulted during planning on 2026-09-07; re-check against the version actually installed before implementation. These links are external interface references, not evidence that HarnessRelay implements them.

- [OpenCode configuration](https://opencode.ai/docs/config/): JSON/JSONC, scopes, and effective configuration.
- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/): local integration surface.
- [Codex non-interactive mode](https://developers.openai.com/codex/non-interactive-mode): native execution and structured output.
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless): native non-interactive interface.
- [Antigravity CLI headless mode](https://antigravity.google/docs/cli/headless/): native non-interactive interface, structured events, status, overrides, permissions, and timeout.
- [MCP 2025-11-25 lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle): supported alpha handshake and version negotiation.
- [Git worktrees](https://git-scm.com/docs/git-worktree): checkout ownership and shared repository state.

For future adapters, add verified primary vendor documentation and installed-help evidence when implementation begins. Do not copy unverified CLI flags or model names from a previous environment.
