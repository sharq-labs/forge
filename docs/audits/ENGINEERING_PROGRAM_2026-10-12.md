# Engineering, performance and scientific-integrity program — 2026-10-12

**Historical snapshot** (see [README.md](README.md)). Source: `origin/main` `2d0fa6c3` (PR #117 merge, after the
PR #129 test-runtime merge). Work was done in an isolated local worktree on branch
`perf/engineering-program-2026-10-12`; the shared checkout (`main` @ `a3f757eb`, 1,300+ commits behind `origin/main`,
with uncommitted `ACTIVE_PLAN`/`PROGRESS` edits and an untracked review file) was not touched. Nothing was pushed,
merged or recertified.

Environment: Windows 11 Pro 10.0.26200, Intel Family 6 Model 183, 24 logical CPUs, CPython 3.14.2 (GIL enabled),
numpy 2.5.2, scipy 1.18.1, pint 0.25.3. CI interpreters 3.11 / 3.12 are not installed here: **NOT RUN** on them.

Contents: 1 Engineering audit · 2 Performance findings · 3 Scientific integrity · 4 Implementation summary ·
5 Remaining roadmap · 6 Verification record.

---

## 1. Engineering audit

### 1.1 Inventory

| Component | Existing implementation | Status | Problem | Evidence | Action |
|---|---|---|---|---|---|
| Changed-file test selection | `tools/forge_check.py` | DEFECTIVE → fixed | Read only `base...HEAD`: staged, unstaged and untracked edits were invisible; any `src/engcore/` path outside 20 hand-mapped prefixes (units, systems, product, inference, execution/sweep, authority, providers, …) and `pyproject.toml` / `tests/conftest.py` / the manifest selected **zero** of the 133 regression cases; renames reported only the new name; changed test modules were not run | an uncommitted edit to `scientific/units/quantity.py` printed no changed file and selected only the 6 architecture tests | §4 C-1 |
| Model selection | `claims/selection.py` | DEFECTIVE → fixed (D1); PARTIAL (D2, D3) | D1: a candidate with **no active model** stayed VIABLE (UNKNOWN) and was SELECTED as sole survivor, although the module rule rejects candidates whose applicability can never be established | independent read-only review + two tests that fail on `2d0fa6c3` | §4 C-2; D2/D3 in §5 |
| Parameter UQ (propagation) | `claims/uq_studies.py::_propagation`, `parameter_uq.py` (Wilks 95/95, n ≥ 93, `MAX_SAMPLES` 4096) | COMPLETE (scientifically); parallelism NOT JUSTIFIED | none found; every unusable sample makes the channel UNKNOWN; seeded draws re-derived on verify | measured §2.2 | DEFERRED with evidence |
| Numerical refinement | `uq_studies.py::_refinement`, `numerical_uq.py` | COMPLETE | 3 declared levels, level-0 must reproduce the reported value | T3 study = 4 executor calls, ~75 ms warm | DEFERRED (nothing to gain) |
| Robustness envelope | `claims/analysis/sensitivity.py::robustness_envelope` | DEFECTIVE → fixed | (a) `resolution` unvalidated and unbounded; bisection re-ran **identical** inputs once the bracket fell below float resolution; (b) a non-perturbable `parameters` name was silently dropped (sensitivity refuses the same input); (c) the record did not state that the claim is checked only at probes | `resolution=500`: 1,003 solves of which 102 distinct inputs (§2.3) | §4 C-3 |
| Validity-boundary challenge | `claims/analysis/challenge.py::_validity_stress` | DEFECTIVE → fixed | (a) a declared range that could not be stressed was skipped with no record; (b) range edges in the distribution's unit were compared with envelope inputs in the stated unit (degC vs K → wrong side, wrong edge); (c) **false SURVIVED**: "support holds across the declared range" was reported when the 0.95 search cap stopped short of an edge, or when the failure bracket straddled it; (d) a negative stated value was judged against the wrong edge | review finding L3 + follow-up review; four new tests | §4 C-3 |
| Decision impact / reassessment | `claims/analysis/impact.py` (`DecisionGraph`, `detect_changes`, `impact_of`) | PARTIAL → improved | historical/impact/reassessment already separated; UQ study trust registries (`empirical_trust_registry_digest`, `qualification_trust_registry_digest`) were neither graph nodes nor drift-detected, so a change there scheduled nothing although `verify_study_records` would refuse the record | new parametrized test | §4 C-4 |
| Provider process isolation | `providers/process.py::ProcessWorkspace` (6 providers) | DEFECTIVE on Windows → fixed | on timeout Windows killed only the direct child; a descendant holding the pipes kept `communicate()` blocked — a 2 s timeout returned after **60 s** (the descendant's lifetime) | new test on this machine | §4 C-5 |
| Other subprocess launches | ngspice (WSL), discovery `run_provider`, preCICE, blindfold `run_discovery`, health probes | PARTIAL | no tree kill; unbounded capture; preCICE temp dir never removed; `blindfold/isolation.py::run_discovery` blocks in `stdout.read()` before `wait(timeout)` (Linux-only path); `dakota -version` has no timeout | provider inventory | §5 |
| Parallel execution | `execution/sweep.py::run_sweep` (ThreadPool, `workers` ≥ 1, FAIL_FAST refused with workers > 1) | COMPLETE | only pool in `src/` | — | none |
| Caches | units `lru_cache` (cleared by `clear_unit_caches`), multiscale fast-result cache keyed by full `FastExecutionRequest.identity`, provider status cache | COMPLETE (no unsafe scientific reuse found) | `consensus.canonical_component_identity` `lru_cache` never re-resolves; hit path of the multiscale cache skips post-checks only for a result that already passed them under the same key | provider inventory | none; noted |
| Execution budgets | `execution/orchestration` (`ExecutionBudget`, `ResourceBudget`, post-hoc), `MAX_SAMPLES`, red-team budget, hybrid-UQ multistart | PARTIAL | robustness envelope had no effective bound (fixed: float-resolution stop); sweep has no budget | — | §4 C-3; §5 |
| Solver profiling | `benchmarks/performance/run_suite.py`, `docs/performance/core-performance.md`, `tools/certification/performance_telemetry.py` | COMPLETE | — | — | ALREADY SATISFIED |
| Conservation / invariants | `scientific/conservation.py` (`ConservationBalance` → FAIL check → NOT_SUPPORTED), domain checks (KCL, power balance, lumped balance, coulomb balance, CSTR admissibility), multiphysics `_audit_conservation` | PARTIAL | `systems/products/drone_coupled.py::coupling_balances` reports residuals as bare numbers (no tolerance, no check); thevenin, throughput fade, conduction 1D/2D, NAFEMS T3, `systems/electrothermal/coupled.py` carry no balance check | flagship inventory | §3.1, §5 |
| Cross-solver independence | `scientific/consensus.py` (5 independence dimensions, pinned dependency declarations), `independence_evidence.py`, `verification/dependencies.py`, `providers/compare.py` | COMPLETE | `CROSS_SOLVER_VALIDATED` sits in `VERIFICATION_LEVELS`, never `VALIDATION_LEVELS` | — | ALREADY SATISFIED |
| Uncertainty vocabulary | `UncertaintySource`, `UncertaintyChannel`, `uq/budget/source.py`; SRIA budget reports undeclared channels as UNKNOWN | PARTIAL | three vocabularies; no operating-condition member; `uq/budget` aggregation of an empty component list is 0 | flagship inventory | §5 (not changed: a vocabulary change is a design decision) |
| Checkpoint / replay | `system_runtime/checkpoint.py`, `multiscale/checkpoint.py`, SRIA campaign V3, `system_runtime/replay.py` (identity / bitwise / numerical tolerance separated) | COMPLETE | system result digest hashes `wall_seconds` (known, PROGRESS) | — | ALREADY SATISFIED; known gap kept |
| Certification | `certification/current_core_v2.json` | DRIFT (pre-existing) | binds `3e396bc4`, not `main` (ACTIVE_PLAN, OD-3) | FAST baseline §6 | BLOCKED: owner-run recertification |
| Dependencies | `pyproject.toml` | COMPLETE | `scikit-learn` declared, imported nowhere — already documented and pinned by `tests/test_core_guards.py::test_a_declared_dependency_nothing_imports_is_recorded_rather_than_assumed` | — | ALREADY SATISFIED (removal is an owner packaging decision) |

### 1.2 Architectural findings

* Layer direction holds for every change here: nothing in `claims` imports `mcp`; `providers/process.py` stays transport.
* `tools/forge_check.py` is inside the hardened certificate's scope (`tools/certification/core_certificate.py:171`).
  Its `--regression` path — the one the certificate child runs — is unchanged in behaviour, but the file's bytes
  changed, so the next hardened recertification must cover it (OD-3).
* `src/engcore/claims/**`, `src/engcore/providers/**` are outside the certified scope.

---

## 2. Performance findings

### 2.1 Method

Bounded workloads on the production registry, run with `python -I` against the worktree (import path asserted),
warm-up excluded, 3 repetitions unless stated. Executor calls counted by wrapping each declaration's executor. Peak
working set from `psutil`. Measurement scripts (kept outside the repository so they cannot trip the dependency guard):
`D:/forge-perf-bench/bench_uq.py`, `bench_robust.py`, `bench_parallel.py`.

### 2.2 UQ studies — baselines, and why no parallelism was added

| Workload | Executor calls | Wall (warm) | Parent CPU | Peak WS | Verdict | Assessment digest (16) |
|---|---:|---:|---:|---:|---|---|
| ET claim + EPISTEMIC_PARAMETER (93 Wilks samples) | 94 | 1.03 / 1.13 s | 0.97 / 1.09 s | 210 MB | supported | `e961bda4cd4ca6e0` |
| T3 claim + NUMERICAL (3-level ladder) | 4 | 0.077 / 0.075 s | 0.06 / 0.08 s | 200 MB | supported | `74f451522b536e6f` |

Profile of the propagation (cProfile, 2.84 s under instrumentation): `run_electrothermal_case` 2.69 s cumulative over
94 calls; fixed-point coupling 1.22 s; lumped validity context 0.62 s; DC solve 0.48 s; 12,126 pint `Quantity`
constructions and 8,084 `parse_units` calls. The per-sample cost is framework, not numerics — as
`docs/performance/core-performance.md` already found.

Parallel fan-out of the same 93 seeded variants:

| Option | Measured | Result identity |
|---|---|---|
| sequential | 0.952 – 0.962 s | reference |
| `ThreadPoolExecutor(4)` | 0.919 – 0.970 s (no gain: GIL enabled) | identical (run id, value, usable) |
| process pool | one Windows worker cold start (spawn + import + `production_registry()`) = 1.82 – 2.01 s | not built |

A process worker costs about twice the whole sequential study before it runs a sample. Registries can hold lambdas
(`product/cstr.py:378`) and executors are not declared process- or license-safe, so a pool would also need a new
picklability/safety contract. **Decision: DEFERRED.** It becomes worth building only for a capability whose single
solve takes seconds (an external FEM/CFD provider) *and* that declares EPISTEMIC_PARAMETER; none does today.
Refinement (4 calls, 75 ms) has nothing to gain.

### 2.3 Robustness envelope

ET example claim, `parameters=(ambient_temperature,)`:

| `resolution` | Before: solves (distinct inputs) | After: solves (distinct) | Before wall | After wall | Boundaries |
|---:|---:|---:|---:|---:|---|
| 6 (default) | 15 (15) | 15 (15) | 0.134 s | 0.143 s | identical (kinds, `last_holding`, `first_not_holding`) |
| 500 | 1,003 (102) | 102 (102) | 8.43 s | 1.04 – 1.13 s | identical to the last bit (`335.83020286548805` / `335.8302028654881`; `240.0` / `239.99999999999997`) |

At the default resolution nothing changes; the early stop only removes solves of an input already run. Memory: NOT
MEASURED separately (the workload holds no large arrays).

### 2.4 Provider timeout (correctness, measured)

`ProcessWorkspace` with a 2 s timeout around a step whose grandchild sleeps 60 s holding the inherited pipes:
**before 60.08 s** (the timeout bounded nothing), **after** the whole `tests/test_provider_boundary.py` module
(30 tests including this one) ran in 6.6 s; the grandchild is gone afterwards (`psutil.pid_exists`).

### 2.5 Developer gate

`tools/forge_check.py --changed --base origin/main --workers 4` on this branch: 324 passed, 1 skipped (pre-existing
symlink-privilege skip) in 13.6 s. It now selects the whole pack for this diff because `providers/process.py` and
`tools/forge_check.py` are unclassified — correct, and printed as such.

---

## 3. Scientific integrity

### 3.1 Conservation and invariants

| Where | Kind | On violation |
|---|---|---|
| `scientific/conservation.py::ConservationBalance` | verified numerically | FAIL check → verdict NOT_SUPPORTED |
| multiphysics `_audit_conservation` | verified numerically | recorded diagnostic; missing edge raises |
| `system_runtime/assess.py::ConservationAssessment` | diagnostic | "conservation_diagnostic_not_validation" |
| electrical DC (KCL, power balance), lumped balance, coulomb balance, CSTR admissibility | verified numerically | typed `ValidationCheck` |
| `EnergyConversion` declaration | by construction | `InvalidScientificProblem` |
| `drone_coupled.coupling_balances` | **reported, not checked** | none — needs a declared tolerance (scientific decision) |
| thevenin, throughput fade, conduction 1D/2D, NAFEMS T3, `systems/electrothermal/coupled.py` | not checked | — |

No universal invariant was invented. Adding the drone balance check needs a justified tolerance; recorded in §5.

### 3.2 Applicability, verification, validation

* Selection: OUTSIDE excluded; UNKNOWN never treated as IN_DOMAIN (identity comparisons only); ties are AMBIGUOUS,
  never ranked; IN_DOMAIN outranks UNKNOWN and is recorded as OUTRANKED. Fixed: a modelless candidate is now
  REJECTED (`VALIDITY_UNASSESSABLE`). Open: D2 (NOT_ASSESSABLE never surfaced by the compiler — stays UNKNOWN, so no
  false support), D3 (array-section mismatch hides an OUTSIDE value — fails closed), calibration / parameter-set
  validity is not checked by selection.
* Verification ≠ validation is enforced by the level vocabulary (`CROSS_SOLVER_VALIDATED` is a verification level).

### 3.3 Uncertainty and evidence

* Missing UQ stays UNKNOWN in every studied path (unusable sample → UNKNOWN; level 0 must reproduce the run).
* The robustness envelope now records that it checks the claim only at its probes.
* Impact analysis now schedules reassessment when a UQ study's trust registry moves. Historical records are never
  edited; the report only lists reassessment.

### 3.4 Refusals

New refusals: robustness `resolution` that is not a non-negative int; robustness `parameters` naming a non-perturbable
input (consistent with `sensitivity_study`); a modelless capability as evidence bearer. New explicit records instead
of silence: NOT_ATTEMPTED validity-boundary challenges.

Removed false confidence: a validity-boundary challenge used to report SURVIVED ("support holds across the declared
range") for a TCR range of 1 %–199 % of nominal although the probes stop at 95 % of the nominal on both sides; it is
now INCONCLUSIVE and names both unexamined edges. A range written in degC around a stated kelvin value used to be
judged against raw degC magnitudes (WEAKENED for the wrong side, "domain_ends at 239.6" against an edge of −13.15);
it is now judged in kelvin and names the real failure (`increase: fails_beyond` near 336 K inside [260, 340] K).
Edge-exact failures (`first_not_holding` one rounding beyond the edge) used to fall to "not inside"; they now weaken.
For a negative stated value the `decrease` side moves toward `hi`; the old code compared it with `lo`, so such a range
could never be judged reached.

---

## 4. Implementation summary

| ID | Improvement | Initial Status | Changes Made | Tests | Performance | Scientific Risk | Final Status |
|---|---|---|---|---|---|---|---|
| C-1 (P0.8) | Changed-file selection | DEFECTIVE | `tools/forge_check.py`: rule table; unclassified `src/engcore/**` and config files → whole pack (printed); working tree included by default, `--committed-only` opt-out; renames report both names; deletions reported; changed test modules run; `--regression` unchanged | `tests/test_forge_check.py` +15 (all 15 fail on `2d0fa6c3`) | gate 13.6 s for this diff | none to verdicts; certified-scope file → needs recertification (OD-3) | COMPLETED |
| C-2 (P0.4) | Modelless candidate cannot bear evidence | DEFECTIVE | `selection.py`: `VALIDITY_UNASSESSABLE` rejection when no model is active | `test_claims_selection.py` +2 (both fail on base) | n/a | tightening only; production capabilities all have always-active models, so no production selection changes | COMPLETED |
| C-3 (P0.7, P1.3) | Robustness envelope bounds and honesty; no support inferred outside the evaluated envelope | DEFECTIVE | `sensitivity.py`: resolution validation, refusal of non-perturbable names, float-resolution early stop, probe-spacing assumption. `challenge.py`: NOT_ATTEMPTED instead of silent skip; edges converted to the stated unit; an edge not reached by a holding probe → INCONCLUSIVE (never SURVIVED); an edge-exact failure counts as inside; negative stated values judged against the edge each side moves toward (`_side_against_range`) | `test_sensitivity_robustness_challenge.py` +11: 9 fail on `2d0fa6c3` by behaviour; the 2 helper tests fail there by ImportError (the helper is new), their behavioural difference is argued in §3.4 | `resolution=500`: 1,003 → 102 solves, 8.43 → ~1.1 s; default unchanged | removes a false SURVIVED; envelope digest changes (new assumption string) — no stored envelope or challenge record found | COMPLETED |
| C-4 (P1.1) | Reassessment on UQ trust-registry drift | PARTIAL | `impact.py`: TRUST_REGISTRY edges for study trust digests; `detect_changes` compares them (new keywords default to production registries) | `test_impact_replay.py` +2 (both fail on base) | n/a | conservative: more reassessment, never fewer; latent today (no production capability declares ALEATORIC / MODEL_FORM) | COMPLETED |
| C-5 (P1.5) | Windows process-tree termination | DEFECTIVE | `providers/process.py::_kill_tree` (`taskkill /T /F`, then `kill`) | `test_provider_boundary.py` +1 (fails on base: 60.1 s) | timeout 60.1 s → bounded | none to verdicts | COMPLETED |
| P0.5 | Parallel parameter UQ | NOT VERIFIED | none | measured | threads ±0 %; process worker start 1.8–2.0 s > study 0.96 s | — | DEFERRED |
| P0.6 | Parallel refinement | NOT VERIFIED | none | measured | 4 calls / 75 ms | — | DEFERRED |
| P0.1 | Invariant audit | NOT VERIFIED | none (audit) | — | — | drone balances unchecked | PARTIAL |
| P0.2 | Cross-solver independence | — | none | — | — | — | ALREADY SATISFIED |
| P0.3 | Certification drift | — | none (no regeneration) | FAST baseline | — | — | BLOCKED (owner recertification, OD-3) |
| P1.2 | Safe computational cache | — | none (no unsafe reuse found; no new cache) | — | — | — | ALREADY SATISFIED |
| P1.4 | UQ memory streaming | NOT VERIFIED | none | — | peak WS 210 MB for 93 samples | records keep only digest + value per run | ALREADY SATISFIED |
| P1.6 | Solver profiling | — | none | — | — | — | ALREADY SATISFIED |
| P1.7 | Cost planning | — | none | — | — | cost must never select | DEFERRED |
| P1.8 | Mesh convergence automation | — | none | — | — | — | DEFERRED |
| P1.9–P1.11 | UQ attribution, evidence reuse, artifact immutability | — | none | — | — | — | ALREADY SATISFIED / PARTIAL (see §1.1) |
| P2.1–P2.2 | Checkpoint, replay | — | none | — | — | — | ALREADY SATISFIED |
| P2.3 | Failure taxonomy | — | none | — | — | — | NOT VERIFIED |
| P2.4 | Provider capability matrix | PARTIAL (`docs/architecture/providers.md`) | none | — | — | — | DEFERRED |
| P2.5 | Dependency cleanup | — | none | — | — | — | ALREADY SATISFIED |
| Flagships | Readiness audit | — | none | — | — | — | §5.2 |

---

## 5. Remaining roadmap

### 5.1 Ranked opportunities

| Rank | Item | Scientific impact | Performance impact | Effort | Risk | Evidence confidence | Depends on |
|---:|---|---|---|---|---|---|---|
| 1 | `ChallengeReport.status` reports "survived_attempted_challenges" while an attempted challenge is INCONCLUSIVE (pre-existing for alternative-model and guard-band results too) | medium (summary overstates) | none | S | changes a serialized status vocabulary clients may read | high (two reviews) | owner decision |
| 1b | Selection D2: surface NOT_ASSESSABLE as a compiler gap (or reject) | medium (diagnostics) | none | S | low | high (static review) | — |
| 2 | Selection D3: refuse array-section mismatch in `_check_references` | medium (fail-closed today) | none | S | low | high | — |
| 3 | Drone coupled-chain balance check with a declared, justified tolerance | medium | none | S–M | needs a tolerance decision | high | owner/scientific decision |
| 4 | Tree kill + bounded capture for ngspice, discovery `run_provider`, preCICE (and remove its temp dir) | robustness | prevents hangs | M | low | high | — |
| 4b | `ProcessWorkspace` on Windows: a descendant orphaned before the timeout escapes `taskkill /T`; a Job Object (or a bounded second `communicate`) would close it (review L1; not a regression) | robustness | prevents a residual hang | M | low | medium | — |
| 4c | Module docstring of `challenge.py` says an unusable run never weakens, yet VALIDITY_BOUNDARY_STRESS weakens on a domain end inside the declared range (documented per-kind); reconcile the wording | low (wording) | none | S | design | high | owner |
| 5 | `blindfold/isolation.py::run_discovery` timeout effective during reads (Linux) | robustness | — | S | low | high | Linux test env |
| 6 | `ProcessWorkspace` output capture bound (spill to file, keep digest + tail) | memory | bounded memory | M | digest semantics must stay | medium | — |
| 7 | Per-variant framework overhead (pint parsing, validity contexts) | none | up to ~10× per sample (estimate, NOT MEASURED) | M–L | units contract; never cache affine conversions | medium | `benchmarks/performance` |
| 8 | Parallel UQ through a declared process-safe executor contract | none | only for multi-second providers | L | determinism, licensing | low today | an expensive provider with EPISTEMIC_PARAMETER |
| 9 | `uq/budget` aggregation of an empty component list returns 0 | high if reachable | none | S | design decision | medium (not traced) | review |
| 10 | Model-data (calibration / parameter-set) validity in selection | high | none | M | design | medium | design decision |

### 5.2 Flagship readiness

| Domain | Executes | External solver | Experimental data | Numerical verification | Experimental validation | UQ | Recorded status | Classification |
|---|---|---|---|---|---|---|---|---|
| Battery | PyBaMM DFN + TESPy cold plate; Rint/OCV in core; 56-day fade | PyBaMM, TESPy | Chen2020 LG M50 (tuning data, not independent); NASA manifests; Kirkaldy 2024 outside the repo | energy check MET (2.9e-10), DFN energy NOT MET (1.104 % vs 1 %) | LG M50 NOT MET, DFN PRIMARY NOT MET, Kirkaldy fade NOT MET | UNKNOWN | `insufficient_evidence`; `battery.thevenin_1rc` FOUNDATION; confirmatory readiness `NOT_READY(...)` | EXECUTABLE, NOT READY |
| Electric motor | nothing (all couplings `declared_not_executable`) | none | none | none | none | none | template only | IMPLEMENTED (template), NOT READY |
| Drone / aerospace | actuator-disk hover; coupled steady hover chain | none | none (illustrative fixtures) | chain vs closed form (`tests/foundations/test_drone_coupled_hover.py`) | none | UNKNOWN | `coupled_steady_hover_screening_not_validated` | NUMERICALLY VERIFIED (screening), NOT READY |
| HVAC / thermal | lumped, conduction 1D/2D, NAFEMS T3; HVAC template only | TESPy (in flagship A) | NAFEMS T3 benchmark reference (not measurement) | T3 refinement quantified | none experimental | NUMERICAL for T3 | `thermal.nafems_t3` EVIDENCE_BACKED; HVAC "no coupled run is claimed" | T3: NUMERICALLY VERIFIED + benchmark-validated; HVAC: NOT READY |

No flagship is production-ready. No flagship benchmark was run in this program (none was authorized as cheap and
bounded beyond the UQ workloads above).

---

## 6. Verification record

Commands, results and the review record are in `docs/work/PROGRESS.md` (2026-10-12, engineering program). Summary:

* FAST (`-m "not expensive" -n 4`, CPython 3.14, Windows) on pristine `2d0fa6c3`: 151 failed, 9,644 passed,
  185 skipped, 21 errors (216 s). On the branch commit `088a8c8c`: 151 failed, 9,674 passed, 185 skipped, 21 errors
  (204 s). The sorted failure/error node-id sets are **identical** (`comm` shows no new and no removed id); the 30 extra
  passes are the new tests. The common set is Windows/3.14 environment (mutation-workspace POSIX contracts, escrow /
  authority subprocess tests, formal-xdist) plus the known certificate / freeze drift — not caused here.
* `tests/claims` (694), `tests/test_forge_check.py` (30), `tests/test_provider_boundary.py` (30, 1 pre-existing
  symlink skip) and `tools/forge_check.py --changed` pass on the final tree.
* SCIENTIFIC, FULL, hardened recertification, Python 3.11 / 3.12: **NOT RUN**.
* Reviews (read-only `forge-scientific-reviewer`): selection audit (D1 HIGH fixed; D2, D3 recorded); full-diff review
  PASS with M1 (`forge_check.py` is certification-pinned → owner recertification) and L1–L3 (L3 fixed, L1 recorded,
  L2 accepted: the impact test uses synthetic study records because no production capability produces them);
  narrow review of the challenge fix: findings 2 and 3 fixed (re-review PASS), 1 and 4 recorded above.
