# Domain Real-Data Inventory

Branch `claude/domain-real-data` · base `10291d2` (B3 tip = `origin/main` content + Battery Flagship B3) · evidence only · Core frozen

```
python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py --check     # every data file classified
python -X utf8 benchmarks/domain_real_data/audit/quality_screen.py --check     # raw hashes + readiness screen
python -X utf8 -m pytest benchmarks/domain_real_data/tests -q
python -X utf8 benchmarks/domain_real_data/audit/acquire.py fetch --dest DIR   # (network) external evidence
python -X utf8 benchmarks/domain_real_data/audit/external_screen.py --dir DIR
```

Machine-readable sources of truth:

| file | holds |
|---|---|
| `DATASETS.json` | every dataset: provenance, licence, channels, uncertainty, quality grade, claim mapping, held-out possibility, missing information |
| `REPOSITORY_SCAN.json` | every data-bearing file in the repository, classified by an ordered path rule |
| `DATA_QUALITY.json` | readiness screen of the measured files mapped to claims (in-repository bytes) |
| `EXTERNAL_SCREEN.json` | readiness screen of fetched, non-vendored evidence, keyed by checksum |
| `*/…_MANIFEST.json` | file-by-file checksums and endpoints of external records (metadata only) |
| `battery/lg_hg2_mcmaster/PROVENANCE.json` | provenance of the one dataset this round vendored |

---

## 1. Repository-wide inventory (Phase 1)

### How the search was done

- **What was scanned:** every tracked file, not only paths with a domain name, filtered to data-bearing suffixes: csv, tsv, xls/xlsx/xlsm, json/jsonl, parquet, feather, h5/hdf5, mat, npz/npy, dat, txt, log and h, plus one vendored `.py` constants table.
- **How files were classified:** each file is matched against an ordered prefix table in `audit/inventory_scan.py`. A file that matches no rule is `UNKNOWN_PROVENANCE`, and the scan exits non-zero.
- **What was never opened:** the scan reads paths only. No benchmark case file was opened, so the sealed hold-out of `benchmarks/hard` was not touched.
- **Other branches:** `git log --all` found data files that exist only on other branches:
  - 1045 older `cases_hard` JSON files (generated, SYNTHETIC);
  - the core-gap review JSON;
  - four posterior-grid `.npz` fixtures on the thin-ridge branch (DERIVED from repository runs).
  - None of these is a measurement.
- **Ignored files in the shared checkout:** one untracked, ignored `results_hard.json` at the repository root, which is scoring output (DERIVED).

### Result

| class | files |
|---|---:|
| REAL_MEASURED | 11 (10 measured data files + 1 vendored dataset readme) |
| REFERENCE_ONLY | 4 |
| DERIVED | 162 |
| SYNTHETIC | 2980 |
| UNKNOWN_PROVENANCE | **0** |
| **total** | **3157** |

### Every non-synthetic dataset file

| path | class | what it is |
|---|---|---|
| `benchmarks/model_measurement_validation/evidence/ocv_relaxation_24h.xlsx` | REAL_MEASURED | Voicila et al., IEEE DataPort 10.21227/651q-8v82: 24 h OCV relaxation, 8 cells, 1 min |
| `benchmarks/model_measurement_validation/evidence/discharge_curves_1min.json` | DERIVED | a 1-minute reduction of the measured IEEE DataPort 10.21227/cm0f-jg66 curves; **no current value** |
| `benchmarks/battery_flagship_b3/evidence/raw/…incrOCV.csv` | REAL_MEASURED | Jahn 2024 A123, interrupt-relaxed voltage vs charge (B3 primary) |
| `benchmarks/battery_flagship_b3/evidence/raw/…pOCV.csv` | REAL_MEASURED | the same cell, loaded C/20 cycle |
| `benchmarks/battery_flagship_b3/evidence/raw/…HysPowerTest…SOC50.csv`, `…SOC100.csv` | REAL_MEASURED | the same cell: **t, Q, I, U through a 1C step and a 4C discharge**. B3 used them only for rest lengths. |
| `benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/*.csv` (5) | REAL_MEASURED | **new this round:** LG HG2 25 °C HPPC, C/20, 0.5C, 2C, 1C capacity |
| `benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/Readme file - …txt` | REAL_MEASURED (documentation role) | the dataset's own readme |
| `benchmarks/model_measurement_validation/evidence/pt100rtd_table.h` | REFERENCE_ONLY | Pt100 table transcription (DIN 43760 / IEC 751) |
| `benchmarks/empirical_validation/fixtures/platinum_iec60751.json` | REFERENCE_ONLY | IEC 60751 coefficients, recited |
| `benchmarks/empirical_validation/evidence/scipy_codata.py` | REFERENCE_ONLY | CODATA 2022 constants copy |
| `benchmarks/ai_designs/components.json` | REFERENCE_ONLY | datasheet ratings |

