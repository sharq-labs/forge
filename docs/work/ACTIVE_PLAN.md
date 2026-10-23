# Active Plan

Active epic: `engrt.numerical_foundations` (research program; OD-6 decided 2026-10-18; in force when branch
`feat/od6-engineering-program-epic` merges). Earlier entries below that call `battery.thevenin_1rc` the epic, list OD-6
as open, or list EXC-1 as an open exception are superseded by that decision on merge. The program's gates M1-E3 are
bound by its Cross-Domain Scientific Architecture Requirements (physics-agnostic shared structure; heat is the first
reference application).

## Current bounded task - GEN2-BR1.1 authority-bound ScientificWorld + non-bypassable admission (2026-10-22)

Development repair of GEN2-BR1's AUTHORITY_DUPLICATION_BLOCKER on `research/mind-gen2-authority-binding-v1` (base
`1202ea6c`, BR1's report commit). Pushed to `origin` at the 2026-10-23 cloud handoff for local resumption: no PR, not
merged, not certified. **Status: IN_PROGRESS** (not closed): review round 11 found MAJORs, fixed in `d5ef1e3`; round 12
(at `a96baa6`) was INTERRUPTED with no result, and its two started lenses left unverified MAJOR-class leads in
`owners.BudgetReader`. Resume index: `docs/work/BR11_LOCAL_RESUME_CHECKPOINT_2026_10_23.md`.

R12-T1 done locally (2026-10-23, WSL2, CPython 3.12.3; PROGRESS item 28): every round-12 lead reproduced at
`d40aff44`; R12-1..R12-6 confirmed and fixed in `33258438` with failing-first controls
(`tests/mind/test_authority_review_r12.py`) and mutants (17 of 18 caught; the race-only `shared_cache` recorded as
uncontrolled); dispositions in README §9. Local commits are not pushed (WSL has no GitHub access; a bundle is handed to
the Windows side).

Fresh review round 13 at `3b407ddb` did not meet the gate (Q4 YES: MAJORs F13-02 = R13-C-F1, R13-B-F1, R13-C-F2 =
R13-A-F1, critic R13-CRIT-1); all fixed in `13051154` with controls (`test_authority_review_r13.py`) and 32 mutants
each caught; gates show no new failures vs base (PROGRESS item 29).

Fresh review round 14 at `1c9fdd84` did not meet the gate (Q4 YES: a not-read-back state shorter than the observed
history was never recorded, five lenses; critic CRIT14-1, a regression of the dict-only rule); fixed in `7b4a0de8`
with controls (`test_authority_review_r14.py`) and 38 mutants each caught; gates show no new failures vs base
(PROGRESS item 30).

**R15 continuation (Codex, 2026-10-23):** recovered the clean native WSL clone at exact reviewed
`95f3869ed020b04c36c098f0c33050aa009212b6`. Round 15 is complete (15 agents), aggregate Q4 YES.
Its 25 findings are dispositioned in `docs/work/evidence/br11_local_2026_10_23/round15/threat_disposition_matrix.json`.
The repair has 33 deterministic controls plus 54 bounded generated traces (87 pass), and two existing R13 dictionary controls
in mutation proof (89 pass; 36 fail on reviewed source). 16 correctness mutants killed; one redundant guard
removal justified by an independent recovery path and its killed compound mutant. L2: 781 passed.
Repeated affected-path measurements completed. Clean gate source commit `ec4d23dc238d2e8818170a4029a010538e23af72`: L1 115 passed,
regression 279 passed; guards 1496 pass / 2 base failures; expensive subset 335 pass / 13 failures / 14 errors;
FAST 12792 pass / 67 base failures / 190 skipped. Exact failure-ID comparison: NO NEW FAILURES VS BASE.
Rescore/benchmark MATCHES; Gen1 INTACT. Complete repair/evidence batch committed locally.
**Round 16 RUNNING:** exact evidence-complete commit `b8a65bb9d02b5a18e0a8b26779773c1552204dc1`,
read-only checkout `/home/dev_kaeem/forge-r16-review`; scratch results `/home/dev_kaeem/br11-review/r16/`.
Six independent lenses, then two independent skeptics per proposed BLOCKER/MAJOR and a completeness critic.
Source/tests are identical to clean gate commit `ec4d23dc`. No source changes during review.
Six lens reports collected: 8 MAJOR aliases / 2 unique families and 6 MINOR aliases / 2 unique families; Q4 YES. Both independent skeptics reproduced the two MAJOR families; completeness critic complete. Next: failing-first and separable local repairs (canonical retained history, interrupted detached reconciliation, post-return registration); preserve the pre-capture information-loss family as OPEN pending an explicit handoff/lifetime contract decision. Local repairs: 16 new controls; 6 semantic mutants killed; L2 797 passed; regression279; FAST12808 passed/67 base failures/190 skipped at clean source68db8819. Guards/expensive/FAST exact failure IDs show NO NEW FAILURES VS BASE; rescore/benchmark MATCHES, Gen1 INTACT. Round17 RUNNING on evidence-complete committed repair98d72b2ef854012780f4222706884b911c4a2f03, read-only checkout /home/dev_kaeem/forge-r17-review. Six fresh lenses complete; one known pre-capture MAJOR family (six aliases) and one new JSON-roundtrip normalization MINOR family (D2/F2). Skeptics/critic complete. JSON parity repaired with4 failing-first cases,16 new controls and7 killed mutants; L1 201pass, L2 813pass, regression279. Guards/expensive exact base failureIDs unchanged; references MATCHES/INTACT. Clean FAST at41a763a697707db1897ee1fcbf1365495875e45b:12824passed/67basefailures/190skipped. Exact guard/expensive/FAST failureIDs add0 failures. Next: fresh Round18 on evidence-complete repair before owner-only handoff. No closure inferred from partial repairs.
BR1.1 remains NOT CLOSED. No push, PR, merge, certification, OD-3, Portfolio or Kernel implementation.

Synthetic contract fixtures only; Gen1 byte-identical (`gen1_reference --check`: INTACT). Report:
`benchmarks/mind_gen2_authority_v1/README.md`; conclusion in its §12 and in `docs/work/PROGRESS.md`.

The world is now a projection of FORGE's owners, verified against them at every admission and dispatch; admission
decides on exactly the setting an executor receives (as requested: realization uncertainty is not assessed). Independent review rounds run until 0 BLOCKER / 0 MAJOR; after BR1.1 closes or is
precisely blocked: STOP.

OWNER_DECISION_REQUIRED (BR1.1 does not decide these):
- `src/engcore/sria/campaign/budget.py` gained read-only `BudgetLedger.digest` / `.revision` (CORE_CERTIFIED,
  `assurance_admission`), and the changed-file gate marks the certified harness tests BR1.1 adds or changes
  (`tests/mind/test_authority_*.py`, `tests/mind/test_world_contract.py`, `tests/mind/test_world_failing_first.py`,
  `tests/test_sria_budget_ledger_identity.py`): hardened recertification is required before merge and was NOT RUN
  (OD-3 boundary).
- Confirm where admission verification lives: BR1.1 puts it in `engcore.mind.world.admission`, behind the execution
  side's `ExecutionDesk` (BR1 left this as an owner question).
- A hard-enclosure uncertainty form or a core decision-coverage policy: without it no current value decides a
  containment, so 9 of 21 BR1 base proposals are MISSING_INFORMATION (failed closed, nothing worked around).
- A canonical protocol owner: protocol declarations stay caller-declared, held in force by the execution side.
- Budget reservation and at-most-once execution at the execution owner (the desk reserves nothing).
- A provider status loader (`ProviderStatus.from_dict`) on the providers owner.
- Protocol level semantics across units: an action level declared in another unit executes as its conversion into
  the variable's unit, off any other spelling of that level (the variable's own, or a bound's) by conversion rounding
  (one or several ulps: 8 for 95 degF in degC), so a
  bound placed at that level decides on the converted value and can go either way; this holds whether or not the
  variable declares a level set, and an action that declares -0.0 executes -0.0 (README §4). Should bind refuse an
  action level whose conversion into the variable's unit does not round-trip bit-exactly to the action's own spelling
  (and, where the variable declares levels, is not bit-equal to the variable's own spelling, sign of zero included),
  failing closed at bind, or keep deciding on the level as executed (BR1.1 does the latter)?
- Merge requires the changed-file gate's SCIENTIFIC tier for `src/engcore/mind/world` (classification
  `scientific_shared`) and the FAST differential at the merge SHA.

Do not start the Hypothesis Portfolio, the Search Tree, Attempt Memory, the Model Critic or causal reasoning. Do not
install Ax, BoTorch, PySINDy or PySR, and do not run Battery v4. No push, merge or certification without the owner.

## Current bounded task - GEN2-BR1 ScientificWorld + Feasible ActionSpace v1 (2026-10-22)

Development research on `research/mind-gen2-scientific-world-v1` (worktree `D:/forge-gen2-world`, local, base
`da932552`, the sealed Gen1 head). It adds `engcore.mind.world`, imported by its own path. Gen1 is byte-identical.
Synthetic fixtures only. The result is AUTHORITY_DUPLICATION_BLOCKER (see `benchmarks/mind_gen2_world_v1/README.md`):
the check works, but admission is decided on world copies of owner records that nothing verifies with their owners.

STOPPED by the pre-committed stopping rule. The next step needs owner decisions, not more Mind-side rules:
- a verifiable budget ledger (`BudgetLedger` digest);
- a head-state view;
- a core coverage policy for interval uncertainty;
- where admission verification lives.

