# Review — applicability conditions

Read in full: `src/engcore/domains/thermal_models/context.py` (973 L),
`.../lumped.py` (1224 L), and the applicability sections of
`src/engcore/domains/electrical/material.py` and `.../dc/models.py`.

---

## 1. Can a condition be satisfied by omitting an input?

**The shared mechanism.** Three links, each checkable:

1. Every derivation returns `None` when an input is absent — 17 guards in
   `context.py` (`:157 182 202 372 402 445 481 514 551 587 618 655 705 746 790
   826 860`) and 5 in `material.py` (`:943 979 1005 1032 1071`).
2. Every assembler drops a `None` rather than emitting a placeholder:
   `context.py:973`, `material.py:1116`, `dc/models.py:559`, and the two
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
| 1 | `biot_number` | `context.py:406` | `context.py:910-923` | `:445` → dropped `:973` |
| 2 | `internal_fourier_number` | `context.py:518` | `context.py:930` | `:551` (needs Bi) |
| 3 | `conductance_excursion_ratio` | `context.py:674` | `context.py:971` | `:731` → dropped `:993` |
| 4 | `capacity_excursion_ratio` | `context.py:713` | `context.py:953` | `:746` |
| 5 | `radiation_to_convection_ratio` | `context.py:801` | `context.py:959` | `:826`, and `:790` if no ε |
| 6 | `melting_temperature_utilization` | `context.py:834` | `context.py:966` | `:860` |
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
| 1 | `LUMPED_BIOT_LIMIT` `lumped.py:210` | 0.1 | Incropera 6th ed. §5.1 Eq. 5.10 | text states this criterion |
| 2 | `LUMPED_MIN_FOURIER_NUMBER` `lumped.py:218` | 0.2 | Incropera §5.5.2, one-term approx. | **flag — see below** |
| 3 | `RADIATION_NEGLIGIBILITY_LIMIT` `lumped.py:226` | 0.1 | Incropera §1.2.3 Eq. 1.9 | **flag — admitted convention** |
| 4 | `EXCURSION_BUDGET_LIMIT` `lumped.py:234` (hA) | 1.0 | §9.2 (why the bound is caller-set) | definitional |
| 5 | `EXCURSION_BUDGET_LIMIT` (capacity) | 1.0 | Table A.1 (why c_p varies) | definitional |
| 6 | `PHASE_CHANGE_UTILIZATION_LIMIT` `lumped.py:242` | 1.0 | §5.1, single-phase formulation | definitional / hard limit |
| 7 | `LINEARIZATION_BUDGET_LIMIT` `material.py:378` | 1.0 | Ashcroft & Mermin Ch. 26 | definitional |
| 8 | `OPERATING_TEMPERATURE_LIMIT` `material.py:384` | 1.0 | IEC 60115-1 Cl. 2 | definitional / hard limit |
| 9 | `BLOCH_GRUENEISEN_LINEAR_FLOOR` `material.py:395` | 1/3 | A&M Ch. 26 Eq. 26.55; Kittel Ch. 6 | **flag — admitted convention** |
| 10 | `MINIMUM_LINEAR_RESISTANCE_RATIO` `material.py:402` | 0.0 | none (physics of the quantity) | definitional |
| 11-14 | `RATING_UTILIZATION_LIMIT` `dc/models.py:87` | 1.0 | IEC 60115-1 Cl. 2 | definitional |

Eleven of fourteen bounds are **1.0 or 0.0** — "you have consumed all of the
budget you declared", which needs no citation. Only three carry a real number,
and all three are flagged:

- **#2, Fo ≥ 0.2 — the worst of the three, and the code does not say so.**
  Incropera §5.5.2 establishes 0.2 as the accuracy boundary of the *one-term
  approximation to the series solution* of a body with internal conduction. The
  condition uses it for a different claim: "below this the body has several
  time scales and no lumped description has the right shape"
  (`lumped.py:492-501`). That inference is reasonable — one-term validity and
  single-exponential response are the same statement — but the text does not
  make it, and the constant's comment presents 0.2 as though it did. The other
  two conventions are labelled as conventions; this one is not.
