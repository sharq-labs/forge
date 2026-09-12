# Core Runtime Finalization — Sprint 9

> **VERDICT: CORE RUNTIME FINALIZATION COMPLETE — PARALLEL EXECUTION DEFERRED.**
> §29 answers the freeze question; §28 lists what is left.

---

## 2. Baseline

| | |
|---|---|
| branch | `claude/core-runtime-finalization-sprint-9`, from `f5369f0` |
| certificate at start | **OK** — `certificate matches the tree` |
| tree at start | clean |
| Sprint 8 | closed, Calibration & UQ Hardening Complete |

---

## 3. Domain boundary proof

`src/engcore/domains/**` was treated as **read-only**: read for compatibility
analysis, called by the benchmarks, never edited.

Proven by git **tree digest**, which is stronger than a diff because it covers
all 49 files at once and cannot be satisfied by compensating edits:

```
baseline domains tree : 022ee84479a8735d0115e6c2f5e13c6e473d4f02
current  domains tree : 022ee84479a8735d0115e6c2f5e13c6e473d4f02
git diff f5369f0..HEAD -- src/engcore/domains   ->   (empty)
```

**Domain files changed: 0.** No `CORE_ABSTRACTION_BLOCKER` was encountered —
no Core change in this round required a Domain change.

---

## 4. ScientificResult hot path — the profile

Two measurements, deliberately separate because they answer different
questions.

**Framework vs numerical**, on a real tiny DC solve through `solve_circuit`
(3 nodes, 2 resistors, 1 source). The numerical part is MNA assemble-and-solve;
the framework part is everything the Core does to turn that answer into an
attributable, checked, serialized record.

| | p50 | p95 | min |
|---|---|---|---|
| full path | **0.4282 ms** | 0.9461 | 0.3501 |
| numerical only | 0.0521 ms | 0.1281 | 0.0457 |
| **framework** | **0.3761 ms** | | |

**FRAMEWORK SHARE: 87.8 %.** Throughput 2,335 solves/sec. 600 samples for the
full path, 3,000 for the solve, GC disabled inside the measured region,
percentile-reported — this machine's clocks move under turbo and thermal
control and a single number is not reproducible against itself.

**Stage attribution** from the existing suite (`e2e.stage.*`, MEDIUM = 50
conditions/values/checks):

| stage | p50 ms |
|---|---|
| serialize | 0.1607 |
| consensus | 0.1491 |
| applicability | 0.0744 |
| result construction | 0.0713 |
| validation report | 0.0235 |
| provenance | 0.0186 |

---

## 5. Top framework costs

Per 400 solves, by self time, before any change:

| calls | self s | site |
|---|---|---|
| 157,600 | 0.023 | `builtins.isinstance` |
| 19,600 | 0.022 | `serialization.unwritable` |
| 9,600 | 0.018 | `immutable.FrozenMapping.__init__` |
| **50,400** | 0.014 | `quantity.normalize_unit` — **126 per solve** |
| 17,200 | 0.013 | `quantity.Quantity.__post_init__` |
| 45,200 | 0.012 | `immutable.freeze` — 113 per solve |
| 12,000 | 0.011 | `pint.util.UnitsContainer.__eq__` |
| 12,000 | 0.010 | `quantity.is_compatible_with` |
| **16,000** | 0.008 | **`typing.__subclasscheck__`** |
| 24,000 | 0.008 | `quantity.dimension_of` |

---

## 6. Required vs redundant

| operation | class | decision |
|---|---|---|
| `unwritable` walk | **A — required trust cost** | kept; it is the boundary that keeps a record writable |
| `freeze` deep walk | **F — architectural** | kept; already optimised with a learned atomic-type set and pointer compares |
| `Quantity.__post_init__` | **B — required scientific cost** | kept; a unit is validated once per value and that is the contract |
| provenance construction | **A** | kept |
| `normalize_unit` | already **E**, memoized | left; the 126 calls are cache HITS, so the cost is call overhead not recomputation |
| `isinstance` via `typing.*` | **D — redundant** | **removed** (§7.1) |
| `dimension_of(a) == dimension_of(b)` | **E — cacheable pure** | **memoized** (§7.2) |
| `clear_unit_caches` completeness | **defect, not a cost** | **fixed** (§7.3) |

