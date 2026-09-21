# Sprint 3 recovery — battery voltage model and Gate A requalification

Branch `claude/battery-voltage-s3-recovery`, base `claude/battery-thermal-flagship-sprint-3 @ 7aff1449`.

```bash
python benchmarks/battery_voltage_s3_recovery/harness/cycles.py
python benchmarks/battery_voltage_s3_recovery/harness/state.py
python benchmarks/battery_voltage_s3_recovery/harness/ocv2.py
python benchmarks/battery_voltage_s3_recovery/harness/emit_ocv_v2.py
python benchmarks/battery_voltage_s3_recovery/harness/relaxation.py
python benchmarks/battery_voltage_s3_recovery/harness/asymmetry.py
python benchmarks/battery_voltage_s3_recovery/harness/candidates.py
python benchmarks/battery_voltage_s3_recovery/harness/freeze.py
python benchmarks/battery_voltage_s3_recovery/harness/holdout.py --open
python benchmarks/battery_voltage_s3_recovery/harness/diagnose.py
python benchmarks/battery_voltage_s3_recovery/harness/historical.py
```

## 1. Verdict

**S3 RECOVERY / GATE A: NOT YET PASSED**

The voltage model was substantially improved on calibration and validation evidence, and the new locked holdout still fails. Those are two separate findings and both are real.

| Gate A, new locked holdout B0041, cases inside declared applicability | measured | limit | |
|---|---|---|---|
| `terminal_voltage` MAE | 128.51 mV | 40.00 mV | **FAIL** |
| `terminal_voltage` RMSE | 152.17 mV | 50.00 mV | **FAIL** |
| `terminal_voltage` P95 | 320.48 mV | 90.00 mV | **FAIL** |
| `terminal_voltage` max | 466.49 mV | reported, not gated | — |
| `terminal_voltage` bias | +128.18 mV | reported, not gated | — |
| `cell_temperature` MAE | 1.07 K | 2.50 K | **PASS** |
| `cell_temperature` RMSE | 1.30 K | 3.00 K | **PASS** |
| `cell_temperature` P95 | 2.45 K | 5.00 K | **PASS** |
| `cell_temperature` max | 3.30 K | reported, not gated | — |
| `cell_temperature` bias | -0.89 K | reported, not gated | — |

Every threshold above is read from the Sprint 3 preregistration at run time. This recovery holds no second copy of them and a test asserts they are that file's.

### What failed, in one paragraph

The voltage bias on the holdout is +128.18 mV against a mean absolute error of 128.51 mV, so almost every scored residual has the same sign: the model is uniformly high on this cell. On the same model and the same run the calibration bias is -0.38 mV and the validation bias -7.97 mV. This is not a model that drifted; it is one cell sitting at a different level. The cell's own measured resistance is +0.117 ohm above the calibration cell's where the two can be compared, which is +119 mV at the holdout's 1 A — the right sign and nearly the whole size of the bias. The model carries no resistance-growth term and says so in its own exclusion list.

## 2. Area by area

