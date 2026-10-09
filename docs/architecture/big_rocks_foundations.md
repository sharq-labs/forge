# Big Rocks Foundations: Geometry, Assemblies, Providers, Twins, Discovery

**Status: built on branch `claude/adoring-cray-jj367z` (base `origin/main` 44637065); awaiting the integration
gate and hardened recertification. Nothing here is qualified or validated.**

This page maps the platform foundations added by the Big Rocks expansion program and records what was deferred.
Executable contracts and tests are the source of truth.

## Layer map (where each rock lives)

```text
Scientific Core (frozen; NOT modified)
  scientific.twins.ScientificTwin, scientific.ir.*, scientific.results.*
        |
spatial/   geometry.py      GeometryModel: bodies (rectangle, disk, box, cylinder, imported STEP/BREP), frames,
                            rigid transforms, regions, boundaries, interfaces, multi-domain roles, material and
                            boundary-condition bindings, ProviderEntityMap, GeometryReceipt, MeshBinding
           parametric.py    GeometryParameter (unit-aware kinds), ParametricGeometry, GeometryVariant (+ replay)
           gmsh_adapter.py  general Gmsh/OCC provider: cutouts, conformal fragment, feature matching by geometric
                            containment on the owning body's boundary, physical groups, SpatialMesh + receipt
systems/   assembly.py      AssemblyTopology on SystemDefinition: levels, placements, connection points, joints
                            (fixed/revolute/prismatic/spherical, compliant placeholder), interfaces, ownership, slots
           multibody.py     MultibodyModel derived from the assembly (sourced mass properties, declared gravity)
           twin_revision.py TwinRevision: context-bound evidence/applicability/uncertainty over a ScientificTwin
           products/        ProductTemplate + capability_report; drone, vehicle, motor, HVAC compositions
providers/ health.py        NOT_INSTALLED / BROKEN / AVAILABLE / UNQUALIFIED / QUALIFIED; probe receipts;
                            qualification bound to provider build + adapter version
design/    grammar.py       compatibility rules (ProposalGate), three-valued constraint evaluation
           multifidelity.py standard ladder, ledgers with monotone standing, budgeted promotion
           history.py       append-only hash-chained attempt log (failures are information)
           hierarchy.py     component-owned design spaces, sub-candidate replacement, recomposition lineage
           search.py        deterministic discovery loop (classification: search_record_not_validation)
engineering/scene.py        Scene IR (authority: presentation_only)
mcp/foundations.py          describe_engineering_platform / plan_product / run_product_screening (transport only)
providers/{openvsp,openradioss,chrono}/   fail-closed adapter distributions (translation unverified)
flagships/forge_flagships/geometry_slice.py   the first general geometry vertical slice (architecture proof)
```

## Invariants these layers enforce

* Provider tags (Gmsh `(dim, tag)`) never become Forge identity; a MeshBinding is checked against the receipt that
  produced the mesh.
* Units are canonical metres in identity; imported geometry needs a declared unit, checked against the STEP header.
* Nothing physical is defaulted: boundary values, material states, mass properties, gravity, solver settings,
  product inputs and joint compliance must be declared with a source or remain UNKNOWN.
* Available is not qualified; qualified is not validated; supported (multi-fidelity standing) is not validated;
  search results and promotions are scheduling records, not evidence.
* Evidence, applicability and quantified uncertainty are bound to the exact twin context digest; a context change
  drops them; a CANDIDATE cannot carry calibration, validation or measurement evidence.
* The evidence rung of the fidelity ladder decides only with admitted evidence references.

## Provider status in the build environment

Second program ("next three rocks", 2026-10-09): provider environments were created in the session container from
conda-forge with micromamba under `$HOME/mm/root/envs` (`FORGE_PROVIDER_ENVS` layout); runs are recorded in
`docs/work/PROGRESS.md`. Available is not qualified: nothing below is a qualification record.

| provider | adapter | status in the session container | real-run test |
|---|---|---|---|
| Gmsh 4.15.2 | `engcore.spatial.gmsh_adapter` | AVAILABLE | executed |
| Project Chrono 10.0.0 (conda-forge `pychrono`) | `providers/chrono` | AVAILABLE in the `chrono` env (identity bound to the conda records, file bytes and env digest) | pendulum reference route executed and PASSED (2 solvers); NOT_INSTALLED in the main venv |
| FEniCSx (dolfinx 0.11.0) | `providers/fenicsx` | AVAILABLE in the `fenicsx` env | existing suite + slice numerical rung executed |
| CalculiX 2.23 | `providers/calculix` | AVAILABLE in its own `calculix` env | existing suite executed (FEniCSx-vs-CalculiX comparison needs the separate env: same-env paths are not independent) |
| OpenVSP | `providers/openvsp` | NOT_INSTALLED: not on conda-forge or PyPI; openvsp.org blocked | skip-gated |
| OpenRadioss | `providers/openradioss` | NOT_INSTALLED: not on conda-forge or PyPI; GitHub releases 403 | skip-gated |

