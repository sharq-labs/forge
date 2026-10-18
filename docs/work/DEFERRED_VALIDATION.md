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

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-64 | P2 review | Regression tests for the four review MAJORs (forward tear, asserted identity, canonical numbers, fresh-restore build pin) | `pytest tests/test_phase2_review_regressions.py -q` | NOT RUN |

### Phase 2 static review (read-only, nothing executed) and what it changed

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| M1 | MAJOR | A redundant (forward) tear made the runtime build read a torn value in the same sweep, unlike the native lag | Fixed: `runtime_equivalent` refuses forward tears (before `check_against`). |
| M2 | MAJOR | `corroborate` accepted a caller-built or narrowed `ProblemEquivalence` | Fixed: it takes the two `CanonicalProblem`s and derives identity with every aspect required; `same_problem_established` also requires the full aspect set. |
| M3 | MAJOR | Provenance on every mapping method changes the serialized form of field-mapped run records (certified file; the docstring promised otherwise) | Kept deliberately (exact field/mesh provenance is a BR9 requirement); docstring corrected; recorded as an identity change for OD-3 (DV-52). No committed JSON pins these records. |
| M4 | MAJOR | A fresh provider participant restored a checkpoint of any build and adopted whatever ran next | Fixed: the restore pins the checkpoint's build tag and the first execution must match it. Untagged checkpoints are pre-execution state (declared state only) and still restore. |
| m | MINOR | `require_build` ran before the `succeeded` check, hiding failure reasons | Fixed (failure first). |
| m | MINOR | `"1.0"` and `1.0` collided, `1` and `1.0` differed | Fixed: plain numbers canonicalized by value (12 significant digits) and tagged apart from text. |
| m | MINOR | Cold-start note repeated per refinement attempt | Fixed (once per solver). |
| m | MINOR | An admitted mock was labelled only in diagnostics | Fixed: every output's UNKNOWN note names the mock participants. |
| m | MINOR | `ResultParticipant` treats a failed termination as a numerical failure; the native loop ignores termination | Documented in the adapter's correspondence list. |
| m | MINOR | Serial CONSTANT/AITKEN relaxation requires every edge, but a deferred edge may not carry a criterion | Recorded limit: such plans are refused at initialization; seed every edge to use them. |
| m | MINOR | A termination condition on a deferred steady output refuses at start with a misleading message, participants not finalized on that raise | Recorded (refusal, not a silent pass); not changed. |
| m | MINOR | Pre-Phase-2 PyBaMM checkpoints (no build tag) are refused; provider_state_id of new checkpoints changes | Recorded (DV-55); in-process checkpoints only, none stored. |
| m | MINOR | `sign_convention` is metadata only; INTENSIVE edges unchecked | Recorded: the contract checks mapping/unit/pairing, not the sign of transferred values. |
| m | MINOR | Mock refusal happens after the run executes; build-drift break consumes an attempt; `converted_resume_point` does not re-check the problem (safe only because the caller checked it); legacy unbound checkpoints resume on any build; BoxIndex O(n^2) registrations for domain-sized boxes; `session.identity` read not classified | Recorded, not changed. |

## Phase 3 — Advanced numerical & multiphysics engine (2026-10-17)

Branch `feat/phase3-advanced-numerical-multiphysics` (worktree `D:/forge-phase3`), stacked on Phase 2 `2661b640`
(itself on Phase 1 `6249c2d2` on `origin/main` `de11dffa`; none pushed or merged, re-verified 2026-10-17). Rocks are
P3-BR13..P3-BR17. **No test of any kind was executed** (owner direction): only `py_compile`, import checks and
`git diff --check`. Every changed capability is IMPLEMENTED / UNVERIFIED at most; every touched pinned file is
UNCERTIFIED until OD-3. Phase 1 (DV-31..DV-47) and Phase 2 (DV-48..DV-64) items are NOT resolved by Phase 3 unless a
row below says so.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-65 | P3-BR13 health, damped Newton, chain acceptance, weighted norm | New tests | `pytest tests/test_phase3_br13_numerical_stability.py -q` | NOT RUN |
| DV-66 | P3-BR13 | Existing robust-solve and heater-chain suites: a chain with differing tolerances is now refused (every existing chain declares identical ones); `NumericalDiagnostics` serializes unchanged when the new fields are unset | `pytest tests/numerical tests/domains/electrical -q` | NOT RUN |
| DV-67 | P3-BR13 | Weighted vs unweighted field norms on real coupled runs with non-uniform supports (does `l2_measure` change convergence decisions where `l2` misled?); existing coupling suites (unchanged: no plan declares `l2_measure`) | `pytest tests -q -k "multiphysics or coupling" -m "not expensive"` + new comparison test | NOT RUN / comparison NOT WRITTEN |
| DV-68 | P3-BR13 | Nonlinear robustness campaign: Newton / Newton-Armijo vs MINPACK hybr / lm on a declared problem set; failure-class distribution only, no performance claim | owner-authorized benchmark | NOT WRITTEN |

### P3-BR13 status: IMPLEMENTED / UNVERIFIED

- `numerical/health.py`: `NumericalFailureClass` (non_finite, diverging, stagnating, step_stagnation,
  line_search_failed, singular_jacobian, iteration_limit, tolerance_not_met, backend_failure); history detectors with
  the coupling runtime's rules; `ResidualScaling` (declared, never inferred); `RESIDUAL_IS_NOT_AN_ERROR_BOUND`.
- `numerical/nonlinear.py`: `DampedNewtonProvider` (`newton`, `newton_armijo`) for square NONLINEAR_ROOT problems --
  every acceptance value explicit; declared or finite-difference Jacobian; optional `condition_limit`; a vanishing step
  with a large residual is STEP_STAGNATION, never convergence; every failure classified; the last iterate withheld.
