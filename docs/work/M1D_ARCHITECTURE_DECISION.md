# M1D bounded adaptive transient execution / recovery

Preimplementation decision, 2026-10-18. Exact base M1C
73a18468d02e5817178e1bf10d53298d5cc14900; branch codex/m1d-adaptive-transient.
main -> #159 -> #160 -> #161 -> #162 -> #165 -> M1C Draft#166 -> M1D local.
Checkpoint#158 independent. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.
M1C census integration hold remains; no certification pin or model change proposed.

## Bounded task / ownership

| Files | Acceptance | Dependencies | Verification |
| --- | --- | --- | --- |
| numerical/adaptive_transient.py | Physics-neutral explicit criterion/decision, issued mesh operations, accepted-window ordering, complete history, rollback-or-poison | M1A/M1B, typed time, domain backend protocol | Written tests + compile/static only |
| domains/thermal_models/adaptive_conduction1d.py | Thermal backend, fresh target material resolution/storage/session rebuild, bounded same-object checkpoint | M1B/M1C, strict existing CheckpointSeal | Independent static review; no execution |
| domains/thermal_models/conduction1d_transient_fv.py | Explicit issued energy continuation route; original sourced constructor preserved | Existing domain model, M1B placed states | Compatibility and adversarial tests, NOT RUN |
| tests/test_m1d_adaptive_transient.py | Independent balances, refinement/coarsening, recovery/poison/order/convergence definitions | New runtime and original parent stack | NOT RUN |
| docs/work/M1D_* plus active/progress/deferred | Exact census impact/compatibility, source inventory, decisions and recipes | Core Freeze/program policies | Static references only |

## Execution architecture

Separate a generic AdaptiveTransient1D coordinator from a thermal backend. Coordinator
owns immutable issued criterion/decision records, accepted-window/adaptation/failure
history and refusal state. Domain backend owns physical session creation, material
resolution and recovery details. Numerical module never imports thermal laws or units.
Explicit versioned M1D admission; legacy require_supported_adaptation transient refusal
unchanged. No implicit estimator, marking threshold, refinement schedule or tolerance.

Criteria are caller-declared versioned definitions with actual pinned source bytes.
Decisions explicitly name a registered criterion, current accepted result/state, exact
mesh/time, operation/cells or issued sibling bisections and caller-supplied mesh policy.
This binds a declared selection to its basis; it does not verify the criterion's physical
adequacy or grant numerical-error evidence. No adaptation before an accepted window.
Unsupported/undeclared decisions refuse. Refine/coarsen only through live M1B -> M1A.

Window execution calls M1C exactly; accepted receipts record window, before/after states,
mesh/support, complete solver result and hash-linked history. Start must equal current
exact TimePoint, no gaps/overlaps/basis guessing or silent retries. Failure receipts stay
in history and never count as successful windows. Repeating a refused attempt requires
an explicit caller action after safe rollback; no automatic time stepping.

Adaptation occurs between accepted windows at their exact shared instant. Preserve the
issued source integrated energy, invalidate via M1B/M1A, remap that energy using dual
supports/A-3. Never remap C or temperature as conserved values. Domain backend requires
explicit target regions/contacts, re-resolves each material and reintegrates actual dual
storage. It reconstructs temperature from transferred energy and new qualified C, then
constructs a fresh M1C session. Old fixed-mesh sessions retire. Mesh-dependent registered
fields/cache/history clear through parent machinery. No metadata-only invalidation.

## Derived continuation, not fabricated initial provenance

M1C's original constructor remains sourced-initial only, with the same signature.
Add a separate domain-issued continuation permit and factory. Permit is issued before
adaptation by the exact current session and binds source energy/support/context/time/
provider/build/configuration. Factory admits only its issuer's permit, actual immediate
issued mesh transition, transferred current energy and actual transfer receipt. Context
rebinding is explicit derived state with exact parent IDs, not a new measurement or
manufactured KnowledgeSource for temperature. Fresh target context and material C are
bound; the permit/rebuild receipt connects old and new contexts. Core semantics unchanged.

