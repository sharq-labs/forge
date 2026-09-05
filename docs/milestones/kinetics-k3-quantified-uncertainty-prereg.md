# K3 — Quantified posterior-predictive uncertainty preregistration

Status: **FROZEN BEFORE K3 IMPLEMENTATION**

Milestone ID: `K3`

Starting stable baseline: Scientific Twin V0.1 PASS/FROZEN with `main == dev` at `16d2cba5e5b00c78a1a2137f282ea1f069b6518c` before this preregistration commit.

K2 scientific source: `eab5879e8c17d5c1cf8f697f0eb2e57816cc99b5`.
K2 preregistration: `824a4167a7ebead813dc3b023b9ace31742e3789`.
K2 final stable baseline before Twin work: `5dceeb4e3ad1437c5c01aa993ac85942989c7c88`.

## Scientific question

Given the frozen K2 posterior over the correlated Arrhenius parameters `log_k0` and `e_over_r_k`, can the platform produce reproducible, unit-bearing, scientifically admitted posterior-predictive uncertainty for CSTR observables at conditions that were **not used to fit the posterior**, while separating parameter/epistemic uncertainty from declared observation noise?

K3 is about quantified uncertainty, not model adequacy. K4 will ask whether the model family itself is adequate.

## Architectural boundary

K3 is a shared UQ capability pulled by one scored Kinetics study.

```text
ScientificTwin (system identity / typed state)
        +
Admissible K2 posterior
        +
Admitted holdout forward predictions
        |
        v
Posterior-predictive UQ
        |
        +-- epistemic / parameter uncertainty
        +-- declared observation noise
        +-- total predictive uncertainty
        |
        v
Unit-bearing quantified prediction + evidence refs
```

The LLM does not generate any numerical uncertainty value.

## Frozen twin binding

The scored K3 study will construct a Kinetics `REFERENCE` or `CALIBRATED` Scientific Twin using the already frozen Twin V0.1 contract and the versioned CSTR model reference `kinetics.cstr.nonisothermal_first_order` / `0.1.0`.

K3 may bind UQ outputs to a `TwinReference`; it must **not** rewrite Twin V0.1 to smuggle distributions into the frozen declaration contract.

## Inference source

K3 reuses the frozen K2 `61 x 61` posterior support and K2 observation model.

Training conditions remain exactly K2 C1/C2/C3. Their values, prior, truth and noise declarations are not changed.

Primary K2 inference seed remains `20260809`.
Repeated inference seeds remain `20260810..20260829` (20 datasets).

## Frozen predictive holdout conditions

Neither holdout is used in posterior fitting.

### H1 — between C2 and C3

- coolant temperature: `307.5 K`
- feed temperature: `360.0 K`
- initial temperature: `315.0 K`
- initial concentration: `1000 mol/m^3`
- horizon: `1800 s`

### H2 — between C1 and C2

- coolant temperature: `292.5 K`
- feed temperature: `340.0 K`
- initial temperature: `305.0 K`
- initial concentration: `1000 mol/m^3`
- horizon: `1800 s`

All other reactor/chemistry/numerical declarations are inherited from the frozen K1/K2 configuration.

Observables for both holdouts:

- final concentration `C_A_final`
- final temperature `T_final`

Observation noise remains exactly the K2 declaration:

- concentration sigma: `2 mol/m^3`
- temperature sigma: `0.20 K`

Primary holdout observation seed: `20260909`.
Repeated holdout observation seeds: `20260910..20260929`, paired in order with K2 repeated inference seeds `20260810..20260829`.

## UQ definitions

For one holdout observable, let posterior support have weights `w_i` and admitted model predictions `mu_i`.

### Epistemic / parameter predictive uncertainty

The latent predictive distribution is the weighted discrete distribution over `mu_i`.

Reported quantities:

- posterior-predictive mean;
- weighted standard deviation;
- central 95% weighted interval.

### Total predictive uncertainty

