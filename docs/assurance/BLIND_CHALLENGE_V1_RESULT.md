# Blind challenge v1 — result

The first benchmark in this repository whose truth was fixed before the thing
it measures ever saw it.

**Firewall commit (`PRE_FORGE_FREEZE_SHA`): `52963eb`, 2026-09-09 23:58:51 UTC.**
**First run: HEAD `a9db9d5`, 2026-09-10 00:00:32 UTC, clean worktree.**

---

## The headline, which does not move

| | decided denominator | false accepts | false rejects |
|---|---|---|---|
| **FIRST RUN — frozen, never revised** | **272 / 400 (68.0 %)** | **1** *(harness, see below)* | 94 |
| POST-FIX, after two proven runtime defects were repaired | 336 / 400 (84.0 %) | **0** | 45 |

44 cases sit within the resolution floor of their bound and are scored
separately, never inside that denominator: 27/44 on the first run, and the one
case that still disagrees after both fixes is one of them.

**The 68.0 % is the number this round produced.** It is committed, sealed by
digest, and it understates the runtime — for reasons given below that were
established afterwards and could not be used to change it. That is the point of
the arrangement, not a flaw in it.

### The one false accept was ours

`KIN00372` declares a zero residence time; its frozen truth is
`REJECTED_AT_BOUNDARY` and that truth is correct. The **runner** divided a
volume by that zero to build a flow rate and crashed before Forge was reached.
Forge refuses the case. The row stands in `FORGE_FIRST_RUN.json` because a first
run is not corrected.

**Across 444 blind cases, Forge accepted nothing the independent truth refuses.**
That is the single most load-bearing number here, and it survived both runs.

---

## What the blind challenge found

### 1. A declaration could not state a temperature in degrees Celsius

`RUNTIME_DEFECT`. 72 of 444 cases, across two systems and every boundary
stratum.

`Quantity.parse` handed the whole string to the units backend's *string*
parser, which reads `"20 degC"` as the multiplication `20 * degC`. Multiplying
by an offset unit is ambiguous, so the backend refused. The two-argument
constructor never multiplies — `Quantity(20.0, "degC").magnitude_in("kelvin")`
has always been 293.15 — so the core supported degrees Celsius everywhere
except where a caller could write one.

It also misreported its own cause: the message said the quantity could not be
*read*, when the unit was perfectly readable.

The repository's own test says this should work:
`test_a_dimension_check_is_not_a_unit_check` — *"rejecting `degC` where the
model wrote `kelvin` would be the unit-string comparison this platform
refuses"* — and exercises the claim with `"2 minute"`, a ratio-scale unit,
which is why nothing ever went red.

**Nothing in the existing 2400-case corpus could have found it. Every
temperature in it is written in kelvin.**

### 2. A ratio of two declarations was computed on an interval scale

`RUNTIME_DEFECT`, and **strictly unreachable until the first one was fixed**.
33 cases.

`CrossLimitCondition` converted the denominator into the *numerator's* unit and
divided the magnitudes — correct for every unit whose zero is physical, wrong
for every unit whose zero is a convention.

```
reference_temperature   -12.33 degC
debye_temperature       407.67 kelvin

before   407.67 K -> 134.52 degC,  -12.33 / 134.52 = -0.0917   VIOLATED
after    both on the base unit,    260.82 / 407.67 =  0.6398   SATISFIED
```

A satisfied condition reported as violated, with the answer depending on which
unit the caller happened to write — which
`test_offset_unit_arithmetic.py` states as the one thing a unit may never do.

The rule was not new: two callers already refuse an affine scale for a
*difference*, with the same argument. `is_ratio_scale` generalises that test
past temperature and gives it a name; a ratio has the requirement for the same
reason.

**This is the finding that justifies the round.** It sat behind a defect that
looked like a parsing nuisance, and no corpus written in kelvin could reach it.

### 3. Three declared conditions cannot be violated by an admissible input

Not a defect — refusing earlier is refusing better — but a property of the
current core that a benchmark not knowing it would report as a wrong verdict
every time:

