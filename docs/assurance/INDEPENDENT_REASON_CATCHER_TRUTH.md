# Independent reason and catcher truth

The verdict round asked *what* each DEV case is. This one asks *why* — and
whether "the primary catcher" is a well-defined thing to ask for at all.

A why is much easier to fake than a what. A module that read the benchmark's
declared catcher and echoed it back would score perfectly and establish
nothing. So the reason set and the causal catcher here are reconstructed from
the payload alone, and causality is decided by **counterfactual repair**: a
condition is causal because undoing its mechanism changes the verdict, not
because anything reported it.

Machine-readable results:
`benchmarks/oracles/results/independent_reason_truth_dev.json`
truth digest `b9642449dd893e81c3043215fb7d11986b7c28ece3b5182f111d81af4d9882c9`

---

## 1. The headline: "primary catcher" is mostly not well defined

| primary catcher status | cases | |
|---|---|---|
| `UNIQUE_CAUSAL_CATCHER` | **335** | exactly one condition whose repair changes the verdict |
| `ONE_CAUSAL_PLUS_REDUNDANT` | 47 | one causal, plus others that survive their own repair |
| `NO_UNIQUE_PRIMARY` | **483** | every violation clears under its own repair, yet the verdict survives each time |
| `UNRESOLVED` | **128** | no minimal counterfactual can be constructed |
| `NOT_APPLICABLE` | 407 | nothing failed |

**Of the 993 cases that have a finding at all, only 382 (38.5 %) have a unique
causal catcher.** For 483 the violations are *jointly* sufficient and
*individually* not: remove any one and the verdict stands. For 128 the question
cannot be posed, because no repair exists that changes one mechanism without
changing the others.

**`MULTIPLE_CAUSAL_CATCHERS` occurred zero times.** Where a causal catcher
exists it is unique; the ambiguity is never "which of several", it is always
"none of them individually".

So the round's question has an answer, and it is *no*: asking for **the**
primary catcher is well posed for about a third of the interesting cases and
ill posed for the rest. A benchmark that demands one everywhere is demanding
something the physics does not supply.

### Counterfactual status, per condition rather than per case

| status | conditions |
|---|---|
| `CAUSAL_BUT_REDUNDANT` | **875** |
| `COUNTERFACTUAL_NOT_WELL_DEFINED` | 446 |
| `CAUSAL_ISOLATED` | 382 |

`NON_CAUSAL` — a condition that survives its own repair — occurred **zero**
times. Every repair in the table does undo the condition it targets, which is
pinned by test rather than asserted.

---

## 2. What the reasons rest on

| reason truth class | cases | |
|---|---|---|
| `CONTRACT_ONLY` | **490** | the deciding condition is a utilisation against a limit the caller declared |
| `INDEPENDENT_SCIENTIFIC` | **360** | the deciding bound is sourced |
| `POLICY_DEPENDENT` | **244** | the arithmetic is verified; the number is `INTERNAL_POLICY` |
| `MIXED` | 63 | several conditions decide it and they differ in class |
| `NO_REASON_REQUIRED` | 243 | nothing failed |

**Of the 1157 cases carrying a reason, 360 (31 %) rest on sourced science.**
That is lower than the verdict round's 37 %, and the difference is real rather
than a recount: a verdict can be scientific because *some* condition deciding
it is sourced, while the reason set is only scientific if a sourced condition
is among those actually reported.

By kind of finding: `CONTRACT_VIOLATION` 532, `SCIENTIFIC_VIOLATION` 423,
`POLICY_VIOLATION` 307, `CONTRADICTORY_INPUT` 197,
`MISSING_REQUIRED_EVIDENCE` 164, `INVALID_MODEL_REGIME` 95.

---

## 3. Forge's mechanism against the causal one

| | mechanism-level | strict names |
|---|---|---|
| `EXACT_CAUSAL_MATCH` | **382** | 382 |
| `ALL_VALID_REASONS_REPORTED` | **775** | 758 |
| `CORRECT_VERDICT_WRONG_MECHANISM` | **0** | 17 |
| `VALID_BUT_REDUNDANT` | **0** | 0 |
| `MISSING_CAUSAL_REASON` | **0** | 0 |
| `NOT_APPLICABLE` | 243 | 243 |

**On every DEV case with a causal catcher, Forge reports it. On every case
without one, Forge reports every valid reason.** There is no case where a
causal mechanism existed and Forge named a different one instead, and no case
where Forge reached the right verdict with no valid mechanism behind it.

### The one place a name difference is allowed to count as agreement

The two columns differ by exactly 17 cases, and by exactly one name:

| this analyser | Forge | why they are the same proposition |
|---|---|---|
| `thermal_runaway_no_steady_state` | `coupling_transfer_refused` | both assert the coupled loop reached no self-consistent operating point |

