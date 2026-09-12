# Performance & Campaign Execution Hardening — Sprint 7

**Branch** `claude/performance-campaign-sprint-7` · **base** `3bffde8`

---

## 1. Final verdict

> ### **PERFORMANCE HARDENING COMPLETE — PARALLEL EXECUTION DEFERRED**

Framework overhead was measured, not assumed: **97.0 % of a small-solve
campaign was framework and 3.0 % was numerics.** Four redundancies were removed
and the campaign is **2.7× faster** end to end, with every scientific output
bit-identical. Parallel execution is deferred because it was measured and is
**slower** than sequential (§13), and shipping it would be shipping a
regression with a feature's name on it.

| Acceptance item | Verdict |
|---|---|
| current performance profile exists | **HOLDS** — §4 |
| framework vs numerical time quantified | **HOLDS** — 97.0 / 3.0, §6 |
| top bottlenecks classified | **HOLDS** — §5 |
| campaign execution abstraction exists | **HOLDS** — §7 |
| campaign cases isolated | **HOLDS** — §7 |
| failures do not poison other cases | **HOLDS** — §7 |
| immutable declarations reused safely | **HOLDS** — §8 |
| no mutable execution state shared | **HOLDS** — a solver is refused by name, §8 |
| caching scientifically keyed | **HOLDS** — §9 |
| memory behaviour measured | **HOLDS** — §14 |
| 100/1k/10k benchmarks recorded | **HOLDS** — §15 |
| before/after recorded | **HOLDS** — §16 |
| scientific output equivalence | **HOLDS** — bit-identical, §18 |
| stable regression budgets | **HOLDS** — call counts, §17 |
| FAST green | **HOLDS** — §19 |
| FULL green | **HOLDS** — §19 |
| guards green | **HOLDS** — §19 |
| wheel green | **HOLDS** — §21 |
| certificate state correct | **HOLDS** — went red, reissued, §22 |

---

## 2. Baseline hardware / software

| | |
|---|---|
| Python | 3.14.2 |
| platform | Windows-11-10.0.26200-SP0 |
| processor | Intel64 Family 6 Model 183 Stepping 1 · 24 logical cores |
| numpy / scipy | 2.5.2 / 1.18.1 |

Every number here is from this machine. The repository's existing performance
suite argues at length that a wall-clock threshold describes the machine rather
than the code, and this report takes that seriously: the *guards* added in §17
are call counts, and the wall-clock figures below are evidence for a
before/after on one machine, not thresholds anybody should inherit.

---

## 3. Workload matrix

| | Workload | Where |
|---|---|---|
| A | tiny scalar solve — DC divider, 3 nodes | `solve_circuit` |
| B | field solve 32² / 64² / 128² | `solve_steady_conduction` |
| C | campaign 100 / 1,000 / 10,000 evaluations of A | loop and sweep |
| D | parallel spike, 1 / 2 / 4 workers | `run_sweep(workers=…)` |
| E | memory at each campaign scale | `tracemalloc`, separate pass |

Deterministic by construction: no RNG, no clock in any input, no case files.

**Not measured, and why.** CSTR is a stiff `solve_ivp` integration orders of
magnitude larger than the rest; it is dominated by the integrator, no framework
change here touches it, and its oracle tests pin its values. Battery and lumped
thermal are closed-form evaluators with no `ScientificResult` producer, so they
would measure the same framework path as A with a cheaper kernel. The
equivalence check in §18 covers all of them.

---

## 4. Profiling results

`cProfile`, attributed by **self-time** (`tottime`) so the categories sum to the
run. Cumulative time would double-count — a solve's cumulative time contains
its own unit conversions — and the percentages would mean nothing.

### 1,000 tiny DC solves — before

