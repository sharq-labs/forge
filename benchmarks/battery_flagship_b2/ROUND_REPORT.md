# Battery Flagship B2 — Existing SOC-Dependent OCV Model Validation

Branch `claude/battery-flagship-b2` · `B2_BASELINE = 6797668` (B1 head) · domain-first · Core frozen

```
python -X utf8 benchmarks/battery_flagship_b2/audit/run_b2.py
python -X utf8 -m pytest benchmarks/battery_flagship_b2/tests tests/domains/battery -q
```

## 1. Verdict

**BATTERY B2 BLOCKED — DATA LIMIT UNDER THE BINDING SPLIT**

The existing SOC-dependent OCV curve does not materially fix B1's failure.

- **Accuracy:** held-out RMSE improves by **1.23 %**.
- **Adequacy:** still inadequate.

The reason is structural, not a flaw in the curve implementation.

- **The data available:** the binding B1 split leaves three calibration SOC levels (20, 50, 80 %).
- **The smallest curve saturates them:** the smallest SOC-dependent existing curve has 3 parameters, so it uses all 3 levels and has zero residual degrees of freedom.
- **What the levels cannot show:** the flat 40–60 % plateau, or the knee below 20 %.
- **Richer curves don't help:** any richer existing curve is structurally unidentifiable from three levels (rank 3 of 5).

The verdict follows the mapping in `PREREGISTRATION.json`, which was committed before any measured B2 run.

- **Why not "improves":** that verdict would be false.
- **Why not "cannot support honest held-out validation":** also false. The validation *is* honest: no leakage, genuine predictions, and evidence identities identical to B1's.

## 2. The existing curve (Phase 1, read from code)

| aspect | fact |
|---|---|
| type | `engcore.scientific.models.curves.DeclaredCurve`, **frozen Core**, accepted by `CellSpecification.open_circuit_voltage_curve` |
| forms | `TabulatedForm` (samples + LINEAR or PREVIOUS interpolation; "measured curves arrive this way") · `PolynomialForm` (ascending coefficients about a reference; "fitted correlations arrive this way") · `PiecewiseForm` (polynomial pieces over breakpoints, continuity not required) |
| knots | strictly ascending (SOC, V) samples; a tabulated interval may not reach past its samples |
| units | against `state_of_charge` in dimensionless, value in volt |
| extrapolation | **none**: outside [lower, upper] evaluation returns `OUTSIDE_VALIDATED_DOMAIN` and no value |
| cell integration | the endpoints are derived **from** the curve at z = 0 and z = 1; a curve that cannot answer at both is refused |
| serialization | primitives, round-trips; the fingerprint (minus source and description) enters `physical_key` |
| solver | `evaluate_step` evaluates OCV(z_end) on the curve |
| voltage cutoff | the solver **refuses** curve + cutoff; that refusal is pinned by a **certified** harness test |
| validity path | **before B2:** silently inverted the chord of the curve's endpoints |
| applicability | the same 11 conditions as the chord; none reads the curve or any measurement |

## 3. Claim boundary (Phase 2)

**What it claims:** OCV is a declared tabulated or fitted function of SOC over its declared interval, inside an Rint circuit with one constant R_int.

**Not claimed:**

- a LiFePO4 electrochemical model;
- hysteresis;
- RC polarization;
- temperature dependence;
- ageing;
- relaxation dynamics;
- rate dependence;
- charging;
- anything outside the declared interval.

## 4. Same data (Phase 3)

The data is identical to B1's:

- **file:** `9b8c5416…`
- **cell:** BATT_001
- **branch:** `24h_Discharge_APR`
- **split:** calibration {0.2, 0.5, 0.8}, held-out {0.0, 0.4, 0.6}
- **uncertainty:** the A2 sigma rule
- **decision:** α 0.01, credible mass 0.95

The **held-out evidence identity digests are byte-identical to B1's** at all three points, so the model changed and the evidence did not.

## 5. Parameterization and flexibility (Phases 4, 9)

