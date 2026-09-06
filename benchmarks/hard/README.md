# Adversarial electro-thermal benchmark — 2000 cases

## Run it
    python benchmarks/hard/score_hard.py --src src --cases benchmarks/hard/cases_hard

Writes `results_hard.json`. Parallel over cores; a few minutes.

## Files
| File | What |
|---|---|
| `generate_hard.py` | The generator. `verify_sound()` is the independent soundness check. |
| `score_hard.py` | The scorer. |
| `cases_hard/*.json` | 2000 cases: payload + ground truth. |
| `index_hard.json` | Composition by label, verdict and defect tag. |
| `results_hard.json` | Baseline run against main. |

## Composition
453 sound, 1547 unsound, 95 distinct defect tags.

What makes it hard: every threshold case sits at a controlled distance from its
bound (0.2%, 1%, 5%, 20%) on **both** sides — a case 1% inside must be accepted,
1% outside must be refused. Plus adversarial-sound cases that look alarming but
are fine, adversarial-unsound cases that look tame but are broken, compound
defects with a stated precedence, and near-miss unit errors (a factor of 2, not
1000).

## Ground truth
Computed in Python from first principles; never consults engcore. The generator
solves the electro-thermal fixed point itself and computes Biot, the radiation
share, the excursion budgets and the Fourier number. `verify_sound()` re-checks
**every** condition before a case may be labelled sound, with a margin on all of
them except the one the shaper deliberately placed near its bound.

An earlier draw mislabelled 16% of its sound cases because shapers widened only
the limit they targeted and left another condition violated by the base draw.
`verify_sound()` is that fix, and 0% of the current sound set is mislabelled.

**If a case turns out to be labelled wrong and the tool right, say so
explicitly.** Do not quietly correct the generator.

## Composition after the ratings round

353 sound, 1647 unsound, 116 distinct defect tags, seed 20260906.

Two changes to ground truth, both because the tool turned out to be right:

* `verify_sound()` now checks the linear TCR form's **own declared range**,
  200-450 K, which is narrower than the `maximum_operating_temperature` a case
  declares. Omitting it mislabelled 61 cases as sound that ran far above 450 K;
  the tool correctly refused them and the benchmark scored that as a false
  reject.
* Cases now declare **component ratings**, and `shape_rating` places one at a
  controlled distance from the operating point on both sides, like every other
  threshold. A rating is a declared limit and a sound case must clear it.

## Baselines

| Metric | main `b60e757` | after this round |
|---|---|---|
| Catch rate | 1547/1547 (100%) | **1623/1643 (98.8%)** |
| False accept | 0/1547 (0.00%) | **20/1643 (1.22%)** |
| False reject | 453/453 (100%) | **0/357 (0.0%)** |
| Exact verdict match | 1236/2000 (61.8%) | **1806/2000 (90.3%)** |
| Runs ending in an exception | 40 | **0** |

**The first column's catch rate was unearned, and the second column is what
exposed it.** `electrical.dc.kcl` declared no validity conditions, so it
assessed UNKNOWN on every run and no payload could ever be SUPPORTED. Every
unsound case was "caught" by a verdict the tool gave to sound and unsound cases
alike; a tool that refuses everything catches everything. Once KCL states its
condition, the ratings have a payload field, and a stopped run produces a
report instead of an exception, the pair became informative for the first time
— and then had to be earned back, which it was.

A gate on catch rate is only meaningful alongside a gate on false reject.
NEEDS.md section 5 records why.

Three places the tool turned out right and this benchmark wrong, all corrected
here rather than in the domain: the linear TCR form's own 200-450 K range,
which `verify_sound()` did not check; `Fo = (t/tau)/Bi` rather than `t/tau`;
and component ratings, which no case declared. One place the benchmark turned
out right and the domain wrong: the Debye floor belongs at the coldest state a
run occupies, not at the temperature it converges to.

The 20 remaining false accepts are 11 `band_out`, 8 `geometry_conflict` built
exactly at the sphere's shape factor where the bound is inclusive on purpose,
and one small overshoot.

## Composition after the convection round