## Recovery scope and failure policy

Reuse existing strict CheckpointSeal unchanged. Same backend object seals a bounded
window snapshot of the exact M1C session, placed-state registries/handles, scalar clock,
issued receipts and registered plain builtin dict/list cache/history resources. Snapshot
contains captured canonical material and verified references, never repr/pickle/hash of
opaque state. Resource values must be finite JSON scalar/list/dict trees with string
keys; opaque provider resources refuse checkpointing. SparseFVProvider must be exact,
stateless builtin type, with source/SuperLU/config identity intact. No external provider
session or hidden continuation state is supported. Snapshot export grants no issuance.

Rollback is supported only if the exact adapter/primal version/support did not change
and source/config/build and saved immutable records/data bytes still verify. Restore
known in-memory registries/handles/time/receipt state and registered resource contents
on their same objects, then verify full M1C/M1B identity and values before declaring
rollback successful. New speculative states become unissued. A failed window returns no
successful result; rollback receipt retains refusal and unchanged logical time.

Mesh mutation is deliberately outside this rollback capability. If an adaptation,
transfer, material re-resolution or rebuild fails after mesh mutation, or any restoration
fails/authority is missing/bytes drifted, poison the complete coordinator/backend and
refuse further execution. Never attempt a partial mesh rollback or flip failed state
back to success. Cross-object/process recovery remains unsupported. This is a bounded
rollback-or-poison contract, not full adaptive recovery/certification.

## Compatibility / science boundaries

New numerical/domain records are /1 audit-only; old schemas/imports/IDs, strict seal,
legacy guards and frozen/certified artifacts untouched. M1C constructor/private setup
may be factored while keeping original sourced admission behavior and model identities.
Its implementation build hash intentionally changes. New derived continuation path is
an explicit domain compatibility change, documented and reviewed before implementation.
No additional scientific model: census remains statically20 vs pinned19; reserving16,
condition names96, reserved names63 have no semantic additions. Actual import outcomes
are UNKNOWN until execution; do not treat a successful compile as import verification.

UNKNOWN uncertainty remains UNKNOWN. Integral remap/balance is not local accuracy,
solver convergence studies are not validation, caller criteria are not evidence.
Physical sources/model applicability remain unqualified/UNKNOWN as in M1C. Tests use
synthetic mathematical inputs; no invented material measurements or thresholds.

M1 acceptance still needs owner-authorized execution of all deferred parent/M1D packs,
spatial/temporal/adaptive studies and required CDAR probes, model-census compatibility
approval and OD-3/integration decisions. M1D cannot close M1 from implementation alone.

## Final bounded safeguards

Fresh target partitioning may split identical material regions, but overlay comparison
must preserve the exact material property/state identities, IDs, area and contact
field. Changing physical properties is not adaptation. Re-resolve actual source bytes;
never transplant old C. Coordinator binds the expected committed backend state/time,
so direct out-of-band checkpoint restore cannot rewind accepted history silently.
Restoration must reproduce the full pre-attempt identity, not merely return without error.

Registered resource roots are restored on their same builtin objects; JSON-tree value
contents are supported, not arbitrary alias identity in external references. Arbitrary
external aliases/provider sessions are outside recovery scope. Speculative immutable
bulk blobs may remain in the content store without live issued handles after rollback;
this is not a store garbage-collection operation.

At material jumps a source dual average may conceal within-cell variation. Conservative
remap/reconstruction can therefore alter local temperature even for an initially
constant temperature; UNKNOWN remap error remains. No automatic boundary overwrite:
if reconstruction conflicts with a subsequent Dirichlet initial consistency requirement,
the window refuses/rolls back. A broader material-weighted remap or Dirichlet adaptation
policy needs separate domain design; no universal local accuracy claim is made here.
