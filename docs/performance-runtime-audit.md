# Performance runtime audit

Engineering telemetry, not scientific evidence. Nothing in this document is a
claim about a reactor, a circuit or a campaign. Where a number is a wall-clock
time it is labelled as such and is **not** reproducible across machines; where a
number is an operation count it is deterministic and *is* the thing a future
regression gate should assert on.

Scope: measure first, then change only what the measurements justify. Several
suspected bottlenecks were measured and found not to be bottlenecks; those are
recorded here with their numbers rather than quietly optimized.

---

## PERF-0 — environment

| Item | Value |
|---|---|
| Repository | `sharq-labs/crafty` |
| Branch | `perf/sria-runtime-audit` |
| Base commit | `0ecc60cd57f22dcabad7b55c6807bda18aa67f3d` (`fix/k1-merge-readiness`) |
| Frozen K1 commit (untouched) | `bc7b1a3e5175b19d98ba22664caff777e849d135` |
| Python | 3.14.2 (MSC v.1944 64-bit AMD64) |
| NumPy | 2.5.1 |
| SciPy | 1.18.0 |
| scikit-learn | 1.9.0 |
| pint | 0.25.3 |
| pytest | 9.1.1 |
| Platform | Windows 11 Pro 10.0.26200 (`Windows-11-10.0.26200-SP0`) |
| CPU count | 24 |
| Measurement location | **Local workstation, not CI** |

**Platform caveat.** GitHub CI reported roughly 1066 passed in ~239 s. This
machine runs the same suite in ~148 s. The two numbers are not comparable and no
before/after comparison here mixes them. Every before/after pair in this document
was measured on this one machine, back to back.

Base commit note: merge-readiness *had* advanced past the frozen K1 commit, so
this branch is based on `0ecc60c` rather than on `bc7b1a3`. `fix/k1-merge-readiness`
itself is untouched — performance work is not mixed into PR #5.

Reproduce with the harnesses in `benchmarks/perf_runtime_audit/`. Recorded
baselines live beside them as `baseline_*.json`.

---

## Full suite

Baseline, this machine:

```
1117 passed in 147.96s   (wall 148.85s)
```

The test count is 1117 rather than CI's 1066 because merge-readiness added
tests. Runtime is highly concentrated: the slowest 30 tests account for ~88% of
the total.

Slowest 30 tests at baseline (paths relative to `tests/`):

| s | phase | test |
|---|---|---|
| 36.46s | call | `domains/kinetics/test_cstr_domain.py::test_the_gate_withholds_reference_levels_without_tolerance_independence` |
| 28.49s | setup | `test_thermal_t3_decision_aware_fidelity.py::test_the_policy_only_pays_for_rungs_it_visited` |
| 12.95s | call | `test_electrical_v01_demo.py::test_1_demo_config_is_deterministic` |
| 8.62s | call | `test_thermal_t1_fidelity_inference.py::test_forward_map_is_monotonically_decreasing_in_alpha` |
| 4.81s | setup | `test_thermal_t2_repeated_draw_calibration.py::test_every_arm_sees_the_same_draws` |
| 4.65s | call | `test_thermal_t2_repeated_draw_calibration.py::test_config_hash_is_stable_and_preregistration_covers_both_halves` |
| 4.18s | call | `test_sria_s11_transport_calibration.py::test_results_reproduce_exactly_under_the_frozen_configuration` |
| 2.76s | call | `test_sria_e2_model_adequacy.py::test_1_frozen_e2_config_hash_is_stable` |
| 2.38s | call | `domains/kinetics/test_cstr_domain.py::test_a_strongly_stiff_regime_defeats_the_explicit_probe` |
| 2.34s | call | `test_thermal_t2_repeated_draw_calibration.py::test_draws_are_reproducible` |
| 2.18s | call | `test_sria_falsification_transport.py::test_benchmark_payload_is_machine_readable_and_complete` |
| 1.99s | call | `domains/kinetics/test_cstr_domain.py::test_the_adiabatic_regime_is_measurably_stiff` |
| 1.84s | call | `test_thermal_t1_fidelity_inference.py::test_forward_map_is_deterministic` |
| 1.67s | call | `test_sria_falsification_transport.py::test_evsi_is_non_negative_and_bounded_by_evpi` |
| 1.66s | call | `test_thermal_t1_fidelity_inference.py::test_shared_posterior_agrees_with_frozen_e2_posterior` |
| 1.63s | setup | `domains/kinetics/test_cstr_domain.py::test_the_gate_awards_the_analytic_level_only_on_an_adiabatic_reactor` |
| 1.56s | call | `domains/kinetics/test_cstr_domain.py::test_a_usable_run_still_earns_its_levels` |
| 1.40s | call | `test_sria_e3_adequacy_obligation.py::test_1_frozen_e3_config_hash_is_stable` |
| 1.18s | call | `test_thermal_t2_repeated_draw_calibration.py::test_draws_are_distinct_across_replications` |
| 1.14s | call | `test_thermal_t2_repeated_draw_calibration.py::test_draws_match_the_declared_observation_model` |
| 0.96s | call | `test_sria_e1_electrical.py::test_1_preregistered_config_hash_is_stable` |
| 0.79s | call | `domains/kinetics/test_cstr_domain.py::test_the_gate_awards_nothing_to_a_converged_but_unusable_run` |
| 0.77s | call | `test_sria_e2_model_adequacy.py::test_null_calibration_is_deterministic_and_validly_constructed` |
| 0.73s | call | `test_sria_falsification_transport.py::test_evsi_is_computed_from_predictive_outcomes` |
| 0.73s | call | `domains/kinetics/test_cstr_domain.py::test_the_gate_records_why_an_unusable_rung_was_withheld` |
| 0.73s | call | `test_sria_falsification_transport.py::test_naive_policy_reproduces_the_extrapolation_trap` |
| 0.72s | call | `test_sria_falsification_transport.py::test_changing_the_hidden_truth_out_of_support_changes_nothing` |
| 0.71s | call | `test_electrical_v01_demo.py::test_16_demo_is_deterministic` |
| 0.70s | call | `domains/kinetics/test_cstr_domain.py::test_an_unusable_rung_never_becomes_the_reference_for_a_comparison` |
| 0.68s | call | `test_sria_falsification_transport.py::test_a_declared_transport_justification_restores_certifiability` |

