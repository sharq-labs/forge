# Independent case truth

What independent science says each DEV case should be — reconstructed from the
payload alone, before anything read the stored answer or ran Forge.

Machine-readable results:
`benchmarks/oracles/results/independent_case_truth_dev.json`
truth digest `e9ebfe974a6ac5f831d53a5fa8e146d85d3269edd8e5cf505a3a0bc4effe524e`

---

## 1. The headline, and the caveat that belongs with it

| | |
|---|---|
| DEV cases evaluated | **1400 / 1400** |
| independently resolvable | **1400 (100 %)** |
| **Forge agrees with independent truth** | **1400 / 1400 (100.0 %)** |
| stored benchmark truth agrees | **1362 / 1400 (97.3 %)** |
| stored-truth mismatches | **38** |

A second evaluator that **imports nothing from `engcore`** — not the
applicability evaluator, not `derive_verdict`, not the solvers, not even the
unit registry — reproduces Forge's verdict on every DEV case. And the 38 cases
where the stored answer key disagrees with Forge are the same 38 where it
disagrees with an independent reconstruction.

**The caveat, stated once and plainly: the evaluator's development was
Forge-guided.** Three defects in it were found by looking at where it disagreed
with Forge — a vacuous two-route comparison treated as undecidable, a missing
declared-limits check, and a missing fluid property treated as unreconstructable
rather than as a gap. Each was then fixed on an argument that stands without
Forge, and the module is *structurally* independent. But a construction that had
never been compared would be worth more, and this one has not earned that
description. The agreement figure should be read as **"two independent
implementations of the governed contract agree"**, not as "Forge was blind-tested
against nature".

---

## 2. Truth classes — what each verdict actually rests on

A verdict is only as independent as the weakest bound deciding it.

| class | cases | meaning |
|---|---|---|
| `CONTRACT_ONLY` | **575** | every evaluated condition held, or the deciding bound is a *definitional* utilisation against a caller-declared limit. The arithmetic is independent; the limit is the caller's. |
| `INDEPENDENT_SCIENTIFIC` | **518** | the deciding bound is sourced or derived (Biot, Fourier, geometry route, convection agreement) |
| `POLICY_DEPENDENT` | **244** | the arithmetic is verified; the deciding number is `INTERNAL_POLICY` |
| `MIXED_SCIENCE_AND_POLICY` | **63** | several conditions decide it and they differ in class |
| `UNRESOLVED` | **0** | — |

**Only 518 of 1400 (37 %) rest on sourced science.** A further 63 partly do.
**307 verdicts (22 %) turn wholly or partly on a policy number**, and 575 turn
on limits the caller supplied and Forge never vouched for.

That decomposition is the round's real result. A 100 % agreement figure across
all 1400 would be badly misread without it.

---

## 3. Family matrix (largest 14 of 144)

| family | n | science | policy | mixed | contract | stored≠ind | Forge≠ind |
|---|---|---|---|---|---|---|---|
| `geometry_conflict` | 87 | **72** | 0 | 15 | 0 | 0 | 0 |
| `adv_unsound:cool_but_low_debye` | 53 | 0 | **39** | 14 | 0 | 0 | 0 |
| `adv_unsound:small_overshoot` | 50 | 13 | 4 | 0 | 33 | 0 | 0 |
| `compound:horizon+tmax` | 49 | 18 | 2 | 0 | 29 | 0 | 0 |
| `adv_unsound:brief_but_slow` | 43 | 42 | 1 | 0 | 0 | **1** | 0 |
| `compound:biot+cond` | 41 | 38 | 0 | 3 | 0 | 0 | 0 |
| `compound:biot+tmax` | 40 | 37 | 0 | 3 | 0 | 0 | 0 |
| `compound:cond+melt` | 38 | 5 | 6 | 0 | 27 | 0 | 0 |
| `compound:biot+band` | 37 | **37** | 0 | 0 | 0 | 0 | 0 |
| `limit_conflict:ref_above_ceiling` | 36 | 11 | 2 | 0 | 23 | 0 | 0 |
| `limit_conflict:melt_below_ceiling` | 27 | 5 | 7 | 0 | 15 | 0 | 0 |
| `runaway` | 26 | 25 | 0 | 0 | 1 | 0 | 0 |
| `limit_conflict:band_vs_ceiling` | 22 | 4 | 4 | 0 | 14 | 0 | 0 |
| `adv_unsound:tiny_rise_tight_budget` | 21 | 6 | 1 | 0 | 14 | 0 | 0 |
| **all 144** | **1400** | **518** | **244** | **63** | **575** | **38** | **0** |

`adv_unsound:cool_but_low_debye` is the family worth naming: **all 53 cases turn
on the Debye floor**, which the bound register classes `INTERNAL_POLICY` (the
Bloch–Grüneisen regime is standard; the exact θ_D/3 is convention). Not one of
those verdicts is independently scientific.

---

## 4. The 38 stored-truth mismatches

Every one runs the same direction:

> stored `INSUFFICIENT_EVIDENCE` → independent **and** Forge `NOT_SUPPORTED`

and they are concentrated in the `missing:*` families:

| family | n | | family | n |
|---|---|---|---|---|
| `missing:fluid_conductivity` | 6 | | `missing:surface_emissivity` | 2 |
| `missing:melting_temperature` | 4 | | `missing:fluid_kinematic_viscosity` | 2 |
| `missing:fluid_expansion_coefficient` | 4 | | `missing:body_conductivity` | 2 |
| `missing:fluid_prandtl_number` | 4 | | `missing:maximum_operating_temperature` | 2 |
| `missing:linearization_band` | 4 | | `horizon_out@0.2` | 2 |
| `missing:debye_temperature` | 3 | | `adv_unsound:brief_but_slow` | 1 |

