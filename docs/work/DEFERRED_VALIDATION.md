# Deferred validation backlog

Build phase (owner direction, 2026-10-17): Big Rocks are implemented first. Tests are written but NOT executed;
only `py_compile` / import checks are run. Nothing here is verified, validated or certified. Every item stays
**NOT RUN** until the owner authorizes the stabilization phase; then run each listed command, record the exact
result in `PROGRESS.md`, and fix or record every failure. Do not execute these automatically.

Every changed certification-pinned file is **UNCERTIFIED** until recertification (OD-3).

| ID | Big Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-1 | BR1 adaptive coupling windows | New tests | `pytest tests/test_multiphysics_window_control.py -q` | NOT RUN |
| DV-2 | BR1 | Existing multiphysics runtime suites (exception subclass, plan serialization, run-record shape) | `pytest tests/test_stateful_multiphysics_runtime.py tests/test_big9_review_runtime_fixes.py tests/test_multiphysics_conservation_history.py tests/test_multiphysics_fan_in_units.py tests/test_external_participant_checkpoints.py tests/test_coupled_transport_admission.py -q` | NOT RUN |
| DV-3 | BR1 | Stored plan/run fingerprints unchanged for plans without window control (any test or benchmark that pins a `CouplingPlan.fingerprint()` or run digest) | FAST tier, diffed against a pristine baseline | NOT RUN |
| DV-8 | BR2 joint IQN-ILS | New tests (hand-computed expectations) | `pytest tests/test_multiphysics_iqn_ils.py -q` | NOT RUN |
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

## Unverified assumptions (BR2)

- Joint IQN-ILS is exact for linear maps once enough independent secant pairs span the interface. Its behaviour on
  the nonlinear couplings in this repository is unmeasured, including the electrothermal feedback, which uses an
  EXPLICIT scheme today and does not reach it.
- `np.linalg.lstsq` with the default `rcond` is the only conditioning filter. There is no QR column filtering as in
  preCICE, so near-dependent secant pairs are handled only by the truncated SVD.
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
