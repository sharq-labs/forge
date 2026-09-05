# T2 — Repeated-draw numerical calibration

Config hash: `63d8e07e0e3a5cfdedb0c8481f37916d873a35ec65ef796a99fd8a4b35dc9bd1`
Preregistration hash: `0bcdd3e92110db3bb1c6547535019e64a6272d51217cef3fec5d1348214a1d05`
Base commit (T1 freeze): `3e2ca40cfa69a591896dba45620e449c5a0651cf`

**Does numerical discretization error cause systematic posterior miscalibration and confident parameter bias across repeated observations, and at what fidelity does observation noise become the dominant error source?**

500 preregistered draws from `SeedSequence(20260908).spawn(...)`. Everything T1 froze is held fixed and imported; only the noise realization varies. Nominal credible level 95%.

## Calibration

| arm | work | coverage | Wilson 95% | predicted | band | in band |
|---|---|---|---|---|---|---|
| `coarse` | 80 | **0.000** | [0.000, 0.008] | 0.000 | [0.000, 0.020] | yes |
| `medium` | 5,120 | **0.106** | [0.082, 0.136] | 0.101 | [0.055, 0.155] | yes |
| `reference` | 327,680 | **0.952** | [0.930, 0.968] | 0.932 | [0.880, 0.980] | yes |
| `exact` | — (control) | **0.962** | [0.941, 0.976] | 0.950 | [0.920, 0.985] | yes |

## Estimation quality

| arm | mean bias | RMSE | posterior sd | sd spread | mean z | sd of z | confidently wrong |
|---|---|---|---|---|---|---|---|
| `coarse` | +5.9750e-07 | 5.9777e-07 | 1.8689e-08 | 0.0011 | +31.97 | 0.92 | 1.000 |
| `medium` | +5.5676e-08 | 5.8073e-08 | 1.7341e-08 | 0.0010 | +3.21 | 0.95 | 0.894 |
| `reference` | +6.5048e-09 | 1.7625e-08 | 1.7203e-08 | 0.0010 | +0.38 | 0.95 | 0.048 |
| `exact` | -1.9714e-10 | 1.6363e-08 | 1.7184e-08 | 0.0010 | -0.01 | 0.95 | 0.038 |

*confidently wrong* = the interval excludes α **and** is no wider than 1.5× the reference arm's median width (1.0125e-07) — wrong while looking as authoritative as a good answer.

## Error budget — where does noise take over?

| arm | discretization → α | noise RMS → α | ratio | dominated by |
|---|---|---|---|---|
| `coarse` | +5.5956e-07 | 1.6363e-08 | 34.196 | discretization |
| `medium` | +5.5461e-08 | 1.6363e-08 | 3.389 | discretization |
| `reference` | +6.6961e-09 | 1.6363e-08 | 0.409 | noise |
| `exact` | +9.2525e-14 | 1.6363e-08 | 0.000 | noise |

Observation noise first dominates at the **reference** rung.

The control arm's non-zero entry is not discretization: its forward map is the closed form. It is linear interpolation of that map at α_true, which sits between grid nodes by design. It matches the interpolation bound f''h²s(1−s)/2 to 3 parts in 10⁵, is common to every arm and so cancels between them, and is 5×10⁻⁶ of a posterior standard deviation.

## QoI prediction

| arm | mean error | RMS error |
|---|---|---|
| `coarse` | +6.1702e-06 | 4.7610e-04 |
| `medium` | +6.2147e-06 | 4.7610e-04 |
| `reference` | +6.2203e-06 | 4.7610e-04 |
| `exact` | +6.2211e-06 | 4.7610e-04 |

## Observed, not preregistered

*Noticed in the results rather than predicted before them. Reported as observations with checked mechanisms, and deliberately not counted as criteria.*

**QoI prediction error is essentially identical at every arm, including the coarse rung whose parameter estimate is ~32 posterior sd wrong.**

QoI prediction RMS varies by only 1.29e-06 across all four arms and sits at the observation-noise floor σ/√n = 5.0000e-04 (at floor: True).

Mechanism: the posterior centre is fitted so the forward map reproduces the observed mean. A forward map biased by d shifts alpha_hat by -d/(du/dalpha), which is exactly the shift that cancels d in the prediction. So the bias is absorbed, the predictive error falls back to the observation-noise floor sigma/sqrt(n) = 5.0000e-04, and every arm looks equally good at predicting what was already measured.

Consequence: predictive performance on the assimilated observable is not evidence that the parameter is right. On this benchmark the coarse rung is indistinguishable from an exact solver by that measure alone, while being wrong about alpha by 4.7%.

Scope limit: shown for the QoI that was assimilated, at one benchmark. Whether an unassimilated or out-of-range prediction would expose the bias is not tested here.

**Second observation.** posterior width barely varies across draws or arms (relative spread ~1e-3), so the width clause in the confidently-wrong definition almost never binds and the metric reduces to 1 - coverage on this benchmark. the metric carries independent information only where posterior width varies with fidelity. Here it does not, so it should not be read as a second, corroborating result.

## Preregistered criteria

- PASS — A1_coarse_coverage_in_band
- PASS — A2_medium_coverage_in_band
- PASS — A3_reference_coverage_in_band
- PASS — A4_control_arm_calibrates
- PASS — A5_standardized_error_falls_with_fidelity
- PASS — A6_rmse_falls_with_fidelity
- PASS — A7_noise_dominates_only_at_high_fidelity
- PASS — A8_confidently_wrong_rate_falls_with_fidelity

No falsification trigger fired.

The control arm calibrated, so differences between the solver arms are attributable to discretization rather than to the likelihood, the prior or the grid.

## Answer

Yes. Across 500 draws the coarse rung covered α on 0.0% of them against a nominal 95%, and was confidently wrong — narrow interval, excluded truth — on 100.0%. The identical inference with an exact forward map covered 96.2%, so the miscalibration is caused by discretization and not by the inference. Observation noise becomes the dominant error source at the **reference** rung, where coverage reaches 95.2%.

## What this does not show

- no adaptive fidelity selection and no fidelity policy — nothing here chooses a rung
- no new EVSI machinery, no commitment promotion, no ObligationSet change, no certification change
- no production SRIA change of any kind
- no physical validation; the hidden truth is synthetic and known
- no modification to T1's preregistration or results, which are pinned by digest