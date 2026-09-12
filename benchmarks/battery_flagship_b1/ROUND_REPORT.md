# Battery Flagship B1 — Real-Data Scientific Validation

Branch `claude/battery-flagship-b1` · `B1_BASELINE = f89a32a` (`v1.0-core-freeze`) ·
Domain-first · Core frozen

```
python -X utf8 benchmarks/battery_flagship_b1/audit/run_b1.py
python -X utf8 -m pytest benchmarks/battery_flagship_b1/tests tests/domains/battery -q
```

---

## 1. FINAL VERDICT

**BATTERY FLAGSHIP B1 COMPLETE — MODEL INADEQUACY DEMONSTRATED**

On measured data, in one run, the preregistered protocol gives three results:

- **CALIBRATION_CONVERGED**
- **PARAMETERS_IDENTIFIABLE**
- **MODEL_INADEQUATE**

The selected model is `battery.cell.rint_ocv` with its affine open-circuit-voltage chord. It calibrates cleanly, its two parameters are pinned to 0.1–0.2 %, and it still fails to predict every held-out measured state of charge.

- **At 0 %:** the miss is 372 mV.
- **On the plateau (40 %, 60 %):** the miss is 12–13 mV, against a measurement uncertainty near 1 mV.

None of the model's own validity conditions flags any of this.

---

## 2. CORE FREEZE STATUS

**Unchanged. Nothing about the frozen Core was modified.**

| check | result |
|---|---|
| `git diff f89a32a -- scientific data inference uq adequacy execution studies api_snapshot.py engcore/__init__.py domains/__init__.py tests/api tools/certification certification pyproject.toml` + the 5 harness files | **empty** |
| `python -m tools.certification.core_certificate --verify` | **OK** |
| `python -m tools.certification.core_freeze --verify` | **OK**, mode **DESCENDANT**, 29 binding checks pass |
| `CORE_GAP_CANDIDATE` raised | **none** |

This is the freeze verifier's first real use in DESCENDANT mode.

- **Binding checks still pass:** frozen API, serialization, identity, ordering and exceptions.
- **Byte-level checks became informational, as the post-freeze policy says they should:**
  - The domain digest moved, because a domain file was added.
  - The post-candidate path list no longer applies.

---

## 3. BATTERY MODEL SELECTED

**`battery.cell.rint_ocv@0.1.0`, realization `closed_form`, solver `engcore.battery.cell_closed_form@0.1.0`.**

### Phase 1 inventory

These figures were read from production code, not from README claims.

| Capability | Current implementation | Evidence | Limitation |
|---|---|---|---|
| Rint terminal voltage and heat | `models.RINT_OCV_MODEL`, `solver.evaluate_step`: V = OCV(z) − I·R, Q = I²R | `SELF_CONSISTENT`; solver attains `DIMENSIONALLY_VALID` only | one constant R; no RC, no hysteresis, discharge only |
| OCV representation | affine chord between two endpoints, **or** an optional declared curve (`open_circuit_voltage_curve`) | before B1, one earlier measurement round only | curve route cannot invert a voltage cutoff (refused) |
| Coulomb counting | `COULOMB_COUNTING_MODEL`: z = z₀ − It/(ηQ) | `SELF_CONSISTENT` | no self-discharge, no feedback |
| Runtime to cutoff | `CONSTANT_CURRENT_RUNTIME_MODEL` | `SELF_CONSISTENT` | constant current, chord inversion only |
| Peukert derating | `PEUKERT_DERATING_MODEL` | `UNVALIDATED` | fitted correlation |
| State variables | SOC (state), current (control), temperature (state, supplied externally) | — | temperature never inferred |
| Inputs / parameters | capacity, R_int, OCV endpoints or curve, η, duration | — | `DischargeLoad` requires **strictly positive** current and duration |
| Applicability | 11 `RangeCondition`s (C-rate, pulse, SOC window, temperature, R drift, self-heating, polarization, terminal ratio) | — | every one is UNKNOWN until the caller declares its input; **none bears on whether the OCV representation fits the cell** |
| Solvers | one closed-form evaluator | 3 checks (dimensions, coulomb residual, terminal residual) | residual checks establish no level |
| Coupling | one-way self-heating march against the lumped thermal model | tests | thermal applicability undeclarable |
| Result / provenance | `ScientificResult` via the solver protocol; MCP boundary `mcp/battery.py` | tests | — |
| Calibration adapter | **none before B1** | — | added in B1 (§26) |
| Empirical evidence | none shipped in the domain | `model_measurement_validation` compared the pinned chord with S-OCV | no Core calibration, UQ or adequacy was used |
| Known limitations | stated in `docs/domains/battery-v0.md` and each record's `exclusions` | — | — |

**Why this model:** `rint_ocv` is the only battery model whose measured-data prediction has every input stated in an in-repo dataset (§5).

- **Coulomb counting, runtime, Peukert and R_int:** all need a measured discharge current, which no in-repo dataset records.

