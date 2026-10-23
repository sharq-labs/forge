# BR1.1 owner-publication lifetime closure evidence

Status: Round19 found two substantive corrective families; repaired source under full-gate rerun and fresh Round20 required. NOT CLOSED.
Initial clean SHA: `a57f1fdd393d1c98f603f6eb1a4ed99fb708f149`; identical source/tests to Round18 `cc7ef06b0d08398173d9448ff47d8abb7e375d44`.
Authorized primary: `/home/dev_kaeem/forge-gen2-authority-v1`, branch `research/mind-gen2-authority-binding-v1`, existing WSL Ubuntu24.04 CPython3.12.3 venv. No new implementation worktree/branch.

## Cause and approved contract

Round18 retained a raw returned dictionary before capture. Two interruptions left no stable binding/history; restoring an entry in that same dictionary erased the only reference needed to distinguish spent from unspent. The native matched reproducer executed twice for live mappings at depths144/145 and once for detached controls. The owner approved stable, recoverable published bindings/history across restore on2026-10-24.

`AccountPublication` now commits immutable native binding generations before handoff. It retains the actual canonical BudgetLedger/ScientificExperiment objects, whose native histories append in place; it creates no second budget/evidence vocabulary. Readers reconcile histories from every retained generation through the existing owner JSON normalization and comparison rules. Missing or unreadable history never implies unspent. A generation acknowledged earlier can grow later, so it remains retained.

Terminal close invalidates source readers and snapshots. Retirement requires closure and no active acquisition leases, including construction. Leases are caller-owned before registration and marked inactive before removal, allowing retirement to recover interrupted removal without timeouts or GC assumptions. Open-source incremental retirement is deliberately unsupported. Read acceptance has a final open-source and generation-identity check. A new generation during comparison triggers bounded canonical rereconciliation against the original handed binding; sustained churn refuses transiently. Publications after the final check order later. This is an in-process observation boundary, not an atomic reservation/execution transaction.

## Necessary API migration

`BudgetReader.following(callback)` retains its call shape but now requires the callback to return `source.publish(ledgers, experiments)` from one exact `AccountPublication`. Raw mutable callback results cannot establish lifetime and are rejected. Keep one publication source across restores; a new source deliberately states a new timeline. Publish bindings before handing them to readers. Do not replace a source merely to clear refusal. Public constructor mode over fixed account objects is unchanged; it does not follow replacement registries.

Synthetic Owned fixtures hold a persistent publication. Historical test callbacks use an explicit test-only publishing adapter; the callback prepares a binding and publication commits it before reader handoff. The adapter does not claim authority over callback-local states never published. Three direct callback replacement fixtures and the detached generated trace were migrated too. Existing assertions were retained. No scientific/persistence payload schema or Gen1 implementation was changed. Publication generations are runtime retention, not serialized evidence or replay proof.

## Failing-first and controls

Before production edits, `test_pre_capture_restore_does_not_restore_authority` ran: 1 passed (single interruption), 1 failed (double interruption), with assertion `restore erased spent authority` and executor count2. Native original source hash: `bee80307fcd73de69a8a00f49b3e1d7d56295b2e4f7d78bd0183616a6568a298`.
On repaired source, 34 native recursion-depth/control combinations (130–146, live/detached) each refused redispatch with one executor call. This does not assert that every depth reaches the same phase. Deterministic controls establish the precise phase separately.
57 added controls comprise 21 focused lifecycle cases and 36 bounded traces. All 870 targeted tests passed. Eight semantic mutants were killed; zero survived, zero invalid, zero unexecuted. Positive controls before/after: 57 passed each. Exact commands and failing nodes are in mutations.json; full logs remain outside the repository.

The design review found writable tokens, overridable source history and orphan acquisition leases; these were fixed with frozen tokens/bindings, exact source type and explicit lease quiescence controls. It was static design feedback, not scientific validation.

## Scope and residuals

Synthetic software authority evidence only: not physical validation, certification or formal verification. In-process retention grows with distinct published bindings and reconciles retained entry histories; no bounded-memory/performance claim. Repeated hostile interruptions can deny service; no timeout converts uncertainty into authority. Process crash persistence, executor reservation/at-most-once concurrency and arbitrary private-state tampering remain outside this bounded change. Source lifetimes must not be substituted during ordinary restore. No push, PR, merge, OD3 or later Big Rock.

Raw logs and temporary mutant sources: `/home/dev_kaeem/br11-review/lifetime-closure/`. Curated state_machine.json records explored trace parameters and coverage limits. PROGRESS records exact commands and intermediate failures, including fixture migration and refusal-message compatibility issues; none is concealed as a passing run.

## Pre-FAST ladder at repaired source

Owner source SHA256 `839a4ac9ce18f363a55612a93e2acbb5072b02924c1ea7246f5360242bc13368`.
Targeted: 870 passed; regression: 279 passed; guards: 1585 passed / 2 failed;
affected expensive: 335 passed / 13 failed / 14 errors. Failure IDs AND normalized
exception reason lines match the preserved same-environment base at1202ea6c.
Rescore and authority benchmark MATCHES; Gen1 INTACT. Base failures remain red.
FAST will run against a clean source commit in this same implementation checkout;
then its curated evidence will be committed before independent Round19. No new implementation worktree.

## Round19 corrective continuation
See ../round19/README.md for complete disputed-finding disposition and failed-first approaches. Identity mismatch alone no longer establishes permanent divergence; canonical conflicting histories still do. Final generation checks cover constructor and ordinary pins. The initial helper incorrectly switched the pin to the latest binding; R10 caught that, and the corrected helper preserves original snapshot identity. Full gate results below will supersede the historical pre-FAST counts without concealing the failed Round19 gate.

## Corrected-source evidence before final FAST
At source hash efad8b564d00331877308151648554970222652a3249220c7fe934d4118eb7a3: targeted885passed, regression279passed, guards1600passed/2failed, affected expensive335passed/13failed/14errors. Rescore MATCHES, authority benchmark MATCHES, Gen1 INTACT. Ten isolated semantic mutants killed, zero survived/invalid/unexecuted;72positive controls passed before and after. Prior eight-mutant report remains historical; new two mutants specifically omit final generation check or restore identity-as-divergence. Native depth/control sweep rerun34cases,0duplicate dispatches. First rerun stopped on stale harness HEAD assertion before any scenario; only expected HEAD was updated, then all34cases executed.
