# Independent authority-lifetime design review

Reviewed source: a57f1fdd393d1c98f603f6eb1a4ed99fb708f149, native primary checkout. Static inspection only; no tests executed, no implementation edits. Inspected BudgetReader, canonical BudgetLedger history protection, ScientificExperiment.record, benchmark fixture, and representative following callsites. User approved stable publication/history lifetime contract.

## Root cause and compatibility boundary

`owners.py:464` accepts an arbitrary zero-argument callback. `owners.py:983` calls it before reader retention. Even the recovery handler cannot establish what the callback published if interruption prevents capture and the callback returns mutable owner mapping storage. Copying in another wrapper after the callback merely moves the gap. A callback cannot promise recoverable publication by its Python type or caller assertion.

A typed source must own stable published binding storage BEFORE readers attempt acquisition. Its state is a lifecycle record of existing canonical accounts, not new balances, evidence, or budget decisions. Current benchmark fixture at `benchmarks/mind_gen2_authority_v1/fixtures.py:185` passes a lambda over replacement mappings; tests contain many such callsites. There are no non-definition production `BudgetReader.following` callsites under src in the search performed.

## Recommended smallest safe design

Introduce an explicit owner publication source beside the budget adapter. Publish detached native binding entries into an immutable state container held by the source. Keep references to the exact canonical BudgetLedger/ScientificExperiment objects, and retain every replaced binding generation for the source lifetime. A reader acquires the source state, reconciles retained generations through EXISTING BudgetReader canonical history/readback, and serves only the current generation after comparison. Any unestablished retained state refuses that verification. Reconciliation progress must never discard source-owned history needed by another interrupted reader.

Canonical accounts already prevent history truncation through their public mutation APIs: BudgetLedger.__setattr__ rejects reassignment of charges; settle appends; ScientificExperiment.record appends to its internal evaluations. Restoring by constructing a new canonical account does not erase the retained old account's spent history. No duplicate ledger or independently authoritative spend counter is needed. Public append-only history plus stable object references is sufficient for this lifetime property; private object mutation remains the existing trust boundary, not a newly invented exclusion.

Publish by constructing a new immutable source state containing BOTH retained generations and current generation, then swapping ONE source-state reference under its lock. An interruption before commit leaves the previous complete state; after commit the complete new state is recoverable. Do not implement publication as removal of old bindings followed by insertion of new ones. Initial construction must finish publication before the source can be supplied to a live reader. New account objects not yet committed to a publication cannot be used as the source's current dispatch authority.

States: OPEN(current, retained) -> OPEN(new_current, retained + old_current) on publish/restore; OPEN -> CLOSED irreversibly on close; CLOSED -> RETIRED only when no pending reader can obtain an actionable result requiring retained history. Every interrupted acquisition can reacquire the same stable source-owned history, including after an arbitrary number of restores. Failure during acquisition does not seal an honest source. A malformed authoritative account still follows the existing structural/unreadability rules.

## Retirement: prefer terminal retirement over per-read acknowledgements

A cursor acknowledging generation G once is NOT proof G can be retired when later replaced: G contains live accounts that may spend after acknowledgement and before replacement. That is a concrete lost-spend counterexample to a naive generation-watermark scheme. Likewise, reader `_in_flight` empty alone is insufficient: the reader can be called again.

The simple design retains historical bindings until an explicit source close irreversibly prevents EVERY associated reader from providing further live authority. Pending verifications must observe closure at the authoritative comparison boundary, just as reader sealing does. A previously captured projection is not live, and a new dispatch must reverify against the closed source and refuse. Release history only after the implementation establishes that pending operations cannot produce fresh acceptance requiring that history. Explicit active acquisition tracking and a CLOSED-but-not-yet-RETIRED state are acceptable. Interrupted retirement must leave history retained; it must never reopen the source or infer quiescence from timeout/GC. Do not retire merely because account mappings were detached, a weak reference vanished, or a time interval elapsed.

If bounded incremental history reclamation is required, a more complex closed-generation protocol is needed: owner freezes a generation's final history, readers reconcile THAT final history, and all relevant readers acknowledge it or are irreversibly closed. This is optional complexity, not needed for a first safe implementation. Record retained-generation growth as a resource limitation; do not silently discard records to cap it.

## Compatibility alternatives

1. Recommended: `BudgetReader.following(typed_source)` is the dispatch-capable path. Existing callback form remains callable for read-only projection/replay, but is explicitly not live for dispatch; migrate execution fixtures to publish every replacement through the typed source. Document this necessary trust-boundary tightening and test rejection of raw callback dispatch. Existing canonical account serialization stays unchanged.
2. Reject raw callbacks immediately with actionable migration error. Simpler semantics, larger compatibility break. Prefer only if preserving read-only callback mode creates ambiguity.
3. Accept a callback only if it returns typed publications issued and retained by a typed source already supplied to the reader. This can preserve an owner polling hook, but the source identity must be established BEFORE the callback starts; verifying a returned token afterwards is insufficient. More complicated than direct source reads.
4. Reject: automatic callback wrapping, detached-copy-on-return alone, arbitrary retry counts, permanent seal on all interrupts, or source history retirement by timeout. These either preserve the original race or reject legitimate recovery.

Do not use a public boolean such as `stable=True` as evidence of lifetime safety. A nominal wrapper around an unmanaged callback is also not enforcement.

## Required failure challenges

- Interrupt before acquisition begins, during acquisition, immediately after source return, and again in reader cleanup; publish a restored account after each interruption; retained spent account must still refuse redispatch.
- Interrupt publish before and after its single state commit; source remains exactly old or new complete state, never new current without old history.
- Account spends after a successful read, then owner replaces it before another read. Old account reference must remain observable despite previous reader acknowledgement.
- Multiple readers, one stalled and one advancing; source replacement cannot retire the stalled reader's spend history.
- Retain malformed/unknown history and publish an apparently empty account. Missing/unreadable history cannot become no spend.
- Repeated unchanged detached restores recover and allow legitimate progress; do not classify different object identity as contradictory history.
- Close races with acquisition, canonical readback, comparison, and dispatch re-verification. No fresh valid result after close's authoritative boundary. Attempted future use remains refused after physical retirement.
- Replay reconstructs canonical payload identities but cannot recreate a live publication source or erase its pending lifetime state.

## Decision

No additional owner decision is necessary for terminal source-lifetime retention plus explicit irreversible close: it fits the user's approved contract and optional acknowledgement guidance. The implementation must state its exact close/dispatch ordering and prove it with deterministic tests. Incremental reclamation would require additional engineering, not a weaker safety condition. Scientific verification/certification are not established by this static design review.