| run | form | free p | calibration n | p/n | residual dof |
|---|---|---|---|---|---|
| B1 chord (control) | affine chord | 2 | 3 | 0.67 | 1 |
| **B2-POLY2 (primary)** | `PolynomialForm` degree 2 over [0, 1], voltages at declared nodes {0, 0.5, 1} | **3** | **3** | **1.0** | **0** |
| B2-TAB3 (secondary) | `TabulatedForm` LINEAR, knots {0, 0.5, 1} | 3 | 3 | 1.0 | 0 |
| B2-TAB5 (guard) | `TabulatedForm` LINEAR, knots {0, 0.25, 0.5, 0.75, 1} | 5 | 3 | 1.67 | −2 |

**Nesting.** A degree-1 curve through nodes {0, 1} **is** the B1 chord, to 1e-12, so B2 nests B1.

**Declared positions.** Nodes and knots are declared, never measured. 0.5 coincides with a calibration SOC, and that is disclosed.

**Zero residual dof.** B2-POLY2's calibration residuals are **zero by construction**. That is recorded as *no internal check* and never read as validity.

**Flexibility guard (B2-TAB5).**

- **Rank:** the Jacobian from knot voltages to calibration predictions has rank **3 of 5** (singular values 1.0, 0.82, 0.82), leaving a 2-dimensional null space.
- **Convergence is not identifiability:** the frozen `calibrate` still **converges**, at χ² 1e-9, on arbitrary knot voltages.
- **Held-out:** it is not scored, because an unidentified fit has no prediction to score.

**Measured-map semantics.** A tabulated curve whose samples *are* the measurements is **not testable** under this split. `CellSpecification` needs the curve at z = 0, which is held out, and at z = 1, which was never measured on the discharge branch.

## 6. No leakage (Phase 5)

- **Split disjointness:** calibration and held-out are disjoint by identity and by content digest, through the frozen `ObservationSplit`.
- **Calibration sigmas:** computed from calibration traces only.
- **Everything else:** no held-out value enters knots, nodes, initialization, grid centre or priors.

## 7. Synthetic controls (Phase 6) — before measured data

| control | result |
|---|---|
| truth from B2-POLY2 itself + 2 mV noise | CONVERGED + IDENTIFIABLE + **PASS** |
| knee + plateau step | CONVERGED + IDENTIFIABLE + **FAIL**, worst at 0 % |

## 8. Calibration and identifiability (Phases 8, 9)

| | B2-POLY2 | B2-TAB3 |
|---|---|---|
| status | CALIBRATION_CONVERGED (gtol), 5 evaluations | CONVERGED (gtol), 5 evaluations |
| estimates at z = 0 / 0.5 / 1 (V) | 3.21517 / 3.29200 / 3.35383 | 3.21817 / 3.29200 / 3.35683 |
| vs closed form | 7e-14 V | 7e-14 V |
| objective χ² | 0 (dof 0) | 7.6e-26 (dof 0) |
| bounds / initial | [2.0, 3.6] V / 3.2, 3.3, 3.4 V | same |
| posterior σ (mV) | 2.59 / 1.12 / 4.10 | 1.29 / 1.12 / 2.78 |
| identifiability | **IDENTIFIABLE**: cond 49.5, \|r\| 0.77, 95 % widths 0.14–0.49 % | IDENTIFIABLE: cond 13.6, \|r\| 0.58 |
| grid | 25³ = 15 625 points, 0 rejected, ESS 158, step 0.5 σ | ESS 280, step 0.5 σ |

**Sensitivity check (preregistered).** The same fitted polynomial, expressed through its **coefficients** (3.2152, 0.1687, −0.0300 V):

- **Curvature interval:** its 95 % interval is **2.05×** the curvature coefficient's own magnitude.
- **Classification:** the frozen width rule would then call it **NOT_IDENTIFIABLE**.

The identifiability verdict therefore depends on parameterization. That is why the primary uses volt-valued node parameters, chosen and stated before the run.

## 9. Held-out prediction (Phase 10) and direct comparison (Phase 11)

