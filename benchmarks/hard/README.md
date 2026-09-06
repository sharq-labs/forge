# Adversarial electro-thermal benchmark — 2000 cases

## Run it
    python benchmarks/hard/score_hard.py --src src       --cases benchmarks/hard/cases_hard --workers 4 --split dev

Writes the tracked `benchmarks/hard/results_hard.json`. About 20 s at
`--workers 4` on a 24-core host.

`--split dev` is not optional decoration. 600 of the 2000 cases are a **sealed
hold-out** and the scorer exits non-zero if you try to score them without
`--open-holdout`; see [The hold-out split](#the-hold-out-split) at the foot of
this file for why. `--workers` is bounded rather than `auto` because each worker
carries its own engcore import and the pool dies as a `BrokenProcessPool` when a
many-core machine exhausts RAM.

**Current numbers live in `results_hard.json` and in the release page,
[docs/release/v1.0.md](../../docs/release/v1.0.md). The tables below are the
round-by-round history that produced them, and every figure in them is a
full-set figure the generator was tuned against.**

## Files
| File | What |
|---|---|
| `generate_hard.py` | The generator. `verify_sound()` is the independent soundness check. |
| `score_hard.py` | The scorer. |
| `cases_hard/*.json` | 2000 cases: payload + ground truth. |
| `index_hard.json` | Composition by label, verdict and defect tag. |
| `split_hard.py` | The 70/30 development / hold-out split rule. `--verify` prints the composition proof. |
| `split_hard.json` | The split itself: seed, rule, digests, and both id lists. |
| `results_hard.json` | The current **development-split** run. Carries the case-set digest. |
| `HOLDOUT_OPENINGS.log` | Every time the sealed hold-out was scored. Empty means never. |

## Composition
**As of the first draw — superseded twice below.** 453 sound, 1547 unsound, 95
distinct defect tags. The set on disk today is **342 sound, 1658 unsound, 144
distinct defect tags**, seed 20260906; `index_hard.json` is authoritative and
this paragraph is kept only because the rounds that follow argue against it.

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

**Full-set figures for the current draw are withheld: publishing a full-set
number beside a development number hands the hold-out over by subtraction,
which defeats the seal.** The development-set metrics are at the foot of this
file and are the only ones published until the hold-out is opened.

| Metric | after ratings round | after convection round | after geometry relabel |
|---|---|---|---|
| Catch rate | 1623/1643 (98.8%) | withheld | withheld |
| False accept | 20/1643 (1.22%) | withheld | withheld |
| False reject | 0/357 (0.0%) | withheld | withheld |
| Exact verdict match | 1806/2000 (90.3%) | withheld | withheld |

The `after ratings round` column survives because it was scored against a case
set that **no longer exists** — the convection round regenerated the draw, so
that column's digest differs from today's and it cannot be differenced against
the development figure. The two withheld columns were scored against today's
2000 cases (the convection column against a draw differing in only the 124
`geometry_conflict` cases), and either one would give the hold-out away.

**The first two false-accept columns were dominated by cases the tool is right
about, and the third column is what happens when that is corrected.**

`geometry_conflict` drew its factor from {3, 10, 0.1, 30}, and 3 is *exactly*
the sphere's shape factor — the number `GEOMETRY_AGREEMENT_FACTOR` was derived
from, and where the bound is inclusive on purpose. Admitting a body whose V/A_s
is exactly L_c/3 is correct; those labels were wrong. That draw happened to
produce 15 of them where the previous produced 8:

| | after ratings | after convection | after relabel |
|---|---|---|---|
| False accepts, total | 20 | withheld | withheld |
| of which `geometry_conflict` at exactly 3× (correct to admit) | 8 | 15 | 0 |
| **remaining, and real** | **12** | withheld | withheld |

The `geometry_conflict` counts are kept because they are the size of a
relabelling, not a score: they say how many cases carried a wrong label, which
is a property of the generator rather than a measurement of the tool.

The shaper now draws the factor from {3·1.05, 1/(3·1.05), 30, 1/30} — strictly
outside the tolerance, two just past it and two an order beyond, one pair on
each side — and the boundary value is excluded in the shaper's docstring so it
cannot be reintroduced. The list stays four elements long so `rng.choice`
consumes the same draw and every non-geometry case was byte-identical to the
previous set: **only the 124 `geometry_conflict` cases changed.**

**The real false accepts did not move across the relabel** — the same count
before and after. The headline false-accept rate fell because 15 mislabelled
cases left the numerator, not because the tool improved. The two rates
themselves are withheld for the reason given under Baselines. What remains is
8 `band_out` (including two drawn a full 20% outside the band, so these are
genuine misses rather than rounding), 2 `adv_unsound:small_overshoot` and 1
`runaway` — and all eleven have since been run down; see `NEEDS.md`,
small-corrections round, §1.

**Eight of the eleven are the tool's, not this file's.** The `band_out` cases
are bodies that start below `T_ref` and warm toward it, so the largest
excursion is at t = 0; the tool judges `linearization_excursion_ratio` only at
the converged endpoint and never looks there. Its own sibling condition, the
Debye floor, is deliberately evaluated over the path with a docstring giving
exactly the argument that applies to the band. Those labels are right and the
tool misses them. The other three — 2 `small_overshoot` and 1 `runaway` — are
this file's, and §1.2 and §1.3 say how.

**So the run of rounds in which the generator was the weaker of the two does
not extend to what is left.** It is worth saying, because the opposite is the
comfortable reading.

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

---

# The hold-out split

## Why it exists

The generator behind these 2000 cases has been corrected **four times** in
response to what scoring them revealed: `verify_sound()` gained the linear TCR
form's own 200-450 K range, then component ratings, then the whole set was
regenerated for convection, then `geometry_conflict` stopped drawing the sphere's
exact shape factor. Every one of those corrections is defended above, and every
one of them is right. That is precisely the problem. A benchmark that gets
corrected whenever it disagrees with the tool converges on agreeing with the
tool, and no amount of care in the individual corrections changes what the
final number then measures. **Every figure in the baseline tables above is a
figure this generator has been tuned against, four times over.** The hold-out
is the only one that is not: 600 cases drawn by a rule fixed before they were
scored, sealed against inspection, and opened once. It is the difference
between "the tool scores 91.6 % on cases we kept adjusting until it did" and
"the tool scores X on cases nobody looked at", and only the second is evidence.

## The rule

Fixed in `split_hard.py`; seed **20260906**, rule id **`stratified-hash-hamilton/1`**.

1. A case's **stratum** is its `ground_truth.defect` tag — 144 of them.
2. Within a stratum, cases are ordered by `sha256(f"{seed}:{case_id}")`, case id
   as tiebreak. Not a draw: no generator state, nothing to re-sample. Re-running
   gives the same answer; a different answer requires editing the tracked seed.
3. The hold-out gets `round(0.30 * 2000) = 600` seats, allocated across strata by
   **largest remainder** — `floor(0.30 * n_s)` each, leftovers to the largest
   fractional remainders, ties broken by stratum name.
4. The hold-out is the first `k_s` of each stratum's order; the development set
   is the remaining 1400.

Reproduce and check:

    python benchmarks/hard/split_hard.py --cases benchmarks/hard/cases_hard --verify

## The composition is preserved, and here is the check

The test is on **proportions**, not counts — the partitions are different sizes,
so equal counts would be the wrong test. For each of the 144 defect tags, its
share of the hold-out is compared with its share of the development set.

| | |
|---|---|
| Development / hold-out | 1400 / 600 (exactly 30.0 %) |
| Distinct defect tags | 144 total; **144** present in dev, **139** in hold-out |
| Largest \|share gap\| over all 144 tags | **0.00119** — one case's worth of a 600-case set |
| Largest \|share gap\| by `label` | 0.0043 (`model_inapplicable`: 40.07 % dev vs 40.50 % hold-out) |
| Largest \|share gap\| by `expected_verdict` | 0.0052 (`NOT_SUPPORTED`: 69.64 % vs 70.17 %) |
| `SUPPORTED` share | 17.21 % dev vs 16.83 % hold-out |

The five tags absent from the hold-out are the five strata that hold **one case
each** — `horizon_in@0.002`, `horizon_in@0.05`, `horizon_in@0.2`,
`rating_current_in@0.01`, `rating_voltage_in@0.002`. A stratum of one is 100 %
on one side of any split and 0 % on the other; no stratified rule can do
otherwise, and this is stated rather than rounded away.

**It is the rule that preserves the composition, not the seed.** Re-running the
split at each of the nine seeds 20260902-20260910 gives a largest share gap of
**0.00119 at every one of them**, the published seed included. The seed was
fixed to the round's date before the split was computed; the sweep is there so
that a reader does not have to take that on trust. The sweep reports composition
only — no alternative split was ever scored, because scoring alternative splits
is exactly the search this file exists to prevent.

## How the seal is enforced

In the harness, not by convention. `score_hard.py --split` takes `dev`,
`holdout` or `all`; the last two contain sealed cases and **exit non-zero**
without `--open-holdout`:

    $ python benchmarks/hard/score_hard.py --src src --cases benchmarks/hard/cases_hard
    REFUSED: --split all scores the sealed hold-out.
      600 of 2000 cases are sealed under rule stratified-hash-hamilton/1, seed 20260906.
      ...
      Development runs:   --split dev
      Final evaluation:   --split all --open-holdout --note "why"

Opening appends a dated line to `HOLDOUT_OPENINGS.log` — UTC timestamp, split,
case-set digest, hold-out digest, the four metrics and a stated reason. The log
is tracked, so an opening is a line in the repository's history rather than a
claim in a document, and a second opening cannot be mistaken for the first.

The seal binds to the bytes: it applies only when `split_hard.json`'s
`case_set_digest` matches the case files actually on disk. `cases_battery` has
no split, so scoring it is unrestricted and its summary says so.

**What the seal does not do.** It stops the hold-out *cases* from being scored,
listed, or diffed run-to-run — which is the mechanism by which a benchmark gets
fitted to a tool. It does not make the hold-out aggregate unknowable: the
full-set figure is published above, so hold-out ≈ (full − dev) is arithmetic
anyone can do. Saying otherwise would be another unearned number.

## Development-set result

    python benchmarks/hard/score_hard.py --src src \
      --cases benchmarks/hard/cases_hard --workers 4 --split dev

| Metric | **development set (1400 of 2000)** |
|---|---|
| Exact verdict match | **1282/1400 (91.6%)** |
| Catch rate | **1149/1159 (99.1%)** |
| False accept | **10/1159 (0.86%)** |
| False reject | **1/241 (0.41%)** |
| Runs ending in an exception | **0** |

**These are the only metrics published for this case set.** There is no
full-set column, and there was one until the seal was audited: printing 1400
correct-of-1400 beside 2000 correct-of-2000 states the hold-out's score as a
subtraction, so the seal was worth nothing while both were on the page.

Ten known false accepts and the one known false reject (`S00709`, diagnosed
above) fall in the development set. `src/` was not touched in the round that
produced this split. The split re-partitions the measurement; it does not
change it, which was verified by comparing all 1400 development rows against
the same 1400 rows of a pre-split full run — every row identical — rather than
by scoring the hold-out.

**The hold-out has not been scored.** `HOLDOUT_OPENINGS.log` is the record of
whether that is still true.

## The publication rule

Until the hold-out is opened, **only development-set metrics are published**.
No figure computed over the current 2000 cases appears in this file,
`NEEDS.md`, or `docs/release/v1.0.md`, because a full-set figure beside a
development figure is the hold-out in two subtractions. Figures from superseded
draws are kept and labelled: their case sets have different digests, so they
cannot be differenced against anything current.

When the hold-out is opened — once — the full-set figure becomes publishable,
because at that point there is nothing left to protect.
