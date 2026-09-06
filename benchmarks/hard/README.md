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

| Metric | main `b60e757` | after TASK 1 + KCL |
|---|---|---|
| Catch rate | 1547/1547 (100%) | 1404/1647 (85.2%) |
| False accept | 0/1547 (0.00%) | 243/1647 (14.75%) |
| False reject | 453/453 (100%) | 19/353 (5.4%) |
| Exact verdict match | 1236/2000 (61.8%) | 1595/2000 (79.8%) |

**The first column's catch rate was unearned and the second column is what
exposed it.** `electrical.dc.kcl` declared no validity conditions, so it
assessed UNKNOWN on every run and no payload could ever be SUPPORTED. Every
unsound case was "caught" by a verdict the tool gave to sound and unsound cases
alike. Once KCL states its condition and the ratings have a payload field, the
tool can say SUPPORTED — and the cases it should still be refusing become
visible. They are the remaining tasks: geometry conflict (88), the horizon
condition (103 across three tags), and melting-versus-ceiling (28).