| SOC | observed | B2 mean | B2 error | B2 z | B2 95 % total interval | B1 error |
|---|---|---|---|---|---|---|
| 0.0 | 2.8473 V | 3.2152 V | **−367.9 mV** | −106.2 | [3.2084, 3.2220] | −372.4 mV |
| 0.4 | 3.2894 V | 3.2778 V | **+11.6 mV** | +8.2 | [3.2751, 3.2806] | +13.2 mV |
| 0.6 | 3.2929 V | 3.3056 V | **−12.7 mV** | −7.8 | [3.3024, 3.3087] | −11.5 mV |

| metric | linear chord B1 | SOC curve B2 | improvement |
|---|---|---|---|
| RMSE | 215.27 mV | 212.62 mV | **1.23 %** |
| MAE | 132.39 mV | 130.70 mV | 1.28 % |
| max \|error\| | 372.44 mV | 367.87 mV | 1.23 % |
| coverage (95 %) | 0/3 | 0/3 | none |
| χ² (3 df) | 2.227e4 | 1.142e4 | 48.7 % — *see note* |
| free parameters | 2 | 3 | +1 |
| residual dof | 1 | 0 | −1 |
| identifiability | IDENTIFIABLE | IDENTIFIABLE | — |
| adequacy | INADEQUATE | INADEQUATE | — |

**Note on χ².** χ² fell 49 % while RMSE fell 1.2 %. That is **wider predictive uncertainty, not better prediction**. The extra parameter raises the parameter σ at the extrapolated 0 % point from 0.99 to 2.59 mV, so the same miss is divided by a larger σ.

**Other metrics:**

- **Mean log predictive density:** −3923 (B1: −4254).
- **Model discrepancy:** `MODEL_DISCREPANCY_NOT_MODELLED`.

## 10. Residual structure

| SOC | 0.0 | 0.2 | 0.4 | 0.5 | 0.6 | 0.8 |
|---|---|---|---|---|---|---|
| partition | held | cal | held | cal | held | cal |
| B2 residual (mV) | −367.9 | 0.0 | +11.6 | 0.0 | −12.7 | 0.0 |
| B1 residual (mV) | −372.4 | −0.3 | +13.2 | +1.7 | −11.5 | −1.8 |

**Same shape as B1:**

- The plateau misses have **opposite** signs at 0.4 and 0.6, which rules out a SOC-scale error. The curve still cannot see that 0.4–0.6 is flat.
- The knee at 0 % dominates by 30×.

**Calibration residuals are zero by construction** (0 dof), not by merit.

## 11. Validity condition (Phase 12)

`engcore.domains.battery.empirical.assess_ocv_empirical_adequacy`. It is a separate assessment beside `assess_rint_validity`, not a new RangeCondition on the model record.

**Why separate:** a new condition would have turned every existing IN_DOMAIN verdict without measured OCV into UNKNOWN, including the 400 pinned benchmark cases.

**Two statuses, never merged:**