Nothing in classes A, B, C or F was touched. No check was weakened, no "fast
mode" added, no debug/release split, no unsafe constructor, no back door.

---

## 7. Optimizations

### 7.1 `isinstance` against a typing alias

`typing.Mapping.__origin__` **IS** `collections.abc.Mapping` — literally the
same class — but the alias routes the check through
`typing.py:__subclasscheck__`. Measured on this interpreter:

| form | ns | |
|---|---|---|
| `isinstance(x, typing.Mapping)` | 365.1 | |
| `isinstance(x, collections.abc.Mapping)` | 142.6 | **2.56× faster** |
| `type(x) is dict` | 39.8 | **9.18× faster** |

Annotations keep `Mapping` — they are strings under
`from __future__ import annotations` and cost nothing at run time. The four HOT
modules the profile named (`serialization`, `results/immutable`,
`results/result`, `consensus`) use `_RuntimeMapping` for the runtime check,
with exact-type fast paths first. That is the technique `freeze` already uses
and documents in its own source.

`typing.__subclasscheck__` left the top-22 entirely; total function calls per
solve fell **13 %** (992,802 → 862,002 per 400 solves).

### 7.2 A memoized compatibility predicate

`is_compatible_with` was `dimension_of(a) == dimension_of(b)`: two memo lookups
and a pint `UnitsContainer.__eq__` that walks a mapping, **30 times per tiny
solve**. It is a pure function of two strings over a registry that cannot
change while the process runs, so it is memoized for exactly the reason
`_canonical_unit` is — and a same-string fast path handles the overwhelmingly
common Quantity-to-Quantity case in one string compare.

### 7.3 The cache clear was still incomplete

Part K asked for a test that `clear_unit_caches` really clears every dependent
memo. Written as an **enumeration** rather than a list — a list is what went
stale in Sprint 7 — it immediately found **`base_unit` and `is_ratio_scale`
surviving a clear**, and they had done since both were written.

That is the Sprint 7 defect in two more places, found on the first run of the
new guard. Both are now cleared, and the enumeration means a memo added later
cannot be forgotten the way these two were.

---

## 8. Before / after

| | before | after |
|---|---|---|
| tiny DC solve, p50 | 0.4282 ms | **0.3626 ms** |
| framework portion | 0.3761 ms | **0.3144 ms** |
| throughput | 2,335 solves/sec | **2,757 solves/sec** |
| function calls / 400 solves | 992,802 | **862,002** |

**Speedup 1.18× (15.3 % faster).** Framework cost down 16.4 %.

> These are the numbers AFTER the float fast path was removed in
> response to the certified harness finding G10c blinded (§19-23). With
> it the solve measured 0.3573 ms; the difference is inside this
> machine's run-to-run spread.

---

## 9. Framework vs numerical share

| | before | after |
|---|---|---|
| framework | 87.8 % | **86.7 %** |
| numerical | 12.2 % | **13.3 %** |

The share barely moves, and that is the honest headline: **the remaining cost
is required trust machinery, not redundancy.** What is left is unit validation
on every Quantity, the immutability walk, the writability boundary, provenance
construction and canonical serialization — each of which is a contract this
repository exists to keep. Optimizing further would mean weakening one of them,
so **optimization stopped here**.

### Part E — at scale

Same solve at four scales, each building a fresh circuit per iteration (so
these µs/eval are higher than §8's fixed-circuit p50 — they include circuit
construction and validation, and the two answer different questions):

| evaluations | wall s | eval/sec | µs/eval | framework |
|---|---|---|---|---|
| 100 | 0.052 | 1,910 | 523.7 | 87.8 % |
| 1,000 | 0.592 | 1,690 | 591.6 | 89.2 % |
| 10,000 | 4.949 | 2,021 | 494.9 | 87.1 % |
| 100,000 | 52.927 | 1,889 | 529.3 | 87.9 % |

**Per-evaluation cost is flat: 1.011× at 100,000 relative to 100.** That is the
question worth asking at scale, because a per-evaluation cost that grows with
the count is a retention bug wearing a performance costume.

---

## 10. Parallel benchmarks

**And the first version of this measurement was biased, in the direction that
would have produced the wrong decision.**

