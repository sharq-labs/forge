# Semantic impact matrix (Phase B design plus expanded consumer inventory)

Base: `0284ae161ad957d51674ee481e47cfd43d10c5f0`. Phase A/B initial inventory
contained 39 direct contract consumers before implementation. Expanded static reference
closure below also covers graph/runtime/authority and helper consumers, including tests.
Exact baseline references come from git grep over tracked src/providers/flagships/tests.
All imports/instances through these shared contracts are affected by admission and nested
serialization. No tests or imports were executed to establish this inventory. External
callers and runtime-generated factories cannot be exhaustively discovered statically.

| File | Exact baseline lines | Impact / disposition |
| --- | --- | --- |
| `flagships/forge_flagships/battery_cooling.py` | 43, 46, 61, 64, 72, 218, 220, 222, 223, 225, 226, 244, 274, 357, 469, 525 | Producer/bundle identity; no regeneration or level promotion; alias refusal may block former run |
| `flagships/forge_flagships/chem_thermal.py` | 105, 107, 108 | Producer/bundle identity; no regeneration or level promotion; alias refusal may block former run |
| `flagships/tests/test_flagship_portfolio.py` | 40 | Producer/bundle identity; no regeneration or level promotion; alias refusal may block former run |
| `providers/fenicsx/tests/test_coupling_fenicsx.py` | 1, 21, 25, 32, 35, 37, 99, 102, 127, 138, 139, 140, 143, 144, 145, 146, 163, 307, 313, 314, 320, 380, 417 | Provider boundary fixture/adapter; no automatic alias migration; real-provider re-execution deferred |
| `providers/fenicsx/tests/test_multiscale_fenicsx.py` | 4 | Provider boundary fixture/adapter; no automatic alias migration; real-provider re-execution deferred |
| `providers/fenicsx/tests/test_pde_fenicsx.py` | 342, 344, 345, 355, 383 | Provider boundary fixture/adapter; no automatic alias migration; real-provider re-execution deferred |
| `providers/pybamm/tests/test_pybamm_checkpoint_identity.py` | 25, 45 | Provider boundary fixture/adapter; no automatic alias migration; real-provider re-execution deferred |
| `providers/pybamm/tests/test_pybamm_coupling_options.py` | 13, 29 | Provider boundary fixture/adapter; no automatic alias migration; real-provider re-execution deferred |
| `providers/pybamm/tests/test_pybamm_multiphysics.py` | 1, 17, 19, 26, 28, 72, 74, 96, 97, 99, 103 | Provider boundary fixture/adapter; no automatic alias migration; real-provider re-execution deferred |
| `providers/pybamm/tests/test_system_runtime_battery.py` | 4, 25, 28, 33, 36, 45, 97, 99, 101, 102, 104, 172, 185 | Provider boundary fixture/adapter; no automatic alias migration; real-provider re-execution deferred |
| `src/engcore/assembly/multiphysics.py` | 26, 627, 867 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/compositionpacks/authority.py` | 159 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/compositionpacks/blueprint.py` | 18, 19, 25, 58, 61, 81, 83, 152, 160, 208, 220 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/compositionpacks/builtin_electrothermal_feedback.py` | 44, 46, 50, 331, 335, 339, 343, 347, 351, 358, 362, 366, 370, 374, 381, 385, 389, 443, 449, 455, 459 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/compositionpacks/builtin_thermal_resistance.py` | 33, 36, 299, 306, 313, 320, 327, 334, 344, 351, 358, 365, 372, 412 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/compositionpacks/participant.py` | 17, 93, 150, 154, 249 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/coupling/__init__.py` | 3, 15, 24, 25, 28, 29 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/coupling/adapters.py` | 16, 32, 33, 44, 48 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/domainpacks/multiphysics.py` | 19, 28, 43, 48 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/domains/electrical/dc/models.py` | 64, 1031, 1048 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/execution/multiphysics/__init__.py` | 56, 62, 95, 108 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/admission.py` | 1, 19, 156, 160, 161 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/authority.py` | 5, 89, 95, 99, 120, 121 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/conjugate_interface.py` | 44, 115, 232 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/external.py` | 13 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/factory.py` | 20, 210, 274, 276, 277, 307, 346, 348, 349 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/interface_exchange.py` | 37, 92, 127 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/runtime.py` | 17, 32, 84, 132, 136, 144, 180, 253, 318, 385, 388, 449, 1210, 1211, 1212, 1240, 1252 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/splitting.py` | 39, 82, 141, 183, 184 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/steady.py` | 5 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/subcycling.py` | 36, 71 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/execution/multiphysics/transfer.py` | 21, 25, 79, 82, 165, 276, 361, 362 | Scalar transfer/runtime conservation; typed fields refused pending A-3; no evidence promotion |
| `src/engcore/multiscale/fast.py` | 4 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/multiscale/runtime.py` | 23 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/numerical/health.py` | 8 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/planning/__init__.py` | 14, 101 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/planning/blueprint.py` | 16, 17, 21, 22, 71, 93, 95, 159, 171, 176, 180, 193, 194, 228, 235, 266, 273, 277, 283, 284, 286, 287, 292, 299, 319 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/planning/records.py` | 20, 506, 533, 534, 817 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/planning/selection.py` | 16, 496, 506, 554 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/scenarios/lifecycle.py` | 5 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/scientific/__init__.py` | 122, 124, 253, 255 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/composition/__init__.py` | 8, 34, 52, 57, 70, 73 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/composition/conversion.py` | 8, 25, 31, 88, 272, 510 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/composition/dependency.py` | 118, 133, 140, 163, 217, 238, 249, 261, 444, 474, 507, 525 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/composition/transfer.py` | 3, 63, 104, 132, 134, 430 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/conservation.py` | 32, 59, 69, 80, 81, 96, 97, 134, 217, 221, 222, 229 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/equations/__init__.py` | 110, 111 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/equations/conservation.py` | 6, 16, 32, 34, 35, 50, 81, 83, 84, 86, 98 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/fields/transfer.py` | 3, 194 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/__init__.py` | 14, 15, 22, 23, 66, 168, 170, 172, 198, 199 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/composition.py` | 1 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/conservation.py` | 33, 78, 92, 96, 108, 160, 165 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/graph.py` | 17, 18, 28, 47, 53, 70, 71, 91, 101, 109, 112, 115, 132, 133, 148, 149, 192, 224, 228, 231, 271, 301, 374, 503, 508, 517 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/interface.py` | 1, 3, 18, 164, 165, 166 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/participant.py` | 11, 80, 133, 193, 199, 204, 281 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/plan.py` | 1, 24, 591, 605, 631, 673 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/ports.py` | 68, 173 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/report.py` | 16, 544, 572, 574, 1104 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/multiphysics/value.py` | 15, 45, 77 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/scientific/results/uncertainty_mapping.py` | 16, 74, 109, 111 | Record/admission or serialization; frozen exports untouched; typed child /2 and material semantics |
| `src/engcore/system_runtime/__init__.py` | 17, 38 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/system_runtime/assess.py` | 6, 21, 140, 148, 153 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/system_runtime/authorities.py` | 8, 98, 99, 102 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/systems/electrothermal/coupled.py` | 52, 120, 121, 257, 332, 336, 338, 368, 438, 445, 561, 662, 675, 680, 737, 773, 848, 886, 887, 1310, 1330, 1348, 1360, 1375, 1389, 1407, 1574, 2055, 2313 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/systems/electrothermal/resistor_body.py` | 54, 312, 330, 345, 358, 373, 401, 442 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/systems/electrothermal/runtime_adapter.py` | 7, 19, 99, 107, 113, 114, 145, 194, 196, 214, 225, 254, 370, 448 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/systems/products/drone_coupled.py` | 4, 41, 45, 46, 51, 99, 101, 131, 132, 135, 192, 280, 282, 283, 284, 285, 287, 298, 300, 344 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/systems/topology.py` | 3, 16, 42, 49, 50, 66, 254, 255, 256, 260, 263, 270, 276, 278, 280, 305, 349, 374 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `src/engcore/uq/cross_domain.py` | 25 | Review exact-name legacy compatibility; migrate ambiguous aliases explicitly; tests deferred |
| `tests/api/frozen_api_snapshot.json` | 6211, 8752 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/api/full_api_snapshot.json` | 6514, 9055 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/api/v2_frozen_api_snapshot.json` | 9532, 12073 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/api/v2_full_api_snapshot.json` | 9836, 12377 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/architecture/test_cross_domain_fixtures.py` | 4, 35, 40, 41, 44, 55, 100, 131, 132, 133, 165, 166, 192, 206, 207, 208, 245, 251, 252, 261, 262, 301, 306, 307, 309, 310, 311, 345 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/claims/test_coupling_numerical_condition.py` | 20, 24, 25, 43, 60, 61, 65, 90 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/execution/orchestration/test_phase2_checkpoint_recovery.py` | 179, 183 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/foundations/test_authority_integrity.py` | 408, 410, 411 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/multiscale_reference.py` | 16, 40, 45, 61, 63, 283, 303, 304, 305, 308, 309, 405, 406, 413 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/mutation_population_v4.py` | 5052, 5063, 5068, 5074, 5199 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_big9_review_runtime_fixes.py` | 20, 27, 28, 41, 74, 75, 82, 125, 129, 162, 170, 201, 208 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_conservation.py` | 7, 14, 17, 20, 21, 35, 37, 38, 48, 50, 51, 63, 65, 66, 69, 71, 72, 84, 86, 87, 94, 96, 97, 104, 106, 107, 114, 123, 125, 126, 131 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_core_api_serialization.py` | 32 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_core_guards.py` | 3137, 3138, 3162, 3801, 3802, 3812, 3818, 3823, 3832, 3838, 3851, 3854, 3871, 3892, 3903, 3909, 3918, 3926, 3939, 3953, 3961, 4042, 4044, 4055, 4057, 4102, 4116, 4148, 4152, 4202, 4205, 5119, 5120, 5182, 5188 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_core_scientific_audit_batch47.py` | 19, 20, 28, 49, 224, 235 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_core_scientific_audit_batch48.py` | 21, 22, 41, 69, 75, 80, 187, 256 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_core_scientific_audit_batch49.py` | 20, 66 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_cross_domain_uq.py` | 7, 8, 30, 105, 113 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_electrothermal_vertical.py` | 28, 63, 65, 709, 739, 821, 931, 972, 1025, 1065, 1132, 1288, 1291, 1414, 1424, 1431, 1725, 1862 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_external_participant_checkpoints.py` | 19, 24, 25, 67, 68, 170, 171, 177 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_field_ir_ceiling.py` | 30, 189 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_lifecycle_engine.py` | 20, 32, 33, 76, 114 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_materials_engine.py` | 19, 42, 236, 269 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_min_foundation_electrothermal.py` | 31, 118, 120, 355, 387, 475, 499, 637, 648, 668, 712, 794, 797, 819, 832, 852, 935 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multidomain_science_hardening.py` | 37, 318 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_concurrent_jacobi.py` | 18, 23, 103, 129, 130, 135 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_conservation_history.py` | 3, 18, 22, 23, 25, 37, 66, 67, 68, 69, 71, 72, 73, 77, 210, 233, 285, 288, 300, 305, 307, 316, 321, 323 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_event_aligned_outcome.py` | 15, 19, 20, 35, 61, 62, 68 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_fan_in_units.py` | 22, 27, 28, 42, 43, 44, 45, 46, 69, 105 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_iqn_ils.py` | 16, 22, 23, 173, 194, 195, 201 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_numerical_error_accounting.py` | 14, 21, 22, 38, 56, 57, 61, 146, 150 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_splitting_estimate.py` | 16, 24, 25, 49, 53, 55, 56, 57, 76, 86 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiphysics_window_control.py` | 20, 25, 26, 49, 99, 103, 158, 228, 229, 235 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_multiscale_runtime.py` | 3, 23, 337 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase1_coupling_convergence_coverage.py` | 26, 33, 34, 57, 97, 98, 99, 174, 193, 207, 230 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase1_exact_time_windows.py` | 19, 24, 25, 36, 46 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase1_numerical_error_semantics.py` | 23, 31, 32, 100, 110 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase1_system_runtime_outcomes.py` | 3, 20, 26, 27, 32, 43, 65, 66, 77, 85 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase2_coupling_authority.py` | 3, 29, 40, 41, 192, 208, 209, 217, 258 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase2_external_coupling.py` | 9, 23, 35, 36, 40, 51, 52, 97, 98, 100, 103, 106, 125, 175, 178 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase2_review_regressions.py` | 123, 128 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase35_ws2_electrothermal_migration.py` | 5 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase35_ws3_conjugate_interface.py` | 22, 23, 34, 46, 48, 50 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase3_br14_iqn_imvj.py` | 23, 29, 30, 200, 223, 224, 231 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_phase3_br15_window_error_control.py` | 26, 33, 34, 44, 92, 97, 190 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_provider_participant_checkpoints.py` | 37, 57 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_stateful_multiphysics_runtime.py` | 10, 16, 30, 31, 77, 83, 183, 203, 204 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_system_runtime_big13_additions.py` | 5, 19, 64, 85, 97, 98, 99 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_system_runtime_executor.py` | 266, 270 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_system_runtime_external_providers.py` | 5, 18, 21, 22, 26, 60, 61, 69, 70, 76, 85 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_system_runtime_review_fixes.py` | 17, 35, 39, 40, 79 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_time_engine.py` | 16, 29, 505, 506, 526 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |
| `tests/test_world_runtime_sprint1.py` | 31, 62, 68, 69, 211, 212, 213, 222, 223, 229, 230, 234, 357, 505, 813 | Regression/fixture migration inventory; not executed; only explicit requirement tests changed |

## Migration categories and acceptance

- Exact-name legacy temperature/state connections remain on the unchanged untyped writer.
- Legacy different-name links need explicit endpoint/form agreement or typed ports plus
  transport. Cross-meaning physical conversion belongs to a qualified model participant;
  unexamined aliases are not a Core synonym catalogue.
- Native electrothermal adapter, drone coupled screening, compositionpack factories,
  multiscale reference, provider coupling tests and flagship producers must each disposition
  their aliases before claiming prior application compatibility. None is assumed migrated.
- Planning blueprints, SystemExecutor/MultiphysicsAuthority, claims/replay and stored bundles
  transitively consume graph admission/identity. Existing assurance is not automatically
  reissued for a semantically changed graph.
- Frozen QuantityDependency/EnergyConversion/LossPath and their readers are unchanged.
  General standalone legacy balances remain arithmetic-only until explicitly typed.
- The A-1 gap pin becomes a refusal regression; A-2/A-13 legacy pins remain documented
  limitations alongside positive typed-path tests. No semantic gap is CLOSED.
- New standard-libraries-only semantic code has no Domain Pack/provider/MCP dependencies.
  Frozen shape, import, identity and certified dependency checks remain deferred.