---

## 4. EXACT MODEL CLAIM

As implemented, not as marketed:

> **What the model describes:** terminal voltage and irreversible heat of one cell. The cell is one ideal source at OCV(z) in series with one **constant** resistance:
>
> - V = OCV(z) − I·R_int
> - OCV(z) = V_empty + (V_full − V_empty)·z, unless a curve is declared
> - Q = I²·R_int
>
> **The regime it covers:**
>
> - **discharge only**
> - **one uniform temperature, supplied from outside**
> - **no diffusion or double-layer dynamics:** no RC branch, **no hysteresis**
> - **no ageing**
> - **no reversible heat**
> - **no dependence of R_int on temperature or SOC**

The distinctions the brief lists, applied to this model:

| distinction | this model |
|---|---|
| constant vs SOC-dependent OCV | **affine in SOC** by default; a declared curve is optional |
| constant vs state-dependent R | **constant** |
| temperature dependence | **none** (drift is only screened, never modelled) |
| static vs transient | **static**, closed form per interval |
| charge vs discharge | **discharge only** |
| hysteresis | **excluded** |
| ageing | **excluded** |
| polarization dynamics | **excluded**; a timescale screen only |

**Real cases inside that claim, with measured data in this repository:**

- **In claim, and tested here:** the equilibrium OCV of a cell brought to a known SOC by discharge. That is the `open_circuit_voltage` output.
- **In claim, but untestable:** terminal voltage under a known constant discharge current. No in-repo dataset records the current.

---

## 5. REAL DATASET

Phase 3 inventory:

| dataset | location | class |
|---|---|---|
| S-OCV, 24 h OCV relaxation, 8 cells | `benchmarks/model_measurement_validation/evidence/ocv_relaxation_24h.xlsx` | **REAL_MEASURED** (LEVEL 2) |
| S-DCHG, constant-current discharge curves, 10 LiFePO4 cells | `…/evidence/discharge_curves_1min.json` | **DERIVED** from REAL_MEASURED (decimated to 1 min); current not recorded |
| 400 hard-benchmark battery cases | `benchmarks/hard/cases_battery/` | **SYNTHETIC** (`generate_battery.py`) |
| empirical-validation cell fixture | `benchmarks/empirical_validation/fixtures/battery_cell.json` | **SYNTHETIC** ("representative, not measured") |
| blind / blind_v2 battery oracles | `benchmarks/blind*/…/battery.py` | **REFERENCE_ONLY** (independent analytical reimplementation) |
| PyBaMM half-cell / "example" tables | rejected by the earlier round | **UNKNOWN_PROVENANCE** / out of scope |

**Flagship experiment (Phase 4, one only):**

- **Dataset:** S-OCV
- **Cell:** BATT_001
- **Sheet:** `24h_Discharge_APR`
- **Data:** 24 h relaxed OCV at SOC 0, 20, 40, 50, 60 and 80 %

---

## 6. DATASET PROVENANCE

| | |
|---|---|
| title | 24-hour OCV relaxation measurements after complete charge/discharge cycles for batteries with different chemistries |
| authors | Voicilă, Enache, Vîlciu, Serițan — National University of Science and Technology POLITEHNICA Bucharest |
| identifier | **DOI 10.21227/651q-8v82** (IEEE DataPort, v1), CC BY 4.0 |
| related publication | Voicila et al. (2025), *Batteries* 11(5) 186 |
| retrieved via | `raw.githubusercontent.com/BulyK47/battery-datasets` mirror; the DOI host is blocked in this environment |
| file SHA-256 | `9b8c541675256c08c24cc6ebeb486a46d07c533a70bf4dabcca4955dba90e08a`, checked before and after the run: **unchanged** |
| instruments | NI USB-6251 (16-bit), Allegro ACS724 (±1.5 % typical), chamber ±0.5 °C, input impedance 10 GΩ |

Every metadata value above was read from the workbook's own Header sheet.

---

## 7. CHEMISTRY / CONDITIONS

| | |
|---|---|
| cell | BATT_001, Lithium Werks APR, 18650 |
| chemistry | **LiFePO4** |
| nominal capacity | **1100 mAh** |
| nominal voltage | 3.3 V |
| declared internal resistance | 12.6 mΩ |
| voltage window | 2.0 V discharge cutoff, 3.6 V charge |
| temperature | ambient **23 ± 2 °C** (one temperature only) |
| load profile | discharged from 100 % SOC at the standard 0.2C to the target, then **open circuit for 24 h** |
| SOC range | 0–80 % on the discharge branch (20–100 % on the charge branch) |
| channels | open-circuit voltage |
| sampling | 60 s, 1441 samples per trace |
| units | hours, volts, % of nominal capacity |

### Phase 5 — raw data integrity (`DATA_INTEGRITY.json`): **PASS**

Checked on both APR sheets before anything was fitted:

| check | result |
|---|---|
| rows per sheet | 1441 |
| missing samples | 0 |
| timestamps | finite, strictly increasing, 0 → 24 h |
| sampling step | 60 s, jitter below 1e-8 s |
| duplicate timestamps | 0 |
| repeated trace IDs | none |
| column labels vs the Header's inventory | match exactly |
| non-finite values | 0 |
| physically impossible voltages (outside 0–5 V) | 0 |
| values outside the cell's published 2.0–3.6 V window | 0 |
| discharge-sheet range | 2.0123–3.3310 V |
| Header metadata vs every fixed declaration | consistent |

**Transformations:** none to the raw file. The relaxed value is the sample at t = 24 h, as published.

---

## 8. CALIBRATION SPLIT

**Calibration set:** SOC {0.2, 0.5, 0.8}.

- **Condition IDs:** `BATT_001.DCHG.SOC020`, `SOC050`, `SOC080`.
- **Dataset ID:** `S-OCV.BATT_001.discharge.calibration`.

**What the split is by:** one relaxation trace, meaning one independently conditioned state of charge.

**Why no time-sample leakage can occur:** time samples are never observations. Only the 24 h value of each trace is.

**Sigma rule (amendment A2):** calibration sigmas are computed from **calibration traces only**. Otherwise held-out measured values would set the calibration likelihood's weights.

---

## 9. HELD-OUT SPLIT

**Held-out set:** SOC {0.0, 0.4, 0.6}, dataset ID `S-OCV.BATT_001.discharge.held_out`.

- **0.4 and 0.6:** interpolation on the plateau.
- **0.0:** extrapolation into the knee.

**CALIBRATION ∩ HELD_OUT = ∅, proved twice:**

- **By identity:** `intersection_by_identity = []`.
- **By material content:** `intersection_by_material_content = []`, using `observation_content_digest`.

Both went through the frozen `ObservationSplit`.

**Disclosed:** the earlier round's result was known when the split was preregistered, including a knee at 0 %. That is recorded in `PREREGISTRATION.json` §`what_was_already_known`. The plateau points are held out alongside the knee so that a plateau pass was possible and would have been reported.

---

## 10. PARAMETERS CALIBRATED

| canonical name | physical meaning | unit | bounds | initial | status |
|---|---|---|---|---|---|
| `open_circuit_voltage_at_empty` | the chord's OCV at z = 0 | V | 2.0 – 3.6 (cell cutoff / charge voltage) | 3.2 | **CALIBRATED** |
| `open_circuit_voltage_at_full` | the chord's OCV at z = 1 | V | 2.0 – 3.6 | 3.4 | **CALIBRATED** |
| `nominal_capacity` | rated charge | Ah | — | 1.1 (dataset) | fixed |
| `internal_resistance` | series resistance | Ω | — | 0.0126 (dataset) | fixed — **not identifiable** at open circuit |
| `coulombic_efficiency` | charge debited per charge drawn | 1 | — | 1.0 | fixed |
| cell temperature | uniform cell temperature | K | — | 296.15 | fixed |
| conditioning current | discharge that set the SOC | A | — | 0.22 (0.2C) | fixed — **proved immaterial** (§17 / S5) |

**What the fitted numbers mean.** Fitted over 0.2–0.8, V_empty and V_full are the chord's **intercepts**, as the model record defines them. They are not claims about the cell's measured OCV at 0 % or 100 %.

**Amendment A1.** The preregistered start was 3.3 V for both parameters. The domain refuses that as a cell (`V_full` must exceed `V_empty`). The synthetic control caught it before any measured run, and the start became 3.2 / 3.4 V.

---

## 11. TRUE/REFERENCE VALUES IF KNOWN

**No true chord exists.** A chord is a property of the model, not of the cell. The reference values available are:

| reference | value |
|---|---|
| measured relaxed OCV, discharge branch | 0 %: 2.8473 V · 20 %: 3.2477 · 40 %: 3.2894 · 50 %: 3.2920 · 60 %: 3.2929 · 80 %: 3.3309 V |
| measured relaxed OCV at 100 % (charge branch) | 3.389 V at 24 h (the value the earlier round pinned as its full-charge endpoint) |
| independent closed-form WLS chord (same calibration data) | V_empty 3.2197416152890, V_full 3.3608822091385 |
| published nominal voltage | 3.3 V |

The WLS chord is the independent cross-check of the Core calibration.

---

## 12. RECOVERED PARAMETERS

| | |
|---|---|
| method | `engcore.inference.calibrate` — bounded trust-region (`trf`) least squares on standardized residuals |
| status | **CALIBRATION_CONVERGED** |
| termination | `xtol` termination condition is satisfied |
| optimizer evaluations | 5 |
| admitted forward predictions | 39, every one through the production solver |
| objective (χ²) | 3.669 on 1 degree of freedom (p = 0.055) |
| wall time | 0.012 s (informational) |
| **V_empty** | **3.219742 V** |
| **V_full** | **3.360882 V** |
| standardized calibration residuals | +0.43, −1.51, +1.09 |
| agreement with independent WLS | **1.0e-12 V** |