The first process prototype created the `ProcessPoolExecutor` **inside** the
timed region, so every measurement charged processes for pool spin-up and
interpreter import: 0.01×–0.43×, which reads as an obvious defer. Deferring on
that would have been deferring on a comparison built to lose. Measured both
ways since. A second correction went the same way: the prototype returned a
small summary dict, which understates the process boundary by omitting the very
object the Core exists to produce, so workload **D** returns the whole
`ScientificResult` and pays the pickling.

| workload | backend | 4 workers | speedup |
|---|---|---|---|
| A tiny CPU-light (400 cases) | sequential | 97,411/s | 1.00× |
| | threads | 52,968/s | **0.54×** |
| | processes, pool per sweep | 626/s | **0.01×** |
| | processes, persistent pool | 182,807/s | 1.88× |
| B medium, 1 solve (200) | sequential | 2,105/s | 1.00× |
| | threads | 1,828/s | **0.87×** |
| | processes, persistent pool | 7,340/s | 3.49× |
| C heavy, 20 solves (40) | sequential | 106/s | 1.00× |
| | threads | 96/s | **0.90×** |
| | processes, persistent pool | 402/s | 3.78× |
| **D medium, full `ScientificResult`** (200) | sequential | **1,987/s** | 1.00× |
| | threads | 1,747/s | **0.88×** |
| | processes, pool per sweep | 232/s | **0.12×** |
| | **processes, persistent pool** | **5,127/s** | **2.58×** |

**Threads are never faster.** 0.54×–0.97× across every workload and worker
count. The Core is pure Python, so workers contend on the GIL rather than
overlapping.

### Ship / defer decision

Against Part H's six conditions:

| # | condition | status |
|---|---|---|
| 1 | correctness equivalent | **not established** — no backend exists |
| 2 | failure semantics clear | **not established** |
| 3 | memory growth controlled | **not established** |
| 4 | throughput meaningfully improves | **met** — 2.58× on the realistic payload |
| 5 | sequential remains available | met |
| 6 | small workloads not silently slower | **the trap** — a per-sweep pool is **8× slower than sequential** |

**PARALLEL EXECUTION DEFERRED.** The benefit is real but depends entirely on a
persistent-pool architecture the current sweep does not have, and the naive
form fails condition 6 catastrophically. Building it correctly means pool
lifecycle, per-worker solver isolation, deterministic ordering, exception
transport, cancellation safety and a conservative AUTO policy — Part G's nine
requirements, all correctness-critical, immediately before a Core freeze.

**Sequential is frozen as the recommended Core backend.**

---

## 11. Process safety

Not assessed, and that is a consequence of the decision rather than an
omission: no process backend was built, so there is nothing whose input
serialization, solver isolation, child-failure isolation, output ordering,
exception transport, provenance or result identity could be verified. Part G's
checklist is carried forward to whichever round builds one.

---

## 12. Failure isolation

The Part J sweep — **PASS PASS FAIL PASS FAIL** — under both policies and 1, 2
and 4 workers.

| claim | result |
|---|---|
| failed cases isolated, siblings survive | 3 succeeded, 2 failed, 0 not-run |
| failed case keeps its identity | `case-2`, `case-4`, each with its own SHA-256 content digest |
| successful siblings uncontaminated | each carries its own answer |
| output order is declaration order | held at 1, 2 and 4 workers |
| `FAIL_FAST` | 2 succeeded, 1 failed, **2 NOT_RUN** — not failed; nobody asked them |
| aggregate record deterministic | identical across repeated runs |
| sequential ≡ threaded failure record | byte-identical at 1, 2, 4 workers |
| no stale state between sweeps | identities and values reproduce |

---

## 13. Memory

| claim | result |
|---|---|
| per-case retained memory | **flat** from 1,000 to 10,000 cases (≤ 1.10× tolerance) |
| per-run retained global state | five 2,000-case sweeps grow the unit memo by **0** |
| failed-case retention | traceback kept as **text**, not as a live exception |

The last one matters more than it looks: an exception object holds its
traceback, which holds every frame, which holds every local — so retaining one
per failed case in a large sweep would retain the whole call stack of every
failure. A test asserts no `SweepOutcome` field holds a `BaseException`.

---

## 14. Cache audit

Seven memos in `scientific/units/quantity.py`, all `lru_cache(maxsize=4096)`,
all keyed on unit **strings** and all deriving from a registry that is built
once under a lock and never replaced.