| Category | Calls | ms | % |
|---|---|---|---|
| **units backend (pint)** | **2,484,000** | **1,572.8** | **40.9 %** |
| interpreter builtins | 3,272,001 | 674.4 | 17.5 % |
| domain (DC solver) | 374,000 | 393.1 | 10.2 % |
| units (Forge wrapper) | 516,000 | 354.2 | 9.2 % |
| other | 647,001 | 209.2 | 5.4 % |
| stdlib | 368,000 | 109.8 | 2.9 % |
| **numerics** | 66,000 | **85.0** | **2.2 %** |
| json | 28,000 | 81.8 | 2.1 % |
| freeze | 59,000 | 81.1 | 2.1 % |
| IR / serialization / validation / provenance / thresholds | 132,000 | 176.1 | 4.6 % |
| **total** | **8,051,002** | **3,849.0** | |

Hottest: `pint quantity.__new__` 58,000 calls, `isinstance` 1,027,000,
`pint registry._validate_and_extract` 58,000, `normalize_unit` 188,000.

**Fifty-eight backend quantity constructions and fifty-eight unit-string parses
per solve**, for a circuit with two resistors.

### Field solve 32×32 — before

| Category | Calls | ms | % |
|---|---|---|---|
| **sparse structure (lil)** | **183,320** | **87.8** | **55.0 %** |
| interpreter builtins | 260,056 | 34.3 | 21.4 % |
| domain (assembly loop) | 23,265 | 23.5 | 14.7 % |
| Core framework, all of it | ~15,400 | ~5.4 | ~3.4 % |
| **factorization** | **5** | **0.06** | **0.04 %** |

`scipy.sparse._lil.__setitem__` is a Python call per matrix element. It lives
in scipy and it is not linear algebra, so it is reported on its own line;
counting it as numerical work would have answered the sprint's question
wrongly. **The trust machinery the earlier sprints built — units, freeze,
validation, provenance, fields, thresholds — is 3.4 % of a field solve.**

---

## 5. Top bottlenecks, classified

| # | Bottleneck | Class | Optimized |
|---|---|---|---|
| 1 | backend quantity built and unit string parsed per conversion | **C** duplicate framework work | yes |
| 2 | `lil_matrix` per-element assignment in field assembly | **C/D** | yes |
| 3 | circuit fingerprint computed 5× per solve | **C** | yes |
| 4 | `normalize_unit` prologue run 188× per solve | **D** Python overhead | yes |
| 5 | `threshold_digest` recomputed twice per solve | **B** trust work | **no — §9** |
| 6 | `isinstance` traffic | **B/D** | no — mostly driven by 1 and 2, and fell with them |
| 7 | validation, provenance, freeze | **B** | no |

Only C and D were touched. Nothing in class B was made cheaper.

---

## 6. Framework vs solver time

| Workload | Framework | Numerical |
|---|---|---|
| 1,000 tiny DC solves — before | **97.0 %** | 3.0 % |
| 1,000 tiny DC solves — after | **92.9 %** | 7.1 % |
| field solve 32×32 — before | 87.9 % (of which 55 % sparse container) | 12.1 % |

The ratio barely moves for the tiny solve, and that is the honest reading: a
three-node divider *is* framework. Removing 63 % of the wall time removed
framework work, and what remains is still overwhelmingly framework, because
2 ms of contract work around 0.03 ms of arithmetic is what a scientific record
costs. The number to act on is not the ratio; it is that the same guarantees
now cost 2.7× less.

---

## 7. Campaign architecture

`src/engcore/execution/sweep.py`. **Not called a campaign**:
`engcore.sria.campaign` already is one and is a different thing — an autonomous
decision loop that chooses which experiment to run next from a belief snapshot.
A sweep chooses nothing; it is handed its cases. Two things called Campaign in
one codebase would be the ambiguity this repository refuses everywhere else.

| Record | What |
|---|---|
| `SweepDefinition` | operation, cases, shared context, failure policy |
| `SweepCase` | one case's own inputs, and nothing shared |
| `SharedContext` | declarations every case may read and none may write |
| `SweepOutcome` | what one case produced, or why it produced nothing |
| `SweepSummary` | counts, identities, timings, failures — never the results |

