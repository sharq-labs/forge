# Active Plan

Purpose: keep the current Forge execution slice bounded, resumable and aligned
with `docs/project/FORGE_MASTER_PLAN.md`.

## Current objective

Execution strategy changed (2026-09-25): **build the big architecture first**
(BIG 2 Time Engine -> BIG 3 Environment -> BIG 4 Lifecycle ...), using only
focused smoke/regression checks during the build. After the architecture is
built: run real scenarios, review it scientifically/numerically, audit/rewrite
stale tests, and only then run the full FAST / SCIENTIFIC / mutation /
recertification campaign. The P0/P0.1 full-verification items below are
deferred to that campaign, not abandoned.

Current: **BIG 11 — Solver Provider Expansion** built (provider registry/discovery with no ranking or
fallback, content-derived execution identity, argv-only process boundary, PyBaMM / Cantera / CoolProp /
TESPy / CalculiX / OpenFOAM / SU2 / Code_Aster / OpenModelica executed; see PROGRESS); BIG 12 not started.
BIG 10 (multi-timescale runtime) is built on the same branch.

## Current branch / PR

- Branch: `feat/big-10-multitimescale` (from `main` @ `e3ae778a`, BIG 2-9 merged); local worktree `D:/forge-big10`
- PR: none opened; verify GitHub before making a current PR claim.
- Base: `main`

## Task tree

### P0 — Core / CI / assurance stabilization

- [x] Run the normal Tests workflow automatically on pull requests.
- [x] Re-run normal merged-tree checks on pushes to `main`.
- [x] Restore automatic hardened-core recertification ownership on pull requests.
- [x] Retain manual recertification as a fallback.
- [x] Require all V4 mutation shards explicitly before certification.
- [x] Remove the invalid `hardening_assurance build --event` invocation.
- [x] Make certificate-child verification work for the automatic PR flow.
- [x] Run branch-policy verification after updates to `main`.
- [x] Install all declared reproducibility extras in the Docker image.
- [ ] Obtain a complete green automatic PR assurance run on the current head.
- [ ] Verify the certificate/assurance produced by the automatic flow is bound
      to the exact measured source commit.
- [ ] Verify/restore the required GitHub branch ruleset for `main`; repository
      code can report policy but cannot substitute for repository settings.
- [ ] Resolve any remaining P0 workflow/test failures before adding scientific
      feature code.

### P0.1 — Scientific Correctness Hardening

Implementation exists for BIG 1, but verification is pending.

- [ ] Add/adjust focused regressions for every changed scientific invariant.
- [ ] Verify removing/replacing evidence cannot increase coverage support.
- [ ] Verify independent-group counting and split isolation.
- [ ] Verify missing observation noise never becomes zero uncertainty.
- [ ] Verify affine-temperature spreads use delta/ratio semantics.
- [ ] Verify oracle levels require typed execution/provenance binding.
- [ ] Verify consensus preserves comparable disagreements.
- [ ] Verify multiphysics windows, participants, events, termination and state chains.
- [ ] Verify replay cannot pass with zero expected outputs.
- [ ] Verify discovery identity binds holdout/result-changing content.
- [ ] Run changed-area compile/tests and `git diff --check`.
- [ ] Run `python tools/forge_check.py --changed` and required scientific tiers.
- [ ] Run the read-only scientific reviewer after tests stabilize.
- [ ] Obtain green CI on the final source head.
- [ ] Verify GitHub rules require `recertification-gate` and `tests-gate`.

### P1 / BIG 2 — Time Engine foundation

Implemented in `src/engcore/scenarios/timeline.py` (tests:
`tests/test_time_engine.py`). Built during the BUILD phase; full tiers NOT RUN.

- [x] Canonical immutable `TimeBasis` (no default clock), `TimePoint`
      (cross-basis ordering refused), `TimeWindow` (half-open/closed,
      empty/inverted refused) and deterministic `Timeline.digest`.
- [x] Typed `TimelineEvent` markers (scheduled/reached synchronization,
      discontinuity, state-change request, termination) with fail-closed
      ordering of order-sensitive events at a shared instant.
