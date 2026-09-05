# K2 — Multi-parameter Arrhenius inference preregistration

Status: **FROZEN BEFORE K2 IMPLEMENTATION**

Experiment ID: `K2`

Frozen starting point: K1.5 PASS/FROZEN at commit `f479777d67295355fbf3fcf7877cd834d30eee99`.

## Scientific question

Can SRIA recover two correlated Arrhenius parameters from noisy, multi-condition CSTR observations with a reproducible posterior while preserving the K1.5 inference-admissibility boundary, and can it demonstrate that a deliberately weak single-condition study is less identifiable than the multi-condition study?

K2 is the first scored Bayesian parameter-inference milestone for the Kinetics/CSTR domain. It is not an optimization milestone, not experiment design, not model competition, and not physical validation of a real reactor.

## Non-negotiable evidence boundary

Every numerical forward prediction used by the likelihood must cross the K1.5 boundary. In particular:

- no bare solver array or float mapping may enter likelihood code;
- no bare `ScientificResult` may enter likelihood code, even if `is_usable == True`;
- every numerical prediction must be domain-interpreted, provenance-bearing, physics-bound, unit-bearing, and backed by sequence-level `NUMERICALLY_CONVERGED` evidence;
- execution hardware, worker count, GPU use, batching and cache state must not change scientific meaning or posterior values beyond declared numerical parity tolerances;
- an inadmissible parameter point receives no finite likelihood contribution. It is not silently repaired, clipped into validity, or treated as a solver success.

## Parameters to infer

The unknown vector is

`theta = (log_k0, e_over_r_k)`

where:

- `log_k0 = ln(k0 / (1/s))`, natural logarithm of the SI pre-exponential factor;
- `e_over_r_k = E/R` in kelvin.

The synthetic truth is inherited exactly from the frozen K1 nominal chemistry:

- `k0 = 7.2e10 / 60 = 1.2e9 1/s`;
- `log_k0 = ln(1.2e9)`;
- `E/R = 8750 K`.

The truth is known because K2 is a recovery study. Posterior code is not allowed to read the truth except when computing post-run recovery metrics.

## Prior

Independent uniform prior in the inference coordinates:

- `log_k0 in [ln(1e8), ln(1e10)]`;
- `e_over_r_k in [7500, 10000] K`.

The prior is intentionally broad enough to preserve the Arrhenius ridge while still restricting the scored study to the model family and numerical envelope K2 is designed to evaluate.

No prior is tuned after observations are generated.

## Forward-model construction

For a parameter point `(log_k0, e_over_r_k)`:

1. construct `k0 = exp(log_k0) 1/s`;
2. construct `E = R * e_over_r_k J/mol` using the domain SI gas constant;
3. keep heat of reaction, density and heat capacity fixed at frozen K1 nominal values;
4. keep each operating condition otherwise fully declared;
5. obtain CSTR observables only through the K1.5 CSTR inference adapter.

The likelihood may consume only admitted predictions.

## Operating conditions

All three scored conditions use the frozen K1 nominal volume, flow, feed concentration and UA, BDF production numerics, 1800 s horizon, and 2001 output points. They differ only in declared thermal operating conditions and initial temperature.

### C1 — cool / low-rate condition

- coolant temperature: `285 K`
- feed temperature: `330 K`
- initial temperature: `300 K`
- initial concentration: `1000 mol/m^3`

### C2 — nominal/intermediate condition

- coolant temperature: `300 K`
- feed temperature: `350 K`
- initial temperature: `310 K`
- initial concentration: `1000 mol/m^3`

### C3 — warmer / higher-rate condition

- coolant temperature: `315 K`
- feed temperature: `370 K`
- initial temperature: `320 K`
- initial concentration: `1000 mol/m^3`

These conditions were chosen before the K2 scored run to expose the same Arrhenius pair over separated temperatures. If any condition fails the frozen scientific admissibility boundary at the truth, K2 records a preregistered-condition failure; the condition or validation threshold is not changed to manufacture a pass.

## Observables and synthetic measurements

Each condition contributes exactly two observables:

- final reactant concentration `C_A_final` in `mol/m^3`;
- final reactor temperature `T_final` in `K`.

Synthetic observations are generated from the admitted truth prediction and then perturbed with independent zero-mean Gaussian measurement noise using NumPy `PCG64` through `numpy.random.default_rng`.

Primary scored dataset seed: `20260809`.

Declared 1-sigma measurement noise:

- concentration: `sigma_C = 2.0 mol/m^3`;
- temperature: `sigma_T = 0.20 K`.

Noise is part of the observation model. It is not solver uncertainty and must not be reported as such.

## Likelihood

Conditional on a parameter point, observation errors are independent Gaussian with the declared per-observable standard deviations. Therefore the scored log likelihood is the sum of the standard Gaussian log densities over the six observations.

No hidden nuisance parameter, fitted noise scale, robust-loss switch, or post-hoc outlier rejection is allowed in K2.

A parameter point for which any required forward prediction is scientifically inadmissible receives log likelihood `-inf`.

## Reference posterior

The primary reference posterior is an exact discrete posterior on a fixed Cartesian grid:

- `61` equally spaced points in `log_k0`;
- `61` equally spaced points in `e_over_r_k`;
- `3721` parameter points total.

