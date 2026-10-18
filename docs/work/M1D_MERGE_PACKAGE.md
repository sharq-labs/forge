# Draft PR-ready M1D package: bounded adaptive transient runtime

Suggested title: `Compose issued adaptive transient windows with conservative rebuild and bounded rollback`
Branch codex/m1d-adaptive-transient, exact base
73a18468d02e5817178e1bf10d53298d5cc14900. Future draft targets codex/m1c-transient-fv-1d.
main -> #159 -> #160 -> #161 -> #162 -> #165 -> M1C Draft#166 -> M1D local.
Checkpoint#158 independent. M1C published against M1B labelled INTEGRATION HOLD;
no earlier PR merged, retargeted or certification pin updated. M1D local package only.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED; INTEGRATION HOLD, not full M1 acceptance.

## Proposed description

Add a physics-neutral coordinator for exact accepted transient windows and explicitly
issued adaptation decisions. Register actual versioned criterion source bytes; bind
each selection to current mesh/state/time and accepted result. No automatic estimator,
refinement criterion or scientific tolerance. Criteria/schedules are declarations,
not verified error evidence.

Compose M1A lineage/sibling coarsening, M1B dual integrated-state remap and fresh M1C
sessions through a thermal backend. Invalidate fields/registered cache/history, transfer
energy, re-resolve actual target material/source records, integrate fresh storage and
reconstruct intensive state with an issued continuation permit. Preserve physical
material/area/contact field across partition changes. Derived temperature is never
relabelled as sourced initial measurements. Old sessions retire; time never advances
across a refused window.

Reuse strict CheckpointSeal unchanged for same-object, unchanged-mesh window rollback.
Capture verified immutable references, state/clock/issuance registries and registered
finite JSON-tree resources. Separate local reference anchors reject equal-content
replacement of issued objects inside a sealed snapshot. Restore exact captured state
and verify actual bytes/identities. Failed restoration or any failure after mesh mutation
poisons execution; no partial mesh rollback, external provider or durable recovery claim.
Accepted/adaptation/refusal receipts form an issued hash-linked history with UNKNOWN UQ.
Committed-state binding refuses out-of-band rewind of accepted history.

## Exact changed-file inventory relative to M1C

| File | Purpose |
| --- | --- |
| src/engcore/numerical/adaptive_transient.py | New generic criterion/decision/coordinator/history and rollback-or-poison protocol |
| src/engcore/domains/thermal_models/adaptive_conduction1d.py | New thermal backend, strict same-session checkpoint and source-qualified rebuild |
| src/engcore/domains/thermal_models/conduction1d_transient_fv.py | Preserve sourced constructor; add issued derived continuation and factored common initialization |
| tests/test_m1d_adaptive_transient.py | Synthetic conservation/adversarial/recovery/study designs, NOT RUN |
| docs/work/M1D_ARCHITECTURE_DECISION.md | Preimplementation architecture/table and final bounded limitations |
| docs/work/M1D_COMPATIBILITY_MATRIX.md | Exact references and API/identity/lifecycle impact |
| docs/work/M1D_MODEL_DISCOVERY_COMPATIBILITY.md | Intentional census20 proposal and import/other guard impact for owner approval |
| docs/work/M1D_STATIC_REVIEW.md | Independent A-J review and final addendum |
| docs/work/M1D_MERGE_PACKAGE.md | This PR package, remaining limits and decisions |
| docs/work/ACTIVE_PLAN.md | Current bounded M1D state, dependency/hold and remaining gates |
| docs/work/DEFERRED_VALIDATION.md | DV-133..136, NOT RUN |
| docs/work/PROGRESS.md | Publication, milestones/failed approaches, review corrections and actual checks |

## Recovery and scientific limits

Rollback covers only exact stateless SparseFVProvider, same backend/session/mesh/support/
build, saved immutable data that remain intact, and registered builtin dict/list roots
with finite JSON-tree contents. No external nested alias identity/opaque factorization,
external session/process, concurrency or durable persistence. Checkpoint refusal occurs
before execution for unsupported resources. Orphan immutable blobs may remain after
rollback without issued/live state handles; store GC is outside scientific recovery.

Adaptation rollback is unsupported once mesh identity changes. A failed transfer,
target property/source resolution or rebuild then poisons the complete driver/backend.
No accepted adaptation receipt is produced. Failed-window attempts remain refusals
in audit history even after complete same-mesh restoration; retry is caller-explicit.
Native seal same-object ownership/build/record refusal is preserved, independent of
checkpoint PR#158. No existing checkpoint authority is extended across processes.

Only qualified scalar 1D geometry/phase-constant thermal laws from M1C. Integral remap
uses the declared piecewise-constant energy density implied by source dual amounts.
At material jumps this can change local reconstructed temperature, even for constant
initial temperature. No constant-temperature/local accuracy promise at unresolved
material interfaces. Subsequent Dirichlet initial consistency may refuse after such
remapping/coarsening; no silent boundary overwrite or invented reservoir correction.
Broader material-weighted remap/Dirichlet adaptation policy requires separate design.

UNKNOWN numerical/model discrepancy stays UNKNOWN. Conservation and manufactured
study definitions are not executed solution verification, physical validation or
certification. Caller criteria are not scientific evidence. No autonomous mesh-selection
algorithm supplied or claimed. Target physical-property changes are refused, not a
supported physical evolution/material-switching law.

## Discovery compatibility and remaining M1 acceptance

Static intended populations: models20 (pin19), reserving16, condition names96,
reserved names63 and ScientificSolver11 unchanged. No new model in M1D. Mandatory
import failures remain fatal; actual import-failure list UNKNOWN until execution.
M1D_MODEL_DISCOVERY_COMPATIBILITY.md proposes an explicit owner-reviewed 19->20 count
change, with no suppression/skip/equality weakening or frozen/certificate regeneration.
No such approval/edit is inferred here; OD-3 stays separate.

Remaining M1: execute all predecessor and M1D DV packs, record/fix actual failures,
run required contextual temporal/spatial/adaptive convergence and conservation studies,
run mandatory CDAR architecture fixtures, resolve the census compatibility/certification
hold and complete exact integrated-tree checks. Owner then decides M1 under the program;
no capability promotion follows from this code. Real physical input/model qualification
and any broader recovery/remap/BC policy still require appropriate owner/domain decisions.

Independent static review is separate from execution. No pytest/provider solves/full
FAST/performance/mutation/full assurance/OD-3 in this build. Deferred DV-133..136 and
all earlier rows remain NOT RUN. No automatic M1D publication or merge.