Guarantees, each with a test in `tests/test_execution_sweep.py`:

* **case identity** is a digest of the case's own content, and does not change
  because another case was inserted before it;
* **ordering** is declaration order whatever order cases ran in, asserted with
  four threads forced to interleave on a barrier;
* **failure isolation** — one case raising neither stops nor contaminates the
  others, and `FAIL_FAST` accounts for the cases it did not run rather than
  omitting them;
* **no implicit deduplication** — duplicate case ids stay distinct records;
* **re-running failures** carries the same case identities, so a case that
  failed and then succeeded is one case with two outcomes;
* `KeyboardInterrupt` is not swallowed as a case failure.

---

## 8. Shared immutable context

The saving comes from sharing declarations, and the whole risk of that saving
is sharing something that should not be shared. `SharedContext` checks every
entry on construction and refuses:

| Refused | Why |
|---|---|
| anything carrying `prepare` and `solve` | it is a solver — request-specific execution state. Sprint 2 established it must never leak between solves, and hoisting one out of a loop is exactly how it would |
| `dict`, `list`, `set`, `bytearray` | any case that reaches it can change it |
| a mutable dataclass | same |
| an object with a writable `__dict__` | same |

Admitted, and recorded by name and type in every summary: atoms, tuples and
frozensets of admitted values, the core's own frozen mapping, and frozen
dataclasses. The solver check is **structural**, by the protocol's own verbs,
so it catches a solver from any domain including one not written yet.

Reused in the benchmark: two `Quantity` declarations. What a sweep does *not*
reuse is a solver, a problem, a prepared state or any per-case diagnostic.

---

## 9. Caching decisions

Three caches, each keyed on scientific identity, plus one deliberate refusal.

| Cache | Key | Why it is safe |
|---|---|---|
| unit conversion rule | canonical `(source, target)` pair | the registry is a constant for the life of the process |
| `normalize_unit` | the caller's spelling | pure function of the string |
| circuit fingerprint | the instance | the record is frozen and every hashed field is a string, number or frozen tuple |

**No scientific result is cached.** A repeated case is run again; the sweep
deduplicates nothing.

**`threshold_digest` is deliberately not memoized.** It is computed twice per
solve and its own docstring says why it recomputes: *"so a set whose values
were changed after it was built is judged by the values it holds now."* That is
a fail-safe against a mutated threshold set, and Phase 4's rule — do not
optimize a safety check because it costs time — applies exactly. Measured cost
of leaving it: two SHA-256 digests over a four-entry mapping per solve.

---

## 10. Quantity performance

The measurement that drove the whole sprint. `Quantity.to` built a fresh
`pint.Quantity` from `(magnitude, unit string)` per call, so both units were
re-parsed every time.

What is cached is the **rule** for a unit pair, never the arithmetic:

* a **multiplicative** pair caches the factor and multiplies;
* an **affine** pair goes to the backend's own `convert` with both unit
  containers already parsed.

The split is decided by measurement, not algebra. `m * (one − zero) + zero` is
algebraically the backend's affine conversion and numerically is not — the
subtraction and the addition each round:

| | bit-identical to the backend |
|---|---|
| multiplicative pairs | **5,412 / 5,412 (100 %)** |
| affine pairs | 178 / 440 (40.5 %) |

So affine pairs never take the multiply. `tests/test_unit_conversion_equivalence.py`
is that measurement kept as a test — asserting the backend's own **bits**, not
a tolerance, over every compatible pair of a 48-unit set and magnitudes chosen
for where floating point misbehaves (denormals, 1e±300, 2⁻¹⁰⁰⁰).

Measured: `Quantity(...).to()` 10.43 µs → `convert` with cached containers
3.77 µs (2.8×), and a multiplicative pair to a float multiply.