| Area | Baseline | Change | Evidence | Validation effect | Final status |
|---|---|---|---|---|---|
| Charge-state basis | 2 Ah manufacturer rating, declared constant | measured available charge per run, from prior like-for-like cycles | the rating is 22% above what these cells deliver at the median; the estimator's own spread is 0.74% at one sigma over 624 calibration discharges | validation RMSE 116.4 → 60.7 mV | **adopted** |
| Initial state | full charge asserted from one rest-voltage screen | two independent witnesses; UNKNOWN when they disagree | at 4 °C the charger stops with 40–84 mA still flowing against a declared 20 mA, so those cells are not at the protocol's full-charge state | 15 trajectories refused rather than asserted | **adopted** |
| OCV authority | one pseudo-OCV on the declared axis, 32.6 mV median spread, floor 0.2737 | re-derived on the measured axis, conditioned on cell-temperature band | pooling the bands collapses the admissible interval to 4 knots at 34.5 mV | cold 12.6 mV / warm 22.9 mV median spread | **adopted** |
| R0 charge-state axis | none; one value per group | measured branch-difference shape, no fitted parameter | 0.201 → 0.133 Ω warm and 0.499 → 0.294 Ω cold across charge state | close to neutral on residuals; the cold unit goes from 3 unidentified parameters at condition 1.6e20 to 0 | **adopted on identifiability** |
| Parameter unit | one set per experiment group | one set per group, ambient corner and nominal load | measured resistance rises 0.169 → 0.208 Ω from 2 A to 4 A while the model's polarization is linear in current | validation RMSE 60.7 → 39.6 mV, the largest single step | **adopted** |
| Arrhenius terms | fitted, reported weakly identified | kept | fixing both at zero costs 40 mV of validation RMSE | 105.8 mV against 60.7 mV | **kept** |
| Second RC branch | declared excluded | still excluded | two modes fit better on 18/18 rest segments, but the slower time constant's spread is 1.173× its median | no improvement in any candidate; identifiability degrades | **rejected** |
| Hysteresis | declared excluded | still excluded | 0 scored cases carry charge current, and the branch gap's rate dependence has the wrong sign for a fixed offset | unfalsifiable on this corpus | **rejected** |
| Measurement screen | none | a sample whose current and voltage channels contradict each other is not an observation | 2 mA reported while the voltage has fallen 590 mV — 295 Ω implied from a 0.2 Ω cell | 82 of 14 837 samples refused, applied to every split alike | **adopted** |
| Applicability | ambient 20–30 °C, 0.5–4.5 A, charge state ≥ 0.2737, cycle ≤ 40 | two declared cell-temperature bands, 0.5–2.5 A, per-band charge-state floor, usable-capacity band, refusal between bands | Sprint 3's own envelope had already classified every 2C cell FAILED while its contract claimed 4.5 A | narrower and honest; the rate ceiling matches the envelope | **adopted, and one dimension is now known to be wrong** |
| Temperature model | passed Sprint 3's Gate A | untouched | no defect demonstrated | holdout MAE 1.07 K, RMSE 1.30 K | **still passes** |

## 3. The questions, answered

**Selected model.** `battery.cell.electrothermal_1rc@0.2.0`, candidate `M11`. Same equations as Sprint 3's `@0.1.0` — one RC branch, Arrhenius on both resistances, irreversible heat only — with a measured available-charge basis, a band-conditioned open-circuit voltage authority, a measured charge-state shape on the ohmic resistance that adds no fitted parameter, and one parameter set per declared operating block (7 parameters per unit, 42 in total).

**Why selected.** M10 and M11 are indistinguishable on the Gate A statistics -- M11 is 2.4 mV better on mean absolute error and 0.5 mV better on RMSE, M10 is 2.1 mV better on the 95th percentile -- and they carry the SAME number of fitted parameters, because M11's charge-state shape on the ohmic resistance is a measurement and not a parameter. So the residual statistics do not choose between them and R6 does: identifiability before complexity. M10 leaves 10 of its 42 parameters unidentified and M11 leaves 2, and the difference is concentrated exactly where it matters. In M10 the cold parameter unit -- the only unit that will predict the locked holdout -- leaves the ohmic reference resistance, the polarization reference resistance and the polarization activation energy all unidentified, with a normal-matrix condition number of 1.6e20 and a correlation of -0.9999 between R0 and its own activation energy. That is a fitter absorbing a real charge-state trend into a constant and its temperature slope. Giving it the measured trend instead leaves that unit fully identified at a condition number four orders of magnitude lower. A model whose parameters are not identified in the regime it is about to be tested in is not the simpler model, it is the less determined one.

