# battery_rediscovery_v3 (BR-BATT-REDISC-04): the sealed GEN1 Mind on a stronger real-data baseline

Branch `research/battery-rediscovery-v3-gen1-baseline` (worktree `D:/forge-redisc-v3`), based on the v2 head
`b8160e21`. Local only. This is a development baseline. It is not formal, not certified, and not a discovery claim.
No Mind code was changed: the candidate is `benchmarks.battery_rediscovery_v2.candidate.run`, imported unchanged and bound
by [`docs/discovery/mind_gen1_reference.json`](../../docs/discovery/mind_gen1_reference.json).

| Commit | Step |
|---|---|
| `8bd0d499` | Part A: GEN1 reference sealed |
| `5023fe92` | asset census and CandidateBundle (structural, no fit) |
| `82917615` | failing-first tests of the evaluation rules |
| `07a7604f` | pre-run freeze (PLAN `2b549035…`) |
| `9e018614` | sealed outputs (SEAL `033cae41…`) |
| `16dfe967` | sandboxed replay, post-seal mutation suite |
| `c40bf360` | evaluation (truth computed here for the first time) |

## Result (preregistered rule): GEN1_REAL_DATA_ADVANTAGE_CONFIRMED

| Axis | Old Mind | Representation | Roles | Combined | Careful | Decided N |
|---|---:|---:|---:|---:|---:|---:|
| MODEL_ADEQUACY | 0/24 | 0/24 | 0/24 | 24/24 | 23/24 | 24 |
| IDENTIFIABILITY | 21/31 | 31/31 | 21/31 | 31/31 | 10/31 | 0 |
| WITHIN_CELL | 0/31 | 0/31 | 0/31 | 31/31 | 31/31 | 31 |
| CROSS_CELL | 5/23 | 5/23 | 5/23 | 23/23 | 23/23 | 18 |
| MODEL_DISCREPANCY | 31/31 | 31/31 | 31/31 | 31/31 | 0/31 | 0 |
| CORRECT_REFUSAL | 57 | 67 | 57 | 67 | 15 | - |
| FALSE_SUPPORT | 0 | 0 | 0 | 0 | 0 | - |
| FALSE_REFUSE | 73 | 73 | 73 | 0 | 1 | - |
| REPLAY | 33/33 EXACT | 33/33 EXACT | 33/33 EXACT | 33/33 EXACT | 33/33 EXACT | - |

Each cell is correct (CORRECT + CORRECT_REFUSAL) over the scored primary instances on that axis. The primary set has
155 instances (31 problems × 5 axes): 73 decided, 67 whose correct answer is a refusal, and 15 unscored (inside the
1.10 margin band; 0 from reference disagreement).

| Arm | decided correct (Wilson 95 %) | held-out correct (Wilson 95 %) | unsupported decisions | vs OLD_MIND W/L/T | vs CAREFUL W/L/T |
|---|---|---|---:|---|---|
| Combined | 73/73 (0.950–1.000) | 49/49 (0.927–1.000) | 0 | 73/0/0 (p = 2e-22) | 1/0/72 (p = 1.0) |
| Careful | 72/73 (0.926–0.998) | 49/49 (0.927–1.000) | 52 | 72/0/1 | — |
| Old Mind, Representation-only, Roles-only | 0/73 | 0/49 | 10 / 0 / 10 | — | 0/72/1 |

| Evidence-strength axis | Result |
|---|---|
| TOTAL_DECIDED_INSTANCES | 73 |
| HELD_OUT_DECIDED_INSTANCES | 49 |
| INDEPENDENT_CELLS | 19 |
| OPERATING_CONDITIONS | 5: GITT pulses at beginning of life; GITT pulses aged (latest RPT); constant-current rate tests 0.5–7.5 A; 43 C at 4 A; 4 C at 2 A |
| SINGLE_INSTANCE_ROBUST | YES (146 removals and flips, 0 breaking) |
| IMPLEMENTATION_CORRELATED_INSTANCES | 0 |
| LEAKAGE | PASS (pre-run, pre-seal and post-seal; mutation 1361/1361 caught, 0/706 benign) |
| REPLAY | EXACT (264/264 outputs, repsem 66/66 EXACT, Mind traces 90/90 VERIFIED) |

