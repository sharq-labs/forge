# Engineering Foundations Program (`engrt.numerical_foundations`)

**Decision OD-6 (owner, Claude Code session, 2026-10-18):** the active epic becomes the research program
`engrt.numerical_foundations`, through the canonical mechanism of
[SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md](SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md): this reviewed change to the
ledger (`scientific_capability_completion.json`, schema `/2`), its checker, its test pin and the PR template. It is in
force only once this change is reviewed and merged. It uses the research-program mechanism designed in
[docs/work/OD6_GENESIS_EPIC_MIGRATION_PACKAGE.md](../work/OD6_GENESIS_EPIC_MIGRATION_PACKAGE.md) (Option C), with this
program as the epic instead of Genesis; Genesis stays on file and is not active.

A research program has **gates, not maturity stages**. A program result never promotes a capability (the Genesis Gate H
rule, restated for this program): every scientific capability the program builds is tracked in the ledger's
`capabilities` array with the 19 maturity gates, enters it at FOUNDATION only when its four FOUNDATION gates PASS with
repository evidence, and climbs only through those gates.

**Decision OD-CAP-0 (owner, Claude Code session, 2026-10-19: scope accepted as drafted; in force only once this
change merges):** the program gains three gates, DA-1 (derivative authority), RE-1 (reliability engineering) and IP-1 (generic
inverse problems), and the scope `src/engcore/quantitative/**` plus four narrowly named touch points. The three
capabilities were outside `allowed_scope`. Three serial exceptions would trip the Completion Policy's anti-loophole
rule, and placing the code under `src/engcore/numerical/**` to fit the old scope would be the loophole itself, so the
program scope is amended instead. The build-first rule, Gate H and the CDAR rule bind the new gates exactly as they bind
M1-E3. Design: [SCIENTIFIC_CAPABILITY_FREEZE_2026_10_19.md](../work/SCIENTIFIC_CAPABILITY_FREEZE_2026_10_19.md)
(PROPOSED, static review of `8ec97064`). Owner decisions the gates still need: OD-CAP-1 (layer slot 8 for
`quantitative` now, one certification ScopeArea at FUNCTIONAL), OD-REL-1 (a rating violation as a failure event),
OD-REL-2 (OpenTURNS licence and installation), OD-REL-3 (preregistered demonstration inputs), OD-INV-1 (hoist of the
held-out scorer into `adequacy`). Each is decided before the wave that needs it, and none blocks building.

## Build-first: gates order DECISIONS, never work

The owner's strategy is to build every foundation first and validate afterwards. The program encodes exactly that:

- **Any gate's scope may be written and implemented at any time** -- before DV0, before any other gate, and in any
  order. Nothing in the ledger, the checker or this contract makes building wait for a test run.
