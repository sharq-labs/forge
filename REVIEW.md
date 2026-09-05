# Review — applicability conditions

Read in full: `src/engcore/domains/thermal_models/context.py` (997 L),
`.../lumped.py` (1250 L), and the applicability sections of
`src/engcore/domains/electrical/material.py` and `.../dc/models.py`.

---

## 1. Can a condition be satisfied by omitting an input?

**The shared mechanism.** Three links, each checkable:

1. Every derivation returns `None` when an input is absent — 17 guards in
   `context.py` (`:157 182 202 380 410 453 489 522 563 599 630 667 735 776 820
   856 890`) and 5 in `material.py` (`:943 979 1005 1032 1071`).
2. Every assembler drops a `None` rather than emitting a placeholder:
   `context.py:997`, `material.py:1116`, `dc/models.py:559`, and the two
   source contexts return `{}` (`dc/models.py:574 592`).
3. An absent key reaches the core as `None` — `definition.py:337`
   (`context.get(condition.name)`) — and `RangeCondition.evaluate` returns
   `UNKNOWN` for any non-`Quantity` (`definition.py:117-119`). A domain with an
   unknown and no violation is `UNKNOWN`, not `IN_DOMAIN`
   (`definition.py:346-350`).

**Proven for 14 of 14.** This section originally read "13 of 14" and flagged
`conductance_excursion_ratio` as unprovable; that defect has since been fixed
and the finding is retained below as a record of what was wrong and how it was
closed. Line numbers are post-fix.

| # | Condition | Derived at | Context built at | Absent input → |
|---|---|---|---|---|
| 1 | `biot_number` | `context.py:414` | `context.py:935-948` | `:453` → dropped `:997` |
| 2 | `internal_fourier_number` | `context.py:526` | `context.py:974` | `:563` (needs Bi) |
| 3 | `conductance_excursion_ratio` | `context.py:678` | `context.py:975` | `:735` → dropped `:997` |
| 4 | `capacity_excursion_ratio` | `context.py:743` | `context.py:979` | `:776` |
| 5 | `radiation_to_convection_ratio` | `context.py:831` | `context.py:984` | `:856`, and `:820` if no ε |
| 6 | `melting_temperature_utilization` | `context.py:864` | `context.py:992` | `:890` |
| 7 | `linearization_excursion_ratio` | `material.py:953` | `material.py:1097` | `:979` |
| 8 | `operating_temperature_utilization` | `material.py:987` | `material.py:1102` | `:1005` |
| 9 | `reduced_debye_temperature` | `material.py:1014` | `material.py:1106` | `:1032` |
| 10 | `linear_resistance_ratio` | `material.py:1041` | `material.py:1110` | `:1071` |
| 11 | `dissipated_power_utilization` | `dc/models.py:528` | `dc/models.py:600` | `:523` → `{}` `:559` |
| 12 | `working_voltage_utilization` | `dc/models.py:528` | `dc/models.py:600` | `:523` |
| 13 | `source_current_utilization` | `dc/models.py:562` | `dc/models.py:626` | `:523` → `{}` `:574` |
| 14 | `compliance_voltage_utilization` | `dc/models.py:577` | `dc/models.py:641` | `:523` → `{}` `:592` |

**#3 was the exception, and is now closed.** It returned `Quantity(0.0)` on
`regime == "forced"` *before* reading either argument, so the condition reported
satisfied with the operating point and the bound both absent. Not satisfied by
silence — a `None` regime fell through — but satisfied by a *substituted*
declaration: an unverifiable string no record could check, which never reached
provenance because a category cannot cross the Quantity-only boundary (§4.2).

**The fix removed the branch and the parameter.** The function now takes exactly
`excursion` and `bound`, both required; there is no third argument to assert
through. The regime stays on `LumpedApplicabilityDeclaration` as recorded intent
— why the caller thinks their span is credible — validated, serialized, read by
no derivation. Regression tests in `test_lumped_applicability.py`:
`test_declared_forced_convection_no_longer_waives_the_declared_bound`,
`..._no_longer_waives_the_operating_point`,
`..._is_still_judged_against_its_own_bound`, and
`test_the_declared_regime_changes_no_verdict_at_all` (three declarations
differing only in regime → three identical assessments).
`test_the_conductance_budget_takes_no_regime_and_has_no_bypass` pins the
signature so the branch cannot return.

