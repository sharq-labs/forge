# Model selection — Sprint 3 battery voltage recovery

Every candidate below was fitted on **calibration** trajectories and judged on **validation** trajectories. The locked holdout is not on disk for the candidate harness to read, and the harness calls `corpus.refuse_holdout` on the trajectory set it actually loads. No number in this document came from a holdout residual.

Selected: **M11**. Frozen Gate A limits, carried unchanged from the Sprint 3 preregistration: MAE ≤ 40 mV, RMSE ≤ 50 mV, P95 ≤ 90 mV.

## 1. The candidate matrix

`coverage` is the fraction of the validation split's **admissible** samples the candidate answers. It leads the table because a candidate whose open-circuit voltage interval is narrow answers only the easy part of a discharge, and its residual statistics look better for it. That is a narrower claim, not a better model. `penRMSE` charges every unanswered sample one acceptance tolerance, the same way the fit objective charges an unreached one.

| Model | Free params (per unit × units) | Coverage | Calib RMSE | Valid MAE | Valid RMSE | Valid P95 | penRMSE | Residual structure | Identifiability | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| `M0` | 7 × 4 = 28 | 0.994 | 134.8 | 83.6 | 116.4 | 210.2 | 116.1 | bias -42.7 mV, lag-1 0.9053 | 16 id / 10 weak / 2 unid | rejected |
| `M1` | 7 × 4 = 28 | 0.787 | 77.5 | 48.3 | 60.7 | 114.2 | 58.6 | bias -34.9 mV, lag-1 0.9855 | 14 id / 10 weak / 4 unid | rejected |
| `M1p` | 7 × 4 = 28 | 0.130 | 51.6 | 35.1 | 47.4 | 98.4 | 49.7 | bias -27.1 mV, lag-1 0.9621 | 7 id / 15 weak / 6 unid | rejected |
| `M2` | 5 × 4 = 20 | 0.787 | 123.2 | 72.6 | 105.8 | 208.4 | 96.6 | bias -30.0 mV, lag-1 0.9949 | 13 id / 6 weak / 1 unid | rejected |
| `M3` | 7 × 4 = 28 | 0.787 | 73.5 | 50.1 | 61.3 | 107.9 | 59.1 | bias -39.8 mV, lag-1 0.9894 | 17 id / 11 weak / 0 unid | rejected |
| `M4` | 9 × 4 = 36 | 0.787 | 73.4 | 50.4 | 61.4 | 108.0 | 59.1 | bias -39.9 mV, lag-1 0.9898 | 11 id / 16 weak / 9 unid | rejected |
| `M5` | 9 × 4 = 36 | 0.787 | 76.0 | 50.3 | 62.6 | 110.1 | 60.1 | bias -37.2 mV, lag-1 0.9871 | 12 id / 18 weak / 6 unid | rejected |
| `M6` | 7 × 5 = 35 | 0.787 | 61.8 | 37.4 | 51.5 | 111.6 | 51.2 | bias -17.2 mV, lag-1 0.9842 | 18 id / 11 weak / 6 unid | rejected |
| `M7` | 5 × 5 = 25 | 0.787 | 112.5 | 65.7 | 93.2 | 181.6 | 85.8 | bias -51.9 mV, lag-1 0.9935 | 15 id / 7 weak / 3 unid | rejected |
| `M8` | 7 × 5 = 35 | 0.787 | 67.3 | 37.0 | 51.6 | 103.5 | 51.3 | bias -24.5 mV, lag-1 0.9871 | 15 id / 19 weak / 1 unid | rejected |
| `M9` | 9 × 5 = 45 | 0.787 | 54.8 | 37.7 | 51.9 | 115.9 | 51.5 | bias -19.0 mV, lag-1 0.9845 | 18 id / 17 weak / 10 unid | rejected |
| `M10` | 7 × 6 = 42 | 0.787 | 42.7 | 26.0 | 39.6 | 90.2 | 42.0 | bias -8.8 mV, lag-1 0.98 | 17 id / 15 weak / 10 unid | rejected |
| `M11` | 7 × 6 = 42 | 0.787 | 40.1 | 23.6 | 39.1 | 92.3 | 41.6 | bias -8.0 mV, lag-1 0.9822 | 20 id / 20 weak / 2 unid | **SELECTED** |

