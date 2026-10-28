# Public L2 development integration

Two supplied families: V = a I (a in ohm) and V = b I² (b in V/A²).
This tests selection among declared alternatives, not structure discovery.
All four fixture truths are public and noiseless. No blindfold, final evaluation,
physical validation or scientific superiority claim is made.

## Run

```powershell
.\.venv\Scripts\python.exe -m benchmarks.rediscovery_l2.run --output .forge/l2-development.json
.\.venv\Scripts\python.exe -m benchmarks.rediscovery_l2.run --replay .forge/l2-development.json
.\.venv\Scripts\python.exe -m pytest tests/mind/test_l2_development.py -q
```

Output creation refuses existing files. Replay compares the complete regenerated
record, including source, observations, models and decisions. Telemetry is printed
to stderr with the deterministic record digest and can be saved separately. It
measures local fit+selection time for each engine/reference family; engine time
includes contract checking and assessment bookkeeping. Timing is not replayed and
does not establish algorithmic efficiency or a campaign budget.

## Data roles and scope

Each family is fitted on calibration only through the existing repsem.v2 path.
There are 21 available calibration rows, 20 scored (existing engine excludes
the initial row), and 20 selection rows scored by both engine and reference.
The analytic reference fits the same one-parameter family with the same positive
0.1–10 parameter bounds and observation budget. No final data is accepted.
No selection observations or selection threshold enter the fit/assessment spec.

Selection sample/group IDs must not overlap calibration IDs. This catches declared
lineage overlap, not fraudulent relabeling or physical dependence. The public
controls share a declared generating formula; group names do not prove independence.
Selection currents must lie within the scored calibration range. Units convert
to A/V before fitting, applicability checks and RMSE calculation.

The caller supplies a positive development RMSE resolution in volts. The fixtures
use 0.01 V as an illustrative engineering input, **not a measured noise level,
significance test, confidence interval or approved final acceptance policy**.
Exactly one compatible family yields ONE_COMPATIBLE; multiple yield AMBIGUOUS;
none yields NONE_COMPATIBLE. Unknown resolution or zero excitation yields
UNASSESSED. A selection result is not independent confirmation or final evidence.
The underlying assessments have no declared noise and cannot acquire uncertainty
from the selection threshold. Conditional identifiability of these single-scalar
families is checked by nonzero design energy, not by a generic scientific verdict.

Cases: linear truth, quadratic truth, ambiguity at constant I=1 A (both families
produce the same observations), and an added 1 V offset compatible with neither.
These are correctness controls, not an estimated false-support/refusal rate or
representative useful-answer rate. Generalization, unmodeled physics, negative
parameters, active experiments and final custody/isolation remain outside scope.

L1 package and its historical output are unchanged. L3 requires a separately
declared grammar/equivalence contract and competent structure-search baselines.
Mandatory project gates, independent custodian and Linux isolation remain open.
