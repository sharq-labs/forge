# PR-ready package: declared quantity semantics

Suggested title: `Require declared quantity semantics for physics-neutral scalar coupling`

Status: IMPLEMENTED / UNVERIFIED / UNCERTIFIED. Not merge-ready until authorized
validation, compatibility disposition and required CI/OD-3 complete. No gap CLOSED.
Branch `codex/quantity-semantics`, base latest fetched origin/main
`0284ae161ad957d51674ee481e47cfd43d10c5f0`. Design-only commit `ab688c0f`
precedes shared implementation. Checkpoint Draft PR [#158](https://github.com/sharq-labs/forge/pull/158)
is independent; no checkpoint commits are included here. No automatic merge.

## Proposed PR description

Dimensional equivalence allowed unrelated quantity labels to connect and classified
force through legacy energy-density inference. Add explicit scalar meaning/role and
structured transport declarations. Typed ports must agree on exact meaning, roles
and conserved measure; opaque aliases and mixed typed/untyped paths refuse.

Reuse existing conservation arithmetic and LossPath fractions for named, realized
scalar partitions. Unknown delivery refuses; unquantified coefficient uncertainty
keeps output uncertainty UNKNOWN. Domain transformation participants own physical
laws; names and conservation closure provide no qualification or validation.

Untyped writers retain /1; typed extensions use /2 with downgrade/missing-field
refusal and material graph identity. Frozen exports, QuantityDependency and
EnergyConversion shapes stay unchanged. Legacy different-name connections require
explicit migration or exactly matched conversion forms. Existing exact-name thermal
behavior is retained by design; downstream execution is deferred.

Adversarial tests are written, NOT RUN. Independent static design/patch review PASS
does not establish verification, validation or certification. Typed fields refuse
pending the separate A-3 proposal. No provider capability claim is added.

## Exact changed-file inventory relative to base

| File | Purpose |
| --- | --- |
| src/engcore/scientific/semantics.py | New generic semantic/transport declarations and versioned extensions |
| src/engcore/scientific/multiphysics/ports.py | Optional dimension-bound port semantics |
| src/engcore/scientific/multiphysics/graph.py | Exact semantic admission; legacy alias refusal; typed conservation binding |
| src/engcore/scientific/multiphysics/conservation.py | Conserved measures and typed contribution roles |
| src/engcore/scientific/conservation.py | Semantic terms in existing balance arithmetic |
| src/engcore/execution/multiphysics/transfer.py | Structured scalar partitions; UNKNOWN coefficient UQ |
| src/engcore/execution/multiphysics/runtime.py | Bind actual balance terms to declared measure |
| tests/architecture/test_quantity_semantics.py | New adversarial and regression fixtures |
| tests/architecture/test_cross_domain_fixtures.py | Strengthen historical stiffness gap pin into refusal regression |
| docs/work/SEMANTIC_COMPATIBILITY_PROPOSAL.md | Preimplementation architecture and compatibility decisions |
| docs/work/SEMANTIC_IMPACT_MATRIX.md | 122-file static consumer index with exact baseline line references |
| docs/work/SEMANTIC_STATIC_REVIEW.md | Independent design/patch review, resolved fixture findings |
| docs/work/A3_DECLARED_FIELD_KIND_PROPOSAL.md | Separate unequal-cell mapping proposal only |
| docs/work/SEMANTIC_MERGE_PACKAGE.md | This PR-ready package |
| docs/work/DEFERRED_VALIDATION.md | DV-107..DV-112, all NOT RUN |
| docs/work/ACTIVE_PLAN.md | Current bounded resume state |
| docs/work/PROGRESS.md | Publication, implementation, static results, limitations |

## Compatibility and integration requirements

- Review all indexed producer/consumer categories, especially native thermal,
  electrothermal, composition packs, provider adapters, multiscale and flagships.
  Static references are an inventory, not a migration-completion claim. External
  factories/callers may require additional discovery.
- Owner must accept the fail-closed legacy alias behavior or approve explicit
  per-consumer migration before integration. Never infer semantic synonyms centrally.
- Confirm old-reader refusal of typed /2, untyped serialization/import identity,
  replay, graph/run digests and frozen snapshot equality by authorized execution.
- No frozen/certification artifact was updated. Shared trust/admission and pinned
  runtime dependency changes need existing CI classification and separate final-tree
  OD-3; do not bypass control-plane gates or silently regenerate pins.
- Run checkpoint DV-100/DV-101..106 in its separate repair tree first when authorized;
  start semantic checks with DV-107 (including revised DV-99), then DV-108..112.
  Resolve migrated/refused consumer outcomes before broad integration tiers.

## Limitations and owner decisions

Meaning identifiers are domain declarations, not verified ontology. The generic Core
does not establish applicability/qualification from them. Different meanings require
an explicitly qualified domain/provider participant under existing authority.

This slice does not implement all legacy dependency migrations, reaction/source
physics, independent storage dynamics, vector momentum/frame projections, time
integration, field mapping, complete single-sink loss or coefficient UQ. SIGNAL
provides no conserved partition. A passing partition identity would not validate
species reactions, charge dynamics, mechanics or heat physics.

Owner decisions remaining: per-consumer alias migration dispositions, timing of
legacy dependency deprecation/promotion of new records, test/provider authorization,
final integration certification, and A-3 versioned field-kind/legacy mapping policy.
No additional owner decision was needed to implement the already-authorized bounded slice.

Next bounded task: approve/design an explicit scalar declared-field-kind mapping
contract, using A3_DECLARED_FIELD_KIND_PROPOSAL.md before implementation. Distinguish
integrated amounts from densities on unequal cells; specify coverage, measure, sign,
support identity and UNKNOWN uncertainty, with no automatic 2D/vector capability claim.
