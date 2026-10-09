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

| provider | adapter | status here | real-run test |
|---|---|---|---|
| Gmsh 4.15.2 | `engcore.spatial.gmsh_adapter` | AVAILABLE (ran) | yes, executed |
| OpenVSP | `providers/openvsp` | NOT_INSTALLED (openvsp.org blocked by egress policy) | skip-gated |
| OpenRadioss | `providers/openradioss` | NOT_INSTALLED (release download 403) | skip-gated |
| Project Chrono | `providers/chrono` | NOT_INSTALLED (conda-only; the PyPI `pychrono` is an unrelated package and is refused as BROKEN by API identity) | skip-gated |
| FEniCSx | `providers/fenicsx` (existing) | NOT_INSTALLED | slice numerical rung records provider_unavailable |

## DEFERRED_HARDENING ledger

Non-blocking items found during the program. None of them can turn UNKNOWN into known or create false support in
the code paths as built; each blocks a stronger claim later.

1. Provider translations are unverified against running providers: OpenVSP parameter names, OpenRadioss deck syntax
   (`/RWALL/PLANE` card layout, `/DT`), Chrono 9 API calls. First real runs must pass the skip-gated reference tests.
2. Chrono adapter: actuators, joint limits, joint-coordinate outputs and compliant joints are refused, not translated.
3. Gmsh adapter: no union boolean, no quad/hex meshes, per-body sizing through point sizes only, feature matching is
   sample-based (refuses ambiguity; curved faces are polygonal), STEP files with conversion-based units (inch) refused.
4. Multibody: closed kinematic loops are refused by the assembly topology.
5. Product templates: all couplings are `declared_not_executable`; vehicle suspension force elements and
   electromagnetics/losses have no adapter; capability_report does not cross-check provider physics families.
6. The existing `systems/aerospace/multirotor` reference study was not re-audited for hidden defaults.
7. TwinRevision `ApplicabilityState` / `UncertaintyStatus` overlap Core `ValidityStatus` and SRIA uncertainty
   channels (review round 2, LOW-8); `verify_evidence` is not yet wired to an SRIA evidence store.
8. DesignHistory head anchoring relies on the caller keeping `DiscoveryRun.history_head`; no persistence store yet.
9. Scene IR has no renderer; field overlays are not checked against a mesh.
10. Lint: new modules follow the repository's own style but not every ruff rule (UP037/I001); pre-existing F401s in
    `systems/aerospace/multirotor/study.py`, `systems/topology.py` and `spatial/fields.py`.
11. The vertical slice's FEniCSx rung has not executed in any environment yet.
12. Hardened-core recertification is required for this branch (tests/**, pyproject.toml and
    tools/certification/skip_admission.py changed) and has not been run.
