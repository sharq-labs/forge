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