- **MODEL_APPLICABLE:** existing applicability. It is recorded in the assessment and never consulted.
- **MODEL_EMPIRICALLY_ADEQUATE:** χ² of (measured − declared)/u, n dof, α 0.01 (B1's rule).

**Never adequate:**

- **`NO_MEASURED_EVIDENCE`:** there is nothing to score.
- **`EVIDENCE_OUTSIDE_CLAIM`:** charge-conditioned OCV is set aside, with its reason.

**Refused inputs:** a point without provenance or a positive finite uncertainty.

**Scoring a curve cell:** on the curve, never on the chord of its ends.

**Applied to BATT_001 held-out:**

| cell | applicability | violated conditions | empirical |
|---|---|---|---|
| B1 chord | unknown | **none** | **MODEL_EMPIRICALLY_INADEQUATE** (χ² 2.64e4, worst −372 mV) |
| B2 curve | unknown | **none** | **MODEL_EMPIRICALLY_INADEQUATE** (χ² 2.58e4, worst −368 mV) |

B1's gap is closed: a cell with zero violated conditions is now **reported** empirically inadequate.

## 12. Voltage cutoff with curves (Phase 13)

`context.voltage_cutoff_state_of_charge_on_curve` uses the chord's physical semantics, the SOC at which OCV(z) − I·R reaches the cutoff, applied on the declared curve.

**Linear tables:** exact segment inversion.

**Polynomial or piecewise curves:** deterministic 200-step bisection, after a 2049-point monotonicity check.

**Target outside the curve's span:** `OUTSIDE_VALIDATED_DOMAIN`, with no chord extrapolation.

**Refused, with a reason:**

- a PREVIOUS (step) table;
- a non-increasing table;
- a non-monotone curve;
- a discontinuity jumping over the target (root residual above 1e-9 V).

**Chord equivalence:** a degree-1 curve reproduces the chord inversion to 1e-12.

**Wired into the validity derivations.** A curve cell's two cutoff conditions now read the curve. The old fallback gave the **wrong verdict** on a knee:

- **Chord:** cutoff at z = 0.7, so it reported VIOLATED.
- **Curve:** cutoff at z = 0.1, so SATISFIED.

**A declared cutoff the curve cannot locate withholds both conditions.** The test caught reachability being satisfied from the SOC cutoff alone.

**Solver refusal unchanged.** `solver._binding_cutoff` still refuses curve + cutoff. Its refusal is pinned by the certified `test_the_unmigrated_inversion_refuses_rather_than_answering_from_the_chord`; changing it needs certification review, which a frozen Core does not allow.

**Applied to the dataset's 2.0 V cutoff at 0.22 A:**

- **B1 chord:** answers SOC **−8.62**, a number with no physical meaning.
- **B2 curve:** refuses with **OUTSIDE_VALIDATED_DOMAIN**. The calibrated curve spans only 3.215–3.354 V, because it has no knee.

## 13. Hysteresis (Phase 14)

Measured only; no model was added.

| SOC | charge − discharge | B2 residual | ratio |
|---|---|---|---|
| 0.2 | +1.3 mV | 0 (cal) | — |
| 0.4 | **+9.6 mV** | +11.6 mV | **0.83** |
| 0.5 | +7.0 mV | 0 (cal) | — |
| 0.6 | **+9.1 mV** | −12.7 mV | **0.72** |
| 0.8 | +2.1 mV | 0 (cal) | — |

**Dependence on SOC:** the hysteresis is largest mid-plateau (7–9.6 mV) and small near 20 % and 80 % (1–2 mV).

**Size relative to the residuals:**

- **Plateau:** it is **not small**, at 72–83 % of the B2 residual magnitude.
- **Knee:** it is **under 3 %** of the 368 mV miss.

**Decision:** hysteresis is not the next justified addition while the knee is unresolved. Any plateau-precision claim will eventually need it.

## 14. Generalization (Phase 15)

BATT_002 (BSE 18650 LiFePO4, 1500 mAh), discharge branch SOC {0, 0.5, 0.6}. It was scored with BATT_001's parameters unchanged and BATT_002's own measurement budget.

| cell model | 0 % | 50 % | 60 % | empirical |
|---|---|---|---|---|
| B1 chord | −225.7 mV | +3.7 mV | −8.4 mV | INADEQUATE |
| B2 curve | −221.2 mV | +2.0 mV | −9.6 mV | INADEQUATE |

**Neither representation transfers.** The plateau lands within 2–10 mV; the knee misses by more than 220 mV.

**Other chemistries (BATT_003–008): DATA_LIMIT.** They carry only 0 % and 100 % OCV, and a LiFePO4 curve makes no claim about them.

## 15. Core freeze proof (Phase 16)

| check | result |
|---|---|
| frozen Core paths changed vs `6797668` and vs `v1.0-core-freeze` | **0** |
| `python -m tools.certification.core_certificate --verify` | **OK** |
| `python -m tools.certification.core_freeze --verify` | **OK**, DESCENDANT |
| B1 artifacts changed | **none** |

## 16. Tests (Phase 17)

| group | result |
|---|---|
| battery focused (`tests/domains/battery` + MCP boundary + oracle) | 335 passed |
| B1 regression (adapter + round guards) | 35 passed |
| B2 curve (controls + round guards) | 34 passed |
| cutoff with curves | 21 passed |
| empirical adequacy | 11 passed |
| calibration integration | 20 passed |
| held-out | 16 passed |
| UQ + adequacy | 13 passed |
| evidence integrity | 40 passed |
| certified harness suites | 470 passed (the certified curve + cutoff refusal intact) |
| **FAST** | **4976 passed**, 5 skipped, 0 failed |
| **FULL** | **5522 passed**, 5 skipped, 0 failed |

**Count check:** +51 tests since B1 (19 curve + 21 cutoff + 11 empirical).

**Excluded:** `benchmarks/model_measurement_validation/tests`. Its stale digest predates B1 (Sprint 10), and running it rewrites committed evidence. It remains separate maintenance debt, and the working tree was confirmed clean after every group.

## 17. Files changed

**12 files.** No frozen Core file is among them.

- **`src/engcore/domains/battery/`**
  - `calibration.py`: curve parameterizations and one shared admission path.
  - `context.py`: curve cutoff inversion, wired into validity.
  - `empirical.py`: new.
- **`tests/domains/battery/`**
  - `test_battery_ocv_curve_calibration.py`
  - `test_battery_ocv_curve_cutoff.py`
  - `test_battery_ocv_empirical.py`
- **`benchmarks/battery_flagship_b2/`**
  - `PREREGISTRATION.json`
  - `audit/run_b2.py`
  - `RESULTS.json`
  - `COMPARISON.json`
  - `SECONDARY.json`
  - `tests/`
  - this report

## 18. Commits

| | |
|---|---|
| `02bcb0b` | prereg: B2 protocol, before any measured B2 run |
| `06204b0` | calibrate the existing OCV curve through the frozen Core; synthetic controls |
| `2213a7b` | cutoff validity conditions invert the declared curve, never its chord |
| `9024f9a` | empirical OCV adequacy, separate from applicability |
| `5bc1b1e` | B2 measured result |
| *(this commit)* | round report |

## 19. Exact new battery claim

> **Setup.** On the same measured 24 h relaxed OCV of BATT_001 (LiFePO4, DOI 10.21227/651q-8v82), under B1's binding protocol, `battery.cell.rint_ocv` was run with its existing SOC-dependent OCV curve: a degree-2 `PolynomialForm`, calibrated through the frozen Core.
>
> **Calibration.** It converges and is identifiable, with 0 residual degrees of freedom.
>
> **Held-out prediction.**
> - RMSE 212.6 mV, a **1.23 %** improvement on the affine chord;
> - misses of −367.9 mV at 0 % SOC, and +11.6 and −12.7 mV at 40 and 60 %;
> - still inadequate at α 0.01.
>
> **Why no richer curve helps.** A curve with more than three free voltages is structurally unidentifiable from the three calibration levels.
>
> **New domain capabilities, beyond the result:**
> - an empirical OCV-adequacy assessment that reports **MODEL_EMPIRICALLY_INADEQUATE** where applicability reports no violation;
> - voltage-cutoff validity conditions that invert a declared curve and refuse rather than fall back to the chord.

## 20. What still cannot be claimed

- **Knee or plateau under this split:** that any existing OCV curve predicts this cell's knee or plateau. The split gives it no information about either.
- **A curve fitted to all six SOC levels:** that it would be adequate. It was not tested, because that would dissolve the held-out set.
- **Runtime to a voltage cutoff:** any prediction on a curve cell. The solver refusal is certified and unchanged.
- **Unmeasured models and quantities:** R_int, terminal voltage under load, coulomb counting, runtime and Peukert. No measured current exists.
- **Excluded physics:** hysteresis, relaxation dynamics, temperature, rate or ageing.
- **Generalization:** to BATT_002 (fails at the knee) or to any other chemistry (DATA_LIMIT).
- **Parameterization-independent identifiability:** the coefficient form of the same fit is NOT_IDENTIFIABLE.
