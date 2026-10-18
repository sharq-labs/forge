# M1C compatibility and affected-file matrix

Exact base M1B9b092d563507b0de3563c4209d42d6fc0772ea0a. Preimplementation
decision ef11c1da. IMPLEMENTED / UNVERIFIED / UNCERTIFIED; tests NOT RUN.

## Exact source, test and dependency references

| File | Exact lines | Impact |
| --- | --- | --- |
| `src/engcore/domains/thermal_models/conduction1d_transient_fv.py` | 40, 53, 66, 71, 81, 133, 150, 158, 164, 169, 203, 234, 305, 324, 336, 355, 364 | New bounded source or synthetic adversarial/analytical tests |
| `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` | 97, 156, 200, 207, 326 | Unchanged steady model/realization/outputs; reuse explicit boundary records only |
| `src/engcore/numerical/vertex_state.py` | 30, 166, 176, 230, 285, 291, 330 | Existing unchanged contract/dependency |
| `src/engcore/numerical/core.py` | 99, 164, 254, 271, 366, 429, 491, 666 | Existing unchanged contract/dependency |
| `src/engcore/numerical/providers.py` | 81 | Unchanged; its bounded dense condition diagnostics motivate separate sparse-only provider |
| `src/engcore/materials/properties.py` | 206, 215, 246, 304 | Existing unchanged contract/dependency |
| `src/engcore/materials/identity.py` | 159, 191 | Existing unchanged contract/dependency |
| `src/engcore/scientific/knowledge/source.py` | 15, 26 | Existing unchanged contract/dependency |
| `src/engcore/scenarios/timeline.py` | 102, 136, 146, 183, 253 | Existing unchanged contract/dependency |
| `src/engcore/scientific/models/definition.py` | 1422, 2087 | Existing unchanged contract/dependency |
| `src/engcore/scientific/realizations/definition.py` | 240 | Existing unchanged contract/dependency |
| `tests/test_m1c_transient_fv.py` | 91, 102, 113, 124, 134, 145, 155, 167, 181, 200, 205, 211, 218, 225, 239, 248, 259, 276, 288, 299, 310, 320, 336, 343, 358, 372, 386, 400 | New bounded source or synthetic adversarial/analytical tests |

## Compatibility decisions

| Surface | Disposition |
| --- | --- |
| Source inventory | One new thermal domain module; no prior production source modified. New tests/docs only otherwise. Nine-file inventory in merge package. |
| Scientific identity | New transient model/realization0.1.0, distinct from steady. No old model/realization IDs or serialization rewritten. Model applicability UNKNOWN; UNVALIDATED. |
| Model census | tests/test_core_guards.py:163 walker discovers new model; :199 pins19 and :534 checks exact population. Static expected20 creates integration hold M1C-C1. Guard untouched; owner-approved count/certification review required. |
| Core API | No frozen export, signature, enum, current/legacy schema or digest material changed. Existing classes used as defined. Core compatibility execution deferred. |
| Numerical provider | Existing NumericalProvider/Problem/Method/ExecutionRecord vocabulary; new sparse-only SuperLU backend. No dense conditioning conversion or alternate fallback. Existing providers unchanged. |
| Build identity | Provider binds module source bytes, SuperLU binary bytes and NumPy/SciPy versions. Missing readable build artifacts refuses; packaging compatibility unexecuted. |
| Materials/applicability | Actual MaterialPropertySet resolution and source payload hashes; known phase-constant scalar properties only. ASSUMED allowed only explicit synthetic admission. Neither source labels nor resolved inputs establish model applicability. |
| M1B | Exact support/version/intensive/integrated meanings and source artifacts reused; original storage ID and actual bytes bound. New thermal session is separate from generic state-only admission. |
| Boundary contracts | Old ConductionBoundary shape/sign meaning unchanged; M1C additionally refuses affine quantities and independently admits transient both-Neumann. Legacy steady two-Neumann refusal unchanged. |
| New audit records | ThermalStep /1 export-only; local issuance required, inherited from_dict refuses restored authority. Step identity includes context/source/window/state/provider/outcome/flux/residual. |
| Downstream | Steady clients and prior stack unaffected; no domain registration, claims/SRIA/MCP production path or mature capability declaration. Future M1D consumes this fixed-mesh session only via new bounded design. |
| Certification | No certified/frozen pin edited. Known model-census integration impact remains explicit; no certification or gate closure. OD-3 separately authorized. |

Reference consumers were identified by static source review; dynamic external users are
not exhaustively known. Deferred DV-129..132 covers numerical/design, materials/parents,
legacy steady and Core/census/closure checks. No actual integration result inferred.
