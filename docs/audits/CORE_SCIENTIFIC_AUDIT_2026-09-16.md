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
| 3a | verification versus validation in result semantics | CORE-008, CORE-013, CORE-015 |
| 3b | scoping and binding of validity, validation and uncertainty records | CORE-009, CORE-014, CORE-016 |
| 4 | adequacy, comparison and prediction domain | CORE-006, CORE-007, CORE-011, CORE-012 |
| — | hardening, folded into the nearest batch | CORE-017, CORE-018 |

## Findings

| ID | Sev | Area | Finding at the audited commit | Batch | Status |
|---|---|---|---|---|---|
| CORE-001 | P0 | local route, grid route | No goodness-of-fit gate. An affine fit to quadratic truth (chi² 8204 on 10 dof) is `LOCAL_GAUSSIAN SUPPORTED`, `PARAMETERS_IDENTIFIABLE`; the linearized prediction at x = 2 misses the truth by 373 total sd and is SUPPORTED. | 1 | FIXED (routed claims); V1 functions unchanged, see below |
| CORE-002 | P0 | grid route | A supplied grid's box becomes the posterior. Containment is checked only on rebuilt grids. A parameter with no effect on the data is `GRID_AS_SUPPLIED SUPPORTED IDENTIFIABLE` (its sd is the box width); a box of ±0.6 posterior sd reports sd 0.337× the exact value, SUPPORTED. | 1 | PARTIAL |
| CORE-003 | P1 | local route diagnostics | The chi² probes sit at exactly ±2 sd. A posterior Gaussian to 2.05 sd with a slowly rising tail is SUPPORTED; its reported 95% interval holds 4.7% of the posterior mass. | 1 | PARTIAL |
| CORE-004 | P1 | identifiability | Relative width is divided by \|mean\| and the condition number is taken on the raw covariance: a location shift turns IDENTIFIABLE into NOT_IDENTIFIABLE, a metre→micrometre rescale turns IDENTIFIABLE into WEAKLY_IDENTIFIABLE (condition 2.54 → 2.54e12). | 2 | PARTIAL |
| CORE-005 | P0 | grid route binding | A supplied grid is bound to the request by `dataset_id` string only (HUQ-06). A grid computed from data shifted by 185 sd, under the same id, is `GRID_AS_SUPPLIED SUPPORTED`. | 1 | PARTIAL |
| CORE-006 | P1 | predictive UQ | No calibration or prediction domain; the predictor is not bound to the calibrated model. Extrapolation to 10⁴× the calibrated range, and an unrelated predictor in kelvin, are SUPPORTED. | 4 | OPEN (INF-01 deferred) |
| CORE-007 | P1 | adequacy | Held-out leakage is refused by label only; a model comparison between two identical models is won by +0.95 nats through the leak. | 4 | OPEN (INF-03/07 deferred) |
| CORE-008 | P1 | result semantics | A record whose only passing checks are verification levels (dimensional, numerical convergence, analytic) derives a SUPPORTED credibility verdict. | 3 | PARTIAL |
| CORE-009 | P1 (latent) | experimental validation | An oracle observation carries no conditions, inputs or model version; `EXPERIMENTALLY_VALIDATED` attaches to any result. | 3b | OPEN |
| CORE-010 | P2 | grid prior | Grid weights carry no cell volume, so node density is an undeclared prior: a clustered axis moves the mean 0.9 sd and cuts the sd 29%, SUPPORTED, against the non-claim "no informative priors". | 2 | FIXED (routed claims) |
| CORE-011 | P2 | model comparison | `preferred_model` is issued for any delta > 0, including 1.5e-9 nats on one observation. | 4 | OPEN |
| CORE-012 | P2 | calibration statistics | Only independent Gaussian noise is representable, and nothing asks for independence to be attested; a shared systematic offset narrows as 1/√n. | 4 | OPEN |
| CORE-013 | P2 | validation report | `ValidationReport.status` is PASS while an experimental check is NOT_RUN. | 3 | FIXED |
| CORE-014 | P2 | validity | A validity assessment is not bound to the input values it was computed at. | 3b | OPEN |
| CORE-015 | P2 | experiments | An OK evaluation accepts unassessed or model-less results (residual of RES-06). | 3 | FIXED |
| CORE-016 | P2 | uncertainty, composition | Uncertainty carries no source category; transfers drop upstream uncertainty and credibility. | 3b | OPEN |
| CORE-017 | P3 | split | The copy detector rounds to twelve digits; a 1 ppm sigma change evades it (residual of INF-06). | — | OPEN |
| CORE-018 | P3 | misc | Consensus compares values in each route's own unit; bound ordering uses raw magnitudes; `ModelType` and model validation status are inert labels. | — | OPEN |

## Batch 1 — what now holds

Commits `f174d3c` (audit record, preregistration, strict xfails) and `2018fb8` (fix). Thresholds:
`benchmarks/core_v4_false_confidence/BATCH1_THRESHOLD_PROTOCOL.json`, with three dated amendments, none of which moved a
threshold or a gating rule. Regression tests: `tests/hybrid_uq/test_core_scientific_audit_batch1.py`. Guard mutations:
`benchmarks/core_v4_false_confidence/BATCH1_MUTATIONS.log` (17 killed, green control); all 71 existing
hybrid_uq/inference/uq mutations still apply and are killed.

