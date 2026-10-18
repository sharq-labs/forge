# M1B vertex-centred dual-volume state adapter

2026-10-18. Preimplementation decision. Exact base M1A
7f8cb5dac01cd7a270ef72886b77c8cddf717d3b, published as Draft PR #162 against
A-4 #161. New branch codex/m1b-vertex-dual-state; future PR base codex/m1a-mesh-lineage.
main -> #159 -> #160 -> #161 -> #162 -> M1B. Checkpoint #158 independent.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED; no full M1 or execution claim.

## Placement and geometry decision

Add numerical/vertex_state.py, separate from legacy/M1A primal-cell state APIs.
Compose the M1A managed lineage/resource session, without editing its contracts.
For issued version vertices x[0..n], dual boundaries are endpoints plus exact
representable midpoints. There are n+1 dual cells, n primal cells and n+1 vertices.
Use Grid1D to represent the boundary partition for A-3 overlap; it grants no new
refinement ancestry. Dual identity binds exact primal version, frame, vertices and
boundaries. Same geometry at a later version never reactivates old handles.
Require finite positive dual widths; collapsed floating midpoints refuse.

StatePlacement is explicit VERTEX_INTENSIVE, DUAL_CELL_DENSITY or
DUAL_CELL_INTEGRATED, mapped to existing A-3 FieldSemantics kinds. Intensive state
is a vertex-associated primary value; conserved density/amount values belong to
that vertex's dual control volume. Shape alone never converts placement. No primal
records or unissued cloned dual records enter this adapter. Root initial inputs
explicitly declare their placement; a caller deliberately mislabelling equal-length
arrays cannot be detected from numbers alone.

## Conserved mapping and storage

Only immediate issued primal mesh changes authorize dual support transfer. Reuse
A-3 map_cells_1d on dual boundary grids. Independently recompute both coverages,
actual totals and residual in declared amount units. Tolerance uses the parent A-3
representation allowance, never tuned to outputs. No extrapolation/global rescaling.
Densities are amount per declared 1D length, not volume densities with an implicit
unit cross-section. Multidimensional geometry and variable-area quadrature are
unsupported; their already-integrated contribution can be supplied in explicit
per-dual-cell coefficients. Never infer area, density or heat capacity.

Direct vertex interpolation is refused: unresolved fine information is not supplied.
Reconstruction requires a new, current-target, positive finite per-dual-cell linear
storage coefficient, with exact intensive and integrated quantity meanings. Bounded
law A_i = C_i u_i, with C_i having amount/intensive units, is explicit and reversible
only under its declared zero-reference linear rule. Nonlinear, offset, state-dependent
laws and affine quantities refuse. Coefficients can differ at every vertex and are
never remapped as state or inherited implicitly. Convert conserved densities to
amounts using actual dual lengths before applying this law. Domain packs own physical
qualification and coefficient construction, including material interfaces and area.
Roundtrip preserves total amount; no pointwise accuracy or information recovery claim.

## Input origin and authority

Reuse KnowledgeSource, ScientificDataReference, BulkDataResolver and Uncertainty.
Require a KnowledgeSource plus immutable normalized-input bytes, with SHA-256 matching
its document_digest and the exact canonical normalized input material (mesh/support,
placement/meanings, units, values and declared context). This supports only an explicit
normalized-input artifact with an external locator/version/issuer; arbitrary raw
papers, URLs, free-text provenance or a context digest alone refuse. It binds supplied
source bytes, not their authenticity, physical applicability or experimental standing.
Synthetic fixtures explicitly label their source as synthetic; no real material values
or measured provenance are invented. More general extraction/admission is deferred.
Every initial state and coefficient requires this origin, including explicit UNKNOWN
uncertainty. Derived records retain exact input/state/law/transfer parent identities;
output uncertainty remains UNKNOWN. No new provenance/evidence/UQ authority system.

## Lifecycle and policy

Compose AdaptiveMesh1D for exact local issuance, active primal version, cache/history
binding and actual container clearing. Own same-object snapshot registry for dual
supports, fields, coefficients and receipts. Clear active fields/coefficients/support
on every mesh change, record invalidated IDs. Old source may be transferred only
through its issued immediate invalidation; prevent populated destination overwrite.
Failure to derive new dual support after a mesh change poisons this adapter, preventing
execution on mixed geometry. External caches, concurrency and durable import unsupported.

Require explicit Admission.OD6_VERTEX_DUAL_STATE_V1 at construction. This authorizes
only state placement and recorded adaptation under OD-6, never transient solving,
claims reachability or evidence. require_supported_adaptation remains unchanged and
continues refusing legacy transient calls. M1C needs its own explicit solver admission.

## Compatibility review before implementation

No frozen exports/schema/imports/identity material changed. No shared semantic enums
changed, and no frozen/certified artifact or capability maturity touched. New records
are numerical-only /1 audit records, not shared frozen contracts; deserialization cannot
grant local issuance. Existing primal records cannot masquerade as vertex states.
Consumers: Grid1D/MeshLineage1D and AdaptiveMesh1D, A-3 FieldSemantics/map_cells_1d,
existing stores/source/unit/UQ records. Existing steady thermal vertex FV is a future
consumer only, not modified or automatically migrated. A-4 interface execution untouched.
Tests and exact line impact matrix follow implementation. No tests/forge_check/OD-3 run.

Remaining M1: M1C transient vertex FV/backward Euler with explicit boundaries,
sourced state/materials and numerical studies, then adaptive transient orchestration.
Owner direction settles placement. Future physical input/source qualification,
nonlinear storage, variable-area geometry and execution authorization remain decisions.
