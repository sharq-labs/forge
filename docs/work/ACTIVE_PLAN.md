# Active Plan

Purpose: keep the current Forge execution slice bounded, resumable and aligned
with `docs/project/FORGE_MASTER_PLAN.md`.

## Current objective

Execution strategy changed (2026-09-25): **build the big architecture first**
(BIG 2 Time Engine -> BIG 3 Environment -> BIG 4 Lifecycle ...), using only
focused smoke/regression checks during the build. After the architecture is
built: run real scenarios, review it scientifically/numerically, audit/rewrite
stale tests, and only then run the full FAST / SCIENTIFIC / mutation /
recertification campaign. The P0/P0.1 full-verification items below are
deferred to that campaign, not abandoned.

Current: **BIG 3 — Environment Engine** built on BIG 2; next is **BIG 4 — Lifecycle/Degradation**.

## Current branch / PR

- Branch: `claude/serene-tesla-n7t17w` (from `main` @ `2b76017f`)
- PR: none opened; verify GitHub before making a current PR claim.
- Base: `main`

## Task tree

### P0 — Core / CI / assurance stabilization

- [x] Run the normal Tests workflow automatically on pull requests.
- [x] Re-run normal merged-tree checks on pushes to `main`.
- [x] Restore automatic hardened-core recertification ownership on pull requests.
- [x] Retain manual recertification as a fallback.
- [x] Require all V4 mutation shards explicitly before certification.
- [x] Remove the invalid `hardening_assurance build --event` invocation.
- [x] Make certificate-child verification work for the automatic PR flow.
- [x] Run branch-policy verification after updates to `main`.
- [x] Install all declared reproducibility extras in the Docker image.
- [ ] Obtain a complete green automatic PR assurance run on the current head.
- [ ] Verify the certificate/assurance produced by the automatic flow is bound
      to the exact measured source commit.
- [ ] Verify/restore the required GitHub branch ruleset for `main`; repository
      code can report policy but cannot substitute for repository settings.
- [ ] Resolve any remaining P0 workflow/test failures before adding scientific
      feature code.

### P0.1 — Scientific Correctness Hardening

Implementation exists for BIG 1, but verification is pending.

- [ ] Add/adjust focused regressions for every changed scientific invariant.
- [ ] Verify removing/replacing evidence cannot increase coverage support.
- [ ] Verify independent-group counting and split isolation.
- [ ] Verify missing observation noise never becomes zero uncertainty.
- [ ] Verify affine-temperature spreads use delta/ratio semantics.
- [ ] Verify oracle levels require typed execution/provenance binding.
- [ ] Verify consensus preserves comparable disagreements.
- [ ] Verify multiphysics windows, participants, events, termination and state chains.
- [ ] Verify replay cannot pass with zero expected outputs.
- [ ] Verify discovery identity binds holdout/result-changing content.
- [ ] Run changed-area compile/tests and `git diff --check`.
- [ ] Run `python tools/forge_check.py --changed` and required scientific tiers.
- [ ] Run the read-only scientific reviewer after tests stabilize.
- [ ] Obtain green CI on the final source head.
- [ ] Verify GitHub rules require `recertification-gate` and `tests-gate`.

### P1 / BIG 2 — Time Engine foundation

Implemented in `src/engcore/scenarios/timeline.py` (tests:
`tests/test_time_engine.py`). Built during the BUILD phase; full tiers NOT RUN.

- [x] Canonical immutable `TimeBasis` (no default clock), `TimePoint`
      (cross-basis ordering refused), `TimeWindow` (half-open/closed,
      empty/inverted refused) and deterministic `Timeline.digest`.
- [x] Typed `TimelineEvent` markers (scheduled/reached synchronization,
      discontinuity, state-change request, termination) with fail-closed
      ordering of order-sensitive events at a shared instant.
- [x] Usage/exposure `QuantityHistory` (gaps are UNKNOWN, integrals over gaps
      UNKNOWN, affine-unit integrals UNKNOWN) and `CycleHistory` (no skipped
      indices, no fractional cycle counts).
- [x] Bound to existing authorities: `Timeline.from_scenario` binds the
      `ScenarioSpecification` digest; `Timeline.bind_run` copies
      `MultiphysicsRunRecord` receipts verbatim and refuses another scenario.