| ID | What now holds | Residual |
|---|---|---|
| CORE-001 | chi2_min against chi-square on n - p dof: p < 0.01 downgrades `RESIDUALS_EXCEED_DECLARED_NOISE`; with chi2/dof > 4 it refuses `MODEL_MISFIT_BEYOND_DECLARED_NOISE`. No grid route, supplied or rebuilt, is used past either. Re-derived on read. | The frozen V1 `assess_identifiability` and `posterior_predictive_uq` take no observations and apply no goodness of fit; only routed (V2) claims are held to it. Under-dispersion is not gated. Correlated or systematic errors that the residuals cannot reveal are CORE-012. |
| CORE-002 | A supplied grid's faces must fall ln 1e6 below its peak; a rebuilt grid whose posterior reaches both declared bounds of an axis is passed over `GRID_POSTERIOR_BOUND_DOMINATED`. | Containment is a face test on a tensor lattice: a second mode outside a supplied grid's box, separated from it by density below 1e-6 of the peak, is not detected (the rebuild path searches for modes by multistart). A bound-dominated axis on a supplied grid reaching one declared bound is passed over, not diagnosed. |
| CORE-003 | chi2 rise at 3 and 6 sd along each principal axis against r^2: below 0.9 downgrades `TAIL_HEAVIER_WITHIN_6_SD`, below 0.5 refuses `TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN`. | Any finite probe set can be evaded: a plateau strictly between probe radii, off the principal axes, or beyond 6 sd with bounds about 1e6 sd away. The thresholds are class C heuristics and the record carries them. |
| CORE-005 | A supplied grid is routed only with observations and forward; admission and chi-square must equal the forward model's at deterministic nodes, else `HybridUQError`. `grid_predictive_uncertainty` without that evidence is DOWNGRADED `GRID_NOT_BOUND_TO_EVIDENCE`. | A grid altered only at unchecked nodes is not caught (shared with HUQ-05). `routed_predictive_uncertainty` trusts a `HybridUQResult`'s grid, which the router bound when it built the result; a hand-constructed result is integrity-only, as every record digest is. |

**First measurement on real evidence.** `benchmarks/core_v2_hybrid_uq/PERFORMANCE.json` was regenerated: the uniform-knot
LINEAR OCV family on B3's calibration data now REFUSES at p = 2, 5 and 10 (chi2/dof 24.3, 13.4 and 4.6) and is DOWNGRADED
only by the multistart minimum at p = 20 and 41 (chi2/dof 0.69 and 0.006; the latter is over-fitted, which is not gated).
Before batch 1 the first three reported covariances built from a declared sigma the residuals contradict. The V1 grid part
of the same record still reads PARAMETERS_IDENTIFIABLE at p = 2..4 (see the CORE-001 residual).

**Other evidence.** `TCR.json` and `FAILURE_CASES.json` were regenerated; every declared expectation is met. F1's rebuilt
grid is retired (its decay-rate sd was the declared upper bound's: 1.75, 2.57, 5.81 with the bound at 20, 40, 80).
`BATTERY_T41.json` and `KINETICS_K2.json` stay superseded and were not re-scored under batch 1. `WHEEL_V2.json` records
frozen digests and is regenerated in the Core Freeze V4 round.

**Compatibility.** `RouteReason` gains 7 members, `RouteDiagnostics` 3 trailing fields (`hybrid_uq.route_diagnostics/2`;
/1 records are refused on read), `grid_predictive_uncertainty` 3 defaulted keyword arguments. On this branch the V2 frozen
snapshot tests, the Core Freeze V1/V2/V3 manifest tests and the core certificate tests fail by design until Core Freeze V4.

## Batch 2 — what now holds

Commits `4f5a341` (preregistration, strict xfails), `08e50a6` (fix), `fbeb7b6` (evidence, mutations). Compatibility decision
by the repository owner on 2026-09-16: Core Freeze V4 may add to V1-frozen symbols and may not remove or change anything.

| ID | What now holds | Residual |
|---|---|---|
| CORE-004 | The identifiability condition number is taken on the correlation matrix everywhere (V1 `assess_identifiability`, the routed rule, read-back). The metre/micrometre reproduction reaches one verdict. Every explanation states that relative widths are measured against each parameter's declared zero. | The origin dependence is stated, not removed: an origin-invariant width needs a declared scale of interest, which no parameter declaration carries. `FAILURE_CASES.json` `poorly_scaled_parameterization` moved WEAKLY → IDENTIFIABLE; its route stays DOWNGRADED `POORLY_SCALED_PARAMETERIZATION`. |
| CORE-010 | Routed grids must be evenly spaced in each parameter's inference coordinate (log for LOG parameters), else `GRID_PRIOR_NOT_UNIFORM_IN_INFERENCE_COORDINATES`. | The V1 `gaussian_grid_posterior` still defines equal node mass as its prior; only routed claims are held to the declared one. |

## Batch 3a — what now holds

Commits `f838c27` (preregistration, strict xfails), `b569b20` (fix). Guard mutations: `BATCH3A_MUTATIONS.log` (5 killed, green
control); the 27 existing mutations in the three changed files still apply and are killed.

| ID | What now holds | Residual |
|---|---|---|
| CORE-013 | `ValidationReport.status` is FAIL > NOT_RUN > WARNING > PASS. | Domains record NOT_RUN both for missing evidence and for a check that does not apply (the DC solver's absent element classes); the aggregate and `derive_verdict` treat both as not established. |
| CORE-008 | `ValidationReport.evidence_basis` (VALIDATED / VERIFICATION_ONLY / NONE) and `verdict_qualifiers.evidence_basis` on every credibility report, re-derived on read. | The verdict word is unchanged: SUPPORTED on verification alone is still SUPPORTED, now visibly qualified. Changing the word moves the scored benchmarks and is left as an explicit owner decision. |
| CORE-015 | `Experiment.best` ranks only candidates whose models were all assessed IN_DOMAIN, with declared constraints checked and satisfied. | An OK evaluation may still be recorded over an unassessed result; it is recorded, not ranked. |
