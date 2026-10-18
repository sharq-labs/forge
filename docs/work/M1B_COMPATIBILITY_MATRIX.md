# M1B Core compatibility and affected-file matrix

Preimplementation review: M1B_ARCHITECTURE_DECISION.md commit4fb78436 before source.
Exact parent7f8cb5da. Non-Core opt-in addition; no existing production consumer migrated.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED. Static references are not executed evidence.

## Existing dependencies and downstream consumers

| File | Exact lines | Impact / disposition |
| --- | --- | --- |
| `src/engcore/numerical/mesh_adaptation.py` | 75, 86, 190, 339 | Unchanged Grid1D identity/legacy refusal/issued ancestry; no dual refinement ancestry inferred |
| `src/engcore/numerical/interval_transfer.py` | 113, 131, 140, 175, 187, 195, 205, 210 | Unchanged primal-cell adapter composed for lineage/cache history; its records cannot be read as dual state |
| `src/engcore/numerical/field_mapping.py` | 24 | Unchanged dependency; reused existing contract |
| `src/engcore/scientific/fields/semantics.py` | 15, 64, 107 | Unchanged dependency; reused existing contract |
| `src/engcore/scientific/knowledge/source.py` | 15, 26 | Unchanged dependency; reused existing contract |
| `src/engcore/data/resolver.py` | 33, 61, 96, 110 | Unchanged dependency; reused existing contract |
| `src/engcore/data/store.py` | 71, 169 | Unchanged dependency; reused existing contract |
| `src/engcore/scientific/results/uncertainty.py` | 30, 36, 53, 171 | Unchanged dependency; reused existing contract |
| `src/engcore/domains/thermal_models/conduction1d_nonuniform.py` | 186, 191, 196, 200, 207, 234, 276, 291, 304, 311, 326, 360, 371 | Unchanged steady vertex FV; future M1C consumer only, no automatic migration |
| `src/engcore/scientific/units/quantity.py` | 595, 619, 838 | Unchanged dependency; reused existing contract |

## New implementation and tests

| File | Exact symbols / lines | Impact |
| --- | --- | --- |
| `src/engcore/numerical/vertex_state.py` | 26, 30, 42, 56, 66, 91, 117, 135, 166, 176, 189, 242, 254, 261, 291, 330, 387, 407 | New opt-in implementation or synthetic adversarial fixtures, NOT RUN |
| `tests/test_m1b_vertex_dual_state.py` | 69, 79, 84, 95, 115, 123, 131, 148, 164, 172, 183, 188, 193, 203, 213, 228, 236, 259, 273, 287, 307, 316, 322, 334, 347, 365, 374, 388, 398, 417, 432 | New opt-in implementation or synthetic adversarial fixtures, NOT RUN |

## Compatibility decisions

| Surface | Decision / migration |
| --- | --- |
| API/import | New numerical.vertex_state module only. No canonical export or existing signature changed. Explicit admission enum object required; raw legacy/JSON admission cannot silently enable a route. |
| Core semantics | Existing QuantitySemantics, ConservedQuantity and FieldSemantics are reused unchanged; placement is a numerical support association, not a parallel physical-meaning vocabulary. No frozen enum extended. |
| Serialization | New /1 numerical audit records; from_dict refuses local authority import. normalized-input /1 is an exact artifact format, not a legacy reader or raw-source extractor. |
| Identity | New support material binds primal VERSION/frame plus exact primal and dual geometry. State identity adds typed placement/meaning/data/UQ/context/source/parents. Law binds exact primary/amount/optional density semantics and current support. Existing historical IDs unchanged. |
| Source provenance | Reuse KnowledgeSource plus verified normalized immutable bytes. Hash/source class is not physical standing. Initial state and coefficients missing bytes/ref/context refuse. No new Evidence or provenance system. |
| Numerical meaning | One value per vertex/dual cell. Primal-cell handles refuse. Direct vertex interpolation refuses; supplied target storage is required. Density measure is 1D length, never assumed unit-area volume. |
| Lifecycle | Compose existing managed cache/history clearing; own dual support/fields/storage invalidation. Complete derived ancestry required; unsupported partial transition makes adapter unusable. External caches/concurrency unsupported. |
| Policy | Legacy require_supported_adaptation unchanged, including transient refusal. New explicit OD6_VERTEX_DUAL_STATE_V1 permits only state operations; no solver/claims reachability. |
| Certification | No frozen manifests, certified source, API snapshots, maturity ledger or gate pins edited; no recertification or promotion claim. Required compatibility/closure recipes deferred. |
| Downstream | Existing source APIs retain behavior. Future M1C must construct correctly integrated coefficients on each support; no remap of old material law or implicit nodal-to-cell conversion. Dynamic external consumers not exhaustively enumerated. |

Exact nine-file changed inventory is in M1B_MERGE_PACKAGE.md. Deferred execution
DV-125..128 includes ancestor, legacy policy, A-3/A-4, Core/import and closure checks.