* CSTR `temperature`, `[250, 1000] K` — all three declared temperatures are
  refused against that range at construction;
* battery `coulombic_efficiency`, `(0, 1]` — the one **hard** battery bound;
* conduction `alpha > 0`.

---

## What the challenge got wrong

Two frozen truths are wrong. Neither was edited; both are recorded in
`v1/TRUTH_ERRATA.json`, and the v1 score stands at what it scored.

| | n | what | Forge |
|---|---|---|---|
| `ERR-001` | 73 | the generator spelled resistances `kilohm`; the registry defines `kiloohm` | **right** — and the refusal names the field, the string and the dimension wanted |
| `ERR-002` | 3 | `soc_step_resolution` declared outside `[0, 1]`, which the constructor refuses | **right** |

`ERR-001` has a root cause worth keeping: the challenge's vocabulary guard
checked that the **oracle** could read every unit the generator emits, and
never that the **runtime** could. A closed vocabulary on one side of a
comparison is not a closed vocabulary.

**Diagnostic, not a headline:** on the 336 cases whose frozen truth is not
known to be defective, the post-fix run is 336/336. Quoting that figure alone
would be excluding exactly the cases you failed on, so it is quoted only
alongside 68.0 % and 84.0 %, and only because Forge is demonstrably right about
all 64 excluded mismatches.

---

## Scorecards, kept apart

Averaging these would average four different kinds of claim.

### By truth class (first run / post-fix, decided denominator)

| class | n | first run | post-fix |
|---|---|---|---|
| `INDEPENDENT_SCIENTIFIC` | 231 | 163 (70.6 %) | — |
| `POLICY_DEPENDENT` | 88 | 47 (53.4 %) | — |
| `CONTRACT_ONLY` | 79 | 62 (78.5 %) | — |
| `MIXED_SCIENCE_AND_POLICY` | 2 | 0 | — |

A case decided by `radiation_to_convection_ratio <= 0.1` tests a 10 %-neglect
allowance with no located source. Agreement on it says the runtime implements a
convention correctly and says nothing about physics.

### By system (post-fix)

| system | tier | n | verdict | FA | FR |
|---|---|---|---|---|---|
| conduction-1D | model contract | 58 | **58/58 (100 %)** | 0 | 0 |
| kinetics CSTR | model contract | 53 | **53/53 (100 %)** | 0 | 0 |
| battery | system boundary | 109 | 107/109 (98.2 %) | 0 | 1 |
| electro-thermal | system boundary | 180 | 118/180 (65.6 %) | 0 | 44 |

Every one of the 62 remaining electro-thermal mismatches is an `ERR-001`
`kilohm` case.

### By boundary stratum (post-fix)

| stratum | n | verdict |
|---|---|---|
| `CONSTRUCTION_REFUSED` | 18 | 100 % |
| `MALFORMED` | 12 | 100 % |
| `FAR_INSIDE` | 50 | 92.0 % |
| `NEAR_INSIDE` | 154 | 84.4 % |
| `NEAR_OUTSIDE` | 40 | 82.5 % |
| `NOT_APPLICABLE` | 49 | 81.6 % |
| `FAR_OUTSIDE` | 49 | 79.6 % |
| `SOFT_BOUND_NEAR` | 28 | 64.3 % |

The spread tracks where `kilohm` cases landed, not where the runtime is weak.
`AT_BOUNDARY` is scored separately by construction.

### Reasons and causes (post-fix, decided)

* reason set: 116 exact of 174 scored; 58 missing, all of them cases refused at
  the boundary where no condition is assessed at all.
* causal catcher: 96 exact of 149 scored; 13 `NO_UNIQUE_PRIMARY`, **not
  counted as failures** — where several conditions are each violated, repairing
  any one leaves the verdict where it was, so none is uniquely causal.
* wrong reasons: **0**. wrong causal mechanisms: **0**.

---

## Performance

