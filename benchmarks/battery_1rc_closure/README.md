# Battery 1RC scientific evidence package (`battery.thevenin_1rc`, 2026-10-14)

Branch `feat/battery-1rc-scientific-closure`, base `origin/main` `e193e573`. Local only: nothing is pushed or merged,
and no recertification has been run.

**Outcome:** PARTIALLY_CLOSED. The official ledger computes **FUNCTIONAL** (it was FOUNDATION):
- `execution`, `provenance_replay`, `real_data` and `benchmark_metrics` now PASS with evidence.
- `calibration` is NOT_IDENTIFIABLE.
- Cross-cell `independent_validation` FAILS acceptance.
- `measurement_uq` is UNKNOWN.

So no EVIDENCE_BACKED claim is made.

## 1. Executable 1RC model and replay (Rock A)

`src/engcore/domains/battery/thevenin_route.py` defines `battery.cell.thevenin_1rc@0.1.0`. The route consists of:
- a realization, `.exact_piecewise_constant`;
- a solver, `engcore.battery.thevenin_1rc_march@0.1.0`;
- typed parameter sets, initial states and profiles. Positive current means discharge; charge is refused; SOC is never clipped.
- validity over the whole march (temperature range, current utilization, SOC);
- a `ScientificResult` whose provenance comes from `ExecutionBinding.from_execution`, with UNKNOWN uncertainty on every output;
- `replay_thevenin_1rc`, which refuses a stale, altered or non-reproducing record.

The route is **not** registered in the production registry, MCP or the domain pack. It is verified against independent
references in `tests/domains/test_battery_thevenin_route.py`:
- an adaptive DOP853 integration of the ODE agrees to < 1e-9 V;
- splitting an interval changes nothing (exact update);
- rest relaxation is exact;
- as R1 → 0 it matches the production Rint kernel to < 1e-11 V;
- the τ ≪ dt and τ ≫ dt limits hold;
- the superposition check detects a perturbed update.

## 2. Source data and receipts (Rock B)

| Item | Value |
|---|---|
| Archive | NASA PCoE "5. Battery Data Set.zip" (data.nasa.gov, Li-ion Battery Aging), 209,708,670 bytes, sha256 `82302a7d…f2e`. It is kept outside the repo, in `D:/forge-data/nasa_pcoe_battery/` |
| Cells | B0005 `.mat` sha256 `0eae4585…`, B0006 `fa818ab4…`, B0007 `d022afa0…`. All ingested by `tools.nasa_battery_aging` (canonical `7f53903b…`, `9c6d599b…`, `f4275bc9…`) |
| Refused | B0018: the importer fails closed on `cycle[114].Voltage_measured[940] = NaN`, and the file is never repaired |
| Preregistration | v1 `35bb500c…`. v2 `408f9dc4…` amends it **before any fit**: NASA's `Capacity` is defined to 2.7 V, but B0007 discharges to 2.2 V, so the capacity basis became the integrated measured charge |
| Trajectories | calibration `f295bebc…` (38 cycles), within-cell holdout `af31c944…` (20), cross-cell B0006 `1db6db35…` (29). 0 cycles refused under v2 |

Declared trajectory rules (preregistered, never presented as evidence):
- Forge current = −`Current_measured`, checked per cycle by the passive step response;
- currents within ±10 mA are rest;
- backward hold of the measured current;
- full-charge screen of 4.15 V;
- z0 = 1, with a causal capacity basis;
- v_p0 = 0, with its basis stated;
- coulombic efficiency η = 1, for discharge only.

## 3. Calibration and identifiability (Rock C): NOT_IDENTIFIABLE

Recorded in `results/CALIBRATION.json` (`a302989a…`):

| Model | Calibration RMSE | Parameters |
|---|---|---|
| Rint | 56.7 mV | — |
| 1RC | 48.4 mV | R0 0.132 Ω, R1 0.226 Ω, C1 760 F, τ 172 s |

- The profiles for R0, C1 and τ rise by less than 10% within a factor of 3, so the preregistered rule refuses them. R1 alone passes the profile test.
- The fitted 1RC OCV reaches its 4.5 V bound at SOC 0.9. With one 2 A current level, the OCV table absorbs the RC branch: OCV(z) and R0 + R1 are confounded.
- The bootstrap coefficients of variation (3–7%) are misleadingly small. A one-sample shift in the switch time (forward hold) moves R1 by +25% and C1 by +23%.

**Protocol required to identify the parameters:**
1. An OCV characterization: a C/20 discharge, or GITT rest points.
2. Multi-level current pulses, sampled at ≥ 1 Hz, with rests ≥ 5 τ.
3. A new preregistration covering both.

## 4. Rint vs 1RC held-out comparison (Rock D)

Recorded in `results/VALIDATION.json` (`ff6f1956…`). The held-out data was opened once. After the scientific review the
results were re-reported from the same frozen calibration: no data was reopened and no threshold changed. Acceptance was
50 mV RMSE and 90 mV P95 (the earlier Gate A limits), and it is now gated by applicability: a set containing a cycle the
route judges outside its validated domain cannot PASS.

| Set | Model | RMSE | MAE | Bias | Max abs | P95 | Lag-1 autocorrelation | Body / tail RMSE | Acceptance |
|---|---|---|---|---|---|---|---|---|---|
| Within-cell (B0005/B0007, ordinals 21–30), narrow | 1RC | 49.7 | 15.3 | +0.7 | 869 | 59.1 | 0.76 | 48.0 / 86.4 | **NOT_ASSESSABLE**: the thresholds are met, but 12 of 20 cycles are outside the domain |
| | Rint | 54.1 | 15.9 | −0.9 | 856 | 69.1 | 0.67 | 47.7 / 148.8 | FAIL |
| Cross-cell (B0006, ordinals 2–30), transfer | 1RC | 89.2 | 32.4 | −26.5 | 1104 | 115.7 | 0.92 | 83.1 / 392.6 | **FAIL** |
| | Rint | 93.1 | 34.3 | −30.2 | 1105 | 118.2 | 0.84 | 83.5 / 492.6 | **FAIL** |