That table is `MECHANISM_EQUIVALENCE` in `run_independent_reason.py`, it has
one entry, and both figures are published so the difference is auditable.
Every other name matches literally — including
`declared_limits_are_mutually_consistent`, which Forge reports through the
**validation-check** channel rather than as a validity condition. An earlier
version of this comparison read only the condition channel and therefore
scored 15 `melt_below_ceiling` cases as though Forge had found nothing, when
it had named the defect exactly. That was an instrumentation defect, not a
Forge defect, and it accounted for most of a "41 wrong mechanism" figure that
does not survive contact with the second channel.

---

## 4. Benchmark intent against causal truth

| intent class | cases | reading |
|---|---|---|
| `INTENT_IS_REDUNDANT` | **394** | the declared catcher is valid, but the verdict survives its repair |
| `INTENT_IS_CAUSAL` | **307** | the declared catcher is the causal one |
| `INTENT_IS_VALID_NOT_CAUSAL` | 290 | valid reason, no causal status of its own |
| `INTENT_NAMES_A_NEAR_MISS` | 221 | the case is designed to *pass*; the field names what it is about |
| `NO_MACHINE_CHECKABLE_INTENT` | 107 | no declared catcher |
| `INTENT_IS_A_GAP_NOT_A_REASON` | 69 | the declared catcher is undecidable here — a gap, not a finding |
| **`INTENT_DID_NOT_FAIL`** | **12** | the declared catcher did not fail, in any sense |

`INTENT_NAMES_A_NEAR_MISS` is not a defect. The `*_in@*` families place a value
just *inside* a bound and name the condition the case is about; the field is
being used as "what this tests", not "what must fire". Classifying that as a
miss would penalise the benchmark for saying what it meant. It is separated
here using **this analyser's** verdict, not the stored one.

Whole families are `INTENT_IS_REDUNDANT` by construction — `compound:biot+cond`
41/41, `compound:biot+tmax` 40/40, `compound:cond+melt` 38/38,
`compound:biot+band` 37/37. A compound case injects two defects, so neither is
individually necessary. **The benchmark's declared catcher is right about those
cases and its `primary catcher` metric is measuring something that is not
there.**

---

## 5. The 12 genuine intent defects

Forge names the same mechanism this analyser does in **all twelve**. These are
benchmark ground-truth defects, not runtime defects.

### 5a. Eight `runaway` cases that are not runaways

`U00287 U00382 U00524 U00637 U00676 U00954 U01031 U01673`

Declared catcher: `thermal runaway`. Stored reason: *"the electro-thermal loop
does not contract. A design that runs away…"*.

Independently, and confirmed by Forge's `linear_resistance_ratio`, the actual
mechanism is different: **the conductor's linear TCR form gives R ≤ 0 at the
body's own initial temperature.** The design does not run away — it starts
outside the region where the model describes a conductor at all.

U01031 is the clearest: α = +0.05 /K about a 293.15 K reference puts R at zero
at 273.15 K, and the body starts at 255.9 K. There is nothing thermally
unstable about it. Both signs of α appear across the eight (+0.05, −0.05, +0.03),
so this is not one generator branch misfiring; it is the family label being
applied to two different physical situations.

The remaining 17 of the 26 are genuine: no real root of the balance exists, so
no temperature makes generation equal loss.

**Why no previous round saw this.** The v3 scorecard reports `runaway` as
26/26 verdict and 25/25 primary catcher, 0 coincidental. It reaches that by
accepting `linear_resistance_ratio` as a valid catcher for the family — which
it *is*. Catcher-name scoring cannot tell "the right condition fired for the
declared reason" from "the right condition fired for a different reason". Only
reconstructing the mechanism separates them.

### 5b. Four `adv_unsound:small_overshoot` coincidences

`U01000 U01769 U01830 U01940`

Declared catcher `operating_temperature_utilization`, stored reason *"Over the
ceiling by 0.189 K. Small, and still over."* The intended catcher does not
fire: at the governed operating point (the endpoint, per the U01001
adjudication) the ceiling is not exceeded. What refuses these is
`radiation_to_convection_ratio`, `temperature` or `biot_number`.

These are four of the six cases the v3 scorecard already lists as coincidental
(`U00188 U01000 U01769 U01830 U01881 U01940`). **This round reproduces that
finding from an unrelated direction**, and places the other two —
`U00188` and `U01881`, both `compound:horizon+tmax` — as
`INTENT_IS_A_GAP_NOT_A_REASON`: their declared catcher
`internal_fourier_number` is a conservative screen, which produces a gap and
never a finding. That is the adjudicated semantics, recovered independently.

**No truth was changed.** These 12 are an adjudication-ready packet, not an
applied repair.

---

## 6. Two defects found in the evaluator itself

Both were in this project's own oracle, not in Forge. They are reported here
because the round's rule is that guided development is disclosed.

### 6a. Found WITHOUT Forge — the damped iteration

`_coupled_operating_point` solved the loop by damped iteration. Deriving the
same balance in closed form —

    u² + u(α T_ref − 1 − α T_off) − α S V² / (hA R_ref) = 0,  u = 1 + α(T − T_ref)

