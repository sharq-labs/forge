# Electrical V0.1 — end-to-end demonstration

Base commit `4ac821b8b3fbbc06fb784d9d66a7e12a5fe391cc` · config hash `03d37581be252fd7d34474f90a0fc4b3c2b12a8aa02b2e5300f2bb8c0c2766c1` · scenario hash `6f0d1ebcd9fabe0424b67e37653d85224cc7f7bf0a7b97157ef272515166732f`

## What was asked

In a two-resistor divider with a known 1000 ohm upper resistor, is the unknown lower resistance above 1200 ohm — and may that answer be certified for the declared operating range?

The campaign is allowed to assume the resistance is a single constant. That assumption is the thing on trial: it may not be certified until it has been tested at operating conditions the parameter measurement never visited.

## What was assumed, and what was uncertain

- **Model** — one constant unknown resistance `R2`, forward-mapped by the real `ElectricalDCSolver`. The decision path never uses a formula.
- **Uncertain** — `R2` on a 401-point grid from 500 to 2500 ohm, uniform prior (sd 578.792 ohm).
- **Decision** — A iff `R2` > 1200 ohm, with asymmetric loss 4 : 1, so indifference sits at P(above) = 0.8.
- **Instruments** — one precise parameter measurement at 10 V (sigma 0.01 V, cost 0.10) and five validation probes at 16–28 V (sigma 0.05 V, cost 0.15 each).
- **Certification requirement** — `certification:constant_r:operating_range`, requiring exactly 3 of those probes: `validate_vmid_16V`, `validate_vmid_22V`, `validate_vmid_28V`. Two probes exist and are never required, which is what makes it finite.

## World A — model adequate

Hidden truth: `A_well_specified` — inside the assumed family: **True**. The decision path is not told either way.

### What it measured, and why

| iter | action | family | reason | parameter EVSI | cost | net |
|---|---|---|---|---|---|---|
| 1 | `measure_vmid_10V_precise` | characterize | `POSITIVE_NET_VALUE` | 6.435e-01 | 0.1 | +0.5435 |
| 2 | `validate_vmid_16V` | validate | `CERTIFICATION_REQUIREMENT` | 4.090e-283 | 0.15 | -0.1500 |
| 3 | `validate_vmid_22V` | validate | `CERTIFICATION_REQUIREMENT` | 6.580e-306 | 0.15 | -0.1500 |
| 4 | `validate_vmid_28V` | validate | `CERTIFICATION_REQUIREMENT` | 0.000e+00 | 0.15 | -0.1500 |

Iteration 1 bought parameter learning because it was worth its price. From iteration 2 on, **every** action scored net-negative — including the probes that were then executed anyway, for a stated constraint reason.

### What changed in the posterior

| | mean [ohm] | sd [ohm] | P(above) | EVPI | decision |
|---|---|---|---|---|---|
| prior | 1500 | 578.792 | 0.648379 | 6.484e-01 | B |
| final | 1387.26 | 4.49209 | 1.00000000 | 0.000e+00 | A |

### Did the model survive its own predictions?

| condition | Vs [V] | predicted [V] | observed [V] | z | two-sided tail | level |
|---|---|---|---|---|---|---|
| `validate_vmid_16V` | 16 | 9.30448 ± 0.05250 | 9.24310 | -1.169 | 2.423e-01 | consistent |
| `validate_vmid_22V` | 22 | 12.79367 ± 0.05463 | 12.79830 | +0.085 | 9.325e-01 | consistent |
| `validate_vmid_28V` | 28 | 16.28285 ± 0.05731 | 16.25375 | -0.508 | 6.117e-01 | consistent |

Joint log score -5.208 against a simulated null of -4.497 ± 1.218 → p_joint = 6.656e-01; 0 of 3 conditions individually extreme.

### Result

```
POSTERIOR_DECISION        = A
PARAMETER_EVPI            = 0.000e+00
PARAMETER_EVSI (best)     = 0.000e+00
CERTIFICATION_REQUIREMENT = SATISFIED
MODEL_ADEQUACY            = ACCEPTABLE_FOR_DECLARED_SCOPE
STOP                      = STOP_APPROVED
SCIENTIFIC_CERTIFICATION  = ELIGIBLE
reason                    = ADEQUACY_ACCEPTABLE_FOR_DECLARED_SCOPE
disposition               = CERTIFICATION_ELIGIBLE
```