---

## 13. IDENTIFIABILITY

**PARAMETERS_IDENTIFIABLE**, from the frozen `assess_identifiability` with default thresholds.

| measure | value | threshold |
|---|---|---|
| condition number | 7.95 | 1e6 |
| max \|correlation\| | 0.664 | 0.95 |
| 95 % relative widths | 0.129 % (V_empty), 0.225 % (V_full) | 1.0 |
| effective sample size | 104.4 over 1681 points | ≥ 8 |
| grid step / posterior σ | 0.30, 0.30 | < 1 |
| grid refusals | none |

**The grid was resolved, not collapsed.** This is a scientific verdict, not the `NUMERICAL_POSTERIOR_RESOLUTION_INADEQUATE` case.

**`internal_resistance` is PARAMETERS_NOT_IDENTIFIABLE from this experiment.** The compared quantity is independent of R_int, so R_int was never calibrated.

---

## 14. PARAMETER UNCERTAINTY

**Grid:** 41 × 41 = 1681 points, ±6 SE around the WLS centre, 0 rejected rows.

| | mean | posterior σ | 95 % marginal |
|---|---|---|---|
| V_empty | 3.219742 V | 0.99 mV | [3.217664, 3.221819] V |
| V_full | 3.360882 V | 1.80 mV | [3.357093, 3.364671] V |

**Posterior correlation:** −0.664.

**Parameter share of predictive uncertainty at the held-out points:** 0.55–0.99 mV.

---

## 15. PREDICTIVE UNCERTAINTY

Computed by `engcore.uq.posterior_predictive_uq`, frozen. The total interval is the exact Gaussian mixture, not a Gaussian approximation.

**Measurement standard uncertainty.** This is the earlier round's budget, unchanged: voltage acquisition, SOC × local slope, entropic term, and measured final-hour drift. Per point:

| SOC | 0 | 0.2 | 0.4 | 0.5 | 0.6 | 0.8 |
|---|---|---|---|---|---|---|
| u (mV) | 2.30 | 0.63 | 0.97 | 1.12 | 1.23 | 1.61 |

| held-out SOC | PARAMETER_UNCERTAINTY | MEASUREMENT_UNCERTAINTY | total | total 95 % interval |
|---|---|---|---|---|
| 0.0 | 0.99 mV | 2.30 mV | 2.51 mV | [3.2148, 3.2247] V |
| 0.4 | 0.55 mV | 0.97 mV | 1.12 mV | [3.2740, 3.2784] V |
| 0.6 | 0.87 mV | 1.23 mV | 1.51 mV | [3.3015, 3.3074] V |

**MODEL_DISCREPANCY_NOT_MODELLED.** No discrepancy term was invented, and no sigma was widened. The total is the parameter and measurement terms in quadrature, which the round tests check.

---

## 16. HELD-OUT RMSE

**215.27 mV** over the three held-out points.

For the plateau interpolations alone (0.4, 0.6) it is **12.38 mV**.

---

## 17. HELD-OUT MAE

**132.39 mV.** Maximum material error: **372.44 mV**, at 0 % SOC.

| SOC | observed | predictive mean | error | standardized | two-sided tail p | log density |
|---|---|---|---|---|---|---|
| 0.0 | 2.8473 V | 3.2197 V | **−372.4 mV** | **−148.6** | 0 | — |
| 0.4 | 3.2894 V | 3.2762 V | **+13.2 mV** | **+11.8** | < 1e-15 | — |
| 0.6 | 3.2929 V | 3.3044 V | **−11.5 mV** | **−7.6** | 2.3e-14 | — |

**Mean log predictive density:** −4254.

**S5 — conditioning current.** The held-out predictions were re-evaluated at 1C instead of 0.2C and are **bitwise identical** (for example 3.2761978528201148 V both times). The unstated conditioning current does not enter the compared value.

---

## 18. COVERAGE

**0 of 3** held-out observations fall inside their 95 % total predictive interval.

- **Wilson 95 % interval** on the coverage rate: [0, 0.56].

---

## 19. RESIDUAL STRUCTURE

**Axes supported by the data:** SOC, and time at rest.

**Axes not supported:**

- **temperature:** there is one temperature.
- **current:** it is zero during the measurement.
- **voltage level:** this collapses into SOC here.

**Against SOC (S2), all six points** relative to the calibrated chord:

| SOC | 0.0 | 0.2 | 0.4 | 0.5 | 0.6 | 0.8 |
|---|---|---|---|---|---|---|
| partition | held | cal | held | cal | held | cal |
| observed − chord (mV) | **−372.4** | −0.3 | **+13.2** | +1.7 | **−11.5** | −1.8 |
| in σ | −161.7 | −0.4 | +13.6 | +1.5 | −9.3 | −1.1 |