- `numerical/robust.py`: a fallback chain cannot loosen acceptance (identical tolerances, or one `ChainAcceptance`
  re-evaluated from the problem's own residual on every converged attempt); attempts carry the failure class.
- `ResidualNorm.L2_MEASURE` (`execution/multiphysics/field_measures.py`): measure-weighted RMS; the unweighted `l2`
  stays as it was and is documented as RMS over stored values.
- `numerical/mesh_quality.py`: measures, orientation, inversion, degeneracy (64 eps h^d), shape quality.

Unsupported regimes (refused, not approximated): non-square or least-squares "root" problems; finite-difference
Jacobians above 4096 unknowns; `l2_measure` on scalar edges, quadrilateral node fields and hexahedra; trust-region
globalization in the new provider (MINPACK `hybr` / `lm` remain the trust-region methods).

### Unverified assumptions (P3-BR13)

- The Armijo slope `-2 phi` assumes the linear solve is exact; a nearly singular Jacobian without a declared
  `condition_limit` can make the direction poor (it is then classified by the line search or the history, not hidden).
- The weighted RMS of a vector field gives every component of a site the site's weight (one shared frame).
- `DampedNewtonProvider`'s step-stagnation test uses `step_rtol * (1 + ||x||_inf)` in normalized space.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-69 | P3-BR14 accelerator, IMVJ | New tests | `pytest tests/test_phase3_br14_iqn_imvj.py -q` | NOT RUN |
| DV-70 | P3-BR14 | Existing IQN-ILS suite: the arithmetic moved to `acceleration.py` unchanged (same operations in the same order); error messages kept | `pytest tests/test_multiphysics_iqn_ils.py tests/test_multiphysics_window_control.py -q` | NOT RUN |
| DV-71 | P3-BR14 | IMVJ vs ILS on NONLINEAR coupled maps, ill-conditioned or dependent histories, field-valued interfaces; convergence and fallback recorded, no rate claimed | new tests | NOT WRITTEN |
| DV-72 | P3-BR14 | Accelerator history across window rejection end to end (an IMVJ run under window control with subdivisions and error rejections) | new test | NOT WRITTEN |

### P3-BR14 status: IMPLEMENTED / UNVERIFIED

- One accelerator (`execution/multiphysics/acceleration.py::InterfaceQuasiNewton`) for IQN-ILS and IQN-IMVJ;
  `RelaxationController` delegates; the runtime begins each attempt with its exact duration and ends it as accepted or
  rejected; a fresh controller per run.
- IQN-IMVJ: `J = J_prev + (W - J_prev V)(D V)^+ D`, `x <- H(x) - J r` (`J_prev = 0` gives IQN-ILS). Carried only from an
  accepted, CONVERGED window into one of the same exact duration, layout and supports; discarded (recorded) on
  rejection/rollback, event re-run, iteration-limit acceptance, layout/support change, `imvj_reuse_windows` reuses, or
  a non-finite update (which also falls back to constant relaxation for that step). Interfaces above
  `imvj_max_dimension` are refused. IMVJ additionally drops secant columns below `iqn_filter` x the largest column.
- Convergence coverage is unchanged: every required edge is still judged on its UNRELAXED transfer.
- Uncertainty of an accelerated iterate: UNKNOWN. No Gauss-Seidel IQN variant is admitted.
- Record: `final_outputs["_acceleration"]` always for IMVJ; for ILS only after a non-routine event.

### Unverified assumptions (P3-BR14)

- A carried approximation is assumed useful only for windows of identical exact duration; windows of other lengths
  (subdivided retries, schedule-forced ends) restart from zero. This is conservative, not optimal.
- `numpy.linalg.pinv` and `lstsq` agree to round-off on the filtered (full column rank) secant matrix, so IMVJ with
  `J_prev = 0` reproduces IQN-ILS up to rounding, not bit for bit.
- Restart-free IMVJ can accumulate stale information; `imvj_reuse_windows` bounds it, it does not prove it harmless.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-73 | P3-BR15 error-aware windows, clocks, subcycling | New tests | `pytest tests/test_phase3_br15_window_error_control.py -q` | NOT RUN |
| DV-74 | P3-BR15 | Existing window-control, event-alignment and exact-time suites: window-controlled runs with schedule-forced short windows now record `forced_below_minimum_window`; participants reporting an end within the tolerance now produce `_time_grid` | `pytest tests/test_multiphysics_window_control.py tests/test_phase1_exact_time_windows.py tests/test_phase1_coupling_convergence_coverage.py tests/test_stateful_multiphysics_runtime.py -q` | NOT RUN |
| DV-75 | P3-BR15 | Error control with implicit coupling, IQN-IMVJ, event-capable participants, field-valued outputs, step-size memory; exact rational boundaries of the half windows | new tests | NOT WRITTEN |
| DV-76 | P3-BR15 | Temporal refinement study: step-doubling indicator vs observed local error on a problem with a known solution (is the indicator conservative for the actual participant schemes?) | new test / benchmark | NOT WRITTEN |

### P3-BR15 status: IMPLEMENTED / UNVERIFIED

- `WindowErrorControl` (plan, absent when unset): after a window converges it is re-executed as two half windows from
  the restored start; `eta = max |c - f| / (atol + rtol max(|c|, |f|))`. `eta <= 1` keeps the COARSE window
  (participants restored to its end, accelerator restored from a snapshot); `eta > 1` rejects it as
  `rejected_error_indicator` (never `subdivided`) and retries a shorter window through the existing bounded
  subdivision and step-size memory; exhaustion raises `CouplingWindowErrorNotControlled` (a retryable numerical
  failure). Event-cut windows are `not_assessed`; failed or unrepresentable halves reject.
- Schedule-forced windows below `minimum_window`: recorded, not refused (owner decision open, P1-BR4).
- Participant clock differences within the reporting tolerance: recorded in `_time_grid` (plan order).
- `subcycling.py`: the explicit in-window contract (zero-order input hold, window-end exchange, minimum substeps,
  declared substep budget).

Not an accuracy claim: the indicator is the local step-doubling difference; for an order `p >= 1` scheme in its
asymptotic range the coarse local error is 1x to 2x it, neither order nor regime is verified, and nothing bounds the
accumulated (global) error or model-form error. Without `error_control` window adaptation is convergence-driven only.

### Unverified assumptions (P3-BR15)

- Restoring every participant to the coarse end from a checkpoint taken there reproduces the coarse state exactly
  (deterministic restore is required and digest-checked by `_restore_all`).
- Half windows may be shorter than `minimum_window`; they are a measurement, not a schedule.
- Clock disagreements are recorded once per (window, attempt, participant) and never from the half windows of an
  assessment (review M4).

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-77 | P3-BR16 mesh validity, adaptation provenance | New tests | `pytest tests/test_phase3_br16_mesh_validity_and_adaptation.py -q` | NOT RUN |
| DV-78 | P3-BR16 | Existing adaptation and non-uniform conduction suites (the adaptation record gains provenance keys; the EXC-1 exit gate DV-27..DV-30 still stands) | `pytest tests/numerical/test_mesh_adaptation.py tests/domains/thermal_models/test_conduction1d_nonuniform.py -q` | NOT RUN |
| DV-79 | P3-BR16 | Mesh adaptation conservation and spatial/temporal refinement studies (transient non-uniform 1D, 2D/3D) | BLOCKED (policy, OD-P3-1/OD-P3-2) | NOT WRITTEN |

### P3-BR16 status: PARTIAL / UNVERIFIED

Implemented (inside existing authority): grid digests and per-cycle provenance (grid evaluated, cells marked,
largest neighbour ratio, superseded grids); round-off bisections skipped; `require_supported_adaptation` refuses
everything outside the EXC-1 A1 slice; mesh validity checks (`mesh_quality`, `assess_support`); relaxation and the
accelerator never mix values on two supports.

BLOCKED (EXC-1 enumerates its allowed work; each needs an owner-approved amendment): coarsening, transient /
time-adaptive solves on adapted grids (no conservative state transfer between grids), triangle and tetrahedron
refinement, coupled field transfer between changing meshes (the runtime registers supports at construction and
refuses an unregistered one).

Spatial/temporal relationship as built: spatial adaptation exists for steady 1D only; temporal adaptation is
window-level (convergence- and, when declared, error-indicator-driven); there is no joint space-time adaptivity, and
an adapted grid never carries a transient state.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-80 | P3-BR17 nonlinear PDE contract, moving-mesh kinematics | New tests | `pytest tests/test_phase3_br17_nonlinear_pde_and_moving_mesh.py -q` | NOT RUN |
| DV-81 | P3-BR17 | Nonlinear PDE manufactured solutions through a real provider (e.g. FEniCSx Newton on a k(T) template) | BLOCKED (OD-P3-3) | NOT WRITTEN |
| DV-82 | P3-BR17 | Moving-mesh geometric conservation inside a real ALE scheme; coupled ALE restart and replay | BLOCKED (OD-P3-4) | NOT WRITTEN |

### P3-BR17 status: PARTIAL / UNVERIFIED (nonlinear PDE execution and ALE BLOCKED)

- Inventory: four linear Forge templates (steady/transient diffusion, plane-stress and thermoelastic elasticity);
  `forge_fenicsx` assembles them with a KSP solve; no provider implements a nonlinear PDE or any moving mesh.
- `pde/nonlinear.py` (contract only): no template is nonlinear, so every one is refused; `NonlinearSolveSpec`,
  `InitialGuess` and `admit_nonlinear_execution` (re-derives convergence from Newton histories; refuses false
  convergence) are what a future provider would be held to.
- `numerical/moving_mesh.py` (kinematics only): reference vs current configuration, displacement (m) and mesh
  velocity (m/s) at exact times; inversion or collapse refused at any instant of a step; the discrete GCL residual of a
  declared time rule (midpoint exact in 2D, violated on tetrahedra; two-point Gauss exact in 3D); digest-checked
  history and rollback; fields bound to the mesh state; topology changes and opened interfaces refused.
- `require_ale_formulation` refuses: no governing equation has an ALE form in Forge; nothing here is ALE support.

### Unverified assumptions (P3-BR17)

- Vertex motion is linear in time within a step; another motion law changes the measure polynomial and the GCL
  exactness degrees.
- `numpy.roots` finds the interior critical points of the measure polynomial to round-off; the degeneracy floor is
  64 eps h^d.

| ID | Rock | Deferred test / check | Command (when authorized) | Status |
| --- | --- | --- | --- | --- |
| DV-83 | P3 all | Real-provider compatibility: the FEniCSx coupling and PDE suites on THIS tree | WSL: `FORGE_PROVIDER_ENVS=$HOME/mm/root/envs $HOME/mm/root/envs/fenicsx/bin/python -m pytest -q providers/fenicsx/tests` | NOT RUN |
| DV-84 | P3 all | Runtime and memory: IMVJ dense n x n approximation, step doubling (3 window executions per accepted window), per-cell mid-step inversion loop, finite-difference Jacobians | owner-authorized benchmark | NOT RUN |
| DV-85 | P3 all | Structural guards for the new files: layering, certified-dependency closure, core purity string count, pin portability | `pytest tests/test_core_api_layering.py tests/test_certified_dependency_closure.py tests/test_heterogeneous_ngspice.py tests/test_pin_portability.py -q` | NOT RUN |
| DV-86 | P3 all | FAST and SCIENTIFIC tiers on the Phase 1+2+3 tree, diffed against a pristine baseline | `python -m pytest -m "not expensive" -q -n 4` / `python -m pytest -m "not campaign" -q -n 4` | NOT RUN |

### Certification impact (Phase 3)

Pinned by `certification/current_core_v2.json` and changed (UNCERTIFIED until OD-3):
`execution/multiphysics/{convergence,relaxation,runtime}.py`, `numerical/core.py`, `scientific/multiphysics/plan.py`.
New files inside certified SCOPE patterns (`execution/**`, `numerical/**`, `pde/**`), not yet in the pinned list:
`execution/multiphysics/{acceleration,field_measures,subcycling}.py`, `numerical/{health,nonlinear,mesh_quality,moving_mesh}.py`,
`pde/nonlinear.py`; unlisted files changed: `numerical/{robust,mesh_adaptation}.py`. New certified -> unpinned import
edges (must be pinned or declared at recertification): `convergence.py -> field_measures.py`,
`relaxation.py -> acceleration.py`. No mutant of the V4 population targets a changed line.

Serialization identity: unchanged for every existing record type when the new fields are unset (policies, diagnostics,
strategy records, window control). Deliberate changes, recorded: IQN-ILS runs gain `_acceleration` only after a
non-routine event; window-controlled runs gain `forced_below_minimum_window` events; runs whose participants report
an end that differs within tolerance gain `_time_grid`; the 1D adaptation record gains provenance keys.

### Phase 3 static review (read-only, nothing executed) and what it changed

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| M1 | MAJOR | A chain could loosen acceptance through `residual_scales` (an option, not a tolerance) | Fixed: providers declare `acceptance_options`; the chain compares them with the tolerances or needs a `ChainAcceptance`; test added. |
| M2 | MAJOR | `weighted_rms` divided by `components x sum(w)`, contradicting its definition (a written test would fail) | Fixed: `sqrt(sum w_i |v_i|^2 / sum w_i)`, the site-vector norm. |
| M3 | MAJOR | The runtime's restorability check for error control was unreachable (`validate_against` refuses first); the test matched the wrong text | Fixed: dead block removed, test matches the real refusal; the monitored tolerance unit is checked at construction (MINOR 4). |
| M4 | MAJOR | Clock records: undocumented identity change, one entry per iteration, entries from rejected attempts and half windows | Fixed: once per (window, attempt, participant) with `window_index` and `attempt`; suspended during half windows; identity change stated in code and here. |
| M5 | MAJOR | IMVJ: a round-off first residual set a ~1e13 edge weight, amplifying round-off into the carried approximation | Fixed: an IMVJ edge scale is set only by a residual above 64 eps x the image RMS (IQN-ILS arithmetic unchanged). |
| m | MINOR | Event-cut windows skipped error control without saying so in the entry | Fixed: `accepted: true, error_assessed: false` and the notice. No run-level count is kept. |
| m | MINOR | An assessment that raised left the attempt open | Fixed: the attempt is closed as rejected before the error propagates. |
| m | MINOR | The runtime notice inverted the step-doubling relation | Fixed: the coarse local error is 1x-2x the difference. |
| m | MINOR | The PDE admission accepted a CONVERGED record listing only converged steps; it did not count line-search factors | Fixed: `expected_steps` is required and every step 0..n-1 must appear; one factor per iteration. |
| m | MINOR | Non-integral moving-mesh connectivity was truncated silently | Fixed: refused. |
| m | MINOR | The adaptation record serializes its provenance keys unconditionally | Kept deliberately (the record is not pinned anywhere); recorded as an identity change. |
| m | MINOR | `condition_limit` compares a 1-norm lower bound for large sparse Jacobians with an unqualified limit | Recorded (it can only refuse; the record names the method). |
| m | MINOR | Hard (non-numerical) errors inside a half window abort the run | Recorded (a refusal, never a pass). |

## Phase 3.5 — Engineering foundation completion (2026-10-18)

Branch `feat/phase35-engineering-foundation-completion` (worktree `D:/forge-phase35`), on Phase 3 `7389f4b4` (on Phase 2
`2661b640`, Phase 1 `6249c2d2`, `origin/main` `de11dffa`; none pushed or merged, re-verified 2026-10-18). **No test of
any kind was executed**: only `py_compile`, import checks and `git diff --check`. DV-31..DV-86 are preserved and not
resolved by Phase 3.5 unless a row says so. Policy-blocked scope: `docs/work/PHASE_3_5_POLICY_PROPOSALS.md`.

| ID | Workstream / capability | Required test | Expected evidence | Affected claims | Certification impact | Status |
| --- | --- | --- | --- | --- | --- | --- |
| DV-87 | WS1 same-problem admission | `pytest tests/test_phase35_ws1_same_problem_admission.py -q` | every assertion passes: diagnostics never reach level 5; pre-rule, relabelled, tampered and hand-forged records refused; re-derivation from stored canonical problems | every level-5 (independent-provider) ladder claim | `providers/{compare,problem_identity}.py` in certified SCOPE (pattern): OD-3 | NOT RUN |
| DV-92 | WS1 | Existing suites whose fixtures or expectations were updated: `pytest tests/test_engineering_contracts.py tests/test_engineering_round5_fixes.py tests/test_provider_boundary.py tests/test_phase2_solver_selection_and_identity.py flagships/tests/test_flagship_ladders.py flagships/tests/test_flagship_portfolio.py -q` | pass; `cavity_re100` and `structure_flagship` bundles REFUSED (`same-problem`), the other six verify | flagship ladders and committed bundles | test files pinned by recertification scope | NOT RUN |
| DV-93 | WS1 | Regenerate the cavity (OpenFOAM/SU2) and structure (FEniCSx/CalculiX/Code_Aster) flagship bundles in their provider envs, so their level 5 is decided by admitted corroboration; update `BUNDLE_DIGESTS` and the reports; run `providers/su2`, `providers/calculix` and the flagship real-provider tests | regenerated bundles verify; level 5 REACHED only if within tolerance AND admitted | the two flagship reports' level-5 statements (currently STALE: the committed bundles no longer verify) | flagships are outside the core certificate | NOT RUN (real-provider runs) |
| DV-88 | WS2 parity fixtures | `pytest tests/test_phase35_ws2_electrothermal_migration.py -q` | outcome, iteration count, per-iteration largest change and final values equal to the native loop within 1e-9 on NOMINAL, TWO_STAGE, relaxed, iteration-limit and refused-transfer cases | any claim that the runtime may replace the native electrothermal loop | `runtime.py`, `plan.py` (pinned list), `steady.py`, `authority.py` (SCOPE): OD-3 | NOT RUN |
| DV-89 | WS2 | Existing coupling and electrothermal suites (relaxation scope default unchanged; adapter 0.2.0): `pytest tests/test_phase2_coupling_authority.py tests/test_phase2_review_regressions.py tests/test_electrothermal_vertical.py tests/test_electrothermal_fixed_point_relaxation.py tests/test_multiphysics_iqn_ils.py tests/test_multiphysics_window_control.py -q` | pass | as DV-88 | as DV-88 | NOT RUN |
| DV-90 | WS2 | Candidate vs native on the golden pipeline and MCP electrothermal cases (U00048 refusal, relaxed product plans), boundary differences 1-7 measured | recorded differences only where the adapter lists them | migration decision (`RUNTIME_PATH_PARITY_VERIFIED`) | none beyond DV-88 | NOT WRITTEN |
| DV-91 | WS3 conjugate interface admission, maturity | `pytest tests/test_phase35_ws3_conjugate_interface.py -q` | pass | none (infrastructure; no FE/CFD claim exists) | `execution/multiphysics/conjugate_interface.py` (SCOPE) | NOT RUN |
| DV-94 | WS3 real FE <-> CFD coupling | real FEniCSx <-> OpenFOAM conjugate run, conservation diagnostics, analytic conjugate case | — | — | — | BLOCKED (policy, P35-E2) / NOT WRITTEN |
| DV-95 | WS4 transient 1D adaptation, conservative 1D transfer, coarsening, triangle refinement | adaptation / conservation / temporal / replay tests | — | — | — | BLOCKED (policy, P35-A4/A5) / NOT WRITTEN |
| DV-96 | WS5 provider-backed nonlinear PDE | manufactured solution, Newton failure, admission re-check through FEniCSx | — | — | — | BLOCKED (policy, P35-E1) / NOT WRITTEN |
| DV-97 | WS6 ALE | constant-state preservation, GCL, known mesh motion, rollback | — | — | — | BLOCKED (policy, P35-E3) / NOT WRITTEN |
| DV-98 | All | Structural guards: layering, certified-dependency closure, core purity, pin portability; FAST and SCIENTIFIC tiers on the Phase 1-3.5 tree diffed against a pristine baseline | pass or recorded failures | all | — | NOT RUN |
| DV-99 | Engineering program CDAR fixtures (OD-6) | `pytest tests/architecture/test_cross_domain_fixtures.py -q` | 4 fixture tests pass (RC geometric decay and a refused A -> V edge, symplectic-Euler invariant and energy bound, two-tank inventory and d'=d/(1+2r)); 5 gap pins pass, each recording a gap as it stands (A-1, A-2, A-9, A-11, force-edge energy-density rule); any gap pin that fails means its gap moved and must be rewritten | none: design findings, never domain evidence; required before any of M1-E3 is decided | test file only, outside certified SCOPE; no xfail (UNEXPECTED_SKIP in hardened runs) | NOT RUN |
| DV-100 | Integration 2026-10-18: I-8 vs P2-BR10 checkpoint authority | `pytest tests/test_provider_participant_checkpoints.py tests/test_external_participant_checkpoints.py tests/execution/orchestration/test_phase2_checkpoint_recovery.py tests/test_phase2_review_regressions.py tests/test_phase2_external_coupling.py -q`; then `providers/pybamm/tests/test_pybamm_checkpoint_identity.py` in the WSL battery env | pass; a checkpoint of another participant object is refused (`not issued`); build drift refused; the slot names the executed build | checkpoint/restore and recovery claims of provider and external participants | `external.py` and `coupling/adapters.py` are certification-relevant: OD-3 | NOT RUN |

### WS1 status: IMPLEMENTED / UNVERIFIED (closes OD-P2-3 by owner direction)

- Inventory of cross-provider comparison and corroboration entry points: `providers.compare.compare_providers` (now a
  DIAGNOSTIC), `providers.compare.corroborate` (the only corroboration), `engineering.ladder` level 5 and
  `check_provider_comparison` (bundle and summary verification), flagships `cavity_cfd` and `thermo_mechanical` (the only
  level-5 producers), `numerical.core.compare_executions` (agreement of two executions of ONE Forge problem digest; never
  corroboration; unchanged). Not routed through the new admission, recorded: the Core `scientific.consensus`
  (`CrossSolverConsensus`, domain-pinned routes such as `dc_consensus` that solve one declared problem object; Core frozen,
  unchanged) and the scientific verification ladder's EXTERNAL_SOLVER -> V5 category mapping.
- Stored records: a record re-derives its admission from the two canonical problems it carries; a pre-rule record
  (no admission), a relabelled diagnostic, an admitted record relabelled as a diagnostic, a consistently forged
  admission without canonical problems, or tampered problems are refused. Limit: two forged-but-identical canonical
  declarations still derive SAME_PROBLEM -- declaration fidelity is the adapter's claim (`ProblemBinding`).
- Identity changes (deliberate): every comparison record states `same_problem_established`; the diagnostic class;
  admitted records carry `canonical_problems`. Two committed bundles no longer verify (DV-93).

### WS2 status: PARTIAL / UNVERIFIED (code-complete candidate; migration gated on executed parity)

- `RelaxationPolicy.scope = "lagged_edges"`; runtime relaxes only lagged edges; `ResultParticipant(refuse_failed_sink=...)`
  (default unchanged); `runtime_adapter.run_coupled_via_runtime` returns a native `CoupledRun`;
  `run_electrothermal_coupling` keeps NATIVE as default; the candidate refuses without `acknowledge_unverified_parity`
  while `RUNTIME_PATH_PARITY_VERIFIED` is False. Seven boundary differences are listed in the adapter docstring.
- The product path (`coupled.run_fixed_point_coupling`) is unchanged and remains the convergence authority in production.

### WS3 status: PARTIAL / UNVERIFIED (infrastructure only; real FE/CFD BLOCKED)

- `execution/multiphysics/conjugate_interface.py`: interface-condition admission and a seven-stage provider-pair maturity
  record (`CHT_FENICSX_OPENFOAM`: no stage reached). No adapter, solver or mock numerical output.

### WS4-WS6 status: BLOCKED (policy)

Nothing implemented beyond Phase 3; narrow proposals P35-A4, P35-A5 (EXC-1 amendments) and P35-E1..E3 (new exceptions,
which trigger the anti-loophole OD-6 review) are drafted, not active.

### Phase 3.5 static review (read-only, nothing executed) and what it changed

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| B1 | BLOCKER | Committed cavity/structure bundles no longer verify; portfolio and round-5 tests still expected them to | Tests now assert the refusal (digest pins kept); round-5 F1 downgrades the stored links before its attack; regeneration is DV-93 |
| B2 | BLOCKER | Stale classification expectations (provider boundary, SU2, CalculiX tests) | Updated to the diagnostic class |
| M1 | MAJOR | Stored admission checked for shape only; consistent forgery promoted a pre-rule record; hand-built equivalence possible | Fixed: canonical problems stored and re-derived; hand-built equivalence refused; tests added |
| M2 | MAJOR | Flagship canonical problems mostly from shared constants | Fixed: derived from each provider's own problem object; equation class by provider problem type only |
| M3 | MAJOR | Maturity record could claim validation without execution/verification | Fixed: every earlier stage required; evidence refs labelled unresolved |
| m | MINOR | Undocumented boundary differences (undeclared-efficiency refusal; which failed result is named) | Documented (items 5-7) |
| m | MINOR | Parity gate is a caller assertion; CouplingEvidence cannot tell a candidate run | Recorded as OD-P35-4 |
| m | MINOR | `refuse_failed_sink=False` cannot let a value travel | Confirmed, no change |
| m | MINOR | Docs lag (plan.py, Phase 2 test docstring, bundle.py, architecture docs) | Fixed |
| m | MINOR | WS3: plan not validated, duplicate direction message, unused test parameter | Fixed |
| m | MINOR | A stored plan rewritten to `lagged_edges` shrinks required edges | Recorded (same class as any stored-plan edit) |
| m | MINOR | Core consensus / verification-ladder V5 not routed through admission | Recorded above (Core frozen) |

Certification-pinned (`certification/current_core_v2.json`) files changed in Phase 3.5:
`execution/multiphysics/runtime.py`, `scientific/multiphysics/plan.py`. Changed or new files inside certified SCOPE
patterns: `providers/{compare,problem_identity,__init__}.py`, `execution/multiphysics/{steady,authority,conjugate_interface}.py`.
No new import from a pinned-list file into an unpinned module. No V4 mutant targets a changed line (the G20a anchor in
`systems/electrothermal/coupled.py` is untouched). OD-3 recertification required.


## Semantic compatibility A-1/A-2/A-13 (2026-10-18)

Status: IMPLEMENTED / UNVERIFIED / UNCERTIFIED. All commands below NOT RUN.
DV-101..DV-106 are reserved by separate checkpoint Draft PR #158; these rows
start at DV-107 to avoid collision. DV-100 and checkpoint DV-101..106 run first
when separately authorized on the appropriate checkpoint tree; do not claim that
this independent semantic branch contains those repairs. DV-99 is repeated with
the strengthened stiffness refusal regression; its other gap pins are not support.

| ID | Scope | Exact deferred recipe | Admission / expected result | Status |
| --- | --- | --- | --- | --- |
| DV-107 | Typed scalar semantics and revised DV-99 | `python -m pytest tests/architecture/test_quantity_semantics.py tests/architecture/test_cross_domain_fixtures.py -q` | Correct refusal/roundtrip/identity/partition assertions; interpret remaining gap pins as known gaps; no domain validation | NOT RUN |
| DV-108 | Conservation, transfer and runtime | `python -m pytest tests/test_conservation.py tests/test_multiphysics_conservation_history.py tests/test_multiphysics_fan_in_units.py tests/test_stateful_multiphysics_runtime.py tests/test_phase2_external_coupling.py -q` | Preserve arithmetic and units; classify legacy alias refusals explicitly, never edit physical expectations merely to pass | NOT RUN |
| DV-109 | Frozen API, serialization, layering, certified closure | `python -m pytest tests/test_core_api_snapshot.py tests/test_core_v2_api_snapshot.py tests/test_core_api_serialization.py tests/test_scientific_serialization_integrity.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_core_freeze_v4_manifest.py tests/test_certified_dependency_closure.py -q` | No frozen surface drift; investigate certified dependency/pin failures; no automatic manifest update | NOT RUN |
| DV-110 | Thermal downstream and parity boundaries | `python -m pytest tests/test_electrothermal_vertical.py tests/test_electrothermal_fixed_point_relaxation.py tests/test_min_foundation_electrothermal.py tests/test_phase35_ws2_electrothermal_migration.py -q` | Existing exact-name paths retain expectations; owner-approved alias migrations required for newly refused paths; no parity promotion from declarations | NOT RUN |
| DV-111 | Provider consumers | In the existing WSL battery environment: `python -m pytest providers/pybamm/tests/test_pybamm_multiphysics.py providers/pybamm/tests/test_pybamm_coupling_options.py -q`; separately in FEniCSx environment: `python -m pytest providers/fenicsx/tests/test_coupling_fenicsx.py -q` | Re-establish provider identity, wiring and existing thermal intent; environment failures recorded; no substitute callback evidence | NOT RUN |
| DV-112 | Normal local integration gate | `python tools/forge_check.py --changed`, then `python tools/forge_check.py --regression` only after targeted checks and authorization | Gate may execute tests; NOT a permitted static-only command in this session; no assurance/certification claim | NOT RUN |

Before integration, classify the final diff under Core Freeze/certification policy.
Shared trust/admission, runtime and certified dependency changes require the normal
CI control plane and separately authorized OD-3 on final integrated source. Full
assurance, mutation, normal broad integration tiers and hardened recertification
remain separately gated; none was run here. Do not regenerate pins to silence refusal.
A-3 proposal examples were checked by hand only, not numerical execution.


## A-3 declared field kind mapping: DV-113..116 (2026-10-18)

Stacked branch base semantic98da0c02 / Draft PR #159. All commands NOT RUN.
Predecessor checkpoint DV-101..106 and semantic DV-107..112 remain NOT RUN.
No verification/validation/certification follows from declarations or static PASS.

| ID | Scope | Exact deferred recipe | Required interpretation | Status |
| --- | --- | --- | --- | --- |
| DV-113 | A-3 numerical/adversarial probes | `python -m pytest tests/test_declared_field_kind_mapping.py -q` | Preregistered integrated(4,4),total8; density contrast; 1D/refinement/coarsening/coverage/unit/orientation; 2D and declared unequal-volume tetrahedra; no local physical-validity claim | NOT RUN |
| DV-114 | Legacy conservative consumer migration audit | `python -m pytest tests/test_phase1_conservative_cell_mapping.py tests/test_phase2_field_transfer.py -q` | Unmigrated declarations intentionally refuse. Record failures and disposition each owning-model kind; these historical fixtures cannot prove new typed behavior or count as retained coverage. Do not alter numerical expectations to pass | NOT RUN |
| DV-115 | Core/serialization/trust compatibility | `python -m pytest tests/test_core_api_snapshot.py tests/test_core_v2_api_snapshot.py tests/test_core_api_serialization.py tests/test_scientific_serialization_integrity.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py -q` | Frozen shape/import identity preserved; /2 refuses in old readers; investigate dependency/pin failures, no automatic manifests | NOT RUN |
| DV-116 | Semantic and runtime integration | `python -m pytest tests/architecture/test_quantity_semantics.py tests/architecture/test_cross_domain_fixtures.py tests/test_multiphysics_fan_in_units.py tests/test_stateful_multiphysics_runtime.py tests/test_multiphysics_conservation_history.py -q` | Recheck parent scalar invariants, actual source record binding and known gap meanings; classify consumer migration failures explicitly | NOT RUN |

After targeted execution/migration, owner must authorize `python tools/forge_check.py --changed`
and `python tools/forge_check.py --regression`, normal integration tiers and final-source CI.
These commands execute tests and were not run as static checks. Provider runs, mutation,
full assurance and OD-3 remain separately authorized. A-4 is not closed by normal metadata.
No transient adaptive solver or automatic history/lineage restoration is added.


## A-4 interface execution: DV-117..120 (2026-10-18)

Base A-3 4f239fa7; predecessor DV-101..116 remain NOT RUN. All commands below NOT RUN.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED. Local/static PASS never scientific evidence.

| ID | Scope | Exact deferred recipe | Expected interpretation | Status |
| --- | --- | --- | --- | --- |
| DV-117 | A-4 numerical/contract probes | `python -m pytest tests/test_interface_flux_execution.py -q` | Executed scalar normal signs, density vs integrated amounts, unequal surface cells, full coverage, roundtrip limits, identity/unit/schema/context refusals, thermal + nonthermal; integral residual is constructed transfer diagnostic only | NOT RUN |
| DV-118 | Parent semantic and field-kind guarantees | `python -m pytest tests/test_declared_field_kind_mapping.py tests/architecture/test_quantity_semantics.py tests/architecture/test_cross_domain_fixtures.py -q` | Preserve A-1/A-2/A-13 and A-3; unsupported interface without explicit executable contract still refuses; interpret residual gap pins as gaps | NOT RUN |
| DV-119 | Concrete legacy interface migration audit | `python -m pytest tests/test_phase35_ws3_conjugate_interface.py tests/test_phase2_review_regressions.py -q` | WS3 lines68-104 expect prose-only admission and old sign metadata; intentionally refused until explicit typed migration. Record failures/dispositions; do not change physics expectations or count as retained coverage | NOT RUN |
| DV-120 | Core/trust/schema/runtime compatibility | `python -m pytest tests/test_core_api_snapshot.py tests/test_core_v2_api_snapshot.py tests/test_core_api_serialization.py tests/test_scientific_serialization_integrity.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py tests/test_stateful_multiphysics_runtime.py tests/test_multiphysics_conservation_history.py -q` | Exact frozen/import identity, nested edge /3 refusal/readers, certified dependency and existing runtime behavior; no automatic pin regeneration | NOT RUN |

After targeted migration/execution, separately authorize `python tools/forge_check.py --changed`
and `python tools/forge_check.py --regression` and required CI/integration tiers. These
execute tests and are not static commands. Provider runs, mutation, full assurance and
final integrated source OD-3 remain separately authorized. No real FE/CFD interface
execution, coupled physical verification or experimental validation follows from these
fixtures. E2 unstructured surfaces and independent flux/source balances remain future work.


## M1A lineage-bound adaptation: DV-121..124 (2026-10-18)

Stacked on A-4#161/1f43c59e; predecessor DV-101..120 remain NOT RUN.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED. No gate closure, verification or validation
from code, deterministic identity, a conservation diagnostic or static PASS.

| ID | Scope | Exact deferred recipe | Required interpretation | Status |
| --- | --- | --- | --- | --- |
| DV-121 | New M1A lineage/state/adversarial pack | `python -m pytest tests/test_m1a_mesh_lineage.py -q` | Issuance/geometry/siblings, refine-transfer-coarsen-transfer-back, nonrecoverable fine variation, units/coverage, stale/tampered records/bytes/cache/history, frame and replay refusal, false conservation and uncertainty dimensions | NOT RUN |
| DV-122 | Legacy mesh and steady-reference compatibility | `python -m pytest tests/numerical/test_mesh_adaptation.py tests/test_phase3_br16_mesh_validity_and_adaptation.py tests/claims/test_adaptive_resolution.py tests/domains/thermal_models/test_conduction1d_nonuniform.py -q` | Grid1D identity, legacy APIs/refusals, steady FV remain unchanged; these tests do not verify a transient M1 solver | NOT RUN |
| DV-123 | Parent semantic/transfer guarantees | `python -m pytest tests/test_declared_field_kind_mapping.py tests/test_interface_flux_execution.py tests/architecture/test_quantity_semantics.py tests/architecture/test_cross_domain_fixtures.py -q` | Recheck A-3 kind/operator and A-4 sign guarantees with shared dependencies; retain gap pins as gaps | NOT RUN |
| DV-124 | Core/trust/import compatibility | `python -m pytest tests/test_core_api_snapshot.py tests/test_core_v2_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py -q` | No frozen export/digest/serialization/import drift; no pin regeneration to silence failures | NOT RUN |

After targeted execution, separately authorize `python tools/forge_check.py --changed`
and `python tools/forge_check.py --regression` and required integration/CI tiers.
These commands execute tests, not permitted static gates in this session. Provider
runs, mutation, full assurance and final-source OD-3 remain separately authorized.
M1 transient temporal/spatial refinement and physical energy/source balances are
future tests for the future domain solver, not satisfied by this arithmetic pack.


## M1B vertex dual state adapter: DV-125..128 (2026-10-18)

Exact base M1A7f8cb5da/Draft#162. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.
All predecessor DV-101..124 remain NOT RUN; no imported earlier evidence.
Run only after separate owner execution authorization. Do not adjust expectations
or tolerances to obtain agreement. Static PASS establishes no numerical evidence.

| ID | Scope | Exact deferred recipe | Required interpretation | Status |
| --- | --- | --- | --- | --- |
| DV-125 | M1B dual placement/storage/adversarial pack | `python -m pytest tests/test_m1b_vertex_dual_state.py -q` | Nonuniform duals/half cells, exact placement/meaning, conservation/refine-coarsen roundtrip, explicit discontinuous storage, provenance, unit conversions, stale/cache/history/ancestry/byte attacks, false residual and unsafe transition poisoning | NOT RUN |
| DV-126 | Parent lineage/kinds/interface regressions | `python -m pytest tests/test_m1a_mesh_lineage.py tests/test_declared_field_kind_mapping.py tests/test_interface_flux_execution.py -q` | Parent issuance, primal/dual separation, A-3 kind guarantees and A-4 execution unchanged; no physical conservation or transient evidence | NOT RUN |
| DV-127 | Legacy mesh policy, steady FV and CDAR | `python -m pytest tests/numerical/test_mesh_adaptation.py tests/test_phase3_br16_mesh_validity_and_adaptation.py tests/domains/thermal_models/test_conduction1d_nonuniform.py tests/architecture/test_cross_domain_fixtures.py -q` | Legacy transient refusal remains; steady solver not relabelled transient; fixtures are architecture probes, not domain validation | NOT RUN |
| DV-128 | Core compatibility and certification boundaries | `python -m pytest tests/test_core_api_snapshot.py tests/test_core_v2_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py -q` | No frozen/API/import/schema drift; no certificate or expected-digest regeneration to silence failures | NOT RUN |

After bounded recipes and failure recording, separately authorize repository
forge_check/integration gates. No pytest, provider execution, full assurance,
mutation or OD-3 in this build. M1C manufactured solutions, temporal/spatial order,
solver-backed conservation and full adaptive-loop studies are still unwritten future
solver tests, not satisfied by normalized-input or remap arithmetic fixtures.


## M1C transient vertex FV: DV-129..132 (2026-10-18)

Exact base M1B9b092d56/Draft#165. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.
All previous DV-101..128 remain NOT RUN. These recipes execute numerical solves;
owner authorization is required before any execution, including targeted tests.
Do not tune expected orders/tolerances after observing a result; record failures.

| ID | Scope | Exact deferred command | Required interpretation | Status |
| --- | --- | --- | --- | --- |
| DV-129 | M1C real sparse numerical, manufactured/refinement and adversarial pack | `python -m pytest tests/test_m1c_transient_fv.py -q` | Independent specified-flux/source energy totals, both-Neumann, half duals/reactions, series/contact resistance, exact source averages, BE first order and spatial study, provider/failure/context/source/stale-state/refusal probes | NOT RUN |
| DV-130 | Parent state and legacy steady compatibility | `python -m pytest tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py tests/domains/thermal_models/test_conduction1d_nonuniform.py tests/numerical/test_mesh_adaptation.py -q` | Existing identities/outputs/refusals retained; do not infer M1D or physical validation | NOT RUN |
| DV-131 | Material and cross-domain semantics | `python -m pytest tests/test_materials_engine.py tests/test_declared_field_kind_mapping.py tests/test_interface_flux_execution.py tests/architecture/test_cross_domain_fixtures.py -q` | Existing resolution/meaning/field/sign boundaries remain; synthetic data stay assumptions, UNKNOWN remains UNKNOWN | NOT RUN |
| DV-132 | Model census and Core/certification compatibility | `python -m pytest tests/test_core_guards.py tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py -q` | Known static integration hold: model census pin19 vs new model20; do not regenerate pins or suppress model discovery. Owner must decide compatible pin/certificate change explicitly | NOT RUN |

Manufactured study definitions: uniform T=300+exp(-t), insulated, c=A=1,
q=-exp(-t) sampled at step end isolates BE temporal order; stationary-in-time
T=300+sin(pi*x), q=pi²sin(pi*x), exact dual-average source on nonuniform grids
isolates spatial behavior. These are synthetic mathematical verification designs,
not calibration or experimental validation. Code/expectations NOT EXECUTED.

After bounded execution, separately authorize forge_check/integration gates,
mutation/full assurance and final-source OD-3. M1D adaptive/rollback studies are
future tests for a future driver, not satisfied by this fixed-mesh pack.


## M1D adaptive transient: DV-133..136 (2026-10-18)

Exact base M1C73a18468/Draft#166. IMPLEMENTED / UNVERIFIED / UNCERTIFIED,
INTEGRATION HOLD. Earlier DV-101..132 remain NOT RUN. Separate owner authorization
required for every numerical/test recipe. No expectations/tolerances retuned after runs.

| ID | Scope | Exact deferred command | Required interpretation | Status |
| --- | --- | --- | --- | --- |
| DV-133 | New M1D adaptive, recovery and study pack | `python -m pytest tests/test_m1d_adaptive_transient.py -q` | Independent known energy budgets, constant/reference histories, issued refine/coarsen, fresh storage, rollback registry/resource/clock completeness, unsafe restoration poison, criterion/source/state refusal and manufactured studies | NOT RUN |
| DV-134 | M1A/B/C and legacy numerical regression | `python -m pytest tests/test_m1a_mesh_lineage.py tests/test_m1b_vertex_dual_state.py tests/test_m1c_transient_fv.py tests/numerical/test_mesh_adaptation.py tests/domains/thermal_models/test_conduction1d_nonuniform.py -q` | Original sourced constructor/legacy guards and prior numerical expectations unchanged; new continuation does not fabricate source evidence | NOT RUN |
| DV-135 | Seal/time/material/semantic/CDAR compatibility | `python -m pytest tests/test_external_participant_checkpoints.py tests/test_provider_participant_checkpoints.py tests/test_time_engine.py tests/test_materials_engine.py tests/test_declared_field_kind_mapping.py tests/architecture/test_cross_domain_fixtures.py -q` | Strict same-object scope, exact time and source/meaning boundaries; fixtures remain design probes | NOT RUN |
| DV-136 | Census/Core/certification integration | `python -m pytest tests/test_core_guards.py tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py -q` | Known static model20 vs pinned19 hold; reserving16/conditions96/reserved63/solver11 expected unchanged; capture ALL import failures, no silent skip/pin regeneration | NOT RUN |

Study definitions: uniform exponential transient T=300+exp(-t), source=-exp(-t),
insulated, dt=.1/.05/.025, one explicit refinement at t=.5; compare with independent
analytical value and a uniform run (agreement alone is not truth). Spatial study uses
stationary manufactured T=300+cos(pi*x), q=pi²cos(pi*x), exact regional/dual averages,
uniform starting nodes5/9/17 and one issued refinement between two .05s windows.
Assert monotonic refinement target only; no universal remap/jump spatial order claimed.
These are authored studies, not executed evidence. Failure stays recorded; no tuning.

After targeted execution, separately authorize repository forge_check/integration,
full FAST, performance, mutation/full assurance and exact-source OD-3. No such command
is a permitted static gate here. M1 still needs executed complete contextual evidence,
required CDAR fixtures and an explicit owner gate decision; implementation cannot close it.
