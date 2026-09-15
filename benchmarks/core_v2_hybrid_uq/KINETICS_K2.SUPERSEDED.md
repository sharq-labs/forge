# KINETICS_K2.json — SUPERSEDED, not regenerated

`KINETICS_K2.json` (sha256 `2864ed96b841584457ad01f7334ece57c8da3bab3a97bee9f740e1138222f786`) was produced on 2026-09-13 by `audit/kinetics.py`, before the
audited Core V2 route rules (stream hybrid, HUQ-01..14). Its bytes are left exactly as written. **Its route claims were
established under the weaker rules and are not current**; its covariance-derived numbers are. Machine-readable marker:
`KINETICS_K2.SUPERSEDED.json`.

## What changed

- **HUQ-08, diagonal probes (18e1a95).** MULTI's SUPPORTED claim rested on 4 axis probes. Re-measured over 8 probes
  (no multistart): nonlinearity index 0.0715, unchanged, and no probe lowers χ². The committed refits
  are not below the estimate's χ², but the lower-objective rule was not re-run through them.
- **HUQ-07 / HUQ-11, predictive probes and scaling (25138e7).** The C2 predictions' SUPPORTED claim rested on axis probes
  scaled by total sd (0.036). Re-measured with diagonal and Σ∇g probes, in parameter sd:
  0.0566, below 0.10.
- **HUQ-01 (18e1a95).** The script's 6 starts at p = 2 meet the minimum search; no downgrade is projected.
- **HUQ-03 (3ddc686).** `k0_declared_log`'s ln k0 width is now the natural-scale relative width (≈0.645, was ≈0.030);
  the status stays NOT_IDENTIFIABLE.
- **HUQ-14 / HUQ-09.** `MULTI_v2.route.record_digest` and every embedded record digest no longer reproduce.

**Unchanged:** the MULTI estimate and sds (identical when re-derived without multistart), its covariance, identifiability statuses, C2 predictive sds,
the V1 reference grids, every `CORRECTED` errata quantity (so `benchmarks/core_v1_thin_ridge_repair/ERRATA.md`'s addendum
stands), WEAK_C2 REFUSED, and the parameterization verdicts.

## What it would now say

| part | label | claim now | reasons |
|---|---|---|---|
| MULTI route | PROJECTED (refits not re-run) | SUPPORTED | - |
| C2 predictive | PROJECTED | SUPPORTED | - |
| natural_k0_identity | MEASURED | REFUSED | NONLINEAR_BEYOND_LOCAL_GAUSSIAN, GLOBAL_UNIQUENESS_NOT_ASSESSED, POORLY_SCALED_PARAMETERIZATION |
| k0_declared_log | MEASURED | DOWNGRADED | GLOBAL_UNIQUENESS_NOT_ASSESSED |
| WEAK_C2 | RULE | REFUSED | NO_RESIDUAL_DEGREES_OF_FREEDOM |

Probe: `audit/superseded_probe.py k2` (about 207 s, no multistart).

## Why not regenerated

The MULTI multistart alone is ~76 min of CSTR solves, and this stream must never run it. **Stage-cache trap:**
`kinetics.py` caches stages in `D:/v2_k2_cache`, whose stage 1/2/5 entries hold records built under the old rules; the
V2-route stages are now cached under `*_audit_hybrid` names so a rerun recomputes them.
