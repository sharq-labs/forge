# T1 — Thermal parameter inference at fixed fidelity

Config hash: `2b231b00b950e43818aca18004b29ac55ebca924e4b6c1cfd06f3372917050b7`
Preregistration hash: `35ff4a22a26e5bb5af5e869a92bf52cfb3b20c07a32d46ee888cd66de8ea875f`

**Can a numerically coarse but apparently converged solver produce a posterior over alpha that is confident yet systematically biased?**

Hidden truth (grader only): α = 1.2000e-05 m²/s, exact QoI = 0.4913436406, sensitivity dα→du = -29096.2. Observations are the exact solution plus declared Gaussian noise, generated once and reused unchanged at every rung.

## Three inferences, one difference

| rung | cells×steps | work | discretization err | posterior mean | mean err | in sd | 95% CI | covers α |
|---|---|---|---|---|---|---|---|---|
| `coarse` | 8×10 | 80 | +1.6281e-02 | 1.263085e-05 | +6.308e-07 | +33.7 | [1.25950e-05, 1.26662e-05] | **NO** |
| `medium` | 64×80 | 5,120 | +1.6137e-03 | 1.208662e-05 | +8.662e-08 | +5.0 | [1.20512e-05, 1.21225e-05] | **NO** |
| `reference` | 512×640 | 327,680 | +1.9483e-04 | 1.203720e-05 | +3.720e-08 | +2.2 | [1.20025e-05, 1.20700e-05] | **NO** |

| rung | posterior sd | CI width | QoI predictive mean | QoI pred err |
|---|---|---|---|---|
| `coarse` | 1.8726e-08 | 7.1250e-08 | 0.49045824 | -8.8540e-04 |
| `medium` | 1.7373e-08 | 7.1250e-08 | 0.49045829 | -8.8535e-04 |
| `reference` | 1.7235e-08 | 6.7500e-08 | 0.49045829 | -8.8535e-04 |

## Does more fidelity remove the bias?

- bias falls monotonically with fidelity: **True**
- coarse → reference bias reduction: **17×** for **4096×** the work
- coverage recovered at the reference rung: **False**
- posterior width varies across rungs by only 1.09× — the *confidence* barely moves while the *answer* does

## Prediction recorded before execution

| rung | predicted bias (σ) | observed (σ) | coverage predicted | observed | as predicted |
|---|---|---|---|---|---|
| `coarse` | 32.6 | +33.7 | False | False | yes |
| `medium` | 3.2 | +5.0 | False | False | yes |
| `reference` | 0.4 | +2.2 | True | False | **no** |

### Where the prediction missed, and why

The pre-execution prediction was computed from discretization alone. It omitted the realized noise draw, which displaces every rung's posterior by the same amount: the four observations averaged -8.848e-04 below the exact QoI, worth +3.041e-08 in α, or +1.8 posterior standard deviations. That term is shared by all three rungs because all three saw the same observations.

| rung | discretization → α | noise → α | linear sum | observed | nonlinear residual | dominated by |
|---|---|---|---|---|---|---|
| `coarse` | +5.5956e-07 | +3.0411e-08 | +5.8997e-07 | +6.3085e-07 | +4.0877e-08 | discretization |
| `medium` | +5.5461e-08 | +3.0411e-08 | +8.5872e-08 | +8.6618e-08 | +7.4554e-10 | discretization |
| `reference` | +6.6961e-09 | +3.0411e-08 | +3.7107e-08 | +3.7201e-08 | +9.3802e-11 | noise |

So the discretization prediction held at every rung; what the prediction got wrong was assuming a noise-free draw. The reference rung missed coverage not because its numerics were inadequate but because this particular draw sat 1.8σ low — and coverage of ONE credible interval from ONE noise draw is a single Bernoulli outcome, not a calibration statement. What the decomposition shows is which term the residual error is made of, and that is a property of the rung rather than of the draw.

## Finding

on this benchmark a solver at the cheapest rung of the frozen verification ladder produced a posterior over alpha whose width is comparable to the reference rung's, and whose centre is 33.7 posterior standard deviations from the true value. Nothing in the inference is wrong: the forward map is biased, and an exact Bayesian update against a biased forward map is exactly this confident and exactly this wrong.

The complement is equally the result: at the reference rung the residual error is noise-dominated, and refining further cannot fix it. Discretization stopped being the binding constraint somewhere between the medium and reference rungs, and no amount of additional fidelity buys back the missing coverage.

## Fidelity corpus

Registered 3 rungs and 2 observed relationships — **computational cost ratios only**.

- corpus status without T1: `insufficient_real_data`, 0 models with a real ladder
- corpus status with T1: `observed`, 1 models with a real ladder

These are the first genuine low/high-fidelity rungs in the repository — the same quantity computed at three accuracies — so the M2 note that no such pairs exist no longer applies to the thermal model. No production code changed to make that true.

Not recorded: accuracy, discrepancy and sufficiency. ModelFidelityRelationship raises on DOMAIN_OWNED, and T1 does not route around that: the measured bias lives in this experiment's results, not in the calibration corpus.

## What this does not show

- no adaptive fidelity selection — nothing here chooses a rung
- no campaign, no EVPI, no EVSI, no certification, no model adequacy
- no physical validation; the hidden truth is synthetic and known
- no new inference framework beyond a grid posterior over one parameter