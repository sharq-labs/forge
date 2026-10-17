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
| DV-28 | BR20 1D mesh adaptation (EXC-1 exit gate, with DV-27) | New tests + scientific review | `pytest tests/numerical/test_mesh_adaptation.py -q` + forge-scientific-review | NOT RUN |
| DV-29 | BR21 non-uniform steady 1D conduction (EXC-1 exit gate, with DV-27/28) | New tests + scientific review | `pytest tests/domains/thermal_models/test_conduction1d_nonuniform.py -q` + forge-scientific-review | NOT RUN |
| DV-30 | BR22 model + realization declaration (EXC-1 exit gate, with DV-27/28/29) | New tests + the model census and per-model guards + scientific review | `pytest tests/domains/thermal_models/test_conduction1d_nonuniform.py tests/test_core_guards.py tests/test_blind_challenge_guards.py tests/test_model0r_realization_foundation.py -q` + forge-scientific-review; test_core_guards is certified, so OD-3 too | NOT RUN |
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

## Unverified assumptions (BR20)

- The indicator assumes a smooth solution. At a discontinuity or kink it is still largest there, but it is not an
  error estimate there.
- Boundary nodes copy their neighbour's curvature estimate, which is exact for quadratics and first-order otherwise.
- Gradation uses repeated single bisections until no violation remains. It terminates because every bisection halves
  a cell above `minimum_cell`, but its node cost on extreme layers is unmeasured.

## Unverified assumptions (BR21)
- The wall-layer test assumes `adapt_conduction` (theta 0.5, tolerance 1e-2 K) meets TOLERANCE_MET_ESTIMATED
  within 50 cycles and 10 000 nodes. The cycle count was estimated (about nine bisection levels at the wall), not
  measured.
- The adapted grid beating a uniform grid of the same node count on NODAL error is the expected behaviour for a
  boundary layer. The indicator estimates interpolation error, not nodal error, so this is a behavioural claim
  the test checks, not a property the indicator guarantees.
- The second-order ratio (> 3 between 17 and 33 nodes for k = 1 + x) follows from the midpoint rule's
  per-cell O(h**3) flux error. It has not been executed.
- At a discontinuity in k, the curvature the indicator reads is not the solution's. The adaptation record's
  notice covers this; no test exercises a k jump.

## Unverified assumptions (BR22)
- `EXPECTED_MODELS` 19 assumes the package walk finds exactly one new model record. Nothing else in this
  branch adds or removes one. Not run.
- The per-model guards in `test_core_guards.py` (classified condition names, assembler refusal, declared
  exclusions, conservative screens, condition dependencies) were read, not run, against the new record.
- `varies_with="position"` names an axis that is not itself a model input. The only other use (battery) names
  a declared input. Nothing found requires that, but no test exercises a curve handed to these inputs.
- Zero validity conditions is a deliberate UNKNOWN. A scientific reviewer may instead require sourced
  conditions (for example, a Biot or aspect-ratio screen for 1D applicability) before any claim use.

## Phase 1 — Scientific & numerical correctness (2026-10-17)

Branch `fix/phase1-scientific-numerical-correctness` (worktree `D:/forge-phase1`), base `origin/main` `de11dffa`.
Local commits only. The rocks are numbered P1-BR1..P1-BR7 here so they are not confused with the Engineering
Runtime V1 BR1..BR22 above. **No test of any kind was executed in this phase** (owner direction): only `py_compile`
and `git diff --check`. Every capability changed here is IMPLEMENTED / UNVERIFIED and every touched
certification-pinned file is UNCERTIFIED until OD-3.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-31 | P1-BR1 coverage, explicit plans, non-finite residuals | New tests | `pytest tests/test_phase1_coupling_convergence_coverage.py -q` | NOT RUN |
| DV-32 | P1-BR1 | Existing suites that build EXPLICIT plans (all refused on `main` since `35d8f557`) or implicit plans with partial criteria (now refused); expect outcome changes in both directions | `pytest tests/test_multiphysics_window_control.py tests/test_multiphysics_iqn_ils.py tests/test_multiphysics_splitting_estimate.py tests/test_multiphysics_event_aligned_outcome.py tests/test_big9_review_runtime_fixes.py tests/test_stateful_multiphysics_runtime.py tests/compositionpacks -q` | NOT RUN |

### Unverified assumptions (P1-BR1)

- Serial forward edges without relaxation are treated as consistent by construction. The runtime delivers
  `old + 1.0 * (new - old)`, which equals `new` only up to one rounding; the policy accepts that rounding.
