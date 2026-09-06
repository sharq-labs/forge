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

| Metric | after ratings round | after convection round | after geometry relabel | after rating relabel |
|---|---|---|---|---|
| Catch rate | 1623/1643 (98.8%) | 1632/1658 (98.4%) | 1647/1658 (99.3%) | **1647/1658 (99.3%)** |
| False accept | 20/1643 (1.22%) | 26/1658 (1.57%) | 11/1658 (0.66%) | **11/1658 (0.66%)** |
| False reject | 0/357 (0.0%) | 1/342 (0.29%) | 1/342 (0.29%) | **0/342 (0.0%)** |
| Exact verdict match | 1806/2000 (90.3%) | 1821/2000 (91.0%) | 1836/2000 (91.8%) | **1837/2000 (91.8%)** |

**Both of the last two columns are label corrections, and neither is a tool
improvement.** In both rounds the generator was the weaker of the two and the
tool was right. Saying so is what makes the rest of the numbers worth reading.

### The geometry relabel

`geometry_conflict` drew its factor from {3, 10, 0.1, 30}, and 3 is *exactly*
the sphere's shape factor — the number `GEOMETRY_AGREEMENT_FACTOR` was derived
from, and where the bound is inclusive on purpose. Admitting a body whose V/A_s
is exactly L_c/3 is correct; those labels were wrong. That draw happened to
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
consumes the same draw and every non-geometry case was byte-identical to the
previous set: **only the 124 `geometry_conflict` cases changed.**

**The real false accepts did not move: 11 before, 11 after.** The headline went
1.57% → 0.66% because 15 mislabelled cases left the numerator, not because the
tool improved. What remains is 8 `band_out`, 2 `adv_unsound:small_overshoot`
and 1 `runaway`.

### The rating relabel — the operating point, not the asymptote

`S00709` was this benchmark's only false reject, and the paragraph that stood
here blamed `NEEDS.md` §A2.9: the tool "builds its circuit at the declared
reference resistance … so it computes 3.5634 W". **Measured, that is not what
happens.** The rating conditions have always read the converged electrical
result — §A2.9's defect was in the element list and could only ever reach
`resistance > 0` — and the number they read is 3.5240 W.

The cause was in this file. `base_draw` sized every rating against `R(T_ss)`,
the resistance at the **steady state**, and `shape_rating` placed this one
0.2 % inside it: T_ss = 298.364 K, R = 62.605 Ω, P = 3.4919 W, rated 3.49889 W.
But each payload declares a finite `duration`, and the tool marches a
first-order lumped model to that horizon and **stops**. This case declares
66.169 s against a 27.376 s time constant, so the body reaches 295.999 K —
2.4 K short of the steady state its rating was sized at. A positive-TCR
conductor that is cooler is *less* resistive, so it dissipates **more**:
3.5240 W, 1.0072× its rating, at the operating point the case itself declares.
The tool refused a design that really was over its rating, and the benchmark
scored that refusal as a miss.

**The fix is `endpoint_temperature`.** It solves the same fixed point
`steady_temperature` does, with the first-order reach factor applied:

    T(dur) = T_amb + (P(T)/hA)·(1 − e^(−dur/τ)) + (T_init − T_amb)·e^(−dur/τ)

`base_draw` sizes `_p_diss` and `_i` from it, and `shape_rating` refreshes the
operating point before placing a rating, so the margin a case declares is the
margin the tool measures. Checked against the tool on 148 sampled cases: the
formula reproduces the converged resistance and dissipation to 1e-9 relative,
which is the coupling tolerance rather than a difference.

The map is the steady one scaled by a factor ≤ 1, so it is strictly the more
contractive of the two and converges wherever the steady map does. It therefore
rejects no draw the old form accepted and **the draw sequence is unchanged**:
2000 cases, 342 sound, 1658 unsound, 144 defect tags, same seed, as before.

**What moved.** 1744 of 2000 case files, because every case carries default
ratings at 3× its operating point and that point shifted. **One verdict**:
`S00709`, now SUPPORTED, and **all 83 rating cases score exactly right, with
zero mismatches.** False reject 1 → 0; catch rate, false accept and the
false-accept ID list are unchanged. No bound moved and nothing in the tool was
touched.

`_t_ss` is still drawn and still sets the thermal limits — those are about
where the body ends up. The ratings are about what the part is doing while it
gets there, and the two are not the same question.

The original arithmetic is pinned in `tests/mcp/test_problem.py::
test_s00709_is_over_its_rating_at_every_resistance_the_run_can_offer`, which
keeps the pre-correction payload deliberately: it is the assertion that the
tool refuses a part over its rating at the point it converges to, and a
benchmark whose labels are now sized at that same point could not catch a
regression in it.

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