The prior is constant on this rectangle. Posterior normalization must use a stable log-sum-exp calculation.

This grid is the K2 reference oracle. Faster CPU/GPU execution is allowed only if it reproduces the same grid posterior within the parity rules below.

## Deliberately weak control

The weak-control posterior uses only condition C2, with the same parameter grid, prior and declared observation noise.

Frozen qualitative prediction: C2 alone leaves a stronger Arrhenius correlation/ridge and less posterior concentration than the three-condition study.

## Repeated recovery

After the forward grid has been computed once, generate `20` additional synthetic datasets from the same truth and conditions with seeds:

`20260810` through `20260829` inclusive.

The forward predictions are identical across these recovery datasets and must be reused rather than recomputed. Only observation noise and posterior scoring change.

Repeated recovery is therefore both a calibration check and a check that scientific work is not repeated when the physics declaration is identical.

## Posterior summaries

For each posterior report:

- posterior mean of both coordinates;
- posterior standard deviation of both coordinates;
- MAP grid point;
- equal-tail 95% marginal credible interval for each coordinate;
- posterior Pearson correlation between `log_k0` and `e_over_r_k`;
- 2x2 posterior covariance matrix and determinant;
- fraction of grid points scientifically admissible;
- total forward evaluations and total admitted/rejected parameter-condition evaluations.

All summaries are computed from normalized posterior weights, never generated by an LLM.

## Primary acceptance criteria

K2 passes only if all of the following are true on the frozen primary dataset and reference grid:

1. **A1 — truth-condition admissibility:** all three truth-condition forward predictions cross the K1.5 boundary.
2. **A2 — finite posterior:** at least one grid point is admissible, normalization is finite, all posterior weights are finite/non-negative, and weights sum to 1 within `1e-12` absolute error.
3. **A3 — recovery:** the truth lies inside both multi-condition 95% marginal credible intervals.
4. **A4 — point accuracy:** the multi-condition posterior mean satisfies `abs(log_k0_mean - log_k0_truth) <= 0.50` and `abs(e_over_r_mean - 8750 K) <= 250 K`.
5. **A5 — identifiability gain:** the determinant of the multi-condition posterior covariance is at most `0.50` times the weak C2-only covariance determinant.
6. **A6 — ridge reduction:** the geometric mean of the two multi-condition marginal standard deviations is at most `0.80` times that of the weak C2-only posterior.
7. **A7 — repeated recovery:** across the 20 frozen recovery seeds, each true parameter is contained in its 95% marginal interval in at least `15/20` datasets.
8. **A8 — deterministic replay:** repeating posterior scoring from an already computed forward grid and identical observations reproduces posterior weights bit-for-bit on the same NumPy path, or exactly after serialization round-trip if a stable canonical encoding is used.
9. **A9 — execution parity:** serial and parallel CPU execution produce identical admissibility masks and forward observable values within the existing CSTR sequence tolerance; posterior weights then agree to max absolute difference `<= 1e-12`.
10. **A10 — GPU parity if GPU path is enabled:** GPU posterior/likelihood scoring is accepted only if normalized weights agree with the NumPy reference to max absolute difference `<= 1e-10`. A GPU speedup is optional; scientific parity is mandatory.

If A5 or A6 fails, the result is a scientific finding about this design and noise model; do not alter the conditions, prior or threshold after observing the result.

## Performance rules

Performance is secondary to scientific correctness but is measured because K2 is computationally repetitive.

### CPU

Independent parameter-condition forward evaluations may execute through a persistent process pool. Worker count is capability/workload-derived, never selected from CPU product names.

The implementation must retain a serial path as the reference and fallback.

### GPU

The SciPy CSTR integrator is not moved to GPU merely to claim acceleration. GPU use is restricted to genuinely batched numerical work such as likelihood/posterior scoring or later surrogate operations.

Batch size must be capability/workload-driven. The previously observed best batch on one GPU is diagnostic evidence only and must not become a hard-coded scientific constant.

### Work avoidance

Forward predictions for a fixed grid/condition declaration must be computed once and reused across primary, weak-control and repeated-recovery posterior scoring. Reusing identical physics is required; repeated solver work is not scientific depth.

## Explicitly out of scope

K2 does not claim or implement:

- calibrated numerical uncertainty beyond the K1/K1.5 sequence gate — that is K3;
- model competition or model discrepancy — K4;
- physical/experimental validation or a measured real reactor;
- experiment selection / EIG / EVSI / decision optimization;
- BoTorch acquisition optimization;
- digital-twin state estimation;
- generic chemistry ontology;
- distributed cluster scheduling;
- autonomous inference/solver agents.

## Failure handling

- Solver or domain-invalid candidate: mark candidate-condition prediction inadmissible and give the full parameter point log likelihood `-inf`.
- Truth condition inadmissible: K2 fails A1; stop the scored run and report it.
- Zero finite posterior mass: K2 fails A2; stop and report it.
- CPU/GPU parity failure: reject the accelerated path; the serial NumPy reference remains authoritative.
- Performance below expectation with scientific parity intact: performance finding only, not a scientific failure.

## Freeze rule

This document is frozen before K2 implementation and before any K2 scored observation or posterior is generated. Any later change must be recorded as an explicit deviation; this file must not be silently rewritten to match observed results.
