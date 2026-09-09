# Benchmark scorecard v2

> **SUPERSEDED by `BENCHMARK_SCORECARD_V3.md`.** Kept for lineage. The
> figures below were correct for the truth on disk when they were taken;
> the DEV truth repair afterwards moved the declared-catcher rate from
> 91.5% to 97.3% and coincidental catches from 110 to 6, without moving a
> single verdict. v3 §6 decomposes exactly what changed and why.


What the hard and battery benchmarks actually measure after this round, with
every denominator stated, and what changed for which of the three possible
reasons.

**The distinction this document exists to hold.** Three things can move a
benchmark number and they look identical from outside:

| | |
|---|---|
| **runtime improvement** | the tree got better |
| **ground-truth correction** | the answer key changed |
| **scorer-semantic change** | the question changed |

This round contains one of the second and one of the third, and **none of the
first**. No file under `src/` was modified.

---

## 1. Three questions, never merged

A scored case now answers three independent questions:

| question | field | what it asks |
|---|---|---|
| verdict correctness | `verdict_match` | did Forge return the expected final verdict |
| declared-catcher correctness | `declared_catcher_status` | did the mechanism the truth names decide the case |
| what a refusal actually was | `catch_type` | declared, an explicitly-permitted alternate, or a coincidence |

A case can be `verdict_match=True` and `catch_type=COINCIDENTAL` at once. That
combination is what the old single-enum scorer could not express, and there are
**110** of them in the development split.

### Vocabulary

`declared_catcher_status` ∈ `FIRED` · `HELD` · `NOT_FIRED` · `NOT_DECLARED`
`catch_type` ∈ `DECLARED` · `ALTERNATE_VALID` · `COINCIDENTAL` · `UNDECLARED` · `NONE` · `NOT_APPLICABLE`
`reason_match` ∈ `MATCH` · `MISMATCH` · `UNSPECIFIED` · `NOT_APPLICABLE`

`ALTERNATE_VALID` is returned **only** when the case lists the condition in
`acceptable_catchers`. No case does today, so it is never inferred from the
fact that something else happened to fail — that inference is precisely how a
coincidence becomes a success.

---

## 2. Hard, development split (1400 cases)

| metric | value | denominator is |
|---|---|---|
| exact verdict match | **1362/1400 (97.3%)** | all scored cases |
| catch rate | **1157/1157 (100.0%)** | unsound cases |
| false accepts | **0/1157 (0.00%)** | unsound cases |
| false rejects | **0/243 (0.0%)** | sound cases |
| **declared-catcher rate** | **1183/1293 (91.5%)** | cases that declare a mechanism |
| declared-catcher missed | **110** | — |
| cases declaring no mechanism | **107** | excluded from the rate above |
| **coincidental catches** | **110** | — |
| alternate-valid catches | 0 | none declared |
| undeclared-mechanism catches | 85 | refusals truth names no mechanism for |
| reason-specified cases | **0** | — |
| reason accuracy | **0/0 (n/a)** | see §5 |

**Read the last four rows before quoting the first four.** A 100% catch rate
and 0 false accepts are true statements about verdicts, and 110 of those
verdicts are right for a mechanism the truth does not name.

## 3. Battery (400 cases)

| metric | value |
|---|---|
| exact verdict match | 389/400 (97.2%) — **unchanged** |
| catch rate | 219/219 (100.0%) |
| false accepts | 0/219 (0.00%) |
| false rejects | 11/181 (6.1%) |
| declared-catcher rate | **389/400 (97.2%)** |
| cases declaring no mechanism | **0** |
| coincidental catches | **0** |
| reason-specified cases | 0 |

Battery truth is materially healthier on the catcher dimension: every case
names a mechanism and none is caught by an undeclared one. Its verdicts did not
move in this round, as required.

The 100% catch rate remains **unearned and disclosed at the point of
measurement**: `run_self_heating_discharge` accepts no applicability
declaration for the body it marches, so the lumped model is honestly UNKNOWN in
every battery report and no case can reach SUPPORTED on the whole report.
`score_hard.py` scopes battery verdicts to the four battery models and says so
in its own source.

---

## 4. Family truth audit (Phase D / P)

Every family carrying a coincidental catch, classified. Verdicts are correct in
all three; what is wrong is the field naming the mechanism.

| family | total | verdict ok | catcher fired | coincidental | classification |
|---|---|---|---|---|---|
| `geometry_conflict` | 87 | 87 | **12/87** | **75** | `WRONG_DECLARED_CATCHER` |
| `compound:horizon+tmax` | 49 | 49 | **18/49** | **31** | `MULTIPLE_VALID_CATCHERS` |
| `adv_unsound:small_overshoot` | 50 | 50 | 45/49 | 4 | `WRONG_DECLARED_CATCHER` |
| `runaway` | 26 | 26 | 25/25 | 0 | `CORRECT_TRUTH` (after U00204) |

### `geometry_conflict` — 75 cases, declared catcher is stale

