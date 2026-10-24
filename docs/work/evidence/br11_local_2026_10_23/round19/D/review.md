# Round 19 independent lens D

Reviewed SHA: `0b605b43416d575b60f87ca57eea7a1d646489d5`. Native WSL Ubuntu-24.04 repository `/home/dev_kaeem/forge-gen2-authority-v1`. Import identity asserted by an executed probe.

## Findings

No confirmed actionable counterexample. This is not confirmation that the lifetime fix is complete.

## Attacks and observations

- Forged token with genuine source and bindings but no registered generation: refused.
- Stale publication token after replacement: refused; updating to latest token still refused the restored pre-spend ledger.
- Seven detached generations, then a late spend on the oldest retained object: both existing and newly constructed readers refused the rollback.
- Five JSON-detached restore cycles with nested tuple/list detail normalization: digest remained the owner digest.
- A recorded admission replayed, but its frozen authorities emitted no admission verdicts and could neither construct an execution desk nor authorize dispatch. No synthetic executor calls occurred.
- Changed budget total in a snapshot without changing recorded identity: replay dependency unavailable.
- Static review traced original source retention, historical account reconciliation, immutable token bindings, exact owner types, stale-token check, close checks and lease retirement. Published account objects are intentionally retained for their lifetime.

## Seven questions

### Q1

No second state authority demonstrated in this lens. RunStateReader reads canonical SystemRunResult/SystemCheckpoint; forward sequence and owner binding checks are adapters. AccountPublication retains owner objects and canonical history rather than issuing balances.

Evidence: `src/engcore/mind/world/owners.py:243-278`, `src/engcore/mind/world/owners.py:392-446`, `src/engcore/mind/world/owners.py:1033-1068`.

Limit: No independent state-chain fuzzing; callback currency remains execution-side policy.

### Q2

No second applicability engine demonstrated. ApplicabilityBinding.assess delegates to exact ScientificModelDefinition.assess_validity.

Evidence: `src/engcore/mind/world/world.py:96-124`, `src/engcore/mind/world/feasibility.py:853-918`.

Limit: Static inspection only for applicability; no physical validation.

### Q3

No parallel unit registry demonstrated. Domain identity/conversion and ledger amount conversion use canonical Quantity and unit-owner functions; replay refuses another registry fingerprint.

Evidence: `src/engcore/mind/world/domains.py:1-21`, `src/engcore/mind/world/world.py:315-337`, `src/engcore/mind/world/admission.py:615-622`.

Limit: No new offset-unit or registry mutation probe in this lens.

### Q4

No replacement design/search or spending engine demonstrated. Canonical ScientificVariable/ActionFamily/BudgetLedger are reused; DiscreteLevels is an explicit missing representation. Publication history adds lifetime control, not spending authority. Detached JSON restoration preserved owner digest in five generations.

Evidence: `src/engcore/mind/world/domains.py:1-21`, `src/engcore/mind/world/actions.py:1-11`, `src/engcore/mind/world/world.py:315-345`, `src/engcore/mind/world/owners.py:588-640`.

Limit: Experiment attempt-limit projection was inspected, not independently exhaustively cross-checked with owner behavior.

### Q5

No replay promotion to scientific verdict demonstrated. AdmissionResult requires live verified owners for export; frozen replay exported no verdicts in probe. Feasibility exports negative constraints only, not positive scientific support.

Evidence: `src/engcore/mind/world/admission.py:256-263`, `src/engcore/mind/world/admission.py:593-603`, `src/engcore/mind/world/feasibility.py:265-276`.

Limit: A self-consistent fabricated history may reproduce by documented design; reproduction is not provenance. Raw FeasibilityDecision verdicts are untrusted reporting views.

### Q6

No bypass established. Suggestions-only policy is selected by execution side and checked at admission and dispatch; caller proposer kind is explicitly not authenticated identity.

Evidence: `src/engcore/mind/world/port.py:18-24`, `src/engcore/mind/world/admission.py:402-417`, `src/engcore/mind/world/admission.py:519-540`.

Limit: Static review only for external suggestion path; in-process private-object introspection is outside the documented boundary.

### Q7

No unadmitted execution demonstrated. Frozen replay authorities cannot construct ExecutionDesk or authorize dispatch in probe; dispatch re-admits and compares minted identity.

Evidence: `src/engcore/mind/world/admission.py:402-440`, `src/engcore/mind/world/admission.py:457-471`, `src/engcore/mind/world/admission.py:500-509`.

Limit: Tests used synthetic executor only; no provider process launched. Executor reservations/at-most-once are out of scope.

## Executed tests

`PYTHONPATH=/home/dev_kaeem/forge-gen2-authority-v1/src:/home/dev_kaeem/forge-gen2-authority-v1 PYTHONDONTWRITEBYTECODE=1 /home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python -m pytest -q -p no:cacheprovider /home/dev_kaeem/br11-review/r19/D/test_replay_probe.py --basetemp /home/dev_kaeem/br11-review/r19/D/tmp`

2 failed, 5 passed in 1.43s; harness expected uppercase enums. Actual results correctly reproduced/refused.; log `tests.log`.

`PYTHONPATH=/home/dev_kaeem/forge-gen2-authority-v1/src:/home/dev_kaeem/forge-gen2-authority-v1 PYTHONDONTWRITEBYTECODE=1 /home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python -m pytest -q -p no:cacheprovider /home/dev_kaeem/br11-review/r19/D/test_replay_probe.py --basetemp /home/dev_kaeem/br11-review/r19/D/tmp2`

7 passed in 1.33s; log `tests_corrected.log`.

## Limits

- Review is not proof of the fix, scientific validation, certification, or general correctness.
- Independent scratch tests only; no full suite or broad random state-machine exploration run by this reviewer.
- Repeated-interruption and close/quiescence implementation and existing tests were statically inspected; not independently rerun in this lens.
- Publication is in-process lifetime control; process-crash persistence and executor reservation/at-most-once are excluded.
- No implementation edits or repository progress writes under read-only task constraint. Scratch only.
- rg unavailable in WSL; used Python targeted file reads.
