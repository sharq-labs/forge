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