**Rejected alternatives.** Eleven, each with the evidence that rejected it, in `MODEL_SELECTION_REPORT.md` and `NEW_GATE_A_PREREGISTRATION.json`. The two that matter: a second RC branch, refused because its slower time constant is not reproducible across trajectories rather than because it fitted badly; and both activation energies fixed at zero, refused because it costs 40 mV of validation RMSE.

**Parameter identifiability.** 20 identified, 20 weak, 2 unidentified across 6 parameter units, each with a standard error from the fit's own Jacobian, the correlated pairs above 0.9, and the normal-matrix condition number. The cold unit — the only one that predicts the holdout — is fully identified, and making it so is why the measured charge-state shape was promoted.

**Initial-state method.** Two independent witnesses: the preceding charge's termination and the trajectory's own opening rest sample. 50 trajectories carry the strong basis, where the charger reached its declared taper and the cell is at the protocol's full-charge state. 22 carry a weaker one: at 4 °C the charger stops with 40–84 mA still flowing, so what is established is only that the run starts from the same state as the cycle its capacity was measured on. 15 are UNKNOWN and are refused.

**Capacity / SOH authority.** `engcore.domains.battery.capacity`. `Q_available` is the delivered capacity of the most recent prior discharge of the same cell at the same load and ambient, and UNKNOWN when there is none. It separates the manufacturer's rating, a reference capacity, the measured usable capacity, the initial available charge and a capacity state of health, and it never reads the trajectory it is asked about. Measured spread: +0.37% median, 0.74% at one sigma, 3.38% at the 95th percentile over 624 calibration discharges.

**OCV authority.** `engcore.domains.battery.flagship_ocv_v2`, generated from `OCV_AUTHORITY_V2.json`. Two curves, one per declared cell-temperature band, on the measured available-charge axis, from calibration cells B0005, B0018, B0033, B0038, B0042 only. Cold: 20 knots over [0.05, 1.0]. Warm: 19 knots over [0.1, 1.0]. No interpolation between the bands: nothing is measured between 13 and 23 °C and the model refuses there.

**Voltage validation.** n=1197, MAE 23.23 mV, RMSE 38.42 mV, P95 91.77 mV, bias -7.97 mV.
**Voltage calibration.** n=1742, MAE 21.07 mV, RMSE 40.19 mV, P95 84.32 mV, bias -0.38 mV.

On the frozen limits, validation passes MAE and RMSE and misses P95 by 1.77 mV. That was known before the holdout was opened and is recorded in `PRE_OPENING_REHEARSAL.json`.

**Temperature validation.** n=1197, MAE 0.67 K, RMSE 0.93 K, P95 1.72 K, bias -0.24 K. The thermal model was not touched.

**New holdout.** Cell **B0041**, trajectories B0041.d0043, B0041.d0048, B0041.d0053, B0041.d0057, B0041.d0062, B0041.d0067. Dataset digest `062d9fcbd487c829…`, holdout opening digest `5632ad218245d85a…`, evaluation id `battery.electrothermal.s3_recovery.holdout.v1`, report digest `c8955bac17d86ba8…`.

**Why independent.** All eleven cells inside Sprint 3's declared ambient band were consumed by its own three splits, so no untouched room-temperature cell exists in this archive. The selection rule — the cells this archive contains that appear in no Sprint 3 split — has exactly one solution, B0041, whose entire life ran at 4 °C, which is why Sprint 3's 20–30 °C screen never saw it. Its measured channels were not on disk until the opening: the development corpus loader refuses a holdout trajectory and the candidate harness calls that refusal on the set it loads. What was read before the freeze is its identity, cycle indices, ambient, nominal load, sample counts and first sample — the two channels the initial-state authority needs — and no voltage after the first sample.

**New holdout metrics.** n=348, MAE 128.51 mV, RMSE 152.17 mV, P95 320.48 mV, max 466.49 mV, bias +128.18 mV. One cell, so the per-cell and the aggregate numbers are the same — which is the opposite of Sprint 3's problem, where one bad cell hid inside three.

Campaign counts, over all three splits:

| | |
|---|---|
| pass | 5927 |
| fail | 647 |
| unscored | 0 |
| missing | 0 |
| error | 0 |
| correct_refusal | 1880 |
| unexpected_refusal | 0 |
| outside_applicability | 12 |
| applicability_undeclared | 0 |
| refusal accuracy | 1.0 |

**Old holdout diagnostic result.** Labelled `historical_diagnostic`, `satisfies_gate_a: false`, and run outside the campaign machinery on purpose so Core cannot call it validation.

| cell | Sprint 3 RMSE | recovery RMSE | change | recovery bias |
|---|---|---|---|---|
| B0007 | 20.47 mV | 7.53 mV | -63.2% | -5.62 mV |
| B0044 | 99.74 mV | 50.72 mV | -49.1% | +48.97 mV |

B0036 is now refused rather than predicted: its experiment group has no 2 A calibration cell, and the block parameter unit will not lend it B0033's 4 A parameters. Sprint 3 did lend them. That refusal is a consequence of the structure this round adopted, not a gap in it.

The mechanism Sprint 3 identified was addressed: B0044, the cell that carried its aggregate, halves. What remains on B0044 is a +49 mV bias of the same sign and the same kind as B0041's.

**Replay.** NOT PERFORMED for the recovery model, and the reason is structural rather than an omission: the composition pack's blueprint pins its participant's model version, so a new model version needs a parallel blueprint, composition pack and execution pack. The freeze record stated this before the holdout was opened. Sprint 3's own replay reproduces `REPLAYED_MATCH` on this tree and is recorded in the baseline.

**Certification.** NOT PRODUCED for the recovery model, for the same reason. Sprint 3's certification record still verifies on this tree.

**Gate A.** NOT YET PASSED.

## 4. Why it failed (R19), and why there is no second holdout

The voltage bias is within a third of a millivolt of the mean absolute error, so almost every scored residual has the same sign: the model is uniformly high on this cell. The same model's calibration bias is -0.38 mV and its validation bias -7.97 mV, so this is one cell at a different level rather than a model that drifted. Nothing that averages out can explain it.

| candidate cause | verdict |
|---|---|
| capacity or state uncertainty | REFUTED on this cell. Every holdout trajectory's available charge is inside the spread the estimator declared on calibration cells |
| ocv inadequacy | SUPPORTED but NOT the sign of the failure. Inside the range where B0041's branches overlap the declared cold curve sits +17 mV from the cell's own branch-averaged pseudo-OCV -- the cell is HIGHER than the curve, which on its own would make the model predict low. The model predicts high, so a curve error is present and is not what the failure is made of |
| resistance structure | SUPPORTED, and it is the leading attribution. B0041's own branch-difference resistance runs +0.117 ohm above the cold calibration cell's where the two can be compared, which is +119 mV at the holdout's 1 A -- the right sign and the right order for the observed bias. The model has no resistance-growth term: its own exclusion list says only the capacity part of ageing is carried, and this is the size of the part that is not |
| rc model form | NOT IMPLICATED. A relaxation-mode error does not produce a single-signed bias across every scored sample, and the rest relaxation analysis already found no reproducible second timescale |
| cell to cell variation | SUPPORTED, and this is the same finding stated from the other side: the cold band has exactly one calibration cell, so the authority carries no cell-to-cell spread at all |
| ageing | SUPPORTED as the mechanism behind the cell-to-cell difference. B0041 delivers 0.96-1.33 Ah where the cold calibration cell delivers 1.41-1.55 Ah at the same condition. Normalizing the charge state by usable capacity removes the capacity part of ageing and nothing else; the model's own exclusion list says so, and this holdout is what measures the size of what is left |
| dataset inconsistency | NOT IMPLICATED. The channel-consistency screen refused the samples where the two channels contradict each other, and the remaining residual is smooth and single-signed rather than spiky |
| measurement quality | NOT IMPLICATED for the same reason, and no instrument accuracy is stated by this source either way |
| applicability definition | IMPLICATED, and this is the actionable one. The contract declares a usable-capacity band of 0.9 to 2.0 Ah, which B0041 is inside, while the cold curve behind that band was derived from one cell at 1.41-1.55 Ah. The contract admits a cell the authority has no evidence for. A band that named the capacity range its own OCV evidence covers would have refused B0041 instead of answering wrongly -- and refusing correctly is what Forge is supposed to prefer |

