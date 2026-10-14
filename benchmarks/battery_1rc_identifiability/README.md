# Battery 1RC identifiability and independent evidence (`battery.thevenin_1rc`, 2026-10-14)

Branch `feat/battery-1rc-identifiability` (worktree `D:/forge-battery-ident`). It is stacked on
`feat/battery-1rc-scientific-closure` (`50671ebd`), because it needs that branch's 1RC route; that branch is not modified.
Local only: nothing is pushed or merged, no certificate is touched, and no recertification has been run.

## Verdict

| Item | Result |
|---|---|
| Experimental outcome (frozen mapping) | **MODEL_REJECTED**: identifiable; the held-out pulses pass the pooled limits; the held-out constant-current test fails marginally. Without the preregistered ±1 °C temperature widening, that test would be out of domain and the outcome would be **IDENTIFIABILITY_SUPPORTED** |
| Identifiability on qualified data | **IDENTIFIABLE**: R0 20.7 mΩ, R1 15.6 mΩ, C1 1586 F, τ 24.8 s |
| Ledger | `calibration` PASS, **scoped**: one LG HG2 cell (SN62A4), 25 °C, pulse time scale, SOC ≥ 0.10, OCV measured rather than fitted, OCV-knot uncertainty not propagated. `independent_validation` and `measurement_uq` remain MISSING. The computed stage is **FUNCTIONAL** (unchanged) |
| Battery 1RC | **NO-GO** for EVIDENCE_BACKED, claims integration or DomainPack integration. **GO** for one bounded next step: a cross-cell pulse-scale evaluation |

## 1. Independent verdict on the NASA results (WP1)

An independent read-only reviewer judged the NASA results **SOUND_WITH_CAVEATS**. Those results are immutable: a test
pins their four record digests, and they are not re-evaluated here.

**Confirmed sound:**
- the calibration/held-out separation (no code path reads a held-out role while fitting);
- the declared initial state;
- capacity integration consistent with the trajectory;
- applicability gating that can only downgrade a result;
- a fair Rint comparison;
- correct ledger reporting.

**Caveats that travel with the NASA results:**
1. The fitted parameters are not physical. The OCV is offset by exactly 2 A × ΔR = 0.231 V, it is non-monotone, it reaches the 4.5 V bound, and it misfits the measured rest at z = 1 by 123 mV. That offset is the substantive evidence of OCV–resistance confounding.
2. NOT_IDENTIFIABLE is the preregistered outcome, but it sits close to the threshold. The lowest decisive profile ratio is 1.082 against a 1.10 rule; at an 8.2 % rule the decision would flip. The single 2 A current level is the robust reason.
3. The cross-cell failure and the large tail errors are entangled with the stale "maximum of earlier cycles" capacity basis, which does not follow fade. They are not purely a test of voltage-model transfer, and the closure README's wording overstates that.
4. The 1RC advantage there is a rest-tail effect on few samples (39 cross-cell). The cross-cell body comparison is "1RC better by 0.4 mV [0.28, 0.51]", not a tie. The 1RC tail error is still 86–393 mV.
5. Within-cell NOT_ASSESSABLE comes from a conservative gate added after the held-out data was opened. The PASS it replaced had a 0.26 mV margin.
6. The comparison covers 2 cells (the calibration cells) and 1 cell. The hold convention moves R1 by 25 %. Measurement uncertainty is UNKNOWN.
7. The closure's binding digests change on every rerun, because a timing field fed them. The raw-bytes rebuild there is opt-in and skips by default. This round avoids both: timings are kept in unpinned `TIMINGS_*.json` files, and a manual rerun in this session reproduced `CALIBRATION.json` and `VALIDATION.json` byte for byte (recorded in PROGRESS; no test checks it).
8. Found while reviewing this round: the closure's acceptance let an out-of-domain set FAIL. Its cross-cell FAIL includes 6 cycles the route judged out of domain, so under "contradiction requires admissible evidence" that FAIL is not admissible as a rejection. In-domain cycles only (descriptive): 1RC 77.5 mV, still above 50. This round's acceptance makes any out-of-domain set NOT_ASSESSABLE in both directions.

## 2. Candidate datasets (WP2)

