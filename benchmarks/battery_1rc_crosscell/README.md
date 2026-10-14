# Battery 1RC — cross-cell evaluation on Kirkaldy 2024 (LG M50T, 25 °C, beginning of life)

**Outcome: `IDENTIFIABILITY_SUPPORTED`.** The parameters are identifiable across cells. Neither held-out set can
support or contradict the model, because part of each set lies outside the unwidened calibration domain.
`independent_validation` stays **MISSING** in the ledger.

The NASA closure (`../battery_1rc_closure`) and the LG HG2 experiment (`../battery_1rc_identifiability`, outcome
`MODEL_REJECTED`) are preserved unchanged. Tests pin them.

## Data

| | |
|---|---|
| Source | Kirkaldy et al. 2024, Zenodo [10.5281/zenodo.10637534](https://doi.org/10.5281/zenodo.10637534), CC BY 4.0 |
| Retrieved | Owner-approved partial download, 2026-10-15. HTTP range reads of the five archives' zip directories, then only the 36 RPT0 CSVs of the 12 cells at 25 °C, each checked by CRC32. 250 MB in total. |
| Location | `D:/forge-data/kirkaldy2024/bol25/` (not committed). SHA-256 receipts are frozen in `PREREGISTRATION.json`. |
| Measurement uncertainty | **UNKNOWN**: the BioLogic accuracy is not admitted. It is never set to zero. |

**Roles** (fixed by experiment number before any fit):

| Role | Cells | Windows |
|---|---|---|
| Calibration | Expt 3 D/E/F, 4 D/E, 5 D/E | 138 windows from the 25-pulse GITT |
| Primary held-out | Expt 1 D/E/F, 2,2 C/D | 99 windows from the 25-pulse GITT |
| Secondary held-out | the same five cells | 17 windows from the 5-pulse GITT (1440 s pulses) |

The three window roles total about 67 MB, so they are **not committed**. Their `.sha256` pins are committed, and
`data.load` refuses any rebuild that does not reproduce them byte for byte. To rebuild them:

```bash
python -m benchmarks.battery_1rc_crosscell.data --raw-dir D:/forge-data/kirkaldy2024/bol25
```

`FORGE_KIRKALDY_DIR=<dir>` enables the rebuild test.

## Construction deviations (recorded before any fit)

1. **Temperature dropouts.** Every window that contains a dropout sample (outside [15, 40] °C) is excluded. The
   preregistered wording ("excluded from the applicability check") could not be met without inventing a temperature
   for the route.
   - This is stricter on applicability, but it is not free: it can remove held-out windows the preregistration would
     have scored, and removing evidence can hide a failure.
   - On these files it removed **none**. All 9 dropout exclusions have the dropout inside the pulse, which the
     preregistration already excludes. `data/exclusions.json` counts the dropout samples per file and labels any window
     removed by this rule alone.
   - A strictly conservative rule for a future preregistration would keep such windows with UNKNOWN applicability,
     which makes their set NOT_ASSESSABLE.
2. **Step-transition records.** The Expt 2,2 files log one sample at every rest → discharge edge, 2 ms before the first
   load sample. It shows I = 0 but an on-load voltage, 67–84 mV below the rest voltage, and it made every Expt 2,2
   window fail the 1 mV relaxation screen.
   - It was found by reading raw samples at the step edges of the **held-out** Expt 2,2 cells, after the first build
     excluded 50 of their windows (22 + 22 from the 25-pulse files, 3 + 3 from the 5-pulse files). No model had been
     run.
   - **This partly unblinded those cells before the calibration fit.** The edges show on-load drops of 67–84 mV at
     2.5 A, an R0 proxy of about 27–34 mΩ. It could not steer the fit: the objective, bounds, starts and rules were
     already frozen, and all eight starts converge to one optimum.
   - One uniform rule in `data.read` drops such records. The census finds them only in the Expt 2,2 files.
   - The calibration roles are byte-identical with or without the rule.

## Results

**Calibration** (`results/CALIBRATION.json`, committed before the held-out evaluation ran; see the partial unblinding
above):

- IDENTIFIABLE: R0 = 33.1 mΩ, R1 = 20.2 mΩ, C1 = 5307 F, τ = 107 s.
- The cell-block bootstrap (B = 200) gives CVs of 0.8–6.1 %. The profiles rise by ≥ 10 % within a factor of 3 on both
  sides, no parameter is on a bound, and the hold-convention shift is ≤ 1 %.
- Calibration RMSE: 8.5 mV for the 1RC, 14.7 mV for Rint.

**Held-out** (`results/VALIDATION.json`, strict transfer through the engcore route):

| Set | Windows outside the domain | Pooled 1RC RMSE / P95 (mV) | Load-only 1RC RMSE / P95 (mV) | Acceptance |
|---|---|---|---|---|
| Primary, 25-pulse | 32 of 99 | 11.1 / 20.9 | 12.1 / 21.5 | NOT_ASSESSABLE |
| Secondary, 5-pulse | 8 of 17 | 11.5 / 21.4 | 11.7 / 21.5 | NOT_ASSESSABLE |

Why windows fall outside the domain (the attribution agrees with the route's status window by window):

- **Temperature.** Held-out cells reached 17.61 °C. The calibration range is 23.19–29.66 °C.
- **Current.** Some held-out pulses exceed the calibration maximum current (2.5017 A) by up to 0.52 mA
  (`VALIDATION.json` `current_A`).

The preregistration keeps both ranges unwidened because no sensor accuracy is admitted. They are not widened after the
fact. The Rint-vs-1RC comparisons on these sets are also NOT_ASSESSABLE.

**Descriptive only** (not preregistered, no verdict):

- In-domain windows only: 9.5 / 19.5 mV on the primary set (67 windows), 11.8 / 21.1 mV on the secondary set (9
  windows from 3 cells). This selection is **not neutral**: the excluded windows carry larger errors (the full primary
  set is 11.1 mV).
- Each held-out cell with its own OCV and own Q: 8.0–11.9 mV. This is computed on **all** primary windows, including
  the out-of-domain ones.

A subset chosen after the held-out cells were opened cannot replace the preregistered set.

## What this does and does not show

**It shows:** the 1RC parameters are identifiable across seven cells from three experiments, given a measured OCV.

**It does not show:** that the model validates on other cells. It is also silent on other temperatures, on ageing, on
charge or drive cycles, and on currents other than 2.5 A. The held-out pulses use the calibration current, so this is
cross-cell transfer, not current extrapolation.

**What would change the outcome.**
- An owner-admitted cycler current accuracy could cover the sub-mA current excess.
- It could **not** cover the temperature gap: the held-out cells reach 17.6 °C against a 23.2 °C calibration minimum,
  and the thermocouple is not the cycler's current channel. 25 of the 32 primary out-of-domain windows fall outside on
  temperature, so the primary set would stay NOT_ASSESSABLE.
- Closing the temperature gap needs calibration data spanning the held-out temperatures, or held-out cells inside the
  calibrated range, under a new preregistration.

**Blindness is spent.** The Expt 2,2 cells were partly unblinded during the role build, and all five held-out cells
were opened by the evaluation. A later evaluation on them, for example after an
owner admits the BioLogic accuracy and the domain is widened, would not be blind and must say so. A blind cross-cell
verdict needs cells that have not yet been opened.

## Changes after the held-out cells were opened (disclosed)

`evaluate.py` ran four times. Every run-1 metric and acceptance value is unchanged in the final record (a test checks
this). The three superseded records are kept in `results/superseded/`, and their digests are listed in
`VALIDATION.json` `post_opening_changes`.

1. Run 2 added descriptive fields: the out-of-domain attribution and the in-domain-only subset.
2. Run 3 gated the Rint-vs-1RC comparison verdict to NOT_ASSESSABLE for sets holding out-of-domain windows. This only
   makes the result stricter: the preregistered comparison rule gated only on fewer than 2 units.
3. Run 4 came from the independent review:
   - the unconditioned comparison label moved out of the verdict field;
   - the calibration comparison is marked IN_SAMPLE;
   - the OCV curve source text was corrected (the z = 1 knot comes from a post-charge rest shorter than 3000 s in 5 of 7
     cells, as the preregistration allows);
   - the held-out maximum current and the calibrated SOC span were added.

`data/exclusions.json` gained dropout counts and a split dropout reason. The window roles and `ocv_cal` are
byte-identical.

## Run

```bash
python -m benchmarks.battery_1rc_crosscell.data --raw-dir <bol25>   # roles (pinned)
python -m benchmarks.battery_1rc_crosscell.fit                      # CALIBRATION.json, ~4 min
python -m benchmarks.battery_1rc_crosscell.evaluate                 # VALIDATION.json, ~6 min
python -m benchmarks.battery_1rc_crosscell.outcome                  # OUTCOME.json
```