**The unit system was not replaced.** Pint still owns the unit algebra; what
changed is how often it is asked to parse a string it has already parsed.

---

## 11. Freeze / type-check performance

Measured and **not optimized**.

`freeze` was 2.1 % of the before profile and 5.2 % of the after profile — it
grew as a share only because the total shrank. `isinstance` fell from 1,027,000
calls to 360,000 without being touched, because most of it was driven by the
backend traffic and the LIL container that were removed.

The tempting change — `freeze(x)` returning `x` when already frozen — was not
made: it is a change to an immutability boundary for a measured 2 % of a
workload that is not the one anybody runs at scale, and the mutation harness
exists precisely because that kind of change is how mutable data gets through.

---

## 12. Field assembly performance

| Support | assemble before | assemble after | whole solve before | whole solve after |
|---|---|---|---|---|
| 32×32 | 10.5 ms | **1.6 ms** | 12.9 ms | **3.6 ms** |
| 64×64 | 49.6 ms | **6.5 ms** | 51.2 ms | **14.6 ms** |
| 128×128 | 179.8 ms | **29.4 ms** | 221.6 ms | **69.0 ms** |

Assembly **6.1×**, whole solve **3.2×** at 128×128.

The loop is unchanged; only the container is. Coefficients are produced in the
same order and appended to three coordinate lists, and scipy sums duplicates on
conversion exactly as `+=` accumulated them. A coordinate is written at most
twice — a ghost node's mirror can coincide with a real neighbour — and the sum
of two floats does not depend on their order.

That argument is not left as an argument. `tests/test_conduction2d_assembly.py`
keeps the previous `lil_matrix` construction verbatim and asserts **bit-identical**
operators, right-hand sides, sparsity patterns and solved fields across five
manufactured cases and supports from 2×2 to 33×33 — with 2×2 in the list
because that is where a mirror coincides with a neighbour, and a further test
asserting such duplicates actually occur, so the bit-identity is not being
demonstrated on cases that never exercise it.

The PDE solver architecture was **not** rewritten, as the sprint required.

---

## 13. Parallel execution results

2,000 cases of workload A:

| Workers | Wall | Cases/s |
|---|---|---|
| 1 | 1.018 s | **1,964** |
| 2 | 1.092 s | 1,832 |
| 4 | 1.127 s | 1,774 |

> **Threads are slower.** This workload is pure Python bytecode — record
> construction, unit lookups, dictionary work — and holds the GIL throughout.
> Adding workers adds scheduling and contention and removes nothing.

So parallelism is **not shipped as a recommendation**. `run_sweep(workers=N)`
exists, is tested for isolation and ordering under four threads, and is
documented as helping only where the operation releases the GIL. `FAIL_FAST` is
refused above one worker: with cases already in flight, "stop at the first
failure" would mean a different set of cases each run.

A process pool was not attempted. It would require every case input, the shared
context and every result to pickle across a boundary, which is a design
question about what a scientific record may cross — not a performance tweak —
and it belongs in its own round.

---

## 14. Memory results

Measured in a **separate pass** from timing, because `tracemalloc` roughly
halves throughput; the first draft of the benchmark ran them together and
reported 760 cases/s for work the un-profiled measurement beside it put at
1,970.

| Cases | loop peak | sweep peak |
|---|---|---|
| 100 | ~0 MB | 1.2 MB |
| 1,000 | ~0 MB | 11.8 MB |
| 10,000 | ~0 MB | 123.6 MB |

The loop discards each result; the sweep retains them, because they are its
output. **12.4 kB per retained `ScientificResult`, linear and flat per case** —
no growth beyond the results themselves, which is the property that matters: no
retained solver session, no accumulated diagnostics, no duplicated provenance.
A test asserts the *summary* does not grow with the case count, which is where
a retained session would appear.

