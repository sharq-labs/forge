# Public rediscovery development — L1

This is an executable integration fixture, **not blindfold, measured physics
validation, a frozen benchmark or evidence of novel discovery**. Public truth is
R = 2 ohm; the engine is given V = R I and estimates R. No structure search,
model selection, experiment selection or final evaluation is performed.

## Run on Windows

From the repository root, with the existing environment:

```powershell
.\.venv\Scripts\python.exe -m benchmarks.rediscovery_development.run --output .forge/l1-development.json
.\.venv\Scripts\python.exe -m benchmarks.rediscovery_development.run --replay .forge/l1-development.json
.\.venv\Scripts\python.exe -m pytest tests/mind/test_rediscovery_development.py -q
```

Output files must not already exist. Use a fresh filename for a new source
version; old records are not rewritten to manufacture successful replay.
The JSON record contains the public problems, existing Assessment records,
implementation bindings and an analytic reference. Exact replay re-executes
the cases and compares the complete deterministic record. Changing inputs,
model/source, environment identity or results can invalidate replay.
Elapsed time is printed separately on stderr; it measures the entire command,
including bookkeeping, and is not per-method performance evidence.

## Cases and interpretation

| Case | What it tests | What must not be inferred |
|---|---|---|
| informative | Recover R from nonzero input | Equation discovery |
| milliamps | Same physical input expressed in mA | New independent success case |
| uninformative | All-zero input cannot identify R | Zero residual proves the parameter |
| misspecified | Added 1 V offset violates the supplied family | Recovered resistance is physically valid |
| unknown_noise | Missing uncertainty stays unknown | Noiseless fixture implies known zero uncertainty |

All are noiseless software controls. Where present, sigma = 0.01 V is an explicit
analysis assumption/resolution, not an empirical noise estimate or a stochastic
noise realization. Standard errors are conditional on that assumption. This
suite does not measure interval coverage, false-support/refusal rates, useful
answer rates or superiority over alternatives.

The analytic through-origin least-squares reference sees the same known equation
and calibration rows as the engine. Both exclude the initial row: 21 available,
20 scored. The reference uses observed arrays, never the public R value. It gives
no uncertainty or scientific acceptance verdict. This elementary L1 reference
is not a sufficient baseline suite for L2/L3 or a formal blindfold campaign.

Current is 0–2 A (0–2000 mA); R bounds are 0.1–10 ohm. The illustrative family is
static and linear: no heating, dynamics, battery claim or extrapolation is tested.
There is no selection set or final set in this L1 fixture. Generalization claims
must remain NOT_ASSESSABLE. Subsequent L2/L3 work must add separate calibration,
selection and independent final roles before ranking or scoring those stages.

## Next gates

L1 integration does not waive project gates. L2 needs bounded model alternatives,
selection data and ambiguity controls. L3 needs an explicit admissible grammar,
equivalence rules and competent symbolic baselines. Both need observation budgets
and per-method compute accounting. Formal hidden cases belong to the independent
custodian, outside coding-agent access; OS isolation and final qualification are
not established by running this public fixture on Windows.