All voltages in millivolts.

## 2. What each candidate varies

| Model | Charge-state basis | OCV authority | Parameter unit | Arrhenius | R0(z) shape | RC branches |
|---|---|---|---|---|---|---|
| `M0` | declared | s3 | group | free | none | 1 |
| `M1` | available | banded | group | free | none | 1 |
| `M1p` | available | pooled | group | free | none | 1 |
| `M2` | available | banded | group | fixed at 0 | none | 1 |
| `M3` | available | banded | group | free | measured | 1 |
| `M4` | available | banded | group | free | measured | 2 |
| `M5` | available | banded | group | free | none | 2 |
| `M6` | available | banded | group_band | free | none | 1 |
| `M7` | available | banded | group_band | fixed at 0 | none | 1 |
| `M8` | available | banded | group_band | free | measured | 1 |
| `M9` | available | banded | group_band | free | none | 2 |
| `M10` | available | banded | block | free | none | 1 |
| `M11` | available | banded | block | free | measured | 1 |

## 3. Why each alternative was rejected

- **`M0`** — Sprint 3's model on this corpus: 116.4 mV validation RMSE. It is the baseline, not a candidate.
- **`M1`** — the two state authorities alone, with parameters per experiment group as Sprint 3 had them: 60.7 mV validation RMSE. It is half of M0's error and it is the step that matters scientifically -- the failure was a state-identification failure -- but a parameter set asked to serve two rates still compromises between them.
- **`M2`** — both activation energies fixed at zero: 105.8 mV validation RMSE against M1's 60.7. The Arrhenius terms are real even though Sprint 3 reported them weakly identified.
- **`M3`** — M1 plus the measured charge-state shape on R0, without the parameter unit change: 61.3 mV against M1's 60.7. No improvement.
- **`M4`** — M3 plus a second RC branch: 61.4 mV. Two more parameters, nothing.
- **`M5`** — M1 plus a second RC branch: 62.6 mV. Worse than M1.
- **`M6`** — parameters per experiment group and cell-temperature band: 51.6 mV RMSE but 111.6 mV P95, and its cold unit leaves both reference resistances unidentified.
- **`M7`** — M6 with the activation energies fixed at zero: 93.2 mV. Same finding as M2.
- **`M8`** — M6 plus the measured shape: better identifiability than M6 and still 103.5 mV P95. Superseded by the block parameter unit.
- **`M9`** — M6 plus a second RC branch: 51.9 mV RMSE, 115.9 mV P95, and the second branch is unidentified in three of five units.
- **`M10`** — one parameter set per declared operating block, without the measured charge-state shape. It is the largest single step in the matrix -- 60.7 to 39.6 mV validation RMSE -- and it is not selected: its cold parameter unit, the one that predicts the holdout, leaves three of seven parameters unidentified at a condition number of 1.6e20. See the rationale for M11.
- **`M1p`** — one pooled open-circuit voltage curve. Its admissible charge-state interval collapses to [0.85, 1.0], so it answers 13 % of the split's admissible samples. Its residual statistics are the best in the table and they are a statement about a narrower claim.