| memo | key | value | cleared by `clear_unit_caches` |
|---|---|---|---|
| `_canonical_unit` | stripped unit text | (canonical string, dimensionality) | yes |
| `_canonical_dimensionality` | canonical unit | rendered dimensionality | yes |
| `_normalized` | caller's spelling | canonical string | yes |
| `_conversion_rule` | (source, target) | conversion factor/rule | yes |
| `_compatible` | (source, target) | bool — **new this round** | yes |
| `base_unit` | unit | SI base unit | **was NO — fixed** |
| `is_ratio_scale` | unit | bool | **was NO — fixed** |

None is a scientific-identity cache: nothing about a model, threshold, context
or verdict participates in any key or value, so the completeness question those
must answer does not arise. Mutability: all values are immutable strings,
tuples or bools. Thread semantics: `lru_cache` is thread-safe for these pure
functions; there are no process semantics because there is no process backend.

**The Sprint 7 bug had not been fully fixed.** It was fixed in the two places
it was noticed and left in two it was not. The guard is now an enumeration over
the module's `lru_cache` objects, so it cannot go stale the way a list did.

---

## 15. Public runtime API classification

Pinned as a test, so a freeze is checkable rather than aspirational.

| symbol | class |
|---|---|
| `run_sweep`, `rerun_failed`, `cases_from` | **FREEZE** |
| `SweepDefinition`, `SweepCase`, `SweepOutcome`, `SweepSummary`, `SharedContext` | **FREEZE** |
| `CaseStatus`, `FailurePolicy`, `SweepError` | **FREEZE** |
| `run_sweep(workers=)`, `rerun_failed(workers=)` | **EXPERIMENTAL** |

Nothing is `DEPRECATE` or `INTERNALIZE`: the freeze candidate carries no
removal debt.

**`workers` is EXPERIMENTAL for a measured reason.** Threads were 0.54×–0.97×
of sequential on every workload tried. A parameter whose only observable effect
is to make a sweep slower is not a supported performance control. It keeps its
default of `1` and stays keyword-only — Part H condition 6 held at the
signature, so a caller who does not ask for parallelism cannot receive the
slowdown by accident.

---

## 16. Runtime mutations

**CONTROL GREEN. 9/9 killed. 2 recorded NOT APPLICABLE.**

The first pass killed only **6 of 9**, and all three survivors were real.

| id | guard broken | verdict |
|---|---|---|
| PERF-RT-1 | compatibility memo answers from the wrong identity | KILLED |
| PERF-RT-2 | cache invalidation skips two memos (Sprint 7 defect restored) | KILLED |
| PERF-RT-3 | the `dict` fast path drops canonical key ordering | KILLED |
| PERF-RT-4 | the float fast path stops refusing NaN | KILLED |
| PAR-1 | a solver may be shared across cases | KILLED |
| PAR-2 | a failed case loses its content identity in the record | KILLED |
| PAR-3 | outputs come back in an unpromised order | KILLED |
| PAR-4 | a worker exception is swallowed and reported as success | KILLED |
| PAR-7 | the worker default stops being sequential | KILLED |

### The two real gaps it found

**PERF-RT-3 — in code written this sprint.** The `dict` fast path added to
`encode` could drop canonical key ordering and nothing noticed. A fast path is
a second implementation of a rule, and one was added without a test that the
two agree — which is how a record starts serializing differently depending on
the order its keys were inserted. `tests/test_core_runtime_fast_paths.py` now
checks every fast path against the general path it short-circuits, on inputs
that take each branch: exactly-`dict`, a `dict` subclass, and a registered
`Mapping`.

**PAR-2 — determinism is not completeness.**
`test_the_aggregate_record_is_deterministic` compares two runs of the same
sweep, so a field dropped from **both** still compares equal. The mutation that
removed `case_identity` from the serialized summary survived it untouched.
There is now an assertion that the record a reader actually gets names each
failure by content digest.

**PAR-1** was the harness aimed at the wrong suite — the guard exists, in
`tests/test_execution_sweep.py`. Retargeted, not excused.

### Not applicable, recorded rather than dropped

- **PAR-5** — "reuse stale cached scientific input across identities" *in a
  process path*. No process backend exists. The same defect **shape** is
  exercised against code that does exist, as PERF-RT-1.
- **PAR-6** — "return different provenance in the process path". There is no
  process path. Nothing was weakened to make this inapplicable: the backend was
  measured and deliberately not built.

