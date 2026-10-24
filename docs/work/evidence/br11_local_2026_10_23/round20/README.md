# BR1.1 Round20 closure

**CLOSED within the authorized BR1.1 development contract.** Implementation reviewed and clean FAST executed at `b4bbee0f6df40b7dd0de9b0739beef392dab6be5`; source SHA256 `efad8b564d00331877308151648554970222652a3249220c7fe934d4118eb7a3`. This closure commit changes documentation/evidence only. Initial recovery SHA `a57f1fdd393d1c98f603f6eb1a4ed99fb708f149`; lifetime implementation commit `0b605b43416d575b60f87ca57eea7a1d646489d5`.

## Independent review
Three fresh independent reviewers cover six lenses: A/F canonical authority and bypass; B/C concurrency/lifetime and identity; D/E serialization/replay and scientific evidence. They independently inspected actual source at the immutable implementation SHA and ran87,129,57tests respectively, including26fresh scratch probes. These suite totals overlap and are not a unique test total. All report PASS and scoped Q1–Q7 NO. Additional forge-scientific-review agent returns supplied-source static PASS for corrective delta; its limits are explicit. Fresh completeness critic PASS:0BLOCKER/0MAJOR/0substantiveMINOR; no unresolved contract-invalidating challenge. Review reports, exact commands and small probe sources are retained here. Bulky logs remain outside repo.

Round19 is preserved as CHANGES REQUIRED, Q4YES, two substantive families. Canonical identity mismatch now remains unresolved until actual content comparison. New generations arriving during comparison cause bounded rereconciliation against the original pin binding; final source check orders subsequent publications later. Repeated churn temporarily refuses. No execution reservation was added. Both corrective families had intended red-first failures; no tests relaxed/deleted/skipped.

## Executed ladder and base comparison
Same existing WSL Ubuntu24.04 CPython3.12.3 environment, no installs. Base `1202ea6c3d96f5c31d0b142a32438da75e020cae`, preserved same-environment logs.

| Suite | Corrected implementation | Comparison |
|---|---|---|
| Targeted |885passed|No failures|
| Regression |279passed|No failures|
| Guards |1600passed,2failed|Same2failureIDs and extracted reasons as base|
| Affected expensive |335passed,13failed,14errors|Same27failure/error IDs and extracted reasons|
| Clean FAST |12896passed,67failed,190skipped,2warnings|Same67failureIDs;66/67extracted reasons identical|
| Rescore / authority benchmark |MATCHES / MATCHES|Executed|
| Gen1 reference |INTACT|Executed|

**Known diagnostic difference:** existing `test_synthetic_data_is_never_called_measured` fails unknown_provenance_files==0 at1202versusbase456. Scanner and failing-test source are byte-identical to base. Data-bearing review/evidence files increase inventory debt; the critic counted746changeddata-bearing paths (740docs/6benchmarks,739under docs/evidence). This is not identical diagnostic text, not a clean test gate and not a claim that provenance debt was repaired. The inventory analysis is bounded; it does not reconstruct every unknown-path classification. Existing domain/certification failures remain outside this repair.

Dirty-source FAST69fail included two tree.clean-only failures; retained separately. Clean-commit rerun removes those two and has no new failure identities. Earlier0bFAST exposed the genuine R6 regression; fixed and preserved in history. No certificate or test weakened to obtain this comparison.

## Adversarial evidence
Original Round18 double interruption reproduced duplicate execution; single/detached controls distinguished it. New lifetime tests57cases include36bounded generated traces in addition to preserved54older traces. R19 adds15cases, total72focused lifecycle/correction cases. Final10semantic mutants killed;0survive/0invalid/0unexecuted,72positivecontrols before/after. Native recursion depth/control sweep34cases,0duplicate dispatches. These counts are bounded software evidence, not exhaustive exploration or proof. Exact commands and failed approaches are in PROGRESS and ../lifetime_closure manifests.

## Limits and stop boundary
Runtime publication requires explicit AccountPublication adoption and persistent source identity across restore. Open lifetime retention grows with publications; no bounded-memory claim. Repeated interruption/churn can refuse service. Final observation check is not an atomic execution reservation: ordinary overlapping dispatch, process crash persistence and arbitrary private-state tampering are outside this contract. Source replacement intentionally declares a new timeline.

Status: IMPLEMENTED, TESTED, MEASURED (bounded synthetic software contract). Not physical SCIENTIFICALLY_VERIFIED, CERTIFIED or FORMAL. Historical/core certification debt remains; no OD3, install, push, PR, merge or other Big Rock. Scientific Contract Kernel v0 is the next authorized Big Rock; this task stops without starting it.
