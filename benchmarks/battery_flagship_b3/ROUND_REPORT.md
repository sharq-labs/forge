# Battery Flagship B3 — Richer Real-Data Acquisition & Honest OCV Revalidation

Branch `claude/battery-flagship-b3` · `B3_BASELINE = ae9d794` (B2 head) · domain / evidence work · Core frozen

```
python -X utf8 benchmarks/battery_flagship_b3/audit/prepare_b3.py          # Phases 6-9 (deterministic, digest-pinned)
python -X utf8 benchmarks/battery_flagship_b3/audit/run_b3.py --controls   # synthetic controls
python -X utf8 benchmarks/battery_flagship_b3/audit/run_b3.py              # the measured round (~15 min, 12 workers)
python -X utf8 -m pytest benchmarks/battery_flagship_b3/tests -q
```

## 1. FINAL VERDICT

**BATTERY B3 COMPLETE — EXISTING OCV CURVE EMPIRICALLY ADEQUATE**

This is the preregistered mapping (A) applied to the preregistered protocol. It holds with the scope and qualifications below, and none of them is optional.

**The adequate model.**

- **What it is:** an existing `TabulatedForm` (LINEAR, 41 declared knots, T41), calibrated through the frozen `calibrate` on 67 observations.
- **How it was chosen:** by cross-validation on calibration data, never by held-out error.
- **Held-out result:** it predicts all 33 held-out discharge-conditioned observations adequately, both globally and in every SOC region, including the knee.
- **Robustness:** it stays adequate at every rung of the preregistered relaxation-allowance ladder, from 0 to 50 mV.

**Scope.** The claim covers an **interrupt-relaxed pseudo-OCV**:

- one A123 18650M1A cell, at 25 °C, discharge-conditioned;
- the rest after each interrupt is **undocumented**;
- it is interpolated at 1 % SOC resolution.

It is never the cell's equilibrium OCV, and never another cell.

**The chord and degree-2 forms are still inadequate on this data.** The B1 chord form (P1) misses by 67.6 mV RMSE, and the B2 degree-2 form (P2) by 55.4 mV RMSE. The better B3 number comes from **data**, not from those forms.

> **CORE_GAP_CANDIDATE — no non-grid posterior / identifiability / predictive-UQ path in `engcore.inference` for models with more than ~5 free parameters.**
>
> **What is not Core-certified.** T41's identifiability status and predictive intervals come from the preregistered `DOMAIN_LINEAR_GAUSSIAN` route. That route is an exact Gaussian posterior for a model that is affine in its parameters, with the frozen identifiability thresholds applied, and it lives in the benchmark harness, not in the Core.
>
> **Why it was accepted.** The route may carry a claim only because it reproduced the frozen Core grid on all six models both could run. The worst deviation was 2.4e-11 posterior sd in means and 1.6e-5 relative in predictive sd.
>
> **What still needs no grid:**
> - calibration, done through the frozen `calibrate`;
> - the rank gate;
> - the Battery-domain `assess_ocv_empirical_adequacy`, which on its own also returns `MODEL_EMPIRICALLY_ADEQUATE` for T41 (χ² 2.80 on 33).
>
> **If domain-side UQ is not acceptable as evidence:** no Core-certified model (p ≤ 5) is adequate in every region. T5, the best of them, is adequate globally but fails the knee. The Core was **not** modified.

## 2. B3 BASELINE

`B3_BASELINE = ae9d79458846e3d1bdb314a57132bf538b14ff84`

At the start, both of these returned **OK**:

- `core_certificate --verify`
- `core_freeze --verify`, in DESCENDANT mode

## 3. DATA SEARCH

**Repository (Phase 1).**

- **Method:** every tracked data file by type was listed, and every tracked JSON/YAML/header file was grepped for OCV, SOC, LiFePO4, LFP and battery content. Untracked and ignored paths were listed too.
- **Real measured OCV:** the only such evidence is S-OCV, which has at most **6 SOC levels per branch**. That is B1/B2's data, and it is insufficient.
- **Everything else:**
  - loaded terminal voltage with no recorded current (S-DCHG);
  - synthetic (hard benchmark, empirical-validation fixtures);
  - reference-only (blind oracles, equation ledgers).

**External (Phase 3).** Unlike Sprint 10's environment, zenodo.org, data.mendeley.com, calce.umd.edu and springer static content are reachable here. Candidates were retrieved and their raw files inspected where a claim depended on them. Full record: `DATA_SELECTION.json`, committed as `467b706` **before any model touched external data**.

## 4. DATASET CANDIDATES

| Dataset | Real measured | Provenance | License | SOC count (one branch) | Knee (<10 %) | Plateau | Temp known | Suitable |
|---|---|---|---|---|---|---|---|---|
| S-OCV BATT_001 (in repo) | yes | DOI + paper | CC BY 4.0 | 6 | 1 | 3 | 23 ± 2 °C | **no** — too few levels |
| S-DCHG (in repo) | derived | DOI | CC BY 4.0 | continuous | — | — | yes | **no** — loaded, current unknown |
| **Jahn 2024 A123 incrOCV** | yes (16-bit codes) | DOI + peer-reviewed paper + Univ. Bayreuth | **CC BY 4.0** | **100 dis / 101 chg** | **10 / 11** | **30 / 29** | **25 °C chamber** | **yes — rest undocumented (disclosed)** |
| Jahn 2024 pOCV | yes | same | CC BY 4.0 | continuous | yes | yes | 25 °C | no — loaded C/20; used only as a Phase 7 ordering check |
| Bath LIC 280 Ah (10.5281/zenodo.20813753) | yes | DOI + Univ. Bath | CC BY 4.0 | 10 | 1 | yes | 15–35 °C | no — knee coverage, 15-min rests (measured from raw current) |
| UCCS A123 26650 (10.17632/p8kf893yv3.1) | yes | DOI + UCCS | CC BY 4.0 | continuous | yes | yes | −25…45 °C | no — raw Arbin files show a continuous ~C/30 current, loaded |
| CALCE A123 / SP | yes | institution | **none** (citation request) | 10 % steps or continuous | — | — | yes | no — license; derived/interpolated or loaded; SP not LFP |
| Braun & Bessler | derived curve | DOI | CC BY-NC 4.0 | — | — | — | — | no |
| Windsor Samsung 30T | yes | DOI | CC BY 4.0 | — | — | — | — | no — not LFP |