**Solver-heavy tests dominate.** The single slowest test is a CSTR verification
gate; thermal and electrical solver fixtures follow. Optimizer/GP tests are not
in the top tier, and serialization/checkpoint tests do not appear at all — the
campaign scaling defect found below is latent, because no test exercises a long
campaign.

No slow test was deleted, skipped or weakened.

---

## K1 — solver invocation audit

`solve_ivp` invocations per workflow, counted by a transparent shim that forwards
every argument and records the call *before* the backend runs (so an integration
that exhausts its evaluation budget and raises out of the right-hand side is
still counted — an earlier version of this harness counted only calls that
returned, and silently omitted exactly the most expensive invocations).

Baseline (`baseline_k1_solver_calls.json`):

| workflow | `solve_ivp` calls | of which duplicated |
|---|---|---|
| one ordinary solve | 1 | 0 |
| `run_verification_gate` | **6** | **1** |
| `measure_stiffness` | 2 | 0 |

### Duplicate finest solve: CONFIRMED

The gate's six integrations, for regime R3 (strongly stiff):

| call | method | rtol | nfev | njev | nlu |
|---|---|---|---|---|---|
| 0 | BDF | 1e-06 | 907 | 3 | 51 |
| 1 | BDF | 1e-08 | 1563 | 4 | 108 |
| 2 | BDF | 1e-10 | 3818 | 2 | 225 |
| 3 | BDF | 1e-12 | 5345 | 2 | 436 |
| **4** | **BDF** | **1e-12** | **5345** | **2** | **436** |
| 5 | Radau | 1e-12 | 38421 | 2 | 254 |

Calls 3 and 4 agree in method, tolerance and *every* work counter. Call 3 is the
ladder's finest rung; call 4 is `_resample_finest`, which re-integrated the
identical problem solely to recover the trajectory arrays `ScientificResult`
discards. Two solves of the same problem at the same tolerance with the same
method cannot produce different information.

Total right-hand-side evaluations per gate, and the duplicated share:

| regime | total nfev | duplicated nfev | share |
|---|---|---|---|
| R1 (easy) | 8 868 | 980 | 11.1% |
| R2 (moderately stiff) | 41 686 | 3 936 | 9.4% |
| R3 (strongly stiff) | 55 399 | 5 345 | 9.6% |

Profiled against the suite's slowest configuration (the oscillatory reactor,
`n_output_points=20001`), `cProfile` attributes **9.563 s of 69.971 s (13.7%)**
to `_resample_finest`, and 98.8% of gate time to the six integrations overall.

### Trajectory allocation: real, but NOT a bottleneck

Every completed solve converts three dense arrays into Python lists
(`grid_time_s`, `grid_concentration_mol_per_m3`, `grid_temperature_k`), which
`solve_reactor` then strips before building the result.

| points | Python float objects | conversion time | traced bytes | ndarray bytes |
|---|---|---|---|---|
| 2 001 (default) | 6 003 | 0.235 ms | 190 088 | 48 024 |
| 20 001 (oscillatory) | 60 003 | 2.75 ms | 1 956 584 | 480 024 |

Memory overhead is ~4× the ndarray form, transiently. But at 2.75 ms against a
36.8 s gate the runtime cost is **~0.045%** — six solves contribute ~16 ms of
36 810 ms. This does not justify restructuring the validation path. Recorded as
debt with its number attached; see "Not done".

