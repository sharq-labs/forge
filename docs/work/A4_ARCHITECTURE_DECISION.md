# A-4: executed physics-neutral interface flux convention

2026-10-18. Design/Core compatibility review BEFORE source changes.
Branch codex/interface-flux-execution depends on A-3 head
4f239fa7fe705e3d8ae390a8e885302dcb07904e. Main -> semantic PR #159 ->
A-3 PR #160 -> A-4. Checkpoint PR #158 independent. No merge or test execution.
Status when implemented: IMPLEMENTED / UNVERIFIED / UNCERTIFIED; no gate CLOSED.

## Bounded decision

Scalar normal components only, on CELL values of two StructuredMesh rectangles
representing surfaces in one explicit common plane/frame. Plane origin is meters;
orthonormal u/v axes embed mesh parameter coordinates into that plane. Area is
therefore the existing metric rectangle measure. Normals must be finite unit 3-vectors
parallel or antiparallel to u cross v. No oblique projection, different frames,
curved surfaces, vector-valued flux, unstructured surface or partial-coverage policy.
The common embedding is a declaration, not externally established geometry evidence.

Reuse InterfaceConvention, FieldSemantics/QuantitySemantics/ConservedQuantity,
FieldRecord/FieldValue and MappingDiagnostics. New InterfaceTransfer binds source and
target support fingerprints/conventions, physical meaning, conserved rate/amount,
representation (normal density or integrated surface amount), full coverage,
qualified common-plane overlap and sign relation. Domain Packs own quantities and
constitutive laws; no thermal law or universal quantity ontology enters Core.

Stored q = orientation * dot(physical vector, normal). For admitted parallel normals,
q_target = orientation_source * orientation_target * dot(n_source,n_target) * mapped(q_source).
The sign is derived and executed, never supplied as a free coefficient. A declared
equal-and-opposite outward relation additionally requires opposing geometric normals;
same-direction conventions can express one continuous oriented flux without pretending
to be two outward normals. Orientations affect stored values, not the physical law.

Flux density maps with overlap / target area. Integrated surface amount maps with
source-area division BEFORE overlap. No density/integrated conversion or time integration
is implicit. Reuse A-3 arithmetic and qualified structured rectangle geometry, checking
both coverage directions; identity is admitted only on identical geometry/support.
Direct FieldMapper and graph/TransferEngine use the same typed executable contract.
Without it, old flux/interface refusals stay in force. A-3 cell semantics remain unchanged.

## Authority and conservation

Report mapping consistency separately from executed oriented integral residual, using
actual stored source and target arrays normalized to their declared normal conventions.
Equal-and-opposite outward totals can be diagnosed from transferred values, but the
target value was constructed by this transfer. This is NOT an independent target
solver flux or coupled physical conservation proof. Numerical solution verification
and experimental validation remain separate; output uncertainty stays UNKNOWN.
Existing CoupledConservation continues to refuse fields; no diagnostic is admitted as
an executed source/storage balance or promoted to validation. Missing evidence stays UNKNOWN.

Generalize InterfaceContract and add neutral Dirichlet-Neumann admission parameterized
by exact intensive/flux semantic records. CHT is a wrapper requiring explicit domain
semantics and the equal-and-opposite typed transfer. Old prose normals cannot authorize
execution. Legacy CHT aliases/signs need explicit migration; no automatic identity rewrite.

## Core/API/schema/identity compatibility review

Frozen canonical manifests/exports and existing scientific evidence/uncertainty records
are unchanged. Add optional trailing CouplingEdge.interface_transfer, emitting edge /3;
legacy /1 and scalar semantic /2 payloads retain writer shape. Readers reject interface
keys on old schemas, missing /3 contract, or mixing scalar transport/conversion/prose
and executable interface transfer. Nested contract material enters graph/run identity.
FieldDefinition remains /2; allow declared 3D surface normal on 2D parameter support
only as a declaration, while execution requires the qualified transfer. InterfaceTransfer
has its own exact /1 schema. FieldMapper gains optional keyword-only interface contract.
Old imports remain canonical; no new canonical export, frozen pin or certificate update.

Affected consumers: graph/run serialization and replay, field unit conversion/record
binding, mapper callers, transfer/runtime mapping diagnostics, InterfaceContract and
CHT admission, provider boundary adapters, existing thermal fixtures and certified
dependency closure. A4_COMPATIBILITY_MATRIX.md records exact baseline references.
Behavioral refusal/migration is material even without a frozen digest change.
Final integrated CI, frozen/serialization/layer checks and OD-3 remain separately gated.

## Deferred adversarial probes

Opposing/same/reversed normals and orientations; unequal areas and discretizations;
density vs integrated formula; incorrect sign; missing conventions; geometry, coverage,
units/meaning mismatches; scalar vs vector; typed thermal and nonthermal charge transfer;
graph/schema identity and direct-mapper escape refusal. All tests NOT RUN.
Remaining scope: vector projections, unstructured/curved interfaces, independent coupled
balance, physical constitutive validation, moving interfaces, numerical error estimation.
