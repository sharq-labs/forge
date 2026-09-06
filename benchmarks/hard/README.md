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

| Metric | after ratings round | after convection round |
|---|---|---|
| Catch rate | 1623/1643 (98.8%) | **1632/1658 (98.4%)** |
| False accept | 20/1643 (1.22%) | **26/1658 (1.57%)** |
| False reject | 0/357 (0.0%) | **1/342 (0.29%)** |
| Exact verdict match | 1806/2000 (90.3%) | **1821/2000 (91.0%)** |

**Both false-accept columns are dominated by cases the tool is right about.**
`geometry_conflict` draws its factor from {3, 10, 0.1, 30} and 3 is *exactly*
the sphere's shape factor, which is the number `GEOMETRY_AGREEMENT_FACTOR` was
derived from and where the bound is inclusive on purpose. Admitting those is
correct and the labels are wrong. This draw happened to produce 15 of them
where the previous produced 8:

| | after ratings | after convection |
|---|---|---|
| False accepts, total | 20 | 26 |
| of which `geometry_conflict` at exactly 3× (correct to admit) | 8 | 15 |
| **remaining** | **12** | **11** |

So the real false accepts went **down**, 12 to 11, and the corresponding catch
rates are 99.27% and **99.34%**. Fixing the labels means drawing the geometry
factor at 3·(1±margin) rather than exactly 3; it is not done here because it
would move the metrics for a reason unrelated to this round.

**The one false reject is a real one, and the tool is wrong about it.**
`S00709` is `rating_power_in@0.002`: the resistor dissipates 3.4886 W at the
converged fixed point against a 3.49889 W rating, 0.3% inside. The tool builds
its circuit at the **declared reference resistance** rather than the converged
one, so it computes 3.5634 W and reports the rating violated. That is
`NEEDS.md` §A2.9 — *"the resistor assessment reads the declared resistance, not
the converged one"* — recorded two rounds ago and witnessed by the benchmark
here for the first time, because no earlier draw put a power rating 0.2% from
the operating point of a conductor whose TCR moved the resistance by 2%. The
error is conservative (it over-reports dissipation for a positive-TCR part that
heats up), which is why it shows as a false reject rather than a false accept.
Not fixed here: the fix is in the electrothermal coupling, which this round
does not own.
