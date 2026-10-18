# Draft PR-ready package: M1B vertex-centred dual-volume state adapter

Suggested title: `Bind vertex state to issued dual control volumes and explicit storage`
Branch codex/m1b-vertex-dual-state. Exact base
7f8cb5dac01cd7a270ef72886b77c8cddf717d3b; future PR target codex/m1a-mesh-lineage.
main -> Semantic#159 -> A-3#160 -> A-4#161 -> M1A#162 -> M1B.
Checkpoint#158 independent. M1A published as draft against A-4; no merge.
M1B local PR-ready only. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.

## Proposed description

Primal interval fields cannot represent vertex-centred finite-volume state without
changing their meaning. Add a separate numerical adapter: each issued primal vertex
owns a dual interval bounded by endpoints/midpoints, with version-bound typed vertex
intensive, dual density and dual integrated state. Shapes and physical meanings are
checked independently. No primal record is relabelled and no dual refinement ancestry
is inferred from coordinates.

Conserved transfer reuses A-3 interval mapping on derived dual supports, with independent
source/destination coverage and actual amount checks. Integrated amounts use source
dual measures correctly; density remains amount per length. Direct vertex interpolation
refuses. Reconstruct primary state only through an explicit current-support positive
per-dual integrated linear storage coefficient, binding exact intensive/integrated and
optional density meanings. No default area, density, heat capacity or material averaging.
All initial/coefficient artifacts require existing KnowledgeSource records and exact
hash-checked normalized bytes. These records remain declared input origins, not evidence
of physical applicability, measured data or validity. Derived states bind their parent
records and retain UNKNOWN output uncertainty.

Reuse local M1A mesh lineage, recorded coarsening and actual registered cache/history
clearing. Invalidate old dual supports, states and coefficient handles at mesh changes.
Require complete issued parent support/state/storage/transition lineage; refuse clones,
missing authority, byte substitution, unsupported coverage and replay/overwrite. Failure
following a mutated primal mesh poisons the adapter. Legacy transient adaptation guard
is unchanged; the explicit OD-6 /1 admission permits state adaptation only.

Independent static scientific architecture review PASS after two MEDIUM findings were
corrected (density meaning and missing ancestor support/transition issuance). This is
not executed scientific evidence. Tests are written, NOT RUN; only compile-only and
static checks allowed. DV-125..128 and predecessor DV rows await execution authorization.
No frozen export/schema or maturity/certification artifact changes.

## Exact changed-file inventory relative to M1A

| File | Purpose |
| --- | --- |
| src/engcore/numerical/vertex_state.py | New opt-in dual support, typed placement, sourced state/storage, lineage/invalidation and A-3 transfer adapter |
| tests/test_m1b_vertex_dual_state.py | Synthetic conservation, compatibility and adversarial probes, NOT RUN |
| docs/work/M1B_ARCHITECTURE_DECISION.md | Decision and Core compatibility review before implementation; final clarified density binding |
| docs/work/M1B_COMPATIBILITY_MATRIX.md | Exact dependencies, consumer and new implementation references |
| docs/work/M1B_STATIC_REVIEW.md | Independent A-J scientific architecture review |
| docs/work/M1B_MERGE_PACKAGE.md | PR description, inventory, limits and follow-on decisions |
| docs/work/ACTIVE_PLAN.md | Current M1B bounded scope, stack and remaining gates |
| docs/work/DEFERRED_VALIDATION.md | DV-125..128, NOT RUN |
| docs/work/PROGRESS.md | Publication, failed approaches, corrections and actual lightweight check results |

## Scientific limits and nonclaims

The measure is a 1D line interval. A dual density means amount per length, never an
implicit volume density with unit area. Spatial material/area integration is domain
work: supply the actual integrated coefficient on each exact target support. Equal
geometry/array length is insufficient to establish placement or local issuance.
Caller deliberately mislabelling same-length raw numbers cannot be detected numerically.

Only positive finite diagonal zero-reference linear storage A_i=C_i*u_i is supported.
Offset/nonlinear/nonlocal/state-dependent laws, vector/tensor state, affine quantities,
multidimensional/variable-area geometry quadrature and underdetermined reconstruction
refuse or remain unsupported. No remap/inheritance of coefficients; supply target-support
coefficients anew with provenance. Derived sources trace through existing state/law
parents; no claim that these are authenticated physical measurements.

KnowledgeSource is caller-constructible. Matching normalized bytes demonstrates exact
artifact/context binding, not truth, external authenticity, calibration, applicability,
licensing suitability or measured-data admission. Only normalized /1 artifacts are
supported here; raw document extraction and source qualification belong upstream.
Synthetic fixtures and arbitrary source-class labels never upgrade UNKNOWN uncertainty.

Coarsening loses unresolved information; integral preservation does not establish
pointwise accuracy, stability, solution verification or experimental validation. Mapped
state uncertainty and storage-law discrepancy remain UNKNOWN. Issuance is session-local,
serial and audit-export-only. External caches/provider sessions and concurrent mutation
are outside guarantees; only registered containers/handles are managed. Retained lineage
verification scales with history; no performance qualification.

## M1C follow-on and owner decisions

Next bounded task is M1C: domain-owned vertex-centred transient FV/backward Euler with
declared first-order temporal accuracy, explicit boundary/initial conditions and sourced
storage/conductivity/source records. Reuse this dual placement while deriving actual
material/interface integration; do not sample or average material discontinuities silently.
No existing steady solver is converted or legacy transient refusal relaxed in M1B.

Owner placement direction is implemented. For M1C, physical reference inputs/provenance,
material/interface integration rules and validity envelope still need concrete selection;
synthetic manufactured solutions must be labelled verification fixtures. Variable-area,
nonlinear storage or wider physics requires a new bounded design. Execution of DV rows,
full assurance/mutation/OD-3 and final gate/merge decisions remain separately authorized.
M1C followed by adaptive transient orchestration and numerical studies is still required
before full M1 can be decided. No capability promotion follows from this package.