- Every existing implicit plan in `src/`, `flagships/` and `tests/multiscale_reference.py` was read against the
  coverage policy and monitors its required edges (drone hover: `bus_voltage`, `winding_temperature`; battery
  cooling and the heater board monitor every edge). Plans inside other test files were not audited; DV-32 finds them.
- The field residual `l2` stays the root mean square over stored values. On a non-uniform support it is not a
  mesh-weighted L2 norm; that is documented, not changed (changing it would move convergence decisions).
- Non-finite participant outputs are refused when the `Quantity` / `FieldValue` is built, before any residual;
  that refusal is not retried by window control. Only an overflowing residual is a retryable numerical failure.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-33 | P1-BR2 conservative cell remap | New tests (hand-computed overlap oracles, refusals, diagnostics identity) | `pytest tests/test_phase1_conservative_cell_mapping.py -q` | NOT RUN |
| DV-34 | P1-BR2 | A field-mapped coupled run through `TransferEngine` with a conservative edge (mapping provenance reaches the run record); none written | new test | NOT WRITTEN |
| DV-35 | P1-BR2 | Cost of the polygon path (O(source x target) candidate search in Python) on a realistic interface mesh; owner-authorized measurement only | benchmark | NOT RUN |

### Supported geometry (P1-BR2)

- Two axis-aligned `StructuredMesh` grids of any spacing: exact separable overlaps (`kron` of 1D overlaps).
- Any pair of planar 2D supports made of triangles, strictly convex quadrilaterals or structured rectangles:
  Sutherland-Hodgman intersection of convex polygons in the target cell's local frame.
- Refused: node fields, offset-scale units (degC, degF), any coverage deficit above the declared round-off
  allowance in either direction (no extrapolation, no dropped source integral), 3D cells, non-convex or
  degenerate cells, `ExtrapolationPolicy.NEAREST` on a conservative definition. No nearest-site fallback.

### Unverified assumptions (P1-BR2)

- `CONSERVATIVE_COVERAGE_ROUNDOFF = 1e-9` (relative to the cell measure) absorbs float64 intersection
  round-off. Measured deficits are recorded in provenance; the value itself is a numerical choice, not a measurement.
- First order only: a piecewise-constant remap is conservative, not accurate; its pointwise error is
  unquantified and stays so in the numerical-error accounting (P1-BR3).
- The structured path assumes `axis_coordinates()` partitions are sorted and gap-free, which the record
  guarantees by construction.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-36 | P1-BR3 error semantics | New tests + the three rewritten `_mapping_sources` tests and one new identity test in the ERT V1 BR3 file | `pytest tests/test_phase1_numerical_error_semantics.py tests/test_multiphysics_numerical_error_accounting.py tests/claims/test_coupling_numerical_condition.py -q` | NOT RUN |
| DV-37 | P1-BR3 | Every run digest changes (`_coupling_error` payload and `coupling_error_bound=None`); any test pinning a run digest or the old budget shape moves | FAST tier diffed against a pristine baseline | NOT RUN |

### Semantics after P1-BR3

| Evidence | Status | Summed into a bound? | Closes a source? |
| --- | --- | --- | --- |
| Mapping round-trip residual | DIAGNOSTIC | never | never |
| Mapping conservation residual | DIAGNOSTIC | never | never |
| Forward error of a non-identity field mapping | UNQUANTIFIED | -- | -- (vetoes the claims NUMERICAL channel) |
| Identity mapping on one support | no source (exact) | -- | -- |
| Fixed-point contraction estimate | ESTIMATED (unchanged) | never | never |
| Explicit splitting without an estimate | UNQUANTIFIED (unchanged) | -- | -- |
| Window not completed | UNBOUNDED (unchanged) | -- | -- |
| Mathematical bound | QUANTIFIED -- nothing in the coupling runtime produces one today | yes | yes, if exactly zero |

### Unverified assumptions (P1-BR3)

- `MultiphysicsRunRecord.coupling_error_bound` stays in the schema for reading old records; the runtime writes
  None. A stored non-None value is not re-interpreted anywhere; nothing in `src/` reads the field.
- The claims condition's behaviour on a real field-mapped coupled run is unexercised (no claims capability
  produces a multiphysics run record yet); the new tests patch the assessment.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-38 | P1-BR4 exact window boundaries | New tests (exact ends, long horizon, absorbed remainder, event shift, one-ulp event pair refused, determinism) | `pytest tests/test_phase1_exact_time_windows.py -q` | NOT RUN |
