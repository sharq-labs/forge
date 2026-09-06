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

## Baseline on main
| Metric | Result |
|---|---|
| Catch rate | 1547/1547 — 100% |
| False accept | 0/1547 — 0.00% |
| False reject | 453/453 — 100% |
| Exact verdict match | 1236/2000 — 61.8% |
| Accuracy 0.2% outside a bound | 92% (does not degrade at the edge) |

Every sound case is refused because the electrical models leave their rating
conditions UNKNOWN — the payload has no field to declare a rating. That is the
gap TASK 1 closes.
