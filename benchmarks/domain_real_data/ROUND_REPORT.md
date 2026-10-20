# Domain Real-Data Acquisition Sprint — Round Report

Branch `claude/domain-real-data` · base `10291d2` · evidence only · domain first · Core V1 frozen

```
python -X utf8 -m pytest benchmarks/domain_real_data/tests -q
python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py --check
python -X utf8 benchmarks/domain_real_data/audit/quality_screen.py --check
```

Detail tables are in `INVENTORY.md`. Per-dataset facts are in `DATASETS.json`.

---

## 1. FINAL VERDICT

**DOMAIN REAL-DATA INVENTORY COMPLETE — SOME DOMAINS DATA-LIMITED**

- **Complete:**
  - every data-bearing file in the repository is classified (3157 files, 0 of unknown provenance);
  - every dataset has recorded provenance and a checked licence;
  - one dataset was vendored byte-for-byte;
  - one next dataset is named for four of the five domains.
- **Data-limited:**
  - **Kinetics** has no trustworthy measured dataset for its current claim.
  - **Thermal** has none with independently known heat capacity and conductance.
  - **Electrical's** only specimen R(T) dataset carries a NonCommercial-NoDerivatives licence and cannot be vendored.

## 2. CORE STATUS

Core V1 is frozen and untouched.