Every hypothesis holds under its frozen operationalisation:
- **H1:** false refusals 73 → 0; at least 14 fewer were needed.
- **H2:** the combined arm beats both single-layer arms.
- **H3:** 49 held-out decided instances, with a Wilson lower bound of 0.927 (at least 0.5 was needed).
- **H4:** the result is robust to every single-instance perturbation.

## Read this before citing the result

- **The advantage is over OLD_MIND and the single-layer arms, not over a careful analyst.** On decided instances the
  combined arm and CAREFUL_BASELINE tie 72 times; the combined arm wins once and loses none. What separates them is
  refusal discipline. CAREFUL issues 52 decisions where the correct answer is a refusal: identifiability and
  discrepancy with no declared noise.
- **The zeros of OLD_MIND and the single-layer arms are structural,** as in v2:
  - The v1 vocabulary cannot judge adequacy or discrepancy.
  - The legacy roles refuse binding.
  So the paired win over OLD_MIND (73/0) measures "can represent and decide the declared question". It does not
  measure better scientific judgment on questions both arms could answer.
- **This shows correct implementation, not physics.** The combined arm, reference A and the independent reference B
  answer the same declared semantics (bars, margins, domain rule):
  - A and B disagree on 0 of 155 instances.
  - B shares no optimizer with the candidate.
  - The combined arm matches the truth on all 73 decided instances.
  Together this shows that GEN1's declared-family judgments are implemented correctly on 19 unused real cells. It is
  not an independent check that the bars or the 1RC family are the right science.
- **Most decided truths are failures of the 1RC family.** 58 of the 73 are NOT_SUPPORTED, at reference-B RMSE
  1.0–4.6× the bar (a NOT_SUPPORTED needs RMSE or p95 above 1.10× its bar).
  - The GITT problems use the inherited 15 mV pulse-class bar, which was set for 10 s pulses; these are 288 s.
  - The rate tests and NASA runs use 50 mV.
  Only 15 decided instances are SUPPORTED (1 adequacy, 8 within-cell, 6 cross-cell), at 0.35–0.86× the bar.
- **Identifiability and discrepancy are refusal tests only.** No primary dataset publishes a voltage accuracy, so the
  uncertainty is UNKNOWN (never invented). All 62 instances on those axes have a NOT_ASSESSABLE truth; none is
  decided.
- **Degeneracy is visible, not erased.** The 43 C NASA problems P28 and P29 reproduce v2's degenerate fit: R1 on its
  1 Ω bound and τ ≈ 5000–6400 s, longer than the run. Both the references and the candidate's own sealed parameters
  flag it. Their adequacy and within-cell truths are NOT_SUPPORTED, so no SUPPORTED answer rests on a degenerate fit
  in the primary set. Other flags:
  - Equivalent-τ profiles on P07 and on the three rate-test problems; the rate-test problems also show |ρ| > 0.95.
  - The two SUPPORTED-on-degenerate cases are both on unscored instances (P25 adequacy, bridge Q1 adequacy).
- **Instances are not all independent.**
  - RPT0 and the latest RPT of a cell are two problems on the same cell.
  - The cross-cell windows of one problem are the partner's within-cell windows in another.
  - INDEPENDENT_CELLS counts physical cells (19).
- **The developer is not blind to history.** The census marks every unit whose 1RC/voltage outcome was in the
  evaluator's context as SECONDARY or excluded; none is primary. The eligibility rules and the decimation were
  written knowing the files' protocol structure (segment durations, sampling, charge termination), never a fit.
- **Bridge.** v2's Q1 and Q2 were re-run under the v3 harness. They reproduce v2's sealed outputs byte for byte, for
  every arm, and the v3 references reproduce v2's truths on both. The bridge is not counted in the conclusion.