The decision is reported as what it is: the decision preferred by p(R2 | data, constant-R model); a statement conditional on the family, not about the world.

## World B — model inadequate

Hidden truth: `C_systematic_misspecification` — inside the assumed family: **False**. The decision path is not told either way.

### What it measured, and why

| iter | action | family | reason | parameter EVSI | cost | net |
|---|---|---|---|---|---|---|
| 1 | `measure_vmid_10V_precise` | characterize | `POSITIVE_NET_VALUE` | 6.435e-01 | 0.1 | +0.5435 |
| 2 | `validate_vmid_16V` | validate | `CERTIFICATION_REQUIREMENT` | 4.090e-283 | 0.15 | -0.1500 |
| 3 | `validate_vmid_22V` | validate | `CERTIFICATION_REQUIREMENT` | 0.000e+00 | 0.15 | -0.1500 |
| 4 | `validate_vmid_28V` | validate | `CERTIFICATION_REQUIREMENT` | 0.000e+00 | 0.15 | -0.1500 |

Iteration 1 bought parameter learning because it was worth its price. From iteration 2 on, **every** action scored net-negative — including the probes that were then executed anyway, for a stated constraint reason.

### What changed in the posterior

| | mean [ohm] | sd [ohm] | P(above) | EVPI | decision |
|---|---|---|---|---|---|
| prior | 1500 | 578.792 | 0.648379 | 6.484e-01 | B |
| final | 1430.19 | 4.65508 | 1.00000000 | 0.000e+00 | A |

### Did the model survive its own predictions?

| condition | Vs [V] | predicted [V] | observed [V] | z | two-sided tail | level |
|---|---|---|---|---|---|---|
| `validate_vmid_16V` | 16 | 9.30448 ± 0.05250 | 9.44618 | +2.699 | 6.955e-03 | moderate |
| `validate_vmid_22V` | 22 | 12.79367 ± 0.05463 | 13.22462 | +7.889 | 3.040e-15 | extreme |
| `validate_vmid_28V` | 28 | 16.28285 ± 0.05731 | 16.86617 | +10.179 | 2.460e-24 | extreme |

Joint log score 64.079 against a simulated null of -4.497 ± 1.218 → p_joint = 5.000e-05; 2 of 3 conditions individually extreme.

### Result

```
POSTERIOR_DECISION        = A
PARAMETER_EVPI            = 0.000e+00
PARAMETER_EVSI (best)     = 0.000e+00
CERTIFICATION_REQUIREMENT = SATISFIED
MODEL_ADEQUACY            = MODEL_SPACE_INADEQUATE
STOP                      = STOP_REJECTED
SCIENTIFIC_CERTIFICATION  = NOT_CERTIFIABLE
reason                    = MODEL_SPACE_INADEQUATE
disposition               = MODEL_REVISION_REQUIRED
```

The decision is reported as what it is: the decision preferred by p(R2 | data, constant-R model); a statement conditional on the family, not about the world.

## Why STOP was approved in one world and rejected in the other

Both runs pause economically with `no_action_worth_buying`. That is a statement about prices. What decides is the registered stopping criterion, evaluated into an assessment and handed to the **Arbiter**:

| world | requirement | adequacy | Arbiter | stop review |
|---|---|---|---|---|
| A | satisfied | acceptable_for_declared_scope | `valid` | **stop_approved** |
| B | satisfied | model_space_inadequate | `invalid` | **stop_rejected** |

`STOP_APPROVED` is structurally unmintable without a genuine Arbiter decision, and neither review is a certificate of scientific completeness — approving a stop means one declared criterion was found satisfied.

## The five distinctions this demo exists to show

- **EXECUTION VALIDITY != MODEL ADEQUACY** — in World B every routed probe was computationally VALID and ADMITTED (4 admitted, 0 rejected) while the model was refused.
- **PARAMETER POSTERIOR CONFIDENCE != MODEL ADEQUACY** — World B ends at sd = 4.6551 ohm and P(decision) = 1.00000000, and is still not certifiable.
- **PARAMETER EVSI ~ 0 != ALL SCIENTIFIC EVIDENCE COMPLETE** — after iteration 1 every action scored net-negative, yet three required probes remained outstanding and were then executed.
- **CERTIFICATION REQUIREMENT SATISFIED != MODEL PASSED** — both worlds end with requirement satisfied, and adequacy acceptable_for_declared_scope versus model_space_inadequate.
- **ECONOMIC NO-ACTION != SCIENTIFIC STOP APPROVED** — both runs pause with no_action_worth_buying; the stop review returns stop_approved in World A and stop_rejected in World B.