---

## 2. Is any threshold unjustified?

| # | Constant | Value | Source cited in code | Verdict |
|---|---|---|---|---|
| 1 | `LUMPED_BIOT_LIMIT` `lumped.py:216` | 0.1 | Incropera 6th ed. §5.1 Eq. 5.10 | text states this criterion |
| 2 | `LUMPED_MIN_FOURIER_NUMBER` `lumped.py:241` | 0.2 | Incropera §5.5.2, one-term approx. | restated — see below |
| 3 | `RADIATION_NEGLIGIBILITY_LIMIT` `lumped.py:249` | 0.1 | Incropera §1.2.3 Eq. 1.9 | **flag — admitted convention** |
| 4 | `EXCURSION_BUDGET_LIMIT` `lumped.py:256` (hA) | 1.0 | §9.2 (why the bound is caller-set) | definitional |
| 5 | `EXCURSION_BUDGET_LIMIT` (capacity) | 1.0 | Table A.1 (why c_p varies) | definitional |
| 6 | `PHASE_CHANGE_UTILIZATION_LIMIT` `lumped.py:264` | 1.0 | §5.1, single-phase formulation | definitional / hard limit |
| 7 | `LINEARIZATION_BUDGET_LIMIT` `material.py:378` | 1.0 | Ashcroft & Mermin Ch. 26 | definitional |
| 8 | `OPERATING_TEMPERATURE_LIMIT` `material.py:384` | 1.0 | IEC 60115-1 Cl. 2 | definitional / hard limit |
| 9 | `BLOCH_GRUENEISEN_LINEAR_FLOOR` `material.py:395` | 1/3 | A&M Ch. 26 Eq. 26.55; Kittel Ch. 6 | **flag — admitted convention** |
| 10 | `MINIMUM_LINEAR_RESISTANCE_RATIO` `material.py:402` | 0.0 | none (physics of the quantity) | definitional |
| 11-14 | `RATING_UTILIZATION_LIMIT` `dc/models.py:87` | 1.0 | IEC 60115-1 Cl. 2 | definitional |

Eleven of fourteen bounds are **1.0 or 0.0** — "you have consumed all of the
budget you declared", which needs no citation. Only three carry a real number:
one has since been restated; two remain flagged as conventions:

- **#2, Fo ≥ 0.2 — was the worst of the three; since restated.** Incropera
  §5.5.2 establishes 0.2 as the accuracy boundary of the *one-term
  approximation to the series solution*. The condition used it for a stronger
  claim — "below this the body has several time scales and no lumped
  description has the right shape, however small Bi is" — which the text does
  not make and which is in fact false at small Bi, where the higher modes carry
  O(Bi) amplitude and are negligible before they have decayed. The condition now
  claims exactly the one-term criterion and labels itself a conservative screen:
  below 0.2 the model is *not validated*, not *shown wrong*. The citation and
  the number now match the claim, so this is no longer a flag.
  `test_the_fourier_condition_claims_only_what_its_source_establishes` pins it,
  including that the removed clause does not return.
