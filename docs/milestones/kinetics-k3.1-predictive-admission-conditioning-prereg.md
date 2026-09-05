# K3.1 — Explicit predictive-admission conditioning preregistration

Status: **FROZEN BEFORE K3.1 IMPLEMENTATION**

Milestone ID: `K3.1`

Parent scientific milestone: K3 preregistration `c640af0f9a436b9efb5828b7e4d0caba07d67882`.

Recorded K3 support-boundary failure: `docs/kinetics-k3-support-boundary-failure.md`.

K3 scored predictive-grid producer source: `68fcc6a6a9ea305016119a86238aa9329ef33b9c`.

## Why K3.1 exists

K3 discovered that a posterior point can be admissible at the fitting conditions and fail numerical admission at a new predictive condition.

The original K3 contract correctly failed closed because it prohibited silently deleting non-zero posterior mass. K3.1 does not rewrite that outcome. It introduces a new, explicit and auditable methodology for posterior prediction **conditional on predictive admission** when unsupported posterior mass is demonstrably negligible under a preregistered budget.

## Frozen scientific inputs

K3.1 keeps all K3 scientific declarations unchanged:

- frozen K2 61x61 posterior support and observation model;
- K2 C1/C2/C3 fitting conditions;
- H1/H2 predictive holdout conditions;
- all K2/K3 seeds;
- concentration and temperature observation noise;
- 95% credible mass;
- K1.5 scientific admission boundary;
- CSTR model identity and Twin binding.

K3.1 must not alter H1/H2, solver convergence thresholds, K2 posterior science, or Twin V0.1 semantics.

## Cache reuse

The scored H1/H2 predictive grid already required 928.40 s and was produced by K3 source `68fcc6a6a9ea305016119a86238aa9329ef33b9c` under the frozen K3 preregistration.

K3.1 is allowed to reuse that exact cache only after verifying:

- cache schema;
- producer commit exactly `68fcc6a6a9ea305016119a86238aa9329ef33b9c`;
- K3 preregistration commit;
- K2 scientific-source commit;
- parameter names/support points;
- H1/H2 observation keys and condition IDs;
- admission mask and recorded rejection reasons.

The successor runner must not relabel the cache as newly produced by K3.1.

## Predictive-admission event

For a posterior with normalized weights `w_i` and predictive admission mask `a_i`, define:

`M_supported = sum_i w_i * 1[a_i]`

`M_unsupported = 1 - M_supported`

computed by direct summation of unsupported stored weights for audit stability.

K3.1 introduces a frozen maximum unsupported-mass budget:

`MAX_UNSUPPORTED_POSTERIOR_MASS = 1e-12`

This threshold is tied to the repository's existing strict posterior-normalization scale used in K2, not to a claim that unsupported mass is scientifically zero.

## Policy

For every posterior used for predictive UQ:

1. Compute and record exact stored unsupported posterior mass.
2. If unsupported mass is greater than `1e-12`, **FAIL CLOSED**. No predictive UQ is produced for that posterior.
3. If unsupported mass is in `[0, 1e-12]`, explicitly condition on predictive admission:

   `w_i' = w_i / M_supported` for admitted predictive points, and zero otherwise.

4. The resulting UQ is labelled `conditional_on_predictive_admission = true` whenever unsupported mass is non-zero.
5. Report:
   - original posterior dataset ID;
   - supported mass;
   - unsupported mass;
   - conditioning factor `1 / M_supported`;
   - unsupported point count;
   - unsupported point indices;
   - recorded rejection reasons;
   - Twin/model/source bindings.
6. No rejected forward value is fabricated, interpolated, substituted, or marked admissible.
7. No K1.5 numerical threshold is weakened.

This is explicit probability conditioning, not silent truncation.

## Scope of the budget check

The mass budget must pass separately for every posterior actually used by K3.1:

- primary multi-condition posterior;
- primary weak-C2 posterior used for U7 comparison;
- all 20 repeated multi-condition posteriors used for latent/noisy coverage.

A single posterior exceeding the budget fails the corresponding acceptance criterion and the milestone.

## UQ semantics

After explicit conditioning, K3's frozen UQ definitions remain unchanged:

- epistemic distribution: weighted discrete admitted predictive means;
- total predictive distribution: finite Gaussian mixture using the frozen observation sigma;
- exact variance decomposition;
- deterministic mixture quantiles;
- no model-discrepancy term (K4 remains responsible for model-form adequacy).

## Acceptance criteria

### S1 — support accounting is exact and explicit

For every posterior used, stored supported + unsupported mass must equal one within `1e-12`, and the output must contain the full support-conditioning audit record.

### S2 — unsupported mass budget

Every posterior used by K3.1 must satisfy:

`unsupported_mass <= 1e-12`.

No post hoc larger budget is allowed.

### S3 — fail-closed regression

A controlled test posterior with unsupported mass greater than `1e-12` must be rejected, and a posterior with zero unsupported mass must pass without changing its weights.

### S4 — K3 U1/U2/U3 preserved

- H1/H2 truth predictions are admitted;
- all four primary predictive outputs are finite and quantified;
- variance decomposition satisfies the frozen K3 tolerance.

### S5 — primary latent truth coverage

The frozen K3 U4 criterion must pass after explicit predictive-admission conditioning.

### S6 — repeated latent coverage

The frozen K3 U5 criterion must pass: at least 15/20 for each H1/H2 observable.

### S7 — repeated noisy predictive coverage

The frozen K3 U6 criterion must pass: at least 15/20 for each H1/H2 observable.

### S8 — information gain survives propagation

The frozen K3 U7 criterion remains unchanged: multi-condition epistemic predictive standard uncertainty <= 0.80 times weak-C2 for all four holdout observables.

### S9 — deterministic replay

Canonical results, including support-conditioning audit fields, must reproduce exactly from the same frozen K2 and K3 cache artifacts.

### S10 — Twin/evidence binding

All primary outputs retain the exact TwinReference, CSTR ModelReference, posterior dataset ID, UQ method, scientific source refs, and support-conditioning record.

### S11 — regression safety

Full repository regression remains green. Frozen K1, K1.5, K2, Twin V0.1, K3 preregistration, and K3 failure record are not rewritten.

## Explicitly out of scope

K3.1 does not:

- call an inadmissible point scientifically valid;
- weaken numerical convergence gates;
- invent predictions for rejected points;
- add model discrepancy;
- establish model adequacy;
- change H1/H2 or any frozen seed/threshold/noise declaration;
- claim that `1e-12` unsupported mass is physically zero;
- generalize this budget to every future domain without a domain/study admission policy.

## Failure rule

If the unsupported-mass budget or any frozen K3 scientific criterion fails, record the failure. Do not enlarge the budget, alter holdouts, or change coverage thresholds post hoc.
