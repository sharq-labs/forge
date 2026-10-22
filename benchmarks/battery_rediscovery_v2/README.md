# battery_rediscovery_v2 (BR-BATT-REDISC-03): fresh real-data confirmation of the representation + roles repair

Branch `research/battery-rediscovery-v2` (worktree `D:/forge-redisc-v2`), based on the repsem repair head `86034639`.
Local only. This is a development experiment: not formal, not certified, not a discovery claim.

| Commit | Step |
|---|---|
| `f6229986` | pre-run freeze (PLAN.json `85f1b7f3…`) |
| `ee3a6946` | sealed outputs (SEAL.json `843c6e14…`) |
| `6a75d816` | sandboxed replay, post-seal mutation suite |
| `625f5fea` | evaluation (truth computed here for the first time) |

## Result (preregistered rule): REAL_DATA_IMPROVEMENT_CONFIRMED, on thin evidence

| Axis | Old Mind | Representation | Roles | Combined | Careful |
|---|---:|---:|---:|---:|---:|
| MODEL_ADEQUACY | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 |
| IDENTIFIABILITY | 1/2 | 1/2 | 1/2 | 2/2 | 2/2 |
| WITHIN_CELL | 0/1 | 0/1 | 0/1 | 1/1 | 1/1 |
| CROSS_CELL | 1/2 | 1/2 | 1/2 | 2/2 | 2/2 |
| MODEL_DISCREPANCY | 1/2 | 1/2 | 1/2 | 2/2 | 1/2 |
| CORRECT_REFUSAL | 3 | 3 | 3 | 3 | 2 |
| FALSE_SUPPORT | 0 | 0 | 0 | 0 | 0 |
| FALSE_REFUSE | 5 | 5 | 5 | 0 | 1 |
| REPLAY | 2/2 EXACT | 2/2 EXACT | 2/2 EXACT | 2/2 EXACT | 2/2 EXACT |

Cells: correct (CORRECT + CORRECT_REFUSAL) / scored instances on that axis, over Q1 and Q2. Two of the ten instances
are unscored because the reference statistic falls inside the ±10 % margin band of the bar: Q1 adequacy (46.2 mV
against 50 mV) and Q1 within-cell (54.3 mV against 50 mV).

| Hypothesis | Holds | Numbers |
|---|---|---|
| H1: fewer false refusals than OLD_MIND, no more false support | yes | FR 5 → 0 (needed ≥ 2 fewer); FS 0 → 0 |
| H2: beats each single-layer arm on decided instances | yes | correct decided: combined 5, representation-only 0, roles-only 0; FS 0 for all |
| H3: moves toward CAREFUL on held-out data | yes | held-out correct: careful 2, combined 2, old 0 (gap 2 → 0) |

Truth per instance (reference protocol, computed after the seal):

| | Q1 (aging archive, 44 C, fitted OCV, noise UNKNOWN) | Q2 (LG HG2 pulses, measured OCV, Type-B noise) |
|---|---|---|
| MODEL_ADEQUACY | unscored (marginal) | SUPPORTED (12.1 / 25.0 mV vs 15 / 30) |
| IDENTIFIABILITY | NOT_ASSESSABLE (noise UNKNOWN; not near-structural) | SUPPORTED (declared and residual-inflated FIM both IDENTIFIABLE) |
| WITHIN_CELL | unscored (marginal) | SUPPORTED |
| CROSS_CELL | NOT_SUPPORTED (57.1 / 163 mV vs 50 / 90) | NOT_ASSESSABLE (no second cell) |
| MODEL_DISCREPANCY | NOT_ASSESSABLE (noise UNKNOWN, no bound) | NOT_SUPPORTED (rmse 12.1 mV > 1.1 × 5.4 mV bound) |

Leakage: pre-run mutation PASS (434/434 leaks caught, 0/219 benign), pre-seal audit PASS, post-seal mutation PASS,
post-seal audit PASS. Replay: 16/16 outputs identical, 4/4 repsem assessments EXACT, 4/4 OLD_MIND traces VERIFIED.

## Read this before citing the result

- **The evidence is thin.** Five instances have a decided truth, and two of them are held out. A single flipped instance
  would break H3. The label is the preregistered rule's output, not a strong finding.
- **The win is mostly structural.** OLD_MIND and SEMANTIC_ROLES_ONLY cannot judge adequacy or discrepancy at all (v1
  vocabulary). REPRESENTATION_ONLY is refused at binding by design. Their zeros on the decided instances are refusals,
  as in the synthetic ablation. What is new here is that the combined arm made **no false support and no false refusal
  on real data**:
  - it decided the five decided instances correctly;
  - it refused the three structural NOT_ASSESSABLE instances;
  - it did not mistake the real-data noise, nuisance drift or sampling irregularity for evidence.
- **The combined arm and the truth share question semantics.** The reference is an independent implementation (written
  without reading the candidate code; its own forward model, a denser oracle fit), but the questions it answers are the
  ones the same developer specified for repsem. Two points follow:
  - The combined arm reached the same Q1 optimum: held-out rmse agrees to ~1e-11.
  - So this run shows that repsem's declared-family judgments are **correctly implemented on real data**. It is not an
    independent check that the 1RC model is physically right.
- **Q1's fitted 1RC is physically degenerate.** At the optimum R1 sits on its 1 Ω upper bound with τ ≈ 5200 s, so the
  "RC branch" is a slow drift absorbed alongside the fitted OCV. Both the combined arm and the reference answered
  identifiability NOT_ASSESSABLE (no declared noise), which is correct under the rule. The combined arm's reason does
  not mention the bound, because repsem checks bounds only when a noise is declared. CAREFUL said REVIEW.