**Why `M11`.** M10 and M11 are indistinguishable on the Gate A statistics -- M11 is 2.4 mV better on mean absolute error and 0.5 mV better on RMSE, M10 is 2.1 mV better on the 95th percentile -- and they carry the SAME number of fitted parameters, because M11's charge-state shape on the ohmic resistance is a measurement and not a parameter. So the residual statistics do not choose between them and R6 does: identifiability before complexity. M10 leaves 10 of its 42 parameters unidentified and M11 leaves 2, and the difference is concentrated exactly where it matters. In M10 the cold parameter unit -- the only unit that will predict the locked holdout -- leaves the ohmic reference resistance, the polarization reference resistance and the polarization activation energy all unidentified, with a normal-matrix condition number of 1.6e20 and a correlation of -0.9999 between R0 and its own activation energy. That is a fitter absorbing a real charge-state trend into a constant and its temperature slope. Giving it the measured trend instead leaves that unit fully identified at a condition number four orders of magnitude lower. A model whose parameters are not identified in the regime it is about to be tested in is not the simpler model, it is the less determined one.

## 4. The model-form questions, answered from the measurement

### A second relaxation timescale (R7)

18 rest segments from calibration cells B0005, B0018, B0033, B0038, B0042, fitted with one exponential and with two, with no cell model involved.

| | one mode | two modes, fast | two modes, slow |
|---|---|---|---|
| median τ (s) | 89.52 | 21.4 | 160.47 |
| spread of τ, IQR / median | 0.403 | 0.702 | 1.173 |

Two exponentials fit better on 18 of 18 segments and the modes are separated on 18 of them — which is what two exponentials always do to a relaxation. The slower time constant's spread is 1.173 times its own median and it ranges from 79.5 to 620.49 s, so it does not land in the same place twice.

**no second reproducible relaxation timescale is established.** The 1-RC branch is retained.

### Charge/discharge asymmetry (R8)

Two independent grounds, and the first settles it: 0 scored cases carry charge current, so a hysteresis state would change no prediction in this corpus and nothing here could falsify one.

The second is a measurement. A rate-independent offset inflates the branch-difference resistance at *low* rate. Measured, warm band:

| charge state | R_eff at 2 A (Ω) | R_eff at 4 A (Ω) | ratio |
|---|---|---|---|
| 0.3 | 0.1492 | 0.2219 | 0.672 |
| 0.4 | 0.1501 | 0.2173 | 0.691 |
| 0.5 | 0.1517 | 0.1884 | 0.805 |
| 0.6 | 0.1543 | 0.1895 | 0.814 |
| 0.7 | 0.1530 | 0.1791 | 0.854 |

The ratio is below one at every charge state, so the sign is the opposite of a hysteresis offset. What the archive shows instead is a rate dependence of the effective resistance, which is nonlinear polarization a linear RC branch cannot represent. the 2 A and 4 A calibration blocks are different cells, so part of this rate difference could be cell-to-cell variation. That weakens the positive finding about rate dependence; it does not weaken the negative one, because a hysteresis offset would have to push R_eff the other way and no cell-to-cell spread in this archive is large enough to hide a sign reversal of this size

**no charge/discharge asymmetry term is admitted. Two independent reasons: the campaign scores one current direction, so a hysteresis state would change no prediction here and nothing could falsify it; and the branch gap's rate dependence has the wrong sign for a rate-independent offset**

### A temperature axis on the open-circuit voltage (R4, R9)

The curve was re-derived per declared cell-temperature band and also pooled across them. Pooling is the test, not a candidate:

| curve | pairs | admitted interval | knots | median IQR (mV) |
|---|---|---|---|---|
| cold | 22 | [0.05, 1.0] | 20 | 12.58 |
| warm | 178 | [0.1, 1.0] | 19 | 22.93 |
| pooled | 200 | [0.85, 1.0] | 4 | 34.48 |

Pooling collapses the admissible interval because the two bands disagree by more than the frozen 50 mV acceptance tolerance over most of the axis. That collapse is the evidence that they are two relations, and the candidate that used the pooled curve (`M1p`) is in the matrix to show what a narrow claim looks like from the inside.

Conditioning is on **measured cell temperature, not ambient**. At 4 °C ambient the 4 A discharges self-heat to 23–41 °C and are not cold measurements; the 1 A discharges at the same ambient stay at 6–13 °C. Ambient labels the chamber.

## 5. What the Sprint 3 failure actually was