| DV-39 | P1-BR4 | Window-control, event-alignment, scenario and multiscale suites: window ends and window-control log floats can move by an ulp; STEP samples off the exact grid (e.g. built as `k * 0.1` in float) are now refused | `pytest tests/test_multiphysics_window_control.py tests/test_big9_review_runtime_fixes.py tests/test_stateful_multiphysics_runtime.py tests/test_multidomain_science_hardening.py tests/test_multiscale_runtime.py -q` | NOT RUN |

### Rules after P1-BR4

- Boundaries are exact `Fraction` seconds from `exact_seconds` (`SAME_INSTANT_RULE`); records and participants
  still receive `float(boundary)`, which is correctly rounded and never accumulated.
- A nominal window is `current + width` in exact arithmetic. Events, STEP-input and operating-condition change
  instants and the horizon cut it exactly; after any non-nominal end the grid restarts from that exact instant
  (the pre-existing shift semantics are kept).
- A forced boundary beyond the nominal end by no more than the float64 resolution of the grid since its last
  anchor (one ulp of the anchor, one ulp of the width per window, one ulp of the boundary) is absorbed into the
  window and logged in `final_outputs["_time_grid"]` (absent otherwise, so other runs keep their identity).
- A window no wider than one ulp of each of its boundaries is refused (`MultiphysicsExecutionError`): the schedule
  cannot be represented consistently. A subdivision retry that narrow ends the subdivision.
- Subdivision, minimum window and step-size memory compute in exact arithmetic (`Fraction(repr(factor))`);
  `minimum_window` is compared exactly, without the old `1 - 1e-12` slack.
- STEP sample alignment is exact: `(instant - start) % width == 0`.

### Unverified assumptions (P1-BR4)

- A participant's reported end and terminal-event instants are still compared with the pre-existing
  `1e-12 * max(1, |t|)` tolerance (`_advance_one`, `_terminal_event`, `_checkpoint_all`). That is a participant
  reporting contract, not the window grid; for sub-microsecond windows it is loose and is recorded as open.
- `minimum_window` governs subdivision only. A window forced short by an event, an input change or the horizon
  may be shorter than it; whether such a schedule should be refused under window control is an owner decision.
- `float(Fraction)` is correctly rounded in CPython; the determinism test relies on it.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-40 | P1-BR5 typed verification | New tests + the existing verification suites (all existing policies use V1/V2/V4 with route kinds the table keeps; expected unchanged) | `pytest tests/scientific/verification tests/execution/test_verification_runner_v2.py tests/execution/test_verification_runner_identity_v2.py tests/credibility/test_assurance_manifest_v2.py tests/compositionpacks -q` | NOT RUN |
| DV-41 | P1-BR5 | Mutation population V4: mutant **N60d** pins the removed ordinal line of `plan_verification` and can no longer apply; N60e, N60f and N60i lines are byte-identical. The population is certification-pinned, so the replacement mutant (typed admission -> `if False`, killed by `test_a_legacy_v2_requirement_is_not_met_by_validation_model_form_or_reproduction`) needs OD-3 | owner recertification | NOT RUN |

### Category table (P1-BR5)

| Category | Provided by route kinds | Legacy `minimum_level` that names it |
| --- | --- | --- |
| repeatability | same_solver_rerun | V0 |
| solution_verification | different_algorithm | V1 |
| code_verification | different_implementation, external_solver, analytical_reference | V2 |
| model_form_comparison | different_model | V3 |
| analytical_comparison | analytical_reference | V4 |
| independent_solver_corroboration | external_solver | V5 |
| experimental_validation | experimental_measurement | V6 |
| reproducibility | independent_reproduction | V7 |

The only many-to-one entry is code verification (code-to-code comparison and comparison with an exact solution of
the same model). Every promotion the ordinal check allowed beyond this table is now refused, including
V6/V7 for V2, V5 for V4 and V3 for V1/V2.

### Unverified assumptions (P1-BR5)

- Admitting `analytical_reference` and `external_solver` for code verification is a scientific judgement (Roache /
  Oberkampf code-to-code and exact-solution comparison). An owner may narrow it; nothing else is many-to-one.
- A plan whose candidate was rejected for its level now carries a different rejection text; any stored
  `verification_plan` payload with such a rejection would be refused as stale by `plan_from_dict`. No stored payload
  was found in `benchmarks/`, `certification/` or `tests/`.
