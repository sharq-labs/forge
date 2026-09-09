# Benchmark scorecard v3

What the hard and battery benchmarks measure after the DEV truth repair, with
every denominator stated and every remaining gap named.

**Supersedes** `BENCHMARK_SCORECARD_V2.md`, which stays for lineage. v2's
figures were correct for the truth on disk at the time; §6 below says exactly
what moved and why.

**Nothing in `src/` changed in this round.** Every figure that moved, moved
because the answer key was repaired or because a new question is being asked.

---

## 1. Five questions, never merged

| question | field | what it asks |
|---|---|---|
| verdict | `verdict_match` | did Forge return the expected final verdict |
| primary mechanism | `declared_catcher_status` | did the mechanism the truth names decide the case |
| alternate mechanism | `alternate_fired` | did a mechanism the truth explicitly accepts decide it |
| what a refusal was | `catch_type` | declared, declared-alternate, coincidence, or undeclared |
| reason | `reason_match` | did the run report the reason the truth names |

plus two statements *about* the truth rather than about Forge:

| | |
|---|---|
| `review_status` | does the benchmark stand behind this case's truth |
| `oracle` | what kind of thing decided it |

A case can be `verdict_match=True` and `catch_type=COINCIDENTAL` at once, and
six still are.

---

## 2. Hard, development split (1400 cases)

### Verdict

| metric | value | denominator |
|---|---|---|
| exact verdict match | **1362/1400 (97.3%)** | all scored cases |
| catch rate | 1157/1157 (100.0%) | unsound cases |
| false accepts | **0/1157 (0.00%)** | unsound cases |
| false rejects | **0/243 (0.0%)** | sound cases |

Unchanged by this round. No verdict truth was revised.

### Mechanism

| metric | value | denominator |
|---|---|---|
| **primary catcher rate** | **1258/1293 (97.3%)** | cases declaring a mechanism |
| primary misses | 35 | — |
| alternate declared | 31 | cases declaring an alternate |
| **alternate catcher rate** | **29/31 (93.5%)** | those 31 |
| primary **or** alternate | **1287/1293 (99.5%)** | cases declaring a mechanism |
| cases declaring no mechanism | **107** | excluded from the rates above |

The primary rate is never inflated by an alternate. 29 of the 35 primary misses
are cases where a declared alternate caught it; the remaining 6 are below.

### Coincidence

| metric | value |
|---|---|
| **coincidental catches** | **6** |
| ids | `U00188` `U01000` `U01769` `U01830` `U01881` `U01940` |
| alternate-valid catches | 29 |
| undeclared-mechanism catches | **85** |
| **cases under review** | **6** — *exactly the six above* |

Every coincidence in the split is now either a declared alternate with a
recorded basis, or a case explicitly marked as truth the benchmark does not
stand behind. There are no unexplained coincidences left.

### Reason

| metric | value | denominator |
|---|---|---|
| reason-specified cases | **18** | — |
| reason matches | 18 | |
| reason mismatches | 0 | |
| **reason accuracy** | **18/18 (100.0%)** | reason-specified cases, **not 1400** |
| unknown-verdict cases | 202 | expected `INSUFFICIENT_EVIDENCE` |
| unknown-reason specified | 18 | of those 202 |
| unknown-reason accuracy | 18/18 (100.0%) | those 18 |

**1382 of 1400 cases still have no machine-checkable reason.** `reason` is
human prose and no scorer can read it. The 18 that do were supplied by the
screen adjudication, not generated from Forge's output.

### Oracle

| class | cases |
|---|---|
| `GENERATOR_CONSTRUCTION` | **1378** |
| `EXPERT_ADJUDICATED` | 18 |
| `UNSOURCED` | 4 |

98.4% of DEV truth was decided by the generator that drew the case. That is not
independent of this repository and is never reported as though it were.

---

## 3. Battery (400 cases) — unchanged

| metric | value |
|---|---|
| exact verdict match | 389/400 (97.2%) |
| false accepts / rejects | 0/219 · 11/181 (6.1%) |
| primary catcher rate | 389/400 (97.2%) |
| coincidental catches | **0** |
| alternates declared | 0 |
| reason-specified | 0 |
| oracle | `GENERATOR_CONSTRUCTION` × 400 |

Battery truth needed no repair: every case names a mechanism, none is caught by
an undeclared one. It supports **verdict and catcher** accuracy today, and
**not** reason accuracy — no battery case carries a machine-checkable reason,
and none was invented.

