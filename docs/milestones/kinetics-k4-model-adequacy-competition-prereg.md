# K4 — Model adequacy and model competition preregistration

Status: **FROZEN BEFORE K4 IMPLEMENTATION**

Milestone ID: `K4`

Starting stable baseline: K3.1 PASS/FROZEN with `main == dev` at `f5a932c03a35cb45e661d03d725ea96aecb2f974` before this preregistration commit.

K3.1 preregistration: `bfb2439fdea769779ea0aaec747353708146add6`.
K3.1 scored source: `b970487773cc24ad288ad712fe7e96a2a69d59ad`.
K3 scored H1/H2 cache producer: `68fcc6a6a9ea305016119a86238aa9329ef33b9c`.
K2 scientific source: `eab5879e8c17d5c1cf8f697f0eb2e57816cc99b5`.

## Scientific question

Can the platform distinguish two different questions that must not be conflated:

1. **Adequacy:** does a model's posterior predictive distribution behave consistently with held-out observations for this declared study?
2. **Competition:** when two scientifically declared model families are fitted to the same evidence and evaluated on the same unseen conditions, which receives stronger out-of-sample predictive support?

K4 does not turn a winning model into truth. It produces study-bounded evidence about predictive adequacy and relative predictive support.

## Frozen models

### M1 — Arrhenius non-isothermal CSTR

Existing model reference:

- `kinetics.cstr.nonisothermal_first_order`
- version `0.1.0`

Inference is the frozen K2 posterior over `log_k0` and `e_over_r_k`, with K3.1 predictive-admission conditioning retained exactly.

### M2 — constant-rate first-order CSTR approximation

A separately versioned Kinetics model will be declared before scoring:

- model id: `kinetics.cstr.nonisothermal_first_order_constant_rate`
- version: `0.1.0`
- model type: `APPROXIMATION`

It retains the same well-mixed species balance, energy balance, heat of reaction, jacket heat transfer and physical assumptions, but replaces Arrhenius temperature dependence by a single temperature-independent first-order rate constant `k_const`.

The competitor is scientifically meaningful as a restricted approximation; it is not labelled physically validated.

Frozen competitor inference coordinate:

- parameter: `log_k_const`
- prior/grid bounds: `ln(1e-5 s^-1)` to `ln(1 s^-1)`
- uniform grid: 121 points

The implementation may reuse the already verified CSTR numerical machinery by setting activation energy to exactly zero, but provenance/model binding must identify M2 explicitly rather than pretending it is M1.

## Frozen evidence split

Both models are fitted only to the same K2 training conditions C1/C2/C3 and the same K2 observation noise model.

Both are evaluated only on the frozen K3 holdouts H1/H2:

- H1: coolant 307.5 K, feed 360 K, initial 315 K, initial concentration 1000 mol/m^3, horizon 1800 s
- H2: coolant 292.5 K, feed 340 K, initial 305 K, initial concentration 1000 mol/m^3, horizon 1800 s

Holdout values are not used to fit either model.

Primary and repeated seeds remain exactly those frozen by K2/K3:

- primary inference seed `20260809`
- repeated inference seeds `20260810..20260829`
- primary holdout seed `20260909`
- repeated holdout seeds `20260910..20260929`

## Predictive adequacy statistics

For one noisy held-out observation `y` and one finite posterior-predictive Gaussian mixture:

- predictive CDF / PIT value: `F(y)`;
- two-sided predictive tail probability: `2 * min(F(y), 1-F(y))`;
- exact log predictive density: `log p(y)` computed by log-sum-exp over the finite mixture;
- standardized predictive residual: `(y - predictive_mean) / total_predictive_std`;
- central 95% predictive interval coverage.

No Gaussian approximation may replace the finite-mixture CDF or density in the scored path.

## Study-bounded adequacy semantics

K4 may classify a model for this study as:

- `ADEQUATE_FOR_DECLARED_STUDY`
- `INADEQUATE_FOR_DECLARED_STUDY`
- `INCONCLUSIVE`

