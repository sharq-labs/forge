# K4 — Model adequacy and model competition freeze

Status: **PASS / FROZEN**

Milestone ID: `K4`

## Frozen identities

- K4 preregistration commit: `3e685454d44d81e3fa446f41bcc26160eb11c372`
- K4 scored source commit: `da1e9bb1758d7b0d622b90368712a1e24c9fd2a2`
- K3.1 stable baseline before K4: `f5a932c03a35cb45e661d03d725ea96aecb2f974`
- K3 scored H1/H2 cache producer: `68fcc6a6a9ea305016119a86238aa9329ef33b9c`
- K2 scientific source: `eab5879e8c17d5c1cf8f697f0eb2e57816cc99b5`

The preregistration was frozen before K4 implementation and was not rewritten after scoring.

## Models compared

### M1 — Arrhenius non-isothermal CSTR

- model id: `kinetics.cstr.nonisothermal_first_order`
- version: `0.1.0`

### M2 — constant-rate first-order CSTR approximation

- model id: `kinetics.cstr.nonisothermal_first_order_constant_rate`
- version: `0.1.0`
- model type: `APPROXIMATION`

M2 used the same verified CSTR numerical machinery at the exact `activation_energy = 0` reduction, while scientific result/provenance binding identified M2 explicitly. Numerical evidence was not allowed to masquerade as M1 evidence.

## Evidence split

Both models were fitted only to the frozen K2 C1/C2/C3 training evidence and were scored only on the frozen K3 H1/H2 held-out conditions.

The scored path preserved the frozen seeds, noise declarations, support rules and K3.1 predictive-admission mass budget of `1e-12`.

No H1/H2 observation entered either posterior fit.

## M2 forward execution

Training grid:

- support: `121` points
- admitted: `88/121`
- workers: `24`
- wall telemetry: `26.66 s`

Held-out predictive grid:

- support: `121` points
- admitted: `97/121`
- workers: `24`
- wall telemetry: `21.29 s`

The wall times and worker count are execution telemetry, not scientific acceptance criteria.

## Primary predictive-support accounting

- M1 unsupported predictive posterior mass: `2.5757981943588344e-224`
- M2 unsupported predictive posterior mass: `0.0`
- frozen maximum unsupported posterior mass: `1e-12`

Both models therefore satisfied the preregistered predictive-admission policy for the primary comparison.

## Primary out-of-sample comparison

Exact finite-mixture held-out log predictive scores:

- M1: `-6.021523`
- M2: `-65362.582231`
- delta `M1 - M2`: `+65356.560707`

The positive delta is evidence that M1 had stronger predictive support on the declared held-out study. It is **not** a Bayes factor, a probability that M1 is true, or a global physical-validation claim.

## Repeated paired competition

Across the 20 preregistered repeated paired held-out datasets:

- M1 beat M2 in `20/20` pairs;
- every paired delta was positive;
- the aggregate paired delta was therefore strictly positive;
- every repeated M1 predictive-support loss remained far below the frozen `1e-12` budget;
- every repeated M2 unsupported predictive mass was `0.0` in the scored run.

This exceeds the preregistered A8 requirement of at least `14/20` M1 wins plus a strictly positive sum of paired deltas.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A1 — shared adequacy math | PASS |
| A2 — competitor explicit and versioned | PASS |
| A3 — fit/predict separation | PASS |
| A4 — numerical admission | PASS |
| A5 — Arrhenius repeated predictive adequacy | PASS |
| A6 — Arrhenius standardized residual behavior | PASS |
| A7 — primary comparison finite | PASS |
| A8 — repeated competition | PASS |
| A9 — model-specific evidence not conflated | PASS |
| A10 — deterministic replay | PASS |
| A11 — claim boundary | PASS |
| A12 — regression safety | PASS |

## Regression gate

Full repository regression executed against scored source `da1e9bb1758d7b0d622b90368712a1e24c9fd2a2`:

- `1330 passed`
- `4 warnings`
- `0 failed`
- `0 errors`
- wall time: `203.97 s` (`0:03:23`)

The four warnings were the existing scikit-learn Gaussian-process `ConvergenceWarning` messages from `tests/test_smoke.py`; they were not K4 failures.

## Scientific claim boundary

K4 establishes only study-bounded predictive adequacy and relative out-of-sample predictive support under the frozen synthetic study.

K4 does **not** establish that:

- M1 is physically or universally true;
- M2 is globally invalid;
- either model is experimentally validated;
- the score difference is a model truth probability;
- synthetic holdout evidence substitutes for physical validation.

Neither model's global `ModelValidationStatus` is upgraded by K4 synthetic evidence.

## Frozen outcome

K4 is **PASS / FROZEN**.

The frozen milestone now demonstrates that the platform can keep numerical admission, posterior uncertainty, predictive support accounting, model-specific provenance, held-out adequacy and competing-model evidence separate rather than collapsing them into a single notion of correctness.

Any future model-adequacy or competition change must be a successor milestone. The K4 preregistration, thresholds, seeds, evidence split and frozen result are historical evidence and must not be rewritten post hoc.