**Structure, not noise:**

1. **Staging on the plateau.** Measured OCV is flat from 0.4 to 0.6 (3.2894 → 3.2929 V, 3.5 mV over 20 % SOC), then steps down at 0.2 and up at 0.8. A straight line through the ends and the middle must sit below the flat run at 0.4 and above it at 0.6. The residual sign flips accordingly, the classic signature of LiFePO4's two-phase plateaus.
2. **A knee at empty.** The residual at 0 % is 28× larger than anywhere on the plateau.
3. **Not a SOC-scale error.**
   - A wrong capacity or SOC scaling moves every chord prediction in the **same** direction.
   - The two plateau interpolations miss in **opposite** directions.
   - Explaining 13.2 mV by SOC error alone would take ~9 % SOC, against a sensor's ≤2.5 % × (1−z).
4. **Not measurement uncertainty.** Every held-out residual is 7.6–149 total σ.

**Against time at rest (S3), measured only; the model has no dynamics:**

| SOC | V at 0 h | V at 24 h | recovery | settled within own U from |
|---|---|---|---|---|
| 0.0 | 2.0123 | 2.8473 | +835 mV | **21.5 h** |
| 0.2 | 3.1419 | 3.2477 | +106 mV | 3.4 h |
| 0.4 | 3.2552 | 3.2894 | +34 mV | 4.3 h |
| 0.5 | 3.2610 | 3.2920 | +31 mV | **23.1 h** |
| 0.6 | 3.2703 | 3.2929 | +23 mV | 2.0 h |
| 0.8 | 3.2924 | 3.3309 | +39 mV | 0.6 h |

---

## 20. ADEQUACY VERDICT

**MODEL_INADEQUATE** (`inadequate_for_declared_study`).

**Per-observation scoring:** frozen `assess_predictive_observation`.

**Study rule, preregistered:** Sprint 8's rule, reused.

- Statistic: χ² = Σ standardized residual².
- Degrees of freedom: 3.
- Decision: α = 0.01.

**Result:** χ² = **2.2271 × 10⁴** on 3 df, p < 1e-300 (underflows to 0).

**Nothing was tuned:**

- no threshold changed;
- no sigma inflated;
- no discrepancy term added;
- no point reclassified.

**The model's own applicability assessment** of the calibrated cell, at each held-out SOC:

- **Status:** UNKNOWN.
- **Satisfied:** `nominal_capacity`, `internal_resistance`, `terminal_voltage_ratio`.
- **Violated:** **none**.
- **Unknown:** 8 (C-rate, pulse, pulse duration, SOC window, temperature, R drift, self-heating, polarization), because the dataset declares no ratings.

**Nothing in the model record would have warned a caller.**

---

## 21. APPLICABILITY REGION

**No adequate region was demonstrated at measurement precision.**

**S1 — calibrated on the plateau core** {0.4, 0.5, 0.6}, with each outside point scored alone at α = 0.01:

| scored SOC | error | standardized | consistent | identifiable |
|---|---|---|---|---|
| 0.8 | +34.3 mV | +13.8 | **no** | yes |
| 0.2 | −38.5 mV | −11.1 | **no** | yes |
| 0.0 | −435.5 mV | −158.0 | **no** | yes |

No state of charge outside a calibration set was predicted consistently, by either design.

**Descriptive error map.** This is not an adequacy claim: no engineering tolerance was preregistered, and none is declared after the fact.

| where the chord is used | measured error |
|---|---|
| interpolation inside the calibrated span 0.2–0.8 | 11.5 – 13.2 mV |
| extrapolation from the plateau core to 0.2 / 0.8 | 34 – 39 mV |
| extrapolation to 0 % | 372 – 435 mV |

**Dimension supported:** SOC only, at 23 °C, one cell.

---

## 22. FIRST FAILURE REGION

**Everywhere outside the calibration points, at measurement precision.**

**First catastrophic failure (> 100 mV): below 20 % SOC, at the knee.**

- The chord calibrated on 0.2–0.8 misses 0 % by **372 mV**.
- At 0 % the rested cell had been discharged to the 2.0 V cutoff and was still recovering after 21.5 h.

**Order of failure as the chord moves away from where it was fitted:**

1. **plateau interpolation:** ~12 mV;
2. **plateau extrapolation:** ~35 mV;
3. **knee:** ~400 mV.

---

## 23. CLAIM VS CAPABILITY GAPS

**Claim cases the model cannot express, or that could not be tested:**