### Steady-state reference scan

20 001 scalar Python calls per gate, once per gate:

| regime | scalar scan | vectorized scan |
|---|---|---|
| R1 | 13.9 ms | 0.4 ms |
| R3 | 13.7 ms | 0.3 ms |
| R7 | 19.0 ms | 0.2 ms |

~1–4% of a normal gate (0.5–1.9 s), ~0.05% of the oscillatory gate. Modest, but
the vectorized form was verified **bit-identical** — see PERF-2 below.

### Stiffness measurement

`measure_stiffness` makes exactly 2 integrations (stiff arm + explicit probe). On
R3 the explicit probe deliberately burns its whole evaluation budget and raises;
that single call takes ~55 s and is the most expensive operation in the domain.
It is *the measurement itself* — the RK45/BDF work ratio is how this domain
evidences stiffness rather than asserting it — so it is inherent cost, not waste.
The full suite does not run R3's probe at full budget.

---

## Campaign checkpoint scaling — CONFIRMED O(N²)

`CampaignCheckpoint` carries a whole `CampaignEventLog`; `CheckpointStore` keeps
every checkpoint. So checkpoint *k* stores events 1..N_k and the store stores all
of them. Synthetic deterministic campaign state, 4 events per checkpoint, no
science executed (`baseline_campaign_checkpoint_scaling.json`):

| checkpoints | event records stored | serialized bytes | build+save | last save | `to_dict` | reload |
|---|---|---|---|---|---|---|
| 10 | 220 | 106 793 | 0.002 s | 0.3 ms | 0.000 s | 0.003 s |
| 100 | 20 200 | 8 779 983 | 0.207 s | 3.0 ms | 0.013 s | 0.262 s |
| 300 | 180 600 | 77 982 883 | 1.747 s | 9.4 ms | 0.104 s | 2.337 s |
| 1 000 | 2 002 000 | ~864 MB (extrapolated) | 18.241 s | 33.6 ms | — | — |

The growth law is exact, not approximate: stored records are precisely
`2N(N+1)` — 220, 20 200, 180 600, 2 002 000 for N = 10, 100, 300, 1 000. Bytes
and reload time both grow 9× for a 3× increase in N; build time grows 8.4× then
10.4×. Per-checkpoint save latency is itself O(N), because
`CampaignCheckpoint.__post_init__` calls `events.verify_chain()`, which
recomputes a SHA-256 digest for every event in the log. Summed over N
checkpoints that is O(N²) digests.

At 1 000 checkpoints the store's JSON is roughly 864 MB. Whole-store
serialization was skipped at that size deliberately: materializing it measures
this machine's memory pressure rather than the scaling law, which the three
smaller points already establish.

**This is a P0 scaling defect and it is NOT fixed on this branch.** The fix
changes an SRIA Core contract (`CampaignCheckpoint.to_dict`, `CheckpointStore`
persistence layout), and the standing rule is to stop and report rather than
silently alter frozen Core V0.2. See "Proposed Core V0.3 performance contract".

---

## Decision scoring scaling — LINEAR, no defect

`CandidateEvaluator.evaluate` with deterministic toy providers
(`baseline_decision_scaling.json`):

| candidates | median | µs/candidate | `snapshot.digest` computations |
|---|---|---|---|
| 10 | 0.0010 s | 100.8 | 4 |
| 100 | 0.0080 s | 79.6 | 4 |
| 1 000 | 0.0704 s | 70.4 | 4 |
| 10 000 | 0.8736 s | 87.4 | 4 |

Cost per candidate is flat. Ten thousand candidates score in under a second.
**A batch scoring API (`score_batch`, `cost_batch`, …) is not justified by these
measurements** and was not built.

`snapshot.digest` is recomputed 4 times per evaluation regardless of candidate
count, at ~9 µs each — so reusing it would save ~27 µs per evaluation. Real, and
too small to justify introducing a cache into effectively mutable state.

Decision-basis duplicate detection *is* quadratic:

| basis size | median |
|---|---|
| 10 | 7.0 µs |
| 100 | 94.4 µs |
| 400 | 1.85 ms |
| 1 600 | 21.9 ms |

Realistic bases hold a handful of dependencies, so today's cost is microseconds.
Fixed anyway as PERF-4, because it is a scaling trap in a constructor and the
substitution is provably verdict-identical.

---

## Legacy optimizer profile

`SmartExperimentEngine` / `GaussianSurrogate`, dim 6, candidate pool 4096
(`baseline_legacy_optimizer.json`). Separate from SRIA and from the frozen
V0.3.x optimizers.

