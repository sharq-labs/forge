# Round 20 independent B/C review

## A. Scope
Immutable b4bbee0f6df40b7dd0de9b0739beef392dab6be5, owners.py SHA256 efad8b564d00331877308151648554970222652a3249220c7fe934d4118eb7a3, native Ubuntu-24.04 existing Python environment. Reviewed complete budget-owner publication, acquisition, canonical readback, unread barrier, reconciliation, cleanup and snapshot-serving paths; independently inspected current corrective diff. Repository source was read-only. Read CLAUDE, architecture/core/freeze contracts, active bounded work and relevant Master Plan/Genesis/claims-layer sections. AGENTS.md was absent in native checkout; supplied user contract and CLAUDE applied. No external research or scientific validation.

## B. Authority boundary
### Lens B — concurrency and lifetime
No substantive counterexample found. AccountPublication preserves all published native bindings until terminal closure and quiescence. A final locked generation comparison (owners.py:448–456,1075–1085) orders each completed acquisition against publication; a newer generation triggers bounded canonical reconciliation, including construction. Tests paused actual execution by sys.settrace immediately before this final check and committed two new generations, including a spent generation subsequently replaced by an earlier detached state. Both constructor and existing-reader acquisition refused that restored account. A genuine incompatible canonical history also refused on repeated reads. Closing at the same checkpoint prevented acquisition and retirement remained refused while its lease was active, then succeeded after completion. Three independent readers recovered a published replacement's spend even after one, two or three callback interruptions before handing its token back.

No executor reservation is established by this check. Publication after the final lock boundary orders after this observation. Ordinary simultaneous executions after accepted observations remain execution-owner responsibility; this is not an already-published history-loss finding.

### Lens C — identity and detached canonical records
No substantive counterexample found. Two distinct detached but canonically equal publications during final comparison preserved honest progress in both constructor and pin paths; the live reader subsequently accepted a new settled charge. Canonically conflicting historical entries refused. `_against_unread` at832–856 now leaves identity-incomparable barriers unresolved instead of treating identity alone as proof of divergence. Canonical comparison at904–916 still detects incompatible histories. Existing deterministic R19 changed-barrier controls and R6 monotonic replacement controls executed alongside these independent probes. Historical R16/R17 controls exercised canonical entry and serialization normalization.

## C. Applicability and model use
NO second applicability authority found in the reviewed paths. They preserve canonical budget/experiment owner reads and add no model selection or applicability verdict.

## D. Verification / validation
129 tests actually passed, including 11 independent probes and 118 repository controls. This is synthetic software verification, not physical validation, certification, or a global concurrency proof. Exact argv/environment identity/output is in execution.json and tests.log. No tests were modified, skipped or weakened. Tests used PYTHONDONTWRITEBYTECODE and disabled pytest cache. Source hash remained unchanged.

## E. Uncertainty
NO new UQ vocabulary or invented numerical uncertainty found. This bounded change does not transform missing scientific uncertainty into evidence.

## F. Evidence / context / policy
Retained bindings are lifetime support for existing canonical owners, not a second budget evidence authority. Unknown/unreadable histories refuse or remain unresolved. Neither policy nor caller publication tokens supply independent scientific evidence.

## G. Provenance / replay
Canonical ledger/experiment histories remain rederived by existing owner serialization. A stale snapshot remains nonlive and closure invalidates it. This review makes no durable restart, crash consistency, or exactly-once claim.

## H. Adversarial test coverage
Independent test_independent.py: constructor/pin × spent-restore/equal-detached/close/conflict =8 Event-controlled final-boundary traces; three-reader published-spend with1/2/3 interrupted callbacks =3 traces. Repository suites executed: authority_lifetime, authority_lifetime_state_machine, authority_review_r19, authority_publication_currency_r19, authority_review_r6, authority_review_r16, authority_review_r17. Total129 passed in9.57s. No harness failures in executed tests. Initial instruction read command encountered absent native AGENTS.md; this was not a test result and was resolved by reading CLAUDE and supplied user instructions.

Q1 NO — no second scientific state authority in these budget lifetime paths.
Q2 NO — no second applicability authority.
Q3 NO — no duplicate units.
Q4 NO — no duplicated design/search or independent budget accounting authority found; canonical owners decide histories.
Q5 NO — world reader emits owner records/refusals, no scientific verdict.
Q6 NO — no proposer bypass found in the reviewed acquisition surface; this lens did not re-audit every external adapter.
Q7 NO — no unadmitted provider execution path introduced or found through this lifetime surface; concurrent reservation semantics are explicitly outside this observation guarantee.
All answers are bounded to the reviewed source and actual probes, not universal absence proofs.

## I. Findings
0 BLOCKER,0 MAJOR,0 MINOR substantive findings. Residuals: retained generations grow throughout an open source's lifetime; sustained publication churn may transiently refuse; arbitrary private-memory tampering, process persistence, executor reservation and events after final comparison are outside the approved lifetime contract. These are limitations, not demonstrated defects in this review.

## J. Verdict
PASS
