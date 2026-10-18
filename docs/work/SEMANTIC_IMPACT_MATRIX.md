# Semantic impact matrix (Phase B, before shared implementation)

Base: `0284ae161ad957d51674ee481e47cfd43d10c5f0`. Direct consumers below
were enumerated by static `git grep -n -E` of the eight affected contract names
across tracked src/providers/flagships. Exact baseline line references are retained.
All runtime consumers also transitively consume graph serialization/admission. Dynamic
external callers cannot be exhaustively inventoried; public migration notes are required.
No tests or imports ran to produce this inventory.

| File | Exact baseline lines | Impact / disposition |
| --- | --- | --- |
| `flagships/forge_flagships/battery_cooling.py` | 61, 64, 222, 223, 226 | Flagship producer/bundle identity and provenance; no bundle regeneration or level promotion |
| `flagships/forge_flagships/chem_thermal.py` | 105, 107, 108 | Flagship producer/bundle identity and provenance; no bundle regeneration or level promotion |
| `providers/fenicsx/tests/test_coupling_fenicsx.py` | 32, 35, 138, 139, 140, 143, 144, 145, 314 | Provider test/adapter contracts; explicit alias migration and provider re-execution deferred |
| `providers/fenicsx/tests/test_pde_fenicsx.py` | 345, 355 | Provider test/adapter contracts; explicit alias migration and provider re-execution deferred |
| `providers/pybamm/tests/test_pybamm_multiphysics.py` | 26, 28, 96, 97, 99 | Provider test/adapter contracts; explicit alias migration and provider re-execution deferred |
| `providers/pybamm/tests/test_system_runtime_battery.py` | 33, 36, 101, 102, 104 | Provider test/adapter contracts; explicit alias migration and provider re-execution deferred |
| `src/engcore/compositionpacks/authority.py` | 159 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/compositionpacks/blueprint.py` | 18, 19, 58, 61, 81, 83, 208, 220 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/compositionpacks/builtin_electrothermal_feedback.py` | 44, 46, 50, 331, 335, 339, 343, 347, 351, 358, 362, 366, 370, 374, 381, 385, 389, 443, 449, 455, 459 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/compositionpacks/builtin_thermal_resistance.py` | 33, 36, 299, 306, 313, 320, 327, 334, 344, 351, 358, 365, 372, 412 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/compositionpacks/participant.py` | 17, 93, 150, 154, 249 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/coupling/adapters.py` | 16, 32, 33, 44, 48 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/domains/electrical/dc/models.py` | 64, 1031, 1048 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/execution/multiphysics/runtime.py` | 17, 1210, 1211, 1212, 1240, 1252 | Transfer/runtime admission and conservation; typed scalar path; field path deferred |
| `src/engcore/execution/multiphysics/transfer.py` | 21, 165, 276, 362 | Transfer/runtime admission and conservation; typed scalar path; field path deferred |
| `src/engcore/planning/blueprint.py` | 16, 17, 22, 71, 93, 95, 159, 176, 180, 193, 194, 273, 277 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/scientific/__init__.py` | 122, 124, 253, 255 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/composition/__init__.py` | 8, 34, 52, 57, 70, 73 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/composition/conversion.py` | 8, 25, 31, 88, 272, 510 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/composition/dependency.py` | 118, 133, 140, 163, 217, 238, 249, 261, 444, 474, 507, 525 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/composition/transfer.py` | 3, 63, 104, 132, 134, 430 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/conservation.py` | 32, 59, 69, 80, 81, 96, 97, 134, 217, 221, 222, 229 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/equations/__init__.py` | 110, 111 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/equations/conservation.py` | 6, 16, 32, 34, 35, 50, 81, 83, 84, 86, 98 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/fields/transfer.py` | 3, 194 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/multiphysics/__init__.py` | 14, 15, 22, 66, 168, 170, 172, 199 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/multiphysics/conservation.py` | 33, 78, 92, 96, 108, 160, 165 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/multiphysics/graph.py` | 17, 18, 28, 47, 53, 70, 71, 91, 101, 112, 115, 132, 133, 148, 149, 192, 228, 231, 271, 301, 374, 508, 517 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/multiphysics/participant.py` | 11, 80, 133, 193, 199, 204, 281 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/multiphysics/ports.py` | 68, 173 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/multiphysics/value.py` | 15, 45, 77 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/scientific/results/uncertainty_mapping.py` | 16, 74, 109, 111 | Core-package record/admission or serialization; frozen shape preserved where applicable |
| `src/engcore/system_runtime/assess.py` | 6, 21, 140, 148, 153 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/systems/electrothermal/coupled.py` | 52, 120, 121, 257, 332, 336, 338, 368, 438, 445, 561, 662, 675, 680, 737, 773, 848, 886, 887, 1310, 1330, 1348, 1360, 1375, 1389, 1407, 1574, 2055, 2313 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/systems/electrothermal/resistor_body.py` | 54, 312, 330, 345, 358, 373, 401, 442 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/systems/electrothermal/runtime_adapter.py` | 19, 107, 114, 194, 196, 214 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/systems/products/drone_coupled.py` | 45, 46, 51, 99, 101, 131, 132, 135, 280, 282, 283, 284, 285, 287 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/systems/topology.py` | 16, 42, 49, 50, 66 | Review semantics, identities and migration; no blanket alias mapping |
| `src/engcore/uq/cross_domain.py` | 25 | Review semantics, identities and migration; no blanket alias mapping |

Frozen exports and schema readers must be checked separately through API/serialization
contracts. Composition/planning blueprints, factories, SystemExecutor/MultiphysicsAuthority,
claims/replay and stored flagship bundles are transitive consumers even when the class
name does not occur in their source. Final changed-line references and migration failures
remain subject to deferred execution. A listed consumer is not assumed migrated.