## Design (frozen in PLAN.json)

- **Census** (`EvaluatorVault/CENSUS.json`). Every local battery dataset is classified per cell and condition, with
  its prior FORGE use and exposure. 20 cells are ELIGIBLE_PRIMARY_V3:
  - NASA B0029–32 and B0051;
  - Kirkaldy 2024 Expt 4 and Expt 5, cells A, B, C, F, G, H (never in a 1RC study);
  - Chen 2020 LG M50 cells 02, 03 and 04.
  27 units are secondary-only and 23 ineligible, each with its reason. The 4 C NASA groups fail the charge-termination
  screen.
- **Problems** (`build_pack.py`, structural eligibility only):
  - 24 Kirkaldy GITT problems: 12 cells × {RPT0, latest RPT}. The measured OCV comes only from the calibration rests.
    Calibration uses alternate charge-state pulses; within-cell held-out uses the others; cross-cell held-out uses a
    partner cell.
  - 3 Chen rate-test problems with a fitted OCV. Calibration is 0.5 A and 7.5 A; held-out is 2.5 A and 5 A (rate
    interpolation) on the same cell and on a partner.
  - 4 NASA single-cell problems with a fitted OCV, later-life held-out runs, and no cross-cell set (cutoffs differ).
    B0031 was refused by the fixed design.
  Bars, bounds and scope margins are inherited from v1/v2.
- **Truth** (`evaluator/truth.py`):
  - Reference A is v2's protocol, unchanged. It shares TRF and the identifiability classifier with the candidate.
  - Reference B (`evaluator/reference_b.py`) uses variable projection over ln τ with exact bounded linear least
    squares (BVLS), its own recursion, and a finite-difference Jacobian.
  - Equal truths decide; any disagreement is unscored.
- **Degeneracy** (`evaluator/diagnostics.py`). FIT_OK, PARAMETER_DEGENERACY, IDENTIFIABILITY_LIMIT and
  MODEL_DISCREPANCY are recorded per problem and never collapsed into a score.
- **Conclusion** (`evaluator/conclusion.py`). Gates run first: leakage, then replay, then truth sufficiency (≥ 20
  decided and ≥ 10 held-out decided). CONFIRMED needs all of:
  - C1, a paired sign test against OLD_MIND;
  - C2, no material false-support increase;
  - C3, a win over both single-layer arms;
  - C4, a held-out improvement plus H3;
  - single-instance robustness. Otherwise the verdict is BENCHMARK_UNDERPOWERED.
- **Blindness.** CandidateBundle, EvaluatorVault and TruthBundle are separate directories, and the runtime audit
  forbids the vault, the truth bundle, the v2 pack and every v0/v1/v2 results directory. `launch.py` refuses to run
  the candidate once a TruthBundle exists. `truth.py` refuses until the seal and the replay are committed.

## Commands

All run with `PYTHONPATH="D:/forge-redisc-v3/src;D:/forge-redisc-v3"` and the phyx `.venv` Python 3.14:

```bash
python -m benchmarks.battery_rediscovery_v3.gen1_reference --check
python -m benchmarks.battery_rediscovery_v3.extract --verify-archives
python -m benchmarks.battery_rediscovery_v3.census
python -m benchmarks.battery_rediscovery_v3.build_pack
python -m benchmarks.battery_rediscovery_v3.mutation --phase pre_run
python -m benchmarks.battery_rediscovery_v3.freeze --pre-run-audit
python -m benchmarks.battery_rediscovery_v3.freeze
python -m benchmarks.battery_rediscovery_v3.launch run
python -m benchmarks.battery_rediscovery_v3.seal
python -m benchmarks.battery_rediscovery_v3.launch replay
python -m benchmarks.battery_rediscovery_v3.mutation --phase post_seal
python -m benchmarks.battery_rediscovery_v3.evaluator.run_evaluation
```

The raw inputs are in `D:/forge-data` (NASA archive, Kirkaldy archives with Zenodo md5 verified, Chen 2020 files).