A caller who does not want 10,000 results retained should consume outcomes as
they are produced; that streaming interface is not built and is named in §27.

---

## 15. 100 / 1k / 10k benchmark table

| Cases | Before | After | Speedup | After, via sweep |
|---|---|---|---|---|
| 100 | 0.136 s · 733/s | **0.050 s · 1,994/s** | **2.72×** | 0.055 s · 1,808/s |
| 1,000 | 1.339 s · 747/s | **0.509 s · 1,966/s** | **2.63×** | 0.520 s · 1,923/s |
| 10,000 | 13.544 s · 738/s | **4.976 s · 2,010/s** | **2.72×** | 5.208 s · 1,920/s |

Throughput is flat across three orders of magnitude before and after: the
campaign path is linear in the case count, and was already.

**The sweep abstraction costs about 4.5 %** against a bare loop (1,920 vs
2,010 cases/s at 10,000). That is the price of case records, identities,
per-case timing and failure capture, and it is stated rather than hidden — a
caller who wants the last 4.5 % can still write the loop.

---

## 16. Before / after

| Measure | Before | After |
|---|---|---|
| 10,000-case campaign | 13.544 s | **4.976 s** (−63 %) |
| campaign throughput | 738/s | **2,010/s** (2.72×) |
| 128×128 field solve | 221.6 ms | **69.0 ms** (3.2×) |
| 128×128 field assembly | 179.8 ms | **29.4 ms** (6.1×) |
| profiled campaign time | 3,849 ms | 1,459 ms |
| pint share of profile | 40.9 % | **3.1 %** |
| `isinstance` calls per 1,000 solves | 1,027,000 | 360,000 |

Classification: **BOTTLENECK_FOUND_AND_IMPROVED.** 63 % campaign wall-time
reduction, against the sprint's "prefer > 20 %" bar.

---

## 17. Performance budgets

`tests/test_performance_budgets.py`. **Call counts, not clocks**, following the
rule `tests/test_core_performance_guards.py` already set. Each guard names the
fault it detects: PERF-1 and PERF-8 (shared context rebuilt or abandoned),
PERF-2 (digest memoization disabled), PERF-4 (a fresh unit parse per
conversion), PERF-5 (sessions retained), PERF-6 (results serialized in the
loop), PERF-7 (field topology rebuilt).

Two wall-clock ceilings are included and are deliberately ~60× the development
machine, because their job is to catch something becoming quadratic rather than
to police a constant factor. They say so in their own failure messages, and are
marked `expensive` so they stay out of FAST.

**Writing these caught two mistakes in the tests rather than the code**, both
kept as comments so the next reader does not repeat them. Counting `json.dumps`
through a module attribute counts every caller in the process, because `json`
is one module object — it reported two phantom circuit serializations that were
threshold digests. And counting `canonical_dict` counts more than fingerprints,
because `solve_circuit` calls it directly for its own payload.

---

## 18. Scientific equivalence

**Mandatory, and it holds — bit-identical, not merely close.**

| Check | Result |
|---|---|
| scalar domains: DC, material resistance, lumped thermal, battery | **864 serialized paths, 0 changed, 0 added, 0 removed** |
| unit conversions | backend's own **bits** over 133 pairs × 5,412 magnitudes |
| field operator, right-hand side, sparsity, solved field | **bit-identical** across 5 cases × supports 2×2 … 33×33 |
| CSTR | covered by its oracle suites in FULL |
| validation outcomes, trust levels, provenance, evidence identity, route independence, field identity | unchanged — FULL, guards and EI/RI/FM/SP all green |

The scalar comparison is against the **pre-Sprint-4** baseline, so it spans
Sprints 4 through 7 in one measurement.

---

## 19. FAST / FULL / guards

