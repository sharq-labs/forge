# Core V0.3 — Incremental Campaign Persistence Preregistration

Status: **PREREGISTRATION — implementation not yet admitted**

Base commit: `bccd6c19134770f0b74d543313be1c21e0a7007b`

Working branch: `core/v0.3-campaign-persistence`

This milestone exists because the performance audit measured a scaling defect in campaign persistence. It is not K2, not inference work, not a Decision Engine redesign, and not permission to rewrite frozen campaign history.

---

## 1. Measured defect

The current persistence model stores a complete `CampaignEventLog` inside every `CampaignCheckpoint`, while `CheckpointStore` retains every checkpoint. If checkpoints are taken over a growing campaign, the store therefore retains repeated prefixes of the same event history.

Measured PERF-0 evidence on the frozen predecessor implementation:

| Checkpoints | Events in head log | Event records retained across all checkpoints | Serialized bytes |
|---:|---:|---:|---:|
| 10 | 40 | 220 | 106,793 |
| 100 | 400 | 20,200 | 8,779,983 |
| 300 | 1,200 | 180,600 | 77,982,883 |
| 1,000 | 4,000 | 2,002,000 | full serialization intentionally skipped |

The audit estimated approximately 864 MB near 1,000 checkpoints if the existing representation is fully serialized.

The event-history repetition is proven. Two additional cumulative structures also require explicit accounting during this milestone:

- `BudgetLedger.charges`
- `EffectLedger.applied`

Both are copied into every checkpoint today. Their constants are smaller than the event log in the measured benchmark, but a design claiming linear persistence must not quietly leave another repeated cumulative ledger with quadratic total storage.

---

## 2. Problem statement

Current logical state is correct but the persistence representation is not scalable.

Current shape:

```text
Checkpoint 1
  run
  events[0..E1]
  budget charges[0..B1]
  effects[0..F1]
  plan
  obligation state

Checkpoint 2
  run
  events[0..E2]
  budget charges[0..B2]
  effects[0..F2]
  plan
  obligation state

...
```

The history itself is append-only, but checkpoint serialization repeatedly embeds that append-only history.

Target principle:

> Persist each historical fact once. Checkpoints identify a verified prefix and contain only the minimum resumable state that cannot be reconstructed safely without re-deciding or re-executing.

---

## 3. Non-negotiable invariants

A performance improvement is rejected if any of these change.

### I1 — Append-only campaign history

Previously recorded campaign facts may not be edited, deleted, reordered, or silently replaced.

### I2 — Hash-chain tamper evidence

For every committed event prefix, mutation, deletion, reordering, wrong run identity, or predecessor mismatch must remain detectable.

### I3 — Deterministic resume

Resume must continue the exact recorded decision. It must not rebuild a snapshot, regenerate candidates, re-rank candidates, replace a selected action, or invent a new `IterationPlan` for an in-flight iteration.

### I4 — At-most-once side effects

Resume must not duplicate:

- simulation execution
- evidence creation
- evidence admission
- calibration update
- budget settlement
- any other effect already recorded in the effect ledger

### I5 — Realized budget truth

Previously incurred cost remains a fact. Persistence must not recalculate historical charge splits from a later state or lose an overrun.

### I6 — Obligation state durability

The exact obligation state feeding later snapshots, liveness, and stopping review must survive restart unchanged.

### I7 — In-flight plan durability

If `ACTION_SELECTED` is recorded, the exact snapshot, dependency manifest, recommendation, action, predicted cost, and relevant liveness context must be available after restart. If not, resume must fail closed rather than re-decide.

### I8 — Historical artifact compatibility

Frozen V0.2/M5/M5.1 checkpoint artifacts are historical evidence. They are not rewritten in place.

### I9 — No silent scientific semantic migration

Loading an old artifact under V0.3 must either:

1. preserve its meaning exactly, or
2. refuse with an explicit compatibility error.