| history | GP fit | predict+EI | duplicate distance | step total | GP share | distance tensor |
|---|---|---|---|---|---|---|
| 32 | 0.0526 s | 0.0069 s | 0.0066 s | 0.0660 s | 79.6% | 6.29 MB |
| 50 | 0.0992 s | 0.0094 s | 0.0102 s | 0.1188 s | 83.5% | 9.83 MB |
| 75 | 0.1194 s | 0.0139 s | 0.0167 s | 0.1500 s | 79.6% | 14.75 MB |
| 100 | 0.1548 s | 0.0159 s | 0.0196 s | 0.1904 s | 81.3% | 19.66 MB |

One end-to-end run: 2.99 s over 54 trials (22 GP fits), 28.9 MB traced peak.

**The GP refit dominates at ~80% of every step.** A new `GaussianSurrogate` is
constructed and fitted from scratch each iteration with `n_restarts_optimizer=2`
(three optimizer runs per fit). The `pool × history × dim` broadcast distance
tensor for duplicate suppression is ~10% of step time and allocates up to
19.7 MB per step.

Nothing here was changed. Warm-starting hyperparameters or replacing the distance
tensor would alter fitted models or selected points, which requires a successor
implementation with its own scientific identity rather than an edit to an
existing one. Old evidence must not be reattributed to new code.

### GP ConvergenceWarnings — classified, not silenced

The warnings are explained by the kernel's declared bounds:

* `Matern(length_scale=np.ones(dim), nu=2.5)` takes scikit-learn's default
  `length_scale_bounds=(1e-5, 1e5)` — hence "close to the specified upper bound
  100000.0".
* `WhiteKernel(noise_level=1e-6, noise_level_bounds=(1e-9, 1e-2))` — hence "close
  to the specified lower bound 1e-09".

Frequency: **0 warnings at history 32, then 6 per fit at history ≥ 50, and 29
across one full run.** CI shows only 4 because pytest deduplicates by source
location, which understates how often this happens.

Verdict: **optimization boundary hits, on a near-noiseless deterministic
objective.** With an essentially exact function the marginal likelihood pushes
the noise term to its floor and the length scale to its ceiling. There is a real
performance component — each boundary-hit restart is wasted optimizer work — but
the length scale sitting at 1e5 also means the fitted surrogate is close to
flat in those dimensions, which is a *model specification* question and not a
performance one. **No bounds were widened and no parameter was tuned.** Doing so
would change fitted models and requires a new registered experiment.

---

## Confirmed bottlenecks, ranked

| rank | bottleneck | evidence | complexity | practical impact |
|---|---|---|---|---|
| **P0** | Campaign checkpoint stores full event log per checkpoint | `2N(N+1)` records; 864 MB at N=1000; 18.2 s build | O(N²) storage, serialization and digest work | Severe at length; **latent today** — nothing runs long campaigns. Not fixed (Core contract). |
| **P0** | Duplicate finest CSTR integration | calls 3 and 4 identical in every counter; 9.56 s / 69.97 s profiled | one wasted O(solve) per gate | 9.4–11.1% of gate RHS evaluations. **Fixed (PERF-1).** |
| **P1** | Legacy GP refit from scratch each BO iteration | 80%+ of every step | O(n³) per fit, refit each step | Dominates the legacy loop. Not fixed — needs a successor identity. |
| **P2** | Scalar steady-state bracketing scan | 13.7–19.0 ms → 0.2–0.4 ms | 20 001 Python calls per gate | 1–4% of a normal gate. **Fixed (PERF-2).** |
| **P2** | `pool × history × dim` distance tensor | 19.7 MB and ~10% of step at history 100 | O(pool·n·dim) time and memory | Secondary to the GP fit. Not fixed. |
| **P3** | O(N²) duplicate detection in constructors | 7 µs at 10, 21.9 ms at 1 600 | O(N²) | Negligible at realistic sizes. **Fixed for `BeliefSnapshot` (PERF-4).** |
| **P3** | Trajectory → Python list conversion | 2.75 ms/solve at 20 001 points | O(points) allocations | ~0.045% of gate. Not fixed — see below. |
| **P3** | `snapshot.digest` recomputed 4× per evaluation | ~9 µs each | constant | ~27 µs per evaluation. Not fixed. |

---

## Optimizations implemented

### PERF-1 — remove the duplicated finest integration

Files: `src/engcore/domains/kinetics/cstr/solver.py`,
`src/engcore/domains/kinetics/cstr/validation.py`,
`src/engcore/domains/kinetics/cstr/__init__.py`,
`tests/domains/kinetics/test_cstr_solver_work.py` (new).

*Old:* the ladder solved the finest rung, `ScientificResult` discarded the dense
trajectory, and `_resample_finest` integrated the same problem again to get it
back.

*New:* a domain-local `VerificationSolveBundle` carries the compact
`ScientificResult` alongside the `TransientTrajectorySample` that solve already
computed. `solve_reactor_bundle` returns it; `solve_reactor` is a thin wrapper
returning `.result` and is byte-for-byte unchanged in behaviour.
`_resample_finest` is deleted.

