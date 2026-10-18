# A-3: declared field-kind mapping decision

2026-10-18. IMPLEMENTED / UNVERIFIED / UNCERTIFIED when code is supplied.
Design recorded before source changes. Branch codex/declared-field-kind-mapping
depends on semantic PR #159, exact base 98da0c024bd59bd0b18844941eafad3f1d24d428.
Checkpoint PR #158 is independent. No gap CLOSED; A-4 remains separate.

## Decision

Reuse QuantitySemantics/ConservedQuantity and existing FieldDefinition/FieldRecord,
MappingDiagnostics, content-addressed stores and geometry qualification/refusals.
Add a neutral FieldSemantics declaration: cell-average density, cell-integrated
amount, intensive, normal flux or interface quantity. Domain Packs own identifiers
and physical laws. Conserved density declares measure unit and the resulting amount;
integrated amount declares that same measure and quantity. No kind inferred from units.

FieldDefinition gains an optional trailing semantic declaration. Legacy /1 writer
shape stays unchanged; typed definitions emit /2, exact readers reject downgraded
or missing extensions. Existing imports and frozen exports/shapes stay unchanged.
Nested definitions already enter support-bound FieldRecords and graph fingerprints.
No frozen/certification manifest edits. Core Freeze compatibility, layering, reader
and certified dependency checks are deferred, final-tree OD-3 separately authorized.

Conservative mapping without declared kind now refuses, including legacy calls.
Explicit migration must derive kind from the owning model, never relabel historical
records automatically. Legacy identity/interpolation remains available without a new
conservation claim. Typed intensive remap uses declared overlap averaging with no
conservation diagnostic; typed flux/interface execution refuses pending A-4.

Flux/interface records require support identity/fingerprint, common coordinate frame,
orientation and explicit unit normal convention. These are declarations only: no
normal projection, sign flip, equal-and-opposite law or interface physics executes.

Use one density/integrated/intensive kernel for existing qualified 2D/3D intersections
and a narrow 1D Grid1D adapter. The adapter uses existing grid content digests,
explicit common frame, strictly increasing finite nodes and canonical meter geometry.
It does not add transient adaptation/solver policy, mesh lineage or automatic cache
repair. Both coverage directions must hold within the existing representation allowance.

Integrated: A'_j = sum_i (A_i/V_i) overlap_ij. Density/intensive overlap average:
q'_j = sum_i q_i overlap_ij / V'_j. Integrated roundtrip must use the integrated
reverse operator. L1 scaling handles signed zero totals. Conservation totals use
the declared conserved amount and units; intensive interpolation has no conserved total.
No integral diagnostic bounds local error or grants physical validity, UQ or certification.

Typed field graph edges require matching field declarations and port quantity semantics,
same frame and scalar algebra. They use mapping declarations, not scalar loss fractions.
Cross-kind density-to-integrated transformations, vector/tensor remap, typed reduction,
uncovered regions, affine conserved units and unsupported interface execution refuse.

## Numerical probes and compatibility obligations

Preregistered example: source nodes(0,1,4), amounts(2,6), target nodes(0,2,4).
Integrated output(4,4), total8. Density interpretation instead gives(4,6), total10;
never approve that result as integrated conservation. Test reverse/refinement/coarsening,
unequal measures, signed totals, partial coverage in either direction, unit conversions,
reversed orientation, stale support identities and unsupported kinds. Tests NOT RUN.

A3_COMPATIBILITY_MATRIX.md indexes exact baseline consumer references. Behavioral
refusal is a compatibility impact even if frozen signatures stay unchanged. Consumers
must migrate explicitly before integration; no source producer/old scientific identity
is silently rewritten. Semantic branch retains its legacy alias migration obligations.
Open decisions: per-consumer kind migrations, A-4 normal execution, vector/frame scope,
adaptive lineage/history integration, numerical error estimation and test/OD-3 authorization.