| Dataset | Licence | What it offers | Verdict |
|---|---|---|---|
| **LG HG2, McMaster (doi:10.17632/cp3473x7xv.3)** | CC BY 4.0 | 4-pulse HPPC at 15 SOC levels, sampled at 0.1 s with 1 h relaxed rests (a measured OCV); C/20, 0.5C, 1C and 2C tests; drive cycles; six temperatures. The readme states instrument accuracy (0.1 % of full scale, AD592 ±1 °C) | **QUALIFIED and used**, with limits: **one cell**; the drive cycles contain regenerative charge, which is outside the discharge-only route; the C/20, 0.5C and 2C files lack a preceding rest. The 25 °C bytes match Mendeley's sha256 (they were vendored on `claude/domain-real-data`) |
| Jahn 2024 A123 (Zenodo 10852930) | CC BY 4.0 | Incremental and pseudo OCV; HysPowerTest power steps; tester specification as transcribed by a distributor | Partial. One LFP cell, power tests at a 10 s median interval, no temperature channel. An earlier local pass found the 1RC WEAKLY_IDENTIFIABLE |
| Kirkaldy 2024 LG M50T (Zenodo 10637534) | CC BY 4.0 | Several cells per condition at 10/25/40 °C with periodic reference tests | **Best cross-cell candidate, NOT ACQUIRED.** Only summary tables are local. The raw reference-test data (pulse content and sampling to be verified) is a multi-GB download that needs owner approval |
| Panasonic 18650PF (Mendeley) | CC BY 4.0 | HPPC, C/20, drive cycles, five temperatures | Weaker. Instrument accuracy not stated; one cell that aged from 2.8 to 2.3 Ah during testing |
| Chen 2020 LG M50 (Zenodo 4032561) | CC BY 4.0 | Three cells; CC discharges at C/10 to 1.5C | Not suitable for transients (30 s sampling, no pulses). Possibly useful for cross-cell OCV + resistance checks |
| NASA PCoE FY08Q4 | NASA open data | One 2 A CC level, ~19 s sampling, no stated uncertainty | Used by the closure: NOT_IDENTIFIABLE (§1) |

## 3. Identifiability and validation requirements (what the evidence shows is needed)

1. **A measured OCV.** With the OCV fixed from relaxed rests, R0, R1 and C1 are identified robustly (profiles rise 1.2–600×, bootstrap CV 1–9 %). With a fitted OCV and one current level (NASA) they are not.
2. **At least two pulse current levels sampled at ≤ 0.1 s, with rests ≥ 5 τ.** The switch-time shift was 25 % on NASA and at most 6 % on LG HG2.
3. **Several independent cells.** No cross-cell evaluation is possible with LG HG2.
4. **A model scope matched to the time scale.** One RC fitted to 10 s pulses passes held-out pulses but fails a one-hour 1C constant-current discharge (bias −25 mV). Any claim must either be pulse-scale only, under a new preregistration, or wait for evidence that a richer model is needed. No physics is added here.
5. **Admissible measurement uncertainty.** A publisher-stated Type B accuracy exists for LG HG2 and nothing exists for NASA. Whether a publisher statement is admissible is an owner/review decision.

## 4. The preregistered evaluation (WP3–WP4)

**Order of record (commit history):**
1. Preregistration `f06905dc` (`d8acfb26…`).
2. Data roles `a4e83f72`.
3. Calibration `6e69f0c9`, committed before any held-out comparison.
4. Held-out evaluation `ec788c2f`, opened once.
5. Tests and outcome `709a46de`.
6. Ledger `c99b1781`.

**Data construction:**
- The OCV is 12 knots measured from relaxed HPPC rests, SOC 0.027–1.0. It is fixed, not fitted.
- Calibration uses 18 windows of 3 A and 18 A pulses. The held-out set has 20 windows of 6 A and 12 A pulses (current interpolation) plus the separate 1C capacity test.
- 11 exclusions are recorded with reasons: truncated pulses, SOC below 0.10, insufficient rest, and the C/20 test (no preceding rest).
- The applicability range comes from the measured calibration temperatures widened by the published ±1 °C, and the maximum current is 18 A plus the 75 mA accuracy.
- The route needs an OCV over [0, 1], so the charge axis is re-expressed exactly onto the measured knot range; no voltage is extrapolated. A test checks route = transcription to within 1e-9 V.

**Results** (all held-out units are in domain; mV):

| Set | Model | RMSE | P95 | Bias | Max | Load / rest RMSE | Acceptance |
|---|---|---|---|---|---|---|---|
| Calibration (18 windows) | 1RC | 8.4 | 16.3 | −1.4 | 61 | 11.9 / 7.5 | — |
| | Rint | 31.9 | 68.3 | −19.4 | 154 | 24.5 / 33.2 | — |
| **Held-out 2C/4C pulses (20)** | 1RC | **12.6** | **27.4** | −5.8 | 98 | 19.7 / 10.5 | **PASS** (≤ 15 / 30) |
| | Rint | 29.6 | 57.0 | −21.2 | 160 | 26.8 / 30.2 | FAIL |
| **Held-out 1C CC test (1)** | 1RC | **28.7** | **50.7** | −25.1 | 54 | 28.9 / 7.4 | **FAIL** (≤ 25 / 50) |
| | Rint | 64.7 | 89.1 | −62.6 | 92 | 65.2 / 7.4 | FAIL |