A denominator that quietly shrinks to the mutations that happened to pass is
the failure this apparatus exists to prevent.

---

## 17. Scientific / contract equivalence

No scientific output changed. Established three ways:

1. `src/engcore/domains/**` is **byte-identical** (§3).
2. Every optimization is a **same-answer** transformation, and each is tested
   against the path it replaces: `typing.Mapping` and `collections.abc.Mapping`
   are the same class; the `_compatible` memo computes exactly
   `dimension_of(a) == dimension_of(b)` on a miss, checked against the
   unmemoized form on eight unit pairs including Ohm's law composites and the
   degC/kelvin same-dimension-different-zero case; every fast path is checked
   against its general path.
3. **5,533 FULL tests pass**, including the contract guards, capability
   boundary, scientific truth, field suites and every domain suite.

The one contract that legitimately moved is the **digest of
`src/engcore/scientific`**, because this round changed files there. The two
merged benchmark rounds that pin it are re-pinned, with a comment naming the
pattern: that constant is a snapshot of a tree other rounds are entitled to
move, so it needs re-pinning whenever the Core does. Their substantive question
— *did this round edit production files* — is answered by their `git status`
half, which is lineage-independent and clean.

---

## 18. Domain regression tests

Run for regression detection only; no domain was edited.

| suite | result |
|---|---|
| electrical (DC, material, ngspice) | pass |
| battery | pass |
| CSTR / kinetics | pass |
| thermal scalar | pass |
| field / 2-D conduction + convergence | pass |

All within FULL's 5,533.

---

## 19–23. Final assurance

Run on the frozen candidate tree, in the required order.

| # | check | result |
|---|---|---|
| 1 | runtime/performance tests | pass |
| 2 | cache tests | 15 passed |
| 3 | sweep / failure isolation | 25 passed |
| 4 | fast-path equivalence | 19 passed |
| 5 | API classification | 6 passed |
| 6 | **FAST** | **4,985 passed**, 7 skipped, **0 failed** |
| 7 | **FULL** | **5,533 passed**, 7 skipped, **0 failed** |
| 8 | Contract Guard | 305 passed |
| 9 | Capability Boundary | 306 passed, 675 deselected |
| 10 | Scientific Truth | 293 passed, 3 skipped |
| 11 | field / field-profile suites | 124 / 147 passed |
| 12 | **Sprint 9 runtime mutations** | **9/9 killed**, CONTROL GREEN, 0 survivors |
| 13 | **certified 79-mutant harness** | **79/79 killed**, CONTROL GREEN (470 passed), **0 survivors** |
| 14 | installed wheel smoke | **313 passed** |
| 15 | certificate | **`certificate matches the tree` · OK** |
| 16 | domains untouched | tree digest identical, diff empty |
| 17 | working tree | clean |

### The certified harness was run TWICE, and the first run found a real defect

This is the part of the round worth reading.

**First run: 78/79.** `G10c` came back **`GREEN -- DECORATION`**. That mutation
deletes the non-finite check in `unwritable`'s general path, and it had gone RED
for as long as it had existed. The float fast path added earlier in this sprint
put a **second copy of the same refusal in front of it**, so deleting the first
became invisible — and a guard that is not decoration was reported as
decoration.

It was **not an equivalent mutation**, which is what makes it a defect rather
than a curiosity: `cls is float` is False for a float **subclass**, so the
deleted check is the only thing refusing a subclass NaN. G10c opens a real hole
the fast path does not cover. Nothing tested subclasses, which is exactly why
the shadowing went unnoticed.

Measured before removing it — applied and restored under a digest check — the
float fast path was worth **~11 µs on a 0.39 ms solve**, against a run-to-run
spread of 0.380–0.419 ms. Inside the noise. A duplicated refusal that buys
nothing measurable and blinds a certified mutation is a bad trade, so it was
removed: **one refusal, in one place, where it stays checkable.**

Two guards added so it cannot come back quietly: subclass NaN/Inf are now
tested, and a structural test asserts the NaN refusal appears **exactly once**
in `unwritable()` and that no exact-float fast path has returned.

**Second run, on the corrected tree: 79/79, 0 survivors, CONTROL GREEN.** Both
runs are recorded in the certificate's assurance block. A certificate that
reported only the run that passed would be a certificate about a tree nobody had
to fix.