- **#3, h_r/h ≤ 0.1.** Eq. 1.9 establishes `h_r`, not the ceiling.
  `lumped.py:243-249` says so explicitly ("the same neglected-mechanism
  convention … it is a convention, and it is recorded as one"). Honest.
- **#9, T/θ_D ≥ 1/3.** `material.py:391-395` says neither text prints ⅓ and
  calls it "the conventional engineering reading". Honest.

No threshold is *wrong*. #2 was cited more confidently than its source
supported, and has been restated to claim only what §5.5.2 establishes.

---

## 3. Is `context.py` larger than it needs to be?

Measured after the fixes above: 997 lines, 24 functions. Candidates, most to
least valuable, **none applied**:

1. **`_as_quantity` + `_positive` are always called as a nested pair** — 36 and
   20 call sites, every one reading `_positive(_as_quantity(v, U, L), U, L)`
   and repeating unit and label twice. One
   `_checked(value, unit, label, *, positive=False)` collapses ~20 four-line
   expressions to one line each. **~60 lines.**
2. **The 9 declaration fields are enumerated four times** — `__post_init__`
   `:247`, `is_empty` `:286`, `to_dict` `:303`, `from_dict` `:321` (plus
   `__all__` and the field list). A module-level tuple of
   `(name, unit, positive)` specs drives all four; `is_empty` can use
   `dataclasses.fields(self)`. **~35 lines**, and it removes the real risk of a
   tenth field reaching three of the four places.
3. **Every public function re-validates what the declaration already
   validated** (`__post_init__` `:247` enforces type, dimension, positivity,
   the emissivity range and the span scale). Defensible — the functions are
   public and the unit tests call them directly — but it is a second
   enforcement point.
4. **`__all__` has 43 entries** restating every public name.
5. **Five unit constants are duplicated verbatim in `lumped.py`** —
   `TEMPERATURE_UNIT`, `POWER_UNIT`, `CAPACITY_UNIT`, `CONDUCTANCE_UNIT`,
   `TIME_UNIT`. `lumped.py` already imports 20 names from `context.py`.
6. **`peak_body_temperature` `:608` and `surface_temperature_excursion` `:640`**
   both convert two endpoints to kelvin and take a max; one shared helper would
   serve both. **~10 lines.**
7. **`transient_horizon_ratio` `:493` is derived and exported but carries no
   condition** — it builds `internal_fourier_number` and is otherwise a
   diagnostic. Deliberate (`test_no_upper_bound_is_placed_on_the_horizon…`),
   worth knowing it is not load-bearing.

Cutting 1, 2, 5 and 6 removes roughly **110 lines without losing a check**. The
docstrings are not padding: they carry the definitions and the citations.

---

## 4. Two known gaps

### 4.1 `ScientificResult` has no `validity` field

`result.py:45-75` lists 14 fields; there is no validity field, and no
`ValidityAssessment` import anywhere under `results/`.

**A consumer can see:** the values, which model and version produced them
(`models`, `:49`), which realization and solver (`provenance.bindings`), what
checks ran and what they establish (`validation`), whether the solve converged
(`convergence`), and the declared `assumptions` (`:54`).

**Cannot see:** whether the model was applicable. The verdict exists only if
someone calls `assess_lumped_validity` (`lumped.py:951`) or
`assess_rated_resistance_validity` (`material.py:1130`) and keeps the answer
alongside; it is not in the result, provenance, or serialization. A result that
converged outside its validity domain is indistinguishable from one that did not.

**Minimal core change:** one optional field — `validity: ValidityAssessment |
None = None` — plus its `to_dict`/`from_dict` lines. `ValidityAssessment` is
already in the core (`definition.py:280`) and names no domain. `None` must stay
distinct from `ValidityStatus.UNKNOWN`: *not assessed* and *assessed,
insufficient context* are different failures.

### 4.2 The convection regime is not in the problem — now harmless

`ProvenanceRecord` admits only `Quantity` inputs (`provenance.py:233-237`) and
`coupled.py:1295` builds a thermal result's provenance from
`problem.parameter_values()` wholesale, so a `CategoricalValue` parameter is
refused at that boundary. The regime therefore cannot be a problem parameter
and is not declared as a `ModelInputSpec` (`lumped.py:385-397`).

**When this section was written that was the sharp edge:** the one declaration
that could satisfy a condition without measurement was also the one absent from
the record. The §1 fix removed the first half. No derivation reads the regime
now, so nothing deciding a verdict is missing from provenance.

**A consumer can see:** every quantity-valued declaration — characteristic
length, area, conductivity, emissivity, both excursion bounds, melting point —
as problem parameters (`lumped.py:774-833`) and again in `provenance.inputs`;
that is now the complete set of things any verdict rests on.

**Cannot see:** that forced convection was claimed — now a loss of *context*
rather than of evidence. A reader cannot tell why a wide bound was thought
credible, but the bound and whether the run respected it are both visible.

**Minimal core change, still worth doing but no longer load-bearing:** narrow
`ScientificProblem.parameter_values()`'s annotation to the truth (typed
`dict[str, Quantity]`, returns whatever the parameter holds) and add a sibling
`quantity_parameters()`. The electrothermal pack then builds provenance from the
sibling, and a categorical parameter becomes expressible without weakening the
provenance rule. Preferred over widening `ProvenanceRecord.inputs` to the full
`ScientificValue` union, which would relax a deliberate constraint for little.
