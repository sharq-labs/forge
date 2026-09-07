# Battery domain, v0

An equivalent-circuit cell with state of charge, coupled to the existing lumped
thermal model through self-heating. It answers, for a declared load: what
terminal voltage, what runtime, what heat — and, above all, **whether the model
is applicable to the case asked**.

Package: `src/engcore/domains/battery/`. Tests: `tests/domains/battery/`.
Applicability rows: [`applicability-conditions.md`](applicability-conditions.md).

The domain is a pure consumer of `engcore.scientific` and of the public API of
`engcore.domains.thermal_models`. It modifies neither, and nothing in it is
registered with, imported by, or known to the core.

---

## What it models

One cell — or a series string treated as one lumped cell — as four separate
scientific claims, each with its own record, its own validity domain and its own
realization. They are kept apart because a caller can reasonably accept one and
reject another.

| Model | Claim | Status |
|---|---|---|
| `battery.cell.rint_ocv` | `V = OCV(z) − I·R_int`, `OCV(z) = V_empty + (V_full − V_empty)·z`, `Q = I²·R_int` | `SELF_CONSISTENT` |
| `battery.cell.coulomb_counting` | `z(t) = z₀ − I·t / (η·Q_nom)` | `SELF_CONSISTENT` |
| `battery.cell.constant_current_runtime` | time to the first of a declared voltage cutoff and a declared state-of-charge cutoff | `SELF_CONSISTENT` |
| `battery.cell.peukert_capacity_derating` | `Q_eff = Q_nom·(I_ref/I)^(k−1)` | `UNVALIDATED` |

**Why the Peukert record is `UNVALIDATED` and the others `SELF_CONSISTENT`.**
Self-consistency is a claim available to a closed form that solves an equation:
the solver checks each of the first three against the relation it states, and a
flipped sign or a dropped efficiency leaves the residual non-zero. Peukert's law
is a fitted correlation with no differential balance behind it. Evaluating a
curve fit correctly establishes nothing about whether the curve holds, and
awarding it the same word would be the strongest term this repository has,
applied to the weakest evidence it holds.

**Nothing here is experimentally validated.** No cell in this repository has
been discharged. The only validation level any result claims is
`DIMENSIONALLY_VALID`, and it comes from a check that compares what was computed
against what the model records declare — a reference outside the arithmetic. The
two residual checks establish **no** level, deliberately: they compare a closed
form against the equation it was derived from, which is weaker evidence than the
byte-pinned conduction solver has, and that solver claims no more either.

---

## What it deliberately does not model

Each of these is a real omission with a real cost, stated here and repeated in
the affected models' `assumptions`.

**No diffusion dynamics.** The Rint circuit represents the whole overpotential
as one instantaneous ohmic drop. A real cell's diffusion overpotential grows as
`1 − exp(−t/τ)` after a current step, which is why an RC branch is the standard
next model. The cost is bounded by the `polarization_unmodelled_fraction`
condition rather than hidden, and it is borne in the *middle* of the
relaxation rather than at either end of it: a pulse far shorter than τ omits a
branch that has barely developed, and one far longer omits a branch that has
stopped moving and is already inside an R_int measured the same way.

**No reversible heat.** `Q = I²·R_int` is the irreversible term only. The
entropic term `−I·T·dU/dT` is *not* negligible: near room temperature it is of
the same order as the Joule term at low rate, and it **changes sign** with the
direction of current and with state of charge, so a real cell can absorb heat
while discharging. This domain therefore reports a heat that is systematically
wrong at low rate by an amount it cannot bound. Computing it needs `dU/dT(z)`
for the cell, which is a measurement this repository does not have. No fudge
factor stands in for it.

**No tabulated OCV.** The open-circuit voltage is an affine chord between two
declared endpoints. A real OCV(z) is a measured curve with a plateau and a knee,
and the chord is worst exactly at the ends of the charge axis — which is what
the `soc_window_margin` condition bounds. A tabulated OCV is the obvious next
model and is deliberately not this one.

**No ageing.** No cycle life, no calendar fade, no capacity loss, no resistance
growth. Every number here describes a cell at one point in its life, and nothing
in the domain would notice that it is not the first.

**No thermal runaway**, no abuse response, no gas generation, no venting. The
thermal side is a linear lumped balance with a constant heat source; it has no
exothermic decomposition term and cannot represent one. A run whose temperature
climbs is climbing toward `T_amb + Q/hA` and toward nothing else.