- **#3, h_r/h ≤ 0.1.** Eq. 1.9 establishes `h_r`, not the ceiling.
  `lumped.py:224-226` says so explicitly ("the same neglected-mechanism
  convention … it is a convention, and it is recorded as one"). Honest.
- **#9, T/θ_D ≥ 1/3.** `material.py:391-395` says neither text prints ⅓ and
  calls it "the conventional engineering reading". Honest.

No threshold is *wrong*. One (#2) is cited more confidently than its source
supports.

---

## 3. Is `context.py` larger than it needs to be?

Measured: 973 lines — 525 code, 300 docstring, 111 blank, 37 comment;
24 functions. Removal candidates, most to least valuable, **none applied**:

1. **`_as_quantity` + `_positive` are always called as a nested pair** — 36 and
   20 call sites. Every one reads
   `_positive(_as_quantity(v, U, L), U, L)`, repeating unit and label twice.
   One `_checked(value, unit, label, *, positive=False)` collapses ~20
   four-line expressions to one line each. **~60 lines.**
2. **The 9 declaration fields are enumerated four times** — `__post_init__`
   `:241-249`, `is_empty` `:280-290`, `to_dict` `:298-308`, `from_dict`
   `:317-327` (plus `__all__` and the field list itself). A module-level tuple
   of `(name, unit, positive)` specs drives all four; `is_empty` can use
   `dataclasses.fields(self)`. **~35 lines**, and it removes the real risk that
   a tenth field is added to three of the four places.
3. **Every public function re-validates what the declaration already
   validated.** `LumpedApplicabilityDeclaration.__post_init__` (`:239-276`)
   already enforces type, dimension, positivity, the emissivity range and the
   span scale; `derived_lumped_quantities` then passes those same values into
   functions that check them again. Defensible (the functions are public and
   the unit tests call them directly) but it is a second enforcement point.
4. **`__all__` has 43 entries** restating every public name.
5. **Five unit constants are duplicated verbatim in `lumped.py`** —
   `TEMPERATURE_UNIT`, `POWER_UNIT`, `CAPACITY_UNIT`, `CONDUCTANCE_UNIT`,
   `TIME_UNIT` are defined in both files. `lumped.py` already imports 20 names
   from `context.py`; these five could join them.
6. **`peak_body_temperature` `:596` and `surface_temperature_excursion` `:628`**
   both convert two endpoints to kelvin and take a max; one shared
   endpoint-extremes helper would serve both. **~10 lines.**
7. **`transient_horizon_ratio` `:485` is derived and exported but carries no
   condition** — it exists to build `internal_fourier_number` and as a
   diagnostic. Deliberate (`test_no_upper_bound_is_placed_on_the_horizon…`),
   worth knowing it is not load-bearing.

Cutting 1, 2, 5 and 6 removes roughly **110 lines without losing a check**. The
300 docstring lines are not padding: they carry the definitions and the
citations, which is the point of the module.

---

## 4. Two known gaps

### 4.1 `ScientificResult` has no `validity` field

`result.py:45-75` lists 14 fields; there is no validity field, and no
`ValidityAssessment` import anywhere under `results/`.

**A consumer holding a `ScientificResult` can see:** the values, which model
and version produced them (`models`, `:49`), which realization and solver
(`provenance.bindings`), what checks ran and what they establish
(`validation`), whether the solve converged (`convergence`), and the model's
declared `assumptions` (`:54`).

**Cannot see:** whether the model was applicable to these inputs. The verdict
exists only if someone calls `assess_lumped_validity` (`lumped.py:926`) or
`assess_rated_resistance_validity` (`material.py:1130`) and keeps the answer
alongside; it is not in the result, not in provenance, and not serialized. A
result that converged outside its validity domain is indistinguishable from one
that did not.

**Minimal core change:** one optional field on `ScientificResult` —
`validity: ValidityAssessment | None = None` — plus its `to_dict`/`from_dict`
lines. `ValidityAssessment` is already in the core (`definition.py:280`) and
names no domain, so this adds no domain vocabulary to `scientific/`. `None`
must stay distinct from `ValidityStatus.UNKNOWN`: *not assessed* and *assessed,
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
as problem parameters (`lumped.py:752-811`) and again in `provenance.inputs`;
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
