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