**No charging.** The sign convention is discharge-positive throughout, and only
the *discharge* temperature range is declared. A cell's charge range is
narrower, most sharply at the cold end where charging plates lithium metal
rather than intercalating it. A caller charging the cell is outside the whole
domain, not merely outside one condition, and **no condition here would catch
it**.

**No cell-to-cell variation.** A series string is treated as one lumped cell.
There is no balancing, no weakest-cell logic, and no distribution of state of
charge across a pack.

**No internal temperature gradient.** Every model assigns the cell one
temperature. The `self_heating_rise_ratio` condition is where that assumption is
made falsifiable, but the domain has no core-to-surface resistance and cannot
report an internal hot spot.

**No `R_int(T)`.** The declared internal resistance is a single value. Its
temperature dependence is real and strong — electrolyte conductivity and
charge-transfer kinetics are both thermally activated — and it is *bounded* by
the `internal_resistance_drift_ratio` condition rather than modelled. This is
also why the electro-thermal coupling is one-way (below).

---

## Assumptions, as declared on the records

Shared by all four models:

- one cell, or a series string treated as one lumped cell with no cell-to-cell
  variation and no balancing;
- discharge only; charging is not modelled and no condition here would catch it;
- one uniform cell temperature, supplied from outside and never inferred;
- no diffusion or double-layer dynamics: no RC branch, no hysteresis;
- no ageing, no cycle life, no capacity fade, no resistance growth;
- no thermal runaway, no abuse response, no gas generation;
- no reversible (entropic) heat; the irreversible Joule term only.

Model-specific assumptions are on each record and are not repeated here.

---

## Declarations, and what each unlocks

A cell is five required numbers (`nominal_capacity`, `internal_resistance`, the
two OCV endpoints, `coulombic_efficiency`) plus an optional `CellLimits` record
of twenty declarations. **Every optional field defaults to `None`, meaning *not
declared* and never *typical for a cell of this kind*.**

A field left out removes the conditions that depend on it from IN_DOMAIN reach
and leaves them UNKNOWN. That asymmetry is the point: supplying more information
can only ever move a verdict away from UNKNOWN, and never turns a violated
condition into a satisfied one. A cell declared with only its five numbers is
UNKNOWN on every applicability condition in the domain, which is the honest
verdict for a part whose datasheet nobody supplied.

### The three inert categories

`chemistry` (on the cell), `cooling_mode` (on the limits) and `duty_type` (on
the load) are **declarations, never inferences, and never inputs**. Each is
validated against its vocabulary, serialized with its record, and read by
nothing. They record *why* a caller believes their declared numbers are credible
— a 3C continuous rating is plausible for a power cell and not for an energy
cell — and they never substitute for those numbers.

They are also not emitted as problem parameters, so nothing that could decide a
verdict is invisible to `ProvenanceRecord`, which admits only Quantity-valued
inputs. And they are excluded from `CellSpecification.physical_key`: a caller
must not be able to change what a solver considers the same system by asserting
a string.

This rule is absolute because a sibling domain shipped without it. The lumped
thermal model's constant-`hA` condition once returned `0.0` on
`regime == "forced"` before reading its arguments, so the condition reported
satisfied with the operating point and the bound both absent — a validity domain
whose strongest term was an unverifiable claim by the party being assessed. The
branch was removed; this domain does not repeat it, and
`test_no_declared_category_changes_any_verdict_at_all` compares every field of
every assessment across three declarations differing only in their strings.

---

## Coupling to the thermal domain

`coupling.py` marches a discharge forward against
`domains.thermal_models.lumped`, using its public API — `ThermalBody`,
`build_lumped_thermal_problem`, `LumpedThermalSolver` — and reimplementing none
of it. `systems/electrothermal/` is neither modified nor imported.

A run keeps **three claims apart**, on three different types:

| Claim | Where it lives | What it does during a run |
|---|---|---|
| Numerical convergence | each step's `ConvergenceState` | `NOT_APPLICABLE`, unchanged — both participants are closed forms |
| Coupling structure | the run's `CouplingDirection` | `ONE_WAY`, unchanged |
| Scientific validity | each step's `ValidityAssessment` per model | **this is what flips** |

### Why the coupling is one-way, and why that is not hidden

With a constant `R_int`, the heat `I²·R_int` does not depend on temperature. The
dependency graph is acyclic: the cell drives the body and the body does not
drive the cell back. There is no fixed point, so there is nothing to iterate
toward and nothing to converge.

