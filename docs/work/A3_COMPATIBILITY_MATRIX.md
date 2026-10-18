# A-3 compatibility and affected-file matrix

Baseline: semantic dependency `98da0c02`; exact baseline references. Static symbol index, not executed migration or exhaustive dynamic/external discovery.

| File | Baseline lines | Effect |
| --- | --- | --- |
| `flagships/forge_flagships/geometry_slice.py` | 69, 285 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `flagships/forge_flagships/thermo_mechanical.py` | 36, 109, 170, 188 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `providers/calculix/tests/test_calculix_provider.py` | 55, 69 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `providers/fenicsx/tests/test_coupling_fenicsx.py` | 42, 86, 100, 271, 272, 279 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `providers/fenicsx/tests/test_pde_fenicsx.py` | 33, 83, 155, 229, 289 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `providers/openfoam/forge_openfoam/__init__.py` | 209, 276, 278 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/coupling/__init__.py` | 16 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/coupling/adapters.py` | 14, 20, 36, 40, 44, 52, 59, 80 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/data/field.py` | 10, 36, 43, 126, 131, 133, 211, 226, 240, 256, 270 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` | 55, 277, 291, 292, 293, 326, 360, 365, 371 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/domains/thermal_models/conduction2d.py` | 53, 55, 200, 461, 827, 861 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/execution/multiphysics/__init__.py` | 22, 80, 107 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/execution/multiphysics/conjugate_interface.py` | 232 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/execution/multiphysics/convergence.py` | 28, 58, 71 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/execution/multiphysics/interface_exchange.py` | 72 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/execution/multiphysics/mapping.py` | 5, 7, 13, 42, 44, 61, 652, 653, 655, 703, 704, 716, 718, 780, 936, 939, 1093 | Authoritative mapper admission/operator and diagnostics; conservative legacy calls now refuse |
| `src/engcore/execution/multiphysics/relaxation.py` | 21, 177, 178 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/execution/multiphysics/transfer.py` | 16, 17, 39, 99, 103, 107, 109, 221, 223, 340 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/numerical/mesh_adaptation.py` | 85, 118, 130, 155, 180, 249, 267, 268, 312 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/pde/contracts.py` | 36, 333 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/fields/__init__.py` | 39, 64, 85, 119, 122, 124 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/fields/conditions.py` | 25, 35, 144, 229, 252, 255, 272, 303, 310, 382 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/fields/definition.py` | 9, 45, 126 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/fields/result.py` | 9, 32, 171, 174, 193, 195, 325, 337 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/fields/transfer.py` | 31, 33, 61, 64, 66, 75, 77, 177, 180, 182, 239, 251, 262, 277, 279, 281, 349, 351, 353, 364, 365 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/models/structured_validity.py` | 4, 22, 147, 179, 203, 260, 306, 351 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/models/unknown_diagnostics.py` | 25, 164, 168, 187, 191, 196 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/multiphysics/mapping.py` | 22, 47 | Authoritative mapper admission/operator and diagnostics; conservative legacy calls now refuse |
| `src/engcore/scientific/multiphysics/ports.py` | 11, 77, 106, 119, 121, 190 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/multiphysics/report.py` | 11, 471, 473, 512, 514 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/scientific/multiphysics/value.py` | 10, 17, 23, 25, 38, 61, 63 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/spatial/__init__.py` | 6, 20 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/spatial/fields.py` | 4, 22, 63, 103, 105, 106, 142, 159, 214, 272, 312 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `src/engcore/spatial/mesh.py` | 228 | Typed nested definition identity and /2 readers; no historical relabeling; consumer migration review |
| `tests/architecture/test_quantity_semantics.py` | 15, 239 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/domains/thermal_models/test_conduction1d_nonuniform.py` | 24, 28, 63, 75, 100, 108, 115, 137 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/manufactured_conduction2d.py` | 43, 83 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/mutation_population_v4.py` | 5518, 5529, 5606, 5617, 5628, 5639 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/numerical/test_mesh_adaptation.py` | 17, 24, 41, 72, 81, 88 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_conduction2d.py` | 30, 32, 151, 196, 208, 257, 297, 315, 329 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_core_scientific_audit_batch16.py` | 40, 64, 65 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_core_scientific_audit_batch28.py` | 17, 49 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_core_scientific_audit_batch52.py` | 26, 28, 45, 46, 65, 71, 190 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_core_scientific_audit_batch53.py` | 6, 29, 33, 51, 52, 56, 65, 118, 211, 266 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_core_scientific_audit_batch57.py` | 28, 86, 87, 97, 98 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_field_composition.py` | 22, 47, 152, 154 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_field_profile_limit.py` | 41, 254, 271 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_field_profiled_conditions.py` | 24, 47 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_field_records.py` | 21, 24, 35, 53, 54, 176, 280, 291, 321, 335, 345, 379 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_field_values.py` | 20, 31, 32 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_min_foundation_electrothermal.py` | 778 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_pde_contracts.py` | 34, 82, 118, 194, 265 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_phase1_conservative_cell_mapping.py` | 3, 20, 23, 39, 43, 49, 53, 153, 159, 161 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_phase1_coupling_convergence_coverage.py` | 31, 239 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_phase2_external_coupling.py` | 33, 45, 46, 47, 48, 96 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_phase2_field_transfer.py` | 26, 30, 60, 65, 67, 68, 84, 148, 150, 151, 153, 162, 213, 215, 216, 227 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_phase35_ws3_conjugate_interface.py` | 20, 33, 43 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_phase3_br13_numerical_stability.py` | 39, 269 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_phase3_br16_mesh_validity_and_adaptation.py` | 29, 36, 124, 136, 137, 141, 166 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_spatial_core.py` | 24, 70, 155, 165, 169, 171, 176, 302 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_structured_validity.py` | 10, 12, 47, 49, 61 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
| `tests/test_unknown_diagnostics_v2.py` | 9, 11, 42, 44, 55, 111, 131 | Deferred regression; retain numerical expectations; legacy conservative fixtures need explicit justified migration |