- [x] State transitions reuse `StateTransitionReceipt` (no parallel record);
      the timeline enforces per-participant digest/time chaining and exposes
      state identity only at recorded boundaries (UNKNOWN in between).
- [x] Unsupported interpolation, interpolation mismatch and LINEAR across a
      declared discontinuity are refused.
- [x] `TimelineCheckpoint` binds a prefix digest plus existing
      `CheckpointRecord`s; `compare_replay` refuses empty prefixes and is
      classified `replay_consistency_not_validation`.
- [x] Exact same-instant rule (`SAME_INSTANT_RULE`, rational seconds, no
      epsilon) and scenario-proven input ownership (`input_value_at` takes the
      `ScenarioSpecification`). Re-review: no BIG 3 blocker.
- [ ] Remaining non-blocking BIG 2 gaps: see PROGRESS (BIG 2/3 section).
- [ ] Runtime-side emission: have `MultiphysicsRuntime` produce
      `TimelineCheckpoint`s from its own `_checkpoint_all` and restore from them.
- [ ] Multi-basis / multi-rate timelines (P14 prerequisite): an explicit,
      declared basis-mapping record instead of the current refusal.

### P2 / BIG 3 — Environment Engine

Implemented in `src/engcore/scenarios/environment.py` (tests:
`tests/test_environment_engine.py`). BUILD phase; full tiers NOT RUN.

- [x] Typed, extensible `EnvironmentQuantityKind` registry (13 generic kinds:
      temperature, plane/horizontal irradiance with orientation context,
      humidity, wind speed/direction, precipitation, wetness, chloride,
      particulates, pressure, altitude, gravity). No branching on kind ids.
- [x] `EnvironmentSource` (digest-bound, classified; design assumptions are
      `declared_assumption_not_evidence`), `ReferenceContext`, explicit
      `InterpolationContract` (NONE / STEP_HOLD / LINEAR with required max_gap).
- [x] `EnvironmentChannel` over point samples or the bound timeline's EXPOSURE
      `QuantityHistory` (stored once, in the timeline).
- [x] `EnvironmentState` / `EnvironmentTimeline`: UNKNOWN entries rather than
      omissions; interpolated values labelled and UNKNOWN-uncertainty; no
      extrapolation / gap / discontinuity crossing; overlapping sources refused;
      `dose()` for lifecycle consumers; `verify_state`; deterministic digests.
- [ ] Non-blocking gaps: see PROGRESS (BIG 2/3 section).

### P3 / BIG 4 — Lifecycle / degradation (NEXT BIG step)

Consume `EnvironmentTimeline.dose()` / `state_at()` and `Timeline` usage/cycle
histories; update state through the existing `StateTransitionReceipt` chain.

- [ ] Define generic `LifecycleState` and degradation-model contracts.
- [ ] Separate exposure history, usage history and accumulated damage state.
- [ ] Ensure degradation updates future physics/material state rather than
      existing only as post-processing.
- [ ] Add at least two independent reference degradation families before
      generalizing the API (for example battery aging and material corrosion or
      fatigue).

## Persistent project direction

The long-term roadmap, non-goals, provider strategy, data policy, flagship
systems and session-resume protocol live in:

`docs/project/FORGE_MASTER_PLAN.md`

Do not duplicate or silently replace that strategic direction here. This file
is only the current bounded execution plan.

## Stop conditions

Stop implementation and surface a blocker if a proposed change would require:

- weakening UNKNOWN/fail-closed semantics;
- changing a frozen serialized contract without an explicit version decision;
- inventing measurements, uncertainty, validation, provenance or evidence;
- duplicating an existing scientific identity, timeline, state or authority system;
- adding domain-specific component/state/quantity names to generic Core;
- treating convergence, serialization roundtrip or solver agreement as validation;
- bypassing automatic assurance gates to make a change appear complete.

## Session resume

At a new session, read in this order:

1. `CLAUDE.md`
2. `docs/project/FORGE_MASTER_PLAN.md`
3. this file
4. newest relevant entries in `docs/work/PROGRESS.md`
5. current repository HEAD / branch / PR state

Then continue the first executable unfinished task above.