The trajectory stays domain-local, transient, and out of every serialized
artifact. `ScientificResult` is **not** widened — the universal contract is
untouched, and the public result still carries no trajectory arrays (asserted by
test).

The sample is keyed on the *last rung of the ladder*, not the last *usable*
rung, because the re-solve it replaces was always performed at `ladder[-1]`'s
tolerances regardless of which rung became the reference. Reading a different
trajectory would change what the invariant and stationarity checks report.

Measured:

| | before | after |
|---|---|---|
| gate `solve_ivp` calls | 6 | **5** |
| R1 gate nfev | 8 868 | **7 888** (−11.1%) |
| R2 gate nfev | 41 686 | **37 750** (−9.4%) |
| R3 gate nfev | 55 399 | **50 054** (−9.6%) |

For the wall-clock figure see "Final verification" below — it is reported from a
paired serial measurement, not from the suite, and an earlier contended reading
is documented there rather than quoted here.

`cProfile` on the oscillatory configuration attributed 9.563 s of 69.971 s
(13.7%) to `_resample_finest`. That is a *profiled* attribution, under roughly 2×
instrumentation overhead, so treat it as locating the cost rather than sizing it;
the RHS-evaluation counts above are the exact figures.

Scientific behaviour unchanged: **yes.** Verified per regime against the recorded
baseline — `tolerance_independent`, `invariant_verified`,
`steady_state_verified`, `cross_method_agrees`, `levels_earned` and the
per-rung RHS evaluation counts all identical, and the reported
`invariant_max_rel_error`, `steady_state_rel_error` and
`cross_method_max_rel_difference` are unchanged to full precision.

### PERF-2 — vectorize the steady-state bracketing scan

Files: `src/engcore/domains/kinetics/cstr/reference.py`,
`tests/domains/kinetics/test_cstr_reference_scan.py` (new).

*Old:* `np.array([residual(float(t)) for t in grid])` — 20 001 Python calls.

*New:* the Arrhenius factor and residual are evaluated as array arithmetic. Brent
refinement is **unchanged and still handed the scalar residual**, so the
root-finding algorithm, its tolerance, the root ordering and the reference's
independence from the solve path are all untouched. Only the scan that *locates*
brackets changed.

The scalar path validated the rate parameters on every call via
`arrhenius_rate_constant`; those refusals are now made once, up front, so an
invalid declaration still raises instead of producing a fabricated residual
curve (asserted by test).

Verified **bit-identical**, not merely close, across all eight preregistered
regimes: zero differing residual values out of 20 001 per regime, identical
bracket sets, identical refined roots. `np.array_equal`, not `allclose`.

Measured: 13.7–19.0 ms → 0.2–0.4 ms per gate (~40–90×), 1–4% of a normal gate.

Scientific behaviour unchanged: **yes**, bit-level.

The narrowed claim is preserved verbatim: `SEARCH_SEMANTICS` still says
transversal roots only, and that a tangential root at a fold is not detected.
This work neither strengthens nor hides that limitation.

### PERF-4 — O(N) duplicate detection on the decision basis

Files: `src/engcore/sria/decision/belief_snapshot.py`,
`tests/test_sria_snapshot_basis_duplicates.py` (new).

*Old:* `{k for k in keys if keys.count(k) > 1}` — a scan per key.
*New:* one pass with a seen-set.

Identical verdict and identical message: the reported set is the same set, and
the message still sorts it. Tests pin which keys are named, that every duplicate
is named rather than only the first, that a key repeated many times is reported
once, and that sorted order is preserved (a set has no order, so the message must
not inherit iteration order).

Internal algorithm only — no signature, schema, serialized form or error text
changed. Not a contract change.

Measured impact at realistic basis sizes: microseconds. Justification is removing
a scaling trap, not a measured saving today, and this document does not claim
otherwise.

### CI performance visibility

File: `.github/workflows/sria-tests.yml`.

`--durations=30` added to the authoritative suite run. **Reporting only, not a
gate** — a shared runner's wall clock is not reproducible enough to fail a merge
on, and making it one would buy a flaky gate rather than a fast suite.

A future performance gate should assert deterministic operation counts instead.
The first such gate already exists and runs as part of the suite:
`tests/domains/kinetics/test_cstr_solver_work.py` asserts that the verification
gate performs exactly one integration per tolerance rung plus one cross-method
arm, that the finest rung is never integrated twice, and that the stiffness probe
performs exactly two.

---

## Not done, and why