**Reading the PASS and the FAIL** (review corrections; the thresholds and the mapping are unchanged):
- **The pulse PASS is pooled.** 83 % of the scored samples are rest samples, and they sit next to OCV knots logged minutes earlier in the same record. Under load alone, the 1RC RMSE is 19.7 mV, above 15 (reported in the record as not preregistered). The test covers current interpolation only.
- **The constant-current FAIL is marginal.** It is over by 3.65 mV (RMSE) and 0.67 mV (P95), both below the ±5 mV voltage accuracy, which is not admitted.
- **Its admissibility rests on the preregistered ±1 °C widening.** The case temperature was 23.77–25.24 °C against an unwidened calibration range of 23.56–24.61 °C.
- **Its initial state rests on a 10 s visible rest**, weaker than the 590 s the pulse windows require.
- **What is rejected is the bundle:** the parameters, the measured OCV, the Q_HPPC charge basis, z0 = 1 and v_p0 = 0. It is not "one RC" alone.
- **The route does not enforce SOC ≥ 0.10.** Only the role builder does, so the route's `in_domain` does not certify SOC.

**Comparison (paired window bootstrap, one cell):**
- Held-out pulses: 1RC better by 17.1 mV [14.6, 20.0], both under load and at rest.
- The constant-current set has **one** unit, so its verdict is NOT_ASSESSABLE: the difference is a point value, not an interval.

**Parameter uncertainty:** the joint bootstrap band is ±1–2 mV and covers 23 % of held-out pulse samples. Model form dominates, and the residuals are structured (lag-1 autocorrelation 0.94).

**Descriptive only:** the 0.9 A SOC-step windows with their 1 h relaxations give 1RC 9.2 mV against Rint 12.9 mV.

**Hypotheses for the constant-current failure, which are not evidence:** slower diffusion beyond one time constant, a rate-dependent OCV offset, a capacity-basis offset between test days, and self-heating.

## 5. Remaining capability gates (official ledger)

| Gate | Status |
|---|---|
| `calibration` | PASS (LG HG2) |
| `independent_validation` | MISSING: no cross-cell evaluation, and the constant-current test fails |
| `measurement_uq` | MISSING: owner decision on publisher Type B |
| `parameter_uq` | MISSING: OCV-knot uncertainty not propagated |
| `model_discrepancy` | MISSING |
| `claims_integration`, `domainpack_integration` | MISSING |
| `numerical_uq` | NOT_APPLICABLE (exact update; input reconstruction is tracked under measurement) |

Computed stage: **FUNCTIONAL**.

## 6. Code changes

There are no changes to `src/`: the existing route, the importer and the reader conventions are reused. The new code
lives under `benchmarks/battery_1rc_identifiability/`:
- an LG HG2 byte reader with declared repeat rules;
- the role builder, the fit (OCV fixed), the evaluation and the outcome;
- 19 adversarial tests, plus an opt-in raw-bytes rebuild (`FORGE_LGHG2_DIR`).

Two pinned tests were updated to the new ledger state: the closure's ledger-honesty test and the active-epic pin.

## 7. Integration plan (one frozen source, one recertification)

- **The certification-sensitive changes are on the closure branch:**
  - a new model definition under `engcore.domains` (the production-registry pin moves);
  - `test_battery_thevenin_route.py`, `test_evidentiary_level_audit.py`, `test_capability_completion.py` and `test_core_guards.py`.
- **This branch adds only `benchmarks/**`, the ledger, the matrix and one test edit.** It triggers recertification (tests/**) but changes no certified source.
- **Order:**
  1. Owner approval.
  2. Merge `feat/battery-1rc-scientific-closure`, then this branch (a fast-forward of it).
  3. If approved, merge the separate G0/A1 candidate `integration/g0-a1-unblock`. A trial `git merge-tree` against
     this branch conflicts only in the append-only `docs/work/ACTIVE_PLAN.md` and `docs/work/PROGRESS.md`; no code or
     test file is shared. The trial merge's certificate checks are in PROGRESS.
  4. Run the FAST, regression and changed-file gates on the frozen merge commit.
  5. Run **one** owner hardened recertification of that exact SHA.
- **Data:** the LG HG2 raw CSVs stay outside the repo (`D:/forge-data/lg_hg2/raw`, sha-pinned in the preregistration). They are also vendored on the pushed `claude/domain-real-data` branch. Merging that branch instead would let the raw-bytes test run by default.

## Reproduce

Run Python with `PYTHONPATH="<wt>/src;<wt>"`.

1. Get the five LG HG2 CSVs: either `git show origin/claude/domain-real-data:benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/<f>`, or a download from Mendeley. Check their sha256 against `PREREGISTRATION.json`.
2. Run `python -m benchmarks.battery_1rc_identifiability.data --raw-dir <dir>`.
3. Run `python -m benchmarks.battery_1rc_identifiability.fit`, then `python -m benchmarks.battery_1rc_identifiability.evaluate`, then `python -m benchmarks.battery_1rc_identifiability.outcome`.
4. Run the tests: `FORGE_LGHG2_DIR=<dir> pytest benchmarks/battery_1rc_identifiability/tests`.
