# Compatibility and evidence

Status at the unreviewed PR-2 candidate, 2026-09-08: local offline configuration/setup tests have been run on Debian GNU/Linux 13; no native HarnessRelay adapter, live worker task, or MCP protocol version has been verified. The component versions below are supplied environment inventory, not claims that HarnessRelay supports or has exercised those runtimes.

## Intended support

| Component | Intended role | Initial status / boundary |
| --- | --- | --- |
| OpenCode 1.18.29 | Only master; user-selected model | Supplied version inventory; no live HarnessRelay integration verified. Preserve effective native model/provider configuration. |
| Codex CLI 0.153.4 | Native local worker | Supplied executable version inventory; no live HarnessRelay adapter/task verified. |
| Claude Code 2.1.104 | Native local worker | Supplied executable version inventory; no live HarnessRelay adapter/task verified. |
| AGY / Antigravity 1.1.27 | Native local worker | Supplied executable version inventory; no live HarnessRelay adapter/task verified. Text-only smoke cannot certify repository/browser capability. |
| Gemini CLI | Additional native worker | Deferred optional adapter, not a release prerequisite. |
| Other installed CLIs | Possible future native workers | Unsupported until a named adapter and tests exist; detection alone is insufficient. |
| Remote desktop | Optional real GUI capability | Deferred, disabled by default; no specific product/host required by core. |
| Apple tooling | Optional specialized capability | Deferred, disabled by default; no Mac required by core. |
| Linux, non-root user on Debian GNU/Linux 13 | First required platform | Supplied platform inventory; local offline setup tests ran here. Native worker and MCP capabilities remain unverified. |
| macOS / WSL / native Windows | Additional platforms | Unverified; do not claim support without platform-specific evidence. |

OpenCode's chosen model must be capable of using the exposed tools for the intended task. Model independence does not promise equal reasoning quality or tool reliability across models. HarnessRelay does not rank them or select provider accounts.

Each local worker owns its authentication and upstream routing. An existing auth file is not proof of entitlement or a live session. Do not infer billing, subscription policy compliance, quota, or runtime capability from discovery alone. PR-2 discovery labels selected executable versions `detected-unverified`; it does not claim adapter execution.

The source-preserving JSONC editor uses the pinned Python-native `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8` pair. The JSON grammar reports trailing commas as recovery errors; HarnessRelay accepts only a comma after a complete member/value before the matching close, after masking comments/trailing commas in a strict validation copy. Other recovery/error shapes are rejected. This parser dependency is setup implementation detail, not evidence of a native worker or MCP runtime capability.

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
