# A-4 compatibility and affected-consumer matrix

Exact baseline references: A-3 4f239fa7. Static index, not executed migration or exhaustive external/dynamic discovery.

| File | Baseline lines | Impact |
| --- | --- | --- |
| `flagships/forge_flagships/battery_cooling.py` | 64, 222, 226 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `providers/fenicsx/tests/test_coupling_fenicsx.py` | 35, 138, 139, 143, 314 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `providers/pybamm/tests/test_pybamm_multiphysics.py` | 28, 96, 99 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `providers/pybamm/tests/test_system_runtime_battery.py` | 36, 101, 104 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/compositionpacks/blueprint.py` | 18, 19, 58, 61, 81, 83, 208, 220 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/compositionpacks/builtin_electrothermal_feedback.py` | 46, 443, 449, 455 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/compositionpacks/builtin_thermal_resistance.py` | 33, 412 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/execution/multiphysics/__init__.py` | 22, 62, 80, 107, 108 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/execution/multiphysics/conjugate_interface.py` | 26, 46, 54, 88, 89, 115, 116, 144, 145, 146, 147, 160, 232, 247, 248 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/execution/multiphysics/interface_exchange.py` | 16, 17, 47, 76, 78, 86, 87, 138, 164 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/execution/multiphysics/mapping.py` | 7, 658, 663, 711, 1118 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/execution/multiphysics/runtime.py` | 84, 388 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/execution/multiphysics/transfer.py` | 21, 39, 80, 99, 166, 285, 371 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/planning/__init__.py` | 32, 94 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/planning/blueprint.py` | 16, 17, 176, 180, 193, 194, 273, 277 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/planning/intent.py` | 238, 262, 283, 294, 326, 793 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/scientific/fields/semantics.py` | 24, 56, 68, 101, 126 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/scientific/multiphysics/__init__.py` | 15, 22, 170, 172 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/scientific/multiphysics/conservation.py` | 109, 187 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/scientific/multiphysics/graph.py` | 29, 48, 98, 120, 123, 140, 141, 156, 157, 200, 236, 239, 408, 553, 562 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/systems/electrothermal/runtime_adapter.py` | 107, 214 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `src/engcore/systems/products/drone_coupled.py` | 45, 280, 282, 283, 284, 285, 287 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/architecture/test_cross_domain_fixtures.py` | 4, 40, 44, 132, 133, 166, 207, 208, 252, 263, 307, 310, 311 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/architecture/test_quantity_semantics.py` | 11, 19, 49, 55, 136, 142, 160, 207, 209, 213, 243, 287, 288, 289 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/claims/test_coupling_numerical_condition.py` | 24, 60, 61 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/multiscale_reference.py` | 63, 308, 309 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_big9_review_runtime_fixes.py` | 27, 74, 75 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_declared_field_kind_mapping.py` | 10, 11, 17, 19, 139, 152, 172, 188, 201, 232, 242, 289, 296, 302, 337 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_external_participant_checkpoints.py` | 24, 170, 171 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_concurrent_jacobi.py` | 23, 129, 130 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_conservation_history.py` | 22, 25, 66, 67, 72 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_event_aligned_outcome.py` | 19, 61, 62 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_fan_in_units.py` | 27, 45 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_iqn_ils.py` | 22, 194, 195 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_numerical_error_accounting.py` | 21, 56, 57 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_splitting_estimate.py` | 24, 76 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_multiphysics_window_control.py` | 25, 99, 158, 228, 229 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase1_conservative_cell_mapping.py` | 20, 53, 161 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase1_coupling_convergence_coverage.py` | 33, 97, 98, 174 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase1_system_runtime_outcomes.py` | 26, 65, 66 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase2_coupling_authority.py` | 40, 208, 209 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase2_external_coupling.py` | 9, 29, 35, 100, 103, 109, 110, 111, 158, 163 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase2_field_transfer.py` | 26, 68, 151, 215 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase35_ws3_conjugate_interface.py` | 16, 22, 46, 48, 65 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase3_br14_iqn_imvj.py` | 29, 223, 224 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_phase3_br15_window_error_control.py` | 33, 92, 190 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_system_runtime_external_providers.py` | 21, 69, 70 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |
| `tests/test_world_runtime_sprint1.py` | 62, 234 | Admission/schema/normal execution or downstream caller; explicit migration and deferred regression |

## Exact A-4 implementation references

| File | Current lines | Impact |
| --- | --- | --- |
| `src/engcore/scientific/fields/interface_transfer.py` | 18, 23, 28, 32, 41, 90, 93, 116, 124 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `src/engcore/scientific/fields/definition.py` | 97 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `src/engcore/scientific/fields/semantics.py` | 24 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `src/engcore/scientific/multiphysics/graph.py` | 49, 90, 109, 263, 554, 577 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `src/engcore/execution/multiphysics/mapping.py` | 722, 964 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `src/engcore/execution/multiphysics/transfer.py` | 164 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `src/engcore/execution/multiphysics/interface_exchange.py` | 49, 56, 81, 155, 195, 215 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `src/engcore/execution/multiphysics/conjugate_interface.py` | 73, 102 | Typed admission/execution/schema or adversarial regression; NOT RUN |
| `tests/test_interface_flux_execution.py` | 88, 107, 112, 118, 132, 137, 152, 167, 177, 189, 213, 226, 239, 248, 254, 260, 273, 280 | Typed admission/execution/schema or adversarial regression; NOT RUN |

## Compatibility dispositions

Core Freeze reviewed before edits in decision commit dab92bf0. No canonical frozen exports, existing Evidence/UQ vocabulary, field record/mesh schemas or certification artifacts changed. CouplingEdge optional interface field emits /3; old /1 and scalar /2 writer shapes retained. InterfaceTransfer owns /1, CHT typed admission owns /2 and embeds exact graph identity. New FieldMapper keyword-only interface_transfer does not alter old positional calls; old unqualified flux execution still refuses.
FieldDefinition /2 remains unchanged in shape: a 3D normal may describe a 2D parameter surface, but execution requires explicit qualified common-plane transfer. Scalar port frames remain forbidden; scalar normal basis belongs to InterfaceConvention. No vector FrameTransform/projection is silently applied.
Concrete legacy migration: tests/test_phase35_ws3_conjugate_interface.py:68-104 expects untyped/prose admission and source-normal sign+1 metadata. New typed output has the actual mapped receiver sign; no receiver double-sign. CHT now requires explicit domain-owned temperature_semantics and heat_flux_semantics and source-normal migration. Historical expectations require explicit owning-model disposition; no numerical or historical records were rewritten. FieldMapping roundtrip requirements are enforced for new interface execution.
InterfaceExchange sign_convention remains parseable metadata; only edge_interface_transfer plus the executed graph contract admits a new flux exchange. ExchangeKind adds INTEGRATED_FLUX outside frozen canonical exports. Neutral admission has no thermal units; only the CHT instance checks thermal dimensions. Legacy untyped intensive interface declarations now refuse too.
Run/graph replay, field/provider adapters, runtime mapping diagnostics, cached identities and certified dependency closure are transitively affected. Normal, orientation, support, plane, representation, measure and relation changes are material graph identity changes. No automatic aliases/kinds/sign migrations, pin regeneration or changed scientific thresholds.
Integration requires explicit consumer migration, old-reader/schema/frozen/layering checks and required CI on final source, then separately authorized OD-3. The 48-file baseline index is static; external/dynamic callers are not exhaustively discovered. E2 unstructured surface adapters remain unsupported and require further geometry review, not just the existence of A-4 code.
