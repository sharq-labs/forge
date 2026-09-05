# K3.1 — Explicit predictive-admission conditioning freeze record

Status: **PASS / FROZEN**

Milestone ID: `K3.1`

Frozen preregistration commit: `bfb2439fdea769779ea0aaec747353708146add6`

Scored implementation head: `b970487773cc24ad288ad712fe7e96a2a69d59ad`

Parent K3 preregistration: `c640af0f9a436b9efb5828b7e4d0caba07d67882`

K3 scored predictive-grid producer: `68fcc6a6a9ea305016119a86238aa9329ef33b9c`

Frozen K2 scientific source: `eab5879e8c17d5c1cf8f697f0eb2e57816cc99b5`

## Decision

K3.1 satisfies its preregistered scientific acceptance criteria and the full repository regression gate. It is accepted as the first reusable explicit predictive-admission conditioning method for quantified posterior-predictive uncertainty.

The original K3 support-boundary failure remains historical evidence and is not rewritten. K3.1 is a successor methodology, not a retroactive reinterpretation of K3.

## Scientific behavior frozen

For a posterior bound to a predictive forward table:

1. measure posterior mass on predictive-rejected support;
2. fail closed if unsupported mass exceeds the preregistered budget `1e-12`;
3. otherwise condition explicitly on predictive admission;
4. preserve and report the exact unsupported mass, supported mass, conditioning factor, rejected support identities and recorded reasons;
5. never fabricate predictions for rejected support;
6. never weaken K1.5 numerical-admissibility thresholds;
7. label non-zero support conditioning explicitly rather than treating unsupported mass as mathematically zero.

## Scored K3.1 evidence

Scored source:

```text
b970487773cc24ad288ad712fe7e96a2a69d59ad
```

K3 predictive cache verified:

```text
3,699 / 3,721 predictive points admitted
```

Primary unsupported posterior mass:

```text
2.5757981943588344e-224
```

Weak-C2 unsupported posterior mass:

```text
4.1546995154574106e-59
```

Frozen maximum unsupported posterior mass:

```text
1.0e-12
```

All 20 repeated multi-condition posteriors also remained below the frozen mass budget. Observed repeated unsupported masses ranged from approximately `2.676e-255` to `1.732e-196`.

## Scientific acceptance

| Criterion | Result |
|---|---|
| S1 — support accounting explicit | **PASS** |
| S2 — unsupported posterior mass budget | **PASS** |
| S3 — controlled fail-closed regression | **PASS** |
| S4 — K3 U1/U2/U3 preserved | **PASS** |
| S5 — primary latent truth coverage | **PASS** |
| S6 — repeated latent coverage | **PASS** |
| S7 — repeated noisy predictive coverage | **PASS** |
| S8 — information gain survives propagation | **PASS** |
| S9 — deterministic replay | **PASS** |
| S10 — Twin/evidence binding | **PASS** |
| S11 — full repository regression safety | **PASS** |

Scored runner status before the regression gate:

```text
SCIENCE_PASS_S11_PENDING
```

## Targeted implementation gate

After the floating-point accounting portability fix, the targeted K3.1/K3 suites passed:

```text
16 passed in 4.27s
```

The fix did not enlarge the unsupported-mass budget or change scientific outputs. It only prevented a last-bit floating-point sum such as `supported_mass = 1.0000000000000002` from causing a false audit failure when the measured conditioning factor rounded slightly below one. The measured value remains recorded rather than clamped.

## Full regression evidence

Windows / Python 3.14:

```text
1316 passed, 4 warnings in 164.34s (0:02:44)
```

The four warnings are the pre-existing scikit-learn Gaussian-process convergence warnings emitted by `tests/test_smoke.py`. There were no failures or errors.

## Architecture now established

```text
Scientific Twin
    +
Admissible posterior
    +
Predictive-condition admission mask
        |
        v
Explicit support accounting
        |
        +-- unsupported mass > budget -> FAIL CLOSED
        |
        +-- unsupported mass <= budget
                |
                v
      conditional posterior on predictive admission
                |
                v
      posterior-predictive UQ
                |
                +-- epistemic uncertainty
                +-- declared observation noise
                +-- total predictive uncertainty
```

This makes predictive-domain loss a first-class evidence event instead of silently renormalizing or pretending an inadmissible forward solve is valid.

## Claim boundary

K3.1 establishes quantified parameter/posterior predictive uncertainty with explicit predictive-support accounting for this scored CSTR study.

It does **not** establish:

- model-form adequacy;
- model discrepancy;
- model competition;
- empirical or physical reactor validation;
- arbitrary posterior backends;
- autonomous experiment design;
- a new Scientific Twin schema.

Those remain future milestones. K4 is responsible for model adequacy / competition.

## Freeze rule

The K3.1 preregistration, K3 failure record, scored source identity and this freeze record remain historical evidence. Any future change to support-loss budgeting, conditioning semantics, UQ meaning, predictive admission policy, or model-form treatment must use a new explicitly preregistered successor rather than silently editing this milestone.