— showed that on five DEV cases the iteration reported *no operating point
exists* where a positive root plainly does. **Nothing about Forge was consulted
to find this**; the iteration and the closed form disagreeing with each other
is what exposed it. All five still came out `NOT_SUPPORTED`, so a
verdict-level comparison could not have seen it. Only asking for the mechanism
did.

The closed form also splits one label into two real findings — no real root
(runaway) versus every root demanding R ≤ 0 — which is what §5a rests on.

A second bug in the same fix *was* Forge-prompted: the first closed form took
the largest positive root, which on U01031 selected a branch across the R = 0
singularity that the body cannot reach. Forge disagreeing on that one case
prompted the check; the fix — the model must be physical at the initial state —
stands on its own and is now a precondition rather than a conclusion.

### 6b. Found WITH Forge — the over-broad convection gate

The evaluator required all five fluid properties before forming any of the
three convection conditions, so a case missing only the fluid conductivity
reported two gaps it did not have. A Reynolds number never needs `k`, and the
property range is `0.6/Pr` and needs nothing else. **Forge reporting fewer
gaps is what prompted the check.** Over-reporting a gap is not the safe
direction it looks like: it claims the payload settles less than it does.

**This is contamination and is counted as such.** The register's contamination
row now names two Forge-prompted fixes in this round on top of the three from
the verdict round.

---

## 7. No-peek, proven rather than asserted

`tests/oracles/test_independent_reason_truth.py`, 126 tests, all passing
alongside the 83 verdict-truth tests and the rest of `tests/oracles/`
(363 passed, 2 skipped).

* **9 metadata mutations × 9 cases.** Changing `should_be_caught_by` — to a
  nonexistent condition *and* to a plausible one — `acceptable_catchers`
  (rewritten and emptied), `reason`, `expected_verdict`,
  `expected_unknown_reason`, `defect` or `label` leaves the analyser's output
  **byte-identical**. Every mutation is constructed to differ from what the
  case already stores.
* **The sharpest form, stated separately:** naming a different condition in
  `should_be_caught_by` and emptying `acceptable_catchers` cannot change
  `causal_catchers`, `valid_reasons` or `primary_status`.
* **Import closure** by AST: `{__future__, copy, dataclasses, math,
  independent_truth}` and nothing else; no object in the namespace has a
  `__module__` mentioning `engcore`.
* **Name closure:** below the docstring the code never names a ground-truth
  field.
* **The closed-form root is substituted back into the balance it claims to
  solve**, and asserted to leave a residual under 1e-9 relative — a closed
  form can be silently wrong on every case at once in a way an iteration
  cannot.
* **The operating point is on the branch the body starts on:** u > 0 at the
  initial temperature, the endpoint and the asymptote.
* **The two refusals are distinct**, and constructed payloads produce each:
  an NTC with no real root gives `thermal_runaway_no_steady_state`, a
  conductor with R ≤ 0 at its start gives `linear_resistance_ratio`.
* **Every repair moves the condition it targets** — the property that makes
  "causal" mean anything.
* **One withheld fluid property does not blank the others**, with the mirror
  test that withholding Prandtl on the *natural* route genuinely does take the
  flow range, so the first test cannot be satisfied by a module that never
  reports a flow-range gap.

---

## 8. Circularity

| relationship | class |
|---|---|
| analyser → Forge implementation | **NONE** — no import path exists |
| analyser → declared catcher / acceptable catchers / stored reason | **NONE** — proven by mutation |
| causality → anything Forge reported | **NONE** — decided by repair and re-evaluation |
| analyser → governed contract semantics | **MEDIUM, unavoidable** |
| analyser development → Forge disagreement | **MEDIUM** — one of this round's two fixes; see §6 |
| `MECHANISM_EQUIVALENCE` | **DECLARED** — one entry, both figures published |

The medium in row four is the same one the verdict round carried and is worth
restating: Forge and this analyser both implement the same governed contract —
which operating point a ceiling is read at, that a screen produces a gap, that
a violation outranks a gap. Agreement confirms **two independent
implementations of one specification**. It does not confirm the specification,
and §1 shows the specification asking for something (a primary catcher) that
is not well defined for most cases.

---

## 9. What this does not establish

* **Not a blind test.** One of the two evaluator fixes this round was prompted
  by a Forge disagreement.
* **Not experimental.** Every mechanism here is a definition, a derivation, a
  citation or another program.
* **Not a verdict on the specification.** 490 reason sets are `CONTRACT_ONLY`
  and 307 conditions are policy violations; for those, agreement measures
  faithful implementation of a choice.
* **`INTENT_IS_REDUNDANT` is not a benchmark defect.** 394 cases carry it
  because compound cases have two defects by design.
* **The 12 defects in §5 are unadjudicated.** They are evidence, not a repair.
* **The legacy hold-out was not touched**, and no conclusion here depends on it.