## 5. SELECTED DATASET

**The discharge-conditioned branch of `20230125_Hys_A123_01_25deg_incrOCV.csv`**, described in its record as a *"Full cycle with current interupts at specific states of charge"*.

**Why this one:**

- It is the only candidate that is real, raw, openly licensed, LFP, temperature-controlled and branch-separable.
- It is rich enough to preregister a split that holds out ≥ 2 knee, ≥ 2 plateau and ≥ 1 transition points while still calibrating every region.
- It is the **same cell model** as BATT_001, measured by an independent laboratory.

## 6. SOURCE / DOI

**Dataset:** Jahn, L. — *Probability distributed equivalent circuit model – Data*, **10.5281/zenodo.10852930**.

- **Which version:** 10.5281/zenodo.10852930 is the version the paper's Data availability statement cites; the concept DOI is 10.5281/zenodo.10852929.
- **Where the bytes came from:** version 10.5281/zenodo.11958572, whose files are byte-identical (same MD5).

**Paper:** Jahn, Mössle, Röder, Danzer, *A physically motivated voltage hysteresis model for lithium-ion batteries using a probability distributed equivalent circuit*, Communications Engineering 3, 74 (2024), doi:10.1038/s44172-024-00221-4.

## 7. LICENSE

**CC BY 4.0** covers both the dataset and the article.

- **Attribution:** given in `evidence/PROVENANCE.json` and here.
- **Changes to the vendored bytes:** none.

## 8. RAW FILE HASH

| file | bytes | SHA-256 | Zenodo MD5 |
|---|---|---|---|
| `…_incrOCV.csv` (primary) | 7 242 | `25c318255e1f4203842ec6780b9adbcbbc12a23461c0fb618be2da51480b9704` | `196f0ca0…` ✔ |
| `…_pOCV.csv` | 691 936 | `da6e14f79fe0e16d528780f6a5bacf725778c1390593d689bc6ad54a7517bda0` | `62dbf637…` ✔ |
| `…_HysPowerTest_…_SOC50.csv` | 20 988 | `d6e8b4b7ea4f832a67a859604ab8d507d2a1fdd7541cb37a485ac933dec92fd3` | `e043115d…` ✔ |
| `…_HysPowerTest_…_SOC100.csv` | 47 380 | `009c2fb085e219c7b20afaa050ac9e69d848cf04fc6e9165ce2bbd1282357feb` | `588ecca6…` ✔ |

**Acquisition:** HTTPS from the Zenodo file endpoint on **2026-09-13**, committed as `f0f1b09`.

**Line endings are preserved.** The primary file is **CRLF**, and the repository-wide `eol=lf` would have rewritten it. `evidence/raw/.gitattributes` therefore sets `-text`. The committed index blobs hash identically to the downloads.

**Derived artifacts** (`OBSERVATIONS.json`, `DATA_QUALITY.json`) name the raw SHA-256. Their own digests are pinned in the preregistration and re-derived by a test **without rewriting committed files**.

## 9. CHEMISTRY

LiFePO4 cathode / graphite anode. Source: the paper's Methods.

## 10. CELL(S)

**One cell:** A123 18650M1A, label `A123_01`.

| quantity | value |
|---|---|
| nominal capacity | 1.1 Ah |
| capacity reached at the top of this test | Q_top = 1.006218 Ah |
| capacity reached at the top of the C/20 test | 1.018902 Ah |

## 11. TEMPERATURE

**25 °C**, Binder MK115 climate chamber (paper Methods; file name).

The file has **no temperature channel**, so temperature consistency is UNVERIFIABLE.

## 12. VOLTAGE MEASUREMENT MEANING

**Interrupt-relaxed voltage after a rest of UNDOCUMENTED duration: a pseudo-OCV.**

- It is **not** loaded terminal voltage. The record says "current interrupts", and the branch lies on the relaxed side of the C/20 loaded discharge curve at 90/90 compared points (charge branch: 89/89).
- It is **not** called equilibrium OCV.
- The rest duration, the step current and the sampled point of the rest were searched for and are not documented anywhere retrievable. The places searched were:
  - the paper and its Supplementary Information;
  - the Peer Review File;
  - both data records;
  - the authors' code record, read as text. **No script reads this file.**

**The two branches stay separate:**

- **Discharge branch** (rows 102–201): the primary data.
- **Charge branch** (rows 0–100): hysteresis only.
- **Row 101:** duplicates row 100 character for character. It belongs to the charge branch and is **not** a discharge observation.

## 13. TOTAL SOC OBSERVATIONS

**100 discharge-conditioned** observations, z = Q/Q_top from 0.0017 to 0.9900, at about 1 % steps. There are also 101 charge-conditioned observations, which are out of claim.