| candidate | reason |
|---|---|
| **PERF-3** trajectory NumPy-through-validation | Measured at ~0.045% of gate time (2.75 ms per solve at 20 001 points). Would require moving arrays out of `RawSolverOutput.diagnostics` and changing `build_validation_report`'s inputs. Not worth the risk for 0.045%. Partial-trajectory diagnostics for failed runs are genuine failure evidence and were left alone. |
| **PERF-5** snapshot digest reuse | ~27 µs per evaluation. Too small to justify caching in effectively mutable state. |
| **PERF-6** checkpoint successor architecture | Confirmed O(N²), but the fix is an SRIA Core contract change. Reported below instead of implemented. |
| **PERF-7** batch candidate scoring | Measurements show scoring is linear at ~70–90 µs/candidate from 10 to 10 000. No defect to fix. |
| **PERF-8** legacy optimizer successor | GP refit is 80% of each step, but every plausible fix changes fitted models or selected points, so it needs a successor implementation with a new scientific identity. Out of scope for a performance pass. |
| Widening GP kernel bounds | Would change fitted models. Requires a new registered experiment, not a performance edit. |
| Other O(N²) duplicate-detection sites | Fifteen further sites exist (Scientific Core IR, model definitions, validation reports, charter, budget ledger, …). All are in Core and all are negligible at realistic sizes. Left alone under the no-Core-changes default; `BeliefSnapshot` was fixed because it was the site named for this pass. |

---

## Proposed Core V0.3 performance contract — campaign checkpointing

**STOP condition reached: a Core contract change is required. Not implemented.**

*Exact bottleneck.* `CampaignCheckpoint.events` holds a full `CampaignEventLog`,
and `CheckpointStore` retains every checkpoint. Every checkpoint therefore
re-stores the entire history that preceded it, and
`CampaignCheckpoint.__post_init__` re-verifies the whole hash chain each time one
is constructed.

*Measured scaling.* Stored event records `= 2N(N+1)` exactly. 864 MB of JSON and
18.2 s of build time at 1 000 checkpoints; reload and serialized size both grow
as N². Per-checkpoint save latency grows linearly, so the campaign's total
checkpointing cost is quadratic in its own length.

*Why a domain-local fix is insufficient.* The quadratic behaviour is in the
persistence layout and the constructor invariant, both of which live in SRIA Core
(`src/engcore/sria/campaign/checkpoint.py`, `events.py`). No domain can opt out
of them, and no caller can avoid them without reimplementing checkpointing.

*Minimum generic change.* Store the event log **once, append-only**, and have
each checkpoint reference a position in it rather than embed a copy:

* checkpoint keeps run state, budget state, effect state, obligation state, the
  in-flight iteration plan, an event **sequence cursor**, and the event **head
  digest** at that cursor;
* the store keeps one append-only event stream plus the per-checkpoint cursors;
* resume reads the latest cursor and verifies the chain prefix up to it;
* chain verification incremental from the last verified cursor rather than from
  event 0 — full verification stays available as an explicit audit operation.

Tamper evidence is preserved (the head digest at each cursor still pins the
prefix), append-only semantics are preserved, at-most-once effects are
unaffected, no checkpoint is discarded, and historical audit remains possible.

*Affected contracts.* `CampaignCheckpoint.to_dict` / `from_dict` and its schema
string; `CheckpointStore.to_dict` / `from_dict`, `save_to_path`,
`load_from_path`; `CampaignEventLog.verify_chain` gains an incremental form.

*Migration impact.* Existing serialized stores embed full logs per checkpoint. A
reader must accept both layouts, or a one-way upgrade must be provided.
**No frozen campaign artifact may be rewritten in place.**

*Frozen compatibility.* Core V0.2 is frozen. This belongs in a Core V0.3
performance contract with its own tests, prototyped on a separate branch, not
applied here.

---

## Final verification

| | baseline | after |
|---|---|---|
| tests collected | 1117 | **1161** (+44 regression tests) |
| result | **1117 passed** | **1161 passed** |
| the 44 new tests alone | — | 4.94 s |

Every suite wall time measured this session, in order, with the machine's state:

| run | tests | wall | machine |
|---|---|---|---|
| baseline, before any change | 1117 | 147.96 s | idle |
| after changes, first run | 1161 | 151.88 s | idle |
| clean clone | 1161 | 161.37 s | **contended** (gate benchmark running) |
| after changes, final run | 1161 | **138.85 s** | idle |

**Read these honestly.** Identical code produced 151.88 s and 138.85 s on the same
machine — a 9% spread. The final idle run is 9.1 s faster than baseline while
carrying 44 extra tests worth 4.94 s, which implies roughly 14 s of real
improvement; but the run before it implied roughly none. Both are the same code.

**Suite wall time on this machine cannot reliably resolve an improvement of this
size, which is exactly why the evidence for these changes is operation counts.**
Those are exact and do not vary:

| deterministic count | before | after |
|---|---|---|
| `solve_ivp` calls per verification gate | 6 | **5** |
| gate RHS evaluations, R1 | 8 868 | **7 888** |
| gate RHS evaluations, R2 | 41 686 | **37 750** |
| gate RHS evaluations, R3 | 55 399 | **50 054** |
| Python calls per steady-state scan | 20 001 | **0** (array arithmetic) |
| basis duplicate-detection passes | N per key | **1** |

### Wall-time measurement discipline, and a contaminated reading

An intermediate 5-repeat reading of the oscillatory gate reported a median of
36.18 s — apparently no better than baseline — while a 3-repeat reading of the
same code had reported 31.55 s. The 5-repeat run had been launched while the
clean-clone suite was executing on the same machine, so it was measuring CPU
contention rather than the gate.

That reading is discarded, not reported as a result. The paired measurement
below was taken serially on an idle machine: the same benchmark, at the base
commit and at the branch head, nothing else running.

Five repeats each, base worktree then branch head, nothing else running
(`paired_gate_base.json`, `paired_gate_after.json`):

| oscillatory gate (20 001 points) | median | min | max |
|---|---|---|---|
| base commit `0ecc60c` | 41.85 s | 38.22 s | 45.00 s |
| branch head | **32.77 s** | 31.00 s | 34.32 s |

−21.7% on the median, and the ranges do not overlap: the slowest branch-head run
(34.32 s) is faster than the fastest base run (38.22 s).

**Read even this with the drift in mind.** The base commit measured 36.81 s
earlier in the same session and 41.85 s here — a 14% spread for *identical* code,
across a session of sustained load. Absolute wall times on this machine are not
stable enough to quote in isolation; only the back-to-back paired delta means
anything, and the operation counts above are the hard evidence.

Note also that −21.7% exceeds the ~10% reduction in RHS evaluations. That is
consistent: the eliminated integration was a BDF solve, whose per-step LU work is
the expensive part, and on this configuration it also skipped a dense-output
evaluation over 20 001 points and the ~60 000 Python float allocations that
follow it. The RHS count is a lower bound on the work removed, not a proportional
proxy for it.

The suite's own slowest-test figure (36.46 s → 33.88 s) is a single sample per
run, not a median, and should not be read as a measurement of this change.

### Clean clone

The branch was cloned fresh (single-branch, `perf/sria-runtime-audit` at
`7ed2cb0`, clean working tree) and the suite run from the clone:

```
1161 passed, 4 warnings in 161.37s
```

Nothing depends on the working tree's untracked state. That run's wall time
(161 s) was CPU-contended by a concurrent benchmark and is reported for pass/fail
only, not as a timing.

### Frozen artifact safety

Tree hashes compared between the base commit and the branch head. All identical:

| tree | hash |
|---|---|
| `experiments` | `f595cb5aba80879015ea246c140f260507080b7f` |
| `benchmark_results` | `e20b8b2e7adbad58d1f70e393395e273fa5ccd1a` |
| `validation_results` | `0cb869e1be883ea8b93a80afac5bd61d5f4dffab` |
| `statistical_results` | `1ade0f4cb92266d811122cee4ce9a7ea89aec88a` |
| `parallel_statistical_results` | `459d9308ac4af5a2e9c8ff4f91f003e9947f663b` |
| `v024_results` | `4b95b93c40fa7e54f39eb2c45a000e2a78e47465` |
| `v025_statistical_results` | `04b3c834164322d2925dada1719d265099ff736d` |
| `v026_results` | `059bdf8ec98797330ba675c12c65308436c53535` |
| `v026_suite_results` | `3de6f8e12ea5af4da769980d1f7c3277e91205be` |
| `v027_suite_results` | `3c43b22ccbecff6b4a6d3a7f06fbdd33f2341655` |

`src/engcore/scientific/` is untouched. Electrical E1/E2/E3, Thermal T1/T2/T3 and
the K1 frozen artifacts are all inside `experiments`, whose tree hash is
unchanged, so none of them was regenerated or rewritten. Performance benchmark
output goes to `benchmarks/perf_runtime_audit/`, a new location that overwrites
no existing evidence.

### K1 end-to-end reproduction

Beyond the artifact-integrity tests, K1 was re-executed in memory — every regime,
every verification gate, every stiffness probe — and its output diffed field by
field. Nothing was written into `experiments/`.

Excluded as legitimately non-deterministic: `wall_seconds_telemetry`,
`wall_seconds`, `timestamp`, `source_commit`, `git_commit`, `environment`.

**The comparison that matters is base commit vs branch head, and it is the one
reported here.** Re-executing at the branch head and diffing against the *frozen*
`experiments/kinetics_k1/k1_results.json` produces 137 differences — but every one
of them is attributable to the base merge-readiness commit `0ecc60c`, not to
performance work. They are the merge-readiness changes themselves:

* `core_baseline_commit` added (the provenance-identity correction),
* `usable`, `counts_toward_verification`, `unusable_reason` added to each rung
  (the gate-promotion correction),