- `minimum_level=V0` used to admit every route kind; it now requires repeatability. No policy in `src/` uses V0.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-42 | P1-BR6 sparse correctness | New tests (a `NeverDense` matrix fails on any densification; structure/dtype/finiteness refusals; canonical digest; exact vs estimated vs unresolved conditioning; dense-provider bound) | `pytest tests/numerical/test_phase1_sparse_correctness.py -q` | NOT RUN |
| DV-43 | P1-BR6 | Existing numerical-provider suites: records of sparse systems with 1000 < n <= 2000 change from an exact number to a labelled estimate or UNRESOLVED; larger ones from no record to one | `pytest tests -q -k "numerical or provider" -m "not expensive"` (diff against a pristine baseline) | NOT RUN |
| DV-44 | P1-BR6 | Memory/time of admission and conditioning on a large sparse system (no performance claim is made here) | owner-authorized benchmark | NOT RUN |

### Policy after P1-BR6

| Operand | Admission | Condition record |
| --- | --- | --- |
| dense | finiteness of every value (unchanged) | exact 2-norm, `numpy.linalg.cond (2-norm)` (unchanged label) |
| sparse, n <= 1000 | stored entries only: full structure check, real numeric dtype, finite stored values | exact 2-norm after a bounded dense conversion (same label as dense) |
| sparse, n > 1000, nnz <= 5e6, direct method | as above | deterministic Hager/Higham 1-norm LOWER-BOUND estimate on one SuperLU factorization, labelled ESTIMATED: above the threshold it proves ill-conditioning; below it, UNRESOLVED (never well-conditioned) |
| sparse, iterative method (GMRES) above n = 1000 | as above | UNRESOLVED: no factorization is forced on an iterative method |
| sparse, nnz > 5e6 | as above | UNRESOLVED (factorization policy) |
| sparse into `dense_lu` | densified only up to n = 4096 (128 MiB), else refused | -- |

`array_digest` hashes a canonical CSR copy (duplicates summed, indices sorted, explicit zeros kept; the caller's
matrix is not modified). An already canonical matrix hashes exactly as before.

### Unverified assumptions (P1-BR6)

- SciPy's `onenormest` was not used because it draws random starting columns; the in-module estimator is the
  deterministic LAPACK xLACON scheme. Its estimate is a lower bound in exact arithmetic; with LU round-off it is
  approximately one.
- The limits (1000, 5e6 stored entries, 4096) are memory-budget choices, not measurements.
- Index dtype (int32 vs int64) is still part of a sparse digest; two otherwise identical canonical matrices with
  different index dtypes hash differently. The messy-vs-canonical test assumes SciPy picks int32 for both.
- `SuperLU` fill-in is not bounded by the nnz limit; a `MemoryError` is reported unresolved, other failures propagate.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-45 | P1-BR7 outcome semantics | New tests (typed assessment, forged label, authority success/refusal paths) | `pytest tests/test_phase1_system_runtime_outcomes.py -q` | NOT RUN |
| DV-46 | P1-BR7 | Existing authority suites. Expected: explicit-run nodes that used to FAIL now SUCCEED (`test_multiphysics_conservation_history.py` STEADY case still passes by its own assertion); `test_system_runtime_big13_additions.py` (stub at line 64) and `tests/test_system_runtime_review_fixes.py::test_h2_*` / `test_r2_*` drive the authority with a SimpleNamespace "converged" stub and is now refused ("no run record") -- it must be rewritten on a real run record, not the check weakened | `pytest tests/test_multiphysics_conservation_history.py tests/test_system_runtime_external_providers.py tests/test_system_runtime_big13_additions.py tests/test_system_runtime_review_fixes.py flagships -q` | NOT RUN |
| DV-47 | P1-BR7 | Rewrite of the H2 state-uncertainty tests on a real stateful coupled run | new test | NOT WRITTEN |

### Outcome semantics after P1-BR7

| Plan | Window outcomes | Run outcome | Node |
| --- | --- | --- | --- |
| explicit | explicit_completed / event_aligned | COMPLETED_EXPLICIT (no convergence claim; splitting error open) | succeeds, `coupling_outcome=completed_explicit`, every output UNKNOWN with that note |
| implicit | converged / event_aligned, final iteration satisfied and every required edge measured | CONVERGED (fixed-point residual only) | succeeds, `coupling_outcome=converged` |
| either | any iteration_limit / participant_refused / transfer_refused | NOT_COMPLETED | fails, nothing exposed |
| either | a label the plan cannot produce, an unmeasured required edge, a gap between windows, a plan that does not validate against the graph | NOT_COMPLETED | fails, nothing exposed |

Unchanged and still enforced first: graph and plan fingerprints, required conservation, untraced external providers.
New: a non-record return is refused even for a fixed runtime, and the record's `run_id` must be the one this call
requested. `assess_coupling_numerical_error` turns an inconsistent, unmonitored or unconverged label into an
UNBOUNDED source.