- [x] Usage/exposure `QuantityHistory` (gaps are UNKNOWN, integrals over gaps
      UNKNOWN, affine-unit integrals UNKNOWN) and `CycleHistory` (no skipped
      indices, no fractional cycle counts).
- [x] Bound to existing authorities: `Timeline.from_scenario` binds the
      `ScenarioSpecification` digest; `Timeline.bind_run` copies
      `MultiphysicsRunRecord` receipts verbatim and refuses another scenario.
- [x] State transitions reuse `StateTransitionReceipt` (no parallel record);
      the timeline enforces per-participant digest/time chaining and exposes
      state identity only at recorded boundaries (UNKNOWN in between).
- [x] Unsupported interpolation, interpolation mismatch and LINEAR across a
      declared discontinuity are refused.
- [x] `TimelineCheckpoint` binds a prefix digest plus existing
      `CheckpointRecord`s; `compare_replay` refuses empty prefixes and is
      classified `replay_consistency_not_validation`.
- [x] Exact same-instant rule (`SAME_INSTANT_RULE`, rational seconds, no
      epsilon) and scenario-proven input ownership (`input_value_at` takes the
      `ScenarioSpecification`). Re-review: no BIG 3 blocker.
- [ ] Remaining non-blocking BIG 2 gaps: see PROGRESS (BIG 2/3 section).
- [ ] Runtime-side emission: have `MultiphysicsRuntime` produce
      `TimelineCheckpoint`s from its own `_checkpoint_all` and restore from them.
- [ ] Multi-basis / multi-rate timelines (P14 prerequisite): an explicit,
      declared basis-mapping record instead of the current refusal.

### P2 / BIG 3 — Environment Engine

Implemented in `src/engcore/scenarios/environment.py` (tests:
`tests/test_environment_engine.py`). BUILD phase; full tiers NOT RUN.

- [x] Typed, extensible `EnvironmentQuantityKind` registry (13 generic kinds:
      temperature, plane/horizontal irradiance with orientation context,
      humidity, wind speed/direction, precipitation, wetness, chloride,
      particulates, pressure, altitude, gravity). No branching on kind ids.
- [x] `EnvironmentSource` (digest-bound, classified; design assumptions are
      `declared_assumption_not_evidence`), `ReferenceContext`, explicit
      `InterpolationContract` (NONE / STEP_HOLD / LINEAR with required max_gap).
- [x] `EnvironmentChannel` over point samples or the bound timeline's EXPOSURE
      `QuantityHistory` (stored once, in the timeline).
- [x] `EnvironmentState` / `EnvironmentTimeline`: UNKNOWN entries rather than
      omissions; interpolated values labelled and UNKNOWN-uncertainty; no
      extrapolation / gap / discontinuity crossing; overlapping sources refused;
      `dose()` for lifecycle consumers; `verify_state`; deterministic digests.
- [ ] Non-blocking gaps: see PROGRESS (BIG 2/3 section).

### P3 / BIG 4 — Lifecycle / degradation

Implemented in `src/engcore/scenarios/lifecycle.py`; reference probes in
`src/engcore/domains/battery/aging.py` and `src/engcore/domains/corrosion/`;
tests `tests/test_lifecycle_engine.py`. BUILD phase; full tiers NOT RUN.

- [x] Provider-neutral `DegradationModel` contract (state variables as
      `InitialStateDefinition`, `InputRequirement`, required `ApplicabilityBound`s,
      `DegradationModelIdentity` with UNKNOWN-by-default discrepancy).
- [x] Explicit `InputBinding`s to environment doses / window means and to
      timeline usage integrals / cycle counts; UNKNOWN inputs stop the step.
- [x] Digest-bound `DegradationStepRecord` (scenario, environment, run
      digest, window, prior state digest/values, inputs with source
      provenance, model identity/params, separated uncertainty statuses).
- [x] Feed-forward via `carry_forward` -> runtime `initial_state` ->
      `InitialStateReceipt`; `LifecycleChain.verify` checks each next window
      started from the degraded values and uncertainty; `run_lifecycle` loop.
- [x] Two independent reference families (battery capacity fade feeding a
      state-of-charge physics; corrosion thickness loss feeding heat flux)
      demonstrate changed future physics.
