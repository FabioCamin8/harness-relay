# Development workflow: Sol, Luna, and Astra

These names describe the maintainer's development roles, not dependencies or mandatory models in HarnessRelay. The product remains one OpenCode master with a user-selected model and native local workers.

## Authority

Sol leads scope, coordinates implementation, and independently reviews evidence. One Luna XHigh worker implements the currently assigned work package at a time; do not spawn nested agents. Astra Medium is reserved for difficult blockers or high-risk decisions. Prefer one PR at a time; parallel work is justified only by genuinely independent scopes and separate worktrees.

The available existing native harness/tooling may be used to build this project. Do not require the unfinished HarnessRelay package to orchestrate its own bootstrap. Do not change the maintainer's working installation or authentication/provider routes to run this workflow.

After the initial documentation bootstrap, implementation goes through branches/PRs. No development role automatically merges, tags, publishes a package, migrates a live environment, or force-pushes. Those require a separate maintainer instruction.

## Sol: lead, coordinator, and reviewer

1. Read AGENTS.md, PLAN.md, architecture, acceptance, and compatibility documents. Inspect live repository state, branch/HEAD, open PRs, and checks rather than trusting an old handoff.
2. Audit the plan against the universal native-harness objective. Remove unnecessary complexity; propose only evidence-backed amendments. Do not implement product code while acting as the independent reviewer.
3. Select the next uncompleted work package. Resolve scope, dependencies, permitted source reuse, and relevant gate IDs. A source/access/license ambiguity blocks the affected import, not unrelated read-only investigation.
4. Assign one Luna XHigh implementation writer at a time with a bounded packet. Do not spawn nested agents or claim an invocation that did not occur.
5. Review the full diff and resulting files at Luna's exact candidate SHA. Rerun pertinent offline tests, inspect the installed-package/config behavior where relevant, and independently examine failure cases. Do not accept a summary, test count, or doctor pass as proof of untested capabilities.
6. Publish findings with severity, path/line, reproduction, impact, and required change. Separate code blockers from unavailable optional accounts/hosts or unverified capabilities.
7. Issue PASS, CHANGES_REQUIRED, or BLOCKED against the reviewed SHA. A new commit requires delta review. Reassign only specific defects; do not expand the task into later PRs.
8. After PASS, continue the planned progression when it remains within the active assignment; do not stop for a routine per-PR approval. Maintainer approval still governs merge/release/deployment, not a worker's self-assessment. A separate assignment stop condition remains in force.

Sol handoff format:

```text
Work package: PR-N
Repository / base ref / base SHA:
Objective:
Allowed scope and files/components:
Forbidden changes:
Acceptance gate IDs and exact checks:
Public-source/provenance constraints:
Required deliverables:
Stop condition:
```

## Luna: implementation worker

1. Read the repository instructions and Sol's packet. Verify base SHA, dirty state, active worktrees, and assignment dependencies. Preserve legitimate unrelated work.
2. Work on a dedicated branch/worktree. Implement only the assigned work package. Do not turn the plan into one giant PR or configure live global files during package tests.
3. Inspect the current implementation before copying or refactoring. Private reference source may be reused only when accessible, authorized, and safe to publish. Never copy its history, runtime state, credentials, internal topology, or private knowledge files.
4. Use native CLI help and primary vendor documentation to verify invocation contracts. No API replacement of native workers, hard-coded models/providers, auth workarounds, automatic fallback, or permission widening.
5. Add offline regression tests for each behavior/fix. Run the assigned gates in temporary homes/repos and record exact commands and outcomes. Live checks require authorized available access; missing access remains unverified.
6. Update only the documentation and compatibility claims justified by this work. Inspect the full diff and staged content for private data before every public push.
7. Commit coherent changes, push the assigned branch, and open/update its PR. Do not merge, tag, publish a package, or deploy. Retain useful worktree/log evidence locally without uploading sensitive runtime output.
8. Return the handoff below. Continue only within the active assignment's stated scope and stop condition; do not independently expand into another phase.

Luna return format:

```text
Work package / PR URL:
Base SHA / candidate SHA:
Changed files and purpose:
Acceptance gates: passed / failed / blocked / not run:
Exact commands and results:
Native versions and live evidence, if exercised:
Public-source/license/provenance check:
Known limitations and unresolved blockers:
```

## Review standards

The critical questions are whether the master model remains user-owned, workers really run natively, setup is reversible, result evidence is truthful, work is preserved under failure, and disabled/optional capabilities remain non-required.

Require minimal, reproducible evidence. G01-G14 in docs/ACCEPTANCE.md define the planned gates. Do not mark later gates passed just because the current work package intentionally omits them.

No screenshots, logs, cookies, auth state, account details, private host addresses, or source-history leakage in public PRs. Publish concise sanitized evidence instead. If a public-data leak is discovered, stop further publication and report it; do not assume deleting the latest file erases prior exposure.

## Current assignment state

PR-2 through PR-5 are implemented as linked stacked PRs. Package code candidate `04c5d43` has exact-SHA source, installed-artifact, hosted-CI, and independent review evidence; any later code change requires focused regression and delta review. Maintainer authority is still required for review, merge, tag, publication, deployment, or migration.