All values are in mV.

**Paired cycle bootstrap of RMSE(Rint) − RMSE(1RC)**, scoped to these cycles from 2 independent cells (within-cell) and 1 (cross-cell):

| Set | Overall | Constant-current body | Rest tail |
|---|---|---|---|
| Within-cell | 4.3 mV [2.8, 6.0] | **not distinguished** | 62 mV [49, 81] |
| Cross-cell | 3.9 mV [2.4, 5.4] | 0.4 mV [0.3, 0.5] | 100 mV [91, 110] |

- The 1RC's advantage is the rest relaxation; on the constant-current body the two models are tied.
- **Domain margins** (per cycle in the record): at most 0.46 °C below the calibration temperature range and 0.26 % over the calibration maximum current. The preregistered range is the calibration min–max, so measurement-level excursions trip it. It is not widened after the fact.
- **In-domain cycles only** (descriptive, not preregistered): within-cell 8 cycles, 1RC 42.6 mV against Rint 48.8 mV; cross-cell 23 cycles, 1RC 77.5 mV against Rint 79.5 mV.
- **Bindings:** every 1RC held-out prediction records its route `result_id`, `replay_record_sha256` and parameter-set and profile digests, and a test reproduces one.
- **Cross-cell capacity basis:** it comes from B0006's own earlier cycles (causal). The set tests the transfer of the voltage model, not the transfer of capacity.
- **Rint evaluation:** loaded intervals use the production kernel. That kernel refuses I = 0, so rest intervals use V = OCV(z). This is disclosed in the record.
- **Plots:** `results/plots/*_voltage.svg` (measured vs predicted) and `*_residual.svg`.

## 5–6. Uncertainty, discrepancy, applicability (Rock E)

Recorded in `results/UNCERTAINTY_REPORT.json` and `results/SENSITIVITY.json`. No total is combined.

| Component | Status | Basis |
|---|---|---|
| Measurement | **UNKNOWN** | NASA states no calibrated uncertainty. Instrument calibration evidence is required |
| Parameter | NOT_ADMISSIBLE | The joint bootstrap band is ±1.2 mV and covers 5–15 % of held-out samples, and it is invalid for non-identified parameters |
| Numerical | NOT_APPLICABLE | The update is exact; independent references agree to < 1e-9 V |
| Initial state | Partially quantified | v_p0 = ±20 mA × R1 changes the objective by less than 0.1 % (the physical sign after a CV charge is negative) |
| Input reconstruction | **NOT_REDUCED** | The ~19 s current sampling leaves the switch time unknown. The forward hold changes the objective by ×1.34 and moves R1 by +25 % and C1 by +23 %. This is not numerical, and it is never N/A |
| Model form | Not quantified as UQ | Residuals are 41–79× the parameter band, with lag-1 autocorrelation 0.76–0.92. The error is structured; it is never zero, and it cannot be separated while measurement uncertainty is UNKNOWN |

**Supported regime:** 2 A CC discharge plus rest, ~24 °C, FY08Q4 cells within 30 discharges.

**Unsupported:** other currents, pulses, charge, temperatures or ageing states, and the parameters as physical constants.

**Not analysed:** the sensitivity to the ±10 mA rest band.

**Open, before claims integration:** the parameter set's temperature and current range is declared by the caller and decides IN_DOMAIN. It must be bound to a calibration record.

## 7–8. Tests

- `benchmarks/battery_1rc_closure/tests` has 22 tests: identities, the transcription equals the route on real cycles, malformed and misleading cycles, a changed data file, the refusal of the raw-bytes rebuild check when the `.mat` files are absent, applicability-gated acceptance, replay binding of held-out predictions, leakage, identifiability refusal, the multistart basin, Rint-better reporting, claim scope, and ledger honesty.
- `tests/domains/test_battery_thevenin_route.py` has 24 tests.
- Rerunning fit → evaluate → uq reproduces every scientific number bit for bit. Only the wall-clock timing fields differ.

## Reproduce

Run Python with `PYTHONPATH="<worktree>/src;<worktree>"` (Windows) or `<worktree>/src:<worktree>` (POSIX).

1. Download the archive from the URL above and check its sha256.
2. Extract the nested zips as data only, and run `python -m tools.nasa_battery_aging <B000x.mat> --cell-id B000x --out <dir>/B000x.canonical.json` for B0005, B0006 and B0007.
3. Build the trajectories:
   - `python -m benchmarks.battery_1rc_closure.data --role calibration --canonical-dir <dir>`
   - then the same command with `--role within_cell_holdout` and `--role cross_cell_validation`.
4. Run `python -m benchmarks.battery_1rc_closure.fit`.
5. Run `python -m benchmarks.battery_1rc_closure.sensitivity`.
6. Run `python -m benchmarks.battery_1rc_closure.evaluate`.
7. Run `python -m benchmarks.battery_1rc_closure.uq`.
8. Run the raw-bytes check: `python -m benchmarks.battery_1rc_closure.data --verify-raw <dir with B0005.mat…>`. It
   exits 1 and lists every problem if any pinned role fails to rebuild. It is a command rather than a test because the
   raw files are not shipped, and the hardened gates admit no unexplained skip.
