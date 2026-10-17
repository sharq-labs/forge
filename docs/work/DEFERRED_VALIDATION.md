# Deferred validation backlog

Build phase (owner direction, 2026-10-17): Big Rocks are implemented first. Tests are written but NOT executed;
only `py_compile` / import checks are run. Nothing here is verified, validated or certified. Every item stays
**NOT RUN** until the owner authorizes the stabilization phase; then run each listed command, record the exact
result in `PROGRESS.md`, and fix or record every failure. Do not execute these automatically.

Every changed certification-pinned file is **UNCERTIFIED** until recertification (OD-3).

| ID | Big Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-1 | BR1 + BR11 + BR17 adaptive coupling windows (step-size memory, stagnation) | New tests | `pytest tests/test_multiphysics_window_control.py -q` | NOT RUN |
| DV-2 | BR1 | Existing multiphysics runtime suites (exception subclass, plan serialization, run-record shape) | `pytest tests/test_stateful_multiphysics_runtime.py tests/test_big9_review_runtime_fixes.py tests/test_multiphysics_conservation_history.py tests/test_multiphysics_fan_in_units.py tests/test_external_participant_checkpoints.py tests/test_coupled_transport_admission.py -q` | NOT RUN |
| DV-3 | BR1 | Stored plan/run fingerprints unchanged for plans without window control (any test or benchmark that pins a `CouplingPlan.fingerprint()` or run digest) | FAST tier, diffed against a pristine baseline | NOT RUN |
| DV-8 | BR2 + BR16 joint IQN-ILS | New tests (hand-computed expectations, QR filter) | `pytest tests/test_multiphysics_iqn_ils.py -q` | NOT RUN |
| DV-9 | BR2 | Field-valued (mesh) edges under IQN-ILS: no test exists yet; write one with a registered mesh | new test | NOT WRITTEN |
| DV-10 | BR3 error accounting | New tests (includes estimate >= true error on an exact linear contraction) | `pytest tests/test_multiphysics_numerical_error_accounting.py -q` | NOT RUN |
| DV-11 | BR4 splitting estimate | New tests (exact first-order model problem; determinism of an identical re-run) | `pytest tests/test_multiphysics_splitting_estimate.py -q` | NOT RUN |
| DV-12 | BR5 concurrent Jacobi | New tests (Barrier proof of overlap, sequential equivalence of the run record, first-in-order failure) | `pytest tests/test_multiphysics_concurrent_jacobi.py -q` | NOT RUN |
| DV-13 | BR5 | Wall-time measurement on a provider-bound Jacobi coupling (the only reason to use it); none exists yet | benchmark, owner-authorized | NOT RUN |
| DV-14 | BR6 claims condition | New tests + the BR3/BR4 tests changed by the review fixes | `pytest tests/claims/test_coupling_numerical_condition.py tests/test_multiphysics_numerical_error_accounting.py tests/test_multiphysics_splitting_estimate.py -q` | NOT RUN |
| DV-15 | BR6 | Claims regression after a new claims module (architecture/layering, claims assessment suites) | `pytest tests/claims tests/test_repository_architecture.py tests/test_core_api_layering.py -q` | NOT RUN |
| DV-16 | BR7 nonlinear robustness | New tests (fake basin provider + one real scipy root) | `pytest tests/numerical/test_robust_nonlinear.py -q` | NOT RUN |
| DV-17 | BR8 heater chain | New tests (200-state exact-equality sweep; SciPy-1.18-dependent fallback check) | `pytest tests/domains/electrical/test_heater_root_chain.py -q` | NOT RUN |
| DV-18 | BR8 | Multiscale suites still pass with the fixture unchanged (identity unchanged by construction) | `pytest tests/test_multiscale_runtime.py tests/test_multiscale_review_fixes.py tests/test_big11_review_fixes.py -q` | NOT RUN |
| DV-19 | BR9 multiscale fast non-convergence | New tests + existing multiscale suites (policy digest unchanged by default) | `pytest tests/test_multiscale_fast_nonconvergence.py tests/test_multiscale_runtime.py tests/test_multiscale_review_fixes.py -q` | NOT RUN |
| DV-20 | BR10 pack templates | New tests + composition-pack suites (template/pack digests unchanged) | `pytest tests/compositionpacks -q` | NOT RUN |
| DV-21 | BR12 aligned-window outcome | New tests + existing event-alignment tests (tests/test_big9_review_runtime_fixes.py) | `pytest tests/test_multiphysics_event_aligned_outcome.py tests/test_big9_review_runtime_fixes.py -q` | NOT RUN |
| DV-22 | BR13 mapping sources | Integration test with a real field-mapped coupled run (extrapolating and unverified mappings); none written yet | new test | NOT WRITTEN |
| DV-23 | BR14 untraced external providers | New tests + existing MultiphysicsAuthority suites | `pytest tests/test_system_runtime_external_providers.py tests/test_system_runtime_big13_additions.py tests/test_multiphysics_conservation_history.py -q` | NOT RUN |
| DV-24 | all | Certified-imports-uncertified closure: runtime.py -> concurrency.py (BR5), claims/coupling_numerical.py -> numerical_error.py (BR6) must be pinned or declared before build/verify passes | owner recertification (OD-3) | NOT RUN |
| DV-25 | BR15 refinement per route | Orchestration tests | `pytest tests/execution/orchestration -q` | NOT RUN |
| DV-26 | BR18 electrothermal relaxation | New tests + existing electrothermal suites (plan identity unchanged by default) | `pytest tests/test_electrothermal_fixed_point_relaxation.py tests/domains/thermal_models/test_lumped_applicability.py tests/test_electrothermal_vertical.py -q` | NOT RUN |
| DV-27 | BR19 adaptive resolution (EXC-1 exit gate) | New tests + scientific review of the slice | `pytest tests/claims/test_adaptive_resolution.py -q` + forge-scientific-review | NOT RUN |
| DV-4 | all | Scientific regression pack | `python tools/forge_check.py --regression --workers 4` | NOT RUN |
| DV-5 | all | FAST tier diffed against a pristine `origin/main` worktree (Windows has ~150 environmental failures) | `pytest -m "not expensive" -q -n 4` | NOT RUN |
| DV-6 | all | Scientific review (`forge-scientific-review`) of each Big Rock diff | skill | NOT RUN |
| DV-7 | all | OD-3 recertification of the integrated branch | owner | NOT RUN |