`shape_geometry_conflict` injects a disagreement between two routes to the
characteristic length, deliberately outside `GEOMETRY_AGREEMENT_FACTOR` (3),
and its own reason prose says so: *"Two routes to one quantity that disagree
must not be silently reconciled."* The condition that detects exactly that is
`geometry_route_ratio`, whose bounds are 1/3 to 3. The declared catcher says
`biot_number`, which is computed *from* the characteristic length and cannot
detect a disagreement about it.

So these 87 cases are detected by the **right** mechanism and their
`should_be_caught_by` names the wrong one — most likely a field written before
`geometry_route_ratio` existed.

**Not corrected in this round.** The family spans the sealed partition, so a
family-wide field edit touches hold-out cases (stop condition 6), and a third
family showing a systematic generator error is itself a stop condition (3). It
is reported here and is permanently visible in the scorecard as 75 coincidental
catches rather than hidden inside a catch rate.

### `compound:horizon+tmax` — 31 cases, a recorded alternate the scorer cannot read

The landed `2026-09-09.internal-fourier-number.screen` event searched all 70
cases naming `internal_fourier_number` and found that 47 had an independent
violation — `operating_temperature_utilization` (40),
`reference_temperature_utilization` (34), `radiation_to_convection_ratio` (3) —
and **kept** `NOT_SUPPORTED` on that basis. That is an accepted alternate
mechanism, decided by a human and recorded.

It is recorded **in prose**. The log lists only the 23 cases whose verdict
moved, so no scorer can read which alternates were accepted for the other 47.
These 31 are therefore scored as coincidental when they are in fact
`MULTIPLE_VALID_CATCHERS`.

**The repair is a schema field, not a truth change**: populating
`acceptable_catchers` on those cases from the alternates the event already
names. `scoring.py` reads that field today. Not applied here for the same two
stop conditions.

### `adv_unsound:small_overshoot` — 4 cases

`U01000`, `U01769`, `U01940`, `U01830`. Endpoint at or below the ceiling, so
`operating_temperature_utilization` is correctly satisfied; refused anyway by
an unrelated condition. Same class as `geometry_conflict`: a
`should_be_caught_by` defect, not an `expected_verdict` defect. Left for its
own adjudication, and named in the U01001 event's family audit.

---

## 5. Reason accuracy: honestly undefined

**0 of 1400 cases carry a machine-checkable expected reason.**

`ground_truth.reason` is prose written for a human — *"Over the ceiling by
0.174 K. Small, and still over."* Nothing Forge emits can be compared to it
without a heuristic, and a heuristic that guessed would manufacture exactly the
false precision this round exists to remove.

So every case scores `UNSPECIFIED`, the denominator prints as `0/0 (n/a)`, and
Forge is not penalised for missing a reason the benchmark never defined. The
optional fields a future revision can populate — `acceptable_catchers`,
`expected_unknown_reason` — are read by the scorer and carried by no case.

The machine-checkable proxy that *does* exist is the declared catcher, and it
is reported separately above because it is a different question.

---

## 6. Old score vs new score, decomposed

| figure | before round | after round | why it moved |
|---|---|---|---|
| exact verdict match | 1360/1400 | **1362/1400** | **ground-truth correction** (2 cases adjudicated) |
| false accepts | 2 | **0** | **ground-truth correction** — not a runtime improvement |
| catch rate | 1157/1159 | 1157/1157 | ground-truth correction (denominator moved: 2 cases became sound) |
| false rejects | 0/241 | 0/243 | ground-truth correction (denominator only) |
| declared-catcher rate | *not measured* | 1183/1293 (91.5%) | **scorer-semantic change** |
| coincidental catches | *not measured* | 110 | **scorer-semantic change** |
| battery, all verdict figures | 389/400 | 389/400 | unchanged |

**No runtime improvement occurred in this round, and none is claimed.** `git
diff` over `src/` between the round's start and end is empty. Forge's output
for `U00204` and `U01001` is byte-identical to what it was before the
adjudications; the golden traces assert the same numbers they asserted then.

### The sentence that must accompany the headline

> Hard dev is 1362/1400 with 0 false accepts. Two of those cases became correct
> because their answer key was corrected, not because the tree changed, and 110
> of the remaining correct verdicts are reached by a mechanism the benchmark
> does not name.

---

## 7. Claim audit (Phase T)

| claim | status | note |
|---|---|---|
| "caught 49/50" (small_overshoot) | **superseded** | 45/49 by the declared catcher; 4 coincidental |
| "catch rate 99.8%" | **historical** | true of the pre-adjudication truth; now 100% and still not a defect-detection rate |
| "false accepts = 2" | **historical** | now 0, by truth correction |
| "97.1%" | **historical** | now 97.3%, by truth correction |
| "independent hold-out" | **misleading** | the hold-out is OPENED; see `HOLDOUT_STATUS.md` |
| battery "100% catch rate" | **accurate but unearned** | disclosed in `score_hard.py`'s own source |
| "all defects caught" | **never true** | 110 dev cases are refused by an undeclared mechanism |

History is not rewritten. `results_hard.json` carries the current figures;
`HOLDOUT_OPENINGS.log` carries the superseded hold-out figure with the digest
that dates it; `ADJUDICATIONS.json` carries every previous verdict beside its
replacement.