| # | gap | class |
|---|---|---|
| G1 | The affine chord cannot represent LiFePO4 plateau staging or the low-SOC knee (§19). | **D. MODEL-FORM LIMIT** (of the default chord configuration) |
| G2 | No validity condition bears on whether the OCV representation fits the cell; a 372 mV miss produces zero violations. | **B. REPRESENTATION LIMIT** (applicability coverage) |
| G3 | `DischargeLoad` requires strictly positive current, so a rested cell cannot be declared. B1 represents the conditioning discharge instead, and proves the compared value current-independent. | **B. REPRESENTATION LIMIT** |
| G4 | Declared OCV curve + declared voltage cutoff is refused: the cutoff→SOC inversion was never migrated off the chord. | **C. SOLVER LIMIT** |
| G5 | R_int, terminal voltage under load, coulomb counting, runtime, Peukert and self-heating cannot be validated: S-DCHG never records the discharge current, and its rate labels contradict its durations. | **E. DATA LIMIT** |
| G6 | Temperature dependence cannot be probed: one temperature (23 °C). | **E. DATA LIMIT** |
| G7 | One cell, one chemistry, 6 discharge-branch SOC levels. | **E. DATA LIMIT** |
| G8 | Hysteresis 7.0–9.6 mV at SOC 0.4–0.6 exceeds the expanded uncertainty (S4). It is excluded by the model and was not scored. | **D. MODEL-FORM LIMIT** (declared exclusion) |
| G9 | Relaxation lasts hours (0.6–23 h to settle); no RC branch. Excluded, and the polarization screen needs a caller-declared τ. | **D. MODEL-FORM LIMIT** (declared exclusion) |
| G10 | The frozen Core scores observations individually and has no study-level adequacy decision function. | **not a Core gap**: study policy, Sprint 8 precedent, preregistered here |
| — | anything requiring a generic Core capability | **F. CORE GAP CANDIDATE: none** |

**No parameterization limit (A) was found.** Two parameters were identifiable to 0.1–0.2 %, and the failure is not a lack of freedom.

---

## 24. MINIMUM NEXT BATTERY MODEL

**Proposed only because of the measured result. Not implemented in B1.**

**SOC-dependent OCV, through the domain's existing declared-curve representation.** No new model is needed.

- **Why:** the dominant residual is non-affine SOC dependence — staging at 12–38 mV and a knee at ~400 mV — on a representation that was identifiable and converged. The model already offers the fix, `open_circuit_voltage_curve`.
- **What B1 did not do:** calibrate or validate that curve route through the frozen Core pipeline.

**The minimum B2 work:**

1. **Calibrate and validate the declared-curve route** with the same protocol, preregistered split and adequacy rule.
   - Only 6 discharge-branch SOC levels exist, so held-out interpolation between 20 % steps is the test.
   - The earlier round's two-point check (residuals 3.4× and 7.7× U) suggests even a curve may not reach measurement precision on this plateau.
2. **Add an applicability condition** that can observe an OCV-representation mismatch (G2). What it bounds is a domain decision.
3. **Migrate the cutoff inversion onto declared curves** (G4), before any runtime claim rests on a curve.

**Not justified by the evidence:**

| candidate | why not now |
|---|---|
| SOC-dependent R | no measured current; R is untestable |
| temperature-dependent R | one temperature |
| one-RC circuit | relaxation is observed, but no loaded-voltage data exists to calibrate it |
| hysteresis term | 7–10 mV, second-order to the ~400 mV knee, and the model claims discharge only |

---

## 25. AI VERIFICATION DEMO SPEC

**Scientific contract only. No integration is built in B1.**

**Input — an AI proposal:**

- a battery cell declaration (chemistry, capacity, R, OCV as chord endpoints or curve);
- the parameters it marks free;
- a claimed prediction: OCV at stated SOCs with a claimed accuracy.

**Forge's steps, in order. Each step's refusal ends the run with a named outcome:**

1. **Declaration admission.** The battery domain refuses a non-cell: `V_full ≤ V_empty`, SOC ∉ [0, 1], a SOC reached by charging, or non-positive current.
   → `REJECT_INVALID_DECLARATION`
2. **Data admission.** Hash-pinned measured evidence with provenance, integrity-checked (§7). Missing required inputs (e.g. current for a terminal-voltage claim):
   → `INCONCLUSIVE_DATA_INSUFFICIENT`
3. **Applicability.** `assess_rint_validity`:
   - `OUTSIDE_VALIDATED_DOMAIN` → `REJECT_OUTSIDE_APPLICABILITY`
   - `UNKNOWN` is reported and is **never** acceptance.
4. **Preregistration.** Split by trace, sigma rule (A2), bounds and α fixed **before** any fit.
5. **Calibration** of the proposal's free parameters only, and only those the experiment can identify. R_int from OCV data is refused.
6. **Posterior and identifiability.**
   - `GridResolutionError` → `INCONCLUSIVE_UNRESOLVED` (never read as identifiable)
   - `NOT_IDENTIFIABLE` → `REJECT_NOT_IDENTIFIABLE`
7. **Predictive UQ.** Parameter and measurement uncertainty separated; `MODEL_DISCREPANCY_NOT_MODELLED` stated.
8. **Held-out adequacy.** Frozen per-observation scores; χ² at the preregistered α.