* `steady_state_search_semantics` added and the wording changed from "N steady
  state(s) exist in the envelope" to "N transversal steady state(s) were found"
  (the narrowed root claim),
* `T:max`, `t:T_max`, `max_temperature_k`, `min_concentration_mol_per_m3` moved
  (the envelope correction, which now assesses admissibility over accepted nodes
  **union** the dense grid instead of the nodes alone).

So the frozen `k1_results.json` is stale with respect to `fix/k1-merge-readiness`:
that branch changed what K1 computes without regenerating the artifact, and
`tests/test_kinetics_k1.py` does not catch it because it never calls `run_k1`,
`run_regime`, `solve_reactor` or `run_verification_gate` — it checks the recorded
JSON's internal consistency against the recorded config rather than re-deriving
it.

**That is a finding for PR #5, not something this branch fixed.** Regenerating a
frozen artifact is out of scope for a performance pass, and doing it here would
have silently mixed merge-readiness output into a performance branch.

The paired base-vs-head comparison isolates this work's contribution. K1 was run
in full from the base worktree and from the branch head, and the two dumps diffed:

```
base  config_hash: 73d09cc0004663409f27edf86fb2bb571bdb7bb78a39203e35ca9c0069d00cb0
after config_hash: 73d09cc0004663409f27edf86fb2bb571bdb7bb78a39203e35ca9c0069d00cb0
base  acceptance_all_met: True
after acceptance_all_met: True

NO DIFFERENCES: identical K1 scientific content, base vs branch head.
```

Every regime, every verification gate, every stiffness probe, every validation
level, every reported error and every provenance field: identical. This is the
strongest available evidence that PERF-1 and PERF-2 — which touch exactly the code
K1 exercises — changed no scientific number.

---

## Remaining performance debt

1. **Campaign checkpoint O(N²)** — P0, latent, blocked on the Core V0.3 contract
   above. Highest-value remaining item.
2. **Legacy GP refit** — 80% of each legacy BO step; needs a successor
   implementation with a new scientific identity.
3. **Radau cross-method arm** — 64–70% of gate RHS evaluations (38 421 of 55 399
   on R3). It establishes no validation level by design, but it is the single
   largest remaining gate cost. Whether it must run at the finest rung's
   tolerance is a *scientific* question, not a performance one, and is not
   answered here.
4. **R3 stiffness probe (~55 s)** — inherent: the budget exhaustion *is* the
   measurement.
5. **Trajectory list conversion** — 0.045%; documented above.
6. **Snapshot digest recomputation** — ~27 µs per evaluation.
7. **Fifteen further O(N²) duplicate-detection sites** in Core — negligible
   today, unfixed by policy.
8. **No operation-count regression gate on campaigns or decisions** — only the
   CSTR solver has one.
9. **`experiments/kinetics_k1/k1_results.json` is stale w.r.t. `0ecc60c`** — not
   performance debt, and not this branch's to fix, but it is the thing most likely
   to be mistaken for a performance-induced change by the next reader. See "K1
   end-to-end reproduction".

---

## Ratings

Out of 10, for the state of the tree at the branch head.

| area | score | reasoning |
|---|---|---|
| K1 solver efficiency | **7** | The duplicated integration is gone and the scan is vectorized, so no *wasted* work remains on the measured paths. Held back by the Radau cross-method arm at 64–70% of gate RHS evaluations while establishing no validation level, and by the ~55 s R3 stiffness probe. Both are scientific-design questions, not waste. |
| Campaign scaling | **3** | Confirmed exactly O(N²) in storage, serialization, reload and digest work, with a measured ~864 MB at 1 000 checkpoints. Nothing is fixed. Not lower only because it is genuinely latent — no current workload runs long campaigns — and because the successor design is specified rather than merely lamented. |
| Decision scaling | **8** | Measured linear at ~70–90 µs/candidate through 10 000 candidates; 10 000 score in under a second. One quadratic constructor check fixed. Not higher because ~27 µs/evaluation of redundant digesting remains and there is no operation-count gate guarding the linearity. |
| Legacy optimizer efficiency | **4** | GP refit from scratch dominates every step at ~80%, plus a 19.7 MB distance tensor per step. Fully profiled and explained, entirely unimproved — correctly so, since every fix needs a new scientific identity. |
| CI performance visibility | **6** | Durations now reported, and one real operation-count gate runs in the suite. No campaign, decision or optimizer counts are gated, and there is no recorded CI baseline to compare against — only this local one. |
| Overall performance readiness | **6** | The measurement infrastructure is the durable win: five reproducible harnesses, recorded baselines, and three hypotheses falsified before any code changed. Two real fixes landed with bit-level equivalence proven end to end. The largest confirmed defect is untouched by design, awaiting a Core V0.3 contract decision. |
