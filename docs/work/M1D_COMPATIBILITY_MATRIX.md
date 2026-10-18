# M1D compatibility and affected-file matrix

Exact base73a18468d02e5817178e1bf10d53298d5cc14900. Architecture67cd3134 before source.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED, INTEGRATION HOLD. Static reference index, not execution.

| File | Exact lines | Impact |
| --- | --- | --- |
| `src/engcore/numerical/adaptive_transient.py` | 18, 22, 28, 53, 79, 98, 109, 118, 142, 173, 191, 205, 226, 243 | New numerical/domain implementation or tests |
| `src/engcore/domains/thermal_models/adaptive_conduction1d.py` | 21, 36, 42, 81, 107, 126, 136, 160, 217 | New numerical/domain implementation or tests |
| `src/engcore/domains/thermal_models/conduction1d_transient_fv.py` | 235, 251, 263, 347, 352, 410, 423 | Original constructor signature/model preserved; factored setup and new issued continuation path |
| `src/engcore/numerical/mesh_adaptation.py` | 75, 190, 339, 409, 435 | Unchanged parent contract, reused as-is |
| `src/engcore/numerical/vertex_state.py` | 176, 291, 330, 387, 407 | Unchanged parent contract, reused as-is |
| `src/engcore/execution/multiphysics/external.py` | 152, 191, 213 | Unchanged parent contract, reused as-is |
| `src/engcore/scenarios/timeline.py` | 183, 253 | Unchanged parent contract, reused as-is |
| `src/engcore/materials/properties.py` | 246, 304 | Unchanged parent contract, reused as-is |
| `tests/test_m1d_adaptive_transient.py` | 100, 116, 131, 141, 156, 168, 186, 199, 210, 219, 227, 244, 252, 264, 275, 286, 294, 300, 318, 337, 361 | New numerical/domain implementation or tests |

## Compatibility decisions

| Surface | Decision / migration |
| --- | --- |
| Core Freeze | No frozen export/schema/enum/material identity or certificate/pin edited. New /1 audit-only numerical/domain records refuse deserialization authority. |
| M1C API | Original TransientConduction1D.__init__ parameter shape preserved; sourced-initial admission remains original path. New continuation_permit/from_transfer methods are explicit derived admission, no legacy source relabelling. |
| M1C model | MODEL and REALIZATION scientific definitions/IDs unchanged. Implementation source/build hash intentionally changes; a live old provider scope cannot silently restore across source drift. |
| Context/provenance | Fresh target context binds new mesh/time and exact material resolution, with issued prior-session permit and transfer chain. No reconstructed initial measurement/source invented. UNKNOWN remains UNKNOWN. |
| Physical field | Target partition may split identical regions. Overlaps must preserve exact property/state identities, property IDs and area; contacts unchanged. Arbitrary physical material/source model updates are not adaptation. |
| Numerical direction | Generic coordinator imports no thermal module/physical-law vocabulary. Domain backend owns energy/storage/session reconstruction and qualified recovery. |
| Legacy adaptation | require_supported_adaptation transient refusal unchanged. Separate typed M1D admission applies only to this explicitly composed route. |
| Checkpoint | Existing CheckpointSeal unchanged. Same backend/session/support/build only, verified saved bytes and original nested issuance references. No cross-object/process/durable authority. Mesh-mutation restoration unsupported: poison. |
| Resources | Same builtin root dict/list resources and finite JSON-tree contents. Opaque resources refuse checkpoint before execution; external aliases/sessions/concurrency outside guarantee. Immutable orphan blobs may remain without issued handles after rollback. |
| Discovery | No additional model beyond M1C20. Pin19 untouched. Proposal records all intended population deltas and fatal import rules; actual discovery/import execution UNKNOWN. |
| Downstream | Prior M1A/B records and steady clients unchanged. New callers explicitly choose criterion/source/policy and target material declarations. External dynamic consumers not exhaustively enumerated. |

Exact twelve-file inventory in M1D_MERGE_PACKAGE.md. DV-133..136 and predecessor
recipes remain NOT RUN. Owner census compatibility and OD-3/integration decisions outstanding.
