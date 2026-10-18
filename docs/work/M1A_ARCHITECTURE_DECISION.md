# M1A: lineage-bound 1D adaptation and state transfer

2026-10-18, preimplementation architecture/compatibility decision. Branch
codex/m1a-mesh-lineage, exact base1f43c59eab717aa7cbfea672b948accb37f3cc50.
Dependency main -> semantic PR#159 -> A-3#160 -> A-4#161 -> M1A.
Checkpoint#158 independent. IMPLEMENTED / UNVERIFIED / UNCERTIFIED when supplied.
Read the complete M1/CDAR contract in ENGINEERING_FOUNDATIONS_PROGRAM.md. This
slice does not implement the transient conduction solver or decide the M1 gate.

## Decision

Preserve Grid1D geometry digest, serialization and existing refine/adapt APIs.
Add a separate explicit MeshLineage1D issuer in numerical/mesh_adaptation.py.
Root registration declares a root context, not inferred ancestry. Stable cell ids
bind exact endpoints, root and parent. Recorded bisections contain exact parent and
two child intervals, including representable midpoint. Mesh version ids bind the
previous version, operation, bisections, active cells and geometry digest. Returning
to identical geometry creates a new version: stale bindings never become current.

Coarsen only issued compatible bisections whose exact children remain active adjacent
leaves. Restore that recorded parent object/interval. Refuse duplicate/conflicting
merges, nested non-leaves, unissued/missing/tampered ancestry and ratio/minimum failures.
Use explicit policy parameters; no automatic unrecorded gradation or nearest-match
ancestry. No arbitrary adjacent merge or ancestry reconstruction from coordinates.

Records have deterministic exact /1 audit schemas and material digests, but hashes
alone do not prove issuance. Admission requires the issuer's same-object registry
and a captured canonical snapshot, rechecked for nested tampering. Serialized exports
are audit data only; no deserialization grants lineage authority or cross-process
recovery. Durable trusted lineage import/replay is a separately designed capability.
This preserves the distinction also used by strict checkpoint authority; no seal
is weakened and no new scientific evidence/provenance authority is invented.

Add AdaptiveMesh1D in numerical/interval_transfer.py. It owns the active lineage,
registered content-addressed states, and managed solver-cache/coupling-history bindings.
On a mesh change, clear actual registered built-in dict/list cache containers and
invalidate all active field/resource handles. External out-of-band caches/solver
state and concurrent access are unsupported; adapters must use these bindings.
An exported change receipt records exact invalidated ids. No metadata-only invalidation.

State binds mesh VERSION, A-3 FieldSemantics, ratio-scale unit, existing
ScientificDataReference, existing Uncertainty and explicit producer/context digest.
Initial caller values/context remain declarations, not authenticated measurements or
solver provenance. Issued records bind bytes/context for subsequent execution; bytes
are rechecked by BulkDataResolver, never repr/pickle or unverified stored digests.
Superseded or unissued fields refuse. A just-invalidated source may only be read by
transfer through its exact issued change receipt to the current destination.

Reuse A-3 map_cells_1d for mapping; no parallel kinds or numerical remap formula.
Conserved density and integrated amounts stay distinct. Intensive transfer requires
explicit piecewise-constant overlap rule, and never claims a conserved quantity.
M1 refuses affine units for every kind, even where A-3 allows intensive conversion.
No extrapolation, coverage loss or global rescaling. Recompute both coverage directions
and actual source/destination amount totals before admitting the transferred state;
do not trust a result's self-reported zero residual. Representation allowance reuses
the existing coverage roundoff. Record actual units, ids, totals/residuals and UNKNOWN
transfer uncertainty. Conservation of constructed transfer is not physics validation.

## Compatibility review and remaining M1 scope

Numerical/non-Core additions only; canonical frozen exports, Grid1D fields/digest,
old serialization/imports, shared A-3/A-4 semantics, certification pins and maturity
ledger untouched. Old Grid1D/refine results do not magically acquire ancestry. New
audit records missing issuance cannot enter execution, even if their hashes match.
Exact consumer/implementation references go in M1A_COMPATIBILITY_MATRIX.md.

Managed cache invalidation is bounded to registered containers/handles; no claim of
invalidating arbitrary external solver sessions. No transient solver, physical clock,
adaptive scheduling loop, trusted durable restore, independent local-error bound or
experimental provenance is added. Vertex-centred FV/backward Euler order1 conduction,
sourced initial/material/boundary records, adaptive transient orchestration and executed
refinement/conservation studies remain M1 follow-ons. DV0 does not block build work.
Tests/assurance/OD-3 require separate authorization; no gate closure from this code.