These are not global `ModelValidationStatus` upgrades. Synthetic K4 evidence must not mark either model `EXPERIMENTALLY_VALIDATED`.

## Model competition statistic

For each paired holdout dataset, compute each model's sum of exact log predictive densities across H1/H2 and both observables.

Define paired score difference:

`delta = log_score(M1) - log_score(M2)`.

Positive delta favors Arrhenius M1; negative delta favors constant-rate M2. This is out-of-sample predictive evidence, not a Bayes factor and not a truth probability.

No post-hoc complexity penalty is added: both models are scored on unseen data, and the score itself evaluates predictive sharpness/calibration.

## Admission and provenance

All forward values for both models must cross the existing K1.5 CSTR numerical-admissibility boundary.

Every posterior used for prediction must also pass the K3.1 explicit predictive-admission mass policy with maximum unsupported mass `1e-12`.

No rejected point may be fabricated, interpolated or silently promoted.

K4 outputs must bind:

- exact `TwinReference`;
- exact `ModelReference`;
- posterior dataset id;
- observation source ref;
- predictive-support conditioning audit;
- adequacy method/version;
- source/prereg commits.

## Scientific Twin

K4 will use an `ENSEMBLE` Scientific Twin containing both M1 and M2 references. `ENSEMBLE` here records competing executable representations of the same declared system; it does not imply model averaging.

## Acceptance criteria

### A1 — shared adequacy math

Unit/property tests establish deterministic exact finite-mixture CDF/log-density calculations, unit compatibility, ordered 95% coverage logic, and fail-closed behavior for missing observation noise or support mismatch.

### A2 — competitor is explicit and versioned

M2 has its own `ScientificModelDefinition`, model id/version, approximation status, assumptions and validity declaration. Scored M2 evidence must never carry the M1 model reference.

### A3 — fit/predict separation

Neither H1 nor H2 observation may enter either model's posterior fit. Training and holdout dataset ids/refs remain distinct and auditable.

### A4 — numerical admission

Truth/model forward evaluations needed by scoring cross K1.5. Predictive posterior mass conditioning obeys the frozen K3.1 `1e-12` budget separately for every posterior used.

### A5 — Arrhenius repeated predictive adequacy

Across the 20 repeated paired datasets, M1 central 95% predictive coverage is at least `15/20` for each of the four H1/H2 observable keys.

### A6 — Arrhenius standardized residual behavior

For each of the four observable keys across the 20 repeated datasets, the RMS standardized predictive residual for M1 is finite and no greater than `1.75`.

### A7 — primary comparison is finite

Primary M1 and M2 exact holdout log predictive scores are finite and their difference is reported without converting it to a probability of truth.

### A8 — repeated competition

Across the 20 repeated paired holdout datasets:

- M1 aggregate log predictive score exceeds M2 in at least `14/20` pairs; and
- the sum of paired deltas over all 20 datasets is strictly positive.

### A9 — model-specific evidence is not conflated

Adequacy records, score records, support-conditioning audits and model references remain model-specific. No result may inherit evidence from the competing model merely because both belong to the same Twin.

### A10 — deterministic replay

Canonical primary adequacy and competition outputs replay exactly from the same frozen inputs/caches/source.

### A11 — claim boundary

No K4 result changes either model's global validation status to experimentally validated, and no winner is labelled true, proven, physically validated or universally superior.

### A12 — regression safety

Full repository regression remains green. Frozen K1, K1.5, K2, Twin V0.1, K3, and K3.1 records are not rewritten.

## Explicitly out of scope

K4 does not implement:

- physical reactor validation;
- model averaging or Bayesian model probabilities;
- automatic model discovery;
- structural equation discovery;
- online sensor state estimation;
- autonomous experiment design;
- global certification of either model family.

## Failure rule

If any frozen criterion fails, record the failure. Do not change the competitor prior, grid, holdouts, seeds, thresholds, admission budget or scoring rule post hoc to obtain a pass.