## CampaignRunner routing proof

The routing is done by the frozen `CampaignRunner`, not by any experiment-local adapter. Trace for each required probe:

| world | action | ACTION_SELECTED seq | reason | prediction_ref | EXECUTION_STARTED seq | admitted |
|---|---|---|---|---|---|---|
| A | `validate_vmid_16V` | 16 | `CERTIFICATION_REQUIREMENT` | `e98568b48a86…` | 17 | True |
| A | `validate_vmid_22V` | 28 | `CERTIFICATION_REQUIREMENT` | `c5a4583acdf0…` | 29 | True |
| A | `validate_vmid_28V` | 40 | `CERTIFICATION_REQUIREMENT` | `57d14eb83dac…` | 41 | True |
| B | `validate_vmid_16V` | 16 | `CERTIFICATION_REQUIREMENT` | `2d2ac8da34c7…` | 17 | True |
| B | `validate_vmid_22V` | 28 | `CERTIFICATION_REQUIREMENT` | `66624649c8c5…` | 29 | True |
| B | `validate_vmid_28V` | 40 | `CERTIFICATION_REQUIREMENT` | `e12e616b638e…` | 41 | True |

## EVSI integrity

The same campaign was run with and without the certification requirement declared. Across 12 shared score points the `(parameter EVSI, cost, net value)` triples are **identical: True**. Without the requirement the runner executed `['measure_vmid_10V_precise']` and the review returned `stop_not_assessed`.

| certification action | parameter EVSI | cost | net value | execution reason |
|---|---|---|---|---|
| `validate_vmid_16V` | 4.090e-283 | 0.15 | -0.1500 | `CERTIFICATION_REQUIREMENT` |
| `validate_vmid_22V` | 4.090e-283 | 0.15 | -0.1500 | `CERTIFICATION_REQUIREMENT` |
| `validate_vmid_28V` | 4.090e-283 | 0.15 | -0.1500 | `CERTIFICATION_REQUIREMENT` |

the certification requirement changed no parameter-learning score. The routed actions keep the negative net value the engine gave them, and are executed for a stated constraint reason.

## Belief and admission

| world | executions | evidence created | admitted | rejected | belief size | chain verified |
|---|---|---|---|---|---|---|
| A | 4 | 4 | 4 | 0 | 4 | True |
| B | 4 | 4 | 4 | 0 | 4 | True |

After each world, one deliberately faulty execution was pushed through the same admission chain:

| world | critic | Arbiter | admitted | belief before → after | posterior unchanged |
|---|---|---|---|---|---|
| A | `fail` | `invalid` | False | 4 → 4 | True |
| B | `fail` | `invalid` | False | 4 → 4 | True |

## Budget

| world | total | reserved for validation | parameter spend | validation spend | remaining |
|---|---|---|---|---|---|
| A | 1.2 | 0.45 | 0.1 | 0.45 | 0.65 |
| B | 1.2 | 0.45 | 0.1 | 0.45 | 0.65 |

The frozen `BudgetLedger` does the accounting. Validation spend is drawn from the reservation because the probes are declared VALIDATE; no demo-only budget logic exists.

## What remains unproven

**prediction_ref.** V0.1 production verifies exactly one thing about a required validation action: that a non-empty prediction_ref was recorded in the tamper-evident event log before the action executed. It does NOT verify in production that the reference names a real predictive distribution, that the prediction is bound to the correct evidence snapshot, that it was sealed against later modification, or that its content hash checks out. E2 demonstrated all four of those properties experiment-side, and this demo uses E2's sealed ledger to create the predictions — so the stronger properties hold here in fact, but they are NOT what production enforces. A campaign supplying a meaningless reference would satisfy the V0.1 contract and would have tested nothing.

This is a computational benchmark on a synthetic divider. Nothing here is validated against any physical electrical system, no hardware is involved, and the misspecification in World B is a declared synthetic construct rather than a claim about how any real component behaves.

Result digest: `d349e3f8543353d5b7ff0ba85e16cd6fb66581376455de87fc2d12dbe75e4024`

**ELECTRICAL V0.1 DEMO VERIFIED**