## Unverified assumptions (BR1)

- Every participant restore is complete. The runtime re-checkpoints after restore and compares digests, but only
  as far as each participant's own digest covers its state.
- Operating conditions applied at a window start are not undone by restore, and they are not re-applied before a
  retry. They are applied once per boundary instant, and the retry starts at the same instant, so the assumption
  is that the values are unchanged.
- Bulk-store records written by a rejected attempt are orphaned. Nothing references them, but they are not
  deleted.
- The divergence test compares each edge's latest absolute residual with its first-iteration residual. A
  residual that oscillates and then grows is caught; slow monotone growth below the factor is not.
  (BR17 adds opt-in stagnation detection: no improvement on the earlier best for n iterations.)

## Unverified assumptions (BR2)

- Joint IQN-ILS is exact for linear maps once enough independent secant pairs span the interface. Its behaviour on
  the nonlinear couplings in this repository is unmeasured, including the electrothermal feedback, which uses an
  EXPLICIT scheme today and does not reach it.
- (Superseded by BR16) Near-dependent secant pairs are now dropped by a newest-first QR filter (`iqn_filter`). The
  filter threshold is a numerical choice, declared in the policy and recorded with it.
- An edge whose residual is zero at every iteration keeps weight 1. Its rows are identically zero, so this does not
  affect the step.
- Uncertainty through an IQN step is UNKNOWN by design. A converged coupled value therefore carries no propagated
  uncertainty under IQN, where constant or Aitken relaxation would propagate a declared one.

## Unverified assumptions (BR3)

- The contraction ratio q comes from the last two residuals of one edge. On nonlinear or non-monotone convergence
  the estimate can under-state the error; it is labelled ESTIMATED for that reason.
- A residual-based estimate assumes the recorded residual is the unrelaxed fixed-point residual, which the runtime
  guarantees for implicit windows (`raw_out`).
- Splitting error is reported once per explicit run, not per window or per edge.