The temptation is to run a fixed-point loop anyway and report `CRITERION_MET` on
the first pass, producing a record that *looks* like the electrothermal pack's.
That would be a fabricated convergence claim about an iteration that was never
needed. So this module iterates nothing, and the field is named for the
structure rather than for a verdict.

`CouplingDirection` has **one member**, because only one is executed. A
`TWO_WAY` member would be a name minted from intuition for a case this domain
cannot produce — the same reasoning by which the sibling pack deleted a
`DIVERGED` member. A genuinely two-way coupling needs `R_int(T)`; that is a real
next model, it is out of scope for v0, and it is recorded in `NEEDS.md` rather
than approximated here.

---

## The thresholds

Sixteen named bounds. **Fifteen are 1 or 0** — "you have consumed all of the
budget you declared", or "you are on the edge of the interval you declared" —
which is definitional and needs no citation, because the number follows from how
the ratio was defined.

**Exactly one is a real number**: `POLARIZATION_UNMODELLED_CEILING = 0.05`,
and it is labelled a **convention** in the constant, in the condition
description, in the documentation row and in the test that pins it. The physics
behind the condition *is* cited (Plett, Ch. 3, on the RC branch the Rint model
omits); the 0.05 is the universal engineering reading of "done" for a
first-order response, and no source in this repository's bibliography prints it
as a threshold for this quantity. It is not dressed as a citation.

That single convention is read from **both** ends of the relaxation, which is
why the condition admits two regimes and excludes the band between them: settled
at `t ≥ 3.0 τ_pol` (`exp(−3) = 0.05`) and undeveloped at `t ≤ 0.051 τ_pol`.
**Both of those bounds are conventions.** An earlier version of this condition
was a floor on `t/τ_pol` alone, which rejected every short pulse — the regime in
which a constant `R_int` is least in doubt.

`test_every_other_threshold_in_the_domain_is_definitional` enumerates every
dimensionless bound in all four records and asserts that exactly one is neither
0 nor 1, so a tuned constant cannot be added later without the suite noticing.

---

## Sources

- Plett, Gregg L., *Battery Management Systems, Volume I: Battery Modeling*,
  Artech House (2015). Ch. 2 — state of charge, capacity, the coulomb-counting
  integral. Ch. 3 — equivalent-circuit cell models, the OCV relationship, the
  Rint model and the RC diffusion branches it omits.
- Peukert, W., "Ueber die Abhaengigkeit der Kapacitaet von der
  Entladestromstaerke bei Bleiakkumulatoren", *Elektrotechnische Zeitschrift* 20
  (1897), 287–288.
- Doerffel, D. & Sharkh, S. A., "A critical review of using the Peukert equation
  for determining the remaining capacity of lead-acid and lithium-ion
  batteries", *Journal of Power Sources* 155 (2006), 395–400. Cited for what it
  establishes: that the extracted exponent is not a constant of the cell but
  varies with discharge current and with temperature.
- IEC 61960-3:2017, *Secondary cells and batteries containing alkaline or other
  non-acid electrolytes — Secondary lithium cells and batteries for portable
  applications*, Clause 7 (discharge performance; the conditions rated capacity
  is measured under).
- Incropera, F. P., DeWitt, D. P., Bergman, T. L. & Lavine, A. S., *Fundamentals
  of Heat and Mass Transfer*, 6th ed., Wiley (2007), §5.3, Eq. 5.25 — the lumped
  body with internal generation, for the `Q/hA` steady rise.

Continuous ratings, pulse ratings, temperature ranges and property spans are
**per-cell datasheet facts declared by the caller**, not values this domain
supplies. The conditions are stated over dimensionless utilizations of them so
that one model record serves every cell.

---

## Testing

178 tests in `tests/domains/battery/`, all in the FAST tier (they execute
closed-form arithmetic in milliseconds). Every applicability condition has three
tests — IN_DOMAIN, OUTSIDE_VALIDATED_DOMAIN, and missing-input → UNKNOWN — and
each OUTSIDE test asserts its model's `violated` tuple, so a threshold moved by
accident cannot hide behind a neighbour's failure.

Shared builders live in `battery_cases.py` rather than in a `conftest.py`:
`tests/test_tier_classification.py` imports the *root* `conftest` by module
name, and a second file of that name anywhere under `tests/` shadows it. Test
module basenames are prefixed `test_battery_` for the same reason — the suite's
parallel-safety audit records "duplicate module basenames: none", and that is
worth keeping true.