| Run | Result |
|---|---|
| **FAST** | **4,564 passed, 4 skipped, 543 deselected** (49.4 s) |
| **FULL** | **5,107 passed, 4 skipped, 0 failed** (196.1 s) |
| Contract Guard | 305 passed |
| Capability Boundary | 304 passed, 675 deselected |
| Scientific Truth | 293 passed, 3 skipped |
| field suites | 124 passed |
| field profile suites | 147 passed |
| mutation harness self-guard | 6 passed |

---

## 20. Mutation / assurance results

| Family | Total | Killed | Survivors |
|---|---|---|---|
| EI — evidence pairing | 10 | 10 | 0 |
| RI — route independence | 12 | 11 | **1 (RI2b)** |
| FM — field and mesh | 8 | 8 | 0 |
| SP — spatial profiles | 10 | 10 | 0 |
| | **40** | **39** | 1 |

Control GREEN. RI2b is the **known equivalent mutant** proven equivalent in
Sprint 3, recorded as a survivor rather than excluded from the count.

### Certified 79-mutant harness

| | |
|---|---|
| control | **GREEN** |
| total | **79** |
| killed | **79** |
| survivors | **0** |
| log SHA-256 | `ea3cb81dc6d672e6a49f0f689c39e86c89e451f3a98f852dd839048355f4c65e` |

**Measured on the tree being certified**, which took two attempts and is worth
the sentence. The first run of this round was discarded: a fix to `quantity.py`
landed while it was in flight, and the harness copies the live tree *per
mutation*, so mutants 1–27 saw different source from the rest. A number
measured across a moving tree is not a number, and that is the same objection
this report raises against the previous certificate's.

### A defect the harness found in itself

The first re-run came back **CONTROL RED — ROUND VOID**: the copied tree failed
`test_every_dependency_the_tree_reaches_for_is_declared` with no mutation
applied. The harness copies `src`, `tests`, `experiments`, `docs`, `benchmarks`
and `pyproject.toml` — not `tools`, which Sprint 6's certificate drift test
imports. It refused to produce a number rather than produce a wrong one, which
is exactly what it was built for.

Two things follow, and both belong in the record:

* **this has been true since Sprint 6, and its certificate did not show it.**
  That round ran the harness early, before the drift test existed, so the 79/79
  it records was measured on a tree that predates the tree it certifies. The
  result was real; it was not measured where the certificate implies. This
  sprint re-runs it on the tree being certified.
* the copy set is a second place that has to know what `tests/` reaches for,
  and nothing checks the two agree. The harness's own control is what notices —
  and only when somebody runs it.

---

## 21. Wheel

Built from `git archive` at this branch's head: **206 entries, 0 under `src/`**,
`engcore/execution/` ships, `tools/` correctly does not. Run under
`python -S -E` with a `conftest.py` asserting `engcore.__file__` is under the
install target before any test runs: **306 passed**, including the sweep layer,
the unit conversion equivalence suite and the field assembly equivalence suite.

---

## 22. Certificate status

**Certified scope changed**: `src/engcore/scientific/units/quantity.py`.

The certificate went **red and named it**, which is Phase 25's requirement
proved rather than asserted:

```
AREA core
  MODIFIED: src/engcore/scientific/units/quantity.py
  expected area digest: 71eeddd96dca06fe…
  actual area digest:   9565ca6274a79b3f…
expected aggregate: 2bd8a2807bdd3092…
actual aggregate:   406443e0baa89848…
FAILED
```

Reissued with the V2 tool after all assurance passed. No digest was hand-edited;
`current_core_v1.json` and the V2 certificate's algorithm are unchanged.

Reissued at commit `7d509fd`:

| | |
|---|---|
| files | 72 |
| aggregate | `61f9546d367def9dd007a137d5f35e028020463459179e0d7eb47384558ef20c` |
| previous aggregate | `2bd8a2807bdd3092…` |
| verification | `certificate matches the tree` · **OK** |

Both certified files that changed are recorded: `quantity.py` in the `core`
area and `mutation_guards.py` in the `harness` area.

---

