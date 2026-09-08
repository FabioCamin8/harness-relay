# Acceptance gates

All gates below are **planned and not accepted by this document**. Local command observations are recorded separately from gate acceptance; evidence from a private predecessor or another installation does not automatically validate this public package.

Each result records candidate SHA, test command, environment/version, observed outcome, and evidence location. Use passed, failed, blocked, or not run; never substitute an implementation summary for test evidence.

## Offline gates

Normal CI uses fake native executables, temporary homes/configs, and disposable repositories. No model calls, personal accounts, remote hosts, or provider secrets are required.

| Gate | Owner PR | Required proof |
| --- | --- | --- |
| G01 — Public source | PR-1 | Export contains only permitted source; no private history, secrets, runtime logs, browser state, host identities, or personal config. License/provenance decision and required notices recorded. |
| G02 — Portable package | PR-1 | Built package installs and runs under a temporary non-root home; packaged resources resolve without a source checkout; no hard-coded maintainer paths, model/provider, vault, retrieval MCP, or remote host is required. |
| G03 — Config contract | PR-2 | Strict version/types, disabled default, executable override, missing/unknown adapter, invalid role reference, and unsupported config version produce predictable results. No auth/model/provider config is silently rewritten. |
| G04 — Setup ownership | PR-2 | Dry-run does not write; repeated setup does not duplicate; JSON/JSONC and supported scope conflicts are handled; interrupted writes are recoverable; uninstall preserves unrelated and subsequently edited content. |
| G05 — Native invocation | PR-3 | Each adapter receives correct argv/cwd/stdin and retains native config; task text is not shell syntax; unsupported overrides are rejected; another provider is never invoked as fallback. |
| G06 — Output and errors | PR-3 | Native structured success/failure, valid exit with empty output, malformed/truncated output, auth-required, denied tool, missing executable, and unsupported version are classified without English-keyword heuristics. |
| G07 — Result evidence | PR-3 | Result validates against the packaged schema including nested types; process completion, task outcome, validation, and acceptance are distinct; worker claims are labeled; no unexecuted test is reported passed. |
| G08 — Git evidence | PR-3 | Committed edits, staged/unstaged/untracked edits, rename/delete cases, validation-generated edits, and partial failure retain correct base/result/diff evidence, even when final Git status is clean. |
| G09 — Worktree safety | PR-4 | Independent tasks have distinct owned worktrees; same-name repositories do not collide; run collisions/path traversal/symlink escapes are rejected; dirty source and unmerged results survive failures and cleanup attempts. |
| G10 — Read-only accuracy | PR-4 | A change to an already-dirty file is detected within the declared boundary; a changed HEAD is detected; validation effects are included; user content is never reset/cleaned to hide a violation. Native enforcement limits are documented. |
| G11 — Process lifecycle | PR-4 | Timeout, cancellation, parent disconnect, subprocess failure, and interruption during setup/result writing leave inspectable terminal state; owned child processes are handled; no permanent MCP deadlock or stale running claim. |
| G12 — MCP and recursion | PR-4 | Supported handshake/error handling, protocol-clean stdout, runtime schema validation, enabled-only discovery/invocation, responsive cancel/status behavior, and worker re-entry rejection are tested. Native internal subagents are not prohibited. |
| G13 — Doctor | PR-4 | Doctor is read-only and inference-free; detection/config validity differ from dated capability checks; disabled/optional capabilities are not probed or treated as required failures; required enabled failures are actionable. |

### PR-2 evidence

G03 and G04 are not marked accepted here. A fresh wheel was built from the current candidate working tree at `/tmp/harness-relay-pr2-artifacts.yyeLZa/harness_relay-0.1.0a1-py3-none-any.whl` (SHA-256 `fd47413ae692841772ba660d969175abc472452d637487c05538625a7d3091cb`) and installed with its `[test]` extra into `/tmp/harness-relay-pr2-wheelcheck.mQKImm`. From `/tmp`, with `PYTHONPATH` unset, the installed artifact observed 31/31 PR-2 tests OK, 4/4 package tests OK, and 35/35 tests OK overall. The PR-2 tests cover strict config failures, enabled-only discovery, JSON/JSONC preservation, nested trailing commas, malformed recovery rejection, UTF-8/CRLF ranges, all removal positions, scope conflicts, dry-run, repeat no-op, cold no-process/no-network behavior, ownership-safe uninstall, and injected interruption recovery. These are candidate observations; the exact candidate SHA and gate disposition belong in the PR handoff. No live worker task, MCP runtime, worktree, lifecycle, doctor, CI/release, or G14 claim is made here.