342 sound, 1658 unsound, 144 distinct defect tags, seed 20260906. **The case
set was regenerated**, because the domain now asks where `ambient_conductance`
came from and no case in the previous draw said.

### Why regenerating was not optional

Scoring the *previous* 2000 cases against the new domain gives catch rate
**100%**, false accept **0.00%** and false reject **100%**. That is the
unearned catch rate this file already warns about, in its purest form: with
three new conditions that no case could answer, every model assessed UNKNOWN
and nothing could be SUPPORTED. A tool that refuses everything catches
everything.

So every case now declares a fluid conductivity, kinematic viscosity, Prandtl
number and convection length, plus **exactly one** of an expansion coefficient
(free convection) or a velocity (forced) — declaring both is mixed convection
and the domain refuses it.

### What is synthetic about the fluid, and why that is fine

`hA` and `surface_area` are drawn independently, so h = hA/A_s spans about six
decades. No real fluid gives 10⁵ W/(m²K) at a sane length and velocity. The
length, velocity and expansion coefficient are therefore kept physical and the
**fluid conductivity is solved for**, `k_f = h·L/Nu`, which makes the declared
hA exactly what its correlation predicts. The resulting k_f is often not a real
fluid's. That is the same status the rest of the draw has — `r0` is
10^U(0, 3.5) ohms — and **the tool has no fluid table and claims none**, so a
synthetic k_f tests exactly what these conditions are for: whether the declared
numbers are consistent with each other.

### Three new shapers, both sides

`conv_range_in/out` (Ra against 10⁹ or Re against 5×10⁵, route drawn),
`conv_prandtl_in/out` (Pr against 0.6, forced only — Churchill–Chu states no
Prandtl restriction, so manufacturing one would test a bound no source prints)
and `conv_agree_in/out` (the declared hA at a controlled distance from *both*
edges of the factor-of-2 band). 246 convection cases in this draw, **246 of 246
scored exactly right.**

## Baselines

| Metric | after ratings round | after convection round | after geometry relabel |
|---|---|---|---|
| Catch rate | 1623/1643 (98.8%) | 1632/1658 (98.4%) | **1647/1658 (99.3%)** |
| False accept | 20/1643 (1.22%) | 26/1658 (1.57%) | **11/1658 (0.66%)** |
| False reject | 0/357 (0.0%) | 1/342 (0.29%) | **1/342 (0.29%)** |
| Exact verdict match | 1806/2000 (90.3%) | 1821/2000 (91.0%) | **1836/2000 (91.8%)** |

**The first two false-accept columns were dominated by cases the tool is right
about, and the third column is what happens when that is corrected.**
`geometry_conflict` drew its factor from {3, 10, 0.1, 30}, and 3 is *exactly*
the sphere's shape factor — the number `GEOMETRY_AGREEMENT_FACTOR` was derived
from, and where the bound is inclusive on purpose. Admitting a body whose V/A_s
is exactly L_c/3 is correct; those labels were wrong. This draw happened to
produce 15 of them where the previous produced 8:

| | after ratings | after convection | after relabel |
|---|---|---|---|
| False accepts, total | 20 | 26 | 11 |
| of which `geometry_conflict` at exactly 3× (correct to admit) | 8 | 15 | 0 |
| **remaining, and real** | **12** | **11** | **11** |

The shaper now draws the factor from {3·1.05, 1/(3·1.05), 30, 1/30} — strictly
outside the tolerance, two just past it and two an order beyond, one pair on
each side — and the boundary value is excluded in the shaper's docstring so it
cannot be reintroduced. The list stays four elements long so `rng.choice`
consumes the same draw and every non-geometry case is byte-identical to the
previous set: **only the 124 `geometry_conflict` cases changed.**

**The real false accepts did not move: 11 before, 11 after.** The headline went
1.57% → 0.66% because 15 mislabelled cases left the numerator, not because the
tool improved. What remains is 8 `band_out` (including two drawn a full 20%
outside the band, so these are genuine misses rather than rounding), 2
`adv_unsound:small_overshoot` and 1 `runaway`.