### Unverified assumptions (P1-BR7)

- Window contiguity is checked by exact float equality of consecutive boundaries; records produced by this runtime
  (before or after P1-BR4) satisfy it by construction.
- `assess_run_outcome` lives in the certified `runtime.py` so the certified authority gains no new import edge; the
  lazy import from `numerical_error.py` adds an uncertified -> certified edge only.

### Phase 1 static review (read-only, nothing executed) and what it changed

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| 1 | MAJOR | Mutant N60d no longer matches `planning.py`; `tests/test_mutation_population_v4.py::test_every_folded_mutation_still_matches_the_source_it_names` will fail | Recorded (DV-41). The population is certification-pinned; replacement mutant on the typed admission line needs OD-3. Not edited. |
| 2 | MAJOR | Authority tests that feed a `SimpleNamespace` stub run (`tests/test_system_runtime_review_fixes.py` `_coupled_stub`: `test_h2_*`, `test_r2_*`; `tests/test_system_runtime_big13_additions.py:64` extractor/artifact test) will get "no run record" | Recorded (DV-46, DV-47). The refusal is the fix (a stub's "converged" is a caller assertion); those tests need a real run record. Not rewritten in Phase 1. |
| 3 | MINOR | `test_multiphysics_conservation_history.py` comment described pre-BR7 behaviour | Fixed (comment only; assertion unchanged). |
| 4 | MINOR | `assess_run_outcome` fell back to no required edges when the plan did not validate | Fixed: an implicit plan that does not validate requires every edge. |
| 5 | MINOR | Window-gap check used float equality | Fixed: `exact_seconds` on both sides. |
| 6 | MINOR | STEP inputs were aligned exactly while events got ulp absorption | Fixed: STEP alignment uses the same resolution as the run loop (k ulps of the width, one of the start, one of the instant); the loop then lands on the sample. |
| 7 | MINOR | A stored implicit record whose criteria miss a lagged edge no longer loads (record validates its plan) | Recorded; none found in the repository. |
| 8 | MINOR | `MappingDiagnostics.provenance` was a mutable dict | Fixed: frozen on construction, `detach`ed on serialization. |
| 9 | MINOR | Conditioning of sparse 1000 < n <= 2000 (and GMRES) now estimated or unresolved; `stability.py` then records "singular or unresolved" | Recorded (DV-43): the safe direction; stability decisions change. |
| 10 | MINOR | degC refused for conservative remap although an exactly covering first-order remap is affine-invariant | Kept as a design choice (no conservation claim for an offset scale); owner may relax. |

## Phase 2 — Unified solver & multiphysics architecture (2026-10-17)

Branch `feat/phase2-unified-solver-architecture` (worktree `D:/forge-phase2`), stacked on Phase 1 `6249c2d2`
(itself on `origin/main` `de11dffa`; neither pushed nor merged). Rocks are P2-BR8..P2-BR12. **No test of any kind
was executed** (owner direction): only `py_compile`, import checks and `git diff --check`. Every changed capability
is IMPLEMENTED / UNVERIFIED at most; every touched pinned file is UNCERTIFIED until OD-3. The Phase 1 items above
(N60d, stub-run tests, DV-34, 3D remap, mesh-weighted residual, participant time tolerance, no coupling-error bound)
are NOT resolved by Phase 2 unless a row below says so.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-48 | P2-BR8 authority, deferred outputs, isolation, exact NONE relaxation | New tests | `pytest tests/test_phase2_coupling_authority.py -q` | NOT RUN |
| DV-49 | P2-BR8 | Electrothermal parity: native loop vs runtime build (outcome, iterations, outputs <= 1e-9) on NOMINAL and TWO_STAGE; iteration-limit parity | included in DV-48 | NOT RUN |
| DV-50 | P2-BR8 | Existing suites touched by the NONE-relaxation change (implicit unrelaxed runs now deliver the transfer bit-exactly; iterates may move by an ulp) and the electrothermal provenance text (unrelaxed runs unchanged) | `pytest tests/test_electrothermal_vertical.py tests/test_electrothermal_fixed_point_relaxation.py tests/test_stateful_multiphysics_runtime.py tests/test_big9_review_runtime_fixes.py tests/test_multiphysics_window_control.py -q` | NOT RUN |

### P2-BR8 status: PARTIAL / UNVERIFIED

- Authority: `MultiphysicsRuntime`, declared in `execution/multiphysics/authority.py` (`COUPLING_PATHS`,
  `coupling_authority()`); one outcome vocabulary (`fixed_point_outcome`).
- Not migrated: the electrothermal fixed point (`systems/electrothermal/coupled.py`) still decides its own
  convergence on the product path. A runtime-equivalent build exists (`systems/electrothermal/runtime_adapter.py`)
  for unrelaxed plans only. Remaining: execute parity (DV-49); relaxation semantics (runtime relaxes every serial
  edge, the native loop only torn values); TRANSFER_REFUSED as a recorded stop; `credibility.CouplingEvidence` on the
  runtime record.
- Fixed in passing: the native loop's provenance claimed "no relaxation" for relaxed runs (false support); NONE
  relaxation rounded `old + 1*(new-old)`; one participant object under two concurrent ids was not refused.

### Unverified assumptions (P2-BR8)

- The runtime compares the torn change in the port's base unit, the native loop in the plan's ratio-scale unit; they
  can disagree only by rounding at the tolerance boundary.
- `ResultParticipant` sets `internal_converged` from the result's convergence state (stricter than the native loop,
  which ignores it); every electrothermal executor reports CONVERGED or NOT_APPLICABLE, so parity is expected.