---

## 24. Certificate

Reissued **once**, on the final tree, after the harness came back clean.

| | |
|---|---|
| files | 76 → **76** (nothing entered or left scope) |
| aggregate | `ecce1165d41ce27d…` → **`99c6ea577c938431…`** |
| `core` | 55 files, **CHANGED** — 5 modified, 0 added, 0 removed |
| `evidence_identity`, `harness`, `inference_admission`, `runtime_data`, `trust_registry` | **all byte-identical** |
| `diagnostic` | `false` |
| verification | **`certificate matches the tree` · OK** |

No digest was hand-edited.

---

## 25. Domain tree digest proof

```
baseline (f5369f0)  src/engcore/domains  ->  022ee84479a8735d0115e6c2f5e13c6e473d4f02
final    (HEAD)     src/engcore/domains  ->  022ee84479a8735d0115e6c2f5e13c6e473d4f02

git diff f5369f0..HEAD -- src/engcore/domains   ->   (empty)
domain files: 49
```

**DOMAIN FILES CHANGED: 0.**

A tree digest rather than a diff, because it covers all 49 files in one value
and cannot be satisfied by compensating edits.

---

## 26. Files changed

25 files, +2,549 / −148. **None under `src/engcore/domains`.**

| area | files |
|---|---|
| `src/engcore/scientific` | 5 — `consensus`, `results/immutable`, `results/result`, `serialization`, `units/quantity` |
| `tests/` | 4 new — caches, execution, fast paths, API surface |
| `benchmarks/core_runtime_finalization/` | 9 new — profiler, parallel bench, scaled bench, mutation harness, records, report |
| `benchmarks/{empirical,model_measurement}_validation/` | 4 — digest re-pin and regenerated gate artifacts |
| `certification/` | 1 — the reissued certificate |

---

## 28. Remaining Core blockers

**None for the freeze.** Three things are carried forward, and none of them
blocks it:

1. **Persistent-process execution is unbuilt.** Measured potential ~2.58× on a
   realistic payload. Deferred because the lifecycle, exception-transport,
   memory, ordering and conservative AUTO-policy guarantees do not exist yet.
   Part G's nine-point checklist is the specification for whoever builds it.
2. **`workers` is EXPERIMENTAL, not frozen.** Threads are 0.54×–0.97× of
   sequential. The knob stays, defaulted to 1 and keyword-only, classified so
   nobody freezes it by accident.
3. **The scientific-tree digest pin needs re-pinning whenever the Core moves.**
   It was re-pinned three times in this sprint chain. The constant is a
   snapshot of a tree other rounds are entitled to move; the gates' substantive
   question is answered by their `git status` half. Worth redesigning one day;
   not a freeze blocker.

### The runtime conclusion, stated explicitly

**The remaining tiny-solve framework share is predominantly required trust /
contract machinery. Further reduction is not justified in this sprint.**

Framework share moved 87.8 % → 86.7 % while the solve got 1.18× faster. That
near-immobility is the finding: what is left is unit validation on every
`Quantity`, the immutability walk, the writability boundary, provenance
construction and canonical serialization — each a contract this repository
exists to keep. The only two removable things found were a typing-alias lookup
and a duplicated dimensional comparison, and both are gone. Going further would
mean weakening a check, and the round that tried it already learned what that
costs: the one "optimization" that touched a refusal blinded a certified
mutation for 11 µs.

---

## 29. Ready for Core Freeze?

**YES**, with parallel execution deferred and recorded.

| criterion | status |
|---|---|
| domains untouched | **yes** — tree digest identical |
| hot path measured, redundancy removed, contracts intact | yes |
| trust / provenance / invariants unchanged | yes |
| parallel decision evidence-based | yes — deferred |
| failure isolation proven | yes |
| memory measured | yes — flat |
| caches audited | yes — and two unclear ed memos fixed |
| public API classified and pinned | yes |
| runtime mutants handled honestly | yes — 9/9, 2 recorded N/A |
| certified 79-mutant harness | **79/79, 0 survivors** |
| FAST / FULL / guards / wheel | all green |
| certificate | **OK** |
| tree clean | yes |

**FINAL VERDICT: CORE RUNTIME FINALIZATION COMPLETE — PARALLEL EXECUTION
DEFERRED.**
