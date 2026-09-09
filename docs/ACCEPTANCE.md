# Acceptance gates

Gates are accepted only where a candidate-specific evidence section records a review verdict. Local command observations remain separate from live capability acceptance; evidence from a private predecessor or another installation does not automatically validate this public package.

Each result records candidate SHA, test command, environment/version, observed outcome, and evidence location. Use passed, failed, blocked, or not run; never substitute an implementation summary for test evidence.

## Offline gates

Normal CI uses fake native executables, temporary homes/configs, and disposable repositories. No model calls, personal accounts, remote hosts, or provider secrets are required.

| Gate | Owner PR | Required proof |
| --- | --- | --- |
| G01 — Public source | PR-1 | Export contains only permitted source; no private history, secrets, runtime logs, browser state, host identities, or personal config. License/provenance decision and required notices recorded. |
| G02 — Portable package | PR-1 | Built package installs and runs under a temporary non-root home; packaged resources resolve without a source checkout; no hard-coded maintainer paths, model/provider, vault, retrieval MCP, or remote host is required. |
| G03 — Config contract | PR-2 | Strict version/types, disabled default, executable override, missing/unknown adapter, compatibility role validation, and unsupported config version produce predictable results. No caller/auth/model/provider config is silently rewritten. |
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

G03 and G04 passed independent review at code candidate `8849e043f04e320f111fba8f11e070c012a45e03` on Debian GNU/Linux 13 with CPython 3.13.5. `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /tmp/harness-relay-pr2-exact.XtDLOR/venv/bin/python -m unittest discover -s tests -v` passed 44/44 from source. A wheel built from `git archive 8849e04` was installed with its test dependencies into a fresh virtual environment; `env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 /tmp/harness-relay-pr2-final.WGIHNa/venv/bin/python -m unittest discover -s /tmp/harness-relay-pr2-final.WGIHNa/src/tests -v` passed 44/44 outside the checkout. The wheel is `/tmp/harness-relay-pr2-final.WGIHNa/artifacts/harness_relay-0.1.0a1-py3-none-any.whl`, SHA-256 `8bff2bebab0e520cc25b18b26ad21ba243e1b6ee74bab37195f08451562b7fde`; it contains the package schema and MIT license. An installed cold `setup --dry-run --non-interactive` with no enabled workers ran as UID 65534 against a mode-0555 temporary HOME, whose directory inventory remained empty. CPython 3.9 manylinux2014 x86_64 binary wheels were separately resolved for `tree-sitter==0.23.2` and `tree-sitter-json==0.24.8`. No live worker task, MCP runtime, worktree, lifecycle, doctor, CI/release, or G14 claim is made here.

JSONC setup uses the pinned Python-native Tree-sitter parser pair (`tree-sitter==0.23.2`, `tree-sitter-json==0.24.8`) with no external runtime or network bootstrap. The setup-created `mcp.harness-relay` entry remains `enabled: false` until PR-4 implements and verifies the MCP runtime.

### PR-3 evidence

G05 through G08 passed local lead review at code candidate `8344fc33d048183065c9c7cb7a8d1977c9ecae42` on Debian GNU/Linux 13 with CPython 3.13.5. `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /tmp/harness-relay-pr2-final.WGIHNa/venv/bin/python -m unittest discover -s tests -v` passed 54/54 from source. A wheel built from `git archive 8344fc3` was installed with runtime dependencies into a fresh virtual environment; `env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 /tmp/harness-relay-pr3-exact.eZdTCW/venv/bin/python -m unittest discover -s /tmp/harness-relay-pr3-exact.eZdTCW/src/tests -v` passed 54/54 outside the checkout. The wheel is `/tmp/harness-relay-pr3-exact.eZdTCW/artifacts/harness_relay-0.1.0a1-py3-none-any.whl`, SHA-256 `2d264a755dca030c662dab9e42a4dbbc27490edae97d7108f018348a61b17161`; it contains the config schema, result schema, and MIT license.

