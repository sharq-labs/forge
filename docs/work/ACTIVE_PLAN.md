# Active Plan

Purpose: keep the current Forge execution slice bounded, resumable and aligned
with `docs/project/FORGE_MASTER_PLAN.md`.

## Current objective

Complete **P0.1 — Scientific Correctness Hardening**, verify the full BIG 1
batch, and only then begin the first bounded **Time Engine** slice.

## Current branch / PR

- Branch: `fix/p0-1-scientific-correctness-hardening` (from `origin/main` @ `deabe5cb`)
- PR: none recorded yet; verify GitHub before making a current PR claim.
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

### P1 — Time Engine foundation

Start only after P0/P0.1 have a trustworthy integration path.

- [ ] Define canonical immutable `TimePoint`, `TimeWindow` and timeline identity.
- [ ] Define typed event, usage, exposure and cycle-history contracts.
- [ ] Bind time contracts to the existing scenario/transient authority rather
      than creating a parallel timeline system.
- [ ] Define explicit state-transition records: requested state change,
      producing authority, resulting state identity and provenance.
- [ ] Add fail-closed handling for unsupported interpolation, discontinuities
      and missing time bases.
- [ ] Add deterministic serialization/digest/replay tests.

### P2 — Environment foundation

- [ ] Define provider-neutral `EnvironmentState` / `EnvironmentTimeline`.
- [ ] Support declared solar, ambient temperature, humidity, wind, rain/water,
      salt/chloride, dust/sand, pressure/altitude and gravity/body-force inputs.
- [ ] Keep source, units, uncertainty, interpolation and validity bound to every
      environmental quantity.
- [ ] Ensure environmental history is consumable by domains without adding
      domain-specific branches to Scientific Core.

### P3 — Lifecycle / degradation foundation

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
