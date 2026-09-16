# Scientific core audit — 2026-09-16

Audited tree: `claude/main-audit-fixes` at `4033c220ab455927b6a781eb3bf9d4e46e33a8ea` (PR #47, Core Freeze V3 candidate).
Question asked: can the generic scientific core produce, strengthen, preserve or communicate a conclusion more
confidently than the mathematics or the evidence justifies? Domain physics was out of scope. Verdict at the
audited commit: **yes**. The core refuses inconsistent records well; it accepts consistent records of
scientifically wrong situations — a model that misfits by chi²/dof 820, a parameter the data never touch, a grid
box that cuts the posterior to a third of its width — as SUPPORTED and IDENTIFIABLE.

Every finding below was reproduced against the audited commit. The reproductions are the regression tests named
in the batch that fixes them; each was seen failing on `4033c22` before its fix was written.

Status legend: **OPEN**, **FIXED**, **PARTIAL** (the scenario is refused; a stated residual remains),
**DEFERRED**.

## Batches

The findings are fixed in four batches grouped by mechanism, not one change per finding: new route reasons move the
route vocabulary once, and the certification round (Core Freeze V4) is run once, after the batches land.

| Batch | Mechanism | Findings |
|---|---|---|
| 1 | acceptance criteria of the routed-UQ claims | CORE-001, CORE-002, CORE-003, CORE-005 |
| 2 | invariance of identifiability; grid prior | CORE-004, CORE-010 |
| 3 | verification versus validation in result semantics | CORE-008, CORE-009, CORE-013, CORE-014, CORE-015, CORE-016 |
| 4 | adequacy, comparison and prediction domain | CORE-006, CORE-007, CORE-011, CORE-012 |
| — | hardening, folded into the nearest batch | CORE-017, CORE-018 |

## Findings

| ID | Sev | Area | Finding at the audited commit | Batch | Status |
|---|---|---|---|---|---|
| CORE-001 | P0 | local route, grid route | No goodness-of-fit gate. An affine fit to quadratic truth (chi² 8204 on 10 dof) is `LOCAL_GAUSSIAN SUPPORTED`, `PARAMETERS_IDENTIFIABLE`; the linearized prediction at x = 2 misses the truth by 373 total sd and is SUPPORTED. | 1 | OPEN |
| CORE-002 | P0 | grid route | A supplied grid's box becomes the posterior. Containment is checked only on rebuilt grids. A parameter with no effect on the data is `GRID_AS_SUPPLIED SUPPORTED IDENTIFIABLE` (its sd is the box width); a box of ±0.6 posterior sd reports sd 0.337× the exact value, SUPPORTED. | 1 | OPEN |
| CORE-003 | P1 | local route diagnostics | The chi² probes sit at exactly ±2 sd. A posterior Gaussian to 2.05 sd with a slowly rising tail is SUPPORTED; its reported 95% interval holds 4.7% of the posterior mass. | 1 | OPEN |
| CORE-004 | P1 | identifiability | Relative width is divided by \|mean\| and the condition number is taken on the raw covariance: a location shift turns IDENTIFIABLE into NOT_IDENTIFIABLE, a metre→micrometre rescale turns IDENTIFIABLE into WEAKLY_IDENTIFIABLE (condition 2.54 → 2.54e12). | 2 | OPEN |
| CORE-005 | P0 | grid route binding | A supplied grid is bound to the request by `dataset_id` string only (HUQ-06). A grid computed from data shifted by 185 sd, under the same id, is `GRID_AS_SUPPLIED SUPPORTED`. | 1 | OPEN |
| CORE-006 | P1 | predictive UQ | No calibration or prediction domain; the predictor is not bound to the calibrated model. Extrapolation to 10⁴× the calibrated range, and an unrelated predictor in kelvin, are SUPPORTED. | 4 | OPEN (INF-01 deferred) |
| CORE-007 | P1 | adequacy | Held-out leakage is refused by label only; a model comparison between two identical models is won by +0.95 nats through the leak. | 4 | OPEN (INF-03/07 deferred) |
| CORE-008 | P1 | result semantics | A record whose only passing checks are verification levels (dimensional, numerical convergence, analytic) derives a SUPPORTED credibility verdict. | 3 | OPEN |
| CORE-009 | P1 (latent) | experimental validation | An oracle observation carries no conditions, inputs or model version; `EXPERIMENTALLY_VALIDATED` attaches to any result. | 3 | OPEN |
| CORE-010 | P2 | grid prior | Grid weights carry no cell volume, so node density is an undeclared prior: a clustered axis moves the mean 0.9 sd and cuts the sd 29%, SUPPORTED, against the non-claim "no informative priors". | 2 | OPEN |
| CORE-011 | P2 | model comparison | `preferred_model` is issued for any delta > 0, including 1.5e-9 nats on one observation. | 4 | OPEN |
| CORE-012 | P2 | calibration statistics | Only independent Gaussian noise is representable, and nothing asks for independence to be attested; a shared systematic offset narrows as 1/√n. | 4 | OPEN |
| CORE-013 | P2 | validation report | `ValidationReport.status` is PASS while an experimental check is NOT_RUN. | 3 | OPEN |
| CORE-014 | P2 | validity | A validity assessment is not bound to the input values it was computed at. | 3 | OPEN |
| CORE-015 | P2 | experiments | An OK evaluation accepts unassessed or model-less results (residual of RES-06). | 3 | OPEN |
| CORE-016 | P2 | uncertainty, composition | Uncertainty carries no source category; transfers drop upstream uncertainty and credibility. | 3 | OPEN |
| CORE-017 | P3 | split | The copy detector rounds to twelve digits; a 1 ppm sigma change evades it (residual of INF-06). | — | OPEN |
| CORE-018 | P3 | misc | Consensus compares values in each route's own unit; bound ordering uses raw magnitudes; `ModelType` and model validation status are inert labels. | — | OPEN |
