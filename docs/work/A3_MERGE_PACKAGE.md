# Draft PR-ready package: declared field-kind mapping

Suggested title: `Distinguish cell-integrated amounts from densities in field remapping`
Status: IMPLEMENTED / UNVERIFIED / UNCERTIFIED. A-3 remains open; no automatic merge.
Branch: codex/declared-field-kind-mapping. Dependency/base: semantic PR
[#159](https://github.com/sharq-labs/forge/pull/159) at
98da0c024bd59bd0b18844941eafad3f1d24d428. Architecture decision commit 2e4fe486
precedes source edits. Checkpoint PR #158 remains independent. This package is local;
the owner authorized publication of semantic PR #159, not automatic A-3 publication.
For a future stacked draft, target codex/quantity-semantics to show only A-3 changes;
retarget/review against main after the semantic dependency integrates.

## Proposed description

The conservative mapper previously treated every supplied cell value as a density.
Integrated amounts on unequal source cells therefore could conserve the wrong integral.
Declare physical field kind explicitly and use a distinct integrated operator:
A'_j = sum_i (A_i/V_i) overlap_ij. Density mapping divides the overlapped density
sum by target measure. Intensive overlap averaging carries no conservation claim.

Reuse typed quantity meanings and domain-owned conserved amounts, existing field
records/stores, geometry admission and MappingDiagnostics. Add a scalar Grid1D adapter
sharing the same operator. Both coverage directions must hold; no extrapolation or
global rescaling. Interface/flux records carry explicit support, normal and orientation
conventions, but execution refuses pending A-4. No physical law inferred from units.

FieldDefinition optionally emits /2. Untyped writers retain /1 and typed payloads
cannot downgrade silently. Unit conversion retains semantic declarations. Graph and
transfer contracts reject kind substitution; actual source records must match graph
ports. Frozen exports/shapes and certification artifacts remain unchanged.

Compatibility impact: legacy conservative calls without kind now refuse. Per-consumer
owning-model migration is required before integration. Historical scientific identities
and numerical expectations were not rewritten. Semantic legacy-alias restrictions persist.

Adversarial tests are authored, NOT RUN. Compile-only syntax and whitespace checks
are static checks. Independent static review PASS is not scientific evidence. No pytest,
mutation, full assurance, provider run, Forge import check or OD-3 was executed.

## Exact A-3 changed-file inventory relative to 98da0c02

| File | Purpose |
| --- | --- |
| src/engcore/scientific/fields/semantics.py | New neutral field kinds, measures and declarative interface conventions |
| src/engcore/scientific/fields/definition.py | Optional versioned semantics and support/unit admission |
| src/engcore/scientific/fields/transfer.py | Reject semantic/mixed-kind contract substitution |
| src/engcore/scientific/multiphysics/graph.py | Typed scalar field admission; bypass legacy energy prose |
| src/engcore/data/field.py | Preserve semantic identity across unit conversion |
| src/engcore/execution/multiphysics/cell_mapping.py | Shared density/integrated/intensive operators and totals |
| src/engcore/execution/multiphysics/mapping.py | Declared-kind authoritative mapper and diagnostics |
| src/engcore/execution/multiphysics/transfer.py | Require executed record to match source port |
| src/engcore/numerical/field_mapping.py | Narrow Grid1D scalar overlap adapter with existing UNKNOWN UQ |
| tests/test_declared_field_kind_mapping.py | Counterexample and conservation/adversarial probes |
| docs/work/A3_ARCHITECTURE_DECISION.md | Preimplementation decision and policy/identity review |
| docs/work/A3_COMPATIBILITY_MATRIX.md | 62-file baseline consumer index and exact implementation references |
| docs/work/A3_STATIC_REVIEW.md | Independent A-J review and resolved findings |
| docs/work/A3_MERGE_PACKAGE.md | This package |
| docs/work/DEFERRED_VALIDATION.md | DV-113..116 recipes, NOT RUN |
| docs/work/ACTIVE_PLAN.md | Current task/dependency and remaining gates |
| docs/work/PROGRESS.md | Publication, implementation and static check record |

## Numerical scope and limitations

Preregistered source nodes(0,1,4), amounts(2,6), target nodes(0,2,4) must produce
(4,4), total8. Treating the raw amounts as density would produce(4,6), total10.
These expectations come from hand overlap arithmetic, not observed execution.
Tests also cover unequal areas, density unit conversion, partial coverage both ways,
refinement/coarsening, reversed axes, interface orientations, invalid units/kinds,
signed zero totals, source substitution, schema boundaries and material identity.

Supported execution is scalar CELL overlap or identity, within the existing geometry
set: 2D structured/convex polygons and 3D tetrahedra, plus the explicit 1D adapter.
All numerical support remains UNVERIFIED. The new tetrahedral permutation fixture
does not distinguish integrated/density split/merge behavior; 3D split/merge probes
are remaining coverage, not an established refinement capability.

1D values are caller-supplied arrays; checked grid digests do not authenticate origin,
time, lineage or applicability. Refinement/coarsening transfer is geometric arithmetic,
not a transient adaptive solver, history invalidation mechanism or recovery capability.
The new adapter stores no mesh-sized data in scientific provenance.

No vector/tensor mapping, cross-kind conversion, normal projection, sign-flip execution,
face discretization, source/reaction/storage physics, time integration or independent
local-error estimator is added. A-4 remains open. Spatial transfer uncertainty and
model discrepancy remain UNKNOWN. Integral closure never grants local physical validity.

## Integration gates and open decisions

1. Owner-reviewed explicit field-kind migrations for each conservative consumer;
   existing Phase1/Phase2 fixtures now refuse and cannot count as retained coverage.
   Do not simply label every historical field a density to obtain passing results.
2. Separately authorize DV-113 first, then DV-114..116; predecessor DV-101..112
   remain deferred on their appropriate trees. No gap CLOSED based on static PASS.
3. Recheck frozen API, old-reader refusal, serialization/graph/record identity,
   layering, certified dependency closure and normal CI on final integrated source.
   Shared runtime/trust changes require separately authorized final-source OD-3.
   No certification pin regeneration merely to silence failures.
4. Decide A-4 normal/face ownership, vector/frame scope, adaptive history/lineage,
   and 3D split/merge coverage before extending capability claims. Next bounded work
   should resolve explicit consumer migrations and authorized A-3 validation before
   executing interface signs or declaring M1/M2/E2 scientifically verified.
