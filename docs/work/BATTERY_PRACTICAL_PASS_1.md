# Battery Practical Pass 1: real-data ingestion, receipts, split and the 1RC identifiability gate

Branch `feat/battery-real-data-identifiability`, from Trust Repair Pass 1 `803946af`.
Not committed, pushed or certified. Nothing in this pass is calibration, validation or evidence.

## 1. Data-path audit (before any change)

| Path | Role | Reads raw bytes | Normalizes | Provenance | Scientific authority | Decision |
|---|---|---|---|---|---|---|
| `src/engcore/claims/adapters/nasa_battery_aging.py` | Maps one NASA sample to a claims `DatasetObservation`; derives SOC by coulomb counting | no | sign and unit mapping for one sample | manifest digest only | domain science living in the claims layer | keep as a compatibility shim; SOC derivation to migrate |
| `benchmarks/reference_validation/battery_nasa.py` | Benchmark normalizer from `.mat` to `ReferencePoint` | yes, with no byte pin | yes | snapshot manifest | tooling | keep as tooling, remove later |
| `tools/nasa_battery_aging.py` (PR #117, open, not in this tree) | NASA `.mat` canonicalizer with a byte receipt | yes | no sign change | byte receipt; the filename is inside the identity | tooling presented as the ingestion authority | not adopted; port its `.mat` parsing behind the canonical path once NASA bytes are pinned |
| `benchmarks/battery_flagship_b3/audit/b3_evidence.py` | B3 loader for the A123 CSVs | yes | units assumed, plausibility checked | `PROVENANCE.json` pins | benchmark-local | keep |
| `src/engcore/claims/empirical_uq_trust.py` | S-OCV production catalog | no | none | digest pins | claims trust registry | **fixed** (§5) |
| **`src/engcore/domains/battery/real_data/`** (new) | Canonical ingestion, receipt, quality, split, gate | yes, byte-pinned | yes, with explicit lineage | `BatteryDatasetReceipt` | domain layer | **canonical** |

Defects found in the older paths:

- `battery_nasa.py` truncates channels silently to their shortest length.
- `battery_nasa.py` numbers cycles across all cycle types.
- `battery_nasa.py` exports a name that does not exist (`NASA_BATTERY_ARCHIVE_URL`).
- The claims adapter derives SOC inside the claims layer.
- PR #117's identity includes the filename.
- PR #117 allows duplicate timestamps (it checks only that time is non-decreasing).
- PR #117 records no row-order identity.
- The B1/B2 flagships split one BATT_001 discharge curve by SOC: the holdout is the same cell. Those are historical benchmarks and were not modified.

## 2. Dataset

The data are Jahn 2024, Zenodo `10.5281/zenodo.11958572`, CC BY 4.0. They cover one A123 18650M1A cell (`A123_01`) in two HysPowerTest sequences, already vendored under `benchmarks/battery_flagship_b3/evidence/raw/`. No NASA bytes exist on this machine. Downloading the 209 MB archive needs the owner's approval, so NASA was not ingested.

| File | SHA-256 | Bytes | Rows | Dropped | Line endings |
|---|---|---|---|---|---|
| `…SOC100.csv` | `009c2fb085e219c7b20afaa050ac9e69d848cf04fc6e9165ce2bbd1282357feb` | 47380 | 723 | 0 | CRLF |
| `…SOC50.csv` | `d6e8b4b7ea4f832a67a859604ab8d507d2a1fdd7541cb37a485ac933dec92fd3` | 20988 | 336 | 0 | CRLF |

The receipt digest is `b22162f1237f6e7cd52873ff2d87f57cef60898233cfb9a165e87fa8aad54d5c`. It contains no local path and no ingest time.

## 3. Normalization and lineage

- **Units.** The source states none, so units are declared as second, ampere-hour, ampere and volt. They are verified in two ways:
  - The tester's ampere-hour counter matches the trapezoidal current integral to 0.098 mAh over 1.00 Ah (SOC100) and 0.052 mAh over 0.50 Ah (SOC50). This checks the time unit and the current-to-charge unit ratio, not a common scale error.
  - Every voltage lies inside the declared single-cell window of 1–5 V.
- **Sign.** The source counts charge as positive; canonical current is positive for discharge (the kernel's convention). The conversion is recorded in the lineage. It is verified by the cell's passive step response: at 4 of 4 clear steps per file, the voltage moves against the discharge current.
- **Lineage.** The charge counter is `SOURCE_COMPUTED`, not measured.
- **Temperature.** There is no temperature channel. The 25 °C chamber setpoint is metadata and is not attached to any sample.
- **SOC.** SOC is never a source channel. `DerivedChannel` carries it, with its method, version, inputs and assumptions, when it is derived.
- **What is refused, not cleaned:** NaN, inf or empty fields, ambiguous units (`C`, `deg`), dimensionally wrong units, units contradicted by the data, duplicate or reversed time stamps, mixed line endings, undeclared columns, and a sign contradicted by the step response.
- **Metadata inconsistency, classified rather than corrected.** The record calls the discharge "C/2", but the measured current is 1.10 A against a measured 0→100 % throughput of 1.00 Ah, which is about 1C. The gate uses the measured current only.

## 4. Quality

From `QUALITY.json`, SOC100:

- **Segments:** rest (1 sample), CC-CV charge, rest of 600 s, constant-current discharge at 1.10 A for 1647 s, rest of 600 s, and a 4.39 A discharge down to the 2.0 V cutoff, which ends the file with no rest.
- **Sampling:** the base interval is 10 s; every current step is bracketed by samples 2 ms apart (onsets) or 108 ms apart (interruptions).
- **Other observations:** the voltage quantization step is 190.88 µV; the rest current scatters up to 1.1 mA and is kept as recorded; one run of 68 identical voltages sits in the constant-voltage charge phase; four within-segment voltage-rate flags are recorded and none is removed.

The held-out SOC50 file is published as current structure only. No voltage feature of it is exposed.

## 5. Split

- **Unit:** test sequence.
- **Calibration:** `A123_01/HysPowerTest_SOC100`.
- **Holdout:** `A123_01/HysPowerTest_SOC50`, with the VALIDATION role.
- **Overlap:** zero groups, zero raw files, zero unit keys.
- **Shared cell:** `A123_01`. The scope is recorded as *within-cell only*: one cell exists, so no cell-level holdout is possible and none is claimed. Split digest `8a7fed5c…`.
- **Guards:**
  - `calibration ∩ holdout = ∅` holds over unit keys, group ids and raw digests.
  - `calibration_series` re-derives the split from its own policy.
  - `BatteryDataset` binds every series to its receipt entry (normalized digest, raw pin, physical keys, source membership).

**Review 3 S-OCV leak, fixed.** The production catalog filed both BATT_001 and BATT_002 on both sides of the split. It is now split by cell: BATT_001 is calibration, BATT_002 is validation. `require_independent_split` refuses the old shape at import. The leakage guard inside the model-form study was already refusing the old catalog downstream. With one group on each side, a model-form policy that asks for two groups per side now sees too little data. That is the honest result, and nothing was promoted.

## 6. Structural identifiability

- **OCV treatment.** OCV is not measured during the windows and no OCV curve is identified. Each relaxation window has one unknown constant `OCV_w`, which is marginalized out of the R0/R1/C1 information. Hysteresis is not modelled.
- **The model.** In Laplace form, `Z(s) = R0 + R1/(1 + sR1C1)`:
  - R0 is the high-frequency limit, seen as the jump across a step resolved much faster than τ.
  - R1 is the relaxation amplitude, given the polarization reached before the interruption.
  - τ = R1·C1 is the relaxation shape, and C1 = τ/R1.
- **Degenerate designs, each tested:**
  - steady or zero current: nothing separates;
  - steps sampled slower than τ: only R0 + R1;
  - a transient shorter than τ: R1 and τ are coupled;
  - an unknown polarization before the interruption: only τ is determined, and R1 and C1 are coupled.
- **Check method:** the generic rank of the exact sensitivity matrix of the design, at 8 seeded points, with the nuisance columns projected out.
- **On the A123 calibration window:** rank 3 at every point, so R0, R1, C1 and τ are each structurally identifiable.

## 7. Practical identifiability (calibration group only)

The design has one relaxation window: the last 10 s of the 1.10 A discharge (1647 s of history, 27.8 τ), then the 600 s rest (10.1 τ). The interruption is located to 108 ms (0.0018 τ). The fit is a diagnostic linearization point and is not calibrated: τ ≈ 59 s.

| Metric | Value |
|---|---|
| Sensitivity matrix | 66 × 4 (3 log-parameters plus OCV_w), normalized by the noise scale |
| Projected singular values | 27.8, 11.7, 5.49 |
| Condition numbers | 5.07 (projected), 9.12 (correlation), 17.7 (scaled Fisher) |
| Correlations | R0–R1 −0.68, R0–C1 +0.57, R1–C1 −0.72; collinearity index 2.29 |
| Noise | declared 1 mV; residual RMS 1.40 mV (n − p); residual lag-1 autocorrelation 0.81, which inflates widths ×3.12 |
| Local 95 % relative widths | R0 0.46, R1 0.24, C1 0.62, τ 0.48; the frozen rule says IDENTIFIABLE |
| Profile likelihood 95 % relative widths | R0 0.47, R1 0.25, C1 0.73; all bounded |
| Finite difference vs analytic sensitivity | 1.1e-8 |
| Horizon stability, 150 s and 300 s against 600 s | C1 ×0.68 and ×0.82 (z 9.7 and 9.4); R1 z 5.3 and 3.4; R0 z 5.4 and 4.4: **UNSTABLE** |
| Step consistency | 2 ms onsets at 1.11 A and 4.39 A read 21.7 and 21.8 mΩ, against 27.8 mΩ predicted by the 1RC model at that bracket (z 4.1 and 7.4); the 108 ms interruption is consistent (z 1.94) |
| Excitation | current levels 1.1 A and 4.4 A, but only the 1.1 A discharge has a following rest; one SOC (about 50 %); no temperature variation observable |

## 8. Decision: WEAKLY_IDENTIFIABLE → REVIEW (not CAN_CALIBRATE)

The 1RC parameters are locally and structurally determined by this window. They are not properties of the cell, for three reasons:

1. They move far outside their own 95 % intervals when the rest is shortened.
2. The residuals are strongly correlated.
3. R0 depends on the step bracket.

Possible causes, none established here: more than one relaxation time constant, OCV relaxation or hysteresis during the rest, current-level nonlinearity, and onset/interruption asymmetry.

**Blockers to calibration:**
- the analysis horizon, or a model structure that holds more time constants, must be declared before any fit;
- the record has a single relaxation at one current and one SOC, on one cell;
- the holdout is the same cell, and its only in-domain relaxation follows a 4C discharge to the cutoff.

## 9. Review

`forge-scientific-review` ran five rounds; each returned CHANGES REQUIRED, and every finding was fixed or recorded as an accepted open item (listed in `docs/work/PROGRESS.md`). The fixes:

- the noise scale used by the checks can no longer be enlarged by the caller or by misfit;
- the split and the dataset are re-derived and bound to the receipt;
- the gate re-tests the current sign from data;
- polarization from before the record is never assumed to be zero, and the two polarization bounds are capped on their sum;
- a non-default design caps the result;
- widths are inflated for residual autocorrelation.

## 10. Tests

See `docs/work/PROGRESS.md` for the exact commands and results.