README section 6 lists the eight requirements. GEN2-BR1.1 (above) proposes answers in code to three of the four, each
for the owner to confirm: the ledger digest (an additive read-only owner change, recertification pending), the
head-state view (the run record's own head, read through `RunStateReader`), and where admission verification lives
(`engcore.mind.world.admission`, behind the execution side's `ExecutionDesk`). The coverage policy stays an owner
decision. Do not start the Hypothesis Portfolio, the Search
Tree or Attempt Memory. Do not install Ax, BoTorch, PySINDy or PySR, and do not run Battery v4. No push, merge or certification
without the owner.

## Current bounded task - BR-MIND-REPSEM-01 representation + semantic roles repair (2026-10-22)

Development-only repair on `research/mind-representation-semantics-v1` (worktree `D:/forge-repsem`, local, based on
the v1 evaluation commit `d516e681`). It adds `engcore.mind.repsem` (declared variable roles, scoped claim states,
named refusal conditions, a structured hypothesis record, role-typed binding of declared families, replayable
judgments) and leaves `engcore.mind.minimal` and every battery v1 artifact unchanged. Synthetic fixtures only; no
battery data was evaluated. Result: READY_FOR_BATTERY_V2 against the task's own criteria (see
`benchmarks/mind_repsem_v1/README.md`).

Next executable step: a battery v2 plan. It must freeze role declarations in the pack as protocol metadata, implement
the fitted-OCV declared family (P1), and state up front that P1's UNKNOWN voltage uncertainty forces refusals by
design. No push and no merge without the owner.

## Current bounded task - BR-BATT-REDISC-01 battery rediscovery pilot (2026-10-21)

Development pilot on `research/battery-rediscovery-pilot-v0` (local). The sealed run's preregistered conclusion is
LEAKAGE_INVALIDATED, from an audit false positive: a 760.006 s timestamp matched the 760 F value pattern. At the
owner's request, AMENDMENT_01 (post-seal, disclosed) fixed the regex and reran only the audit and the evaluation:
amended conclusion REPRESENTATION_BOTTLENECK. A clean confirmation would need a v0.1 plan and a fresh sealed run.
No Mind tuning, no formal run, no D5/N-1/Family-3a work.

BR-BATT-REDISC-02 (battery_rediscovery_v1, clean re-execution with scanner v1 and a preregistered representability analysis): REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY. This is not an independent replication (same data and code). No Mind upgrade was made in this task.

## Current bounded task - remaining branches and post-merge CI (2026-10-20)

Owner authorized continuing branch review and investigating Tests/Branch Policy without bypassing gates or OD3. PR180 merged with explicit archival-only approval at67585300. Twenty residual tips / fifteen maximal groups remain; nineteen tips trigger recertification. Prepare archive-only reconciliation of the seven ignored agent/configuration files from c4b9d950; do not activate their historical instructions. Review and run the changed-file gate before concrete PR approval. Investigate GitHub failure from actual job evidence: empty steps and missing log blobs currently leave root cause UNVERIFIED; obtain Annotations before prescribing a hosted-runner repair. Report: BRANCH_RECONCILIATION_CI_2026_10_20.md. No certification-sensitive implementation adoption, freeze or formal run.

## Current bounded task - preserve superseded documentation branches (2026-10-20)

Owner authorized reviewing and reconciling unmerged work, excluding preserve/* and wip/*. Preserve exact historical deltas from fix-bisect-table, evidence-v11, blind-rediscovery-benchmark-v1 and big-13-flagship-demonstrations in docs/archive/branch_deltas_2026_10_20/. Reconcile ancestry only with that explicit archive-only disposition: no superseded text is applied to live contracts, benchmark semantics or task queues. Independent review PASS; ordinary219-node gate217passed2failed, exactsamefailed nodes as pristine main. Await concrete PR approval; no green-gate claim. Scientific/certified implementation branches remain separate and subject to existing decisions/OD3.

## Current bounded task - reconcile preserved assurance history (2026-10-20)

Continue owner-authorized branch reconciliation, excluding preserve/* and wip/*. The entire assurance-performance-investigation report and its progress addition already exist byte-for-byte on current main. Reconcile ancestry while preserving the current tree and historical-source warning; read-only review PASS; normal changed-file gate217passed2failed, identical to pristine main219-node selection. Owner approved PR179; merged at8b29fc07. Do not call the gate green. No source, certification, policy or measurement changes authorized by this history reconciliation.

## Current bounded task - domain inventory integration (2026-10-20)

Owner authorized resolving branch blockers after merging approved PR176, without bypassing tests or OD3. Domain-data integration preserves historical bytes and separates archival replay from live provenance coverage. Owner selected full433-file provenance audit. Audit completed with exact per-file/source hashes;33 domain tests passed after failing-first boundary regressions and staged-identity repair. Five authored analytical metadata records correctly classified DERIVED. Independent review PASS. Full FAST completed with existing failures/errors; exact pristine-main comparison shows zero new failing/error nodes. Owner explicitly approved PR178 with the disclosed baseline results; merged at94aab1f6. No green-gate claim. Do not promote origin classifications into validation or current certification. Other certified branch merges remain subject to OD3; no freeze, formal run or Mind behavior change.


## Current bounded task - reviewed branch reconciliation (2026-10-20)

Owner approved PR176 explicitly and authorized resolving remaining branch blockers sequentially, without bypassing tests or OD3. PR176 merged at3213bb35. Exclude preserve/* and wip/*; preserve scientific contracts and byte-pinned evidence.

- [x] Verify three residual branch histories contain no new content: historical main-check entry byte-present; critical-production and multiphysics-lifecycle commits patch-equivalent. Merge their ancestry with the main tree unchanged.
- [ ] Reconcile domain-real-data archival inventory versus live coverage; retain historical bytes and fail closed for undeclared provenance.
- [ ] Reconcile other unique changes only after their targeted tests and independent review; certified/trust changes remain blocked pending applicable OD3. No formal Genesis run, freeze or candidate behavioral tuning authorized.

## Current bounded task — FAST runtime profiling (2026-10-20)

Owner authorized trying FAST acceleration in this chat. Base: remote main
`8ec97064c35144405e3eba53a4282e90f8593b1c`; branch `codex/fast-runtime-profile`.
This is developer-performance work, not scientific measurement or recertification.

- [x] Measure unchanged FAST on supported Python 3.12 in an isolated Linux checkout.
- [x] Identify dominant costs and try a bounded optimization without removing tests,
      weakening assertions, changing scientific semantics or modifying frozen artifacts.
- [x] Compare exact test outcomes and timings; retain only supported improvements.
- [x] Record commands, failures, environment and limitations in PROGRESS.

Bounded task complete: FAST n=4 measured 794.91s -> 295.49s (one sequential
before/after pair). All 12,113 original cases retain their outcomes; one added
regression passes. The same 64 failures and 176 skips remain. Scientific static
review PASS; 91 targeted tests passed. No integration-readiness claim: SCIENTIFIC,
FULL, mutation populations and hardened recertification remain NOT RUN.

Owner authorized publishing this bounded change to its branch on 2026-10-20,
before inspecting further quick performance opportunities. No merge, dependency
install or hardened recertification is part of this task. Existing scientific
work and capability maturity remain unchanged.

## Current bounded task — BUY-01 MCP UQ repair, FDA-04 / FDA-14 (2026-10-19)

Branch `fix/buy01-fda04-fda14-qmc` (local `17e2edd5`, `428993b1`; base `origin/main` `d3c9cd45`). This is a trust-lane
repair of the uncertified MCP tool, and it does not expand the active epic. Evidence: PROGRESS 2026-10-19.

- [x] Reproduce FDA-04 and FDA-14 (R-04) on `d3c9cd45`; write failing-first tests; repair the sampler, the quantile
      rule and the sigma spread units; bump the schemas to /2.
- [x] Owner: ODC-14a approved (refuse a tail below 0.5/n). ODC-04a approved, Option D (Iman–Conover re-pairing; refuse
      n <= k or lambda_min < 0.64).
- [x] ODC-14b: the interval is stated as an empirical central quantile interval at the requested mass, with no
      guaranteed or calibrated coverage; wording-guard tests added. The ODC-04a guard is labelled a design diagnostic.
- [x] Targeted tests on Python 3.11.17 and 3.12.3: 69/69 each. The changed-file gate's failure set equals pristine
      `origin/main`.
- [ ] Owner: approve push and a Draft PR (not yet authorized).
- [ ] Owner: OD-3 hardened recertification. `server.py` and both test files are certification_pinned.
- [ ] ODC-04b, deferred to its own bounded PR: move the computation into a UQ-owned module. Any new
      `src/engcore/uq/*` file is certification_pinned (`certified:predictive_representation`).

## Current bounded task — final owner-decision preflight (2026-10-18)

- [x] Analyze D1 gate dependency, D2 OD-31 census and D3 M1A issuance-refusal mismatch; preserve existing evidence and source.
- [x] Create FINAL_OWNER_DISPOSITIONS_2026_10_18.md with exact unapplied proposals, independent read-only reviews, impacts and explicit approval questions.
- [x] Owner explicitly approved D1/D2/D3 and final integration. Reviewed exact patch/preimage hashes; fresh census confirmed20same unique identities/sole M1C addition; applied only the approved patches. Application record: `.pytest-review-temp/final-integration-approved-2026-10-18/application.json`.
- [x] Final targeted29 passed with intended negative paths traced; discovery3 passed; claims175 passed; M1A/B/C124 passed; fixed bounded regression279 passed; compatibility153 passed/1 Windows symlink skip. Source indexes unchanged per executed job.
- [x] Single unchanged unified48 conservation execution:48 passed in811.21s (811.703s wall), exit0 within1200s; full source indexes unchanged.
- [x] Separate archive readback investigation reproduced frozen current-/2 refusal, positive M1C control succeeds; dependent scientific impact UNCLASSIFIED/blocking. No archive behavior change approved/applied.
- [x] Final source/report/log review complete; bounded integration PASS_WITH_EVIDENCE. Owner review may proceed. Archive-dependent claims remain blocked with UNCLASSIFIED scientific impact; OD-3/merge BLOCKED_BY_OWNER; Genesis Step0 and Phase3.5 UNVERIFIED. No commit/push/merge/certification/OD-3. Report: FINAL_SCIENTIFIC_INTEGRATION_VERIFICATION.md.

Read-only census confirms20 versus historical19, sole added M1C physical model0.1.0; realization0.2.0 is not another model. Registry full-readback refusal for frozen diffusion is preserved as a separate pre-existing compatibility/contract limitation, not repaired by the count proposal. No epic/maturity/ledger change.

## Current bounded task — P0 scientific correctness closure (2026-10-18)

Existing branch/HEAD unchanged: `fix/post-merge-remediation-2026-10-18` / `93ed64b0`.
The preceding verification's eight uncommitted files were inventoried, hashed and copied to ignored task evidence before edits.

- [x] Reproduce authority failures; independently confirm Windows WMI workaround; isolate pytest temporary paths with forward slashes.
- [x] Trace reports=None to invalid M1C realization blocking the complete domain index; identify separate replay-of-refusal VERIFIED defect.
- [x] Owner approved exact existing-capability / realization0.2.0 correction; independently reviewed and applied, no count pin or historical artifact changed.
- [x] Require stored/fresh completed bound results before replay VERIFIED; preserve schema, enums, numeric comparison, unknown uncertainty and insufficient verdicts.
- [x] Structural malformed-report/realization errors propagate as defects; expected case/input refusals remain insufficient. Direct controls8 passed.
- [x] Full affected seven claims suites plus controls:175 passed, no skips, in existing project venv; no package changes.
- [x] Owner separately approved exact global conservation policy; independent exact-patch review and git apply check completed; applied without changing rtol/atol or physical model.
- [x] Exact production kernel agrees with independent Decimal reference (normal/subnormal/huge finite); Fraction cost measured at4/512/8192 entries.
- [x] Execute48 actual-solver adversarial cases:42 passed; six net-versus-gross exchange fixture assertions failed, were independently diagnosed and corrected with the same tolerance, then6 passed. Production unchanged; all7 required mesh sizes, independent material/source energy accounting and explicit nonfinite refusal covered. No single48-pass rerun claimed.
- [x] Fixed-mesh M1C + parent pack:123 passed,1 pre-existing M1A refusal-text mismatch; all M1C tests executed. Full claims final175 passed.
- [x] Discovery imports complete and finds20; pinned19 test stays red pending OD-31. No automatic pin change.
- [x] Bounded scientific regression after authority repair:277 passed,1 original BLOCKED_WITH_EVIDENCE dependency-contract failure.
- [x] Final policy compatibility153 passed/1 Windows symlink skip; post-numerical fixed regression277 passed/1 original gate-contract failure. Independent static authority/numerical review found no remaining BLOCKER/MAJOR; final report and machine evidence recorded.

P0 bounded repairs: PASS_WITH_EVIDENCE within the final report's numerical/software limits. Branch may proceed to owner review; merge remains blocked by red gate/census/parent dispositions and unexecuted integration/recertification. Phase3.5 and formal Genesis measurement remain UNVERIFIED; existing preparation scope is unchanged. All work remains uncommitted.

No current epic/ledger stage, scientific threshold, historical bundle, certificate, commit, push, PR or OD-3 operation is authorized by this task.
Owner-approved identity/policy decisions are documented in `docs/work/proposals/P0_M1C_IDENTITY_DECISION.md` and `P0_CONSERVATION_POLICY_DECISION.md`.
Report target: `docs/work/P0_SCIENTIFIC_CORRECTNESS_CLOSURE.md`.
Earlier verification findings below are historical baseline; superseded scientific outcomes are recorded without deleting negative evidence.

## Current bounded verification — post-merge remediation (2026-10-18)

User-authorized verification of `fix/post-merge-remediation-2026-10-18`,
HEAD `93ed64b0292e9fea714ac83affb64b71488ac050`, base `337519d1`.
This task does not expand the active epic or scientific roadmap.

- [x] Confirm exact clean starting state and original 23-file inventory (8 source / 9 tests / 6 docs-proposals).
- [x] Diagnose SciPy/Pint import wedge: CPython Windows WMI; task-local fallback, no package changes.
- [x] Execute all seven exact remediation recipes and preserve original collection failures.
- [x] Apply independently reviewed import-order correction; add fresh-process regressions.
- [x] Execute corrected recipes and bounded scientific/checkpoint/semantic/compatibility checks; record failures.
- [x] Independently derive and execute source-extracted energy admission diagnostic: 1e-7 J leak rejected at4 cells, admitted at256/512 due to N² arithmetic floor.
- [x] Record owner decisions, source digests, OD-3 procedure, Phase3.5 and Genesis assessment.
- [ ] SCIENTIFIC_DESIGN_REQUIRED: conservation floor must not become permissive under refinement; no tolerance adjustment approved.
- [ ] OWNER_DECISION_REQUIRED (OD-31): invalid M1C realization lacks provided capability; resolve scientific declaration/identity before model census pin change.
- [ ] Diagnose red forward-tear fixtures and claim/report bridge + replay authority failures; do not infer governance-only.
- [ ] Owner dispositions OD-22/23/24/26/29/30/31/32/33/34 remain open as detailed in the review.
- [ ] Separately authorized final-source supported3.11/3.12 integration/OD-3 after scientific defects and red tests close.

Outcome: **BLOCKED_BY_SCIENTIFIC_CORRECTNESS**, not merge-ready, not Phase3.5 closure.
Canonical program ledger gates remain MISSING; no owner deferral, maturity promotion,
active-epic change, bundle regeneration, commit, push or PR performed.
Report: [POST_MERGE_REMEDIATION_VERIFICATION.md](POST_MERGE_REMEDIATION_VERIFICATION.md).
Durable execution metadata: [evidence/post_merge_2026_10_18.json](evidence/post_merge_2026_10_18.json).
Existing slices below retain their historical source/authorization limits; this entry records the new bounded execution.


## Active bounded slice - M1C transient nonuniform vertex FV (2026-10-18)

Branch codex/m1c-transient-fv-1d, exact M1B base
9b092d563507b0de3563c4209d42d6fc0772ea0a. Stack main -> #159 -> #160 ->
#161 -> #162 -> M1B Draft#165 -> M1C local. M1B exact SHA/ancestry/cleanliness/
nine-file inventory/bounded credential scan/whitespace checked; push completed,
draft targets codex/m1a-mesh-lineage. No earlier PR retargeted or merged.
Checkpoint#158 independent. Previous local-only M1B publication notes superseded.

- [x] Mathematical and compatibility decision before source (ef11c1da).
- [x] Fixed-mesh vertex dual FV, positive phase-constant sourced materials, BE order1 declared.
- [x] Explicit geometry/BC/source/initial/time; both-Neumann transient allowed.
- [x] Series material/contact resistance; opposite shared interior face contributions.
- [x] Sparse-only provider, exact build/context/state binding, residual/conservation refusal.
- [x] Independent static scientific architecture review PASS after corrections.
- [x] Adversarial/manufactured/refinement tests authored, all NOT RUN; DV-129..132 deferred.
- [ ] OWNER_DECISION_REQUIRED M1C-C1: model discovery pin19 ->20 compatibility/certification review.
- [ ] Owner-authorized targeted execution and all earlier DV rows; no scientific gate promotion.
- [ ] M1D adaptive window decisions/transfers/rebuild/cache-history/rollback/full history/studies.

IMPLEMENTED / UNVERIFIED / UNCERTIFIED. M1C is not M1 completion or integration-ready.
M1C_MERGE_PACKAGE.md records exact inventory, limitations and next owner decisions.

## Active bounded slice - M1B vertex-centred dual-volume state adapter (2026-10-18)

Branch codex/m1b-vertex-dual-state from exact M1A
7f8cb5dac01cd7a270ef72886b77c8cddf717d3b. Stack main -> #159 -> #160 ->
#161 -> M1A Draft PR#162 -> M1B local. M1A clean/exact SHA/ancestry/bounded
credential and artifact scan/whitespace checked, pushed, draft targets A-4.
Prior local-only M1A note below is superseded; nothing merged. Checkpoint#158 independent.

- [x] Owner direction: explicit vertex intensive state, derived midpoint dual supports.
- [x] Preimplementation architecture/compatibility decision (4fb78436).
- [x] Typed dual density/integrated placement, qualified exact-meaning linear storage.
- [x] A-3 remap on dual supports, independent both-coverages/actual-total admission.
- [x] Source bytes bound through existing KnowledgeSource; no physical evidence authority.
- [x] Lineage-bound invalidation; managed cache/history clearing; unsafe transition poison.
- [x] Adversarial/regression tests written; independent static review, NOT execution.
- [ ] Owner-authorized DV-125..128 and predecessor DV-101..124.
- [ ] M1C vertex-centred transient FV/backward Euler, explicit sourced inputs/BCs.
- [ ] Adaptive transient driver, numerical refinement/conservation studies, M1 gate.

IMPLEMENTED / UNVERIFIED / UNCERTIFIED. No transient solver, pointwise accuracy,
physical validation, certification or maturity promotion. M1B_MERGE_PACKAGE.md
records exact inventory, compatibility, remaining limits and owner decisions.

## Active bounded slice - M1A lineage-bound adaptive mesh 1D (2026-10-18)

Branch codex/m1a-mesh-lineage, exact base1f43c59eab717aa7cbfea672b948accb37f3cc50.
Stack main -> #159 -> #160 -> A-4 Draft PR#161 -> M1A local branch.
A-4 was clean/ancestry-checked/scanned and published targeting A-3 by owner instruction;
prior local-only publication note superseded. Checkpoint#158 remains independent.

- [x] Full M1/CDAR read; architecture/compatibility decision before source (cbecc2df).
- [x] Explicit issued lineage, reversible recorded bisection coarsening.
- [x] Content-addressed state transfer reusing A-3 semantics and mapper.
- [x] Actual managed cache/history clearing; stale field/receipt/source refusal.
- [x] Adversarial tests written; independent static review PASS, all tests NOT RUN.
- [x] Local Draft PR-ready package and deferred recipes DV-121..124.
- [ ] Transient nonuniform vertex-centred FV/backward-Euler conduction and sourced inputs.
- [ ] Explicit primal-interval vs vertex dual-control-volume state-placement adapter.
- [ ] Adaptive transient loop, provider/cache adapters, refinement/conservation studies.
- [ ] Owner-authorized validation, integration/certification and M1 gate decision.

IMPLEMENTED / UNVERIFIED / UNCERTIFIED. This is M1A only; M1 is not complete.
No capability promotion or arbitrary/durable lineage import. See M1A_MERGE_PACKAGE.md.

## Active repair - A-4 physics-neutral interface flux execution (2026-10-18)

Branch codex/interface-flux-execution, base A-3 4f239fa7fe705e3d8ae390a8e885302dcb07904e.
Stack: main -> semantic Draft PR #159 -> A-3 Draft PR #160 -> A-4 local branch.
A-3 was clean/scanned, pushed and opened against codex/quantity-semantics by owner
instruction. Prior local-only A-3 publication note superseded; no merge.

- [x] Preimplementation Core compatibility/architecture decision (dab92bf0).
- [x] Typed scalar planar interface transfer and executed sign/normal convention.
- [x] Neutral Dirichlet-Neumann admission; explicit thermal wrapper; tests written.
- [x] Independent scientific static review PASS, defects corrected, no execution.
- [x] Local Draft PR-ready package and DV-117..120, NOT RUN.
- [ ] Owner-authorized execution and explicit legacy WS3/interface migration.
- [ ] Independent coupled physical balance, numerical verification, validation and OD-3.

IMPLEMENTED / UNVERIFIED / UNCERTIFIED. No A-4/gate closure from code or static PASS.
Unstructured/curved/vector/moving/partial interfaces remain unsupported. Proposed next
bounded M1 work is lineage-bound 1D transfer and reversible bisection coarsening;
see A4_MERGE_PACKAGE.md for prerequisites. DV0 does not block Build-First implementation.

## Active repair - A-3 declared field kind mapping (2026-10-18)

Branch `codex/declared-field-kind-mapping` is stacked on semantic PR #159,
base `98da0c024bd59bd0b18844941eafad3f1d24d428`. It does not contain checkpoint
PR #158. Semantic branch was pushed cleanly and opened as Draft PR #159 by owner
authorization; legacy alias migration obligations and historical identities retained.

- [x] Architecture/compatibility decision committed before source implementation.
- [x] Typed cell density/integrated/intensive and declarative interface/normal contracts.
- [x] Shared declared-kind operator and Grid1D adapter; adversarial tests written.
- [x] Independent static review PASS; corrections recorded; tests NOT RUN.
- [x] A-3 local Draft PR-ready package; no automatic merge.
- [ ] Owner-authorized validation DV-113..116 and explicit consumer kind migrations.
- [ ] A-4 normal/sign execution, adaptive lineage/history, vector/tensor scope remain open.

Status IMPLEMENTED / UNVERIFIED / UNCERTIFIED; A-3 remains open pending execution
and compatibility/migration disposition. See A3_ARCHITECTURE_DECISION.md,
A3_COMPATIBILITY_MATRIX.md and A3_MERGE_PACKAGE.md. No assurance or OD-3 executed.

## Active repair - semantic compatibility A-1/A-2/A-13 (2026-10-18)

Branch `codex/quantity-semantics`, base latest fetched origin/main
`0284ae161ad957d51674ee481e47cfd43d10c5f0`, isolated semantic-contracts worktree.
Checkpoint hardening is independently published in Draft PR #158 at `02065a6d`;
its changes are not included here. Build-First: no tests/provider execution/assurance.

- [x] Phase A/B proposal and initial 39-file inventory; expanded static index covers 122 files.
- [x] Independent static design compatibility review: PASS, no HIGH/MEDIUM finding.
- [x] Bounded typed scalar implementation, adversarial tests, compatibility records (UNVERIFIED).
- [x] Independent static patch review and local PR-ready package; no tests run.
- [x] Separate A-3 declared-field-kind proposal; no mapping implementation in this slice.
- [ ] Separately authorize deferred tests; do not mark A-1/A-2/A-13 CLOSED on code alone.

See SEMANTIC_COMPATIBILITY_PROPOSAL.md and SEMANTIC_IMPACT_MATRIX.md.

## Active repair — checkpoint integrity R1–R5 (2026-10-18)

Owner-authorized bounded Build-First repair from main `0284ae161ad957d51674ee481e47cfd43d10c5f0`.
Branch `codex/checkpoint-integrity-hardening`; isolated worktree
`C:/Users/dev_kaeem/.codex/worktrees/checkpoint-integrity/phyx`.
The shared stale main checkout and its existing edits are preserved.

- [x] R1 provider-qualified snapshot payload encoding; strict same-object seal retained.
- [x] R2 failed restoration retirement across runtimes, callback/external application guards.
- [x] R3 PyBaMM physical-time and live-state-integrity admission.
- [x] R4 strict legacy orchestration build/problem admission; compatibility review note written.
- [x] R5 adversarial tests written. IMPLEMENTED / UNVERIFIED; tests NOT RUN.
- [x] Independent scientific/compatibility review: PASS (static review only); PR-ready
      package in CHECKPOINT_HARDENING_MERGE_PACKAGE.md. No push/PR/merge performed.
- [ ] Separately authorize DV-100, DV-99, then DV-101..DV-106. Full tiers, mutation,
      full assurance and OD-3 remain separately authorized operations; no automatic merge.

Contract/compatibility/limitations: [CHECKPOINT_HARDENING.md](CHECKPOINT_HARDENING.md).
This slice does not authorize implementation of A-1/A-2/A-13 or A-3 semantics.

## Integration — Codex handoff (2026-10-18)

By owner confirmation in chat, branch `integration/codex-handoff-2026-10-18` merges into `main`, in order: I-8
(`fix/engrt-v1-phase1-interop` `c68f9fc1`), Phase 1, Phase 2, Phase 3, Phase 3.5, the CDAR fixtures and OD-6, plus
[CODEX_HANDOFF.md](CODEX_HANDOFF.md). Everything lands **IMPLEMENTED / UNVERIFIED and UNCERTIFIED**; no test ran. The
"local commits only" lines of the overrides below describe how the work was built, not where it now is; OD-6 is in
force from this merge.

- [x] Merge in dependency order; conflicts resolved by hand (CODEX_HANDOFF.md section 1), including the I-8 vs
      P2-BR10 checkpoint authority (I-8's seal wins; cross-object restore refused) -- owner review.
- [ ] Owner: authorize DV-31..DV-100; OD-3 recertification of the new `main` HEAD; route the preserved, unintegrated
      `preserve/*` and battery Pass 1 branches.

## Active override — Phase 3.5: engineering foundation completion, build phase (2026-10-18)

Branch `feat/phase35-engineering-foundation-completion` (worktree `D:/forge-phase35`), on Phase 3 `7389f4b4`. Local
commits only; no test execution, push, PR, merge or certification. Deferred checks: DEFERRED_VALIDATION.md DV-87..DV-98
(all earlier DV rows preserved). Policy drafts: [PHASE_3_5_POLICY_PROPOSALS.md](PHASE_3_5_POLICY_PROPOSALS.md). Phase 4 not started.

- [x] WS1 mandatory same-problem admission for corroboration (`8a76dbe2`, review fixes `e01bc051`), tests NOT RUN; closes OD-P2-3.
- [x] WS2 electrothermal migration candidate on the runtime, NATIVE default, parity-gated (`e740f208`) -- PARTIAL until DV-88..DV-90 pass.
- [x] WS3 conjugate-interface admission and provider-pair maturity (`feb1f34e`) -- PARTIAL: real FE/CFD BLOCKED (P35-E2).
- [ ] WS4 transient 1D adaptation, conservative transfer, coarsening, triangle refinement -- BLOCKED (P35-A4/A5).
- [ ] WS5 provider-backed nonlinear PDE -- BLOCKED (P35-E1, needs OD-6).
- [ ] WS6 ALE formulation -- BLOCKED (P35-E3, needs OD-6).
- [x] OD-6 / OD-P35-2 decided 2026-10-18: active epic -> research program `engrt.numerical_foundations` (branch `feat/od6-engineering-program-epic` `a40ddc5d`, in force on merge); WS4-WS6 and real FE/CFD become program gates M1, M2, E1-E3.
- [ ] Owner: review/merge the OD-6 branch; OD-P35-1, OD-P35-3..5; regenerate two flagship bundles (DV-93); authorize deferred validation; OD-3.

## Active override — Phase 3: advanced numerical & multiphysics engine, build phase (2026-10-17)

Branch `feat/phase3-advanced-numerical-multiphysics` (worktree `D:/forge-phase3`), stacked on Phase 2 `2661b640`.
Local commits only: no push, PR, merge, certificate or test execution (owner direction). Rocks are P3-BR13..P3-BR17.
Deferred checks: [DEFERRED_VALIDATION.md](DEFERRED_VALIDATION.md) DV-65..DV-86 (Phase 1 DV-31..DV-47 and Phase 2
DV-48..DV-64 unchanged). Phase 4 not started.

- [x] P3-BR13 numerical-health vocabulary, damped Newton, chain acceptance, measure-weighted residual norm (`1d80a142`), tests NOT RUN.
- [x] P3-BR14 one IQN accelerator; bounded IQN-IMVJ with recorded history validity (`9f96c560`), tests NOT RUN.
- [x] P3-BR15 step-doubling window error indicator, recorded clocks and forced short windows, subcycling contract (`87c271ab`), tests NOT RUN.
- [x] P3-BR16 mesh validity checks and adaptation provenance (`f2df47d2`) -- PARTIAL: refinement extensions BLOCKED (EXC-1).
- [x] P3-BR17 nonlinear PDE admission contract; moving-mesh kinematics and GCL (`0a97c8a7`) -- PARTIAL: nonlinear PDE execution and ALE BLOCKED.
- [x] Read-only review: 5 MAJOR + 5 MINOR fixed (`080751eb`), 3 MINOR recorded; tests NOT RUN.
- [ ] Owner: OD-P3-1 (EXC-1 amendment: coarsening, transient non-uniform 1D, 1D grid-to-grid conservative transfer),
      OD-P3-2 (triangle/tetrahedron refinement, changing-mesh coupling), OD-P3-3 (a nonlinear PDE template + provider
      Newton adapter), OD-P3-4 (an ALE formulation), OD-P3-5 (confirm the Phase 3 infrastructure is inside policy),
      OD-P3-6 (schedule-forced windows below minimum_window), OD-P3-7 (make l2_measure / error control mandatory anywhere).
- [ ] Owner: authorize Phase 1 + 2 + 3 deferred validation; push/PR; OD-3. Phase 2 decisions OD-P2-1..OD-P2-5 still open.

## Active override — Phase 2: unified solver & multiphysics architecture, build phase (2026-10-17)

Branch `feat/phase2-unified-solver-architecture` (worktree `D:/forge-phase2`), stacked on Phase 1 `6249c2d2`. Local
commits only: no push, PR, merge, certificate or test execution (owner direction). Rocks are P2-BR8..P2-BR12. Deferred
checks: [DEFERRED_VALIDATION.md](DEFERRED_VALIDATION.md) DV-48..DV-64 (and Phase 1 DV-31..DV-47, unchanged).

- [x] P2-BR8 one declared coupling authority; steady result participants; electrothermal runtime build (`e4dec400`) -- PARTIAL: product path not migrated.
- [x] P2-BR9 unified field-transfer engine: admission table, indexed search, tet->tet conservative remap (`54ff4321`), tests NOT RUN.
- [x] P2-BR10 build- and problem-bound checkpoints; qualified conversion contract; provider/PyBaMM restore guards (`17dd89b6`), tests NOT RUN.
- [x] P2-BR11 canonical problem identity, corroboration after same-problem admission, qualified selection (`77634711`), tests NOT RUN.
- [x] P2-BR12 external-participant infrastructure (mock labels, failure classes, interface contract) (`e9d18d63`) -- PARTIAL: FE/CFD BLOCKED.
- [ ] Owner: OD-P2-1 (FE/CFD conjugate heat transfer vs active epic), OD-P2-2 (electrothermal delegation, relaxation semantics),
      OD-P2-3 (compare_providers refuses without same-problem admission), OD-P2-4 (preCICE role), OD-P2-5 (hex / mixed 3D remap).
- [ ] Owner: authorize Phase 1 + Phase 2 deferred validation; push/PR; OD-3. Phase 3 not started (waits for authorization).

## Active override — Phase 1: scientific & numerical correctness, build phase (2026-10-17)

Branch `fix/phase1-scientific-numerical-correctness` (worktree `D:/forge-phase1`), base `origin/main` `de11dffa`.
Local commits only: no push, PR, merge, certificate or test execution (owner direction). Rocks are P1-BR1..P1-BR7
(not the ERT V1 BR numbers below). Deferred checks: [DEFERRED_VALIDATION.md](DEFERRED_VALIDATION.md) DV-31..DV-47.
Every changed capability is IMPLEMENTED / UNVERIFIED; every touched pinned file is UNCERTIFIED until OD-3.

- [x] P1-BR1 coupling convergence coverage; explicit plans valid again (`a1b6a87e`), tests NOT RUN.
- [x] P1-BR2 conservative cell remap by exact intersection, 2D + structured only (`61226343`), tests NOT RUN.
- [x] P1-BR3 mapping residuals are diagnostics, never bounds (`b7a3a032`), tests NOT RUN.
- [x] P1-BR4 exact rational coupling-window boundaries (`b71eeb3e`), tests NOT RUN.
- [x] P1-BR5 typed verification evidence categories (`56cd0e01`), tests NOT RUN; mutant N60d needs OD-3 (DV-41).
- [x] P1-BR6 sparse admission, canonical digests, exact/estimated conditioning (`71085685`), tests NOT RUN.
- [x] P1-BR7 typed coupled-run outcomes in MultiphysicsAuthority (`20aa9503`), tests NOT RUN.
- [ ] Owner: authorize the Phase 1 deferred validation (DV-31..DV-47); push/PR; OD-3 recertification.
- [ ] Owner decisions recorded in PROGRESS 2026-10-17 "Phase 1" (Phase 2 not started; waits for authorization).

## Active override — Engineering Runtime V1 Big Rocks, build phase (2026-10-17)

Branch `feat/engrt-v1-big-rocks` (worktree `D:/forge-engrt-br`), stacked on `fix/engrt-v1-phase1-interop`. Local
commits only. **Build phase:** tests are written, not run, until the owner authorizes stabilization; see
[DEFERRED_VALIDATION.md](DEFERRED_VALIDATION.md). Big Rocks are runtime engineering by owner decision (no new
ledger capability).

- [x] BR1 adaptive coupling-window control (`af7ea219`), tests NOT RUN.
- [x] BR2 joint IQN-ILS coupling acceleration, Jacobi only (`35d8f557`), tests NOT RUN.
- [x] BR3 coupling numerical-error accounting derived from run records, tests NOT RUN.
- [x] BR4 opt-in splitting-error estimate by window refinement, tests NOT RUN.
- [x] BR5 opt-in concurrent participant advance in Jacobi iterations, tests NOT RUN.
- [x] BR6 coupling numerical error conditions the claims NUMERICAL channel (review fixes applied), tests NOT RUN.
- [ ] Owner, OPEN (2026-10-17: keep opt-in for now): mandatory conditioning of coupled claims (incl. electrothermal
      CouplingEvidence), capability-declared ladder coverage, and a digest link from study to coupled run (review F4, R2).
- [x] BR7 nonlinear robustness: declared method chain and parameter continuation (numerical/robust.py), tests NOT RUN.
- [x] BR8 opt-in hybr->lm root-method chain for the heater KVL, tests NOT RUN.
- [x] Owner decision (2026-10-17): tests/multiscale_reference.py stays on root_method="lm" (evidence identical); the chain stays opt-in.
- [x] BR9 multiscale: opt-in macro-window rejection on fast non-convergence, tests NOT RUN.
- [x] BR10 composition-pack templates declare window control (carried into plans), tests NOT RUN.
- [x] BR11 step-size memory for adaptive coupling windows, tests NOT RUN.
- [x] BR12 defect fix: event-aligned windows keep their own failure outcome, tests NOT RUN.
- [x] MultiphysicsAuthority rejection of explicit_completed/event_aligned windows: fixed in Phase 1 P1-BR7 (owner-directed
      2026-10-17), tests NOT RUN. Provider reporting for external participants (D5) stays as BR14 left it.
- [x] BR13 mapping extrapolation / unverified mappings are open coupling-error sources, tests NOT RUN.
- [x] The coupling error budget's round-trip relative_bound: fixed in Phase 1 P1-BR3 (owner-directed 2026-10-17), tests
      NOT RUN.
- [x] BR14 defect fix: coupled nodes may not run unreported external providers, tests NOT RUN.
- [x] BR15 fallback solver routes start at their own refinement level (F-5), tests NOT RUN.
- [x] BR16 QR filtering of near-dependent IQN-ILS secant pairs, tests NOT RUN.
- [x] BR17 stagnation detection for implicit coupling windows, tests NOT RUN.
- [x] BR18 opt-in under-relaxation of the electrothermal fixed point, tests NOT RUN.
- [x] BR19 adaptive resolution (mesh control slice 1) under EXC-1, tests NOT RUN (DV-27 is the EXC-1 exit gate).
- [x] BR20 1D local mesh adaptation kernel (mesh control slice 2) under EXC-1 A1, tests NOT RUN (DV-28).
- [x] BR21 non-uniform steady 1D conduction solver driven by adapt_grid (mesh control slice 3) under EXC-1 A2, tests NOT RUN (DV-29).
- [x] BR22 non-uniform path declared as model + realization (mesh control slice 4) under EXC-1 A3, tests NOT RUN (DV-30); test_core_guards.py UNCERTIFIED.
- [ ] Owner: wiring adaptive resolution into uq_studies (changes which run carries a claim's evidence); a claims-layer CapabilityDeclaration for the steady path; sourced validity conditions; a transient non-uniform solver.
- [ ] Owner: authorize the deferred validation (DV-1..DV-7); push/PR; OD-3.

## Active override — Engineering Runtime V1, Phase 1: interoperability defects (2026-10-17)

Branch `fix/engrt-v1-phase1-interop` (worktree `D:/forge-engrt-p1`), base `origin/main` `de7527fd`, committed
locally as `04b12344` (owner direction). No push, PR, merge, certificate or hardened run without the owner. Details: PROGRESS, 2026-10-17
"Engineering Runtime V1, Phase 1".

- [x] Orchestration checkpoints bound to their solver; fallback never resumes another solver's or a failed attempt's
      state; unbound resume refused.
- [x] SUM fan-in into an offset-scale port refused (it was unit-dependent).
- [x] Union-bound coverage and spread-unit widths in fan-in and relaxation.
- [x] `ExternalSolverParticipant` checkpoints sealed to the issuing participant and provider build.
- [x] Scientific review passes 1-3 fixed; FAST diffed against the pristine baseline (no new failures beyond the
      `tree.clean` check of the uncommitted tree); real-ngspice electrothermal integration 357 passed.
- [ ] Owner: push/PR decision; OD-3 recertification (pinned files touched); policy decisions on qualification
      gating and provider-build binding for `CallbackParticipant` adapters.
- [x] Bind provider build + token digest into `coupling/adapters.py::provider_participant` and the PyBaMM coupling
      adapter checkpoints. Done twice, independently: I-8 (`fix/engrt-v1-callback-checkpoint-identity`, `1439b470`,
      `28ff37dc`, PR #155: `CheckpointSeal`, same-object issue, record identity, recomputed digest) and Phase 2
      P2-BR10 (`17dd89b6`: observed-build drift refusal, build tag in the record). Integrated 2026-10-18
      (`integration/codex-handoff-2026-10-18`): I-8's seal is the restore authority; P2-BR10's drift refusal and
      build tag are kept; a checkpoint of another participant object is refused (stricter than P2-BR10's
      cross-object restore with a build pin). Tests NOT RUN (DV-55, I-8 gates); needs OD-3 (`external.py`).

## Active override — Open problems pass (2026-10-16)

Branch `fix/open-problems-2026-10-16` (worktree `D:/forge-open-problems`), base `origin/main` `36306da5`, merged with `062e1153`; pushed for a PR.
Details and exact commands: PROGRESS, 2026-10-16 "Open problems pass".

- [x] Landing-pass review MINORs: empty/forged UQ budget, NOT_ASSESSABLE gap label (and the `assess_claim` KeyError
      it hid), declared any-of rating composition, three hostile ownership inventories.
- [x] Windows `snapshot` link count (`st_nlink` 0 refused every seed) and junctions; one UTF-8 test read.
- [x] Scientific review: first pass CHANGES REQUIRED, fixed; second pass PASS (N-4, N-5 LOW recorded).
- [x] Linux FAST on the committed tree: only the two OD-3 certificate failures. Windows FAST: 0 new failures, 29 fewer.
- [ ] Owner: review/merge of the PR; OD-3 recertification (touched pinned files; `main` already needs it); CI
      billing; `authority_result_id` binding and any-of enforcement are design decisions.

## Active override — Battery 1RC identifiability (2026-10-14)

Branch `feat/battery-1rc-identifiability` (worktree `D:/forge-battery-ident`), stacked on the closure branch. Local only.

- [x] WP1: NASA independent review, SOUND_WITH_CAVEATS (immutable; digests pinned).
- [x] WP2: dataset qualification (LG HG2 used; Kirkaldy 2024 is the cross-cell candidate, not acquired).
- [x] WP3/4: preregistered LG HG2 experiment: IDENTIFIABLE; outcome MODEL_REJECTED (marginal constant-current FAIL).
- [x] WP5: ledger calibration PASS (scoped); stage FUNCTIONAL; NO-GO for EVIDENCE_BACKED or claims.
- [ ] Owner: the Kirkaldy 2024 download (cross-cell), Type B admissibility, and one recertification of the merged
      battery + G0/A1 source.

## Active override — Battery 1RC scientific closure (2026-10-14)

Branch `feat/battery-1rc-scientific-closure` (worktree `D:/forge-battery-1rc`), base `origin/main` `e193e573`. Local
only: no push, PR, merge or recertification without the owner. Evidence package:
[benchmarks/battery_1rc_closure/README.md](../../benchmarks/battery_1rc_closure/README.md).

- [x] Rock A: `battery.cell.thevenin_1rc` execution route with replay (ledger execution and provenance_replay PASS).
- [x] Rock B: NASA PCoE FY08Q4 archive receipted (owner-approved download); B0005, B0006 and B0007 ingested, B0018
      refused for a NaN; preregistration v2 (real_data PASS).
- [x] Rock C: calibration ran and is NOT_IDENTIFIABLE (calibration gate MISSING; the required protocol is specified).
- [x] Rock D: held-out comparison opened once. Within-cell, 1RC passes and Rint fails; cross-cell, both fail; 1RC is
      better in every set (benchmark_metrics PASS, independent_validation MISSING).
- [x] Rock E: measurement UNKNOWN; parameter band not admissible; model form dominant and never zero.
- [x] Rock F: the ledger computes FUNCTIONAL; claims and domain-pack integration not justified.
- [ ] Owner: recertification (new model definition under engcore.domains plus test edits), and a decision on the new
      measurement campaign (OCV characterization, pulses at >= 1 Hz) that calibration requires.

## Active override — G0/A1 final closure (2026-10-14)

Same local branch `integration/g0-a1-unblock`. Report: [G0_A1_FINAL_CLOSURE.md](G0_A1_FINAL_CLOSURE.md). Nothing pushed.

- [x] Integration integrity: exact ancestry; docs-only differences are outside every certified area.
- [x] BR-15 hostile confirmation: C1-C3 plus two confirmation rounds fixed with reproducers. Static loader completeness
      is UNRESOLVED (declared); runtime-injected objects are NOT_VERIFIED.
- [x] Genesis-lite v0.2 (`878e6812`): D1-D7, the pilot screen defect and record identity fixed; pilot 1,560 runs, 0 invalid.
- [x] Escrow: same-account exploit measured; SECURITY_BOUNDARY_NOT_PROVEN; OD-20 requirements written.
- [x] OD-6 package prepared (Option C recommended; nothing applied).
- [ ] Owner: OD-3, OD-19 (v0.2), OD-20, OD-8, OD-18, OD-6, OD-1. BR-17/BR-18 stay closed until A1 PASS.

## Superseded override — G0/A1 unblocking sprint (2026-10-14)

Local integration branch `integration/g0-a1-unblock` (worktree `D:/forge-g0a1`) = `origin/main` `e193e573` + BR-15 +
BR-16. Nothing is pushed or merged to `main`. Report: [G0_A1_UNBLOCKING.md](G0_A1_UNBLOCKING.md).

- [x] G0 code gaps with reproducers: F-9 (restored stop-review outcome), F-7 (CI V4 shards vs checkout).
- [x] Escrow leak: heap-scan and stack-walk attacks reproduced; isolated proposer process (same-account, NOT_PROVEN).
- [x] Genesis-lite v0.1: P-1 root cause, joint-credit contract, new identity; v0 preserved.
- [x] Genesis-lite v0.1 Tier-1 cost pilot with isolated proposers: 1,560 runs, 0 invalid, 374.6 s (MEASURED);
      formal baseline tier 31,200 runs ≈ 6,451 s (ESTIMATE). Preregistration `94efff08…`, FREEZE_READY.
- [ ] Owner: OD-1 governance (plan or visibility for branch protection; disable squash/rebase merges); push the
      candidate so CI exercises the F-7 workflow step (not yet observed on GitHub).
- [ ] Owner: OD-3 recertification of this integration HEAD; OD-8 evaluator; OD-18 budget; OD-19 v0.1 identity;
      OD-20 escrow deployment; OD-6 active epic (exception or ledger change). BR-17/BR-18 stay closed until then.

## Superseded override — BR-15 authority boundary & certification closure (2026-10-14)

Branch `fix/br15-authority-closure`, base `origin/main` `e193e573`. No push, PR, merge, settings change or
recertification without the owner. Report: [BR15_AUTHORITY_CLOSURE.md](BR15_AUTHORITY_CLOSURE.md).

- [x] Post-merge truth: `main` certificate FAILS (PR #142 changed two certified harness files); #140 merge clean.
- [x] Independent review of 659da048, 313bbf1e, 05522b59 (ACCEPT) and f869a737 (nested-summary defect, fixed).
- [x] Certified-imports-uncertified gap: derived closure of every certified module, +71 pinned files, one declared
      non-authority edge; red reproducer `dc26175d`, fix `6d62e5cf`, `a49e8d12`, `01073787`; review ACCEPT.
- [ ] Owner: hardened recertification (OD-3) of the intended HEAD — BR-15 cannot PASS without it.
- [ ] Owner: disable squash/rebase merges; branch protection needs GitHub Pro or a public repository (HTTP 403).
- [ ] Next bounded tasks (not started): CI V4 workspace vs `actions/checkout` `config.worktree` (F-7); keyed
      campaign records / restored `stop_review_outcome` (F-9). BR-16 is not started.

Status: PARTIALLY_CLOSED — BLOCKED_OWNER_RECERTIFICATION, BLOCKED_OWNER_GOVERNANCE.

## Superseded override — BR-16 Genesis-lite v0 preparation (2026-10-14)

Branch `feat/br16-genesis-lite-benchmark` (worktree `D:/forge-br16`), base `origin/main` `e193e573`. This is A1
preparation only: no certified file was touched and no Mind capability was added. Report:
[GENESIS_LITE_V0.md](../discovery/GENESIS_LITE_V0.md). No push, PR or merge without the owner.

- [x] Benchmark layer over `engcore.blindfold`: presentations (renamed, paraphrased, trap), equal-budget arms,
      reveal step, separately implemented evaluator, leakage tests (Genesis F1–F8).
- [x] Preregistration frozen for the pilot (`f99fcfbd…`); two review rounds, every finding fixed.
- [x] Tier-1 cost pilot: 960 runs, 0 invalid, 85 s (MEASURED); formal baseline tier ≈ 1,185 s (ESTIMATE).
- [ ] Owner: OD-3/G0 exit, OD-8 evaluator, OD-18 budget, OD-19 v0.1 identity (pilot finding P-1), OD-20 escrow
      deployment (renumbered: open PR #130 uses OD-15..17). Formal ≥20-seed runs wait for all of these.

Status: PILOT_COMPLETE · BLOCKED_OWNER_APPROVAL (not GENESIS_A1_PASS).

## Superseded override — hostile remediation round 1 (2026-10-13)

The current user scope is F1–F8 plus scanner/genesis/empty-UQ closure, with no
push, PR, merge or Mind work. Branch `fix/hostile-review-p0-p1`, clean worktree
`D:/forge-hostile-remediation`, base `5d73e8f5118aa845f1957decc5aae986e72476a9`.
This bounded task supersedes the older executable queue below for this branch.

- [x] Verify current origin/main and create isolated worktree.
- [x] Complete phase-0 reproduction before changing production code (WSL Ubuntu, 3.11/3.12 venvs).
- [x] Implement F1, F4, F2/scanner, F5, F6, F7, empty-UQ and F8 repairs (see PROGRESS, 2026-10-13/14).
- [x] Run targeted/adversarial/mutation checks and independent scientific review (eight passes).
- [x] Run supported 3.11/3.12 tiers and exact failure attribution (no REAL_REGRESSION).
- [x] Hardened recertification: SOURCE_PASS at 05522b59, certificate child b1eea81b, LOCAL_ASSURANCE: PASS.
- [x] Merged to `main` as PR #140 (623149f3) after resolving a docs-only PROGRESS conflict.
- [x] Confirm the restored CI triggers ran on `main`: they did, on push of `e193e573` (PR #142), 2026-10-14
      (Tests run 38544091505, Branch Policy run 38544091368). Results, classified 2026-10-15 in PROGRESS:
      FAST 3.11 / 3.12 and SCIENTIFIC fail only `test_the_certificate_describes_this_tree` (certificate does not
      bind `main`: OD-3); Branch Policy fails on the rulesets 403 (OD-1); `reproduce` (Docker) has 161
      environment failures (no `.git` in the image, ngspice-39 exit status) whose fix touches certified
      `tests.yml` (OD-3); `mutations` hit the 6 h job limit (cancelled).
- [ ] Independent review of 659da048, 313bbf1e, 05522b59 (mutation-proven, not yet reviewed).
- [ ] Owner decisions: the certified-imports-uncertified scope gap (PROGRESS, eighth review); host
      branch protection (no required status checks; not re-verified this session).

Status: implemented, recertified (certificate child b1eea81b) and merged to `main` as
PR #140 (623149f3, tree identical to the reviewed branch tip 52bf55d3).
Evidence: PROGRESS.md and `~/forge-hostile-evidence/` in WSL. Historical
phase-0 blocker report: [HOSTILE_REMEDIATION_ROUND1.md](HOSTILE_REMEDIATION_ROUND1.md).

**The only executable queue.** Scope (Master Plan §1): this file owns only "what work is active right now?". It may not
override Genesis science, Completion maturity rules, Performance measurement semantics or `CLAUDE.md` repository
constraints; execution authority does not imply semantic authority outside its scope. Strategy: `docs/project/FORGE_MASTER_PLAN.md` Part I. Track A science:
`docs/discovery/FORGE_GENESIS.md`. Maturity: `docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md`. History up to
2026-10-10 (BIG 14 queue, Big Rocks program, Local Assurance passes 2–13): `docs/work/archive/ACTIVE_PLAN_HISTORY_TO_2026-10-10.md`
— not a queue. Last consolidated: 2026-10-11.

## Objective

Owner-requested repair slice (2026-10-13), `codex/repair-scientific-boundaries`,
updated base `5d73e8f5`: empty UQ budgets, NOT_ASSESSABLE applicability compilation,
and the Discovery read/write deadline. The latest main already owns benchmark
output isolation and the additive challenge outcome summary; preserve those
implementations. Exit: adversarial tests, repository gate results with failures
recorded, independent scientific review. No certificate regeneration (OD-3).

Implementation complete at `cf0f31f1`; scientific review PASS. Committed-tree
regression: 256 passed. FAST: 10047 passed / 1 failed; SCIENTIFIC: 10623 passed /
3 failed; their failure union matches pristine `5d73e8f5` (certificate and two
historical benchmark gates). Freeze checks pass on the committed tree. Integration
remains blocked by these red gates; this slice does not declare G0 PASS or change
scientific maturity. Exact commands and failures are in PROGRESS.

Prove a trustworthy, measurable scientific reasoning loop. Order: **G0** Trust lane → **A1** Genesis-lite measurement →
**A2** Minimal Mind → **B1** narrow real demo. One Trust architecture, one Mind; no second authority.

## Verified state (2026-10-13; re-check before relying on it)

Checked this date from git, `gh api` (read-only) and `core_certificate.py --verify`; details in
`docs/audits/REMEDIATION_2026-10-13.md`.

- `origin/main` = `c4e05ee6` ("Merge test-loop optimization and cleanup", 2026-10-12). It was pushed to `main`
  directly, not merged through a PR. It contains PR #132 (engineering program, `305928f9`), #129, #128, #126, #123
  and #117.
- The hardened certificate binds `39d43456` (`fix/trust-repair-pass1`, recertified in `795042e1`), an ancestor of
  `main`, **not** `main`: `--verify` FAILS with 14 changed certified files in 4 areas (certification_control, harness,
  inference_admission, runtime_dependencies), changed by 13 commits between 2026-10-09 and 2026-10-12. The certificate
  is a valid record of `39d43456` only. Status: BLOCKED_OWNER_RECERTIFICATION (OD-3).
- `main` is unprotected (`protected: false`); protection and ruleset endpoints return 403 (private repo, free User
  plan); squash and rebase merges are enabled, contrary to `docs/assurance/BRANCH_PROTECTION.md`. Every workflow is
  `workflow_dispatch`-only, so nothing runs on a PR or a push (OD-1).
- Open PRs: #131 and #130 (docs, conflicting), stale #107, #39, #24.
- Local branch `fix/remediation-2026-10-12` (worktree `D:/forge-remed`, uncommitted, not pushed): remediation of the
  2026-10-13 owner findings; it adds `execution/sweep.py` to the recertification scope.

Historical snapshot, 2026-10-12 (superseded above; kept for the record):

- `main` = `2d0fa6c3`. Since `4634eba` it also carries #128 (planning consolidation), #129 (test-suite runtime),
  #126 (authority ledger, real escrow, battery blind readiness `NOT_READY`), #123 (Trust Repair Pass 1: R3-01, R3-02)
  and #117 (NASA PCoE raw ingestion). Together with #124 (Big Rocks foundations) and #125 (Roadmap V2 R1–R8) these are
  built, **not certified and not qualified**.
- The hardened certificate (`certification/current_core_v2.json`, the owner's 2026-10-09 recertification carried by
  #123) binds `39d43456` (the #123 tree), **not** `main`. FAST on each landing tree (PROGRESS 2026-10-12, CPython 3.12,
  shallow clone) had 14 failures, identical to unmodified `main` `de36168e` in the same environment (certificate,
  freeze v1/v3/v4 manifests, batch56 r65, two mutation-workspace tests); UNCLASSIFIED. FAST on `2d0fa6c3` itself:
  **NOT RUN** (its tree differs from the last FAST tree `bfccb351` by one PROGRESS entry).
- GitHub rulesets: the REST API returns 403 (private repository on a free plan). No merge gate is enforced remotely.
- Open PRs: #107 self-hosted CI runner, #39 (draft) and #24 (base `claude/core-v2-hybrid-uq`): all BLOCKED in the
  2026-10-12 landing pass (OD-11, OD-21).
- Capability ledger (computed): `thermal.nafems_t3` EVIDENCE_BACKED; `battery.thevenin_1rc` FUNCTIONAL (no longer the
  epic after OD-6; the research program `engrt.numerical_foundations` is); nothing is PRODUCTION_READY.
- Negative results stand: four BIG 13 flagships `insufficient_evidence`; Kirkaldy fade NOT MET; LG M50 DFN NOT MET.
  Local-only, not on the remote: Battery Practical Pass 1 `7e923e75` (WEAKLY_IDENTIFIABLE). Trust Repair Pass 1
  `803946af` is on `main` through #123.

## Current gate: G0 — Trust lane

| Field | Value |
|---|---|
| Start condition | Now. |
| Window | OWNER_DECISION_REQUIRED (OD-7). |
| Exit gate | The certificate binds the intended `main` HEAD, **or** every unresolved failure is classified with evidence and no `SCIENTIFIC_CORRECTNESS` or `UNCLASSIFIED` item remains open. |
| Circuit breaker | Window expired → Master Plan §5.2: classify (unclassified = blocking), preserve the red result, document here, then fix / isolate / ask. Never loosen a gate. |
| Outcomes | PASS · FAIL · BLOCKED_WITH_EVIDENCE · DEFERRED_BY_OWNER |

Next actions (agent-executable now):

1. Run the FAST tier on the intended certification HEAD selected by OD-3, normally the post-merge `main` HEAD, in a
   supported environment (3.11 or 3.12); record exact failures in PROGRESS. Compare failures against the previously
   recorded 14-test drift set only where still applicable; the historical drift set is not current truth.
2. Classify every failure as `SCIENTIFIC_CORRECTNESS`, `GOVERNANCE_ONLY` or `UNCLASSIFIED` (Master Plan §5.2).
   `GOVERNANCE_ONLY` needs the complete six-question evidence record; anything less stays `UNCLASSIFIED` and blocking.
3. DONE 2026-10-12: PR #123 landed by merge commit after the `CLAUDE.md` gates and `forge-scientific-review` (PASS).
   The review's open LOWs: a REGISTRY_CHANGED bundle result carries the stored verdict without re-deriving it
   (`claims/replay/bundle.py`); `mcp/foundations.py` catches bare `Exception`.

Owner-run: hardened recertification (it writes the certificate); merges (OD-3, OD-4).

## Track A — Discovery credibility

**A1 Genesis-lite measurement** (Genesis §18 Step 1, on the existing `engcore.blindfold`)

| Field | Value |
|---|---|
| Start condition | Preparation now, limited to benchmark, governance, measurement, stabilization or evaluation infrastructure as the Completion Policy allows for A1 (documents, specifications, a pilot cost measurement; no certified file touched; no new scientific capability). The preregistration freeze and the formal ≥20-seed baseline runs start when G0 exits (PASS, or `GOVERNANCE_ONLY` blockers isolated with complete evidence records). |
| Window | OWNER_DECISION_REQUIRED (OD-7). |
| Exit gate | Genesis Step 1 gate: frozen preregistration digest, frozen baseline set (Genesis §10.5), baseline distributions over ≥20 seeds, owner-approved compute estimate (Genesis §10.6). |
| Circuit breaker | Window expired → record what was measured as smoke-scope only and ask the owner. No maturity claim. |
| Outcomes | PASS · FAIL · BLOCKED_WITH_EVIDENCE · DEFERRED_BY_OWNER |

Next actions: draft the Genesis-lite preregistration (task classes, scoring, baselines, leakage-control status
including the escrow's `SECURITY_BOUNDARY_NOT_PROVEN` label); measure per-run cost at the 10-run rung; write the compute
estimate.

**A2 Minimal Mind** (Genesis Step 2). Start: A1 PASS **and** the Completion Policy condition — the active epic formally
changed (OD-6) or a complete, owner-approved, unexpired narrowly scoped exception. Neither exists today. Window: OWNER_DECISION_REQUIRED. Exit: lift over the strongest
applicable frozen baseline with confidence intervals, calibrated predictions scored by a proper scoring rule, LLM-ablation
arm reported. Reuse owners from `docs/architecture/discovery_authority_map.md`; new Mind code must justify why an
existing owner cannot serve.

## Track B — Narrow real demo

**B1 Infeasible-specification refusal and correction** (candidate: drone; OD-13)

| Field | Value |
|---|---|
| Start condition | Preparatory engineering when A2 starts. The demo itself runs only after the A2 gate PASSES. |
| Window | OWNER_DECISION_REQUIRED (OD-7). |
| Exit gate | The user's infeasible requirement is refused and the binding physical constraint is named; a corrected admissible specification is executed through real providers; uncertainty and applicability are reported; the evidence bundle replays; a scientific review is clean. |
| Circuit breaker | Window expired → the existing Trust-only refusal behavior may be recorded or demonstrated separately, explicitly labelled as NOT a B1 completion and NOT evidence of Minimal Mind / Genesis capability, with no maturity change and no bypass of the A2 PASS gate; otherwise BLOCKED_WITH_EVIDENCE. |
| Outcomes | PASS · FAIL · BLOCKED_WITH_EVIDENCE · DEFERRED_BY_OWNER |

Substrate: `engcore.systems.products.drone_coupled` (steady algebraic hover chain; every coefficient a declared input;
uncertainty UNKNOWN) through MCP `run_product_screening(..., screening="coupled_hover")`. Missing: admitted component
data with provenance, one external validation route, quantified uncertainty. Preparation uses already-built
capabilities only; a new capability foundation for the demo (model, provider adapter, synthesis engine) follows the same
Completion Policy rule as A2. Rules: a correction is a PROPOSED
hypothesis until the Trust Layer admits it; the demo changes no maturity stage; it never substitutes for A1/A2 results.

## Not now

Everything in Master Plan §4 NEXT, LATER and DEFERRED. In particular: no new providers without a named benchmark, no
product depth beyond B1, no viewer/assembly/motion work, no GPU/HPC orchestration, no fusion, biomedical or
therapeutic work.

## OWNER_DECISION_REQUIRED

| ID | Decision | Facts |
|---|---|---|
| OD-1 | Merge-gate enforcement: make the repository public, upgrade the plan, or formally accept local SHA-bound assurance as the only merge control. | Rulesets API 403; red gates cannot block merges. |
| OD-2 | Supported Python policy. | `requires-python >=3.11`; CI 3.11/3.12; local runs on 3.13 and 3.14. |
| OD-3 | Recertification: which HEAD, and when (owner-run). | Certificate binds `39d43456`, not `main` `2d0fa6c3`; #126, #123, #117 and #129 all touch certified scope and landed unrecertified. |
| OD-4 | RESOLVED 2026-10-12 (owner direction: merge the open PRs that pass every gate). PR #123 lands by a merge commit (no rebase); it closes R3-01/R3-02 only. | Its certificate binds `39d43456` (the PR tree), not the merged `main`; recertification stays OD-3. |
| OD-5 | RESOLVED 2026-10-12 (owner direction: merge the open PRs that pass every gate). PR #126 lands as one PR; it creates no new scientific capability stage and changes no maturity. | +8,043 lines; new `engcore.authority`; real escrow is relevant to Genesis leakage controls. Not recertified (OD-3). |
| OD-6 | DECIDED 2026-10-18 (owner, in session): the active epic becomes the research program `engrt.numerical_foundations` ([contract](../project/ENGINEERING_FOUNDATIONS_PROGRAM.md)); in force when the branch `feat/od6-engineering-program-epic` is reviewed and merged. Gates DV0, M1, M2, E1, E2, E3; build-first. Battery stays tracked at FUNCTIONAL; Genesis A2 still needs an epic change or an exception; EXC-1 is superseded on merge. | Pinned by the ledger, `tests/test_capability_completion.py` and the PR template (CONTRACT_PIN: a change needs its own reviewed PR). Blocks A2. No blanket Track A/B exemption exists (Completion Policy, anti-loophole rule). |
| OD-7 | Timebox windows for G0, A1, A2, B1. | None set; no dates invented here. |
| OD-8 | External evaluator for Genesis hidden tasks: name a person or group, or fix a selection process and deadline. | Required before the A1 freeze names its held-out protocol, and before Genesis Step 6. |
| OD-9 | RESOLVED. PR #128 supersedes PR #127 and contains Genesis plus the reviewed planning consolidation. PR #127 was closed without merge; its branch remains preserved. | PR #127 existed as the standalone Genesis document. |
| OD-10 | Publish or record the local-only commit `7e923e75`. (`803946af` is on `main` via #123.) | Not verifiable from the remote. |
| OD-11 | Branch and PR hygiene: close, rebuild or land #107, #39, #24. | About 119 remote branches. #107 (237 behind): certificate conflict between two owner certificates, and it rewrites the CI control-plane workflows and adds self-hosted runners with secrets. #39 / #24 (1,500+ behind) edit frozen Core; see OD-21. |
| OD-12 | Confirm the control-plane budget signal (Master Plan §5.3). | Proposed: ~20 % warning plus a two-checkpoint no-progress signal. |
| OD-13 | Confirm the B1 demo system. | Drone recommended: the only executable product chain today. |
| OD-14 | LANDED as #129 (`de36168e`); recertification still OD-3. Was: branch `perf/test-suite-runtime`: land it (needs the OD-3 recertification: it touches `certified:harness`, `inference_admission`, `certification_control`), and decide whether to add V4 mutation entries for the admission-record memo (changes the certified population count of 680). | Owner-requested. FAST 992 s -> 476 s, SCIENTIFIC 1448 s -> 1024 s, same failure sets (PROGRESS 2026-10-12). Review F1–F4 fixed; the memo's three mutants are killed by `tests/inference/test_admission_record_memo.py` today, outside the certified population. |
| OD-15 | CI policy conflict: `CLAUDE.md` § CI policy says PRs are classified and tested automatically and pushes to `main` rerun checks; every workflow has been `workflow_dispatch`-only since `c19d3177` (2026-10-06). Align one with the other. | Last automatic `main` runs 2026-09-28, both failed. MV-10 drift went unnoticed for a month. |
| OD-16 | Freeze v4 API surface is Python-version-bound: it records methods inherited from builtins, so it verifies only on <= 3.12. Exclude inherited builtin members (a surface-version decision) or declare 3.12 the certification interpreter (with OD-2). | PROGRESS 2026-10-12 G0 evidence: 106 added + 29 changed entries on 3.13, zero Forge-defined. |
| OD-17 | Benchmark rounds pinning a digest of live `src/engcore/scientific` (`model_measurement_validation`, `empirical_validation`): re-pin, or bind the "changed nothing" claim to the round's own commit. | Broken since PR #21 (2026-09-12); the MV test rewrites committed `SAFETY_GATES.json`. |
| OD-18 | Approve the Genesis-lite formal compute budget. | Baselines: 15,120 campaign runs ≈ 1,185 s ESTIMATED from the BR-16 pilot; Mind/LLM arms UNMEASURED. |
| OD-19 | Approve Genesis-lite v0.1 before any formal run. | Pilot finding P-1: the floor arm `always_law` dominates the discoverable cell (0.70 vs 0.27), so the lift bar must be the strongest non-adversarial arm, with no loss allowed in control cells. Optional: PySR/BoTorch, a full-grammar enumerator, a distinguishable-rival kind (certified change). |
| OD-20 | Choose the escrow deployment for formal runs. | The in-process escrow leaks (attack test `test_l2_in_process…`); formal runs need the isolated escrow (isolation demo). |
| OD-21 | `ScientificResult.is_usable`: keep "converged and no failed check" (validity excluded), or require every declared model IN_DOMAIN as #39 / #24 propose. | `docs/assurance/CORE_SEMANTIC_INVARIANTS.md` records the exclusion as deliberate and a test pins the 6×4 truth table; on `main`, OUTSIDE_VALIDATED_DOMAIN and UNKNOWN validity are `is_usable`. A scientific-design decision on frozen Core, not a merge fix. #24's UQ refusals already exist on `main` (different messages). |
| OD-22 | Window-control step-size memory: `tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable` expects 8 subdivisions without memory over 2 s; the runtime with Phase 1 BR4 exact rational windows makes 7. Decide which behaviour is specified, then fix the code or the test. **2026-10-18 remediation: an exact-rational replay (`docs/work/proposals/od22_replay.py`, re-derived independently by a reviewer) gives 7 without memory and 4 with growth 2: the last window [7/4, 2] is cut to 1/4 s by the horizon and never fails, which `plan.py` ("Events and input-change instants still cut windows") covers. Recommended: apply `docs/work/proposals/OD22_window_control_subdivisions.patch` (test 8 -> 7). Not applied.** | Found 2026-10-18 solver audit, after the `min()` fix (`cf74cf1c`) let the suite run. BR1/BR11/BR17 and BR4 were built without running each other's tests. |
| OD-23 | Electrothermal native loop relaxation: BR18 / WS2 added `FixedPointCouplingPlan.relaxation_factor` to `systems/electrothermal/coupled.py`; `tests/test_electrothermal_vertical.py::test_l3_no_relaxation_appears_anywhere_in_the_module` pins fail condition §12.10 (relaxation is a separate decision, not a knob in that module) and the module docstring still says there is no relaxation. Remove the knob (relaxation lives in `MultiphysicsRuntime` only) or amend §12.10, the test and the docstring. | Not chosen by the builder (CLAUDE.md: conflicts are recorded, not resolved silently). |
| OD-24 | Self-loop coupling edges: `tests/test_phase1_coupling_convergence_coverage.py::test_a_self_loop_is_a_lagged_edge` (Phase 1 BR1) expects an edge between two ports of one participant to be a lagged edge; `scientific/multiphysics/graph.py::_validate_edges` (older rule) refuses it as internal physics. Keep the refusal and drop the test, or admit self-loops as lagged edges. | Graph rule predates BR1; the BR1 test never ran. |
| OD-25 | GitHub Actions has started no job since 2026-10-15 ("recent account payments have failed or your spending limit needs to be increased"); 15 PRs and 209 non-merge commits (+12.9k lines in `src`) landed on `main` with no CI. Restore billing, use a self-hosted runner, or make local assurance the recorded merge control (with OD-1 / OD-15). | Read from the GitHub API 2026-10-18: last executed `main` run 2026-10-14 (`e193e573`, failed); `main` is unprotected. |
| OD-26 | `tests/test_phase2_review_regressions.py::test_a_redundant_forward_tear_is_refused` has no valid fixture in the electrothermal series pack: `test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal` enumerates every tear set of 1-3 stages and none reaches `runtime_equivalent`'s forward-tear refusal (mixed dimensions are refused by the plan; single-dimension sets that break every cycle are all backward). Delete the test, mark it strict-xfail citing the enumeration, or keep it until a pack (or a mixed-dimension normalization rule) makes a forward tear reachable. | Batch 4B, 2026-10-18. The guard in `runtime_adapter.py` stays as a defensive check; no fixture was fabricated. Independent review (MINOR-3): no passing test protects the guard; a tampered-record test (a frozen plan altered after `__post_init__`) would, without inventing an admissible plan. **2026-10-18 remediation (A2): added `test_a_tampered_plan_with_a_forward_tear_is_refused_by_the_runtime_build` (genuine 1-stage records; the nominal plan plus the heat edge, set with `object.__setattr__` after the constructor refuses it as mixed-dimension; the test pins that the edge is forward in the derived order P, E, T). The original test is unchanged and still fails at `dataclasses.replace` (static reading, NOT RUN). Owner: replace it with the tampered-record test, or keep both.** |
| OD-27 | `MultiphysicsAuthority.execute` never checks that the run's `scenario_digest` is the scenario the system run authorized (`call.context.scenario.digest`); a `run_kwargs` passing another scenario's digest still commits state whose transition receipts name the wrong scenario. Add the check plus an adversarial test (a `src/` change, separate PR). | Independent review of Batch 4 (NOTE-3), pre-existing; outside the Batch 4 diff. |

| OD-28 | `MultiscaleAuthority` binds no scenario / timeline / environment to the call context: `runtime.identities()` carries those digests and they enter the authority's identity, but neither `execute`, `resume` nor `preflight_findings` compares them with `call.context`, so a multiscale node built on scenario A's environment can run, expose outputs and commit slow state inside a request for scenario B. Same class as OD-27 (MultiphysicsAuthority, branch `fix/od27-scenario-identity`). | Independent review of Batch 5 (M2), 2026-10-18; also: the battery fast system's inner `MultiphysicsRuntime` run digest is not checked. Not fixed in Batch 5. |

| OD-28 | `MultiscaleAuthority` binds no scenario / timeline / environment to the call context: `runtime.identities()` carries those digests and they enter the authority's identity, but neither `execute`, `resume` nor `preflight_findings` compares them with `call.context`, so a multiscale node built on scenario A's environment can run, expose outputs and commit slow state inside a request for scenario B. Same class as OD-27 (MultiphysicsAuthority, branch `fix/od27-scenario-identity`). | Independent review of Batch 5 (M2), 2026-10-18; also: the battery fast system's inner `MultiphysicsRuntime` run digest is not checked. Not fixed in Batch 5. **Implemented on branch `fix/od28-multiscale-identity` (draft PR, stacked on #164); UNCERTIFIED until OD-3.** |
| OD-29 | Fast-system inner run identity (follow-up of OD-28): `MultiTimescaleRuntime._execute` checks the fast result's echoed `consumed_environment_digest` / `consumed_timeline_digest` (the timeline digest binds the scenario transitively) and slow-state digest, but those are self-reported; the inner records behind `FastExecutionResult.run_digests` (e.g. the `MultiphysicsRuntime` run a heater/board or battery fast system starts with `scenario_digest=request.scenario_digest`) are never resolved or checked against the request's scenario / timeline / environment. Decide whether fast systems must hand back resolvable inner records (a `FastSystem` contract change in `multiscale/fast.py` and every provider fast system) or whether the echo stays the declared boundary. | Recorded 2026-10-18 while fixing OD-28; out of the bounded scope (multiscale core + providers, not the system-runtime authority). |
| OD-30 | `MultiscaleAuthority` identity payload omits `initial_fast_state` and includes the construction-time `declared_fast_state` of the runtime: two authorities with different declared initial fast states over fresh runtimes get the same `identity_digest`, and the digest depends on whether a shared runtime ran before the authority was built. Adding it changes the authority's serialization identity (a version decision). Separately: identity refusals in `MultiscaleAuthority` and `MultiphysicsAuthority` (OD-27) are reported FAILED, not REFUSED; reclassify both together or keep. | Independent review of Batch 6A (NOTE-3, LOW-3), 2026-10-18; pre-existing, not changed in OD-28. **2026-10-18 remediation (Batch B, user-instructed): fast-state half implemented in the worktree -- the payload's `declared_fast_state` is the authority's own declaration (same payload shape, no version key; an authority declaring none over a never-run runtime keeps its digest), enforced on every returned record. Flagship `cell-cooling-aging` digest moves on regeneration. FAILED-vs-REFUSED half still open. NOT RUN; UNCERTIFIED until OD-3.** |
| OD-31 | Model-discovery count: `tests/test_core_guards.py` pins `EXPECTED_MODELS = 19`, and M1C added `thermal.conduction1d.transient_piecewise_linear@0.1.0` (`domains/thermal_models/conduction1d_transient_fv.py:40`). Static count of `ScientificModelDefinition(` constructions in `src`: 19 at `89b9e7c3` (the commit that set 19) and 20 at `337519d1`; that is the only added or removed construction. The new record declares no validity conditions and no derived quantities, so reserving models (16), condition names (96), reserved names (63) and domains do not move. No added or removed `prepare`/`supports`, so solver classes stay 11. Approve `docs/work/proposals/A1_core_guards_model_count.patch` (19 -> 20). `tests/test_core_guards.py` is hash-pinned in `certification/current_core_v2.json` (already drifted since `89b9e7c3`), so this needs OD-3. | 2026-10-18 remediation, Batch A1. Discovery by import was attempted and could not run (host import wedge: `pint` / `scipy.sparse` imports do not return); the counts above are static. |
| OD-32 | Numerical record-identity decisions left by Batch C (2026-10-18 remediation): (a) C1-4: an unevaluable residual at the declared initial point is DIVERGED with zero iterations, pinned by `tests/test_phase3_br13_numerical_stability.py::test_a_non_finite_residual_is_a_classified_numerical_failure`; make it FAILED with a distinct reason, or keep. (b) C2-1: `NumericalDiagnostics.residual_norm` means a relative 2-norm (linear), an absolute 2-norm (SciPy root) or a scaled L-inf (Newton) under one key; add a `residual_measure` label (changes every record's serialization; `numerical/core.py` is certified). (c) C2-2: linear records do not carry `RESIDUAL_IS_NOT_AN_ERROR_BOUND` (every linear record digest changes; the constant is in uncertified `health.py`, which certified `providers.py` cannot import). (d) C3-1: `oriented_integral_*` in `mapping.py` (certified) re-applies the contract sign and cannot detect a wrong orientation; relabel it, or build an independent receiver-flux check. | Each changes serialization identity or a pinned outcome; not changed in the bounded Batch C slice. The limitation in (d) is pinned by a test. |
| OD-33 | M1D integration (adaptive transient) is not in `main`: `codex/m1d-adaptive-transient` (5fd797dd) is not an ancestor of `337519d1`. Its `from_transfer` reconstructs temperature from energy moved by the M1B length split, which across a jump in c*A turns a uniform 300 K into (300, 450, 257.1, 300) K on a two-material refine (hand derivation in `tests/test_m1b_vertex_dual_state.py`). Before M1D lands it must pass `AmountDistribution1D` (weights c*A per region) to `transfer_state`, and add the heterogeneous-uniform regression. Decide: rebase M1D onto this, or keep M1D homogeneous-only and refuse heterogeneous adaptation. | 2026-10-18 remediation, Batch D (D3-2). The M1B primitive is in the worktree, tests NOT RUN. |
| OD-34 | Issued-record re-verification cost (F2-4): every M1C step re-verifies every issued record (`numerical/mesh_adaptation.py` `_IssuedRecords.verify`), so N steps cost O(N^2). Making it incremental would stop detecting a later in-place tamper of an older record, which current tests pin. Decide: keep the full sweep (cost accepted), or replace it with verification of the ancestry each operation reads plus a periodic full sweep, after measuring step time at step 10 / 100 / 1000. | 2026-10-18 remediation, Batch F. Not changed; see "Proposals awaiting measurement" in `docs/work/REMEDIATION_2026-10-18.md` for F1-a/b/c and F3-2..4 as well. |

## Active-epic exceptions (open until OD-6 merges; EXC-1 is then superseded by the program)

An exception is valid only with every field the Completion Policy requires (scope, allowed work, reason, start, exit,
expiry, owner approval, prohibitions).

### EXC-1 -- adaptive mesh control, slice 1: adaptive resolution (Engineering Runtime V1 BR19)

1. **Exact scope:** a new module `src/engcore/claims/adaptive_resolution.py` and its tests, on branch
   `feat/engrt-v1-big-rocks`. It may import `claims/numerical_uq.py` (the canonical GCI estimator) but may not modify
   it.
2. **Allowed capability work:** an adaptive uniform-refinement driver. It solves at successively finer resolutions
   (counts x ratio^k) and stops when the canonical GCI half-width meets a declared target, or when a declared level
   budget is exhausted. The result is the finest run's value with its quantified NUMERICAL uncertainty (or UNKNOWN),
   recorded per level.
3. **Reason:** owner-directed Engineering Runtime V1 program (adaptive numerical execution and mesh control). The
   owner approved this exception on 2026-10-17 rather than waiting for the battery epic.
4. **Start condition:** owner approval in chat, 2026-10-17; build-phase rules apply (no test execution until
   authorized).
5. **Exit condition:** the slice is built; its deferred tests (DV-27) are executed and pass, or every failure is
   recorded; and a scientific review finds no false-support issue. Or the owner closes the exception.
6. **Expiry / timebox:** 2026-10-31. **Proposed by Claude, not set by the owner**; the owner may amend it.
7. **Owner approval:** the repository owner, in the Claude Code session, 2026-10-17 ("Approve an active-epic exception
   for adaptive mesh control as a new capability foundation").
8. **Still prohibited:**
   - local AMR, new mesh or field record types, or solver changes (a later slice needs its own scope);
   - changes to any capability declaration, the ledger (`scientific_capability_completion.json`) or maturity stages;
   - treating a met accuracy target as validation, or as a stage promotion;
   - any change to the battery 1RC epic or its pins;
   - a second concurrent exception, which would trigger the anti-loophole owner review.

**EXC-1 amendment A1 (2026-10-17): slice 2.** The owner approved it in the session ("Continue EXC-1: build
mesh-control slice 2"). It is the same exception, not a second one.
- **Scope added:** a new module `src/engcore/numerical/mesh_adaptation.py` and its tests.
- **Allowed work added:**
  - a non-uniform 1D grid record local to that module;
  - piecewise-linear a-posteriori error indicators;
  - Doerfler marking, bisection with gradation control, and an adaptation loop around a caller-supplied evaluator.
  - These are pure numerics: estimates labelled as estimates, no authority.
- **Still prohibited:**
  - changes to any domain solver (the uniform-grid `conduction1d` is untouched);
  - changes to Core mesh or field records (`scientific/fields`), capability declarations or the ledger;
  - wiring adaptive resolution into `uq_studies`. That would make a finer run than the claim's reported run carry
    its evidence, which is an owner decision.
  - Everything else in item 8 above.
- **Exit and expiry:** unchanged. DV-27 and the new DV-28 must run, and the scientific review must cover both slices.

**EXC-1 amendment A2 (2026-10-17): slice 3.** The owner approved it in the session ("Amend EXC-1 for slice 3: a
non-uniform finite-difference 1D conduction solver that adapt_grid can drive (new solver path, existing uniform
conduction1d untouched)").
- **Scope added:** a new module `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` and its tests. It is
  imported by its own path; the pinned `thermal_models/__init__.py` is not touched.
- **Allowed work added:**
  - a STEADY 1D conduction solver, -(k u')' = q, on a non-uniform `Grid1D`;
  - vertex-centred finite volumes, conductivity k(x) evaluated at faces, source q(x);
  - explicit boundary conditions at both ends (temperature or heat flux), never defaulted;
  - an evaluator `grid -> nodal temperatures` that `adapt_grid` drives.
- **Still prohibited:**
  - any change to `conduction1d`, `conduction1d_schemes` or any pinned file;
  - registering a model, capability or `ValidationCheck` (evidentiary audit and exact-count guards);
  - a transient solver; claims or `uq_studies` wiring;
  - everything in item 8 and A1.
- **Exit and expiry:** unchanged, plus DV-29 for this slice.

**EXC-1 amendment A3 (2026-10-17): slice 4.** The owner approved it in the session ("Amend EXC-1 for slice 4:
declare the non-uniform conduction path as a capability/realization").
- **Scope added:**
  - in `domains/thermal_models/conduction1d_nonuniform.py`, the scientific-layer declaration of the BR21 path:
    - one `ScientificModelDefinition` for steady 1D conduction with position-dependent k and q;
    - a domain `ScientificCapability` and a domain `SolverCapability`;
    - one `ModelRealizationDefinition`;
    - fresh local model and realization registries (no global singleton), the pattern of `lumped.py` and
      `conduction1d_schemes.py`;
  - the exact count `EXPECTED_MODELS` 18 -> 19 in `tests/test_core_guards.py`.
- **Certification consequence:** `tests/test_core_guards.py` is certification-pinned, so this edit makes it
  UNCERTIFIED until OD-3. The count is updated deliberately, as its comment requires, not to silence a failure.
- **Allowed work added:**
  - The model declares NO validity conditions, so its applicability is UNKNOWN by construction. Absence of declared
    limits is not applicability. This also leaves `EXPECTED_CONDITION_NAMES` and `EXPECTED_RESERVED_NAMES`
    unchanged.
  - Its validation status stays UNVALIDATED.
  - The solution record names the realization it came from.
- **Still prohibited:**
  - a claims-layer `CapabilityDeclaration` or any `CapabilityRegistry` / planning production-registry entry, so the
    path stays unreachable from claims, SRIA and MCP;
  - `ValidationCheck`, `ScientificSolver` or `ScientificResult` construction;
  - validity conditions or thresholds (each needs a sourced bound and moves pinned counts);
  - everything in item 8, A1 and A2.
- **Exit and expiry:** unchanged, plus DV-30 for this slice.

## Stop conditions

Stop and surface a blocker if a change would: weaken UNKNOWN or fail-closed semantics; change a frozen serialized
contract without a version decision; invent measurements, uncertainty, validation, provenance or evidence; duplicate an
existing scientific identity or authority; add domain-specific branches to the generic Core; treat convergence, replay or
solver agreement as validation; change a tolerance or criterion after seeing a result; or bypass an assurance gate.

## Checkpoint log

- 2026-10-11 — planning consolidation (docs only): Big Rocks First and P0–P40 superseded; this file reduced to the live
  queue; history archived. No code, test, result, threshold or certificate changed.
- 2026-10-12 — owner-requested, outside the queue: test-suite runtime branch `perf/test-suite-runtime` (OD-14). Tier
  relabelling and duplicate-work removal; no assertion, tolerance or result changed. Not merged, not recertified.
- 2026-10-12 — PR #126 (authority ledger, real escrow, battery blind readiness `NOT_READY`) merged with `main` on owner
  direction (OD-5). Its follow-ups (designate the battery confirmatory dataset, provision a production authority ledger,
  seal real battery falsifiers, systematic prior-art search, deploy the data authority behind the escrow) are owner-gated
  and sit under LATER with row 47. Kirkaldy stays NOT MET; no confirmatory datum was exposed. Not recertified (OD-3).
- 2026-10-12 — PR #123 Trust Repair Pass 1 (R3-01 offline revalidation, R3-02 MCP `assess_claim` delegating to the
  canonical claim runtime) merged with `main` on owner direction (OD-4). `803946af` is therefore on the remote (OD-10,
  partly). R3-03 to R3-16 stay open. Not recertified on the merged tree (OD-3).
- 2026-10-12 — PR #117 (deterministic NASA PCoE raw ingestion for the active epic `battery.thevenin_1rc`) merged with
  `main` on owner direction. Ingestion only: `real_data` stays `MISSING`, no SOC / pulse-rest / sensor uncertainty /
  R0-R1-C1 is inferred, and the capability stays FOUNDATION. Its ACTIVE_PLAN edit (an old-queue section with
  re-encoded characters) was not carried; its prereg is `docs/milestones/battery-1rc-production-closure-prereg.md`.
- 2026-10-12 — owner-requested, outside the queue: engineering / scientific-integrity program on local branch
  `perf/engineering-program-2026-10-12` (not pushed). Selection, robustness, challenge, impact, provider-timeout and
  changed-file-selection defects fixed; FAST failure set identical to `2d0fa6c3`. `tools/forge_check.py` is
  certification-pinned: landing it needs OD-3. Report `docs/audits/ENGINEERING_PROGRAM_2026-10-12.md`.
- 2026-10-13 — owner-requested, outside the queue: test-loop round 3 on local branch `perf/test-loop-round3` (base
  `9ca337f9`, not pushed). `forge_check --dev` (one command, next required gate) and `--scientific` (developer aid that
  refuses to narrow shared, trust, configuration or unknown changes); timing telemetry with a measured large-slowdown
  guard. Measured and rejected: provider-probe memoization (< 1 s), giant-module splits (no wall gain at -n 4).
  FAST / SCIENTIFIC failure sets identical to base. `tools/forge_check.py` and harness tests changed:
  RECERTIFICATION_REQUIRED (OD-3).
- 2026-10-13 — owner-requested, outside the queue: test-loop round 2 on local branch `perf/test-loop-round2` (base
  `ca24b152`, not pushed). Benchmark rebuild tests isolated (no tracked file written); `forge_check --changed` dry-run
  6.37 s -> 1.81 s with a content-addressed impact cache (identical selections); opt-in `--workers safe-auto`;
  standalone audit of 569 modules found no order-dependent module; probes, escrow stop/close, Dakota version probe and
  preCICE directory removal hardened. FAST / SCIENTIFIC failure sets identical to base. `tools/forge_check.py` changed:
  RECERTIFICATION_REQUIRED (OD-3).
- 2026-10-13 — owner-requested, outside the queue: scientific-integrity / certification / engineering remediation on
  local branch `fix/remediation-2026-10-12` (uncommitted, not pushed). Fixed: guard-band SURVIVED on an undecided
  verdict, model-form bridge promoting a FAILED_VALIDATION discrepancy (and replay crashes, ported), selection D3,
  provider timeouts that an escaped descendant could hold for its lifetime, discovery/ngspice untyped failures, sweep
  budgets (`run_sweep_within_budget`). Recorded owner decisions OD-R1..OD-R8 in `docs/audits/REMEDIATION_2026-10-13.md`.
  `execution/sweep.py`, `ngspice.py` and 8 harness tests need the OD-3 recertification.
- 2026-10-12 — owner-requested, outside the queue: test-loop round on local branch `perf/test-loop-cleanup` (not
  pushed). FAST -14 % at `-n 4`, -28 % at `-n 8`; CI-equivalent SCIENTIFIC -15 %; identical failure sets. The changed-file
  gate now runs the tests a change reaches. Certified harness and `tools/forge_check.py` changed: one owner-run
  recertification (OD-3) covers the batch. Two benchmark rebuild tests still write committed JSON in place (open).

- 2026-10-12 — landing pass closed: #126, #123, #117 merged (`2d0fa6c3`); #107, #39, #24 blocked (OD-11, OD-21).
  Verified state updated. Next agent-executable G0 action is unchanged: FAST on the OD-3 HEAD in a full-history
  checkout, then classify the 14 failures.


## 2026-10-13 bounded test infrastructure closeout

Owner-requested closeout measured origin/main `5d73e8f5118aa845f1957decc5aae986e72476a9` in clean dedicated trees. Outcome: **TEST_INFRASTRUCTURE_FINAL_ASSURANCE_BLOCKED**. Supported FAST/SCIENTIFIC retain certificate drift and the impact scanner parsing .forge/venvs; scanner failure reproduced before Round3 on both supported Python versions. Unrestricted supported FULL: 10607 passed, 4 failed, 157 skipped; added failures are documented benchmark digest baseline. Owner runner REFUSED at fast311 before certificate generation; no mutation completion, certificate child, push or current-main certification is claimed. Primary Windows attribution remains incomplete because the same-environment baseline and FULL stalled.

Evidence and exact next bounded repair: `docs/work/FINAL_TEST_INFRASTRUCTURE_ASSURANCE_2026-10-13.md`; PROGRESS records commands/results. Do not mark Rounds1–3 assurance closed or continue new performance work on this evidence. No scientific verdict, evidence, UQ, Trust/Mind, numerical or frozen experiment change was made.
- 2026-10-16 — landing pass: recent active work merged into `main` by owner direction (PROGRESS 2026-10-16); `main` carries uncertified changes to certified files until the OD-3 hardened run on the new HEAD; `fix/final-assurance-blockers` left out as superseded; stale branches listed for OD-11.