JSONC setup uses the pinned Python-native Tree-sitter parser pair (`tree-sitter==0.23.2`, `tree-sitter-json==0.24.8`) with no external runtime or network bootstrap. The setup-created `mcp.harness-relay` entry remains `enabled: false` until PR-4 implements and verifies the MCP runtime.

Use adversarial but harmless fixtures: filenames with spaces and unusual characters, identifiers containing separators, a fake CLI that spawns a child, a worker that commits and exits, an existing dirty checkout, and a JSONC config containing unrelated comments/keys. Do not treat a denylist of the maintainer's removed tools as a universal product test.

If a gate is not applicable to the selected initial platform or an optional adapter, state the exact boundary. That does not permit claiming support for the omitted case.

## G14 — Independent-user and model-independence acceptance

Owner PR: PR-5. Required for the local alpha acceptance claim.

In an environment independent of the maintainer's live setup, use OpenCode and one supported, authorized native worker. No root, GLM, Z.AI, Semble, vault, remote desktop, or Apple host may be necessary.

1. Install the built artifact, not an editable shortcut into the development tree.
2. Run setup preview, choose one installed native worker, and apply only the managed integration.
3. Give OpenCode a small repository objective and explicitly use the typed delegation tool.
4. Observe the actual native worker process and an isolated writable worktree from the recorded base.
5. Verify the requested change and independently executed validation in the normalized result.
6. Confirm the source checkout is unchanged, no merge occurred, and logs/worktree evidence remain available.
7. Repeat setup and confirm no duplicate integration or unrelated changes.
8. Demonstrate changing the master model through OpenCode without changing worker adapters/config. Offline config-independence tests are mandatory; a second live-model run is recorded separately and requires available authorized access. Missing live access is not fabricated as a pass.
9. Uninstall the integration and verify preservation of pre-existing configuration, native auth, work, and artifacts.

Record precisely which live portions ran. If live model-switch or native-worker access is unavailable, the relevant live claim remains unverified even if offline packaging and adapter tests pass.

## Capability-specific live checks

Live tests are explicit, bounded, and separate from routine doctor/CI. Do not purchase access, change accounts, bypass permissions, or call an unavailable service to complete the matrix.

| Claimed capability | Minimum relevant evidence |
| --- | --- |
| Native text execution | Harmless non-interactive response through the adapter; correct native output and terminal result. |
| Repository reading/review | Worker reads a fixture and correctly identifies a fact not contained in its prompt; no forbidden checkout changes. |
| Repository editing/testing | Worker changes an isolated fixture; runner verifies the change and tests; no source merge. |
| Browser/multimodal | Actual supported tool/input path is exercised; plain text completion is insufficient. |
| Optional remote desktop | Existing desktop interaction with a harmless page and verified observation/artifact; no private sessions reset, exposed, or copied. |
| Optional Apple operations | Explicit configured operation on authorized Apple tooling; Linux tests or reachability alone are insufficient. |

A worker may be verified for text but unverified for repository tools. An intentionally disabled worker is not a defect. An experimental adapter must not be advertised as operational solely because its binary exists or its help command succeeds.

## Release review

Astra reviews the complete diff at the exact release candidate SHA, reruns relevant offline gates, and checks live evidence separately. An upstream/main change or new candidate commit requires a delta review; old approval does not certify new code.

The release record must show the built artifact, supported platforms/versions, schema/config versions, license/provenance, passed gates, omitted checks, and explicit limitations. No success badge or release tag is justified by these planning documents alone.

Preparing a release candidate is not authorization to publish a tag/package or migrate a live installation. Those actions require the maintainer's explicit release/deployment instruction.