With declared independent Gaussian observation noise `sigma_obs`, total predictive uncertainty is the finite Gaussian mixture

`sum_i w_i Normal(mu_i, sigma_obs^2)`.

Reported quantities:

- same predictive mean;
- standard deviation satisfying `Var_total = Var_epistemic + sigma_obs^2`;
- central 95% interval computed from the mixture CDF, not by pretending the mixture is Gaussian.

No model-discrepancy term is invented in K3. Model-form uncertainty belongs to K4.

## Admission rule

A holdout forward value may enter K3 UQ only if it came through the same K1.5 domain inference-admissibility boundary used by K2.

K3 UQ must not accept bare solver arrays or unverified `ScientificResult` values as scientific predictive support.

A posterior and predictive forward table must be bound to the same parameter support. Point mismatch is a hard error.

## Determinism

Given identical posterior weights, admitted predictive support, units, observation sigma and credible mass, K3 summaries must serialize deterministically.

Mixture quantiles use a deterministic numerical root/bisection procedure with a fixed tolerance declared in implementation and pinned by tests. No Monte Carlo sampling is allowed in the scored predictive quantile path.

## Acceptance criteria

### U1 — truth holdout admissibility

Truth evaluations for H1 and H2 must pass the frozen K1.5 inference-admissibility boundary for both observables.

### U2 — finite quantified outputs

For all four primary holdout observables:

- predictive mean is finite;
- epistemic and total standard uncertainties are finite and non-negative;
- central 95% interval bounds are finite and ordered;
- no scored output remains `UNKNOWN` uncertainty.

### U3 — exact variance decomposition

For each primary holdout observable:

`abs(var_total - (var_epistemic + sigma_obs^2)) <= 1e-12 * max(1, var_total)`

in the observable's declared numeric unit.

### U4 — primary latent truth coverage

For the primary K2 posterior, the exact truth-model mean at H1 and H2 must lie inside the central 95% **epistemic** interval for all four observable/condition pairs.

### U5 — repeated latent coverage

Across the 20 frozen repeated K2 inference datasets, the exact truth-model mean must lie inside the corresponding central 95% epistemic interval in at least `15 / 20` runs for **each** of the four holdout observable/condition pairs.

### U6 — repeated noisy predictive coverage

Across the 20 paired frozen holdout-noise datasets, the synthetic noisy holdout observation must lie inside the corresponding central 95% **total predictive** interval in at least `15 / 20` runs for each of the four holdout observable/condition pairs.

### U7 — information gain survives propagation

For each of the four holdout observables, epistemic predictive standard uncertainty under the K2 multi-condition posterior must be no greater than `0.80` times the epistemic predictive standard uncertainty under the weak C2-only posterior.

This is a predictive-space consequence of K2 identifiability gain, not a claim of model adequacy.

### U8 — deterministic replay

Primary K3 UQ replay from the same source-bound posterior/holdout forward artifacts must reproduce the canonical machine-readable result exactly.

### U9 — Twin-bound scientific output

Primary K3 outputs must identify the exact `TwinReference`, posterior dataset ID, predictive condition/observable, model reference, UQ method and scientific source/evidence refs. Metadata alone cannot supply any scientific input.

### U10 — regression safety

The full repository regression suite remains green. Frozen K1, K1.5, K2 and Scientific Twin V0.1 preregistration/freeze records are not rewritten.

## Explicitly out of scope

K3 does not claim or implement:

- model competition or model-form adequacy (K4);
- empirical calibration against real reactor measurements;
- physical validation;
- online sensor state estimation;
- arbitrary Bayesian backends beyond what this milestone requires;
- autonomous experiment design;
- decision analysis;
- discovery/invention;
- a new Twin schema version.

## Failure rule

If any frozen acceptance criterion fails, record the failure. Do not alter holdout conditions, seeds, thresholds, noise levels, prior, K2 data, or acceptance criteria post hoc to obtain a pass.
