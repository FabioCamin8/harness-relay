# Compatibility and evidence

Status at PR-1 candidate review, 2026-09-08: **the package foundation has been verified on Debian GNU/Linux 13 with Python 3.13.5 under a non-root UID; no HarnessRelay adapter or protocol version has been verified yet**. This matrix is still a plan for later capabilities, not a compatibility claim inherited from a private reference implementation.

## Intended support

| Component | Intended role | Initial status / boundary |
| --- | --- | --- |
| OpenCode | Only master; user-selected model | Planned. Preserve effective native model/provider configuration. |
| Codex CLI | Native local worker | First adapter to exercise; no verified HarnessRelay version yet. |
| Claude Code | Native local worker | Candidate adapter; experimental until its task/tool path is tested. |
| AGY / Antigravity | Native local worker | Candidate adapter; confirm executable identity and actual flags locally. Text-only smoke cannot certify repository/browser capability. |
| Gemini CLI | Additional native worker | Deferred optional adapter, not a release prerequisite. |
| Other installed CLIs | Possible future native workers | Unsupported until a named adapter and tests exist; detection alone is insufficient. |
| Remote desktop | Optional real GUI capability | Deferred, disabled by default; no specific product/host required by core. |
| Apple tooling | Optional specialized capability | Deferred, disabled by default; no Mac required by core. |
| Linux, non-root user | First required platform | PR-1 package foundation verified on Debian GNU/Linux 13 with Python 3.13.5 and UID 1000; later product capabilities remain unverified. |
| macOS / WSL / native Windows | Additional platforms | Unverified; do not claim support without platform-specific evidence. |

OpenCode's chosen model must be capable of using the exposed tools for the intended task. Model independence does not promise equal reasoning quality or tool reliability across models. HarnessRelay does not rank them or select provider accounts.

Each local worker owns its authentication and upstream routing. An existing auth file is not proof of entitlement or a live session. Do not infer billing, subscription policy compliance, quota, or runtime capability from discovery alone.

## Evidence record

When a component is tested, record: exact component version and executable identity, OS/runtime, HarnessRelay commit, supported native invocation/format, capability exercised, date, outcome, and a sanitized evidence/PR pointer. Keep detailed logs local rather than embedding them here.

Maintain separate labels for detected, enabled, config-valid, and live-verified capabilities. Unknown/new native versions may be shown as unverified; fail only when a required interface is actually unsupported or cannot be validated safely. Never automatically upgrade a user's harness.

## Primary implementation references

Consulted during planning on 2026-09-07; re-check against the version actually installed before implementation. These links are external interface references, not evidence that HarnessRelay implements them.

- [OpenCode configuration](https://opencode.ai/docs/config/): JSON/JSONC, scopes, and effective configuration.
- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/): local integration surface.
- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive): native execution and structured output.
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless): native non-interactive interface.
- [MCP versioning and compatibility](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning): select a supported SDK/protocol combination rather than echoing an arbitrary client version.
- [Git worktrees](https://git-scm.com/docs/git-worktree): checkout ownership and shared repository state.

For AGY and future adapters, add the verified primary vendor documentation and installed-help evidence when implementation begins. Do not copy unverified CLI flags or model names from a previous environment.