### The three measurements that settle it

**The capacity basis is right.** Every holdout trajectory's available charge is within 1.93% of what it actually delivered, against a declared 95th percentile of 3.38%. The hypothesis Sprint 3's round report pointed at is refuted on this cell.

**The cell's resistance is higher than the calibration cell's.** +0.1174 Ω where the charge and discharge branches overlap, worth +119 mV at 1 A against an observed bias of +128 mV.

**The temperature channel agrees.** One resistance sets the ohmic drop and the ohmic heat, so an under-estimated resistance makes the voltage high and the temperature low. An open-circuit voltage error would move the voltage and leave the temperature alone.

| split | voltage bias | temperature bias |
|---|---|---|
| calibration | -0.38 mV | -0.069 K |
| validation | -7.97 mV | -0.244 K |
| locked_holdout | +128.18 mV | -0.885 K |

**What cannot be separated.** Above the charge state where B0041's two branches overlap (0.3052), the branch-averaged pseudo-OCV is the discharge branch with a held ohmic correction, so it carries the resistance rather than separating from it. Most scored samples sit above that point. How much of the remaining 10 mV is a further resistance excess and how much is a curve difference, this archive cannot say.

### The actionable finding

The contract declares a usable-capacity band of 0.9 to 2.0 Ah, which B0041 is inside, while the cold curve behind that band was derived from one cell at 1.41-1.55 Ah. The contract admits a cell the authority has no evidence for. A band that named the capacity range its own OCV evidence covers would have refused B0041 instead of answering wrongly -- and refusing correctly is what Forge is supposed to prefer.

### What is deliberately not being done

No second holdout. R19 is explicit and it is right: a sequence of holdouts until one passes is not validation. The next governed evaluation needs new evidence or a narrower contract, not another draw from the same archive.

What would settle the remainder:

- A second cold calibration cell, so the open-circuit voltage authority carries cell-to-cell spread instead of one cell's curve. This archive has none once B0041 is the holdout and B0044 has been read.
- A capacity-conditioned open-circuit voltage authority, which needs calibration cells at several states of health in the same band.
- An applicability band that names the usable-capacity range its own curve evidence covers, which would have refused B0041 rather than answering for it.

## 5. Evidence classes, kept apart

| class | what it is here | what it may decide |
|---|---|---|
| **Independent evidence** | the new locked holdout, cell B0041, opened once under a registered evaluation after the freeze commit | Gate A, and nothing else |
| **Validation evidence** | cells B0006, B0034, B0043 — no fit ever saw them | model selection, the applicability contract, the measurement screen. Never Gate A |
| **Model-development evidence** | calibration cells B0005, B0018, B0033, B0038, B0042, and every authority derived from them | parameters, the OCV curves, the capacity estimator's spread |
| **Historical diagnostic evidence** | Sprint 3's opened holdout B0007, B0036, B0044 | whether a mechanism was addressed. No gate, ever, and a regression asserts it |

## 6. R1 — what the baseline reproduced, and two defects it found

The committed Sprint 3 tree reproduces its published result. The selection and the vendored corpus come back byte-identical, the four parameter sets and the validation campaign are identical apart from wall-clock fields, `GATE_A.json` regenerates byte-identically, and the flagship's replay, numerical checks and certification verify.