- A steady participant's deferred initial outputs are never read on forward serial edges; any other edge is refused.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-51 | P2-BR9 transfer engine | New tests (supported table, tet->tet conservation/range/permutation, degenerate refusal, vector components, KD-tree and bucket index vs brute force, provenance, array digests) + the Phase 1 conservative suite (its 3D refusal test now refuses hexahedra; tet->tet is supported) | `pytest tests/test_phase2_field_transfer.py tests/test_phase1_conservative_cell_mapping.py -q` | NOT RUN |
| DV-52 | P2-BR9 | Existing mapping, field and mesh suites: every non-identity mapping now records provenance (run digests of field-mapped runs change); nearest/point location now go through the indexes (values must be unchanged) | `pytest tests -q -k "mapping or field or mesh or spatial" -m "not expensive"` | NOT RUN |
| DV-53 | P2-BR9 | Time and memory of the indexed searches and the tetrahedral overlap on a realistic interface (no performance claim is made) | owner-authorized benchmark | NOT RUN |
| DV-34 | P1-BR2 (carried) | End-to-end field-mapped coupled run through `TransferEngine` | new test | NOT WRITTEN (still) |

### P2-BR9 status: IMPLEMENTED / UNVERIFIED (scope as declared, not universal)

- Authoritative engine: `execution/multiphysics/mapping.FieldMapper`; `transfer_support` admits only the rows of
  `SUPPORTED_TRANSFERS`; `FIELD_TRANSFER_PATHS` declares the other mapping code (P1 interpolation on `SpatialMesh`,
  a separate data model used by `coupling/adapters`; the structured support-contract checker).
- Conservative remap now: structured/structured, 2D triangle/convex-quad/structured pairs (Phase 1), and
  tetrahedron -> tetrahedron (exact convex-polytope intersection: vertex-in-other plus edge-facet points, Qhull
  hull volume). Refused: hexahedra (a trilinear hex is not convex in general), 2D<->3D, node fields, offset units,
  partial coverage. Vector fields: component by component in one shared frame.
- Search: exact bucket index (superset, ascending) for point location and overlap candidates; KD-tree nearest with
  the exhaustive lowest-index tie rule. Acceptance is always the unchanged exact test.
- Provenance on every method (supports, locations, components, search; interpolations say they are not conservative).
- Data plane: `FieldValue.store` passes a float64 array (byte-identical encoding); `BulkDataResolver.resolve_array`
  reads without a Python tuple; meshes and fields read through it.

### Unverified assumptions (P2-BR9)

- Qhull returns the convex-hull volume of the collected points to round-off and raises only for degenerate (flat)
  sets; duplicate points (shared vertices) are tolerated. A 1e-12 * cell-size inside tolerance admits boundary points.
- The bucket grid is capped at 256 buckets per axis; a mesh with very uneven cell sizes registers large cells in
  many buckets (memory not bounded by cell count alone).
- `nearest_sites` reproduces the exhaustive choice whenever the KD-tree distance and the einsum distance agree to
  16 eps relative, which bounds their rounding difference for coordinates of ordinary magnitude.
