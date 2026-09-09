# Forge Core performance suite

> **Scientific benchmark:** *is the answer correct?* — `benchmarks/hard`
> **Performance benchmark:** *how expensive is Forge itself?* — this directory
>
> They are separate on purpose. A scientific number that moves is a correctness
> event. A performance number that moves is usually a machine event. Mixing them
> makes both unreadable, so nothing here imports from `benchmarks/hard`, reads a
> case file, or produces a verdict.

## Run it

```bash
python benchmarks/performance/run_suite.py              # everything (~8 min)
python benchmarks/performance/run_suite.py units freeze # selected modules
python benchmarks/performance/run_suite.py --stability  # machine variance first
```

Results land in `results/*.json`, each carrying the machine record and commit
that produced it. A results file without that context is not evidence.

**Run `--stability` before believing any before/after comparison.** It reports
what this machine's own answer does when nothing changes at all.

## What is measured, and how

| | |
|---|---|
| **COLD** | first meaningful call in a *fresh process*, imports included — measured in a subprocess, because cold cannot be faked in a warm one |
| **WARM** | steady state after warm-up; interpreter import time is never inside it |
| **Percentiles** | P50 / P95 / P99, min, max, sample count. Never one average — a mean hides the distribution, and the distribution is the point |
| **P99** | reported only at ≥ 100 samples; below that it is two data points wearing a percentile's name |
| **GC** | collected before, disabled during. A collection inside one sample is exactly the event that produces an unreproducible P99 |
| **Memory** | `tracemalloc` peak on the large scales |
| **Call counts** | `CallCounter` — machine-independent, and the basis of every deterministic guard |

Workloads are **deterministic by construction**: no RNG, no clock, no case
files. The same workload is built on every machine, so two result files are
comparable without anyone having to check what was measured.

## Scale classes

`TINY / SMALL / MEDIUM / LARGE / STRESS`, mapped by each subsystem onto its own
axis — "large" for a dependency graph and "large" for a provenance record are
not the same number of anything. `STRESS` is deliberately past anything
scientifically plausible: it exists to expose a growth curve, not to represent a
workload, and the report says so wherever it is quoted.

## Reading a number honestly

This machine is a **mobile i7-14650HX on the Balanced power scheme**. Measured
round-to-round variation of the *median*:

| operation | spread |
|---|---|
| `normalize_unit` (~12 µs) | **8.6 %** |
| `Quantity` construction (~6 µs) | **10.5 %** |
| `assess` over 100 conditions (~12 ms) | **2.1 %** |

So a claimed improvement below roughly **15 % on a micro-operation** is not
distinguishable from the machine breathing. Larger operations are far steadier.

**This is why the regression guards are call counts, not milliseconds.** A count
is reproducible in CI, under a debugger, on any machine; a wall-clock threshold
tighter than the variance above is a false-alarm generator, and one loose enough
to survive it catches little. Timing here is evidence for a human, not a gate.

## The headline number

`bench_end_to_end_core.py` runs one complete core verdict path with **no solver
of any kind**:

```
ScientificProblem -> applicability -> validity -> result
                  -> validation -> consensus -> provenance -> serialization
```

That is Forge's own cost to turn a computed answer into an attributable,
checked, serialized scientific record. It is deliberately *not* comparable to a
benchmark case time, which includes the fixed-point solve.

## Files

| File | Measures |
|---|---|
| `common.py` | timing, percentiles, memory, call counting, deterministic fixtures |
| `bench_units.py` | unit normalisation, dimensionality, `Quantity` operations |
| `bench_problem.py` | `ScientificProblem` construction and serialization |
| `bench_applicability.py` | `ValidityDomain.assess`, flat and chained, passing and failing |
| `bench_dependency_dag.py` | topological ordering: flat / chain / fan |
| `bench_validity.py` | the `ValidityAssessment` record itself |
| `bench_evidence.py` | report construction and per-read re-validation |
| `bench_consensus.py` | comparison over routes × required outputs |
| `bench_provenance.py` | typed input encoding, metadata breadth vs depth |
| `bench_serialization.py` | `to_dict` / `to_json` / `from_dict` / writability scan |
| `bench_freeze.py` | `freeze` and `detach`, breadth vs depth |
| `bench_end_to_end_core.py` | the headline path, plus per-stage attribution |
| `run_suite.py` | sequential runner and stability report |

`bench_units.py` was **added because measurement demanded it**, not because a
plan listed it: a reconnaissance profile attributed ~61 % of a real
electro-thermal case to unit handling before any harness existed.