- [ ] Non-blocking gaps: see PROGRESS (BIG 4 section).


### P4 / BIG 5 — Scientific Data + Materials

Implemented in `src/engcore/materials/` (non-Core; registered in
`tests/test_core_api_layering.py::NON_CORE_PACKAGES`) on top of
`scientific.knowledge`; tests `tests/test_materials_engine.py`. BUILD phase.

- [x] Reuse, not duplicate: values are `KnowledgeClaim`s, sources
      `KnowledgeSource`, dataset versions `KnowledgeSnapshot`, import identity
      `KnowledgeIngestionReceipt`. `PropertyApplicability.digest` is the
      claim's `applicability_context_digest`.
- [x] Exact `MaterialIdentity` (name-only refused), `MaterialState`,
      domain-owned `MaterialStateSchema` ranges, `ApplicabilityRange`
      (omitted bound needs a stated reason).
- [x] `PropertyDatum` origins (measured/compiled/fitted/derived/assumed;
      fitted/derived need `TransformationRecord`), explicit
      `InterpolationRule` with breakpoints, fail-closed `resolve` returning a
      digest-bound `ResolvedProperty` (SOURCED / ASSUMED / INTERPOLATED / UNKNOWN).
- [x] Source alignment: `SourceIdentity` view over `KnowledgeSource` and
      `EnvironmentSource` (no serialized migration); sourceless environment
      values say `no_source`.
- [x] Lifecycle: applicability and state ranges are part of
      `DegradationModelIdentity`; every input needs a declared range; states
      checked against the owning domain's range; chain links prior state.
- [x] Executable proofs: temperature-dependent alloy conductivity; moisture
      uptake (lifecycle) -> MaterialState -> resolved conductivity -> heat flux.
- [ ] Non-blocking gaps: see PROGRESS (BIG 5 section).

### P5 / BIG 6 — Mathematical / numerical foundation

Implemented in `src/engcore/numerical/` (non-Core; registered) beneath the
Core `ScientificSolver` protocol; tests `tests/test_numerical_foundation.py`.

- [x] Reuses `SolverIdentity`, `SolverSettings`, `ConvergenceState`,
      `NumericHealth`, `ConditionEstimate`; bridges via `to_raw_solver_output`.
- [x] `UnitBoundary` (Quantity <-> normalized array, recorded scale, affine
      refused), `OperatorIdentity` (array bytes / SymPy srepr / declared =
      attestation), `NumericalProblem` (explicit initial values; ODEs inside a
      BIG 2 `TimeWindow` with explicit breakpoints), `NumericalExecutionRecord`
      (execution identity; outputs withheld on failure), `compare_executions`.
- [x] Providers: NumPy dense LU; SciPy sparse direct + GMRES; root
      (hybr/lm); minimize (BFGS/Nelder-Mead); solve_ivp (RK45/BDF/Radau/LSODA);
      SymPy `SymbolicSystem` (exact Jacobians, derived identity).
- [x] Optional: PETSc KSP provider (petsc4py absent here -> ProviderUnavailable;
      execution path NOT RUN); SUNDIALS contract only (always unavailable).
- [ ] Next numerical slice: SUNDIALS CVODE/IDA implementation, DAE support,
      PETSc execution in an environment that has petsc4py.
- [ ] Non-blocking gaps: see PROGRESS (BIG 6 section).

### BIG 7 — Field + Mesh core

Implemented in `src/engcore/spatial/` (non-Core; registered) on the Core
`UnstructuredMesh`/`UnstructuredMeshData`/`FieldDefinition`/`FieldValue`
records; tests `tests/test_spatial_core.py`. Gmsh 4.15.2 + meshio 5.3.5
executed for real (optional extra `mesh`).

- [x] `SpatialMesh`: identity = Core byte fingerprint + tag/facet/group/frame
      bytes; content-derived mesh id; digest-verified serialization.
- [x] Coordinate frames, physical groups, digest-bound regions/boundaries
      (forged or foreign regions refused), node/cell/facet/edge locations.
- [x] Framed scalar/vector/tensor fields with derivation + provenance; lossless
      bridge to Core `FieldValue` only where nothing would be dropped.
