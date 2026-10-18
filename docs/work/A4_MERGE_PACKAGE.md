# Draft PR-ready package: executed interface flux conventions

Suggested title: `Execute typed normal and orientation conventions for planar interface fluxes`
Branch codex/interface-flux-execution, base4f239fa7fe705e3d8ae390a8e885302dcb07904e.
Dependency: main -> semantic [PR#159](https://github.com/sharq-labs/forge/pull/159)
-> A-3 [PR#160](https://github.com/sharq-labs/forge/pull/160) -> A-4.
Checkpoint PR#158 remains independent. Architecture/compatibility decision commit
dab92bf0 precedes source changes. Future stacked draft should target
codex/declared-field-kind-mapping to isolate A-4. This package is local, no automatic
A-4 publication or merge. Publication of A-3 was explicitly authorized separately.

IMPLEMENTED / UNVERIFIED / UNCERTIFIED. No A-4 or M1/E2 closure based on code.

## Proposed description

Interface admission formerly recorded prose normals without applying them during
field transfer. Add a typed executable interface contract used by graph admission,
direct FieldMapper and TransferEngine. It binds both supports, exact physical meaning,
conserved measure, common-plane geometry, representation, coverage and sign relation.

Bounded execution supports scalar normal CELL components on structured rectangular
surface meshes in one declared plane/frame. Derived orientation/normal sign is applied
to the mapped values. Opposing outward normals produce equal-and-opposite physical
normal components under the declared relation. Integrated amounts divide by source
area before overlap; density divides by target area. Full coverage required both ways.
Roundtrip diagnostics and requested error limits are enforced.

Neutral Dirichlet-Neumann admission takes explicit domain meanings. CHT is its thermal
instance and requires typed semantics/transfer; no additional receiver sign multiplication.
Constitutive laws and physical applicability remain domain-owned. Legacy prose-only
admission now refuses and requires explicit migration; no historical identity rewrite.

Executable interface edges emit /3; legacy /1 and scalar semantic /2 writer shapes
remain. Typed CHT /2 output embeds graph-bound neutral admission. No frozen export,
certification artifact or scientific evidence vocabulary changed. Independent static
review PASS; two implementation defects corrected before completion. Tests NOT RUN.

## Exact affected-file inventory relative to A-3

| File | Change |
| --- | --- |
| src/engcore/scientific/fields/interface_transfer.py | New typed sign/representation/measure/geometry contract |
| src/engcore/scientific/fields/definition.py | Admit declared 3D normal on 2D parameter support |
| src/engcore/scientific/fields/semantics.py | Clarify convention versus executable transfer boundary |
| src/engcore/scientific/multiphysics/graph.py | Optional edge /3 contract, exact admission and identity |
| src/engcore/execution/multiphysics/mapping.py | Signed overlap execution, roundtrip limits and distinct diagnostics |
| src/engcore/execution/multiphysics/transfer.py | Pass the admitted contract to mapper |
| src/engcore/execution/multiphysics/interface_exchange.py | Generic typed density/integrated admission and neutral DN instance |
| src/engcore/execution/multiphysics/conjugate_interface.py | Explicit thermal wrapper and graph-bound admission output |
| tests/test_interface_flux_execution.py | Numerical/adversarial/regression probes, NOT RUN |
| docs/work/A4_ARCHITECTURE_DECISION.md | Preimplementation decision and compatibility review |
| docs/work/A4_COMPATIBILITY_MATRIX.md | 48-file baseline index and exact current implementation lines |
| docs/work/A4_STATIC_REVIEW.md | Independent A-J review and resolved findings |
| docs/work/A4_MERGE_PACKAGE.md | This package and next M1 task |
| docs/work/ACTIVE_PLAN.md | Current dependency, bounded scope and gates |
| docs/work/DEFERRED_VALIDATION.md | DV-117..120 recipes, NOT RUN |
| docs/work/PROGRESS.md | Publication, implementation, review and static check record |

## Scientific guarantees and limitations

| Layer | What the implementation can report | What remains unestablished |
| --- | --- | --- |
| Local mapping consistency | Arithmetic overlap residual and same-kind roundtrip diagnostic | Local physical validity or forward error bound |
| Integral interface conservation | Actual stored source/target totals normalized by executed conventions | Independent target solver balance; result is constructed by transfer |
| Coupled physical conservation | UNKNOWN | Actual independent participant fluxes, storage, sources, constitutive law |
| Numerical solution verification | Not established | Manufactured/analytic solutions, refinement, solver error |
| Experimental validation | Not established | Admissible context-matched measurements and model discrepancy |

Spatial uncertainty remains UNKNOWN. Common plane, scalar normal component origin and
physical meanings are caller/domain declarations, not independently established geometry
or model evidence. No vector projection, curved/unstructured/moving interfaces, partial
coverage, cross-frame/cross-kind conversion, time integration or normal-varying surface.
E2's real FE/CFD unstructured surface path is not supplied here. Existing field-valued
CoupledConservation refusal remains; no mapping diagnostic becomes a physical balance.

All new tests remain NOT RUN: opposing/same/reversed normal and orientation, unequal
areas/discretizations, density/integrated distinction, wrong-sign counterexample, missing
conventions, geometry/vector/coverage/projection refusal, semantics/units/identity/schema,
roundtrip limits, identity sign and thermal plus nonthermal charge/potential examples.
Historical WS3 admission/sign expectations need explicit migration before integration.

Deferred execution: DV-117 first, then parent guarantees DV-118, concrete legacy
migration audit DV-119 and Core/runtime compatibility DV-120. DV-101..116 remain deferred.
Normal CI/integration tiers and final-tree OD-3 require separate authorization; no pins
regenerated merely to silence failures. No pytest/provider/mutation/full assurance ran.

## Precise next bounded M1 task

M1.1: **lineage-bound 1D state transfer and reversible bisection coarsening**.
Work in numerical/mesh_adaptation.py and a narrow numerical/interval_transfer.py bridge
that reuses A-3 map_cells_1d and FieldSemantics instead of duplicating arithmetic or
inventing a second conserved-quantity vocabulary.

Bind the transferred state to the actual Grid1D version, declared measure/kind, existing
content-addressed data and existing provenance/context records. Record parent/children
and bisection lineage. Coarsen only by undoing recorded sibling bisections; refuse stale
or mismatched lineage/support. Produce a new state/version and explicit invalidation of
old field bindings and coupling-acceleration history. Do not claim that bare matching
digests authenticate value origin. Keep kernel free of temperature/energy conditionals.

Write nonthermal amount/density/intensive probes, unequal-cell conservation and signed
totals, split/undo cycles, forged sibling/stale-state refusal, invalid coverage and history
invalidation. Do not execute them without authorization. This precedes M1.2's transient
vertex-centred FV/backward-Euler conduction reference with explicit sourced boundaries,
initial state and material/storage law. Conduction computes energy from its domain law;
Core must never infer conserved energy from temperature alone.

OD-6 already authorizes building M1 within scope; DV0 does not block that build.
Owner decisions needed before integration/scientific verification: explicit legacy
alias/field-kind/CHT migration dispositions; stack/checkpoint integration and validation
authorization; reference conduction boundary/initial/material sources if not supplied;
final certification and gate decisions. Extending beyond reversible bisections, the
approved conduction reference or scalar/static geometry needs a separate scope decision.
No additional physics or approval requirement is inferred for the already-authorized
bounded M1 foundation itself.