**Decision:**

| outcome | condition |
|---|---|
| **ACCEPT** | converged ∧ identifiable ∧ adequate ∧ not outside applicability |
| **REJECT_MODEL_INADEQUATE** | held-out χ² p < α |
| others | as named in steps 1–6 |

**Reason (required):** the per-point residuals, their structure, the tail probabilities, and the evidence digests, so the verdict can be re-derived.

**Forbidden to Forge:** accepting on calibration fit alone, widening noise, choosing α or tolerance after scoring, or treating UNKNOWN applicability as validity.

**B1 as the worked example:**

- **Proposal:** "a two-point chord predicts LiFePO4 OCV to 5 mV".
- **Outcome:** `REJECT_MODEL_INADEQUATE`.
- **Reason:** −372 mV at 0 %, and +13.2 / −11.5 mV on the plateau, at 149 / 12 / 8 σ, with opposite plateau signs ruling out a SOC-scale error.

---

## 26. BATTERY TESTS

| group | selection | result |
|---|---|---|
| Battery focused | `tests/domains/battery` + `tests/mcp/test_battery_boundary.py` + `tests/oracles/test_oracle_battery.py` | **284 passed** |
| Battery calibration adapter | `tests/domains/battery/test_battery_ocv_calibration.py` | **22 passed** |
| Calibration integration | `tests/inference/test_tcr_calibration.py` | **20 passed** |
| Held-out | `tests/inference/test_tcr_heldout_uq.py` | **16 passed** |
| UQ / adequacy integration | `tests/test_k3_predictive_uq.py` + `tests/test_k4_model_adequacy.py` | **13 passed** |
| Evidence integrity | `tests/test_evidence_pairing_integrity.py` + `tests/inference/test_reproducibility_and_evidence.py` | **40 passed** |
| B1 round guards | `benchmarks/battery_flagship_b1/tests` (re-derive the verdict from the raw file) | **13 passed** |
| FAST | `pytest tests -n 4 -m "not expensive and not campaign"` | **4925 passed, 5 skipped, 0 failed** |
| FULL | `pytest tests -n 4` | **5471 passed, 5 skipped, 0 failed** |

**What the adapter tests prove, beyond unit checks:**

- **Adversarial cases:** conditioning by charging, SOC outside [0, 1], zero current, a discharge that misses its target, a non-OCV observable, an unconditioned observation, and a non-cell candidate (refused, not scored).
- **Synthetic controls run the full frozen workflow:**
  - **A known chord:** CONVERGED + IDENTIFIABLE + **PASS**.
  - **A knee:** CONVERGED + IDENTIFIABLE + **FAIL**, at 0 %.

**Reconciling the counts:** FAST and FULL grew by 21 from Sprint 11. That is 22 new tests, plus one freeze test that now correctly **skips**: `test_on_the_exact_freeze_the_domain_digest_binds` applies only on the exact freeze, and this tree is a descendant.

### Found in passing, pre-existing, not B1's

`benchmarks/model_measurement_validation/tests::test_rebuilding_everything_reproduces_the_published_gates` fails, for two reasons:

- **The pin is stale.** Gate MV-10 pins a digest of `src/engcore/scientific` from Sprint 9 (`889d399`). That tree changed in Sprint 10 (`b843a07`). B1 does not touch it, so the failure is identical at `B1_BASELINE`.
- **The test mutates committed evidence.** Running it **rewrites the committed** `SAFETY_GATES.json`. It was restored with `git checkout`. The test has been corrupting its own committed evidence.

It went unnoticed because FAST and FULL collect `tests/` only. It is flagged as a separate task rather than fixed in a battery round.

---

## 27. CORE BYTES UNCHANGED

```
git diff f89a32a -- src/engcore/scientific src/engcore/data src/engcore/inference \
  src/engcore/uq src/engcore/adequacy src/engcore/execution src/engcore/studies \
  src/engcore/api_snapshot.py src/engcore/__init__.py src/engcore/domains/__init__.py \
  tests/api tools/certification certification pyproject.toml tests/mutation_guards.py \
  tests/test_core_guards.py tests/test_repair_guidance.py \
  tests/test_offset_unit_declaration.py tests/test_core_semantic_invariants.py
```

**→ empty.**

**The only `src/` change is the new file `src/engcore/domains/battery/calibration.py`.**

- No existing battery module was modified.
- `domains/__init__.py` (certified) was untouched.

---

## 28. CORE CERTIFICATE

`python -m tools.certification.core_certificate --verify` → **OK**

- **Certified commit:** `b32f67d`.
- **Aggregate digest:** `619f43f7…`.
- **Reissue:** not needed. Nothing in certified scope changed.

---

## 29. CORE FREEZE VERIFIER

`python -m tools.certification.core_freeze --verify` → **OK**, mode **DESCENDANT**.

**Binding contract checks, all passing (29 total):**