No loader may reinterpret old bytes as a stronger guarantee.

### I10 — No timing-based trust claim

Wall-clock speed is engineering telemetry only. Acceptance is primarily based on deterministic storage/operation-count properties.

---

## 4. Architecture under test

The preregistered target is a **journal + compact checkpoint index** model.

Conceptually:

```text
CampaignPersistenceStore
│
├── Event Journal (append-only)
│     event 0
│     event 1
│     ...
│     event N
│
├── Budget Journal (append-only settled charges)
│     charge 0
│     charge 1
│     ...
│
├── Effect Journal (append-only applied-effect records)
│     effect 0
│     effect 1
│     ...
│
└── Checkpoint Records (append-only)
      checkpoint 0
      checkpoint 1
      ...
```

A checkpoint record stores cursors and digest commitments rather than copies of cumulative journals.

Candidate compact checkpoint fields:

```text
run
plan | null
obligation_state

event_count
event_head_digest

budget_charge_count
budget_head_digest
budget aggregate state required for O(1) affordability

effect_count
effect_head_digest

checkpoint_sequence
previous_checkpoint_digest
```

The exact serialized field names may change during implementation review, but the semantic separation above is preregistered.

---

## 5. Event journal contract

### 5.1 Identity

The event journal belongs to exactly one `run_id`.

### 5.2 Sequence

Events remain zero-based and contiguous. The event at index `i` must declare `sequence == i`.

### 5.3 Chain

`prev_digest` continues to commit to the previous event digest exactly as V0.2 does.

### 5.4 Checkpoint commitment

A checkpoint claiming:

```text
event_count = N
event_head_digest = H
```

is valid only if:

- the journal contains at least N events;
- the prefix `[0:N]` verifies;
- the digest of event `N-1` equals H, or H is empty when N is zero;
- all events in the committed prefix belong to the checkpoint run.

A later uncommitted journal suffix must not silently become part of an earlier checkpoint's resume state.

### 5.5 Resume materialization

Materializing a `CampaignEventLog` from a checkpoint is permitted to be O(N) at resume time. What is prohibited is storing O(N) copies of the same prefix at every checkpoint.

---

## 6. Budget journal contract

The current `BudgetLedger` is both audit history and current accounting state. V0.3 separates those responsibilities in persistence without changing budget semantics.

Each settled `BudgetCharge` is written once to an append-only budget journal.

A compact checkpoint may retain aggregate values required for O(1) decision-time accounting, including at minimum:

- total budget
- reserved validation budget
- spent general
- spent validation
- spent total
- overrun
- cost unit
- executor-enforced cap and source, if declared
- number/digest of committed charge records

On load, aggregates must be verifiable against the committed budget-journal prefix. A mismatch is corruption and must fail closed.

A repeated `charge_id` remains idempotent. The persistence redesign must not make a previously settled charge settle twice after restart.

---

## 7. Effect journal contract

An applied effect record is historical state, not an evictable cache entry.

Each record commits at least:

- deterministic effect key
- result/reference string
- sequence
- predecessor digest or equivalent journal commitment

The current `EffectLedger` lookup behavior must be recoverable exactly after restart.

A compact checkpoint stores the committed effect prefix cursor/digest, not a fresh copy of the entire `applied` mapping.

Resume may reconstruct an in-memory lookup index from the committed effect prefix once. This O(N) restart cost is acceptable; repeated O(N) persistence per checkpoint is not.

---

## 8. Checkpoint chain contract

Checkpoint history itself remains append-only and auditable.

Every V0.3 checkpoint record must have a deterministic digest.

The preferred design chains checkpoint records using:

```text
checkpoint_sequence
previous_checkpoint_digest
```

This prevents removing/reordering intermediate checkpoints without detection, instead of relying only on the event log to prove historical ordering.

A checkpoint is admitted only if all committed journal cursors are monotone relative to its predecessor.

Forbidden transitions include:

- event cursor decreases
- budget cursor decreases
- effect cursor decreases
- run id changes
- checkpoint sequence skips or repeats
- previous checkpoint digest does not match

---

## 9. Crash consistency model

This milestone must define and test crash boundaries rather than assuming file writes are atomic.

Preregistered logical write order:

1. append newly completed historical records to their journals;
2. ensure journal records are durably serialized by the persistence backend;
3. append a checkpoint record that commits exact journal prefixes;
4. only a fully valid checkpoint becomes eligible for `latest()` / resume.

If a crash occurs after a journal append but before checkpoint commit, the extra journal suffix is **uncommitted** and must not change resume state.

If a checkpoint references a prefix that is missing, corrupt, or has the wrong digest, load must fail closed.

The initial file backend may use an atomic replace strategy for manifests/indexes where needed; no claim of database-grade transactional durability is allowed unless actually implemented and tested.

---

## 10. Backward compatibility strategy

V0.2 serialization remains frozen.

V0.3 must use new schema identities for changed persisted structures. It must not reuse an old schema string for a meaningfully different shape.

Required compatibility behavior:

### C1 — Read old

A V0.3 compatibility loader must be able to read a valid legacy `CheckpointStore` artifact and expose the same latest resumable state.

### C2 — Do not rewrite old automatically

Loading a legacy artifact does not mutate it or overwrite it with V0.3 bytes.

### C3 — Explicit migration

If migration tooling is implemented, migration creates a new V0.3 artifact beside or at an explicitly requested destination.

### C4 — Migration equivalence

For a migrated store, these must match the legacy source at every checkpoint where applicable:

- run state
- latest event sequence and head digest
- budget charges and accounting totals
- applied effect key/reference pairs
- plan digest
- obligation state
- latest resume behavior

### C5 — Frozen artifact hashes

Existing frozen artifacts and their recorded digests must remain byte-unchanged.

---

## 11. Scope boundary

In scope:

- versioned persistence contracts
- append-only event persistence
- append-only budget-charge persistence
- append-only effect persistence
- compact checkpoint records
- deterministic legacy migration/compatibility
- runner integration needed to persist/resume through the new interface
- deterministic scaling tests
- corruption/crash-boundary tests

Out of scope:

- K2 multi-parameter inference
- K3 uncertainty propagation
- Decision Engine V0.3
- BoTorch
- distributed execution
- remote databases
- cloud object storage
- network replication
- generic event-sourcing frameworks
- solver changes
- new scientific results
- changing stopping/certification policy

---

## 12. Required adversarial tests before merge

The implementation is not merge-ready without tests for all of the following.

### A. Event history integrity

- edit one stored event payload -> load/ref verification fails
- delete a committed event -> fails
- reorder two committed events -> fails
- wrong `prev_digest` -> fails
- wrong event sequence -> fails
- wrong run id -> fails
- checkpoint head digest does not match committed prefix -> fails
- uncommitted suffix exists after latest checkpoint -> latest resume ignores suffix

### B. Checkpoint history integrity

- checkpoint sequence repeats -> fails
- checkpoint sequence skips unexpectedly -> fails
- previous checkpoint digest mismatch -> fails
- any committed cursor shrinks -> fails
- checkpoint references records beyond journal length -> fails

### C. Resume equivalence

For the same interrupted campaign state, legacy and V0.3 resume paths must produce the same next allowed behavior and must not:

- re-execute completed simulation
- re-charge budget
- re-create admitted evidence as a second contribution
- re-run calibration update
- rebuild a selected decision plan

### D. Budget equivalence

- pool balances match before/after migration
- overrun matches
- repeated charge id remains idempotent
- validation reservation split matches

### E. Effect equivalence

- every legacy applied key/reference survives migration
- duplicate effect attempt is still refused/skipped according to existing semantics

### F. Plan/obligation equivalence

- plan digest unchanged through migration
- obligation state unchanged
- selected-action-without-plan still fails closed