- [x] Region -> exact BIG 5 `MaterialState` binding; resolved property fields.
- [x] P1 node->cell (exact for P1 interpolant on triangles) and mesh->mesh
      barycentric mapping (not conservative; integrals reported); no extrapolation.
- [x] Gmsh two-region plate generation (replay-identical here) and meshio
      Gmsh-2.2 roundtrip preserving identity.
- [ ] Non-blocking gaps: see PROGRESS (BIG 7 section).

### BIG 8 — PDE / FEM provider layer

Contracts in `src/engcore/pde/` (non-Core; registered); provider in the
separate distribution `providers/fenicsx` (`forge_fenicsx`, dolfinx 0.11.0 +
PETSc/petsc4py 3.25.5, conda-forge env `/opt/mm/root/envs/fenicsx`). Tests:
`tests/test_pde_contracts.py` (core CI) and `providers/fenicsx/tests/`.

- [x] Forge-owned operator templates (steady/transient diffusion, plane-stress
      elasticity) with dimensioned, range-checked coefficient slots; no caller forms.
- [x] `PDEProblem` identity from content: mesh digest, facet roles (checked
      against facet-cell topology), resolved coefficient fields + material
      provenance, sourced BC values, discretization, PETSc settings, BIG 2
      window/breakpoints/schedule. Every outer facet needs a declared BC.
- [x] Real solves: A steady two-material heat (matches series solution; P1+P2),
      B plane-stress elasticity -> framed vector field, C transient heat on a
      BIG 2 window with breakpoint reassembly, D Robin BC from BIG 3
      environment records, E lifecycle moisture -> next real PDE solve,
      F two mesh resolutions compared (not validated).
- [x] Acceptance = PETSc converged reason AND true residual; failed solves
      expose no field; records verify their fields are COMPUTED by them.
- [ ] Non-blocking gaps: see PROGRESS (BIG 8 section).

### BIG 9 — Generic multiphysics runtime + preCICE

Adapters in `src/engcore/coupling/` over the existing MultiphysicsRuntime;
preCICE provider in `providers/precice` (preCICE 3.4.0).

- [x] A one-way, B two-way relaxed iterative with residual history, C non-convergent refused,
      D cross-mesh via BIG 7 mapping, E >=2 provider types, F TimeWindow, G environment,
      H lifecycle, I conservation diagnostic, J real preCICE run (all executed; see PROGRESS).
- [x] Review blockers fixed (preCICE unit check; Forge-owned acceptance).
- [x] Re-review before BIG 10 (CHANGES REQUIRED, 5 BIG 10 blockers) -> fixed: unrelaxed fixed-point
      residual, undeclared participant events refused, input/condition changes are window boundaries,
      provider adapter state progression + explicit `ParticipantStateContract`; resume handled at
      macro boundaries by BIG 10 (`MacroCheckpoint`).
- [ ] Non-blocking gaps: see PROGRESS (BIG 9 section and BIG 10 "BIG 9 re-review").

### BIG 10 — Multi-timescale runtime

`src/engcore/multiscale/` (non-Core; registered) orchestrating BIG 2-9; reference domain probe
`domains/electrical/resistance_drift.py`; proofs `tests/test_multiscale_runtime.py`,
`tests/test_multiscale_review_fixes.py`, `providers/fenicsx/tests/test_multiscale_fenicsx.py`.

- [x] Declared `ScaleHierarchy` (FAST / OPERATIONAL / SLOW roles; domain declares state ownership; in identity).
- [x] `MacroStepPolicy` (explicit adaptation rules, event SPLIT/REFUSE, explicit-normalization
      state-change limits, threshold localization); every size change / refinement recorded.
- [x] `RepresentativeWindow` approximation contract (exact rational weight, whole-period tiling +
      resolved remainder, declared assumptions/applicability, MEASURED input deviation vs declared
      periodicity tolerances; beyond tolerance -> rejected and refined).
- [x] Aggregation with stated preserved/lost history features; models declare accepted forms and
      required features (`AggregateRequirement`, lifecycle `PHYSICS_AGGREGATE`,
      `StepStatus.INSUFFICIENT_HISTORY`); `compress_history` (derived, never gains features).
