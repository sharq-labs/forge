# Public bounded L3 support recovery

This exercises the existing sparse-discovery engine, **not a general symbolic
regression system**. The admissible dictionary is x, x², x³ with a fitted intercept.
All seven nonempty feature subsets are attempted, with coefficients fitted only
on calibration. Selection rows score those fixed fits. No final data is present.

Physical inputs normalize explicitly: x = I/(1 A), y = V/(1 V). Thus expressions
and target passed to the dimensionless discovery API have declared meaning. A
returned polynomial means V = (1 V) [c0 + c1 (I/1 A) + c2 (I/1 A)² + ...].
The same scales and dictionary apply to every case, independent of public truth.

## Run on Windows

```powershell
.\.venv\Scripts\python.exe -m benchmarks.rediscovery_l3.run --output .forge/l3-development.json
.\.venv\Scripts\python.exe -m benchmarks.rediscovery_l3.run --replay .forge/l3-development.json
.\.venv\Scripts\python.exe -m pytest tests/mind/test_l3_development.py -q
```

Existing output files are never overwritten. Whole-record replay binds the public
input, candidate records, grammar, development policy and implementation sources.
Elapsed solver times are separate stderr telemetry with the record digest. Both
methods have the same observations; sparse search attempts seven fits and dense
cubic fits once. This difference is explicit, not an equal-compute claim.

## What the outcomes mean

The caller supplies an illustrative RMSE resolution (fixtures: 0.01 V). This is
not measured noise, a confidence interval, a significance threshold or an approved
final evaluation policy. The wrapper reports the smallest compatible feature
subsets that also satisfy the engine's survival rule (including no worsening
against its calibration-mean baseline), without changing its ranking or records. One minimal support
is ONE_MINIMAL_SUPPORT; multiple are AMBIGUOUS; no compatible candidate is
NONE_COMPATIBLE. Unknown resolution, no fitted candidates, or constant calibration
target yields UNASSESSED. Intercept-only recovery is outside this engine's current
nonempty-support grammar. No coefficient-pruning tolerance or truth label is used
to choose a support. Supersets may fit too; minimality is a declared preference,
not a proof of a unique physical mechanism.

For distinct monomial supports, equality on a finite sampled set does not imply
polynomial equivalence. At x in {-1,1}, x and x³ are indistinguishable and this
fixture must remain ambiguous. The engine's legacy `holdout_rmse` and
`survived_holdout` names refer here to selection, never independent confirmation.

Public cases recover 1+2x, 1+3x², and 1+2x+3x²; negative controls include aliasing,
x⁴ outside the dictionary, and constant targets. Coefficient assertions use
1e-10/1e-12 numerical tolerances for noiseless least-squares verification only.
These six controls do not estimate population false-support/refusal/usefulness
rates. The full cubic least-squares reference is a competent predictive baseline
for this dictionary, not an independent numerical implementation: both use NumPy.
Rank-deficient dense fits are explicitly marked as not uniquely identified.

All calibration rows are scored, unlike repsem L1/L2's initial-row convention;
both L3 methods use this same budget. Physical sample/group identifiers must be
disjoint; this validates declared lineage, not independent custody or fraudulent
relabeling. Selection is constrained to the calibration current range. Hidden
truth, evaluator seeds, real data, autonomous experiments and final-test access
remain absent. L1/L2 sources and records are preserved, and mandatory project
gates and independent Linux isolation remain open.