## 23. Files changed

13 files, +2,220 / −17. Two of them are in certified scope.

| File | Δ | Certified |
|---|---|---|
| `src/engcore/scientific/units/quantity.py` | +107/−9 | **yes — core** |
| `tests/mutation_guards.py` | +11/−2 | **yes — harness** |
| `src/engcore/execution/sweep.py` | **new**, 518 | no |
| `src/engcore/execution/__init__.py` | **new**, 33 | no |
| `src/engcore/domains/thermal_models/conduction2d.py` | +43/−6 | no |
| `src/engcore/domains/electrical/dc/circuit.py` | +20/−2 | no |
| `tests/test_performance_budgets.py` | **new**, 338 | no |
| `tests/test_execution_sweep.py` | **new**, 327 | no |
| `tests/test_conduction2d_assembly.py` | **new**, 208 | no |
| `tests/test_unit_conversion_equivalence.py` | **new**, 177 | no |
| `benchmarks/performance_campaign/attribution.py` | **new**, 237 | no |
| `benchmarks/performance_campaign/bench_campaign.py` | **new**, 218 | no |
| `benchmarks/performance_campaign/ROUND_REPORT.md` | **new** | no |

`src/engcore/execution/` is deliberately **not** added to certified scope this
sprint. It is an executor, not a contract: it declares nothing a verdict rests
on, and the Sprint 6 criterion for inclusion is that a silent edit would change
what a verdict *means*. A sweep that leaked state between cases would do
exactly that, which is an argument for revisiting it — recorded in §27 rather
than settled here, because widening certified scope is a decision and not a
side effect of a performance sprint.

---

## 24. Commits

| | |
|---|---|
| `026d100` | `perf(units): memoize the unit conversion rule, not the arithmetic` |
| `9d93e84` | `perf(electrical): compute a circuit's fingerprint once` |
| `78e207c` | `perf(thermal): assemble the field operator as coordinates` |
| `2ce5dde` | `feat(execution): run many independent evaluations as a sweep` |
| `ff219ff` | `test(performance): guard the work this sprint removed` |
| `12dd66f` | `fix(assurance): copy tools into the mutation harness tree` |
| *(pending)* | `cert(core): recertify after the performance round` |
| *(pending)* | `docs(core): close the performance and campaign round` |

---

## 25. Push result

Pushed to `origin/claude/performance-campaign-sprint-7`. `main` untouched.

---

## 26. Exact performance claim

> **A campaign of small scientific solves runs 2.7× faster and a 128×128 field
> solve 3.2× faster, with every scientific output bit-identical, because four
> pieces of redundant framework work were removed: a unit conversion that
> re-parsed both unit strings on every call, a unit normalizer that re-ran its
> prologue 188 times per solve, a frozen record whose digest was recomputed five
> times per solve, and a sparse assembly that made a Python call per matrix
> element.**

What is **not** claimed: that Forge is fast in absolute terms, that the
framework/numerical ratio improved (it is still 93 % framework for a three-node
divider — §6), that parallel execution helps (it does not — §13), or that any
safety check was made cheaper (none was — §5, §9, §11).

---

## 27. Deferred items

1. **Parallel execution.** Measured slower; a process pool is a design question
   about what a scientific record may cross, not a tweak.
2. **Streaming outcomes.** A sweep retains every result because they are its
   output; a caller wanting 10,000 cases without 124 MB needs an interface that
   hands each outcome over as it is produced.
3. **`threshold_digest` recomputation.** Deliberate, documented, class B.
4. **The remaining 93 % framework share** for a tiny solve. Reducing it further
   means changing what a `ScientificResult` costs to build, which is a contract
   question and not a performance one.
5. **The copy-set drift** in §20 — nothing checks that the mutation harness
   copies what `tests/` imports.
6. **CSTR was not profiled.** It is integrator-dominated and no change here
   touches it, but that is an argument, not a measurement.