Sprint 3's locked holdout failed on one cell: B0044 at 99.7 mV RMSE against 20.5 and 17.3 mV for the other two. Its round report attributed that to an 8.4 % capacity gap between B0044 and the calibration cell of its group, against a charge-state basis that was a declared constant.

That attribution is right about the mechanism and understates it.

The declared 2 Ah basis is not 8 % wrong, it is about **30 % above what these cells deliver**, and wrong by a different amount for each of them. The absolute part of that error cancels, because the Sprint 3 open-circuit voltage curve was built on the same wrong axis; what survives is the differential between a cell and the calibration cell it inherits parameters from. Two estimators that are causally prior to the trajectory being predicted — the most recent like-for-like discharge of the same cell, and the charge the preceding charge cycle put in — both land within 0.74 % at one sigma and 3.38 % at the 95th percentile, measured over 624 calibration-cell discharges.

The decisive check is that **the prior-evidence estimator costs almost nothing against the oracle.** Re-derived on a capacity-normalized axis, the open-circuit voltage curve's inter-pair spread at fixed charge state falls from 45.0 mV to 22.9 mV, and using each trajectory's *own* delivered capacity — which would leak the answer — gives 23.1 mV. The axis was carrying the variation, and it does not need the answer to be fixed.

The second largest term was not a state problem at all. A parameter set fitted across operating rates compromises between them, because this model's polarization is linear in current and the measured branch resistance is not — 0.169 Ω at 2 A against 0.208 Ω at 4 A. Giving each declared operating block its own set took validation RMSE from 60.7 to 39.6 mV, the largest single step in the matrix.

And one term was never the model's fault. At the first instants of many trajectories the current channel reads about 2 mA while the voltage has already fallen 200–590 mV: a 295 Ω implied resistance from a cell measured at 0.2 Ω. The two channels contradict each other about whether the load is on. Sprint 3 scored those samples — its holdout's rest bucket shows RMSE 111.5 mV over 24 samples — and a model-free screen now refuses them.

## 6. What the selected model still cannot do

- **the cold band has exactly one calibration cell. Every in-band cell of the room-ambient corner was consumed by Sprint 3's three splits, and of the four cells that ran the low-ambient protocol one is the new holdout, one was Sprint 3's holdout and has been read, one is the validation cell and one is the calibration cell. A single calibration cell carries no cell-to-cell spread, and this recovery's own validation evidence puts that spread at 20 to 35 mV against a 50 mV acceptance tolerance**
- The remaining cold-band validation residual is dominated by a systematic offset rather than scatter. On the calibration cell the fit has essentially no bias; transferred to the independent cell of the same group it carries one, and the two cells' opening rest voltages differ by about 20 mV before any model runs.
- No entropic heat, no ageing state, no hysteresis, no second time constant, no charge-state axis on either resistance. Each is a declared exclusion of the model record and each was either tested and rejected in this round or left where Sprint 3 left it.
- No coupled multiphysics run, no replay and no certification record for the recovery model. The composition pack's blueprint pins the participant's model version, so a new model version needs a parallel blueprint, composition pack and execution pack. That is a larger structural change than this recovery is scoped for, and the consequence is stated rather than worked around.

## 7. Provenance

| artifact | sha256 |
|---|---|
| `CYCLE_INVENTORY.json` | `3dd01353dc948488…` |
| `SELECTION.json` | `a42aa7009f572f37…` |
| `BATTERY_STATE_AUTHORITY.json` | `9c0f0a9e0f1dced3…` |
| `OCV_AUTHORITY_V2.json` | `9adcb29f8d69bc01…` |
| `RELAXATION.json` | `82b15ff7504633ed…` |
| `ASYMMETRY.json` | `ca0d8574f6642bdd…` |
| `MODEL_CANDIDATES.json` | `75412e4078ffb1d5…` |
| `NEW_GATE_A_PREREGISTRATION.json` | `bb045efe40488557…` |