**The one false reject is a mislabelled case, and the diagnosis above it was
wrong.** `S00709` is `rating_power_in@0.002`. The paragraph that stood here
said the tool "builds its circuit at the declared reference resistance … so it
computes 3.5634 W", and blamed `NEEDS.md` §A2.9. Measured, that is not what
happens: the rating conditions have always read the **converged** electrical
result, and the number they read is 3.5240 W.

The real cause is in this file's own generator. `base_draw` states each rating
against `R(T_ss)` — the resistance at the **steady state** — and
`shape_rating` places this one 0.2 % inside it: T_ss = 298.364 K, R = 62.605 Ω,
P = 3.4919 W, rated 3.49889 W. But the payload declares a 66.169 s run against
a 27.376 s time constant, so the body reaches 295.999 K and stops, 2.4 K short
of the steady state it was rated against. Cooler is stiffer's opposite — a
lower resistance — so the part dissipates **more**: 3.5240 W, or 1.0072× its
rating, at the operating point the case itself declares.

Nothing the run can offer clears it. The dissipation falls monotonically from
3.5635 W at t = 0 (the reference resistance, the cold start) towards 3.4919 W
and never arrives inside the declared horizon, so the rating is exceeded for
the whole run and the peak is at t = 0. **The tool is right and the label is
wrong**, in the same way the `geometry_conflict` labels were wrong: the
expectation is computed at an operating point the case does not declare.

Not fixed here. `shape_rating` must size a rating at the marched endpoint
rather than at a steady state the run never reaches, and that is a change to
the generator that would move the ratings cases across the whole draw — the
same reason the geometry relabel was kept to one shaper. The arithmetic is
pinned in `tests/mcp/test_problem.py::
test_s00709_is_over_its_rating_at_every_resistance_the_run_can_offer` so the
claim in this paragraph is checked rather than asserted.

§A2.9 itself *was* real and is now closed: the assessment's element list came
from the reference resistances, so the report named a resistance the circuit
had not used. It could never move a verdict — the only condition reading
`resistance` is `resistance > 0` — and it did not move this one.

## The battery benchmark — 400 cases

    python benchmarks/hard/score_hard.py --src src \
      --cases benchmarks/hard/cases_battery --results results_battery.json

| File | What |
|---|---|
| `generate_battery.py` | The generator. Reimplements the self-heating march and re-checks all fourteen conditions. |
| `cases_battery/*.json` | 400 cases, each naming `"system": "battery"`. |
| `index_battery.json` | Composition by defect tag. |
| `results_battery.json` | Baseline. |

`score_hard.py` dispatches on the case's `system` key, which is absent on every
electro-thermal case ever written — so its absence means that system rather
than an error, and one scorer serves both.

### Composition

181 sound, 219 unsound, 110 distinct defect tags. Twelve of the fourteen
applicability conditions are shaped at 0.2 %, 1 %, 5 % and 20 % from their
bounds on **both** sides; the other two, `terminal_voltage_ratio` (> 0) and
`peukert_capacity_ratio` (≤ 1), are directional statements with no declared
bound to place a case against and are checked but not shaped. Plus twelve
omission cases, one per optional limit, each asserting that a missing
declaration is UNKNOWN and never IN_DOMAIN.

### Result

| Metric | battery |
|---|---|
| Exact verdict match | **400/400 (100.0%)** |
| Catch rate | **219/219 (100.0%)** |
| False accept | **0/219 (0.00%)** |
| False reject | **0/181 (0.0%)** |

### Scored over the battery models, and why that is not softening

**No battery case can reach SUPPORTED as a whole report.**
`run_self_heating_discharge` accepts no applicability declaration for the
thermal body it marches, so the lumped model is UNKNOWN in every coupled
battery run. Scored whole-report the numbers are catch rate 100 %, false accept
0 %, false reject **100 %** — the unearned catch rate this file already warns
about, measuring one gap 400 times.

So a battery case is scored over the four **battery models'** verdicts, by the
same precedence `derive_verdict` uses: a violation outranks a gap. Every one of
the fourteen conditions still has to be right, at 0.2 % from its bound, on both
sides. The thermal gap is a real finding and is recorded in `NEEDS.md` C.1
rather than absorbed into a number; it is roughly a five-line change to
`battery/coupling.py`, which the round that added this boundary was forbidden
to make.