- Forward mapping error stays UNQUANTIFIED for every non-identity method (P1-BR3); nothing here bounds it.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-54 | P2-BR10 checkpoint identity and recovery | New tests (build/problem binding, drift, ambiguity, cold start on record, qualified conversion, provider-participant build drift and token corruption) + existing routing suite | `pytest tests/execution/orchestration -q` | NOT RUN |
| DV-55 | P2-BR10 | Real PyBaMM restore with the new build tag and content check (needs the 3.13 / WSL battery env) and the battery-cooling flagship (provider_state_id of its cell checkpoints changes) | `pytest flagships tests/test_multiscale_runtime.py -q` in the provider env | NOT RUN |
| DV-56 | P2-BR10 | External-provider failure and recovery end to end (an ExternalSolverParticipant failing inside a window, rollback, retry on a shorter window, provider records) | new test | NOT WRITTEN |

### P2-BR10 status: IMPLEMENTED / UNVERIFIED

- Orchestration (`execution/orchestration/checkpoint.py`, both runners, `SimulationPlan.problem_digest`): a
  checkpoint is bound to solver id, solver build and problem digest; adoption refuses another build or problem;
  resume refuses build drift, another problem, and ambiguity (recorded build or problem vs none stated); a backend
  whose stated build changes between attempts is refused; a fallback cold-starts and the cold start is recorded;
  failed/diverged attempts never supply state (unchanged).
- `CheckpointConversion`: the only route for one solver's state into another -- both builds named, a stated
  qualification, and a target backend that declares `accepts_converted_checkpoints`. No conversion exists in the
  repository, so every cross-solver fallback cold-starts today.
- `coupling/adapters.provider_participant` (the open ERT item): execution builds must stay the first (and, with
  `expected_build`, the admitted) build; checkpoints carry a build tag; restore refuses another participant, another
  build, and a token whose content does not hash to the record's state digest.
- PyBaMM `cell_participant`: restore refuses another participant, a checkpoint without this build's tag (including
  pre-Phase-2 checkpoints), and a token whose solution does not hash to the recorded digest.
- `ExternalSolverParticipant` sealing (ERT Phase 1) was reviewed and left unchanged.

### Unverified assumptions (P2-BR10)

- A backend's `solver_build` string is its own statement of build identity; the runner compares it and records it,
  it cannot verify it. Backends that state none keep the pre-Phase-2 behaviour (ambiguity refuses only a checkpoint
  that does record a build).
- PyBaMM's solution state digest (`last_state.y` bytes) is assumed to identify the restorable state, as before.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-57 | P2-BR11 problem identity, corroboration, selection | New tests (equivalent and non-equivalent representations, excluded aspects, corroboration refusals, equal provider digests not trusted, qualified deterministic selection) | `pytest tests/test_phase2_solver_selection_and_identity.py -q` | NOT RUN |
| DV-58 | P2-BR11 | Existing comparison suites and the flagships that call `compare_providers` (serialized form unchanged when no equivalence is attached) | `pytest tests/test_provider_boundary.py tests/test_big11_second_rereview_fixes.py flagships -q` | NOT RUN |
| DV-59 | P2-BR11 | Selection with REAL admitted qualifications (route runs + ledger) instead of the patched admission used in the unit tests | new test | NOT WRITTEN |

### P2-BR11 status: IMPLEMENTED / UNVERIFIED

- `providers/problem_identity.py`: `CanonicalProblem` (ten provider-independent aspects; quantities canonicalized to
  base units with the repository identity rule; absolute vs difference kept apart; discretization, mesh, solver,
  solver configuration, tolerances and provider inputs refused as aspects); `compare_problems` -> SAME_PROBLEM /
  DIFFERENT_PROBLEM (names the aspects) / UNDETERMINED (never promoted); `ProblemBinding` records an adapter's
  declared translation of a canonical problem into one execution.
- `providers/compare.corroborate`: compares only after SAME_PROBLEM and one binding per record naming its execution
  and its side's canonical problem; the record states what it establishes and what it does not (validation,
  physical truth, model form, translation fidelity, numerical error). Independence and unit rules unchanged.
- `providers/selection.py`: `SolverRequirement` (scope mandatory), `select_solvers` -> `SolverSelection` record:
  available, capability covers the requirement, an admitted qualification of the exact build and adapter covers the
  scope; deterministic order = explicit preference, then provider id.