- **Branch base:** this branch starts from `10291d2` (the B3 tip: `origin/main` content plus Battery Flagship B3). That base does **not** include the separately handled thin-ridge repair commits.
- **Checks:** the Core certificate and freeze verifier were run at the start and at the end, in a clean worktree isolated from the editable install (`python -S -E`, the checkout's `src/` first on `sys.path`).
- **Scope of changes:** no Core, model, solver, applicability condition or test outside `benchmarks/domain_real_data/` was changed.
- **UQ:** no PosteriorGrid UQ was run or relied on.

## 3. DOMAINS REVIEWED

| domain | where its claims live | models reviewed |
|---|---|---|
| Battery | `src/engcore/domains/battery` | `battery.cell.rint_ocv`, `battery.cell.coulomb_counting`, `battery.cell.constant_current_runtime`, `battery.cell.peukert_capacity_derating`, one-way self-heating coupling |
| Thermal | `domains/thermal`, `domains/thermal_models` | `thermal.lumped.first_order_capacity`, `thermal.conduction1d.linear_diffusion`, 2-D steady plate (spike, unregistered), convection applicability correlations |
| Electrical | `domains/electrical`, `systems/electrothermal` | six `electrical.dc.*` models, `electrical.material.linear_tcr_resistance`, `electrical.material.rated_linear_tcr_resistance`, electrothermal fixed point |
| Kinetics | `domains/kinetics/cstr` | `kinetics.cstr.nonisothermal_first_order`, `…_constant_rate` |
| Aerospace | `systems/aerospace/multirotor` | `ideal-actuator-disk-hover`, `mvr0-multirotor-mass-endurance-reference` (MVR0/MVR1) |
| other | — | none: `design/`, `sria/`, `data/` and `scientific/` hold no physical system; `experiments/falsification` is an abstract linear model |

Aerospace exists as a small analytic pack: actuator-disk hover power plus a mass and endurance roll-up. There is no blade-element model, no propeller map and no motor map. That shaped the aerospace search: only hover thrust and power evidence was sought.

## 4. EXISTING REAL DATASETS FOUND

| id | class | domain | what it measures |
|---|---|---|---|
| DS-BAT-VOICILA-OCV24H | REAL_MEASURED | Battery | 24 h OCV relaxation, LiFePO4, 1 min |
| DS-BAT-VOICILA-DCHG | DERIVED (1-min reduction of measured) | Battery | discharge voltage vs time; **current not reported** |
| DS-BAT-JAHN-A123 | REAL_MEASURED | Battery | incremental OCV (B3), C/20 loaded cycle, **two power tests with t, Q, I, U** |
| REF-PT100-TABLE | REFERENCE_ONLY | Electrical | standard Pt100 relation (transcription) |
| REF-IEC60751-RECITED | REFERENCE_ONLY | Electrical | recited Callendar-Van Dusen coefficients |
| REF-CODATA-2022 | REFERENCE_ONLY | Kinetics (input only) | gas constant |
| REF-DATASHEET-COMPONENTS | REFERENCE_ONLY | Electrical (ratings) | datasheet ratings |

- **Synthetic, not evidence:** every benchmark case, oracle truth and `experiments/` observation set (2980 files).
- **Found by this round in existing bytes:** the Jahn A123 power tests have recorded current and loaded voltage since B3 vendored them, but B3 used them only for rest lengths. They are the repository's only existing measurement of terminal voltage under load.

## 5. EXTERNAL DATASETS FOUND

| id | source | licence | classification | fits a current claim? |
|---|---|---|---|---|
| **DS-BAT-LGHG2** | Mendeley doi:10.17632/cp3473x7xv.3 (McMaster) | CC BY 4.0 | REAL_MEASURED | yes: R_int, loaded V, coulomb counting, Peukert, runtime (partial), self-heating (partial) |
| DS-BAT-PAN18650PF | Mendeley doi:10.17632/wykht8y7tg.1 (Wisconsin) | CC BY 4.0 | REAL_MEASURED | yes: second cell; case and chamber temperature |
| **DS-ELE-WESSKAMP-SHUNT** | Zenodo doi:10.5281/zenodo.164820 (Ruhr-Uni Bochum) | CC BY-NC-ND 4.0 | REAL_MEASURED | yes: specimen R(T); partial self-heated resistor |
| **DS-AER-NASA-TM-2018-219758** | NASA Ames report | UNKNOWN for the TM | REAL_MEASURED (tables) | yes: hover thrust vs power; partial MVR0 electrical power |
| DS-AER-UIUC-PROPELLER-STATIC | UIUC site | none stated | REAL_MEASURED (coefficients) | partial: figure of merit, density absent |
| DS-KIN-SCIEXPEM-JSR-DAGAUT2010 | Zenodo doi:10.5281/zenodo.4881855 | CC BY 4.0 | REAL_MEASURED (curated) | no: gas-phase reaction network |
| DS-KIN-CONSENS-PILOT | Zenodo doi:10.5281/zenodo.1438233 | CC BY 4.0 | REAL_MEASURED | no: tubular reactor (REJECTED) |
| DS-THM-GEOTES, DS-THM-DZIKEVICS-TANK, DS-THM-TURBULENT-CHANNEL-H | Zenodo | CC BY 4.0 | REAL_MEASURED | no: 3-D storage, stratified tank, turbulent channel |

A further 11 sources were searched and rejected without a registry entry, and 4 candidates were named without licence verification. Both lists are in `DATASETS.json`.

## 6. DATASETS VENDORED

**DS-BAT-LGHG2, 25 °C characterisation block**

- **Location:** `battery/lg_hg2_mcmaster/raw/`, 6 files, 6,420,798 bytes.
- **Files:**

| raw filename | bytes | SHA-256 (= Mendeley published) |
|---|---:|---|
| `549_HPPC.csv` | 6,033,634 | `70ffb357511dd77e7c6bc14c642a095ddd51d6918b547987247100a3bd2ea29d` |
| `549_C20DisCh.csv` | 312,505 | `52eff1a8d273f353d557af8172139c2f23709499d36130ac24ffbbb820e8f232` |
| `549_Dis_0p5C.csv` | 15,001 | `85f6147f9bc21157e777a547229af5f252360c308a753672ef3eb1144b57fa75` |
| `549_Dis_2C.csv` | 4,178 | `87b77c00e18242b177bd7a2eac8faa46ad2139c15aa94c146388ae13eba92a06` |
| `551_Cap_1C.csv` | 51,428 | `d9b9dd9b9b842ee6ba91f79a85512d2306527103d2f1cef5ecec4f962a75d83e` |
| `Readme file - Description of Experimental Tests.txt` | 4,052 | `809c0045eabcf4913a380ad520e4016f52a9c4186e6d15958992df3baf0e1427` |

- **Retrieval:** 2026-09-13, HTTPS from the Mendeley public-files endpoint. Each hash was compared with the `sha256_hash` the Mendeley API publishes.
- **Byte safety:**
  - a nested `.gitattributes` (`* -text`) keeps the CRLF and NUL bytes;
  - the committed blobs were re-hashed from `git cat-file` and match.

## 7. DATASETS NOT VENDORED + WHY

| id | why |
|---|---|
| DS-ELE-WESSKAMP-SHUNT | **CC BY-NC-ND 4.0.** NoDerivatives forbids distributing an extracted R(T) table. NonCommercial conflicts with any commercial use. Forge's commercial status is not established here. |
| DS-AER-NASA-TM-2018-219758 | No rights statement for the TM was read. The related NTRS conference-paper record reads PUBLIC_USE_PERMITTED, but that is a different document, and one author is a contractor. The file is also 24 MB. |
| DS-AER-UIUC-PROPELLER-STATIC | The site states no licence and asks for citation only. |
| DS-BAT-PAN18650PF | Licence permits vendoring. It is deferred because the LG subset covers the same claims in CSV, and Panasonic is 197 MB of `.mat` files. |
| LG HG2 other temperatures and drive cycles | Licence permits vendoring. Not needed until a temperature-transfer round; all 415 files are listed with Mendeley SHA-256. |
| LG HG2 technical PDF | The repository's own caveat covers third-party content, and the PDF carries a cell specification table. It was read, not vendored. |
| DS-KIN-SCIEXPEM-JSR, thermal candidates, CONSENS | No current claim can use them. |

For every EXTERNAL_FETCH_REQUIRED record, the repository holds only metadata, checksums (the publisher's where published, otherwise the SHA-256 of the retrieved copy) and `audit/acquire.py fetch` instructions. Fetch-and-verify was run once this round: the shunt matched its MD5, the NASA PDF matched its recorded SHA-256, and 262 of 262 UIUC files were unchanged.

## 8. LICENSE STATUS

| licence | datasets |
|---|---|
| CC BY 4.0, verified from a repository API field | LGHG2, PAN18650PF, JAHN-A123, SCIEXPEM-JSR, GEOTES, DZIKEVICS-TANK, TURBULENT-CHANNEL-H, CONSENS |
| CC BY 4.0, from an earlier round's record | VOICILA-OCV24H, VOICILA-DCHG |
| CC BY-NC-ND 4.0 | WESSKAMP-SHUNT |
| UNKNOWN / UNCLEAR | NASA TM (related record public-use permitted), UIUC (none stated), PT100 table, datasheet components, CODATA copy (scipy licence not re-read), IEC 60751 recitation |

- **Attribution:** every CC BY use in a later round must cite the DOI in `DATASETS.json`.
- **Nothing vendored without permission:** a test fails if a VENDORED record lacks a PERMITTED licence, or if an EXTERNAL_FETCH_REQUIRED record has bytes in the repository.

## 9. BATTERY EVIDENCE

- **Before this round:** OCV was measured well.
  - B1/B2: Voicila LiFePO4, relaxed.
  - B3: Jahn A123, interrupt-relaxed; the T41 curve is adequate.
  - Load was never measured: no dataset in use recorded current, so R_int, loaded voltage, coulomb counting, runtime and Peukert were never testable (B1 §34, B2 §20, B3 §45).
- **Now:** LG HG2 at 25 °C (vendored) has synchronized time, current, terminal voltage, Ah and Wh counters and case temperature.
  - **HPPC:** 48,048 rows at 0.1 s during pulses, currents from −18.0 A (6C) to +6.0 A.
  - **Discharges:** C/20, 0.5C (1.5 A), 2C (6.0 A) and a 1C capacity test, each to the 2.8 V cycler cut-off.
  - **Accuracy:** voltage and current 0.1 % of full scale on a 75 A / 5 V channel; case temperature ±1 °C.
- **In repository, unused:** the Jahn A123 power tests.
  - They record a 1C step and a 4C discharge on the same cell as the B3 OCV curve.
  - The files carry no units, and the rate-label contradiction B3 disclosed still stands.
- **External:**
  - Panasonic 18650PF: five temperatures, HPPC, EIS, case **and chamber** temperature.
  - The other five LG temperatures.
- **Not claimed:** nothing about any battery model's adequacy. This round opened the files for readiness only.

## 10. THERMAL EVIDENCE

| capability | steady / transient | dimension | measured evidence |
|---|---|---|---|
| `thermal.lumped.first_order_capacity` | transient | 0-D | **none with independent C, hA and Q**. Battery case temperature (LG: 24.19 → 27.87 °C over the 2C discharge; Panasonic: case + chamber) is the only in-claim route, and there C and hA must be calibrated. |
| `thermal.conduction1d.linear_diffusion` | transient | 1-D | none possible: the output `u` is dimensionless and the half-sine start profile is not one an experiment produces |
| 2-D steady plate (spike) | steady | 2-D | none found |
| convection applicability correlations (Churchill-Chu, laminar flat plate) | steady | — | none in regime; one turbulent-channel h dataset is off-regime |
| 3-D transient | — | 3-D | GeoTES thermocouples exist, but no Forge model is 3-D |

Teaching cooling-curve CSVs remain rejected, as in `model_measurement_validation`.

## 11. ELECTRICAL EVIDENCE

| model | measured evidence |
|---|---|
| `electrical.dc.resistor_ohm`, `kcl`, `ideal_voltage_source`, `ideal_current_source` | **none**. ngspice agreement is LEVEL 4 external computation, not measurement. |
| `electrical.dc.regulated_voltage_source` | none |
| `electrical.material.linear_tcr_resistance` | **Wesskamp shunt**: 9 steady-state R(T) points, 20.07–89.405 (°C implied), 10.037–10.331 mΩ, no uncertainty, units not in file. The Pt100 table and the IEC recitation are references only. |
| `electrical.material.rated_linear_tcr_resistance` | shunt R(T) plus datasheet ratings (partial) |
| `electrical.dc.self_heated_resistor`, electrothermal fixed point | shunt static calibration: shunt voltage and current at 20 and 30 °C with steady heat-sink temperature. The pairing is not stated (21 current points against 6 temperature points), and the thermal resistance is not in the file. |
| AC / transient / frequency | none sought beyond the search; no current claim |

## 12. KINETICS EVIDENCE

- **Current claim:** a single irreversible first-order A→B reaction in a jacketed non-isothermal CSTR, with outputs C_A, T and conversion.
- **Measured data for it:** none found that is openly licensed and on-model.
- **Off-model records:**
  - **JSR (SciExpeM/ReSpecTh):** a real stirred reactor, but multi-species gas-phase oxidation. 12 points, 17 species, no uncertainty, and truncated species keys in the curation.
  - **CONSENS:** tubular reactors.
  - **Saponification lab reports:** second order, no DOI-backed data.
  - **Acetic anhydride hydrolysis:** pseudo-first-order and exothermic, the right physics, but published only as papers.
- **Input evidence only:** the CODATA gas constant. The model is handed R, so R says nothing about the balances.

## 13. AEROSPACE EVIDENCE

- **Current claim:** ideal actuator-disk hover power P_i = T^1.5 / sqrt(2ρA), and the MVR0 chain from mass to thrust to P_i to electrical power (P_i/η + P_aux) to endurance.
- **NASA/TM-2018-219758, Appendix C:**
  - **Coverage:** 40 hover tables, 494 numeric rows. Isolated-rotor tables C84–C88, full-vehicle tables C74–C83.
  - **Channels:** air density, RPM, Fx/Fy/Fz, Mx/My/Mz, ESC voltage, per-rotor current.
  - **Uncertainty:** per-point force and moment uncertainty tables.
  - **What it can check:** thrust against shaft power (Mz·Ω), electrical power and the ideal induced power bound, on five vehicles.
  - **Test locations:** three vehicles were hovered in a lab, two inside the tunnel, where recirculation "has yet to be quantified" (TM text).
- **UIUC static tests:** 262 files, 4145 rows of RPM, C_T and C_P. No density, no uncertainty, no electrical data.
- **Not measurable from either source:** vehicle mass breakdown, battery energy and flight endurance. So the MVR0 endurance half has no evidence.

## 14. CLAIM ↔ DATA MAP

| Domain | Model / claim | Required measurement | Available? | Dataset |
|---|---|---|---|---|
| Battery | `rint_ocv`: OCV(z) | relaxed or pseudo OCV vs SOC | YES | VOICILA-OCV24H (B1/B2), JAHN incrOCV (B3); LGHG2 C/20 is loaded pseudo-OCV |
| Battery | `rint_ocv`: R_int, V under load | synchronized I and V at known SOC | **YES (new)** | LGHG2 HPPC, 0.5C, 2C; JAHN power tests (partial); PAN18650PF (external) |
| Battery | `coulomb_counting` | I(t), charge counter, capacity | YES | LGHG2 Ah + Cap_1C; JAHN Q (partial) |
| Battery | `constant_current_runtime` | constant-current discharge to cut-off | PARTIAL | LGHG2 0.5C/1C/2C to 2.8 V; solver refuses curve + cutoff voltage |
| Battery | `peukert_capacity_derating` | capacity at ≥ 2 rates, one temperature | YES | LGHG2 C/20, 0.5C, 1C, 2C |
| Battery | R_int temperature drift screen | R at several temperatures | YES (screen only) | LGHG2 / PAN18650PF other temperatures (external) |
| Battery | self-heating one-way coupling | T(t), I, T_amb, C, hA | PARTIAL | LGHG2 case T (no chamber T; C, hA unknown); PAN18650PF case + chamber T |
| Battery | charge, hysteresis, RC, ageing | — | not claimed by the models | — |
| Thermal | `lumped.first_order_capacity` | T(t) of a uniform body with independent C, hA, Q, T_amb | PARTIAL at best | battery case temperature only |
| Thermal | `conduction1d.linear_diffusion` | normalised half-sine mode decay | NO | not measurable as posed |
| Thermal | 2-D steady plate | plate temperature field, k, boundary conditions | NO | — |
| Thermal | convection screens | laminar flat-plate or natural-convection h | NO | turbulent channel only (off-regime) |
| Electrical | `dc.resistor_ohm`, `kcl`, sources | V and I on a physical circuit | NO | — (ngspice is not measurement) |
| Electrical | `dc.regulated_voltage_source` | V_oc, I, R_out | NO | — |
| Electrical | `material.linear_tcr_resistance` | R(T) of a specimen with uncertainty | YES (external; no uncertainty) | WESSKAMP-SHUNT; PT100 / IEC as references |
| Electrical | `material.rated_linear_tcr_resistance` | R(T) + ratings | PARTIAL | shunt + datasheets |
| Electrical | `dc.self_heated_resistor`, electrothermal | I, V, element or heat-sink T at steady state | PARTIAL | shunt static calibration |
| Kinetics | `cstr.nonisothermal_first_order` (+ constant rate) | C_A(t) or conversion, T(t), τ, feed, UA | **NO** | — |
| Aerospace | `ideal-actuator-disk-hover` | thrust, disk area, density; shaft or electrical power as the bound's comparator | YES (external) | NASA TM; UIUC (partial) |
| Aerospace | MVR0 hover electrical power | total thrust against electrical power | PARTIAL | NASA TM full-vehicle hover |
| Aerospace | MVR0 mass and endurance | mass breakdown, battery energy, hover time | NO | — |

## 15. MISSING MEASUREMENTS

- **Battery:**
  - charge-counter uncertainty;
  - chamber temperature for LG (Panasonic has it);
  - cell heat capacity and surface conductance;
  - a relaxed, not loaded, OCV curve for the LG NMC cell;
  - units inside the Jahn power-test files.
- **Thermal:** a transient of a uniform body whose C and hA are known independently of the trace (mass × c_p, measured h·A), with measured heat input and ambient; any measured plate temperature field with known k and boundaries; laminar or natural-convection h.
- **Electrical:**
  - any measured DC circuit (node voltages and branch currents with instrument accuracy);
  - R(T) with uncertainty on a redistributable licence;
  - regulated-source output resistance;
  - element hot-spot temperature against power.
- **Kinetics:** a liquid-phase first-order (or pseudo-first-order) exothermic reaction in a jacketed CSTR with C_A(t) or conversion by an independent assay, T(t), feed flow, volume and UA from a calibration run.
- **Aerospace:**
  - electrical-channel uncertainty;
  - an independently confirmed rotor diameter for each vehicle (TM Table 1 text extraction is column-misaligned);
  - vehicle mass and battery energy with hover endurance.

## 16. DATA QUALITY

| dataset / file | rows | finite | units | duplicates / time axis | grade |
|---|---:|---|---|---|---|
| LGHG2 `549_HPPC.csv` | 48,048 | all | V, A, C, Ah, Wh | 233 exact duplicate rows; 247 repeated Prog Time stamps | B |
| LGHG2 `549_C20DisCh.csv` | 2,423 | all | yes | 2 duplicates; 60 s | B |
| LGHG2 `549_Dis_0p5C.csv` | 111 | all | yes | none; 60 s | B |
| LGHG2 `549_Dis_2C.csv` | 27 | all | yes | none; 60 s; first row 60 s into the step | B |
| LGHG2 `551_Cap_1C.csv` | 397 | all | yes | 2 duplicates; 10 s | B |
| JAHN power tests SOC50 / SOC100 | 336 / 723 | all | **none in file** | none; median 10 s | B |
| VOICILA-OCV24H | 1441 per trace | all | yes | none (B1 DATA_INTEGRITY) | A |
| VOICILA-DCHG (reduction) | — | — | no current | — | C |
| WESSKAMP-SHUNT R(T) | 9 | all | **none in file** | 69.24 / 69.34 pair 0.1 apart | C |
| NASA TM hover tables | 494 | all | in headers | consistent columns per table; transcription needed | B |
| UIUC static | 4145 | all | coefficients | none | C |
| SciExpeM JSR | 12 | — | in XML | truncated species keys; no uncertainty | D (current claim) |

- **Raw or processed:**
  - LG, Panasonic and Jahn are raw instrument exports;
  - the shunt file is a processed MATLAB bundle;
  - NASA and UIUC are processed tables;
  - the JSR record is a curated transcription.
- **Sources:** DATA_QUALITY.json (in-repository bytes) and EXTERNAL_SCREEN.json (fetched copies, by checksum).
- **Readiness only:** nothing was cleaned.

## 17. HELD-OUT READINESS

| Dataset | Real measured | Claim it can test | Quality | Held-out possible | Missing information |
|---|---|---|---|---|---|
| LGHG2 25 °C | yes | R_int, loaded V, coulomb counting, Peukert, runtime (partial) | B | **yes**: calibrate on HPPC and C/20, predict 0.5C and 2C; across SOC levels; across temperatures (external) | charge-counter uncertainty; relaxed OCV |
| PAN18650PF | yes | same on a second cell; self-heating with chamber T | B | yes: cell transfer | accuracy; chemistry |
| JAHN power tests | yes | loaded V, coulomb counting | B | partial: two tests, one cell | units in file |
| VOICILA-OCV24H | yes | OCV only | A | used by B1/B2; saturated | current |
| LGHG2 case temperature | yes | lumped self-heating | C | calibrate hA on one discharge, predict another | C, hA, chamber T |
| WESSKAMP-SHUNT | yes | linear TCR | C | a small declared split of 9 points | uncertainty; licence |
| NASA TM | yes | hover power bound; MVR0 electrical power | B | yes: five vehicles, five rotors | rights; diameters; electrical uncertainty |
| UIUC static | yes | figure of merit | C | yes: many propellers | density; uncertainty; licence |
| Kinetics | — | — | — | **no** | a dataset |

Size did not decide any of this. The largest record reviewed, CONSENS at about 14.6 GB of spectra, was rejected, and the most useful electrical record has nine points.

## 18. NEXT FLAGSHIP DATASET PER DOMAIN

**Battery**
- **NEXT_DATASET:** DS-BAT-LGHG2, 25 °C subset (vendored).
- **NEXT_MODEL_TO_TEST:** `battery.cell.rint_ocv`, terminal voltage under load with R_int. Then `coulomb_counting` and `peukert_capacity_derating`.
- **WHY:** it is the only vendored, CC BY, raw dataset that synchronizes current, terminal voltage, charge and temperature under documented load, with stated instrument accuracy. It closes the gap B1–B3 each recorded.
- **BLOCKERS:**
  - The calibration adapter admits only `open_circuit_voltage` (`calibration.py`: "No terminal-voltage observable"), so a domain adapter for a loaded-voltage condition is needed first. This is a domain change, not a Core change.
  - The model has no RC branch, so pulse-duration dependence must be handled by a preregistered sampling instant, not by adding physics.
  - The OCV source for the NMC cell must be declared: C/20 is loaded.
  - A preregistered rule is needed for the 233 duplicate HPPC rows.
  - The solver refuses a declared curve together with a cutoff voltage for runtime.
  - Charge-counter uncertainty is undocumented.
  - Any posterior-grid UQ waits on the separately handled thin-ridge repair.

**Thermal**
- **NEXT_DATASET:** DS-BAT-LGHG2 case-temperature channel (2C discharge and 1C capacity test), with DS-BAT-PAN18650PF as the chamber-temperature complement.
- **NEXT_MODEL_TO_TEST:** `thermal.lumped.first_order_capacity` through the battery one-way self-heating coupling.
- **WHY:** it is the only measured transient in any current thermal claim, with a synchronized heat-source proxy and a temperature response.
- **BLOCKERS:**
  - C and hA are not measured, so they must be calibrated on one run and predicted on another. That is weaker than the independent-C/hA standard `model_measurement_validation` set.
  - The ±1 °C sensor accuracy is comparable to the ≤ 3.7 °C rise.
  - The LG files have no chamber temperature.
  - Q depends on R_int from the Battery flagship, and entropic heat is unmodelled.
  - A dedicated lumped-body experiment remains the right target.

**Electrical**
- **NEXT_DATASET:** DS-ELE-WESSKAMP-SHUNT, `TemperatureCoefficientResistor` (external fetch).
- **NEXT_MODEL_TO_TEST:** `electrical.material.linear_tcr_resistance`.
- **WHY:** it is the only DOI-backed measurement of a real conductor's R(T) found. It lies inside the model's 200–450 K range.
- **BLOCKERS:**
  - **Licence:** CC BY-NC-ND. The owner must decide on non-commercial use. No derived table may be committed, so a validation round would have to fetch at run time and commit only results.
  - **Data:** 9 points; no uncertainty or units in the file.
  - **Method:** the article's method section has not yet been read.

**Kinetics**
- **NEXT_DATASET:** NONE — no trustworthy on-model dataset exists.
- **NEXT_MODEL_TO_TEST:** `kinetics.cstr.nonisothermal_first_order`, once data exists.
- **WHY:** every measured reactor record found is off-model (gas-phase networks, tubular reactors) or not openly published.
- **BLOCKERS:** a dataset must be obtained with permission from authors (e.g. acetic anhydride hydrolysis calorimetry) or commissioned, to the specification in §15.

**Aerospace**
- **NEXT_DATASET:** DS-AER-NASA-TM-2018-219758, hover tables C74–C88 (external fetch).
- **NEXT_MODEL_TO_TEST:** `ideal-actuator-disk-hover` as a lower bound against measured shaft and electrical power. Then the MVR0 thrust-to-electrical-power relation with η calibrated on some vehicles and predicted on others.
- **WHY:** the only record found that pairs measured hover thrust with measured ESC voltage and current, with per-point force uncertainty and air density.
- **BLOCKERS:**
  - The TM rights statement has not been confirmed.
  - A DERIVED transcription must be checked page by page; the Table 1 diameters are misaligned in text extraction.
  - The electrical channels have no uncertainty.
  - Two vehicles were hovered in the tunnel with unquantified recirculation.
  - The MVR0 endurance half cannot be tested.
  - The pack is not exposed through MCP.

## 19. DOMAIN PRIORITY

| rank | domain | priority | reason |
|---|---|---|---|
| 1 | Battery | **P1** | good raw dataset vendored and screened; a loaded-voltage domain adapter is needed before validation |
| 2 | Aerospace | **P1** | good measured tables exist; a transcription adapter and a rights check are needed |
| 3 | Electrical | **P2** | the only specimen R(T) has 9 points, no uncertainty and an NC-ND licence; DC circuits have no measurement at all |
| 4 | Thermal | **P2** | in-claim evidence exists only through battery case temperature, with C and hA unknown |
| 5 | Kinetics | **P3** | no trustworthy dataset for the current claim |

No domain is P0. OCV validation is already done (B3), and every other claim needs an adapter, a transcription or a licence decision first. Commercial interest did not enter the ranking.

## 20. CORE FILES CHANGED

**0.** `git diff --name-only 10291d2..HEAD` lists only paths under `benchmarks/domain_real_data/`.

## 21. CORE CERTIFICATE

- **Start (at `10291d2`, clean worktree, `-S -E`):** `certificate matches the tree` / `OK`, exit 0.
- **End (at `41b1f4c`, the final content commit, clean worktree, `-S -E`):** `certificate matches the tree` / `commit: certified commit b32f67d7ad16, HEAD 41b1f4c454a8` / `OK`, exit 0.
- **Shared checkout:** in the shared checkout, the same command reported `FAILED` only because another session's untracked files made the tree dirty. That is the reason the isolated clean worktree was used.

## 22. CORE FREEZE VERIFY

- **Start (at `10291d2`, clean worktree, `-S -E`):** mode `DESCENDANT`, 29 PASS, 0 FAIL, `OK`, exit 0.
- **Informational lines, unchanged from the base:** `domain.digest` differs (a descendant may add domains), and post-candidate changes outside the evidence paths are the B1 files.
- **End (at `41b1f4c`, clean worktree, `-S -E`):** mode `DESCENDANT`, 29 PASS, 0 FAIL, `OK`, exit 0. The informational lines are identical to the start.

## 23. FILES ADDED

All under `benchmarks/domain_real_data/`:

- **Round documents:** `ROUND_REPORT.md`, `INVENTORY.md`
- **Registry and screens:** `DATASETS.json`, `REPOSITORY_SCAN.json`, `DATA_QUALITY.json`, `EXTERNAL_SCREEN.json`
- **Audit scripts:** `audit/inventory_scan.py`, `audit/quality_screen.py`, `audit/external_screen.py`, `audit/acquire.py`
- **Tests:** `tests/test_domain_real_data.py` (13 tests)
- **Vendored LG HG2 data:** `battery/lg_hg2_mcmaster/PROVENANCE.json`, `MENDELEY_MANIFEST.json`, `raw/.gitattributes` and the 6 raw files
- **Metadata-only manifests:**
  - `battery/panasonic_18650pf_wisconsin/MENDELEY_MANIFEST.json`
  - `battery/jahn_a123_bayreuth/ZENODO_MANIFEST.json`
  - `electrical/wesskamp_melbert_shunt/ZENODO_MANIFEST.json`
  - `kinetics/sciexpem_jsr_dagaut_2010/ZENODO_MANIFEST.json`
  - `aerospace/uiuc_propeller_database/STATIC_MANIFEST.json`
  - `aerospace/nasa_tm_2018_219758/RETRIEVAL_MANIFEST.json`

## 24. FILES CHANGED

None outside the added directory. No existing B1/B2/B3 or `model_measurement_validation` file was moved or edited.

## 25. COMMITS

| commit | subject |
|---|---|
| `22a4383` | evidence(domains): vendor LG HG2 25 degC cycler exports byte-for-byte; external record manifests |
| `1ba08ee` | data(domains): repository-wide real-data inventory, dataset registry, readiness screens |
| `41b1f4c` | docs(domains): the domain real-data round report |
| (this commit) | docs(domains): record the push in the round report; edits this file only |

### Operational note: a shared checkout

- **What happened:** this round began in the checkout another session was using for the thin-ridge repair. Switching that checkout to the new branch caused the other session's next commit (`b773e5c`, "bench(core): wheel parity at the repair candidate; named-suite runner") to land on `claude/domain-real-data`.
- **How it was undone:**
  - the commit was cherry-picked onto `claude/core-v1-thin-ridge-repair` (now `91e7d3c`);
  - the shared checkout was switched back to that branch;
  - `claude/domain-real-data` was reset to `10291d2` before any work of this round.
- **Where the work was done:** all work was then done in a separate worktree.
- **Open risk:** for the minutes the shared checkout sat on `10291d2`, the other session's working tree did not contain its repair source. Its suite outputs from that window should be re-checked by that session.

## 26. PUSH RESULT

- **Command:** `git push -u origin claude/domain-real-data`, run after the three content commits.
- **Result:** `* [new branch] claude/domain-real-data -> claude/domain-real-data` on `github.com:sharq-labs/forge.git`.
- **Checks on that commit:**
  - 57 tests passed: this round's 13, B3's, and the trust-boundary package-identity suite;
  - `inventory_scan.py --check` reported `REPOSITORY_SCAN.json current`;
  - `quality_screen.py --check` reported `DATA_QUALITY.json current hashes OK`.

## 27. REMOTE HEAD

- **After the first push:** `git ls-remote origin refs/heads/claude/domain-real-data` returned `41b1f4c454a8af92ff1d973dd7110c0f60b2c8f3`, equal to local HEAD.
- **This record commit:** pushed the same way. Its remote-equals-local check is reported where it was made, in the session's final message, because a commit cannot contain its own hash.

## 28. EXACT NEXT DOMAIN VALIDATION ROUNDS

1. **Battery Flagship B4: loaded terminal voltage and R_int on LG HG2, 25 °C**
   - Preregister first: the calibration set (HPPC discharge pulses at a declared SOC subset and a declared sampling instant after pulse onset); the held-out set (the remaining pulses, then the 0.5C and 2C discharges); the duplicate-row rule; the OCV source; the uncertainty model from the 0.1 % FS spec; the verdict mapping.
   - Then build a domain adapter for a loaded-voltage condition.
   - No Core change.
2. **Battery B5: coulomb counting and Peukert on LG HG2**
   - C/20, 0.5C, 1C, 2C at 25 °C.
   - Then temperature transfer using the external 10 °C and 40 °C files, fetched and verified against `MENDELEY_MANIFEST.json`.
3. **Aerospace A1: NASA TM hover evidence round**
   - Confirm rights.
   - Produce a DERIVED machine-readable table of C74–C88 with a page-by-page check and SHA-256 of the PDF.
   - Preregister the actuator-disk lower-bound test and an η split (calibrate on three vehicles, predict two).
4. **Electrical E4: licence decision, then specimen TCR**
   - The owner decides on CC BY-NC-ND use.
   - If accepted: fetch at run time, read the article method, preregister a split of the 9 points, test `linear_tcr_resistance`, and commit results only.
5. **Thermal T4: battery case-temperature lumped transient**
   - Uses B4's R_int.
   - Calibrate hA/C on the 1C capacity test, predict the 2C discharge.
   - In parallel, specify a dedicated lumped-body experiment with independent C and hA.
6. **Kinetics K5: acquisition only**
   - Obtain, with permission, or commission a first-order jacketed-CSTR dataset to the §15 specification.
   - No validation round is possible before that.

---

## Final acceptance

- [x] repository-wide data inventory complete (3157 files, 0 unknown)
- [x] every dataset classified
- [x] provenance recorded (UNKNOWN where the source is silent)
- [x] licences checked
- [x] raw files immutable (`-text`, byte pins, blob re-hash)
- [x] hashes recorded
- [x] no unsupported provenance claims (facts from repository APIs and read documents; inferences labelled)
- [x] claim-to-data mapping complete
- [x] one next dataset chosen per domain where possible (Kinetics: none exists)
- [x] no calibration or UQ executed
- [x] no models changed
- [x] frozen Core files changed = 0
- [x] Core certificate OK (start `10291d2`, end `41b1f4c`)
- [x] Core freeze verifier OK (start `10291d2`, end `41b1f4c`)
- [x] branch committed
- [x] branch pushed
- [x] remote HEAD == local HEAD (`41b1f4c`; this record commit re-checked after its push)