The 100% catch rate remains unearned and disclosed at the point of measurement:
no battery case can reach SUPPORTED on the whole report, so `score_hard.py`
scopes battery verdicts to the four battery models and says so in its source.

---

## 4. Family audit, after repair

| family | DEV | verdict ok | primary catcher | coincidental | under review |
|---|---|---|---|---|---|
| `geometry_conflict` | 87 | 87 | **87/87** | **0** | 0 |
| `compound:horizon+tmax` | 49 | 49 | 18/49 | **2** | 2 |
| `adv_unsound:small_overshoot` | 50 | 50 | 45/49 | **4** | 4 |
| `runaway` | 26 | 26 | **25/25** | 0 | 0 |

`compound:horizon+tmax` shows 18/49 primary because the *lead* mechanism is the
Fourier screen and 31 cases are decided by the second injected defect instead —
29 of them by a declared alternate. Its primary-or-alternate figure is 47/49.

---

## 5. What is still wrong

| gap | size | why it was not repaired |
|---|---|---|
| **85 unsound DEV cases declare no mechanism at all** | 85 | truth says nothing to repair *to*; determining a catcher would mean reading Forge's output back in as truth |
| **1382 DEV cases have no machine-checkable reason** | 1382 | `reason` is prose by design; supplying reasons would mean inventing them |
| **6 cases whose declared catcher provably cannot fire** | 6 | the right catcher is not determinable; flagged `needs_review`, oracle `UNSOURCED` |
| **`geometry_conflict` in the sealed partition still names `biot_number`** | ~38 | hold-out firewall — DEV only. A future regeneration must carry the corrected catcher |
| **1378 of 1400 truths are generator-constructed** | 1378 | circular by construction; the fix is an independent oracle, not a truth edit |
| **the hold-out is opened** | 600 | see `HOLDOUT_STATUS.md`; no reshuffle restores blindness |

---

## 6. What moved, and why

| figure | v2 | v3 | cause |
|---|---|---|---|
| exact verdict match | 1362/1400 | 1362/1400 | — |
| false accepts | 0 | 0 | — |
| primary catcher rate | 1183/1293 (91.5%) | **1258/1293 (97.3%)** | **ground-truth correction** — `geometry_conflict` catcher was stale |
| coincidental catches | 110 | **6** | 75 truth correction + 29 newly-declared alternates |
| alternate catcher rate | *not measured* | 29/31 | **scorer-semantic change** + new truth |
| reason accuracy | 0/0 (n/a) | **18/18** | **new truth** from the screen adjudication |
| under-review cases | *not measured* | 6 | **new truth**: cases the benchmark no longer stands behind |
| battery, everything | unchanged | unchanged | — |

**No runtime improvement occurred and none is claimed.** `git diff` over `src/`
across this round is empty.

### The sentence that must accompany the headline

> Hard dev is 1362/1400 with 0 false accepts, and its declared mechanism fires
> in 97.3% of the cases that name one. 107 unsound cases name no mechanism at
> all, 1382 carry no checkable reason, six are flagged as truth we do not stand
> behind, and 98% of the answer key was written by the generator being scored.

---

## 7. Claim audit

| claim | status | precise reading |
|---|---|---|
| "100% catch rate" | **METRIC-SPECIFIC** | true of verdicts on unsound cases; says nothing about mechanism |
| "97.3%" (verdict) | **ACCURATE** | 1362/1400 exact verdict match |
| "97.3%" (catcher) | **ACCURATE, different metric** | 1258/1293 — same number, different denominator, do not conflate |
| "FA = 0" | **ACCURATE** | 0/1157, and 2 of those came from truth correction in the prior round |
| "coincidental = 110" | **SUPERSEDED** | now 6, after 75 truth corrections and 29 declared alternates |
| "declared-catcher 91.5%" | **SUPERSEDED** | now 97.3% |
| "correctly caught" | **MISLEADING** unqualified | say which of verdict / primary / alternate is meant |
| "all cases caught" | **MISLEADING** | 85 refusals are by an undeclared mechanism |
| "independent hold-out" | **MISLEADING** | opened; see `HOLDOUT_STATUS.md` |

Historical claims are not deleted. `results_hard.json` carries current figures,
`ADJUDICATIONS.json` carries every previous value beside its replacement, and
`HOLDOUT_OPENINGS.log` carries the superseded hold-out figure with the digest
that dates it.