- [x] Fast/slow separation: fast solver gets read-only state; only APPLIED BIG 4 steps change slow
      state; material re-resolution enforced per execution (`MaterialBinding`).
- [x] Exact fast-execution reuse only for a declared-pure system and identical request identity.
- [x] `MacroCheckpoint` (serialized, digest-verified) + `resume` refused unless all fast participants
      DECLARED complete state; `compare_resume` (reproducibility, not validation).
- [x] Approximation ledger (7 separate components; UNKNOWN unless quantified; observations of a more
      temporally resolved numerical reference are not bounds).
- [x] Proofs A-F executed (lumped+SciPy in core env; FEniCSx+SciPy in the conda env) — see PROGRESS.
- [ ] Non-blocking gaps: see PROGRESS (BIG 10 section).

### BIG 11 — Solver provider expansion

`src/engcore/providers/` (non-Core; registered) + separate adapter distributions under `providers/<name>/`;
map and license matrix `docs/architecture/providers.md`; boundary proofs `tests/test_provider_boundary.py`,
`tests/test_big11_review_fixes.py`; provider proofs `providers/*/tests/` (run in the WSL conda envs).

- [x] Final BIG 10 review before providers (9 blockers fixed, `test_b1..b9`).
- [x] Descriptive capability registry, `discover` (id order) / `require` (exact provider or
      `ProviderUnavailable`); `default_registry()` never raises; `python -m engcore.providers`.
- [x] Content-derived `ProviderExecutionIdentity` incl. dependency digests (Python RECORDs; conda env
      package-set digest for process providers).
- [x] Process boundary: argv only, fresh workspace, explicit env, timeout + process-group kill, executable
      re-hashed at launch, outputs = regular files THIS run created/changed, digest-verified reads,
      stale/foreign/input/symlink refused; exit 0 is not success.
- [x] Providers executed: PyBaMM 26.8, Cantera 3.2.0, CoolProp 8.0.0, TESPy 0.11.2, CalculiX 2.23,
      OpenFOAM v2412, SU2 8.5.0, Code_Aster 18.1.7, OpenModelica 1.27.1. Elmer UNAVAILABLE (recorded).
- [x] Integration: PyBaMM <-> TESPy on the BIG 9 runtime; PyBaMM as a BIG 10 FastSystem; BIG 3 ambient /
      coolant channels consumed; BIG 5 E/nu records -> CalculiX/Code_Aster; CoolProp records -> CFD viscosity.
- [x] Record-bound cross-provider comparison (independence, spread tolerances, post-hoc label, values digest).
- [x] Proofs A-J executed — see PROGRESS (BIG 11).
- [x] `forge-scientific-review` (CHANGES REQUIRED, no blocker) -> findings 1-15 fixed; focused re-review
      (CHANGES REQUIRED, 5 MEDIUM) -> fixed with tests; LOW residuals recorded; second re-review NOT RUN.
- [ ] Non-blocking gaps: see PROGRESS (BIG 11 section).
- [ ] BIG 12 — NOT STARTED (per instruction).

## Persistent project direction

The long-term roadmap, non-goals, provider strategy, data policy, flagship
systems and session-resume protocol live in:

`docs/project/FORGE_MASTER_PLAN.md`

Do not duplicate or silently replace that strategic direction here. This file
is only the current bounded execution plan.

## Stop conditions

Stop implementation and surface a blocker if a proposed change would require:

- weakening UNKNOWN/fail-closed semantics;
- changing a frozen serialized contract without an explicit version decision;
- inventing measurements, uncertainty, validation, provenance or evidence;
- duplicating an existing scientific identity, timeline, state or authority system;
- adding domain-specific component/state/quantity names to generic Core;
- treating convergence, serialization roundtrip or solver agreement as validation;
- bypassing automatic assurance gates to make a change appear complete.

## Session resume

At a new session, read in this order:

1. `CLAUDE.md`
2. `docs/project/FORGE_MASTER_PLAN.md`
3. this file
4. newest relevant entries in `docs/work/PROGRESS.md`
5. current repository HEAD / branch / PR state

Then continue the first executable unfinished task above.
