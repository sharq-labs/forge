# Core V0.3 Preregistration Deviation 001 — CampaignRun Iteration History

Status: **PROSPECTIVE AMENDMENT BEFORE IMPLEMENTATION**

Frozen preregistration remains unchanged:

- prereg commit: `4e38277f41ac39db0def713f32476923a7dadbbc`
- prereg blob: `60c7e4201673c5610f453923c68dbaa47f8a5661`

## Discovery

After freezing the preregistration and before implementing persistence, review of `CampaignRun` found another repeated cumulative history that the frozen document did not name explicitly.

`CampaignRun.to_dict()` serializes the complete `iterations` tuple. The runner copies the current `CampaignRun` into every legacy checkpoint. Therefore, even after removing repeated event, budget-charge, and effect histories, storing the full `CampaignRun` in every compact checkpoint would retain iteration prefixes repeatedly and violate the preregistered linear-growth gate S4.

This is not a new optimization goal. It is a necessary correction to make the frozen success criterion internally achievable.

## Amendment

V0.3 checkpoint records MUST NOT serialize the cumulative `CampaignRun.iterations` tuple.

Instead persistence will separate:

1. a compact current run-state record containing scalar/current fields only; and
2. append-only completed iteration records stored once.

A V0.3 checkpoint will commit to an iteration-journal prefix using:

```text
iteration_record_count
iteration_head_digest
```

The materialized `CampaignRun` returned to the existing runner API is reconstructed from:

- compact current run state; plus
- the committed iteration-journal prefix.

## Why a separate iteration journal is required

Using only `ITERATION_COMPLETED` campaign events is insufficient because current runner behavior can append an `IterationRecord` during a stop-proposal path without emitting `ITERATION_COMPLETED`. The persistence layer must preserve the `CampaignRun.iterations` sequence exactly, not infer a weaker approximation from selected event types.

## Additional invariants

- Iteration records are append-only and ordered by their stored sequence.
- A checkpoint's iteration cursor may never shrink.
- A checkpoint claiming N iteration records must commit to the digest of record N-1, or an empty digest when N is zero.
- Migration from legacy checkpoints must preserve the exact `CampaignRun.iterations` tuple at each checkpoint.
- Reconstruction must produce a `CampaignRun.to_dict()` equivalent to the legacy logical state, except for representation-specific persistence schemas outside `CampaignRun` itself.

## Acceptance impact

The deterministic scaling target is amended to count five historical streams stored once:

- campaign events
- budget charges
- applied effects
- completed/recorded iteration records
- checkpoint records

`plan` and `obligation_state` remain checkpoint-local current state. Repeating a bounded in-flight plan across a bounded number of crash-safe checkpoints is a constant-factor cost, not cumulative-prefix quadratic growth.

No scientific, inference, stopping, certification, or solver semantics are changed by this amendment.
