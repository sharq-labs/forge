# Forge Work Progress

This file is persistent engineering memory for long-running AI-assisted work.
Keep it concise and factual. Do not use it as a release note or marketing log.

## Current branch / PR

- Branch: `claude/serene-tesla-n7t17w` (from `main` @ `2b76017f`, PR #106 merged)
- PR: none opened; verify GitHub before making a current PR claim.
- Base: `main`
- Strategic contract: `docs/project/FORGE_MASTER_PLAN.md`
- Current execution authority: `docs/work/ACTIVE_PLAN.md`

## 2026-09-25 BIG 6 — Mathematical / Numerical Foundation (BUILD phase; read this first)

### Pre-check
BIG 5 re-review at `05c4b2c`: no numerical blocker; one HIGH path fixed first
(interpolation between ASSUMED points was labelled INTERPOLATED -> now
refused; wrong-dimension conditions are inadmissible instead of raising).

### Architecture
- Existing numerical authority found and reused: `scientific.solvers.protocol`
  (SolverIdentity, SolverSettings, ConvergenceState, RawSolverOutput),
  `scientific.numerics` (health, conditioning, stability),
  `solvers.admission.require_finite`. `engcore.numerical` is a kernel layer
  beneath domain solvers, not a parallel solver framework.
- Environment: numpy 2.4.6, scipy 1.17.1 present; SymPy 1.14.0 installed this
  session (`pip install sympy`) and declared as optional extra `symbolic`;
  `petsc` extra declared (petsc4py not installed). SUNDIALS: contract only;
  a first attempt probed `scikits.odes` and was removed because an unused
  import of an undeclarable distribution tripped the dependency guard and the
  provider would not use it anyway.

### Scientific review
BIG 6 review: CHANGES REQUIRED for one BLOCKER, fixed: LINEAR problem
identity with a declared digest did not hash its arrays (two matrices, one
identity) -> operand digest now always in identity. Also fixed: bridge keeps
failure reason/termination message; objective value no longer mislabelled
as residual; GMRES re-checks true residual; missing tolerance -> typed
refusal before work; minimize tolerances restricted per method; bitwise
determinism claim removed; PETSc preconditioner must be explicit; ODE output
times strictly after start and coverage verified. Not re-reviewed.

### Open non-blocking gaps
- Callable operators (ODE/root/optimization) have declared (attested) identity.
- `NOT_APPLICABLE` direct solves through Core admission are not yet tested end to end.
- Sparse problems > 2000 unknowns report no condition estimate.
- No DAE execution; SUNDIALS/PETSc execution not exercised here.
- Event *detection* (state-dependent events) is not supported; only declared
  breakpoints are bridged.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/numerical src/engcore/materials` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_numerical_foundation.py tests/test_materials_engine.py tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_core_api_layering.py tests/test_min_foundation_electrothermal.py` — PASS, 201 passed
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_core_guards.py -k dependenc` — PASS, 6 passed (earlier FAIL on undeclared `scikits`, fixed as above)
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI, PETSc/SUNDIALS execution.

### Readiness
Linear (3 providers), nonlinear (SymPy operator, 2 methods), ODE (2 methods,
BIG 2 window, BIG 5 material parameter, breakpoint bridging) and optimization
execute through provider-neutral contracts with fail-closed diagnostics.
BIG 7 not started.

## 2026-09-25 BIG 5 — Scientific Data + Materials (BUILD phase)

### Pre-check
BIG 4 re-review at `a2578a6`: PASS WITH NON-BLOCKING GAPS, no materials
blocker. Its MEDIUM items (per-input + state applicability; chain state link)
were fixed inside BIG 5's identity design.

### Architecture decisions
- `scientific.knowledge` is the data authority (claims, sources, snapshots,
  ingestion receipts, supersession). BIG 5 adds no source/claim/dataset record;
  it binds claims to exact material + applicability and resolves them.
- Constitutive models (e.g. `domains/electrical/material.py` R(T)) stay
  `ScientificModelDefinition`; `materials` holds sourced data only.
- Source alignment decision: `KnowledgeSource` is canonical for scientific
  data; `EnvironmentSource` stays an environment-input record. Both are read
  through `SourceIdentity` (a view). A serialized merge is deferred; it would
  change the `environment_source` contract and needs an explicit decision.
- Applicability is identity: `DegradationModelIdentity.applicability` and
  `.state_ranges` are serialized fields, so changing authorization changes
  the digest (replaces the BIG 4 "bounds not in identity" gap).

### Scientific review
BIG 5 review: CHANGES REQUIRED for one HIGH finding, fixed: interpolation
mixed units across tabulated points (now all positions in the state
condition's unit; test with degC/K points). Also fixed: ASSUMED datum now
resolves as ASSUMED, breakpoints dimension-checked at construction. Not re-reviewed.

### Open non-blocking gaps
- No production (non-test) participant yet constructs `MaterialState` and
  calls `resolve`; the closed material loop is proven in tests with a
  reference insulation participant. Domain physics adoption is future work.
- Removing one of two conflicting data turns UNKNOWN into KNOWN (refusal to
  arbitrate); should be reconciled with "removing evidence must not increase
  assurance" via `scientific.knowledge.conflicts`.
- Only single-variable LINEAR interpolation; no multi-variable tables, no
  explicitly authorized extrapolation.
- Fixture data are illustrative (issuer says so); no real open dataset is
  ingested yet (NIST/NASA/PyBaMM providers are future adapters).
- `QuantityHistory.integrate` still labels its bound STANDARD (BIG 2 gap).

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/materials src/engcore/scenarios src/engcore/domains/battery/aging.py src/engcore/domains/corrosion src/engcore/domains/hygrothermal` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_materials_engine.py tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py tests/oracles/test_oracle_battery.py` — PASS, 300 passed
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI.

### Readiness
A material property resolves from exact identity/state/source/applicability
and changes future computation (moisture -> conductivity -> heat flux).
BIG 6 not started.

## 2026-09-25 BIG 4 — Lifecycle / Degradation Engine (BUILD phase)

### Pre-check
`forge-scientific-review` re-run on BIG 2 + BIG 3 at `5584c57`: PASS WITH
NON-BLOCKING GAPS, no lifecycle blocker. Its advice (bind environment digest
in lifecycle records; do not treat SAMPLED as evidence) is built into BIG 4.
Open from it: required-kind placeholders carry empty source/classification
(explicit, but not a named "unsourced" label).

### Architecture
- `engcore.scenarios.lifecycle`: contracts + `evaluate_degradation`,
  `carry_forward`, `LifecycleChain`, `run_lifecycle`. Reuses
  `InitialStateDefinition/Value/Receipt`, `StateTransitionReceipt` end values,
  `MultiphysicsRuntime.run(initial_state=...)`, `Timeline` histories and
  `EnvironmentTimeline`; no new timeline/state/provenance authority.
- `EnvironmentTimeline.window_mean` (interval channels only; affine allowed;
  uncertainty UNKNOWN with the correlation-free bound stated in notes).
- Reference probes (uncalibrated, not validated): `domains/battery/aging.py`
  `CalendarCycleCapacityFade`; `domains/corrosion/thickness_loss.py`
  `LinearDoseThicknessLoss`. Chosen because they differ in drivers (mean
  temperature + cycle count vs. wetness + chloride doses) and state
  (capacity vs. thickness). `domains/**` is outside the certified core; no
  pinned file changed.

### Closed-loop proof (executed)
Three one-day windows through the real `MultiphysicsRuntime`: battery
capacity fades each window and the next window's state-of-charge swing
(2 A * 24 h / capacity) grows accordingly; wall thickness decreases and the
next window's heat flux (k dT / thickness) grows. `LifecycleChain.verify`
confirms every window acknowledged the degraded state.

### Scientific review
BIG 4 review: no BLOCKER; findings fixed: (1) verify ignored uncertainty,
(2) window_mean labelled a bound as STANDARD, (3) empty applicability meant
"everywhere", (4) chains could mix models, (5) executor could run another
window, (6) carry_forward could drop degraded state. Fixes tested; not re-reviewed.

### Open non-blocking gaps
- Applicability bounds are not part of `DegradationModelIdentity`; two models
  differing only in bounds share an identity (found by a failing test).
- `QuantityHistory.integrate` (BIG 2) still labels its correlation-free bound
  STANDARD (notes say UPPER BOUND); `window_mean` now uses UNKNOWN — align.
- Prior state is not range-checked (e.g. non-positive thickness).
- No uncertainty propagation through degradation models (always UNKNOWN).
- Loop is per participant; multi-participant/multi-model lifecycles and
  degradation inside a single long run (sub-window feed-forward) are not built.
- Point-sample channels give no dose/mean by design; lifecycle needs interval data.
- `EnvironmentSource` vs P4 dataset provenance alignment still open.
- Reference probes: linear/window-additive forms, Jensen gap, uncalibrated.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/scenarios src/engcore/domains/battery/aging.py src/engcore/domains/corrosion` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py tests/oracles/test_oracle_battery.py` — PASS, 281 passed
command: `PYTHONPATH=src python -m pytest ... tests/oracles/test_oracle_battery.py tests/test_solver_lifecycle_state_isolation.py tests/test_world_runtime_sprint1.py` — PASS, 130 passed
command: `PYTHONPATH=src python -m pytest ... $(ls tests/test_*battery*.py)` — INVALID: glob matched nothing, pytest collected the whole tree and stopped on 6 known duplicate-basename collection errors (2 skipped). Not a test result.
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI.

### Readiness
Closed loop demonstrated: Time + Environment + Usage/Cycles -> Degradation ->
State transition -> changed future physics. BIG 5 not started.

## 2026-09-25 BIG 2 gap closure + BIG 3 — Environment Engine (BUILD phase)

### BIG 2 gaps closed
- Same-instant: `TimePoint` stores exact rational seconds from
  `repr(magnitude) * repr(unit factor)` (`SAME_INSTANT_RULE`); `0.1 hour ==
  360 s`, `360.0000000000001 s != 360 s`, no epsilon. Known limit (fail-closed):
  non-decimal magnitudes (1/3 hour) do not merge with 1200 s.
- Input ownership: first attempt stored `input_series_digests` on the
  timeline; the re-review showed it was forgeable (any caller could supply a
  digest). **Failed approach, removed.** Now `input_value_at(scenario, ...)`
  recomputes the presented scenario's digest and reads its composed schedule.
- Mistake recorded: removing a helper by slicing to the next `def` deleted the
  `SAME_INSTANT_RULE` block; restored in a follow-up commit.
- BIG 2 re-review verdict: no blocker for BIG 3 after the ownership fix.

### BIG 3 architecture
`src/engcore/scenarios/environment.py` — see ACTIVE_PLAN BIG 3 checklist.
Reuses `Timeline`, `TimePoint`, `TimeWindow`, EXPOSURE `QuantityHistory`,
scenario digest and `NamedQuantity`; adds no clock or state authority.

### BIG 3 scientific review
First review: CHANGES REQUIRED. Fixed: B1 (BLOCKER) LINEAR interpolated across
a discontinuity exactly at the upper sample; N1 circular kinds (wind direction)
now refuse LINEAR; N2 each value carries its source classification; N3
`verify_state` re-derives a deserialized state; N4 `source()` raised
StopIteration. Fixes covered by tests; not re-reviewed.

### Open non-blocking gaps (BIG 2 + BIG 3)
- `required` pairs have no context; a channel in another context satisfies
  coverage (its own value still appears under its context).
- `EnvironmentSource` is a new source-identity record; align with P4 dataset
  provenance/licensing when that lands.
- No interpolated dose from point samples (deliberate); lifecycle needs interval data.
- No spatial interpolation between locations; one timeline basis only.
- Markers-before-order-sensitive precedence at a shared instant is a convention.
- `canonical_digest` duplication (frozen Core decision needed).
- Runtime does not emit/restore `TimelineCheckpoint`s.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/scenarios` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py` — PASS, 228 passed (includes two executable environment scenarios: coastal exposure day, climb profile)
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 40 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI.

### Readiness
BIG 3 produces a deterministic, provenance-bound environmental history
(`EnvironmentTimeline.history/state_at/dose`, digest-bound to scenario,
timeline and sources). Ready to start BIG 4 Lifecycle.

## 2026-09-25 BIG 2 — Time Engine foundation (BUILD phase)

Strategy change: build the big architecture first; only focused smoke checks
during the build. The full FAST / SCIENTIFIC / mutation / recertification
campaign is deferred until after the architecture, real scenarios, a
scientific/numerical review and a stale-test audit.

### Architecture added

`src/engcore/scenarios/timeline.py` (non-Core package `scenarios`, which is
the existing transient authority; nothing new in the frozen Core):

- `TimeBasis` (ELAPSED with a named origin, or ABSOLUTE_UTC with the fixed
  epoch; no default clock), `TimePoint` (cross-basis ordering refused),
  `TimeWindow` (HALF_OPEN = scenario segment ownership, CLOSED for horizons).
- `TimelineEvent` + `order_events`: synchronization markers commute;
  DISCONTINUITY / STATE_CHANGE_REQUEST / TERMINATION at a shared instant need
  explicit distinct sequences or are refused. Events are markers, not evidence.
- `QuantityHistory` (USAGE/EXPOSURE, piecewise-constant only): gaps are
  UNKNOWN; integrals over gaps or affine units are UNKNOWN; the integral
  uncertainty is the correlation-free bound sum(sigma_i*dt_i), labelled an
  UPPER BOUND, source kind carried only when shared.
- `CycleHistory`: indices start at 0 and never skip; counts outside the
  recorded span are UNKNOWN; partial cycles are listed, never fractionally counted.
- `Timeline`: binds a `ScenarioSpecification` digest (`from_scenario`) and one
  `MultiphysicsRunRecord` (`bind_run`, records `run_id`); holds existing
  `StateTransitionReceipt`s verbatim and enforces per-participant digest and
  time chaining; every receipt must carry the timeline's scenario digest.
  `state_at` is KNOWN only at recorded boundaries.
- `input_value_at`: unsupported interpolation, method mismatch and LINEAR
  across a declared discontinuity are refused.
- `TimelineCheckpoint` (prefix digest + existing `CheckpointRecord`s; refused
  inside a record window, at an order-sensitive event, or for a participant
  state the timeline has no record of) and `compare_replay` (refuses a prefix
  with no execution-produced record; classified
  `replay_consistency_not_validation`).

### Scientific review

`forge-scientific-review` (read-only, no tests executed) returned CHANGES
REQUIRED on the first cut. Fixed: (1) scenario/run binding bypass via empty
digests and cross-run mixing; (2) unrecorded time counted as zero cycles;
(3) integral bound mislabelled / promoted to COMBINED; (4) checkpoints for
unrecorded participant state; (5) replay passing on declared-only content and
prefix omitting history kind/unit/cycle kind/horizon end/checkpoints;
(6) checkpoint ambiguity check only in one constructor; (8, partial) reached
event instant not checked against its schedule. The fixes were not re-reviewed.

### Open design gaps (not fixed; record before BIG 3 consumes the timeline)

- Same-instant grouping uses exact float seconds after unit normalization;
  0.1 hour vs 360 s may differ in the last ulp and escape the ambiguity check.
- Markers are sorted before order-sensitive events at the same instant; that
  precedence is a convention, not a declared rule.
- `input_value_at` does not verify the series belongs to the bound scenario.
- `canonical_digest` duplicates `sria/decision/replay.py` and
  `claims/_records.py`; consolidating into `scientific.serialization` touches
  frozen Core and needs a freeze decision.
- The integral treats each entry as exactly constant; representation error is
  not quantified (stated in the uncertainty notes, not modelled).
- The runtime does not yet emit `TimelineCheckpoint`s or restore from them;
  only one basis per timeline (no declared basis mapping / multi-rate).

### Verification (BUILD-phase smoke only)

2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/scenarios`
result: PASS

command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py`
result: PASS — 194 passed (34 in `test_time_engine.py`)

command: `PYTHONPATH=src python tools/forge_check.py --changed`
result: PASS — 40 passed (architecture/layering gate set)

command: `git diff --check`
result: PASS

command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q tests/test_core_freeze_*manifest.py`
result: FAIL — 15 failed, identically on clean `main` @ `2b76017f` (stash
test). Cause: this session's shallow clone lacks historical commits the freeze
verifiers `git show` (e.g. `af43c896`). Environmental, not caused by BIG 2.

NOT RUN: `forge_check.py --regression`, FAST tier, SCIENTIFIC tier, mutation
shards, hardened-core recertification, full repository test suite, CI.

### Next BIG step

BIG 3 — Environment Engine: provider-neutral `EnvironmentState` /
`EnvironmentTimeline` built on `Timeline` + `QuantityHistory(EXPOSURE)`, with
source, units, uncertainty, interpolation and validity bound to every
environmental quantity. Close the timeline gaps above that BIG 3 depends on
(scenario ownership of input series; same-instant tolerance) first.

## 2026-09-25 P0.1 failure triage

`main` @ `deabe5cb` was RED. Read from GitHub Actions (run 36117761308, Tests):
FAST 3.12, FAST 3.11 and SCIENTIFIC each failed the same **54** tests; the
`mutations` job's CONTROL was RED (round void) because of 3 of them; `reproduce`
(Docker) failed 165; `Branch Policy` failed with `POLICY NOT ENFORCED`.

Root causes (all local, none needed a guard weakened):

| Cluster | Tests | Cause | Fix |
| --- | --- | --- | --- |
| predictive/hybrid UQ fixtures | 24 | fixtures declared no observation noise; production correctly refuses it | fixtures declare a noise sigma |
| `float(P.sigma)` | 3 | `P.sigma` is a per-observation vector; current numpy rejects `float()` | `P.sigma[5]` |
| consensus non-finite | 20 | **production regression**: `over()` compared raw values but stored only finite ones, so the record-recompute check raised at construction | see "Consensus decision" below |
| standard uncertainty to an affine target | 1 | **production defect**: propagated spread was stamped in `degree_Celsius`, which the spread rule refuses | carried on the dimension's base unit (kelvin), slope-only conversion |
| exact-identity attribution | 2 | tests attributed by prose/`@` substring, the spoofing path BIG 1 closed | tests name exact identities; new test that prose is refused |
| multiphysics expectations | 3 | one test forged an empty iteration (refused earlier, by the record) and two expected `UnitCompatibilityError` where the port-contract check raises `InvalidScientificProblem` | two-participant fixture; exception class |
| independence-group message | 1 | message reworded to cover calibration/validation/holdout | match updated |
| stability reasons | 3 | `in tuple` where a substring was meant | `any(... in reason)` |
| stale mutation `B48c` | 2 | target line changed to `references` | repointed; same killing test |
| certificate | 2 | `certification/current_core_v2.json` describes an older tree | **not edited**: regenerated only by the CI certify child on 3.12 |

### Consensus decision (recorded so it is not re-litigated)

BIG 1 made a non-finite reading on an *unshared* diagnostic stop erasing a real
finite disagreement, but did it inconsistently. The rule now, for shared and
unshared readings alike: a non-finite reading **never helps routes agree**
(agreement with any non-finite reading present is a "nothing compared" refusal),
**never hides** a disagreement the finite shared readings show (kept, with the
offenders named), is **not a reported output**, and numbers travel with the record
only when **every** reading is finite, so such a record can never be `earned`.
A finite disagreement kept beside a non-finite reading is a FAIL built from a
route the module calls unfinished. That is fail-closed (it can only withhold), and
was chosen over NOT_RUN so a route cannot avoid a FAIL by emitting a NaN. The
scientific reviewer (read-only) required the single-rule fix; it is applied.
Not changed, pre-existing, noted by the reviewer: `to_check` can report PASS for a
comparison with no recomputable numbers (level still withheld); finite extremes
(1e308 vs -1e308) raise instead of recording; `_delta_magnitude_in` re-implements
`Quantity.magnitude_as_spread_in` with ~1e-13 cancellation error.

### Repository-level findings (not code)

- The `Protect main` ruleset (id 23351506, active, no bypass actors) contains
  `deletion`, `non_fast_forward` and `pull_request` (0 approvals) but **no
  `required_status_checks` rule**. `main` therefore does NOT require
  `tests-gate` or `recertification-gate`. Restoring it is a repository-settings
  change and needs the owner's explicit go-ahead; do it only once the gates are green,
  or the fix PR itself cannot merge.
- The Docker `reproduce` job has failed on every `main` push since 2026-09-14
  (`.dockerignore` excludes `.git`, so certification tests find no repository).
  It is outside `tests-gate`; not fixed by this slice.

## 2026-09-25 scientific-correctness hardening handoff

This is the current AI/session handoff. Read it before older progress entries.
The work below is **implemented but NOT RUN/verified** unless a later
verification entry explicitly says otherwise.

### Why this slice exists

After P0 assurance stabilization, the scientific audit exposed false-confidence
and evidence-integrity paths that must be hardened before P1 Time Engine work.
Reproduce each finding against current code, prefer minimal fail-closed changes,
and never weaken UNKNOWN/evidence semantics merely to make tests green.

### Source lineage

The branch received an automatic recertification child at
`26c8b9b01b9d88b78ce526b4b6e50735e26f8b41`, parent
`44885bf01aa4ceafddaaf317ba2569ef1d04a904`.

Scientific hardening was developed as a detached chain from the same source
parent so CI would not restart after every micro-fix:

- `7efa13d792caf6e9d47a0e976437bbb16f83fb77` — evidence monotonicity and run integrity
- `706756c7d4f7b4216859e4e776b2917e171f0c07` — uncertainty/stability false-confidence paths
- `655f20fe69ef8aae22a657b5ed5af56bede7f226` — independent evidence and oracle provenance
- `ab59ec47d5cd0e53f7b84df398431fb930f9dda0` — missing-noise refusal and exact UQ provenance

The current branch merges that detached chain with the certification child
instead of replacing either history. The old certificate child is historical
evidence only; after source changes it does not certify the new head.

### Implemented in BIG 1 — verification pending

1. **Coverage / evidence monotonicity**
   - unresolved/adverse in-domain outcomes block `SUPPORTED`;
   - coverage counts independent evidence groups rather than correlated case copies;
   - one independence group may not cross calibration/validation/holdout roles.

2. **Campaign adequacy / comparison integrity**
   - independent failure without scored calibration evidence becomes
     `INSUFFICIENT_EVIDENCE`, not automatic model-form failure;
   - exact-zero tolerance keeps FAIL semantics without non-finite JSON.

3. **Consensus**
   - unrelated non-finite diagnostics no longer erase a real shared disagreement;
   - shared non-finite values remain unusable evidence.

4. **Multiphysics**
   - composition fingerprint recursion removed and candidate-derived ambiguity enforced;
   - frame transforms must be proper rotations, not reflections;
   - run end cannot exceed plan horizon;
   - termination instant must equal actual end;
   - every iteration must record exactly one step per graph participant;
   - participant steps must span their coupling window;
   - scenario inputs and QoIs are checked against port value/uncertainty contracts;
   - scheduled events inside the executed horizon require reached receipts;
   - state-transition digest chains must remain contiguous.

5. **Replay**
   - zero expected outputs cannot count as verified replay output agreement.

6. **Uncertainty / UQ**
   - STANDARD uncertainty requires a spread/ratio-scale unit;
   - identifiability classification is fixed at 95%;
   - affine-temperature sigma/std conversions use spread semantics;
   - undeclared observation noise cannot silently become zero total uncertainty;
   - non-finite/negative numerical residual evidence follows an explicit refusal path;
   - model-form residual units must be spread units;
   - cross-domain uncertainty attribution uses exact identities, not substring matches.

7. **Oracle / discovery**
   - oracle binding requires a real `ScientificResult`, not duck typing;
   - discovery fingerprints bind candidate id, calibration/holdout RMSE,
     complexity and status;
   - holdout-result statuses require a holdout RMSE.

### Verification status

Superseded by the verification log below and the P0.1 triage above. The BIG 1
gates are **not** closed until the CI run on the final source head is green.
Do not claim PASS, green, verified, validated or certified from static inspection.

### Next executable work

1. Inspect current branch HEAD/diff; do not trust stale chat state.
2. Add/adjust focused regressions for each changed scientific invariant.
3. Run changed-area compile/tests and `git diff --check`.
4. Run `python tools/forge_check.py --changed`, then the required scientific tiers.
5. Diagnose failures without weakening scientifically valid guards to satisfy old tests.
6. Run the read-only scientific reviewer after tests stabilize.
7. Obtain green CI on the final source head.
8. Verify `main` rules require `recertification-gate` and `tests-gate`.
9. Only then start P1 Time Engine.

### Short recovery prompt

`Read CLAUDE.md, docs/project/FORGE_MASTER_PLAN.md, docs/work/ACTIVE_PLAN.md and docs/work/PROGRESS.md. Inspect the current feat/scientific-correctness-hardening HEAD and continue from the first unfinished scientific-correctness task. Treat NOT RUN as unverified; do not weaken scientific guards or change direction without repository evidence.`

## Completed in this line of work

- Added the persistent Forge Master Plan as the long-term project operating
  contract, including session recovery, roadmap precedence, solver/provider
  strategy, data policy, Time/Environment/Lifecycle pillars and flagship systems.
- Updated `CLAUDE.md` so every new agent/session reads the Master Plan before
  selecting work, and removed the obsolete manual-only CI policy.
- Reframed `ACTIVE_PLAN.md` around P0 assurance stabilization followed by
  Time, Environment and Lifecycle foundations.
- Restored automatic Tests and hardened-core recertification workflows on pull
  requests, retained manual fallback, made V4 mutation shards explicit
  certification prerequisites, fixed the assurance-builder CLI invocation and
  completed the declared Docker test/benchmark dependency set.
- Automatic workflow runs were triggered on PR #102 after these changes.
  Their final scientific/test result must be read from GitHub Actions before
  any PASS/green claim is made.

- Added deterministic hierarchical system/component topology bound to existing
  `ScientificTwin`, `PortDefinition`, `PhysicsGraph` and `CouplingEdge`
  authorities. Structural topology is bound through authorized execution;
  unconsumed parameter/state/constraint bindings fail closed.
- Routed window-aligned STEP scenario inputs through the live multiphysics
  runtime without reinitializing participant state; consumed values are
  receipted per window. Unsupported interpolation/features and schedule-less
  replay fail closed.
- Added immutable, unit-bearing, digestible generic scenario contracts with
  strict timeline, state, interpolation and wire-shape validation.
- Added additive GraphPlan v3 scenario binding. Authorized execution currently
  accepts timing-only scenarios and fail-closed refuses every material
  scenario field until runtime consumption and receipts are implemented.
- Removed battery/electrical/thermal realization and solver imports from
  `planning.production`; enabled validated Domain Packs are now the sole
  production source for these artifacts, with existing fail-closed identity
  collision checks retained.

- Extracted credibility/V&V implementation from MCP transport into
  `engcore.credibility`.
- Removed the `claims -> mcp` implementation dependency.
- Added compatibility shims for old MCP credibility imports.
- Grouped claim analysis, governance, replay and NL adapter implementations
  under subpackages while preserving old import identity.
- Added a current architecture entry point and historical-audit index.
- Added persistent Claude/agent working contract, scientific reviewer,
  regression manifest and fast changed-file gate.
- Added trust-registry change detection to impact analysis.
- Strengthened replay bundles with source/runtime environment fingerprints.
- Renamed sprint-phase claim tests by scientific feature.
- Added `tools/forge_impact.py` for dependency and reassessment queries.
- Added the Scientific Diagnostic Engine: blocking-cause classification, explicit assumption registry, model-data discrepancy diagnostics, corrective actions and sensitivity-ranked repair hypotheses.
- Added `tools/forge_diagnose.py`; diagnostics remain derived/non-authoritative and cannot alter verdicts.
- Hardened diagnostics: raw assessments are re-derived before diagnosis; custom-trust assessments require replay bundles; sensitivity/robustness artifacts are sealed and bound to assessment/plan/capability identity.
- Hardened impact drift: current oracle trust/digest changes and removed policy profiles now trigger reassessment.
- Strengthened replay source identity with tracked-diff and untracked-content digests.

## Verification log

2026-09-25 13:00 EDT
command: `python -m pytest -m "not expensive" -q -n 4` (Python 3.14, worktree D:/forge-p01, HEAD 46cf014b)
result: FAIL (expected baseline + 1 mine)
summary: 11 failed, 8407 passed, 8 skipped. Failures: 2 certificate tests (stale `current_core_v2.json`, CI certify child owns it); 6 freeze/API-surface tests (`test_r69...`, `test_a_descendant_that_keeps_the_contract_still_verifies`, `test_core_freeze_v4_is_the_contract_that_binds_on_this_tree`, 3 in `test_core_freeze_v4_manifest.py`) which fail IDENTICALLY on a pristine `origin/main` worktree under 3.14 (baseline artifact; CI 3.12 passes them); 2 fresh-process digest tests (pass with `PYTHONPATH='D:\\forge-p01\\src;D:\\forge-p01'`); `test_consensus_completeness_grows_linearly_with_required_outputs` (mine: an O(n^2) list membership, fixed in 63b94a3c).
commit: 46cf014b

2026-09-25 13:10 EDT
command: `python -m pytest -q tests/test_consensus_integrity.py tests/test_core_invariants_adversarial.py tests/test_core_numerical_integrity.py tests/test_trust_boundary_consensus.py tests/test_cross_solver_consensus.py tests/test_core_performance_guards.py tests/test_trusted_consensus_gate.py tests/test_audit_consensus*.py -n 4`
result: PASS
summary: 269 passed (before the 3 new regression tests); then tests/test_consensus_integrity.py 26 passed and tests/test_cross_domain_uq.py 13 passed after adding regressions
commit: 63b94a3c (+ working tree tests)

2026-09-25 12:50 EDT
command: `python -m pytest -q -n 4 <the 54 test ids that failed on main>` (Python 3.14)
result: PASS except the 2 certificate tests
summary: 52 of the 54 pass after the batch; the 2 remaining are `test_core_certificate.py::test_the_certificate_describes_this_tree` and `::test_the_certificate_records_the_v1_relationship_truthfully`, which need the CI certify child
commit: 46cf014b

2026-09-25 (GitHub Actions, read, not executed here)
command: Tests run 36117761308 on `main` @ deabe5cb; Recertify run 36114967466 on PR #105 head 5026b40b
result: FAIL
summary: Tests: 54 failed in FAST 3.12 / FAST 3.11 / SCIENTIFIC, mutations CONTROL RED, reproduce 165 failed, Branch Policy `POLICY NOT ENFORCED`. Recertify @ 5026b40b: regression312 and campaign312 SUCCESS; fast311/fast312/scientific312, formal_mutations_0..3, v4_mutations_0..7 FAILED (every V4 shard CONTROL RED with 2-3 failures; shard 0 also B48c NOT_APPLIED); trust_mutations SUCCESS; certify skipped.
commit: deabe5cb / 5026b40b

2026-09-23 19:05 +03:00
command: GitHub Actions PR #102 — Tests run 323 / Recertify Hardened Core run 205
result: FAIL
summary: normal Tests workflow passed; hardened recertification reached the heavy gates, but campaign312 and regression312 failed during pytest collection because duplicate test basenames were imported with legacy import semantics. Updated the recertification workflow so campaign uses --import-mode=importlib and regression sets PYTEST_ADDOPTS=--import-mode=importlib. New head: ddd358c72f9cd5d95cd41835de54dbc03ee17db9.
commit: ddd358c72f9cd5d95cd41835de54dbc03ee17db9


2026-09-21 11:07 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_system_topology.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py; git diff --check`
result: PASS
summary: 21 passed; topology hierarchy/identity/graph bijection and authorized roundtrip pass, while unsupported bindings and impossible constraints refuse; independent scientific review verdict PASS
commit: f1e32ac1 (working tree changes)

2026-09-21 11:00 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/execution; git diff --check`
result: PASS
summary: 26 passed; runtime consumes and receipts window-aligned STEP inputs, while authorized electrothermal execution refuses them under its static-input applicability rule; independent scientific review verdict PASS
commit: 440a8165 (working tree changes)

2026-09-21 10:56 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/scenarios src/engcore/planning/records.py src/engcore/execution/multiphysics/runtime.py src/engcore/assembly/multiphysics.py; py -3 -m pytest --import-mode=importlib -q tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/execution tests/scientific/replay_core/test_run_replay_v2.py; git diff --check`
result: PASS
summary: compileall passed, 31 tests passed, and diff whitespace validation passed; STEP scenario values are consumed and unsupported replay/features refuse
commit: 440a8165 (working tree changes)

2026-09-21 10:54 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py; git diff --check`
result: PASS
summary: 14 passed; scenario contracts round-trip, timing-only scenarios bind through authorized execution, and unsupported material scenario fields are refused
commit: bec4ac58 (working tree changes)

2026-09-21 10:35 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/planning/production.py; py -3 -m pytest --import-mode=importlib -q tests/test_multidomain_science_hardening.py tests/mcp/test_planning.py tests/mcp/test_intent.py; git diff --check; git status --short`
result: PASS
summary: compileall passed, 22 tests passed in importlib mode, and diff whitespace validation passed; status showed only this slice plus pre-existing untracked agent metadata
commit: 72ac242c (working tree changes)

2026-09-21 10:34 +03:00
command: `$env:PYTHONPATH='src'; py -3 tools/forge_check.py --changed`
result: FAIL
summary: collection stopped on 7 pre-existing duplicate test-module basename import mismatches (`test_verify`, `test_serialization`, `test_lineage`, `test_psd`)
commit: 72ac242c (working tree changes)

2026-09-21 10:33 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_multidomain_science_hardening.py tests/mcp/test_planning.py tests/mcp/test_intent.py`
result: PASS
summary: 22 passed; production realization/solver assembly is Domain-Pack-owned and the authorized multiphysics planning path remains operational
commit: 72ac242c (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_numerical_reliability.py tests/test_multidomain_science_hardening.py tests/domainpacks tests/domains/battery/test_battery_solver.py`
result: PASS
summary: 51 passed; numerical-health contradictions are refused and the atomic battery production Domain Pack is frozen/registered
commit: 979e9159 (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest --import-mode=importlib -q tests/test_numerical_reliability.py tests/test_multidomain_science_hardening.py tests/domainpacks tests/domains/battery/test_battery_solver.py`
result: FAIL
summary: battery solver test collection cannot resolve its sibling helper `battery_cases` under importlib mode; the same suite passes in the repository's normal import mode
commit: 979e9159 (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m tools.certification.core_freeze --verify; py -3 -m tools.certification.core_freeze_v2 --verify; py -3 -m tools.certification.core_freeze_v3 --verify`
result: FAIL
summary: historical freeze verifiers fail on the already-drifted live API/serialization and stale certificates; V2 also aborts on a hardened Hybrid UQ fixture, while dirty-tree checks additionally report the current worktree
commit: 979e9159 (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/domainpacks/builtin_battery.py src/engcore/scientific/numerics/health.py; py -3 -m pytest -q tests/test_numerical_reliability.py tests/test_multidomain_science_hardening.py tests/domainpacks tests/domains/battery/test_battery_solver.py tests/test_domain_pack_extension_binding.py; git diff --check`
result: PASS
summary: compileall passed, 57 tests passed, and diff whitespace validation passed
commit: 979e9159 (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/mcp/test_intent.py tests/test_multidomain_science_hardening.py`
result: PASS
summary: 16 passed; production fidelity selection and immediate unit grounding regressions passed
commit: 9143516e (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 tools/forge_check.py --changed`
result: FAIL
summary: collection stopped on 7 pre-existing duplicate test-module basename import mismatches (`test_verify`, `test_serialization`, `test_lineage`, `test_psd`)
commit: 9143516e (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest --import-mode=importlib -q tests/mcp/test_intent.py tests/mcp/test_planning.py tests/test_multidomain_science_hardening.py tests/test_design_d0_contracts.py`
result: PASS
summary: 25 passed
commit: 9143516e (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/mcp/intent.py src/engcore/planning/production.py; py -3 -m pytest --import-mode=importlib -q tests/mcp/test_intent.py tests/mcp/test_planning.py tests/test_multidomain_science_hardening.py tests/test_design_d0_contracts.py tests/test_design_d1_evaluation_archives.py tests/test_model0r_realization_foundation.py; git diff --check`
result: PASS
summary: compileall passed, 145 tests passed, and diff whitespace validation passed
commit: 9143516e (working tree changes)

Status: targeted changed-area tests pass; the repository changed-file gate is
blocked by duplicate test-module basename collection errors recorded above.

Environment note (2026-09-19): attempts to access the branch from the
assistant's local execution container were blocked before checkout because that
container could not resolve `github.com`. The latest hardening verification attempt
ran `git clone ... && python -m compileall -q src tools tests`, but clone failed first
with `Could not resolve host: github.com`; therefore compileall and pytest did not run.
This is not a test result and the status remains NOT RUN.

When a command is executed, append entries in this exact shape:

```text
YYYY-MM-DD HH:MM TZ
command: <exact command>
result: PASS | FAIL | BLOCKED
summary: <counts or first relevant failures>
commit: <sha>
```

Never convert NOT RUN into PASS based on code inspection.

## Failed approaches / dead ends

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 tools/forge_check.py --changed`
result: FAIL
summary: collection stopped on the 7 known duplicate test-module basename import mismatches (`test_verify`, `test_serialization`, `test_lineage`, `test_psd`); no changed-area test failure was produced
commit: 531a104a

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/scientific/multiphysics src/engcore/execution/multiphysics src/engcore/scenarios src/engcore/planning src/engcore/assembly; py -3 -m pytest --import-mode=importlib -q tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py; git diff --check`
result: PASS
summary: compileall passed, 138 tests passed, and diff whitespace validation passed for typed scheduled/reached synchronization receipts
commit: f61a40a8 (working tree changes)

Scientific review milestone: the first scheduled-event review returned CHANGES
REQUIRED because requested controls were stored under `final_outputs`, where
they could be mistaken for calculated results. The corrected design uses
dedicated typed requested/reached synchronization records, exact boundary
indices and the authorized scenario digest; the read-only reviewer then
returned PASS. Neither review executed tests or constitutes validation.

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/scientific/multiphysics src/engcore/execution/multiphysics src/engcore/scenarios src/engcore/planning src/engcore/assembly; py -3 -m pytest --import-mode=importlib -q tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py; git diff --check`
result: PASS
summary: compileall passed, 133 tests passed, and diff whitespace validation passed for the first corrected initial-state implementation
commit: 374c709f (working tree changes)

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest --import-mode=importlib -q tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py; git diff --check`
result: PASS
summary: 135 tests passed after adding fail-closed rejection for unknown state owners and dimensionally incompatible state uncertainty; diff whitespace validation passed
commit: 374c709f (working tree changes)

Scientific review milestone: the read-only `forge-scientific-review` reviewer
returned PASS for the corrected initial-state slice. The review did not execute
tests and is not a validation result. The accepted design requires a declared
participant state schema, exact values with existing uncertainty records, a
participant-produced receipt, dedicated run-record provenance, applicability
evaluation and fail-closed replay.

- Rejected an optional `initialize_state` callback that inferred state support
  from callback presence and let the runtime synthesize its own receipt. A
  no-op callback could acknowledge a requested state without installing it.
  The uncommitted implementation was removed. The next design must include a
  participant-declared state schema, state uncertainty, a typed participant
  acknowledgement/resulting-state identity, applicability evaluation, and a
  dedicated run-record receipt before initial state may enter authorization.

Record failed experiments here with the reason they failed before trying a new
approach. Do not delete old failed approaches merely because a later approach
works.

## Open structural follow-ups

- Manually run `python tools/forge_check.py --changed` on PR #65.
- Run FAST and SCIENTIFIC tiers before merge.
- Split the still-large `mcp/problem.py` in a separate structural slice.
- Continue reducing the remaining flat claim modules only after PR #65 is
  verified.
- Do not expand the frozen Scientific Core for repository-layout aesthetics.