## Next three rocks (second program)

* **Provider reality / qualification path** -- `engcore.providers.qualification`: an adapter-declared
  `ReferenceRoute` (exact request, observable, reference, tolerance with its error budget, scope);
  `record_route_run` measures the observable itself and binds build, adapter (with a source digest), request and
  execution record; a `RouteRunLedger` hash chain commits every run; `assess_health` admits a
  `ProviderQualification` only when it binds a declared route digest and a ledger head whose committed runs of that
  route and build all passed. `tools/provider_routes.py` runs an adapter's routes in its provider env. Nothing
  issues a qualification. Real-run findings on Chrono 10: `ChMatrix33d.SetItem` does not exist; the NSC default
  solver (PSOR) did not hold a bilateral revolute joint, so the solver is a required declaration.
* **Executable product coupling** -- `engcore.systems.products.drone_coupled`: propeller (static C_T/C_P) ->
  DC-equivalent motor + ESC -> battery (OCV + internal resistance) -> lumped steady winding temperature, one
  implicit window of `MultiphysicsRuntime`; every coefficient a declared input; energy crossings declared;
  infeasible duty, battery power limit, thermal runaway and over-limit winding temperature refused; uncertainty
  UNKNOWN. MCP: `run_product_screening(..., screening="coupled_hover")`.
* **Twin evidence and design memory in SRIA** -- `engcore.claims.twin_evidence` resolves TwinRevision pointers
  (`sria:<id>@<record_hash>`) against SRIA records and the gateway's `ScientificBelief`; `engcore.claims.design_memory`
  anchors a DesignHistory head in the campaign event chain through SRIA's generic `RECORD_CHAIN_ANCHORED` event
  (`sria.campaign.anchors`, `IncrementalCampaignRunner.anchor_record_chain`). SRIA still imports only `scientific`.

## DEFERRED_HARDENING ledger

Non-blocking items found during the program. None of them can turn UNKNOWN into known or create false support in
the code paths as built; each blocks a stronger claim later.

1. Provider translations unverified against running providers: OpenVSP parameter names, OpenRadioss deck syntax
   (`/RWALL/PLANE` card layout, `/DT`) -- neither provider is installable here. Chrono 10 is checked only by its
   pendulum route (identity orientation, point mass, one revolute joint, Euler implicit linearized): rotated bodies,
   real inertia, other joint kinds and HHT are not exercised (HHT is refused).
2. Chrono adapter: actuators, joint limits, joint-coordinate outputs and compliant joints are refused, not translated.
3. Gmsh adapter: no union boolean, no quad/hex meshes, per-body sizing through point sizes only, feature matching is
   sample-based (refuses ambiguity; curved faces are polygonal), STEP files with conversion-based units (inch) refused.
4. Multibody: closed kinematic loops are refused by the assembly topology.
5. Product templates: only the drone's coupled hover chain is executable (`iterative_executable`); the drone's
   rotor-aero -> structure coupling and every vehicle/motor/HVAC coupling stay `declared_not_executable`; the coupled
   chain is a steady algebraic screening (static propeller coefficients, lumped thermal, no transient); vehicle suspension force elements and
   electromagnetics/losses have no adapter; capability_report does not cross-check provider physics families.
6. The existing `systems/aerospace/multirotor` reference study was not re-audited for hidden defaults.
7. TwinRevision `ApplicabilityState` / `UncertaintyStatus` overlap Core `ValidityStatus` and SRIA uncertainty
   channels (review round 2, LOW-8). Twin evidence resolution is pointer backing, not a validation verdict; the
   polarity of a support/contradiction record is read from its payload's `polarity` key (domain packs do not yet
   standardise it); verification assessments are not part of an SRIA record's identity.
8. Design-memory anchors use unkeyed SHA-256 like the rest of campaign persistence (accidental corruption, not a
   deliberate rewrite of every stored byte); the stored history file is the caller's (save-then-anchor). The
   provider qualification ledger is a record, not a persisted store.
9. Scene IR has no renderer; field overlays are not checked against a mesh.
10. Lint: new modules follow the repository's own style but not every ruff rule (UP037/I001); pre-existing F401s in
    `systems/aerospace/multirotor/study.py`, `systems/topology.py` and `spatial/fields.py`.
11. The vertical slice's FEniCSx rung executed only in the session container's provider env (dolfinx 0.11.0).
12. Hardened-core recertification is required for this branch (tests/**, pyproject.toml,
    tools/certification/skip_admission.py and src/engcore/mcp/server.py changed) and has not been run: it writes
    certification/current_core_v2.json, which this program was told not to touch. CORE_CERTIFIED
    `sria/campaign/runner.py` was not modified.
