# Phase 3.5 — proposed policy changes (NOT ACTIVE)

Status: **PROPOSED, not approved, not in force.** Written 2026-10-18 by Claude for the owner. Nothing below authorizes
any work. The active epic is `battery.thevenin_1rc` (`docs/project/scientific_capability_completion.json`); EXC-1
(adaptive mesh control, amendments A1–A3) is the only open exception and expires 2026-10-31
(`docs/work/ACTIVE_PLAN.md`). The policy is `docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md`.

The Phase 3.5 prompt asked for capabilities that the policy does not permit without an exception. This file separates
them from the permitted work done in Phase 3.5 and drafts the narrowest change for each. Each draft states the eight
fields the policy requires; the owner-approval field is **PENDING** in every one.

## What could proceed without a change (done in Phase 3.5)

| Workstream | Work | Why it is permitted |
| --- | --- | --- |
| WS1 | Mandatory same-problem admission for corroboration | A defect / false-support fix; the owner directed it in the session (closes OD-P2-3) |
| WS2 | Electrothermal migration candidate on the runtime | Runtime engineering under the existing coupling authority (ERT V1 / Phase 2 precedent); no new capability, legacy path stays default |
| WS3 | Conjugate-interface admission, provider-pair maturity record | Provider-neutral coupling infrastructure (Phase 2 P2-BR12 precedent); no adapter, no solver |
| WS7 | Cross-phase review and guards | Stabilization |

## Which blocked work EXC-1 can legally cover

EXC-1 is an exception for **adaptive mesh control**. An amendment of the same exception is not a second exception
(precedent: A1–A3). So WS4 (transient 1D adaptation, conservative 1D state transfer, 1D coarsening, triangle
refinement) can be covered by amending EXC-1 (P35-A4, P35-A5). Nonlinear PDE execution, FE/CFD conjugate heat
transfer and ALE are **not** adaptive mesh control; EXC-1 cannot cover them. Each would be a second concurrent
exception, which the anti-loophole rule says triggers an OWNER_DECISION_REQUIRED review of the active epic (OD-6)
before any further exception is granted.

