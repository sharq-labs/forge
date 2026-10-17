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

## Why

The Engineering Runtime V1 program and Phases 1–3.5 built the runtime foundations (coupling authority, field transfer,
window control, acceleration, numerical health, mesh validity, moving-mesh kinematics, admission contracts). Five
remaining foundations are new scientific capabilities that the battery epic paused: a provider-backed nonlinear PDE,
real FE ↔ CFD conjugate heat transfer, a bounded ALE formulation, and the adaptive-mesh extensions that EXC-1 did not
cover. Serial exceptions for them would be the "exceptions as the roadmap" the anti-loophole rule forbids, so the epic
itself is re-pointed.

## Scope (`allowed_scope` in the ledger)

| Gate | Work allowed | Code areas |
| --- | --- | --- |
| G0 | Execute the deferred validation of ERT V1 and Phases 1–3.5 (DV-1..DV-98), fix what fails, record every failure | the whole tree, as defect work |
| M1 | Transient non-uniform 1D conduction (vertex-centred FV, backward Euler, declared order 1, explicit boundaries, sourced initial condition); conservative transfer of the cell-integrated energy between `Grid1D`s by exact interval overlap (conservative vs intensive declared; affine units refused; coverage and conservation residual recorded); coarsening only by undoing recorded bisections; an adaptive transient loop recording every grid version, parent and transfer, invalidating stale fields and coupling-acceleration history | `src/engcore/numerical/{mesh_adaptation,interval_transfer}.py`, `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` |
| M2 | Conforming triangle refinement (newest-vertex bisection, conformity closure, quality and inversion refusal, recorded parent-child versions, cell-average transfer through the existing conservative 2D remap) | `src/engcore/numerical/triangle_refinement.py` |
| E1 | One nonlinear Forge template: steady `-div(k(u) grad u) = f`, `k(u) = k0 (1 + beta (u - u0))`, 2D affine triangles, P1/P2; admissibility `k(u) > 0` over the admitted range; a FEniCSx Newton path (exact UFL Jacobian) returning per-step Newton histories for `pde.nonlinear.admit_nonlinear_execution`; a manufactured-solution test | `src/engcore/pde/**`, `providers/fenicsx/**` |
| E2 | Conjugate heat transfer for one pair and one geometry (a planar wall between a solid slab and a laminar channel): a FEniCSx transient-diffusion window session with boundary-trace flux output; an OpenFOAM energy-equation window session (restart per window, interface boundary update, read-back, time-directory snapshot/restore); interface supports as 2D `UnstructuredMesh` surfaces; one declared CHT model with sourced applicability conditions; an end-to-end run | `src/engcore/execution/multiphysics/**`, `src/engcore/coupling/**`, `providers/fenicsx/**`, `providers/openfoam/**` |
| E3 | 1D transient diffusion on a moving domain `[0, L(t)]` in ALE form with a declared linear mesh-motion law, material velocity 0, vertex-centred FV on `numerical.moving_mesh`, a GCL-consistent time rule, linear solves through `SciPyLinearProvider`; tests for constant-state preservation, GCL, a known moving-boundary solution and rollback | `src/engcore/numerical/**`, `src/engcore/domains/thermal_models/**` |

Planned capabilities (enter `capabilities` only at FOUNDATION): `numerics.adaptive_mesh_1d_transient`,
`numerics.triangle_refinement`, `pde.nonlinear_diffusion_fenicsx`, `coupling.cht_fenicsx_openfoam`,
`thermal.ale_moving_domain_1d`.

## Prohibited

- any capability maturity change from a program gate result (Gate H);
- claims, SRIA or MCP reachability of a new capability before its computed stage is FUNCTIONAL;
- validation or benchmark claims without executed evidence; mocks presented as real runs;
- tetrahedral or hexahedral refinement; multi-dimensional or fluid ALE; turbulence models; further nonlinear templates;
  further provider pairs;
- a certified-area change without recertification (OD-3);
- LLM authority over models, thresholds, evidence or verdicts.

## Relationship to the rest of the ledger

- `battery.thevenin_1rc` stays a tracked capability at its computed stage (FUNCTIONAL, 2026-10-18) with every gate,
  evidence path and next action unchanged; it is no longer the epic. Defect, stabilization and evidence work on it stay
  allowed; a new battery capability foundation needs an exception.
- EXC-1 (adaptive mesh control) is superseded by this program on merge: its slices 1–4 and its exit gate (DV-27..DV-30)
  become part of G0 and M1.
- Genesis (`genesis.scientific_reasoning`) is not active; A2 still needs an epic change or an exception.
- Horizontal expansion OUTSIDE `allowed_scope` stays paused.

## Exit

Every program gate is PASS, FAIL or BLOCKED_WITH_EVIDENCE; the owner then names the next epic.