## Unverified assumptions (BR4)

- The builder is trusted to rebuild the SAME participants. Only graph and plan identity are checked. Participant
  implementation behaviour is not part of any record, so a builder that changes a participant's behaviour between
  levels goes undetected; the test's `bias` variant does exactly that.
- Richardson assumes the observed (or declared) order holds at the base window. A smooth problem with a shift in
  dominant error terms between levels can pass the asymptotic-range check and still be mis-estimated.
- Estimate-to-run binding relies on run records being byte-identical across a deterministic re-run, i.e. no hidden
  nondeterminism in `run.to_dict()`. The test relies on this and it is unverified.
- Only scalar outputs at the horizon end are estimated. Field outputs and time histories are not.

## Unverified assumptions (BR5)

- Unit conversion (Pint registry, `lru_cache`d canonicalization) is assumed safe under concurrent use from worker
  threads. `functools.lru_cache` is thread-safe; the registry's own caches have not been checked for it.
- The GIL means pure-Python participants gain nothing. The benefit is expected only for participants that release
  the GIL: external processes (ngspice via WSL, providers), and NumPy or SciPy solves. Unmeasured (DV-13).
- A declared participant's thread-safety is the declarer's claim. Shared `BulkDataStore` writes by two declared
  participants are not guarded here.
- When one concurrent participant fails, the others in the same batch have already advanced. This is the same
  situation as a sequential failure after earlier participants advanced. Window control (BR1) rolls all of them
  back; without it the run fails.

## Unverified assumptions (BR6)

- Run binding: the coupled run's `run_id` names the study's level 0 (`<run_id>~numerical~0`), following the
  `uq_studies` convention. Nothing yet ties a claims report to the digest of the coupled run that produced it. That
  needs the capability integration that does not exist yet.
- Deterministic `run.to_dict()` (canonical digest) is assumed, as in BR4.
- The study record shape is read as `uq_studies._refinement` writes it today. A change there must update this
  module.

## Unverified assumptions (BR7)

- Natural-parameter continuation cannot pass a turning point (fold) of the solution branch. Such a family ends as a
  failure, never as a wrong root; pseudo-arclength continuation is not implemented.
- A warm start assumes the converged outputs of the previous step are a valid initial guess for the next problem,
  i.e. the family is continuous in lam. Nothing checks that continuity.
- A method chain changes WHICH algorithm produced the accepted root. Two methods converging to different roots of a
  multi-root problem are not compared; the first converged one is accepted and recorded.

## Unverified assumptions (BR8)

- MINPACK is deterministic for identical residual, initial value and options, so a chain attempt reproduces the
  single-method result bit-for-bit. The exact-equality test relies on this.
- The 200-state sweep contains at least one hybr false refusal under SciPy 1.18, as recorded in project memory but
  not re-measured.

## Unverified assumptions (BR9)

- The retry assumes a shorter macro window can change the fast execution's outcome: through the slow state
  consumed, the resolved window, or the representative selection. A fast failure independent of all three
  exhausts the rejection bound and refuses, as before, just later.
- No real fast system raises `FastExecutionNotConverged` yet. The reference heater system's coupled loop failures
  reach the macro loop only if they propagate as `CouplingWindowNotConverged` (BR1); that path is untested.

## Unverified assumptions (BR10)

- `dataclasses.replace` on `SystemGraphBlueprint` and `ParticipantBlueprint` re-validates as construction does. The
  positive test builds a restorable blueprint this way.
- No built-in pack participant is deterministically restorable, so no built-in system can use window control
  without adapter work. That is outside this change.

## Unverified assumptions (BR11)

- The remembered width is a numerical heuristic, not an error estimate. It only changes where windows start; every
  window is still held to the same criteria and logged.
- Growth applies per accepted window, including windows cut short by an event. A long run of event-cut windows can
  regrow the width without exercising it.

## Unverified assumptions (BR19)

- The caller's `solve` honours the requested counts and solves the same declared model at each level. The counts
  are checked; the model identity is the caller's responsibility, as in `uq_studies`.
- Three finest levels are re-estimated after every level. Observed-order agreement across four or more levels (a
  rule of the canonical estimator) is not used, because only three levels are passed each time.