### G. Serialization determinism

Given identical logical state, canonical serialized records and digests must be identical across repeated runs on the same declared format.

---

## 13. Scaling acceptance criteria

Performance acceptance is expressed primarily in deterministic record counts and serialized growth.

Using the synthetic benchmark pattern of 4 events/checkpoint:

### S1 — Event record storage

At N checkpoints, total persisted event records must be `4N`, not `2N(N+1)`.

For N=1000:

```text
legacy event records retained: 2,002,000
V0.3 target event records:      4,000
```

### S2 — Checkpoint event payload

A V0.3 checkpoint record must not contain a serialized full event list.

### S3 — Budget/effect duplication

A checkpoint record must not serialize complete historical budget-charge or effect journals.

### S4 — Asymptotic artifact growth

With fixed-size synthetic records and no in-flight plan growth, total persisted bytes must scale approximately linearly with checkpoint count. A regression test should compare growth ratios at 100/300/1000 checkpoints and reject quadratic repeated-prefix behavior using deterministic record counts rather than a fragile wall-clock threshold.

### S5 — Save work

Creating checkpoint N must not verify or serialize all prior event prefixes. Verification may validate the newly committed suffix plus required head commitments.

### S6 — Resume work

One-time O(N) journal verification/materialization during load/resume is acceptable. O(N^2) verification across repeated stored prefixes is not.

---

## 14. Scientific/Core change policy

This milestone intentionally changes SRIA persistence contracts, so it is a Core V0.3 milestone and must be versioned as such.

It does **not** authorize changes to:

- `src/engcore/scientific/`
- scientific model definitions
- solver validation levels
- evidence semantics
- inference semantics
- certification/stopping semantics

If implementation appears to require any of those, stop and review the requirement before changing code.

---

## 15. Implementation sequence

Implementation must proceed in small reviewable steps.

1. Freeze this preregistration and baseline SHA.
2. Add compatibility/scaling tests that fail against the legacy representation where appropriate.
3. Introduce versioned append-only journal record contracts.
4. Introduce compact V0.3 checkpoint record + checkpoint chain.
5. Add legacy reader/migration path.
6. Integrate `CampaignRunner` behind a persistence interface without changing campaign decision semantics.
7. Add crash/corruption adversarial tests.
8. Re-run synthetic scaling audit at 10/100/300/1000 checkpoints.
9. Run full authoritative test suite.
10. Clean-clone verification.
11. Independent PR review / Copilot review.
12. Freeze only after all acceptance criteria pass.

No K2 work starts inside this branch.

---

## 16. Merge gates

Final verdict may be `MERGE READY` only if all are true:

- legacy artifacts still load or explicitly documented incompatible artifacts fail closed;
- frozen historical bytes are untouched;
- full suite passes;
- clean clone passes;
- event/budget/effect histories are each persisted once rather than copied into every checkpoint;
- checkpoint chain corruption is detected;
- journal corruption is detected;
- uncommitted suffix cannot change resume state;
- at-most-once effects survive restart;
- budget accounting survives restart exactly;
- in-flight plan survives exactly;
- deterministic scaling demonstrates linear record growth;
- no scientific or inference semantics changed.

Otherwise verdict is `NOT MERGE READY` or `MERGE READY WITH NON-BLOCKING DEBT` only when the remaining debt cannot compromise resume correctness, auditability, or asymptotic persistence behavior.

---

## 17. Preregistered success claim

If this milestone passes, the strongest allowed claim is:

> SRIA V0.3 campaign persistence stores append-only historical records once and uses digest-committed compact checkpoints for deterministic resume, reducing repeated-prefix persistence from quadratic growth to linear growth in campaign history while preserving audit, budget, effect-idempotency, plan, and obligation semantics.

It must **not** claim distributed transactions, crash-proof storage under arbitrary filesystem failure, physical scientific validation, or general database durability unless those properties are separately implemented and tested.