| | measured | limit | |
|---|---|---|---|
| `terminal_voltage` MAE | 38.42 mV | 40.00 mV | **PASS** |
| `terminal_voltage` RMSE | 62.40 mV | 50.00 mV | **FAIL** |
| `terminal_voltage` P95 | 108.13 mV | 90.00 mV | **FAIL** |
| `cell_temperature` MAE | 1.29 K | 2.50 K | **PASS** |
| `cell_temperature` RMSE | 1.65 K | 3.00 K | **PASS** |
| `cell_temperature` P95 | 3.27 K | 5.00 K | **PASS** |

Sprint 3's own per-cell voltage RMSE, which is where its failure lived:

| cell | MAE | RMSE | P95 |
|---|---|---|---|
| B0007 | 17.64 mV | 20.47 mV | 36.23 mV |
| B0036 | 12.65 mV | 17.34 mV | 36.52 mV |
| B0044 | 78.76 mV | 99.74 mV | 171.09 mV |

Two defects surfaced while verifying the chain, and neither is a battery finding.

**The Sprint 3 open-circuit voltage authority is not reproducible from the committed selection.** It rests on B0038.d0001, which a later amendment rejected — first rest voltage is more than 50 mV from the authority's full-charge anchor — and `ocv.py` was never re-run. Two knots move by 0.7 and 2.0 mV. The production curve the flagship ran with therefore rests on a trajectory the campaign's own screen does not admit.

**A composition pack's authority digest is a property of the process, not of the code.** `implementation_fingerprint` hashes `repr(code.co_consts)`, and a nested code object's `repr` carries its memory address. 4 of the battery pack's implementations are affected, so `composition_authority_digest` and every certification digest derived from it differ between two runs of the same bytes. The within-run verification still holds and the scientific result is unaffected; the recorded digest cannot be re-derived later. This is a Core defect and it is reported, not fixed, in a round scoped to the battery voltage model.

## 7. Artifacts

| artifact | sha256 |
|---|---|
| `S3_RECOVERY_BASELINE.json` | `bfe2b70ddb7a00a9…` |
| `CYCLE_INVENTORY.json` | `3dd01353dc948488…` |
| `SELECTION.json` | `a42aa7009f572f37…` |
| `BATTERY_STATE_AUTHORITY.json` | `9c0f0a9e0f1dced3…` |
| `OCV_AUTHORITY_V2.json` | `9adcb29f8d69bc01…` |
| `RELAXATION.json` | `82b15ff7504633ed…` |
| `ASYMMETRY.json` | `ca0d8574f6642bdd…` |
| `MODEL_CANDIDATES.json` | `75412e4078ffb1d5…` |
| `NEW_GATE_A_PREREGISTRATION.json` | `bb045efe40488557…` |
| `PRE_OPENING_REHEARSAL.json` | `952acf0b193a07eb…` |
| `NEW_GATE_A_RESULT.json` | `06bfe1fc46d38a43…` |
| `FAILURE_DIAGNOSIS.json` | `dff29d1df5630070…` |
| `HISTORICAL_DIAGNOSTIC.json` | `747e11af29500a6a…` |

The freeze commit is `f58f81b9` — the model, its parameters, the applicability contract and the Gate A policy were committed before the holdout was opened, and `holdout.py` refuses to run unless the digests it recorded still match.

## 8. Final decision

`S3 RECOVERY / GATE A: NOT YET PASSED`

Failing metrics: `terminal_voltage` MAE (128.51 mV against 40.00 mV); `terminal_voltage` RMSE (152.17 mV against 50.00 mV); `terminal_voltage` P95 (320.48 mV against 90.00 mV).

`cell_temperature` passes all three. The scientific requirement that failed is not the voltage model's form and not its state identification, both of which improved by about a factor of two on independent validation evidence. It is that the cold band's open-circuit voltage and resistance authorities rest on a single calibration cell, and the applicability contract admits cells whose state of health that cell's evidence does not cover. The next governed evaluation needs a capacity- or impedance-conditioned authority, or a contract that refuses B0041, and either way it needs evidence this archive does not contain.

