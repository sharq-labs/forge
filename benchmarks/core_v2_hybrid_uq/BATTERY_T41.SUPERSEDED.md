# BATTERY_T41.json — SUPERSEDED, not regenerated

`BATTERY_T41.json` (sha256 `a6844a94bef7c370dc285af90cbbc27073f3a914319d31005e26da728ffb0b9e`) was produced on 2026-09-13 by `audit/battery.py`, before the
audited Core V2 route rules (stream hybrid, HUQ-01..14). Its bytes are left exactly as written. **Its claims are not
current.** Machine-readable marker: `BATTERY_T41.SUPERSEDED.json`.

## What changed

- **HUQ-01, minimum multistart (commit 18e1a95).** The record's call uses the default 6-start policy. A search below
  `max(6, 2p + 2)` starts caps the claim at DOWNGRADED with `MULTISTART_INCOMPLETE`. That applies to every model with
  p ≥ 3; **T41 would need 84 starts**. The flagship "T41 LOCAL_GAUSSIAN SUPPORTED" does not reproduce.
- **HUQ-08, diagonal probes (18e1a95).** Re-measured without multistart: over 2p² probes the nonlinearity indices stay
  ≤ 1.9e-5 and no probe lowers χ², so no reason is added. The record's `forward_evaluations_diagnostic_and_jacobian`
  (hardcoded 4k + 1) and the multistart split derived from it are wrong; the diagnostics are 4k + 1 + 2k² evaluations.
- **HUQ-07 / HUQ-11, predictive probes and scaling (25138e7).** Re-measured: ≤ 2.2e-7 parameter sd, no
  `PREDICTIVE_NONLINEAR`. The predictive claim inherits the posterior's downgrade.
- **HUQ-14 / HUQ-09 (3ddc686, 2eca3d1).** `covariance_digest` and every record digest no longer reproduce.
- **HUQ-03.** No effect: the parameters are identity-declared voltages.
- **R-08 / I-02 (core re-audit batch 10).** The minimum search now includes `max_evaluations` and
  `maximum_retractions`, and counts CONVERGED refits rather than half the proposed ones. Every committed model
  lists 6 of 6 starts CONVERGED, so the converged-count rule adds nothing here and `MULTISTART_NO_SECOND_MODE`
  still re-derives from the starts on read-back; the policy this run used is not in the route thresholds, so no
  budget shortfall can be projected from the committed bytes. The claims in the table below are unchanged.
- **R-18 / I-02.** A refused start is now REPLACED by the next unused point of the same Halton sequence instead
  of halved toward the estimate. P1..P5 record `retractions` of 1, 2, 3, 2 and 1 -- between one and three of each
  model's six starts were pulled into the estimate's basin, one of them to 1/8 of its intended distance, and then
  counted as full-span starts behind SUPPORTED `MULTISTART_NO_SECOND_MODE`. So the committed "no second mode"
  rests on a narrower search than the record implies. What it would say instead cannot be projected without
  re-running the search, which is the battery solve this stream must not pay for.
- **R-07 / I-02.** A separated converged refit is classified by its Laplace mass ratio against a floor of 1e-3.
  No effect: all thirty committed refits are `SAME_OPTIMUM`, so nothing here is separated.
- **R-03 / R-20 / I-04 (core re-audit batch 11).** CORE-001 grew a second, leverage-weighted test and an
  unconditional variance-ratio refusal, and downgrades at one or two residual degrees of freedom. The B3
  calibration split is 67 observations, so every model here has 26 to 65 residual dof and none is underpowered;
  the fits sit far below a variance ratio of 1, so the pooled half stays silent. The leverage half was
  MEASURED for the same family, data and p by `benchmarks/core_v4_false_confidence/audit/batch11_performance_probe.py`:
  at p = 41 the statistic is 0.0807 against a null mean of 14.31, a ratio of 0.0056, so it is silent too. The
  probe covers p = 2, 5, 10, 20 and 41; the other models were not measured and already stand DOWNGRADED.
- **R-05 / R-17 / I-05 (core re-audit batch 12).** The same two V2 grid checks. Every model here is routed
  LOCAL_GAUSSIAN with no grid, so neither rule reaches any claim in this record.

**Unchanged:** posterior means and sds (max relative sd change 0.0), identifiability statuses, the tolerance verdicts
against B3's exact route and committed grids (P9 still the one miss), held-out χ² and coverage.

## What it would now say

PROJECTED: the Jacobian, probes, identifiability and predictive were MEASURED under the new rules with
`multistart=None` (`audit/superseded_probe.py battery`); the multistart refits were not re-run, and the committed refits
found no second mode.

| model | p | committed claim | claim now | reasons | minimum starts | nonlinearity (2p² probes) |
|---|---|---|---|---|---|---|
| P1 | 2 | SUPPORTED | **SUPPORTED** | - | 6 | 5.6e-07 |
| P2 | 3 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 8 | 8.1e-08 |
| P3 | 4 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 10 | 3.4e-08 |
| P4 | 5 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 12 | 4.5e-08 |
| P5 | 6 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 14 | 2.7e-07 |
| P7 | 8 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 18 | 2.1e-06 |
| P9 | 10 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 22 | 1.9e-05 |
| T3 | 3 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 8 | 2.5e-08 |
| T5 | 5 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 12 | 2.7e-08 |
| T6 | 6 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 14 | 6.8e-09 |
| T11 | 11 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 24 | 4.4e-08 |
| T21 | 21 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 44 | 7.8e-09 |
| T41 | 41 | SUPPORTED | **DOWNGRADED** | MULTISTART_INCOMPLETE | 84 | 2.1e-09 |

## Why not regenerated

Classified expensive in the user-approved follow-up (every model with refits, a tracemalloc pass on T41, the B3
comparisons); a SUPPORTED T41 would need the 84-start run, which this stream must not run. To regenerate:
`python -X utf8 benchmarks/core_v2_hybrid_uq/audit/battery.py`, with `MultistartPolicy(starts=max(6, 2p + 2))` where
SUPPORTED claims at p ≥ 3 are wanted.