**Root cause.** A `missing:X` case omits one declaration, expecting the
resulting gap to produce `INSUFFICIENT_EVIDENCE`. But the governed precedence
is explicit — *a violation outranks a gap* — and in these 38 the case also
carries a genuine violation, because `widen_all` did not widen far enough. The
stored verdict contradicts the benchmark's own precedence rule.

**Their truth classes matter, and they split:**

| | cases | what can be claimed |
|---|---|---|
| `INDEPENDENT_SCIENTIFIC` | **15** | independent science says the stored verdict is wrong |
| `POLICY_DEPENDENT` | **22** | the violation exists *because of a policy number*; independent **science** says nothing |
| `MIXED` | 1 | partly each |

**No adjudication was applied.** Reasons, in order of weight:

1. **22 of 38 rest on policy bounds.** Correcting them would present a policy
   consequence as a scientific correction.
2. Adjudicating all 38 would move Hard DEV to **1400/1400** — a figure that
   would be read as perfection and is a truth edit, not a measurement.
3. The `missing:*` cases would stop testing what they claim: the declared defect
   is an omission, but the corrected verdict would be decided by an unrelated
   violation. Same coherence problem that stopped the `geometry_conflict`
   catcher repair.

The adjudication-ready packet is the machine-readable artifact plus this
section; applying it needs a governance decision about (1) and (3), not more
evidence.

---

## 5. U01881 and the six review cases

All six now agree across stored truth, independent truth and Forge —
`NOT_SUPPORTED` in every case. What differs is what that verdict *rests on*:

| case | deciding condition | value | bound | truth class |
|---|---|---|---|---|
| U01830 | `biot_number` | 2.029 | ≤ 0.1 (**sourced**) | **`INDEPENDENT_SCIENTIFIC`** |
| U01769 | radiation ratio, temperature | 1.016 | ≤ 0.1 (policy) | `POLICY_DEPENDENT` |
| U01000 | radiation ratio | 0.655 | ≤ 0.1 (policy) | `POLICY_DEPENDENT` |
| U00188 | radiation ratio | 0.489 | ≤ 0.1 (policy) | `POLICY_DEPENDENT` |
| U01940 | radiation ratio, temperature | 0.258 | ≤ 0.1 (policy) | `POLICY_DEPENDENT` |
| **U01881** | radiation ratio | **0.109** | ≤ 0.1 (policy) | **`POLICY_DEPENDENT`** |

**This corrects the previous round's reasoning about these six.** That round
resolved five of them on the size of their margin — 2.6× to 20× past the bound
— and left U01881 open at 1.09×. The independent evaluator gives a cleaner
answer: **margin size is irrelevant to the class of the bound.** Being twenty
times past a policy number is still being past a policy number. Only U01830,
decided by Biot, is independently scientific; the other five including U01881
are `POLICY_DEPENDENT`.

**U01881's verdict is not in doubt** — all three parties say `NOT_SUPPORTED`.
What remains unestablished is whether that verdict is *physics*, and that turns
on a number `SCIENTIFIC_BOUND_REGISTER.md` records as having no located source.
The bound was not moved.

---

## 6. No-peek, proven rather than asserted

`tests/oracles/test_independent_case_truth.py`, 83 tests:

* **9 metadata mutations × 7 cases.** Changing `expected_verdict`, `label`,
  `should_be_caught_by`, `reason`, `acceptable_catchers`,
  `expected_unknown_reason`, `needs_review` or `defect` leaves the independent
  truth **byte-identical**. Each mutation is constructed to differ from what the
  case already stores, so none passes vacuously.
* **Import closure.** The evaluator's AST imports exactly
  `{__future__, math, dataclasses}`; its module namespace holds nothing whose
  `__module__` mentions `engcore`.
* **Name closure.** The code below the docstring never names a ground-truth
  field.
* **Six physics mutations** move the condition they should, in the direction its
  definition predicts, and at least four flip the verdict.
* Removing a declaration produces `UNKNOWN(not_supplied)`, never a pass.
* An unrecognised unit raises rather than being guessed at.

---

## 7. Circularity

| relationship | class |
|---|---|
| evaluator → Forge implementation | **NONE** — no import path exists |
| evaluator → benchmark stored truth | **NONE** — proven by mutation |
| evaluator physics → oracle suite sources | LOW — same citations, independent transcription |
| evaluator *semantics* → governed contract | **MEDIUM, and unavoidable** |
| evaluator development → Forge disagreement | **MEDIUM** — see §1 |

The medium in row four is worth stating: both Forge and this evaluator
implement the same governed contract — which operating point a ceiling is read
at, that a screen produces a gap, that a violation outranks a gap. Agreement
therefore confirms **two independent implementations of one specification**. It
does not confirm the specification.

---

## 8. Battery

Not covered by this evaluator. Battery truth was reconstructed independently in
the previous round and is pinned by
`tests/oracles/test_oracle_battery.py`: coulomb counting done from the payload
under Forge's declared contract reproduces its final state of charge exactly,
and for all 11 false rejects the condition the payload places the case against
is violated at that state. Those 11 remain **ground-truth defects, unadjudicated**,
for the same reason as §4: the repair is a generator correction and a
regeneration, because the payloads were drawn against the wrong horizon.

---

## 9. What this does not establish

* **Not a blind test.** See §1.
* **Not experimental validation.** Every oracle behind these numbers is a
  definition, a derivation, a citation, or another program.
* **Not a verdict on the specification.** 575 cases are `CONTRACT_ONLY` and 307
  turn on policy; for those, agreement measures faithful implementation of a
  choice, not correctness of the choice.
* **The legacy hold-out was not touched**, and no conclusion here depends on it.