- **DV0 gates nothing.** No gate `requires` DV0; DV0 is the deferred-validation gate for the work already built (ERT
  V1, Phases 1-3.5). Running it is an owner decision, and it never blocks M1, M2, E1, E2 or E3 work. (DV0 is not the
  plan's "G0 Trust lane".)
- A gate's `requires` constrains only when that gate may be **decided**: PASS or FAIL after every required gate PASSED;
  BLOCKED_WITH_EVIDENCE after every required gate is decided either way (a FAILED M1 may block M2 and E3). M2 and E3
  can be built now.
- Every decided gate (PASS, FAIL, BLOCKED_WITH_EVIDENCE) cites existing repository evidence; a DEFERRED_BY_OWNER gate
  states why in its next action and keeps the program open until the owner decides it or names the next epic.
- A gate is decided only on **executed evidence** that exists in the repository; until then it is MISSING (built and
  unverified work is MISSING, never PASS). Building something never changes a maturity stage (Gate H).

## Why

The Engineering Runtime V1 program (on `main`) and Phases 1–3.5 (local branches, not yet merged) built the runtime
foundations (coupling authority, field transfer, window control, acceleration, numerical health, mesh validity,
moving-mesh kinematics, admission contracts). Five
remaining foundations are new scientific capabilities that the battery epic paused: a provider-backed nonlinear PDE,
real FE ↔ CFD conjugate heat transfer, a bounded ALE formulation, and the adaptive-mesh extensions that EXC-1 did not
cover. Serial exceptions for them would be the "exceptions as the roadmap" the anti-loophole rule forbids, so the epic
itself is re-pointed.

## Scope (`allowed_scope` in the ledger)

| Gate | Work allowed | Code areas |
| --- | --- | --- |
| DV0 | Execute the deferred validation for every DV row present in `docs/work/DEFERRED_VALIDATION.md` when the gate is decided (DV-1..DV-30 on `main`; DV-31..DV-98 once the Phase branches land), fix what fails, record every failure | the whole tree, as defect work |
| M1 | Transient non-uniform 1D conduction (vertex-centred FV, backward Euler, declared order 1, explicit boundaries, sourced initial condition); conservative transfer of the cell-integrated conserved quantity (energy in the conduction instance) between `Grid1D`s by exact interval overlap (conservative vs intensive declared; affine units refused; coverage and conservation residual recorded); coarsening only by undoing recorded bisections; an adaptive transient loop recording every grid version, parent and transfer, invalidating stale fields and coupling-acceleration history | `src/engcore/numerical/{mesh_adaptation,interval_transfer}.py`, `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` |
| M2 | Conforming triangle refinement (newest-vertex bisection, conformity closure, quality and inversion refusal, recorded parent-child versions, cell-average transfer through the existing conservative 2D remap) | `src/engcore/numerical/triangle_refinement.py` |
| E1 | (Precondition, not a ledger `requires`: Phase 3 `pde/nonlinear.py` has landed on `main`.) One nonlinear Forge template: steady `-div(k(u) grad u) = f`, `k(u) = k0 (1 + beta (u - u0))`, 2D affine triangles, P1/P2; admissibility `k(u) > 0` over the admitted range; a FEniCSx Newton path (exact UFL Jacobian) returning per-step Newton histories for `pde.nonlinear.admit_nonlinear_execution`; a manufactured-solution test | `src/engcore/pde/**`, `providers/fenicsx/**` |
| E2 | Conjugate heat transfer for one pair and one geometry (a planar wall between a solid slab and a laminar channel): a FEniCSx transient-diffusion window session with boundary-trace flux output; an OpenFOAM energy-equation window session (restart per window, interface boundary update, read-back, time-directory snapshot/restore); interface supports as 2D `UnstructuredMesh` surfaces; one declared CHT model with sourced applicability conditions; an end-to-end run | `src/engcore/execution/multiphysics/**`, `src/engcore/coupling/**`, `providers/fenicsx/**`, `providers/openfoam/**` |
| E3 | (Precondition, not a ledger `requires`: Phase 3 `numerical/moving_mesh.py` has landed on `main`.) 1D transient diffusion on a moving domain `[0, L(t)]` in ALE form with a declared linear mesh-motion law, material velocity 0, vertex-centred FV on `numerical.moving_mesh`, a GCL-consistent time rule, linear solves through `SciPyLinearProvider`; tests for constant-state preservation, GCL, a known moving-boundary solution and rollback | `src/engcore/numerical/**`, one new module under `src/engcore/domains/thermal_models/` named in the E3 PR |
| DA-1 | A canonical derivative record (of / with respect to / point / units / method / numerical error, schema `quantitative.derivative/1`); a converged finite-difference source over the frozen `hybrid_uq` `central_difference` (read-only); symbolic (SymPy) and closed-form sources; declare-before-compare cross-method verification between different method families; admission of provider-computed derivatives (plus one trailing `derivative_outputs` field on `ProviderCapability`); total derivatives by the chain rule over `SystemExecutionPlan` and by the implicit-function form over `PhysicsGraph` cycles (a missing partial refuses, an IQN approximation is never admitted); a bridge into the frozen supplied-`LocalSensitivity` boundary | `src/engcore/quantitative/{refs,standing}.py`, `src/engcore/quantitative/derivatives/**`, `src/engcore/providers/catalog.py` (one trailing field) |
| RE-1 | `LimitState` over `ConstraintDefinition` with a cited limit source; `ProbabilisticInputModel` (NORMAL, LOGNORMAL, UNIFORM, TRUNCATED_NORMAL; dependence INDEPENDENT_DECLARED with a basis or GAUSSIAN_COPULA, UNKNOWN refused); per-sample SAFE / FAILED / NOT_ASSESSABLE classification (OD-REL-1); a digest-bound study declaration; crude Monte Carlo with Clopper-Pearson; an OpenTURNS FORM / SORM / importance / subset provider (OD-REL-2) with design-point re-verification and a FORM-versus-Monte-Carlo challenge; calibrated-posterior inputs; one electrothermal demonstration (PWR220T-20 hot-spot limit, inputs preregistered, OD-REL-3) | `src/engcore/quantitative/inputs.py`, `src/engcore/quantitative/reliability/**`, `src/engcore/domains/electrical/reliability_binding.py` |
| IP-1 | `InverseProblem` composing `CalibrationSpec` / `calibrate` without editing them; typed finite-dimensional targets (PARAMETER, MATERIAL_PROPERTY, INITIAL_STATE, BOUNDARY_VALUE, SOURCE_TERM; FIELD refused); `ObservationBinding` with a unit check before any evaluation; `InverseSolution` keeping optimizer convergence, identifiability, solution uncertainty, held-out adequacy and model discrepancy separate; sealed held-out scoring (scorer hoisted into `adequacy`, OD-INV-1); profile-likelihood and pre-data identifiability; a method boundary | `src/engcore/quantitative/inverse/**`, `src/engcore/adequacy/held_out.py`, `src/engcore/studies/calibration_study.py` (re-exports only) |

Planned capabilities (enter `capabilities` only at FOUNDATION): `numerics.adaptive_mesh_1d_transient`,
`numerics.triangle_refinement`, `pde.nonlinear_diffusion_fenicsx`, `coupling.cht_fenicsx_openfoam`,
`thermal.ale_moving_domain_1d`, and under OD-CAP-0 `quantitative.derivative_authority`, `quantitative.reliability`, `quantitative.inverse_problems`.

## Cross-Domain Scientific Architecture Requirements

Part of this program's acceptance criteria (owner direction, 2026-10-18): not a new program and not an exception. **Heat
is the first reference application, not the physics the core is built on.** A reference application may be
domain-specific -- E2 stays conjugate heat transfer -- but the shared structure it builds on (ports, conservation,
transfer, participants, materials, time, identity, verification, frames, API) may not impose thermal assumptions.

**The rule for every gate.** A shared mechanism added or changed by M1, M2, E1, E2 or E3 may not hard-code one
physics's dimensions, units or names. A physics-specific behaviour is a PARAMETERIZATION or an INSTANCE of a generic
contract, declared where it is used. A gap below that needs a Core change is a Core compatibility-review item (Core
Freeze policy); it is recorded here as a requirement and never implemented silently or behind a refactor label. None of
the symbols involved (`PortDefinition`, `FieldMapper`, `FrameTransform`, `ConservationBalance`, `CanonicalProblem`) is
in the frozen API snapshot (`tests/api/frozen_api_snapshot.json`), so "Core review" here means a compatibility review
of Core-PACKAGE semantics (`engcore.scientific`, `engcore.execution`), not a new Core Freeze version.

The evidence is the read-only audit [CROSS_DOMAIN_ARCHITECTURE_AUDIT.md](../work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md)
(of the Phase 3.5 tree; files marked there are not on `main` until the Phase branches land).

| ID | Requirement | Exists today | Gap | Resolution owner |
| --- | --- | --- | --- | --- |
| CDAR-1 | Universal physics contracts: a port states what quantity it carries and its role, independent of the physics | `PortDefinition` (kind, quantity, unit, algebra, frame), `ParticipantSpec`, `CallbackParticipant` -- no physics named | no semantic role (potential / flow, intensive / extensive, density / integrated); `quantity` is never compared on an edge, so same-dimension different-meaning pairs pass | Core review (A-1) |
| CDAR-2 | Generalized conservation of energy, mass, charge, momentum or species, as the problem declares | `ConservationBalance`, `CoupledConservation`, runtime `_balance` are dimension-generic | losses only through `EnergyConversion`; no lossy mass / charge / species crossing; no generic quantity conversion; field-valued balances refused | Core review (A-2) |
| CDAR-3 | Multi-domain field transfer: each field crosses by the rule its kind requires (conserved density, conserved integrated amount, intensive value; scalar, vector, tensor) | `FieldMapper` (identity, nearest, bilinear, conservative cell), component-wise vectors in one frame, `interface_exchange` flux / intensive kinds | conservative remap silently assumes a density; flux / intensive contract opt-in and not applied; sign convention recorded but not applied; no normal projection; CHT admission hard-codes K and W/m^2 | Core review (A-3); M1, M2, E2 |
| CDAR-4 | Generalized solver participants: circuits, ODE / DAE, PDE, process providers -- not FE / CFD only | callback, external, steady-result, provider participants; an MNA circuit participant; a steady coupled screening template spanning propeller, motor, battery and thermal models (`systems/products/drone_coupled.py`; its mechanical link crosses as power, not as force or displacement) | no ODE / DAE participant, no chemical (CSTR), multibody or structural participant; domain packs ship no participant factories | program fixtures (below); later specialization |
| CDAR-5 | Unified material and property models across thermal, electrical, mechanical and chemical properties | `MaterialPropertySet` / `ResolvedProperty` with free property ids; domain-owned state schema | scalar values only (no tensor / anisotropic); no property-id registry or domain qualifier | later review (A-5) |
| CDAR-6 | Multi-timescale coupling | `multiscale/` macro and fast windows; window control; subcycling against one shared window | no multirate (per-participant windows) and no interpolated input histories | later review (A-6) |
| CDAR-7 | Multi-domain problem identity: a comparison is admitted only on one declared scientific problem, in any domain | `CanonicalProblem` / `ProblemAspect` (domain-neutral), mandatory admission (Phase 3.5) | `ProblemAspect` is closed; no aspect for coupling interfaces or frames | Core review (A-7) |
| CDAR-8 | Domain-specific verification rules: each domain supplies its own evidence, error criteria and validity | typed verification ladder, `ValidationCheck`, `ValidityDomain`, domain-pack `validation_protocols` | the domain-pack protocol is typed `Any` and mostly empty; scalar comparison only, no field norms | later review (A-8) |
| CDAR-9 | Coordinate and reference frames for forces, fields, motion and moving meshes | `FrameTransform` (orthonormal, det +1), port frame enforcement, frame hierarchy, moving-mesh kinematics | no translation, time-varying or rotating frames; MIN / MAX fan-in on vectors is component-wise, not frame-invariant | Core review (A-9); E3 |
| CDAR-10 | Physics-neutral API: a new discipline is added without a Core rewrite | neutral `run_simulation`, canonical engineering intent, domain packs | domain-named MCP tools beside the neutral ones; domain packs without participants | later review (A-10) |

### Multi-domain acceptance criteria per gate

| Gate | Acceptance criterion, in addition to its scope |
| --- | --- |
| M1 | The mesh-adaptation and state-transfer kernel takes a DECLARED variable kind (conserved density, conserved integrated amount, or intensive) and the conserved quantity's dimension; conduction is the reference instance; the kernel contains no temperature-, heat- or energy-specific code (CDAR-2, CDAR-3). The kind is declared locally in the program's own 1D module (`numerical/`, outside the Core packages); it becomes a shared Core field kind only through the A-3 review. |
| M2 | Transfer between refinement levels goes through `FieldMapper` / the conservative remap with the conservation rule chosen by the declared field kind, scalar and vector (CDAR-3). That needs the A-3 Core review (a field-kind rule in `engcore.execution`); M2 may be BUILT before it, but is DECIDED only after it. |
| E1 | The nonlinear PDE contract stays generic (`pde/nonlinear.py` already names no physics); `k(u)` diffusion is one template and FEniCSx one provider; nothing in the contract or the provider path assumes a temperature unknown (CDAR-1, CDAR-4). |
| E2 | The interface admission is a GENERIC Dirichlet-Neumann (intensive / flux-density) admission parameterized by the two dimensions and the sign convention, which the transfer applies; conjugate heat transfer is its instance (CDAR-3). Generalizing `conjugate_interface.py` (Phase 3.5) changes admission semantics in `engcore.execution` and so goes through the A-4 Core review: E2 may be BUILT before it, but is DECIDED only after it. That file's docstring still says real FE / CFD is "BLOCKED by policy (OD-P2-1)"; OD-6 supersedes that on merge. |
| E3 | Mesh motion stays separate from the physics (`numerical/moving_mesh.py` already is); the ALE transport form is generic in the transported conserved quantity; diffusion is the instance (CDAR-2, CDAR-9). |
| DA-1 | The derivative record and its assembly name no physics. Units come from `Quantity` division (an affine result unit is refused, an affine variable uses its delta unit). The closed-form thermal partials are a test fixture, not part of the contract (CDAR-1, CDAR-7). |
| RE-1 | The limit state, input model and sample classifier are generic. A domain supplies only which of its validity conditions are ratings (OD-REL-1), and the demonstration binding lives in `domains/` (CDAR-8, CDAR-10). |
| IP-1 | Targets are typed by role (initial state, boundary value, source term), never by a physical quantity's name. The thermal reference and the TCR study are instances (CDAR-1, CDAR-7). |
| DV0 | Unchanged: it never blocks building (build-first) and stays a condition for scientific maturity under the policy. |

### Architectural fixtures (design probes, not domain support)

Before any of M1, M2, E1, E2 or E3 may be **decided**, three small fixtures exist in
`tests/architecture/test_cross_domain_fixtures.py` and have been RUN once, with their results recorded as design findings
(deciding a gate needs executed evidence anyway). They are TEST code only: participants built from the generic
`CallbackParticipant` inside the test, no module under `src/engcore/domains/` or any other product package, no model,
capability or validation check. They test the SHARED structure, not a discipline, and their results are design
findings, never evidence for, or support of, those domains. Like the E1/E3 preconditions, this rule is enforced by the
reviewer of the PR that decides a gate; the ledger does not encode it.

| Fixture | What it probes | Gaps it is expected to expose |
| --- | --- | --- |
| Electrical RC circuit | voltage and current as distinct ports of one participant pair; a time state | CDAR-1 (no potential / flow role), CDAR-4 (no ODE participant: a callback stands in) |
| Mechanical spring-mass | force and displacement with direction and frame; motion over time | CDAR-1, CDAR-9 |
| Chemical mixing | concentration and a REQUIRED mass balance through `CoupledConservation` | CDAR-2 (no lossy mass crossing), CDAR-3 |

Building these fixtures is build-first work like any other; writing them does not wait for DV0 and does not decide a
gate.

## Prohibited

- any capability maturity change from a program gate result (Gate H);
- claims, SRIA or MCP reachability of a new capability before its computed stage is FUNCTIONAL;
- validation or benchmark claims without executed evidence; mocks presented as real runs;
- tetrahedral or hexahedral refinement; multi-dimensional or fluid ALE; turbulence models; further nonlinear templates;
  further provider pairs;
- a shared mechanism that hard-codes one physics's dimensions, units or names (the CDAR rule above); a Core semantic
  change made without its compatibility review;
- a certified-area change without recertification (OD-3);
- LLM authority over models, thresholds, evidence or verdicts.
- FORGE-built adjoint or tangent integrators, FORM/SORM optimizers, MCMC samplers or nonlinear optimizers (DA-1, RE-1 and IP-1 wrap mature providers);
- a derivative agreement, failure probability or inverse solution treated as a claim, evidence, validation or verdict; field-valued inverse targets;
- a new provider dependency (OpenTURNS) without its licence and installation owner decision (OD-REL-2).

## Relationship to the rest of the ledger

- `battery.thevenin_1rc` stays a tracked capability at its computed stage (FUNCTIONAL, 2026-10-18) with every gate,
  evidence path and next action unchanged; it is no longer the epic. Defect, stabilization and evidence work on it stay
  allowed; a new battery capability foundation needs an exception.
- EXC-1 (adaptive mesh control) is superseded by this program on merge: its slices 1–4 (including
  `claims/adaptive_resolution.py`, now in `allowed_scope`) and its exit gate (DV-27..DV-30) become part of DV0 and M1.
- Genesis (`genesis.scientific_reasoning`) is not active; A2 still needs an epic change or an exception.
- DA-1, RE-1 and IP-1 (OD-CAP-0) add no capability to the ledger. Each of `quantitative.derivative_authority`, `quantitative.reliability` and `quantitative.inverse_problems` enters `capabilities` only when its four FOUNDATION gates pass.
- Horizontal expansion OUTSIDE `allowed_scope` stays paused.

## Exit

Every program gate is PASS, FAIL or BLOCKED_WITH_EVIDENCE (a deferred gate keeps the program open); the owner then
names the next epic. Landing order: this governance change may merge alone; E1 and E3 additionally need the Phase
branches on `main` before they can be decided.