**Recommendation.** Decide OD-6 first: either change the active epic through its canonical mechanism (a reviewed PR
changing the ledger's `active_epic`, the test pin and the PR template), or run the program-level review the
anti-loophole rule demands. Three serial exceptions (P35-E1..E3) on top of EXC-1 would be exactly the "exceptions as
the default roadmap mechanism" the policy forbids. P35-A4/A5 can be decided on their own.

---

## P35-A4 — EXC-1 amendment A4: transient 1D adaptation with conservative state transfer and coarsening (WS4 A–C)

1. **Exact scope:** `src/engcore/numerical/mesh_adaptation.py` (coarsening, refinement tree);
   a new `src/engcore/numerical/interval_transfer.py` (conservative state transfer between two `Grid1D`s);
   `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` (a TRANSIENT solver path beside the steady one);
   their tests.
2. **Allowed capability work:**
   - transient `rho c u_t = (k u_x)_x + q` on a non-uniform `Grid1D`, vertex-centred FV, backward Euler (declared
     order 1), explicit Dirichlet/flux boundaries, a sourced initial condition; nothing defaulted;
   - conservative transfer of the cell-integrated energy `int rho c u dx` between grids by exact interval overlap; the
     transferred variable is declared conservative (energy density) or intensive (temperature with a declared
     `rho c`, transferred as energy and divided back); affine units refused; signed and zero-integral states handled;
     transfer coverage and conservation residual recorded;
   - coarsening only by undoing a recorded bisection (parent-child tree), never below the initial grid, with the same
     conservative transfer;
   - an adaptive transient loop (refine/coarsen between time steps from the existing indicator) whose every grid
     version, parent and transfer is recorded; stale fields and coupling-acceleration history invalidated on a grid
     change.
3. **Reason:** owner-directed Phase 3.5 (engineering foundation completion).
4. **Start condition:** owner approval of this amendment in the session.
5. **Exit condition:** DV-27..DV-30 (EXC-1) plus the new transient/transfer tests executed and passing, or every
   failure recorded; a scientific review with no false-support finding.
6. **Expiry:** the EXC-1 expiry (2026-10-31) unless the owner extends it.
7. **Owner approval:** **PENDING.**
8. **Still prohibited:** 2D/3D refinement (P35-A5); wiring into `uq_studies` or claims; any capability declaration,
   ledger entry or `ValidationCheck`; validity conditions without sourced bounds; changes to the uniform
   `conduction1d`; treating an indicator as an error bound.

## P35-A5 — EXC-1 amendment A5: conforming triangle refinement (WS4 D)

1. **Exact scope:** a new `src/engcore/numerical/triangle_refinement.py` and its tests.
2. **Allowed capability work:** newest-vertex bisection of marked triangles with conformity closure (no hanging
   nodes), quality and inversion refusal (`numerical.mesh_quality`), recorded parent-child mesh versions, and
   cell-average transfer between parent and children reusing the Phase 1/2 conservative 2D remap
   (`FieldMapper.conservative_cell`) — no new transfer algorithm.
3. **Reason:** owner-directed Phase 3.5.
4. **Start condition:** owner approval; P35-A4 decided first.
5. **Exit condition:** new tests (conformity, conservation of cell integrals across refinement, quality bounds,
   determinism) executed and passing; review.
6. **Expiry:** as P35-A4.
7. **Owner approval:** **PENDING.**
8. **Still prohibited:** tetrahedral refinement; a 2D adaptive PDE solve (no 2D solver path is admitted); claims or
   capability declarations; hexahedra.

## P35-E1 — new capability: a provider-backed nonlinear PDE (WS5)

Not coverable by EXC-1; triggers OD-6.

1. **Exact scope:** one new Forge operator template in `src/engcore/pde/contracts.py` — steady scalar diffusion with
   temperature-dependent conductivity `-div(k(u) grad u) = f`, `k(u) = k0 (1 + beta (u - u0))`, 2D affine triangles,
   Lagrange P1/P2, Dirichlet/Neumann/Robin as today; `NONLINEAR_TEMPLATES` in `pde/nonlinear.py`; a Newton path in
   `providers/fenicsx/forge_fenicsx` (dolfinx `NonlinearProblem` + `NewtonSolver`, exact UFL Jacobian), returning the
   per-step Newton histories `admit_nonlinear_execution` re-checks; tests incl. a manufactured solution.
2. **Allowed capability work:** that template, its admissibility ranges (`k(u) > 0` over the admitted temperature
   range, refused otherwise), its provider execution and records.
3. **Reason:** owner-directed Phase 3.5 (BR17 part A).
4. **Start condition:** OD-6 decided so that a further capability may start; owner approval of this exception.
5. **Exit condition:** manufactured-solution convergence and Newton-failure tests executed in the WSL FEniCSx env;
   review.
6. **Expiry:** to be set by the owner.
7. **Owner approval:** **PENDING.**
8. **Still prohibited:** any other nonlinear template; a Forge-internal PDE solver; claims/capability declarations
   before FUNCTIONAL; treating a small Newton residual as an error bound.

## P35-E2 — new capability: FE <-> CFD conjugate heat transfer (WS3, OD-P2-1)

Not coverable by EXC-1; triggers OD-6.

1. **Exact scope:** a FEniCSx transient-diffusion window session (restart per window, boundary-trace flux output on
   interface facets); an OpenFOAM energy-equation window session (case restart per window, interface boundary-field
   update, interface read-back, time-directory snapshot/restore) in `providers/openfoam`; interface supports as
   `UnstructuredMesh` 2D surfaces so the existing conservative remap applies; one declared CHT model with sourced
   applicability conditions in the ledger; an end-to-end integration test.
2. **Allowed capability work:** exactly that pair and one interface geometry (a planar wall between a solid slab and
   a laminar channel flow); the admission already built (`conjugate_interface.py`).
3. **Reason:** owner-directed Phase 3.5 (BR12).
4. **Start condition:** OD-6 decided; owner approval.
5. **Exit condition:** the real coupled run executed in the WSL envs with conservation diagnostics recorded; a
   comparison against an analytic conjugate case; review. Only then `REAL_EXECUTION_DEMONSTRATED` /
   `NUMERICALLY_VERIFIED` may be recorded, with run digests.
6. **Expiry:** to be set by the owner.
7. **Owner approval:** **PENDING.**
8. **Still prohibited:** other provider pairs; turbulence models; claims of validation; mocks presented as real runs.

## P35-E3 — new capability: a bounded ALE formulation (WS6)

Not coverable by EXC-1; triggers OD-6.

1. **Exact scope:** 1D transient diffusion on a moving domain `[0, L(t)]` in ALE form,
   `d/dt int_{V(t)} rho c u dx + [rho c u (v - w)]_boundary = [k u_x]_boundary`, with mesh velocity `w` from a declared
   linear mesh-motion law and material velocity `v = 0`; vertex-centred FV on the `numerical.moving_mesh` kinematics;
   a GCL-consistent time rule (any rule is exact in 1D; the record states it); linear solves through the existing
   `SciPyLinearProvider` (the identifiable provider); tests for constant-state preservation, GCL, a known
   moving-boundary analytic solution and rollback.
2. **Allowed capability work:** that one 1D formulation.
3. **Reason:** owner-directed Phase 3.5 (BR17 part B).
4. **Start condition:** OD-6 decided; owner approval.
5. **Exit condition:** the four test families executed and passing; review.
6. **Expiry:** to be set by the owner.
7. **Owner approval:** **PENDING.**
8. **Still prohibited:** multi-dimensional ALE; fluid ALE; moving interfaces between coupled participants; claims.