### What is synthetic or derived, and why it is not evidence

| group | files | why |
|---|---:|---|
| `benchmarks/hard/cases_hard`, `cases_battery` | 2400 | generated; truth from first principles |
| `benchmarks/blind/v1/cases`, `TRUTH.json` | 445 | generated payloads; oracle truth; "nothing checked against a measurement" |
| `benchmarks/blind_v2/cases`, `truth`, `runner` | 5 | generated; dual-oracle truth (closed form + solver / ngspice) |
| `benchmarks/ai_designs/designs` | 100 | hand-written designs; "no laboratory measurement" |
| `benchmarks/empirical_validation/fixtures` (7 of 8) | 7 | hand-constructed operating points, LEVEL 5 analytical |
| `benchmarks/oracles/results`, `scientific_truth/REFERENCE_CASES.json` | 3 | code-oracle outputs |
| `experiments/thermal_t1..t3`, `electrical_e1..e3`, `electrical_v01_demo`, `falsification`, `kinetics_k1` | 20 | hidden truth + injected noise, or solver-admission regimes |
| round artifacts, certification manifests, API snapshots, compute timings | 162 | DERIVED |

Before this round, the repository held measured data for **one domain only (Battery)**, and **only open-circuit or current-free voltage had ever been scored against it**.

---

## 3. External search log (Phase 3)

### Where the search was run

- **Network:** Zenodo, Mendeley Data, DOI resolution, NASA NTRS, the UIUC site, NIST and data.gov were all reachable (probed on 2026-09-13).
- **Correction to an earlier round:** `model_measurement_validation` recorded that DOI resolution and Zenodo were blocked. That is no longer true.
- **Search routes:**
  - the Zenodo records API, full-text queries of type dataset;
  - the Mendeley public API;
  - NTRS;
  - web search;
  - and reading of the candidate records themselves.
- **Where facts came from:** licence, author and checksum facts come from the repositories' own API fields. They were not taken from a summarising fetch tool.

| domain | queries (abridged) | outcome |
|---|---|---|
| Battery | loaded discharge / HPPC / internal resistance with current and temperature | **LG HG2 (McMaster) vendored**; Panasonic 18650PF (Wisconsin) recorded; Jahn A123 power tests re-mapped |
| Thermal | transient conduction thermocouple; lumped cooling; IR thermography of a heated plate; convection h | no dataset with independently known C, hA and Q for a uniform body; four off-claim records described; battery case temperature is the only in-claim route |
| Electrical | TCR measurement; copper wire R(T); PRT calibration; resistor self-heating | **Wesskamp & Melbert shunt R(T)** (CC BY-NC-ND); MetForTC thermometry not established to hold resistance values |
| Kinetics | CSTR concentration/temperature; saponification; acetic anhydride hydrolysis; jet-stirred reactor; reaction calorimetry | no openly licensed first-order liquid CSTR dataset found; JSR (gas-phase network) and CONSENS (tubular) recorded as off-model |
| Aerospace | propeller thrust/torque/RPM; multirotor hover power; thrust stand | **NASA/TM-2018-219758** hover tables (thrust + ESC V and I); UIUC static C_T/C_P |