Offline fake executables exercised the pinned argv/output contracts for Codex CLI 0.153.4, Claude Code 2.1.104, and AGY 1.1.27, including explicit overrides, structured success/failure, authentication and denial codes, empty/malformed output, missing executable, timeout, cancellation, nested schema rejection, and committed/staged/unstaged/untracked/rename/delete/validation Git evidence. Installed help and the primary vendor pages in the compatibility document were checked on 2026-09-08. No live native task, subscription/account capability, G14 workflow, or cross-platform claim is made. Maintainer review of stacked PR [#3](https://github.com/FabioCamin8/harness-relay/pull/3) remains pending.

### PR-4 evidence

All cumulative review findings, including process-group escape and serialized-evidence overflow cases, are corrected and independently reviewed through code candidate `5796fffe92f757a778c4e51152dc820aeda2e90d`. Its 78/78 source tests pass on Debian GNU/Linux 13. Final candidate `04c5d43e5912864a03c4f31d99d508a4acd80d00` adds only an explicit UTF-8 declaration to a fake-worker fixture; that delta received independent PASS review and its exact-head source suite also passes 78/78.

The candidate tests cover parent and final-component symlink rejection, collision/traversal rejection, preservation of dirty, unmerged, and clean committed work, NUL-delimited tracked/untracked/ignored path integrity plus `HEAD`, owned process-group timeout/cancel after leader exit, parent disconnect, interrupted terminal persistence without a stale running record, recursion refusal, strict MCP version negotiation and request IDs, malformed cancellation notifications, enabled-only runtime-validated tools, responsive status/cancel, validation redaction/bounds, and inference-free doctor behavior. Symlink target content outside the worktree is explicitly outside the post-hoc integrity boundary; native sandbox enforcement remains required. These cumulative remediations are carried by stacked PR [#5](https://github.com/FabioCamin8/harness-relay/pull/5) after the standalone PR-4 head; maintainer review of [#4](https://github.com/FabioCamin8/harness-relay/pull/4) and #5 remains pending.

### PR-5 evidence

At package code candidate `04c5d43e5912864a03c4f31d99d508a4acd80d00`, 78/78 exact-head source tests pass, including the offline setup-to-generated-MCP delegation workflow. A wheel built from `git archive 04c5d43` passed 78/78 outside the checkout without `PYTHONPATH` on CPython 3.13.5 as UID 65534 and CPython 3.9.25. Wheel SHA-256 is `76df39d29f922a2dd2006632bebcc8f72e76d8fc86ad0584b0db3b250b9e2239`; sdist SHA-256 is `7e9ae61e07d62bf38114c1d3847d77af749eae2cd7e9f10ce4dedfdae8f3e427`. Both archives validate, and scans of the source export, extracted wheel, and extracted sdist pass. Six hosted push/pull-request checks pass at the exact candidate head. The local artifact and command evidence is retained under `/tmp/harness-relay-04c5d43-final.1IL2WC`; PR [#5](https://github.com/FabioCamin8/harness-relay/pull/5) records the sanitized review evidence.

Live evidence used installed artifact `7afa87f`, OpenCode 1.18.29, and Codex CLI 0.153.4 on 2026-09-08. OpenCode using authorized `openrouter/cohere/north-mini-code:free` called `harness-relay_delegate_codex` exactly once. With explicit `sandbox: "workspace-write"`, Codex changed only the retained worktree's `value.txt` from `before\n` to `after\n`; the independent validator passed, source `HEAD` and status remained unchanged, and no merge occurred. A preceding run inherited the user's read-only Codex default, made no edit, and correctly recorded failed validation; it is not counted as capability success. A separate authorized `openrouter/poolside/laguna-xs-2.1:free` OpenCode run returned the requested text with zero tool calls while the relay worker-config SHA-256 remained `e67fa2a4be61f7306b8f796956b7d0e9a2863c9fbdf206c522b653f757a1d0e2`. Setup repeat was byte-stable. Uninstall removed only owned fragments and preserved the added user model key, relay config, native-auth hashes, source work, and retained run/worktree artifacts.

The live run used the existing authorized maintainer account while all configuration, package, repository, state, and worktrees were isolated under a temporary root. No credential was copied and no auth permission was weakened. The exact artifact's complete workflow separately passed as UID 65534, demonstrating no product root requirement. Claude, AGY live execution, browser/multimodal, desktop, Apple, macOS, WSL, and Windows remain `NOT RUN`. One paid-model attempt was `BLOCKED` by OpenRouter credit limits before inference and is not acceptance evidence. No merge, tag, package publication, deployment, authentication change, billing action, or operational migration occurred.

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
8. Demonstrate changing the caller model through OpenCode without changing worker adapters/config. Offline config-independence tests are mandatory; a second live-model run is recorded separately and requires available authorized access. Missing live access is not fabricated as a pass.
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