**Phase 7 audit (`DATA_QUALITY.json`).** 0 failures, 2 anomalies, 2 unverifiable; nothing was cleaned.

**Anomalies:**

- **the duplicated top row;**
- **a metadata contradiction:** the record calls the power tests "C/2", but their raw current is ±1.10 A = 1C. The paper calls the fast discharge "3C"; the data show 4.4 A = 4C. These files are used only for their rest lengths.

**Unverifiable:** temperature and rest timing.

**Other checks:** every voltage is an integer multiple of 190.88 µV (a 16-bit code), there are no gaps, both branches are monotone, and charge − discharge > 0 at 100/100 points.

## 14. CALIBRATION SPLIT

**67 observations.**

- **Rule (preregistered in `8a5a8a4`):** order by ascending z, then hold out index i where i % 3 == 1. The rule is deterministic and not random.
- **Per region:** KNEE 7, LOW-SOC 20, PLATEAU 20, HIGH-SOC 20.

## 15. HELD-OUT SPLIT

**33 observations:** KNEE 3, LOW-SOC TRANSITION 10, PLATEAU 10, HIGH-SOC TRANSITION 10.

**Leakage proof:** calibration ∩ held-out = ∅, both by `ObservationSplit` identity and by `observation_content_digest`.

**No held-out voltage enters:**

- any sigma (a test moves every held-out voltage by +0.5 V, and all 100 budgets stay identical);
- any knot or node position, which are declared constants;
- the initial point (`linspace(3.0, 3.4, p)`);
- the grid centre, which is a calibration-only weighted least-squares fit;
- the CV folds;
- model selection.

**T-CAL** (knots at every calibration z plus 0 and 1, p = 69 ≥ n_cal = 67) is refused by the gate and never scored.

## 16. KNEE COVERAGE

**Held-out knee points:** z = 0.0117, 0.0416 and 0.0716, each bracketed by calibration points.

**What this does and does not test:**

- **It tests interpolation inside the knee** at 1 % resolution.
- **It does not test extrapolation beyond the measured range**, which is what B1/B2's 368 mV miss at 0 % was.

## 17. PLATEAU COVERAGE

**10 held-out plateau points**, z between 0.40 and 0.70, plus 20 calibration points.

## 18. UNCERTAINTY MODEL

Fixed and committed before any fit; never widened. It is a root-sum-square per observation (`OBSERVATIONS.json` lists every term):