- False-support pathway found and contained, not removed: `compare_providers` still compares two records with no
  same-problem check (each side's `problem_digest` is provider-specific). Its comparisons now report
  `same_problem_established = False`; making that a refusal changes flagship level-5 evidence (owner decision
  OD-P2-3).

### Unverified assumptions (P2-BR11)

- A canonical declaration is as faithful as its author; two authors can state one problem differently (a false
  DIFFERENT_PROBLEM) -- the safe direction. A false SAME_PROBLEM needs two identical declarations of different
  problems, i.e. a declaration that omits what differs; requiring every aspect bounds but does not exclude that.
- Boundary-condition kinds, regimes and equation classes are matched through qualification scope tokens because
  `ProviderCapability` does not declare them; the tokens' meaning is the issuing route's.
- Numerical error of each side is not part of a corroboration; agreement within tolerance says nothing about it.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-60 | P2-BR12 external-participant infrastructure | New tests with LABELLED MOCK sessions: end-to-end field-mapped run (closes DV-34 as WRITTEN), interface contract, mock refusal/admission, failure classification, maturity table | `pytest tests/test_phase2_external_coupling.py -q` | NOT RUN |
| DV-34 | P1-BR2 (carried) | End-to-end field-mapped coupled run through `TransferEngine` | written as `tests/test_phase2_external_coupling.py::test_a_field_coupled_run_maps_the_flux_conservatively_and_records_it` | NOT RUN (now written) |
| DV-61 | P2-BR12 | Re-run the real FEniCSx coupling suite on THIS tree (last recorded: 133 passed on a BIG-14-era tree); the interface contract applied to its thermal <-> electrical graph | WSL: `FORGE_PROVIDER_ENVS=$HOME/mm/root/envs $HOME/mm/root/envs/fenicsx/bin/python -m pytest -q providers/fenicsx/tests` | NOT RUN |
| DV-62 | P2-BR12 | Real FE <-> CFD coupled execution (FEniCSx solid + OpenFOAM or SU2 fluid, conjugate heat transfer) | BLOCKED (policy) | NOT WRITTEN |
| DV-63 | P2 all | Performance and memory regressions of the Phase 2 paths (indexed search, tet overlap, selection) | owner-authorized benchmark | NOT RUN |

### P2-BR12 status: PARTIAL / UNVERIFIED (end-to-end FE/CFD BLOCKED)

Implemented (provider-neutral infrastructure, policy-permitted):
- `ExternalProviderIdentity.mock`: a labelled mock is part of the sealed identity (real identities unchanged);
  `MultiphysicsAuthority` refuses mock external participants unless `allow_mock_participants=True`, then labels them
  (`mock_participants` diagnostic) and exempts only them from the provider-record trace requirement.
- `ExternalProviderFailure`: any non-scientific exception from a session (process, file, library) is a classified
  refusal naming build and phase; scientific errors -- including the retryable `CouplingWindowNotConverged` -- keep
  their type.
- `execution/multiphysics/interface_exchange.py`: `InterfaceContract` types each interface edge as FLUX_DENSITY
  (field-valued, conservative or identity mapping, ratio-scale unit, declared sign convention) or INTENSIVE; a two-way
  interface needs one flux edge and one intensive edge back between the same participants;
  `interface_flux_balance` reads the per-window transfer conservation residuals as DIAGNOSTICS (UNKNOWN where none
  was recorded), never bounds.
- `authority.EXTERNAL_PROVIDER_COUPLING`: per provider, adaptation / field exchange / coupled execution stated
  separately (FEniCSx executed historically on an older tree; OpenFOAM and SU2 adaptation only; FE/CFD BLOCKED);
  `COUPLING_PATHS` now also declares the provider-participant adapters and the preCICE external engine.

BLOCKED -- real FE <-> CFD conjugate heat transfer (owner decision OD-P2-1):
- Policy: a new capability foundation under the active epic `battery.thevenin_1rc`; EXC-1 is open, so a second
  exception triggers the anti-loophole review. Not authorized by this prompt.
- Engineering prerequisites, recorded so they are not rediscovered: (1) an OpenFOAM (or SU2) time-window session --
  case restart per window, a boundary-condition file update for the interface (temperature or flux) before each
  window, read-back of the interface boundary field after it, deterministic snapshot/restore of the time directory;
  (2) a FEniCSx boundary-trace output of the conduction flux on the interface facets; (3) interface meshes as
  `UnstructuredMesh` supports (2D triangles/quads on a shared surface, or matching tetrahedral layers) so the
  conservative remap applies; (4) a declared conjugate-heat-transfer model with applicability conditions in the
  ledger; (5) the WSL envs (`~/mm/root/envs/fenicsx`, the `battery` env with OpenFOAM v2412 / SU2 8.5.0) on PATH via
  `tools/wsl_env.sh`, `MSYS_NO_PATHCONV=1` for `/mnt/d` paths.

### Unverified assumptions (P2-BR12)

- The mock sessions in the tests exercise transfer and record mechanics only; no conclusion about any real solver
  follows from them.
- `forge_precice` keeps its own fixed-point residual check outside the runtime (declared EXTERNAL_ENGINE).
