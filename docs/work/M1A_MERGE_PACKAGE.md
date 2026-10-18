# Draft PR-ready package: M1A lineage-bound 1D adaptation

Suggested title: `Bind 1D mesh adaptation and state transfer to issued bisection lineage`
Branch codex/m1a-mesh-lineage, exact base 1f43c59eab717aa7cbfea672b948accb37f3cc50.
Dependency main -> semantic [#159](https://github.com/sharq-labs/forge/pull/159)
-> A-3 [#160](https://github.com/sharq-labs/forge/pull/160)
-> A-4 [#161](https://github.com/sharq-labs/forge/pull/161) -> M1A.
Checkpoint#158 remains independent. Future stacked draft targets
codex/interface-flux-execution. Architecture decision cbecc2df precedes source edits.
M1A package is local; no automatic publication or merge. A-4 publication was separately
authorized and completed against A-3. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.

## Proposed description

Geometry-only Grid1D refinement does not establish mesh ancestry or protect state/cache
reuse. Add an explicit local lineage issuer with deterministic root/cell/version ids,
exact recorded bisections and coarsening that only restores issued active siblings.
Returning to the same geometry creates a new version. Captured snapshots and same-object
issuance reject fabricated, cloned or tampered history; hashes alone confer no authority.

Add managed content-addressed cell states and actual registered cache/history clearing
on mesh changes. Exact issued transition receipts authorize transfer of just-invalidated
source fields to the current version. Repeated transfer cannot overwrite current state.
Unissued/serialized/legacy ancestry and arbitrary adjacent merging refuse.

Reuse A-3 FieldSemantics and map_cells_1d. Distinguish integrated amounts from densities;
require an explicit intensive overlap rule and ratio-scale state units. Independently
check both coverage directions and actual conserved totals, instead of trusting reported
zero residuals. Output uncertainty stays UNKNOWN and receipts establish no physical
validity, solver verification or experimental validation.

Existing Grid1D/refine/adapt_grid identity, signatures, old schemas and refusal paths
remain intact. New numerical-only audit records use explicit /1 schemas; exported
records cannot grant durable/cross-process lineage authority. Frozen exports, shared
semantic contracts, certification artifacts and capability maturity are unchanged.

Independent static review PASS, four MEDIUM defects corrected. Tests are written,
NOT RUN. Only compile-only/static checks performed; no pytest, provider execution,
full assurance, mutation or OD-3. This implements M1A, not M1 as a whole.

## Exact changed-file inventory relative to A-4

| File | Purpose |
| --- | --- |
| src/engcore/numerical/mesh_adaptation.py | Explicit local lineage records, issued refinement and reversible coarsening; legacy API unchanged |
| src/engcore/numerical/interval_transfer.py | Managed bound state/resources, invalidation receipts and guarded A-3 transfer |
| tests/test_m1a_mesh_lineage.py | Lineage, conservation and adversarial probes, NOT RUN |
| docs/work/M1A_ARCHITECTURE_DECISION.md | Preimplementation decision and authority/compatibility boundaries |
| docs/work/M1A_COMPATIBILITY_MATRIX.md | Exact baseline consumer and current implementation references |
| docs/work/M1A_STATIC_REVIEW.md | Independent A-J review and resolved findings |
| docs/work/M1A_MERGE_PACKAGE.md | This package, limitations and remaining M1 scope |
| docs/work/ACTIVE_PLAN.md | Current bounded task/dependency and remaining gates |
| docs/work/DEFERRED_VALIDATION.md | DV-121..124, all NOT RUN |
| docs/work/PROGRESS.md | Publication, milestones, failed approaches and actual static commands |

## Lineage and conservation guarantees (implemented, unverified)

- Root registration declares context/frame and exact geometry; no ancestry inferred.
  Version identity binds parent, operation, policy and exact cell material. Bisections
  bind the original interval and representable midpoint; only exact active siblings
  can restore that parent. Missing, cloned, conflicting and mutated records refuse.
- State binds version, semantics, units, data bytes, uncertainty and declared context.
  Byte resolution rechecks integrity. Old fields/cache/history bindings refuse even
  after geometry is restored. Actual registered dict/list cache contents are cleared.
- Source transfer access requires its exact issued immediate change, current destination
  and an unconsumed/unpopulated field slot. Transfer is not an implicit rollback API.
- Mapping reuses exact interval overlap. Integrated values use source measure fractions;
  densities preserve their measure-weighted amount. Both coverage directions and actual
  totals are independently checked under existing representation allowance. No global
  rescaling, implicit extrapolation or intensive conservation claim.

## Scientific limitations

Initial values and context digests are caller declarations, not authenticated solver
or measurement provenance. Byte integrity is not scientific truth. Session issuance
is local; audit export is reproducible but trusted durable import/recovery is unsupported.
Serial access only. Managed invalidation covers registered built-in dict/list resources
and handles, not arbitrary external solver objects/caches or out-of-band consumers.

States represent scalar **primal interval cells**, count len(Grid1D.nodes)-1. They are
not nodal temperatures or vertex-centred dual-control-volume amounts. The existing
steady conduction implementation uses nodal unknowns/dual control volumes. M1B must
design an explicit version-bound primal-to-dual support adapter; passing nodal arrays
here refuses, rather than silently changing field meaning or inventing ancestry.
Dual-volume changes are not automatically primal bisections and cannot borrow their
ancestry merely from coincident coordinates.

Coarsening loses unresolved fine-scale information; transfer-back conserves the declared
total, not arbitrary fine variation. Integral closure does not establish local physical
validity or bound numerical error. Spatial error/model discrepancy stay UNKNOWN. No
physical time, transient conduction, adaptation scheduling, solver restart or capability
promotion is supplied. Lineage/snapshot verification cost grows with retained history;
no performance or capacity qualification is claimed.

## Remaining complete M1 contract

| Requirement | Existing boundary / remaining implementation |
| --- | --- |
| Transient nonuniform conduction | Existing conduction1d_nonuniform.py is steady only; do not relabel it transient |
| Vertex-centred FV | Existing steady nodal/dual-volume discretization is a reference; explicit state-placement/dual-support adapter needed |
| Backward Euler, temporal order1 | New transient mass/storage assembly and time rule; no executed temporal order study |
| Explicit boundary/initial/material states | Preserve existing boundary refusal; obtain actual sourced initial state, conductivity and storage/material records, no default properties |
| Adaptive transient execution | Compose issued mesh changes, state transfer, physical clock and managed provider/acceleration invalidation in a future driver |
| Numerical studies | Write then separately authorize temporal/spatial refinement, conservation/source/boundary balances and information-loss studies |
| Program gate/maturity | No decision without executed contextual evidence and mandatory CDAR fixtures; no capability promotion from code |

Recommended next slice M1B: design the version-bound vertex-control-volume state
placement adapter, then implement the bounded transient vertex-centred FV/backward-Euler
reference. Use a domain-owned storage law to convert temperature to conserved energy;
never infer energy from kelvin or silently invent heat capacity/density. Keep shared
lineage/transfer free of thermal conditionals. Do not weaken the legacy transient refusal
until the new transient path exists and has its own explicit admission.

Owner decisions/prerequisites: approve the concrete state-placement/dual-support design
through compatibility review; supply or select admissible boundary, initial and material
sources/context for physical claims; decide legacy consumer migrations and stack/checkpoint
integration; separately authorize DV-121..124, earlier recipes, integration/CI and final
OD-3/gate decisions. OD-6 already permits bounded M1 build work before DV0; no new scope
exception is inferred for the approved reference. Expanded physics, arbitrary merging,
durable authority or unsupported multidimensional adaptation needs separate design/scope.
