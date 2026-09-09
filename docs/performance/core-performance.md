# Forge Core performance — findings, and how to reproduce them

**Round result: PERFORMANCE HEALTHY.** No blocker remains. Five defects were
found by measurement, fixed, and guarded; scientific truth is bit-identical
throughout.

Reproduce everything here with `python benchmarks/performance/run_suite.py`.
Read `benchmarks/performance/README.md` first — in particular the section on
what this machine's own variance is, because it determines which of these
numbers are meaningful.

---

## 1. What the round actually found

The headline is not a number, it is a **ratio**. Profiling one real
electro-thermal benchmark case, attributed by owner of *self* time:

| owner | before | after |
|---|---|---|
| pint (unit library) | **59.2 %** | 28.5 % |
| interpreter / builtins | 20.7 % | 17.9 % |
| Forge scientific core | 3.0 % | 18.6 % |
| **Forge domains/systems — the actual physics** | **2.2 %** | **12.4 %** |
| Forge units layer | 7.1 % | 8.1 % |
| Forge boundary (mcp) | 0.4 % | 2.6 % |

The physics was **2.2 %** of the run. Everything else was bookkeeping, and
almost all of it was Forge asking a third-party unit library the same question
about the same handful of strings, tens of thousands of times per case.

The physics is now 12.4 % — not because it got slower, but because the
bookkeeping around it shrank about fivefold.

## 2. The five defects

| # | Defect | Root cause | Fix |
|---|---|---|---|
| 1 | `normalize_unit` parsed a unit string and then **formatted it back to a string** | `str(registry().Unit(text))` | memoize; return the parse |
| 2 | `dimension_of` **parsed the same string twice** | called `normalize_unit`, then re-parsed its output to reach `.dimensionality`, which the first parse already held | one parse returns both |
| 3 | `Quantity.to` ran a full conversion **to the unit it already had** — 549 of 552 calls (99.5 %) in one real run | no identity check | string compare, return `self` |
| 4 | Four O(n²) scans in record construction | `names.count(name)` per element (×9 sites), a set rebuilt inside the comprehension consuming it, Kahn's algorithm without an in-degree count, membership against a tuple | `Counter`, hoisted set, in-degree walk, hashed set |
| 5 | Ordering a graph with **no** prerequisites built five maps to discover there was nothing to order | no fast path | early return |

## 3. Measured effect

Machine: Intel i7-14650HX (16C/24T), 31.7 GB, Windows 11, **Balanced power**.
Round-to-round spread of the median: **8.6 %** for `normalize_unit`, **10.5 %**
for a `Quantity` construction, **2.1 %** at ~12 ms. Nothing below ~15 % on a
micro-operation is claimed as an improvement.

| measurement | before | after | × |
|---|---|---|---|
| **real electro-thermal case** | 55.4 ms | **11.2 ms** | **4.9** |
| **hard-dev scoring run (1400 cases)** | 33.6 s | **6.8 s** | **4.9** |
| **core verdict path, MEDIUM, no solver** | 6.87 ms | **0.50 ms** | **13.8** |
| FAST test suite | 36 s | 17 s | 2.1 |
| SCIENTIFIC test suite | 131 s | 67 s | 2.0 |
| performance suite itself | 8 min | 15 s | 32 |
| validity assessment, 10,000 unknowns | 3082 ms | 1.70 ms | 1810 |
| consensus completeness, 10,000 outputs | 675 ms | 1.32 ms | 512 |
| dependency order, 5,000 chained | 2106 ms | 6.00 ms | 351 |
| validation report, 10,000 checks | 684 ms | 2.63 ms | 260 |
| `magnitude_in`, same unit | 41.8 µs | 0.16 µs | 258 |
| applicability, 1,000 conditions | 125 ms | 1.94 ms | 65 |

**One thing got slower and it is not hidden.** A *fan* dependency graph — many
conditions depending on one prerequisite — costs about 1.8× the old rescan,
because it has edges and takes the index path. At 1,000 conditions that is
0.45 ms absolute; at the sizes anything declares, under 20 µs. It is the price
of the chain no longer being quadratic.

## 4. Scaling

Every subsystem measured at 10 / 100 / 1k / 10k. All are now linear or better in
their input. The four that were quadratic are named above; nothing else was.

Cold start is **534 ms**, of which **500 ms is interpreter import** (largely
building pint's registry, a known ~160 ms) and **34 ms is the first request**.
Cold start is therefore an import problem, not a Forge-overhead problem, and
process reuse removes essentially all of it.

Memory grows linearly with workload: the end-to-end path peaks at 19.8 KiB at
size 5, 88 KiB at 50, 347 KiB at 200 and 1.67 MiB at 1,000 — about 1.7 KiB per
unit of work at every scale, with no superlinear retention.

## 5. The one cache, and why it is allowed

This repository's rule is that a cache may exist only where its identity can be
*proven* complete. Exactly one was added.

`_canonical_unit(text)` maps a unit string to its canonical spelling and
dimensionality. It is a pure function of the string and the registry, and **the
registry is a constant for the life of the process**: built once behind an
`is None` guard with no path anywhere that replaces it, sealed before it is
published, with every mutating route refused and that enumeration already
exercised by `test_core_guards`.

So the key is the entire varying input. Nothing about a model, threshold,
context, solver or verdict participates in the value — it caches a *lexical*
fact about a unit string, not a scientific conclusion. It is bounded at 4,096
entries; one real case touches 37. `tests/test_unit_memoization.py` computes
every unit cold, warm and cold again and requires all three to agree.

## 6. Concurrency readiness

Assessed, not changed. 12 threads driving the core's read paths on a cold cache:
**0 errors, all 12 produced identical results**, cache converged cleanly.

| state | assessment |
|---|---|
| `_canonical_unit` / `_canonical_dimensionality` (`lru_cache`) | **safe.** CPython's C `lru_cache` locks its bookkeeping; a race duplicates a pure computation, and both answers are equal |
| `_ATOMIC_TYPES` in `immutable.py` (a set `freeze` adds to) | **safe.** `set.add` is atomic under the GIL and the addition is idempotent |
| `_REGISTRY` lazy singleton | **latent init race, pre-existing.** Two threads first-calling `registry()` concurrently could both build a registry; the loser's quantities would carry a back-reference to a discarded one. Not introduced by this round and not fixed in it — closing it is a `threading.Lock` and a decision about initialization semantics, which belongs to a round scoped for concurrency |

No shared mutable state was introduced that a scientific verdict depends on.

## 7. Regression protection

**Deterministic guards** (`tests/test_core_performance_guards.py`, 12 tests,
0.5 s, in FAST): call counts and growth exponents, both reproducible on any
machine. Verified non-vacuous — with the four fixes reverted in a scratch tree,
seven guards go red.

**Not gated: absolute latency.** On a mobile CPU under Balanced power a
wall-clock threshold would describe the machine. Baselines live in
`benchmarks/performance/results/` with the commit and machine record attached,
for a human to compare.

## 8. Scientific truth

Unchanged at every step, which is the only acceptable outcome:

| | before | after |
|---|---|---|
| Hard dev | 1360/1400, FA 2 (`U00204`, `U01001`), FR 0 | identical |
| Battery | 389/400, FA 0, FR 11 | identical |
| `cases_hard` digest | `2f0a48db…` | identical |
| `cases_battery` digest | `32a7bff3…` | identical |