| term | value | source |
|---|---|---|
| acquisition | 0.577 mV | BaSyTec CTS 1 mV accuracy, rectangular. The manufacturer PDF returns 404; the figure is from the distributor's spec table, and the 16-bit resolution is corroborated by the data |
| quantisation | 0.055 mV | measured 190.88 µV code step / √12 |
| temperature | 0.4 mV | 0.2 mV/K × 2 K (B1's generous entropic figure; chamber band declared) |
| state of charge | 0.02–26 mV | \|dV/dz\| from **calibration neighbours only** × 0.33 %/√3 (vendor worst-case relative accuracy; conservative because z is a ratio of the same counter) |
| relaxation allowance | **10.3 mV** | median of BATT_001's **measured** V(24 h) − V(10 min) at its five interior discharge levels {19.2, 12.1, 8.0, 8.4, 10.3} mV (same cell model). 10 min is the only rest length documented in this record's time series |

**Combined:** 10.3 mV on the plateau, up to 28.0 mV at the steepest held-out knee point.

**Preregistered ladder:** relaxation allowance ∈ {0, 2, 5, 10.3, 20, 50} mV. Only the primary rung carries the verdict; the others measure its robustness.

**Known limits:**

- incomplete relaxation is a smooth bias in reality, but is modelled here as independent noise;
- knee-interior relaxation is unknown;
- no replicate spread exists.

## 19. MODEL REPRESENTATIONS

**Existing forms only**, from `engcore.domains.battery.calibration`:

- `PolynomialNodeParameterization`, degrees 1, 2, 3, 4, 5, 7, 9 (P1–P9), with nodes at equispaced declared positions;
- `TabulatedKnotParameterization` LINEAR:
  - T3 {0, .5, 1};
  - T5 {0, .1, .4, .7, 1};
  - T6 {0, .05, .1, .4, .7, 1};
  - T11, T21, T41 uniform.

**Nesting:** P1 is the B1 chord; P2 and T3 are B2's forms.

**Not added:** no hysteresis, RC, temperature, relaxation, ageing or new interpolation.

**No battery model file changed.**

**Two routes:**

- **`CORE_GRID`** (p ≤ 5: P1–P4, T3, T5): the frozen grid posterior, `assess_identifiability`, `posterior_predictive_uq` and `assess_predictive_observation`, over an `AdmittedForwardTable` of production-solver predictions.
  - **Grids:** 41², 25³, 13⁴, 9⁵.
  - **Rejected rows:** 0.
  - **Posterior resolution:** ESS 119–644; spacing/sd ≤ 1.0.
- **`DOMAIN_LINEAR_GAUSSIAN`** (p ≥ 6): exact for these forms, which a test shows are affine in their voltages through the production solver to < 1e-12 V.

## 20. PARAMETER COUNTS

| model | P1 | P2 | P3 | P4 | P5 | P7 | P9 | T3 | T5 | T6 | T11 | T21 | **T41** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 3 | 5 | 6 | 11 | 21 | **41** |

## 21. RESIDUAL DOF

n_cal = 67 for every model.

| model | P1 | P2 | P3 | P4 | P5 | P7 | P9 | T3 | T5 | T6 | T11 | T21 | **T41** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| residual dof | 65 | 64 | 63 | 62 | 61 | 59 | 57 | 64 | 62 | 61 | 56 | 46 | **26** |

**Every model making an empirical claim has positive residual dof.** This contrasts with B2-POLY2, which had 0.

## 22. IDENTIFIABILITY

**Gate:** p < n_cal, rank(J) = p, and status IDENTIFIABLE. **All 13 scored models pass it.** Convergence was never taken as identifiability.

| model | rank | weighted-J cond | posterior cov cond | max \|r\| | widest 95 % rel. width | route |
|---|---|---|---|---|---|---|
| P1 | 2 | 1.8 | 3.2 | 0.53 | 0.0036 | Core grid |
| P2 | 3 | 2.9 | 8.5 | 0.37 | 0.0057 | Core grid |
| P3 | 4 | 3.6 | 13 | 0.39 | 0.0085 | Core grid |
| P4 | 5 | 4.7 | 22 | 0.41 | 0.0117 | Core grid |
| T3 | 3 | 2.1 | 4.3 | 0.41 | 0.0049 | Core grid |
| T5 | 5 | 4.3 | 19 | 0.37 | 0.0151 | Core grid |
| P5 / P7 / P9 | 6 / 8 / 10 | 6.2 / 12 / 26 | 38 / 138 / 687 | ≤ 0.39 | ≤ 0.024 | domain |
| T6 / T11 / T21 | 6 / 11 / 21 | 6.2 / 2.8 / 2.7 | 38 / 7.7 / 7.3 | ≤ 0.37 | ≤ 0.022 | domain |
| **T41** | **41** | **3.1** | **9.5** | **0.66** | **0.026** | domain |

**T41's posterior sd is 9.1–22 mV per knot.** It is dominated by the 10.3 mV relaxation allowance. That is why its predictive intervals are wide at the primary rung, and why the 0 mV ladder rung is the stronger evidence (§25).

## 23. PARAMETERIZATION SENSITIVITY

The same posterior was mapped linearly into a second parameterization.

| model | primary (voltages) | secondary | secondary status |
|---|---|---|---|
| P1 | IDENTIFIABLE | monomial coefficients | IDENTIFIABLE |
| P2, P3, P4 | IDENTIFIABLE | coefficients | **WEAKLY_IDENTIFIABLE** |
| P5, P7, P9 | IDENTIFIABLE | coefficients | **NOT_IDENTIFIABLE** |
| T3 | IDENTIFIABLE | anchor + increments | IDENTIFIABLE |
| T5 | IDENTIFIABLE | increments | **WEAKLY_IDENTIFIABLE** |
| T6, T11, T21, **T41** | IDENTIFIABLE | increments | **NOT_IDENTIFIABLE** (T41: 38 of 41 increments wider than themselves) |

**The identifiability verdict depends on parameterization**, as B2 found.

**Why it happens.** The frozen width rule is relative to the estimate. Plateau increments and high-order coefficients sit near zero, so any finite interval is wider than they are.

**What the primary claim rests on.** Node and knot voltages, which are volt-valued and physically bounded. That choice was preregistered, not chosen after seeing this table.

## 24. CALIBRATION RESULTS

**Every model:** `CALIBRATION_CONVERGED` in 5–8 optimizer evaluations, ftol/xtol termination.

| setting | value |
|---|---|
| optimizer | scipy `least_squares` trf via frozen `calibrate` |
| bounds | [2.0, 3.6] V |
| initial point | `linspace(3.0, 3.4, p)` |
| objective | χ² of standardized residuals |
| agreement with closed-form WLS | ≤ 2.7e-7 V |

**T41 in detail:**

- **Calibration fit:** RMSE 0.87 mV, calibration χ² 0.16, wall time 6.0 s.
- **Estimates:** every knot voltage is in `RESULTS.json`.
- **Units:** volts throughout.
- **Refits after held-out results:** none.

**Calibration fit alone understates prediction error by 9×:**

| T41 error | RMSE |
|---|---|
| calibration | 0.87 mV |
| CV | 7.79 mV |
| held-out | 7.55 mV |

CV anticipated the held-out error; the calibration fit did not.

## 25. HELD-OUT RESULTS

**Best honest model T41**, at the primary uncertainty:

| metric | value |
|---|---|
| RMSE | **7.55 mV** |
| MAE | **1.93 mV** |
| max \|error\| | **42.6 mV** (z = 0.0117, +1.41 σ) |
| max \|standardized residual\| | 1.41 |
| 95 % coverage | **33/33** |
| mean log predictive density | +3.28 |
| χ² | **2.20 on 33 dof**, p ≈ 1.0 |
| adequacy (B1's rule, α 0.01) | **MODEL_ADEQUATE** |
| `assess_ocv_empirical_adequacy` (measurement u only) | **MODEL_EMPIRICALLY_ADEQUATE**, χ² 2.80 on 33 |
| model discrepancy | MODEL_DISCREPANCY_NOT_MODELLED |

**χ² far below its dof means the primary uncertainty is conservative**, so at that rung the test has little power. The ladder answers this: with the relaxation allowance set to **0 mV**, T41 is still adequate globally and in every region.

| rung | 0 mV | 2 | 5 | 10.3 (primary) | 20 | 50 |
|---|---|---|---|---|---|---|
| T41 RMSE (mV) | 7.68 | 7.64 | 7.61 | 7.55 | 7.45 | 7.36 |
| T41 χ² (33) | **7.6** | 4.5 | 3.0 | 2.2 | 1.4 | 0.4 |
| T41 adequate everywhere | **yes** | yes | yes | yes | yes | yes |
| T6 adequate everywhere | no | no | yes | yes | yes | yes |
| P2 χ² / adequate | 4300 / no | 1045 / no | 483 / no | 259 / no | 123 / no | 30 / yes |

**What carries the knee at 0 mV:** the SOC term, 26 mV at the steepest held-out point, not the relaxation allowance.

## 26. REGION-SPECIFIC RESULTS

**T41:**

| region | n | RMSE | MAE | worst | max \|z\| | coverage | χ² (n) | verdict |
|---|---|---|---|---|---|---|---|---|
| KNEE | 3 | 24.8 mV | 16.8 mV | 42.6 mV | 1.41 | 3/3 | 2.10, p 0.55 | adequate |
| LOW-SOC TRANSITION | 10 | 1.48 mV | 0.69 mV | 4.57 mV | 0.26 | 10/10 | 0.074 | adequate |
| PLATEAU | 10 | **0.27 mV** | 0.18 mV | 0.74 mV | 0.04 | 10/10 | 0.003 | adequate |
| HIGH-SOC TRANSITION | 10 | 0.78 mV | 0.46 mV | 2.32 mV | 0.15 | 10/10 | 0.027 | adequate |

**T41's knee points:**

| z | error | total σ |
|---|---|---|
| 0.0117 | +42.6 mV | 30.3 mV |
| 0.0416 | +3.0 mV | 16.5 mV |
| 0.0716 | −4.8 mV | 17.3 mV |

**The knee is still the worst region by 30×.** It is adequate against its declared uncertainty, which is SOC-slope dominated. It is not adequate against instrument precision.

**The same regions for the B1 and B2 forms on this data:**

| model | KNEE RMSE | LOW-SOC | PLATEAU | HIGH-SOC | coverage |
|---|---|---|---|---|---|
| P1 (B1 chord form) | 214.6 mV, inadequate | 24.1, inadequate | 21.2, inadequate | 15.5, adequate | 18/33 |
| P2 (B2 degree-2 form) | 170.6 mV, inadequate | 27.4, inadequate | 18.2, inadequate | 17.4, inadequate | 19/33 |
| T5 (best Core-grid model) | 49.9 mV, **inadequate** | 9.3, adequate | 3.2, adequate | 5.7, adequate | 31/33 |

## 27. COMPLEXITY STUDY

Only gate-passing models were compared. Selection used CV on calibration data.

| model | p | cal RMSE | CV score | CV RMSE | held-out RMSE | held-out χ²(33) | adequate everywhere |
|---|---|---|---|---|---|---|---|
| P1 | 2 | 77.7 | 23.60 | 77.4 | 67.6 | 366 | no |
| P2 | 3 | 66.4 | 19.12 | 67.6 | 55.4 | 259 | no |
| P3 | 4 | 49.5 | 12.30 | 53.5 | 38.8 | 150 | no |
| P4 | 5 | 39.3 | 10.11 | 47.0 | 28.8 | 112 | no |
| P5 | 6 | 29.8 | 7.56 | 40.2 | 21.5 | 91 | no |
| P7 | 8 | 9.9 | 1.40 | 18.3 | 7.9 | 11.0 | yes |
| P9 | 10 | 5.1 | 0.52 | 11.3 | 6.6 | 3.8 | yes |
| T3 | 3 | 69.6 | 19.98 | 70.2 | 58.8 | 279 | no |
| T5 | 5 | 25.3 | 5.76 | 36.7 | 16.3 | 47.0 | no (knee) |
| T6 | 6 | 11.8 | 2.31 | 24.2 | 9.8 | 6.9 | yes |
| T11 | 11 | 24.0 | 5.73 | 36.5 | 15.8 | 45.4 | no (knee) |
| T21 | 21 | 11.0 | 2.20 | 24.1 | 9.4 | 4.1 | yes |
| **T41** | **41** | **0.87** | **0.228** | **7.8** | **7.55** | **2.2** | **yes** |

(RMSE in mV.)

**Underfitting.** Every model with p ≤ 5 underfits. They are inadequate, driven by the knee.

**Placement matters more than count.** T11 (uniform 10 % knots) is worse than T6, which has one knot at 5 %. The knee needs knots where it bends.

**No overfitting was observed up to p = 41:**

- held-out RMSE keeps falling in both families, and never turns upward;
- CV error tracks held-out error closely.

**The preregistered overfit condition (C) is not met.** C requires the best model to be ≥ 20 % worse than a simpler model of its family, or a simpler model to be adequate where the best is not.

**Optimal complexity:**

- **Among tested models:** CV selects p = 41 (T41).
- **At the primary rung:** the smallest adequate-everywhere model is T6 (p = 6).
- **At 0 mV allowance:** it is T41; T21 requires 2 mV.

**Post hoc, not used for selection:** P9 has the lowest held-out RMSE, 6.60 mV.

## 28. B1/B2/B3 COMPARISON

| Metric | B1 Chord | B2 Curve | B3 Best Honest Model (T41) |
|---|---|---|---|
| data | S-OCV BATT_001, 24 h relaxed | same | Jahn 2024 A123_01, interrupt-relaxed |
| n_cal | 3 | 3 | 67 |
| p | 2 | 3 | 41 |
| residual DOF | 1 | 0 | 26 |
| held-out count | 3 | 3 | 33 |
| identifiability | IDENTIFIABLE | IDENTIFIABLE | IDENTIFIABLE (domain linear-Gaussian route) |
| RMSE | 215.27 mV | 212.62 mV | **7.55 mV** |
| MAE | 132.39 mV | 130.70 mV | **1.93 mV** |
| max error | 372.44 mV | 367.87 mV | **42.64 mV** |
| coverage | 0/3 | 0/3 | **33/33** |
| χ² (dof) | 2.227e4 (3) | 1.142e4 (3) | **2.20 (33)** |
| adequacy | INADEQUATE | INADEQUATE | **ADEQUATE, every region** |

**B1/B2 numbers are unchanged:** read from their committed RESULTS.json and checked by a test.

**This table is not like-for-like.** It compares different data, different splits, and extrapolation (B1/B2 at 0 %) against interpolation (B3).

**The fair statement uses B3's own data.** With 67 calibration points spanning the knee:

| form | held-out RMSE | verdict |
|---|---|---|
| B1's chord form | 67.6 mV | inadequate |
| B2's degree-2 form | 55.4 mV | inadequate |

**What changed between rounds is the data**, which now lets a representation with enough flexibility be identified and tested.

## 29. HYSTERESIS STATUS

**Remeasured** at 1 % resolution on the charge branch. No model was added.

| region | charge − discharge (median, range) | T41 held-out RMS error | ratio |
|---|---|---|---|
| KNEE | 42.4 mV (32.2–70.3) | 24.8 mV | 1.7 |
| LOW-SOC | 40.3 mV (29.5–45.9) | 1.48 mV | 27 |
| PLATEAU | 24.7 mV (24.4–27.3) | 0.27 mV | 90 |
| HIGH-SOC | 18.8 mV (15.1–29.0) | 0.78 mV | 24 |

**Jahn plateau hysteresis is 24.7 mV, against BATT_001's 7–9.6 mV.** Part of that difference may be incomplete relaxation, which widens the apparent branch separation.

**Why hysteresis is still not justified for this claim.** The discharge-conditioned claim is now met without it. Hysteresis is now **the largest measured unmodelled effect**, 24–90× the discharge-branch prediction error. It matters for any claim involving charge-conditioned or path-dependent OCV, and such claims are **outside** `rint_ocv`'s declared scope.

## 30. CROSS-CELL RESULT

T41, fitted on the Jahn A123_01 cell, was applied **without refitting** to BATT_001's 24 h discharge OCV, scored with BATT_001's own B1 sigma rule.

| SOC | 0 % | 20 % | 40 % | 50 % | 60 % | 80 % |
|---|---|---|---|---|---|---|
| residual | **+225.8 mV** | +19.0 mV | +0.7 mV | −1.3 mV | −2.7 mV | −2.3 mV |

**Parameters:**

- **Outcome:** `PARAMETERS_DO_NOT_GENERALIZE`, `MODEL_EMPIRICALLY_INADEQUATE` (χ² 9657 on 6).
- **Plateau:** transfers across labs within 0.7–2.7 mV.
- **Knee:** does not transfer.

**Representation:** `REPRESENTATION_GENERALIZATION_UNTESTABLE`. BATT_001 has 6 levels, and refitting 41 parameters leaves no held-out data.

**Confounds, stated rather than resolved:**

- 24 h rest versus an undocumented rest (BATT_001's 0 % point recovers 316 mV between 10 min and 24 h);
- SOC definitions (nominal-capacity coulomb count versus Q/Q_top);
- different labs and instruments.

## 31. EMPIRICAL ADEQUACY

`assess_ocv_empirical_adequacy`, unchanged, applied to T41's calibrated curve against the 33 held-out points with measurement u only:

| status | χ² | p | worst point |
|---|---|---|---|
| **MODEL_EMPIRICALLY_ADEQUATE** | 2.80 on 33 | 1.0 | +42.6 mV (+1.5 σ) at z = 0.0117 |

**The other models:** P1 on the same points is `MODEL_EMPIRICALLY_INADEQUATE`.

**Regression tests confirm the assessment's contracts still hold:**

- measured B3 evidence can produce both ADEQUATE and INADEQUATE;
- no evidence gives `NO_MEASURED_EVIDENCE`;
- charge-conditioned evidence gives `EVIDENCE_OUTSIDE_CLAIM`;
- an applicability status is carried and never consulted;
- a curve cell is scored on its curve, which differs from the endpoint chord by > 50 mV at every held-out knee point.

## 32. NEXT PHYSICS DECISION

**NEXT_PHYSICS_JUSTIFIED = NONE**

**Why.** Under verdict A the preregistered rule ranks no physics. The existing curve is adequate for the discharge-conditioned claim, so OCV complexity **stops increasing**.

**Quantitative context for later rounds:**

- **Hysteresis.** It is the largest measured unmodelled effect: 24.7 mV plateau, 42 mV knee. It becomes relevant only if the claim is extended to charge-conditioned or path-dependent OCV.
- **Relaxation dynamics.** The verdict is insensitive to the relaxation allowance from 0 to 50 mV, so there is no evidence here that it is needed. The undocumented rest remains a data defect, not a model gap.
- **Temperature and rate.** `NO_EVIDENCE`: one temperature, and an undocumented current.
- **RC polarization.** Not assessable: no loaded-voltage prediction was tested.
- **Better OCV representation.** Not needed. An existing `TabulatedForm` suffices, given enough identified knots in the knee.

## 33. AI VERIFICATION DEMO UPDATE

This updates B1's §25 contract; still **no integration is built**. B3 adds steps and outcomes that B1's contract could not show.

**Pipeline.** Each refusal ends the run with a named outcome.

1. **Declaration admission** (as B1) → `REJECT_INVALID_DECLARATION`.
2. **Evidence admission.**
   - **Required:** raw bytes pinned by SHA-256 with the source checksum verified, license and provenance recorded, and the voltage meaning classified (loaded ≠ OCV).
   - **A documentation gap** (e.g. undocumented rest) is **carried as a declared uncertainty with a ladder**, never ignored.
   - **Outcome if missing or unusable:** `INCONCLUSIVE_DATA_INSUFFICIENT`.
3. **Applicability** (as B1). UNKNOWN is never acceptance.
4. **Preregistration.** Split, sigmas (with no held-out value in any term), model list, grid rule, selection rule, α and verdict mapping, all committed before any fit.
5. **Data-sufficiency gate:**
   - p ≥ n_cal or rank < p → `REJECT_STRUCTURALLY_UNIDENTIFIABLE`. This is B2-TAB5 and B3's T-CAL.
   - zero residual dof → `NO_INTERNAL_CHECK`, never validity. This is B2-POLY2.
6. **Calibration** through the frozen `calibrate`. Convergence alone is not identifiability.
7. **Identifiability**, in the declared parameterization. The result in an alternative parameterization is **always reported**.
   - **Core route:** `GridResolutionError` → `INCONCLUSIVE_UNRESOLVED`.
   - **Beyond the grid's reach:** `CORE_GAP` must be named. The domain route is admissible only after reproducing the Core grid where both run.
8. **Selection** by cross-validation on calibration data only. Held-out error is never used.
9. **Held-out adequacy**, globally **and per region**. A catastrophic knee cannot hide behind a good plateau.
10. **Robustness.** The verdict is reported across the preregistered uncertainty ladder.

**Decision:** `ACCEPT` requires all of the following:

- admitted;
- applicable (or UNKNOWN, reported);
- gate-passing;
- identifiable;
- adequate globally and in every region at the primary rung.

**Required reason:** per-point and per-region residuals, tail probabilities, evidence digests, the route used, and the ladder thresholds.

**B3 worked examples:**

| AI proposal | Forge outcome | quantitative reason |
|---|---|---|
| "A degree-2 OCV curve describes this A123 cell's discharge OCV within its uncertainty." | `REJECT_MODEL_INADEQUATE` | P2 held-out χ² 259 on 33; knee RMSE 171 mV; 19/33 covered |
| "A 41-knot declared table predicts this cell's discharge-conditioned pseudo-OCV at 25 °C." | `ACCEPT` (scoped) | T41 χ² 2.2/33, every region adequate, adequate at 0 mV allowance; identifiability via domain route, cross-checked to 1.6e-5 |
| "The same table describes another APR18650M1A cell." | `REJECT_MODEL_INADEQUATE` | BATT_001 +226 mV at 0 %, χ² 9657/6 |
| "The table's parameters are identifiable in any parameterization." | `REJECT_CLAIM` | increments: 38/41 NOT_IDENTIFIABLE |
| "This is the cell's equilibrium OCV." | `REJECT_OUTSIDE_EVIDENCE` | rest undocumented; the data are interrupt-relaxed pseudo-OCV |
| "A table with a knot at every measured point predicts held-out data." | `REJECT_STRUCTURALLY_UNIDENTIFIABLE` | T-CAL p = 69 ≥ n_cal = 67 |

## 34. CORE FILES CHANGED

**Frozen Core paths changed: 0.**

`git diff --name-only ae9d794` lists only paths under `benchmarks/battery_flagship_b3/`:

- no `src/` file changed at all, including no Battery domain file;
- no `tests/`, `tools/` or `certification/` file changed.

## 35. BATTERY TESTS

`-n 4`, basetemp on D:.

| group | selection | result |
|---|---|---|
| Battery focused | `tests/domains/battery` + `tests/mcp/test_battery_boundary.py` + `tests/oracles/test_oracle_battery.py` | **335 passed** |
| B1 regression | `benchmarks/battery_flagship_b1/tests` + `test_battery_ocv_calibration.py` | **35 passed** |
| B2 regression | `benchmarks/battery_flagship_b2/tests` + `test_battery_ocv_curve_calibration.py` | **34 passed** |
| B3 evidence / protocol / result / regressions | `benchmarks/battery_flagship_b3/tests` | **35 passed** |
| Curve calibration / identifiability | within B2 regression + B3 suite (gate, rank, route cross-check) | passed |
| Curve cutoff regression | `test_battery_ocv_curve_cutoff.py` (+ 6 B3 cutoff tests) | **21 passed** |
| Empirical adequacy regression | `test_battery_ocv_empirical.py` (+ 5 B3 tests) | **11 passed** |
| Calibration integration | `tests/inference/test_tcr_calibration.py` | **20 passed** |
| Held-out | `tests/inference/test_tcr_heldout_uq.py` | **16 passed** |
| UQ + adequacy | `test_k3_predictive_uq.py` + `test_k4_model_adequacy.py` | **13 passed** |
| Evidence integrity | `test_evidence_pairing_integrity.py` + `inference/test_reproducibility_and_evidence.py` | **40 passed** |
| Synthetic controls | `CONTROLS.json` | in-model T5 adequate (χ² 39.0/33); knee-misfit P2 inadequate (χ² 161), worst in KNEE; routes agree to 1e-11 sd |

**Working tree:** clean after every group.

## 36. FAST

`pytest tests -n 4 -m "not expensive and not campaign"`: **4976 passed, 5 skipped, 0 failed**. The count is identical to B2, because B3 added no test under `tests/`.

## 37. FULL

`pytest tests -n 4`: **5522 passed, 5 skipped, 0 failed** (identical to B2). Working tree clean afterwards.

## 38. CORE CERTIFICATE

`python -m tools.certification.core_certificate --verify` → **OK**. It reports "certificate matches the tree".

## 39. CORE FREEZE VERIFY

`python -m tools.certification.core_freeze --verify` → **OK**, mode **DESCENDANT**, binding checks PASS.

## 40. KNOWN MAINTENANCE DEBT

**`benchmarks/model_measurement_validation/tests` stays excluded and is not fixed in B3:**

- its scientific-tree digest is stale, predating B1/B2;
- its rebuild test rewrites the committed `SAFETY_GATES.json`.

**Separate maintenance task, retained:** B3 read that suite's `audit/evidence.py` and xlsx read-only, for the BATT_001 relaxation reference and the cross-cell check, and wrote nothing there.

**New item — `CORE_GAP_CANDIDATE`:** a non-grid (e.g. exact linear-Gaussian or Laplace) posterior, identifiability and predictive-UQ path in `engcore.inference` for p > ~5. It needs compatibility review under the post-freeze routing; it was **not** implemented.

## 41. FILES CHANGED

**All new, all under `benchmarks/battery_flagship_b3/`:**

- `DATA_SELECTION.json`
- `evidence/PROVENANCE.json`
- `evidence/raw/.gitattributes`
- 4 raw CSVs
- `DATA_QUALITY.json`
- `OBSERVATIONS.json`
- `PREREGISTRATION.json`
- `audit/b3_evidence.py`
- `audit/prepare_b3.py`
- `audit/run_b3.py`
- `CONTROLS.json`
- `RESULTS.json`
- `COMPARISON.json`
- `SECONDARY.json`
- `tests/test_battery_flagship_b3.py`
- this report

## 42. COMMITS

| commit | content |
|---|---|
| `467b706` | data: inventory, external candidates, selection — before any fit |
| `f0f1b09` | evidence: raw bytes frozen, SHA-256 + Zenodo MD5, CRLF preserved |
| `8a5a8a4` | prereg: voltage meaning, audit, uncertainty, split, gate, selection, verdict mapping |
| `f1c0220` | harness + synthetic controls, before the measured round |
| `4f3ebd9` | measured result + round tests |
| `d08051e` | round report |
| *(follow-up)* | record the push |

## 43. PUSH RESULT

`git push -u origin claude/battery-flagship-b3` → **new branch created** on `github.com:sharq-labs/forge.git`; remote head `d08051e` (the report commit). `main` was not touched. This line is recorded in a follow-up commit.

## 44. EXACT NEW BATTERY CLAIM

> **Setup.** The data are 100 discharge-conditioned, interrupt-relaxed voltages of one A123 18650M1A LiFePO4 cell at 25 °C (Jahn et al. 2024, 10.5281/zenodo.10852930, CC BY 4.0), measured at 1 % SOC steps. The rest after each interrupt is undocumented. On them, `battery.cell.rint_ocv`'s existing declared OCV curve was run as a 41-knot linear `TabulatedForm`:
>
> - calibrated through the frozen Core on 67 observations;
> - identifiable at rank 41 of 41, with 26 residual dof.
>
> **Held-out result, on 33 observations spanning knee, both transitions and plateau:**
>
> - RMSE 7.55 mV, MAE 1.93 mV, max 42.6 mV at the knee;
> - 33/33 inside 95 % predictive intervals;
> - χ² 2.20 on 33: adequate globally and in every region at α 0.01, and still so with no relaxation allowance.
>
> **The low-order forms are not adequate on the same data:**
>
> | form | held-out RMSE | knee RMSE |
> |---|---|---|
> | affine chord | 67.6 mV | 215 mV |
> | degree-2 curve | 55.4 mV | 171 mV |
>
> **Conclusion.** With data that resolve the knee, an existing SOC-dependent OCV representation is empirically adequate for this cell's discharge branch, and no new OCV physics is needed for that claim.

## 45. WHAT STILL CANNOT BE CLAIMED

- **Thermodynamic OCV:** that T41 is the cell's equilibrium OCV. The rest is undocumented, and plateau precision below the relaxation uncertainty is not established.
- **Another cell:** that it describes any other cell. Its parameters miss BATT_001 by 226 mV at 0 %, and representation transfer is untestable on six points.
- **Extrapolation:** that it predicts beyond the measured SOC range, or extrapolates to 0 % or 100 %. The held-out points interpolate at 1 % resolution.
- **Core certification:** that its identifiability and predictive UQ are Core-certified. They come from the domain linear-Gaussian route (CORE_GAP_CANDIDATE), and no Core-grid model (p ≤ 5) is adequate in every region.
- **Parameterization-independent identifiability:** in the increment parameterization, 38 of 41 are NOT_IDENTIFIABLE.
- **Charge-conditioned or path-dependent OCV:** hysteresis is 18–42 mV and not modelled.
- **Other conditions:** any temperature other than 25 °C, any rate, ageing, or relaxation dynamics.
- **Runtime:** runtime to a voltage cutoff on a curve cell. The certified solver refusal is unchanged.
- **Unmeasured models:** R_int, loaded terminal voltage, coulomb counting, Peukert — no measured current was tested.
- **Region adequacy at instrument precision:** knee adequacy is against the declared SOC-slope uncertainty (up to 26 mV), not against the 0.6 mV instrument accuracy.
