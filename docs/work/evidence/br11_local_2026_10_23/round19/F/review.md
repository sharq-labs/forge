# Round 19 independent lens F — architecture and admission bypass

SHA: 0b605b43416d575b60f87ca57eea7a1d646489d5. Native WSL Ubuntu-24.04; CPython 3.12.3. Import verified at /home/dev_kaeem/forge-gen2-authority-v1/src/engcore/mind/world/__init__.py. Read-only repository review; artifacts only in /home/dev_kaeem/br11-review/r19/F. No source/document changes. No inherited review conclusions used.

Disposition: no actionable finding demonstrated within the execution-side public-interface contract. This is bounded software review/testing, not scientific validation or certification.

## Q1 — second state authority?
No second authoritative state store found. projection.py:56–67 reads SYSTEM_STATE records and preserves value and uncertainty; owners.py:1382–1391 rederives replay identity through SystemState and verifies the requested run/value. projection.py:116–157 compares every binding and exact declaration projection. Caller edits cannot become a new state revision through admission.py:293–336. Cross-domain tests exercised stale state and changed projections. Limitation: execution-side selection of which run head is current is trusted; in-process arbitrary code is outside isolation claims.

## Q2 — second applicability authority?
No replacement applicability rule found. world.py:106–124 requires exact ScientificModelDefinition and calls its assess_validity. feasibility.py:853–918 calls that owner rule at exact declared/requested points; UNKNOWN and uncertainty without an exact point refuse gating MODEL_EXECUTION. SYSTEM_QUERY annotations deliberately do not certify a model. No separate physical validation claim is minted. Executed cross-domain controls cover bindings and stale owners; exhaustive model-domain combinations NOT RUN.

## Q3 — duplicate units?
No independent unit registry or conversion engine found. projection.py:53–54 binds the unit registry. world.py:290–301 and 315–338 use canonical Quantity conversions and reject incompatible/offset cost units; admission.py:163–175 returns values in declared units and :217–225 compares what was decided with what executor receives. Boundary tests prohibit direct pint dependency. Unknown unit conversions are refused rather than compared raw. Exhaustive dimensional fuzzing NOT RUN.

## Q4 — duplicate design/search/budget concepts?
ActionSpec/ProposedAction/FeasibleActionSpace are proposal and admission records, not a second search engine or persistent owner ledger. The legacy WorldBudget representation cannot become live admission authority merely by presenting plausible totals: projection.py:83–99 rebuilds projected BudgetStatement records from canonical ledgers/experiments and exact projection verification rejects mismatches. world.py:323–338 reconstructs BudgetLedger and delegates affordability; :339–345 is an explicit experiment-accounting adapter (attempt/observation limits), not a ledger mutation. Remaining/pool values are explanatory projections. Budget cost/duration estimates remain declaration inputs, explicitly classified in admission.py:73–89; they are not scientific predictions. No reservation or general at-most-once claim is made.

## Q5 — world scientific verdicts?
No positive support elevation found. admission.py:72 labels action_admission_not_scientific_support. AdmissionResult.feasibility_verdicts at :256–263 requires live verified owner admission. feasibility.py:265–276 exports only definite negative SRIA FeasibilityVerdict records; missing information is not a negative verdict and absence of negative verdicts is not support. Caller-built authorities can be live over caller-owned records: provenance is the execution-side gateway, not a cryptographic authenticity assertion. Test r3 and cross-domain controls executed. End-to-end scientific claim assessment NOT RUN.

## Q6 — external proposer bypass?
Fresh probes attempted raw ProposedAction, dictionary forms of admitted action and authorization, None, and an admitted bare proposal against a suggestions_only desk. All refused before additional executor calls. admission.py:402–426 requires exact admitted type, strict suggestion policy, live owners and fresh readmission equality. :519–540 enforces policy on gateway admission and dispatch. Closest r3 tests passed for certified suggestion policy and live verdict claims. Fabricated AdmissionGateway/executor construction is not access to the protected executor: the execution owner must retain its own desk. Arbitrary Python closure introspection/private mutation is explicitly inside the process trust domain (:36–41, :543–547). Authentication of remote proposer identity is not established by caller provenance.

## Q7 — provider unadmitted execution?
No route from world records directly into a provider adapter found. ExecutionDesk dispatch :523–524 reaches only its guarded executor; :469–471 freshly authorizes before calling it. Providers are status/version/digest requirements, not callables. world.py:208–214 uses canonical report executability; feasibility.py:921–938 refuses unavailable/mismatched provider. Cross-domain down-provider tests passed; boundary tests reject provider adapter/selection imports and reverse imports from other engcore layers. A separately exposed provider API would require its own access control; this module does not globally revoke arbitrary process code's access to provider packages. No real provider invocation performed.

## Publication lifetime / liveness / replay attacks
Source publication retains all generations until terminal close and proven quiescence (owners.py:392–463); early successful reads do not authorize retirement. 79-test run includes retained-spend restore tests, interruptions, source type/token rejection and close/retire behavior. Fresh probe switches a following reader to a second AccountPublication, then back: source migration refuses and reader remains refused. Closing original source also refuses. This is conservative availability behavior, not false acceptance. Following pin acquires source lease and rechecks closure (:1123, :1164, :1184–1186).

Fresh probe reconstructs Authorities from a JSON-compatible AdmissionRecord snapshot and attempts dispatch: frozen.live is false and dispatch refuses. Canonical record identity is not live capability. admission.py:593–603 accurately limits replay to self-consistency, not proof the owner ever held those records. No process-crash persistence or generalized at-most-once reservation asserted.

## Execution evidence
1. `/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python -m pytest -q -p no:cacheprovider tests/mind/test_authority_review_r3.py tests/mind/test_authority_cross_domain.py tests/mind/test_authority_lifetime.py tests/mind/test_world_boundary.py` — exit 0, 79 passed in 10.31s; focused.log.
2. `/home/dev_kaeem/forge-gen2-authority-v1/.venv/bin/python /home/dev_kaeem/br11-review/r19/F/probe.py` — exit 0, all focused assertions passed; probe.log. Both used PYTHONPATH=repo/src:repo, PYTHONDONTWRITEBYTECODE=1, cwd repo.
3. Initial rg listing attempt: NOT RUN because native WSL rg unavailable; fallback pathlib reads used. No dependency installation.

No severity/threat/repro finding entry because no reproducible contract violation was identified. Residual limits are stated above; not a universal absence-of-bugs claim. Broad FAST gate delegated to root, not claimed executed here. Repository PROGRESS intentionally untouched under review's explicit read-only scope; exact commands/results recorded here instead.