The full list, including the sources rejected without an entry, is in `DATASETS.json` (`searched_and_rejected_without_a_registry_entry`, `candidates_named_but_licence_not_verified`).

---

## 4–5. Provenance and licence summary (Phases 4, 5)

| id | licence (read from) | redistribution | status | persistent id |
|---|---|---|---|---|
| DS-BAT-LGHG2 | CC BY 4.0 (Mendeley API) | PERMITTED | **VENDORED** (25 °C subset, 6.4 MB) | doi:10.17632/cp3473x7xv.3 |
| DS-BAT-PAN18650PF | CC BY 4.0 (Mendeley API) | PERMITTED | VENDORABLE_NOT_VENDORED | doi:10.17632/wykht8y7tg.1 |
| DS-BAT-JAHN-A123 | CC BY 4.0 (Zenodo) | PERMITTED | ALREADY_IN_REPOSITORY | doi:10.5281/zenodo.10852930 |
| DS-BAT-VOICILA-OCV24H | CC BY 4.0 (earlier round) | PERMITTED | ALREADY_IN_REPOSITORY | doi:10.21227/651q-8v82 |
| DS-BAT-VOICILA-DCHG | CC BY 4.0 (earlier round) | PERMITTED | ALREADY_IN_REPOSITORY (reduction) | doi:10.21227/cm0f-jg66 |
| DS-ELE-WESSKAMP-SHUNT | **CC BY-NC-ND 4.0** (Zenodo) | NOT for derivatives / commercial | **EXTERNAL_FETCH_REQUIRED** | doi:10.5281/zenodo.164820 |
| DS-AER-NASA-TM-2018-219758 | UNKNOWN for the TM (related NTRS record: PUBLIC_USE_PERMITTED) | UNCLEAR | **EXTERNAL_FETCH_REQUIRED** | NASA/TM-2018-219758 |
| DS-AER-UIUC-PROPELLER-STATIC | none stated (citation requested) | UNCLEAR | **EXTERNAL_FETCH_REQUIRED** | none |
| DS-KIN-SCIEXPEM-JSR-DAGAUT2010 | CC BY 4.0 (Zenodo) | PERMITTED | CANDIDATE_NOT_ACQUIRED | doi:10.5281/zenodo.4881855 |
| DS-THM-GEOTES / DZIKEVICS-TANK / TURBULENT-CHANNEL-H | CC BY 4.0 (Zenodo) | PERMITTED | CANDIDATE_NOT_ACQUIRED | 10.5281/zenodo.18979098 / 5146091 / 14998599 |
| DS-KIN-CONSENS-PILOT | CC BY 4.0 (Zenodo) | PERMITTED | REJECTED (off-model) | 10.5281/zenodo.1438233 |
| REF-PT100-TABLE, REF-DATASHEET-COMPONENTS, REF-IEC60751-RECITED, REF-CODATA-2022 | UNKNOWN / UNCLEAR | UNCLEAR | ALREADY_IN_REPOSITORY | — |

### Flags this round raises about evidence already in the repository

It moves nothing and edits nothing.

- **Pt100 table:** `pt100rtd_table.h` has no licence on record. A future redistribution decision should treat it as UNCLEAR.
- **A123 power tests:** the files carry no units. Their rate labels contradict their currents, which B3 already disclosed.
- **Voicila discharge curves:** `discharge_curves_1min.json` is a reduction, so it is DERIVED and not raw.

### Raw-evidence immutability (Phase 6)

- **Vendored bytes:** `battery/lg_hg2_mcmaster/raw/` holds the exact bytes Mendeley serves. Each SHA-256 equals Mendeley's published hash.
- **Line endings:** the files are CRLF with one embedded NUL byte. A nested `.gitattributes` (`* -text`) stops the repository-wide `eol=lf` from rewriting them.
- **Tests that pin them:**
  - bytes against `DATASETS.json`;
  - bytes against `PROVENANCE.json`;
  - bytes against the Mendeley manifest;
  - CRLF and NUL presence.
- **Derived artifacts:** no derived artifact was made from these files. Any later normalisation must be a separate file that names this raw SHA-256.