- **Q2 is not new data.** Q2 uses the same pulse windows as v1's P2, re-split by state-of-charge set point instead of by
  current level. The constant-current test that v1 held out was left out, because its outcome (a failure) was known.
  Leaving out a known failure moves the within-cell question in the easy direction. Only Q1 is data that this
  project's Mind work had never used.
- **The developer is not blind** to v0/v1 answers, the repsem gap map, or the LG HG2 study's results:
  - the bars are inherited verbatim from v1 (50/90 mV and 15/30 mV) so as not to choose them;
  - the Q1 scope margins (1 °C, 0.05 A, 0.02 charge state) were set after seeing covariate ranges, but before any
    voltage was compared with a model.
- **The truth semantics are stricter than v1's** where measurement uncertainty is UNKNOWN (brief §5): v1 derived
  NOT_SUPPORTED discrepancy from lag-1 autocorrelation without a noise model, while v2 says NOT_ASSESSABLE. CAREFUL
  (v1 code) still decides there, and is scored UNSUPPORTED_DECISION on Q1 discrepancy.
- **Repsem cannot use a Type-B bound for discrepancy.** Q2's declared noise is a bound, not an independence statement.
  So repsem can only reach NOT_SUPPORTED, by excess variance. Had the residuals been small, the reference (bound
  semantics) would have said SUPPORTED, and repsem would have refused. The synthetic dry run showed exactly that.
- A 24 °C, 4 A problem was dropped before any fit. The causal capacity basis breaks there: runs stop at the cutoff
  early, so the basis is 0.56 Ah in one cell and 1.24 Ah in another.

## Design (frozen in PLAN.json)

- **Data.**
  - **Q1:** three sibling cells of the public aging archive (pseudonyms A, B, C) at 44 °C. Each discharges at 1 A and
    2 A.
    - Calibration: early runs of A and B.
    - Within-cell held-out: later runs of A and B.
    - Cross-cell held-out: early runs of C.
    - The raw `.mat` digests are pinned.
  - **Q2:** the LG HG2 pulse windows grouped into 10 SOC set points.
    - Calibration: the even ranks plus the lowest set point.
    - Within-cell held-out: the remaining four set points.
    - No cross-cell set.
  - The pack rebuilds byte-identically from the pinned inputs (`build_pack.py`). The identities are evaluator-only.
- **Roles** are protocol metadata in the pack, never inferred:
  - `t_s` and `level_A` FIXED_PROTOCOL_CONDITION;
  - `current_A` CONTROLLED_INPUT;
  - `soc` STATE_VARIABLE driven by the current, with no column;
  - `voltage_V` MEASUREMENT;
  - `temperature_C` NUISANCE_VARIABLE;
  - R0, R1, C1 (and Q1's OCV knot values) LATENT_PARAMETER.
- **Model space** (`candidate/families.py`): Thevenin 1RC, with Rint as the declared rival. The OCV is either a measured
  table (Q2) or a fitted piecewise-linear table on the knots z = 0, .05, .15, .3, .5, .75, 1 (Q1). It is the same
  function space for repsem and for the v1 baselines.
- **Uncertainty.** Q1's voltage uncertainty is UNKNOWN: no number is invented, and identifiability and discrepancy are
  declared structurally NOT_ASSESSABLE (unless the data are near-structurally non-identifiable). Q2 declares a Type-B
  uniform bound of 5 mV, with independence not declared.
- **Arms** (`candidate/arms.py`); all see the same pack.
  - OLD_MIND: v1's Minimal Mind arm.
  - REPRESENTATION_ONLY: repsem under legacy roles.
  - SEMANTIC_ROLES_ONLY: the v1 Mind with role-posed prediction. Without a measured OCV, the observable is the voltage
    and the charge state is never a free covariate.
  - REPRESENTATION_PLUS_ROLES: repsem under declared roles.
  - CAREFUL_BASELINE: v1's careful baseline.
  - Reference-only arms: FIXED_FIT, ALWAYS_FIT, ALWAYS_REFUSE.
  - The Mind arms run seeds 0, 1 and 2, and seed 0 is scored.
- **Truth** (`evaluator/reference.py`): an independent forward model, a dense oracle multistart, and a 1.10 margin.
  Marginal or rule-dependent instances are unscored, never guessed.
- **Firewall v2** (`leakage.py`): v1's numeric and text engines, with these changes:
  - Candidate material is scanned. Outputs are not numerically scanned, because they are a deterministic function of
    the scanned inputs, and coincidences on shared data are expected.
  - Pack arrays are protected by provenance.
  - The runtime audit refuses paths outside the roots, forbidden modules, and any read of an output during the run.
- **Conclusion rule** (`evaluator/conclusion.py`), applied in this order: leakage; replay or coverage (INCONCLUSIVE if
  fewer than 4 decided instances); H1 ∧ H2 ∧ H3; partial; then attribution of the combined arm's failures.

## Commands

All run with `PYTHONPATH="D:/forge-redisc-v2/src;D:/forge-redisc-v2"` and the phyx `.venv` Python:

```bash
python -m benchmarks.battery_rediscovery_v2.build_pack
python -m benchmarks.battery_rediscovery_v2.mutation --phase pre_run
python -m benchmarks.battery_rediscovery_v2.freeze
python -m benchmarks.battery_rediscovery_v2.launch run
python -m benchmarks.battery_rediscovery_v2.seal
python -m benchmarks.battery_rediscovery_v2.launch replay
python -m benchmarks.battery_rediscovery_v2.mutation --phase post_seal
python -m benchmarks.battery_rediscovery_v2.evaluator.run_evaluation
```

The pack rebuild and the provenance check need the raw archive in `D:/forge-data/nasa_pcoe_battery`.