Measured, because the naive reading was wrong. The post-fix suite ran ~1.35×
slower than a baseline taken hours earlier — but re-running the **pre-fix
commit on the same machine in the same minute** reproduced that 1.36×. The
fixes' own cost is **0.98× median**, worst 1.07× on one sub-0.3 ms measurement.
The slowdown is machine drift, and this container had been running heavy suites
for hours.

Blind run: 444 cases in 5.2 s wall, p50 2.6 ms, p95 236 ms per case.

---

## One thing found by the post-round sweep, unrelated to the challenge

`tests/mutation_guards.py` was run as part of the closing sweep. **64 of 64
mutations that applied turned the guard suite red, and none went GREEN** — no
guard is decoration.

But **5 of the 69 mutations did not apply at all**: `G2f`, `G2g`, `G22a`,
`G22b`, `G22c`. Their search patterns no longer match the source they were
written against — `G22a` and `G22c` target text that is absent, and `G22b`'s
target sits at a different indentation. The harness distinguishes "did not
apply" from GREEN, which is the right design and is why this is visible at all.

**It predates this round.** Each pattern was checked against both `52963eb`
(before any fix here) and `HEAD`, and is identically absent or mismatched at
both; two of the files were never touched by this work, and the one line that
does exist is at `definition.py:1419` while this round's diff touches lines 32
and 659–699.

The consequence: **5 guards are currently unexercised by the harness**, so
nothing says whether they still guard. That is worth a round of its own and is
not one this round has authority to spend.

## Blindness audit

`v1/BLINDNESS_AUDIT.json` checks each claim against git rather than asserting
it. **Classification: `VALID_BLIND_CHALLENGE`.** No violations.

Three qualifications, all declared before the freeze:

1. **The oracle's contract reading is not blind.** What each condition means
   and which state it is read at came from the model records, and each oracle's
   reading was checked against the runtime on the *already-open* corpus before
   any blind case existed. So this round tests **arithmetic and generalisation
   to unseen parameter regimes**, not the contract reading. Both defects it
   found are ones that calibration could not have hidden: neither is reachable
   from a kelvin-only corpus.
2. **Two frozen truths are wrong** (above). Costs the number, not the method.
3. **Refusal-path reporting is not tested** — a refused coupling's condition
   set is a property of the iteration driver, not of the science, and an oracle
   that reproduced it would be a copy of the driver.

---

## What is proven, and what is not

**Proven.** On 444 cases whose truth was fixed before Forge saw them, drawn
from parameter distributions the existing corpus does not cover — 6.7 decades
of resistance against 3.5, 5.2 decades of source voltage against 2.2,
multi-stage circuits as the common case, non-SI unit spellings throughout —
Forge accepted **nothing** the independent truth refuses. Two model-contract
tiers scored 100 %. Where it disagreed, it was right more often than the
challenge was.

**Not proven.** That the contract reading is correct: the oracle shares it. That
any bound matches experiment: every threshold here is a definition, a
derivation, a citation or a policy. That refusal-path reporting is right: not
tested. That the runtime handles domains, shapes or regimes outside the six
here.

**Not blind any more.** v1 has been seen. A future round needs a v2 whose cases
this one has never met.

---

## Artifacts

| file | what |
|---|---|
| `benchmarks/blind/v1/FREEZE.json` | every digest, taken before the run |
| `benchmarks/blind/v1/FORGE_FIRST_RUN.json` | the primary result, sealed |
| `benchmarks/blind/v1/FIRST_RUN_SEAL.json` | its digest and the freeze SHA |
| `benchmarks/blind/v1/COMPARISON.json` | first-run scorecard, per case |
| `benchmarks/blind/v1/FAILURE_TRIAGE.json` | written before a line was changed |
| `benchmarks/blind/v1/TRUTH_ERRATA.json` | truths proven wrong, not edited |
| `benchmarks/blind/v1/FORGE_POST_FIX.json` | the re-run, which never replaces the first |
| `benchmarks/blind/v1/BLINDNESS_AUDIT.json` | the order of operations, checked against git |
