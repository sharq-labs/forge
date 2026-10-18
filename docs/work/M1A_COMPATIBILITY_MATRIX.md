# M1A compatibility and affected-file matrix

Baseline1f43c59e; exact static references, not executed migration or exhaustive dynamic discovery.

| File | Baseline lines | Impact |
| --- | --- | --- |
| `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` | 55, 277, 291, 292, 293, 326, 360, 365, 371 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |
| `src/engcore/execution/multiphysics/mapping.py` | 660, 661 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |
| `src/engcore/numerical/field_mapping.py` | 14, 24, 34, 35 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |
| `src/engcore/numerical/mesh_adaptation.py` | 39, 74, 85, 118, 130, 155, 180, 243, 249, 267, 268, 272, 280, 287, 288, 310, 312, 314, 318 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |
| `tests/domains/thermal_models/test_conduction1d_nonuniform.py` | 24, 28, 63, 75, 100, 108, 115, 137 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |
| `tests/numerical/test_mesh_adaptation.py` | 17, 24, 41, 42, 44, 49, 55, 57, 72, 81, 88 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |
| `tests/test_declared_field_kind_mapping.py` | 13, 14, 38, 39, 45, 77, 78, 97, 102, 106, 112, 138 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |
| `tests/test_phase3_br16_mesh_validity_and_adaptation.py` | 29, 124, 136, 137, 141, 151, 152 | Legacy geometry/refinement retained; new issuer/managed-state path opt-in; deferred integration |

## Exact current implementation references

| File | Lines | Change |
| --- | --- | --- |
| `src/engcore/numerical/mesh_adaptation.py` | 184, 190, 227, 236, 261, 284, 321, 339, 396, 409, 435 | Local lineage/state admission, invalidation or adversarial probe; NOT RUN |
| `src/engcore/numerical/interval_transfer.py` | 23, 27, 33, 57, 73, 90, 113, 131, 140, 152, 168, 175, 187, 195, 205, 210, 215 | Local lineage/state admission, invalidation or adversarial probe; NOT RUN |
| `tests/test_m1a_mesh_lineage.py` | 52, 75, 84, 96, 112, 129, 142, 155, 168, 179, 190, 205, 219, 234, 247, 262, 274, 285, 295, 312, 319, 328, 341, 348, 360 | Local lineage/state admission, invalidation or adversarial probe; NOT RUN |

## Compatibility and scientific impact

Only numerical/non-Core implementation changes. Grid1D fields, constructor, geometry digest, to_dict and old refine/adapt_grid signatures are unchanged; legacy transient/multidimensional refusals remain. No canonical export, frozen snapshot, existing Core schema, certification pin or capability ledger update.
New lineage/state/receipt audit records have explicit /1 schemas and deterministic material identity including exact root context, frame, geometry, parents, bisections and policy. Their from_dict refuses all unauthenticated audit import; there was no prior supported durable reader to break. Equal hashes/geometry do not establish local issuance. Export alone does not authorize ancestry.
A-3 FieldSemantics, ConservedQuantity and map_cells_1d are reused without shape/behavior changes. M1A deliberately narrows affine admission: all bound state units must be ratio scale, including intensive states. Standalone A-3 intensive affine conversion is unchanged. Guarded receipt totals/coverage are recomputed from actual data rather than trusting mapping metadata.
New AdaptiveMesh1D is opt-in; no existing domain solver or coupled runtime is migrated automatically. Registered field/resource consumers must use its handles; actual built-in dict/list containers are cleared on mesh change. External caches/provider state, concurrency and trusted durable recovery remain unsupported. Failed/consumed transfer never silently replaces populated current state.
Existing steady thermal reference at src/engcore/domains/thermal_models/conduction1d_nonuniform.py:19 and :326 has vertex/nodal unknowns and dual control volumes, whereas M1A states live on primal intervals. A future explicit dual-support adapter is required; no automatic state-placement conversion or invented refinement ancestry. M1 contract is docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md:48 and :93.
Downstream integration concerns are numerical field adapters, mesh-dependent state/cache owners, future thermal transient solver, adaptive driver and coupling history. Existing consumers in baseline index retain their legacy behavior. External/dynamic discovery is not exhaustive. Required future checks: frozen/import identity, legacy regressions, parent semantics and final integrated CI/certification; tests and OD-3 NOT RUN.