- frozen API digest `c80e6418…`, 194 frozen / 11 experimental symbols;
- the serialization inventory and legacy table;
- identity reference digests;
- ordering;
- the seven exception roots;
- experimental exclusions;
- certificate verification;
- pinned snapshot files;
- all assurance evidence.

**Informational, as the post-freeze policy requires:**

| check | why it no longer binds |
|---|---|
| domain digest `81bcc7f8…` → `930f4686…` | a domain file was added |
| certificate identity and package metadata | byte-level |
| reproduction digest | byte-level |
| post-candidate path list | applies only to the exact freeze commit |

**Core Freeze V1 contract: intact.**

---

## 30. FILES CHANGED

**8 files, all additions.**

| file | kind |
|---|---|
| `src/engcore/domains/battery/calibration.py` | domain adapter (new) |
| `tests/domains/battery/test_battery_ocv_calibration.py` | domain tests (new) |
| `benchmarks/battery_flagship_b1/PREREGISTRATION.json` | protocol, committed before any measured run |
| `benchmarks/battery_flagship_b1/audit/run_b1.py` | round harness |
| `benchmarks/battery_flagship_b1/DATA_INTEGRITY.json` | evidence |
| `benchmarks/battery_flagship_b1/RESULTS.json` | evidence |
| `benchmarks/battery_flagship_b1/SECONDARY.json` | evidence |
| `benchmarks/battery_flagship_b1/tests/test_battery_flagship_b1.py` | round guards |

This report is added in the commit that follows.

---

## 31. COMMITS

| | |
|---|---|
| `81aa5f7` | prereg(battery): B1 protocol, committed before any calibration on measured data |
| `2a260bf` | feat(battery): OCV inference adapter, proven on synthetic controls; prereg amendment A1 |
| `b6cd9a3` | prereg(battery): amendment A2 — no held-out value may weight the calibration likelihood |
| `0edaef8` | bench(battery): B1 measured result — CONVERGED + IDENTIFIABLE + MODEL INADEQUATE |
| *(this commit)* | docs(battery): the B1 round report |

**The order is the evidence:** the protocol and both amendments precede the first measured calibration.

---

## 32. PUSH RESULT

**Not recorded here.** A commit cannot record its own publication.

- **Branch:** `claude/battery-flagship-b1` is pushed after this commit.
- **Remote HEAD vs local HEAD:** checked against the server with `git ls-remote`.
- **Where the result lives:** the round's final response.

---

## 33. EXACT NEW DOMAIN CLAIM

> **Against measured 24-hour relaxed open-circuit voltages** of one LiFePO4 cell (BATT_001, Lithium Werks APR 18650; DOI 10.21227/651q-8v82, CC BY 4.0), `battery.cell.rint_ocv` behaves as follows.
>
> **Setup.** The model is configured with its default affine chord and calibrated through the frozen Core on the discharge-conditioned states of charge 20, 50 and 80 %. Every forward value is an admitted prediction from the production battery solver.
>
> **Calibration.** It converges, and its two chord parameters are identifiable to 0.13 % and 0.23 % (95 % relative width).
>
> **Held-out prediction.** It fails at 0, 40 and 60 % SOC, at a pre-declared α of 0.01 (χ² 2.23×10⁴, 3 df):
>
> - **at the knee:** −372 mV (−149σ);
> - **on the plateau:** +13.2 and −11.5 mV (+11.8σ, −7.6σ), in opposite directions, ruling out a SOC-scale error.
>
> **Plateau-core calibration** (40–60 %) fails every neighbouring state of charge as well.
>
> **Warning signal.** The model's own validity assessment reports no violated condition.
>
> **New capability.** The battery domain now has a calibration adapter, `engcore.domains.battery.calibration`. It admits the model's open-circuit voltage into the frozen calibration, posterior, predictive-UQ and adequacy workflow, and it has been shown, on synthetic controls, to reach both an adequate and an inadequate verdict.

---

## 34. WHAT BATTERY STILL CANNOT CLAIM

- **Terminal voltage under load:** no validated prediction, and no validated **R_int**.
- **Other models:** no validation of **coulomb counting**, **runtime to cutoff**, **Peukert derating** or **self-heating**. Every one needs a measured current, which no in-repo dataset records.
- **Declared OCV curve:** no validated prediction through the Core pipeline. The route exists and is untested by B1.
- **Temperature:** any temperature dependence. There is one temperature in the data.
- **Scope of the evidence:** any chemistry other than LiFePO4, any cell other than BATT_001, or any SOC not on the 20 % grid.
- **Excluded effects:** hysteresis, relaxation or polarization dynamics, charging, and ageing.
- **Engineering tolerance:** adequacy of the chord at any tolerance. None was preregistered, and none is declared after seeing the errors.
- **Wider claims:** that `battery.cell.rint_ocv` is inadequate for **other** cells or chemistries. A chemistry with a more nearly affine OCV would show a smaller miss, and this round has no measurement of one.
