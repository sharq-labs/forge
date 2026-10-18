# Active Plan

Active epic: `engrt.numerical_foundations` (research program; OD-6 decided 2026-10-18; in force when branch
`feat/od6-engineering-program-epic` merges). Earlier entries below that call `battery.thevenin_1rc` the epic, list OD-6
as open, or list EXC-1 as an open exception are superseded by that decision on merge. The program's gates M1-E3 are
bound by its Cross-Domain Scientific Architecture Requirements (physics-agnostic shared structure; heat is the first
reference application).

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
