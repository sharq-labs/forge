# Core V1 Certified Repair: Thin-Ridge Posterior Resolution Guard

**Verdict:** CORE V1 THIN-RIDGE REPAIR COMPLETE

**Freeze status:** CORE FROZEN — V1 with a certified correctness repair applied.

**Round facts:**

- **Baseline** (`V1_REPAIR_BASELINE`): `273bfff7d3d685d9e0bb62519795aeb47c05b027`. At the baseline, the certificate verified OK and the freeze verifier passed in DESCENDANT mode.
- **Branch:** `claude/core-v1-thin-ridge-repair`.
- **Scope:** a targeted correctness repair of frozen grid-resolution behaviour. There is no new public capability, no new public symbol, no HD-UQ route, no V2 routing and no Domain work.

## 1. Root cause

`assess_identifiability` refused a `PosteriorGrid` only when both of these held:

- ESS < 8;
- max axis step ≥ that axis's **marginal** sd.

Two defects follow from that rule.

1. **Off-axis aliasing is invisible.**
   - By Poisson summation, a lattice sum of a Gaussian differs from its integral by one term exp(−kᵀΣk/2) for every non-zero reciprocal vector k = 2πn/h, where n is an integer vector.
   - Along a coordinate axis, kᵀΣk = (2πσᵢ/hᵢ)². That is the only quantity the marginal rule bounds.
   - Along an off-axis n aligned with a thin, tilted principal direction, kᵀΣk can be ≪ 1 while every marginal is wide.
   - The grid then reports a collapsed thin direction, a correlation pushed to ±1, and understated epistemic predictive sd. The results are **bit-stable under nested refinement**, so refinement never reveals the error.
2. **The ESS clause was waived whenever spacing looked small.** K2's grid passed with **ESS 1.42**.

`posterior_predictive_uq` had no resolution check at all. It propagated whatever the grid held.

## 2. The diagnostic

The diagnostic is private, lives in `src/engcore/inference/calibration.py`, and is not exported. It proceeds in four steps.

1. **Tensor lattice check.** The points must be the full product of their axis values, from which the per-axis step h is read.
2. **Local curvature fit.**
   - A least-squares quadratic is fitted to the grid's own `log_likelihood`, in **lattice units** (coordinates divided by h), about the highest node.
   - Log-likelihood windows of 50, 500, 5000 and ∞ are tried in turn, so a thin ridge whose near-top nodes are collinear gets a wider window.
   - **Flat or convex fitted directions are clipped to flat** (precision floor 10⁻⁹ relative, 10⁻¹² absolute). Only a concave direction can be thin.
3. **Aliasing number.** A = min over non-zero integer n of (2π)² nᵀSn, where S is the fitted covariance in lattice units. It is found **exactly** by Fincke–Pohst enumeration with a shrinking bound.
4. **Refusal** (`GridResolutionError`, prefixed `GRID_TOO_COARSE_FOR_INFERENCE`) in any of these cases:
   - A < T;
   - ESS < p + 1;
   - the curvature cannot be fitted (too few nodes, collinear nodes, or a singular design);
   - the points are not a tensor lattice;
   - in `assess_identifiability` only: fewer than 2·(p+1)(p+2)/2 admissible nodes.

**Properties:**

| property | how it is met |
|---|---|
| no extra forward solves | reads only `points`, `weights`, `log_likelihood` and `admissible_mask` |
| scale invariant | lattice units. F5 rescaled ×1, ×10 and ×100 gives A = 0.03308, identical in every digit printed |
| sees tilted ridges | off-axis n are enumerated. RIDGE-2 (diagonal only) and RIDGE-3 (axis n only) are both killed |
| deterministic | there is no randomness |
| wiring | `assess_identifiability` runs it after the frozen rule. `posterior_predictive_uq` runs it before any computation |

## 3. Threshold and how it was chosen

**T = 2 ln 100 = 9.2103**, which corresponds to a per-vector aliasing amplitude exp(−A/2) of 1%.

The protocol was predeclared and committed **before** any threshold was wired: `THRESHOLD_PROTOCOL.json` in commit 654eb5b.

- **Ladder:** 2 ln 10ᵏ for k = 1..5.
- **Held-back synthetic set** (seed 20260914): 288 cases, 153 of them materially wrong. It covers correlated 2-D, rotated thin 2-D, consistent scaling, thin 3-D and 1-D spacing families.
- **Real cases:**
  - required healthy: TCR wide 41, TCR narrow 161, Battery P2, Battery P3;
  - known wrong: F5 at 201/401/801, TCR narrow 41, K2 MULTI;
  - reported only: K2 WEAK_C2.
- **Rule:** choose the **largest** ladder value that satisfies all three of these:
  - (i) every materially wrong case is refused;
  - (ii) every confirmed-healthy real case is kept;
  - (iii) the false-refusal rate on healthy held-back cases is ≤ 10%.

Scoring (`audit/select_threshold.py`) ran with the threshold still unwired, so no score could depend on T.

| T | (i) missed | (ii) lost | (iii) false refusal | all three |
|---|---|---|---|---|
| 4.61 | 19 | 0 | 6.7% | no |
| **9.21** | **0** | **0** | **6.7%** | **yes** |
| 13.8 | 0 | 0 | 11.1% | no |
| 18.4 | 0 | 0 | 15.6% | no |
| 23.0 | 0 | 0 | 20.0% | no |

**Selected: 9.21.** The margin is narrow on the low side: the largest aliasing number among held-back materially wrong cases is 7.74. `THRESHOLD_SELECTION.json` is identical to 10⁻¹¹ after both later code changes: the node-count cutoff and the flat-direction clipping.

## 4. ESS repair

A grid with ESS < p + 1 is refused regardless of spacing.

- p + 1 is the fewest effective points that can carry a p-parameter covariance.
- K2 MULTI (ESS 1.42) is refused on this ground.
- A dedicated regression places 0.8 of the mass on one node, with axis spacing 0.22 sd and a fitted A ≈ 6900. **Only the ESS floor sees it**, and RIDGE-5 is killed by it.

ESS alone does not refuse a resolved grid:

- the coverage-study grid at 15 nodes has ESS 6.3, A = 9.9 and thin sd 0.93×, and is kept;
- the frozen ESS < 8 ∧ spacing ≥ 1 rule is unchanged.

## 5. Predictive UQ behaviour

`posterior_predictive_uq` raises the **existing** `GridResolutionError` for an unresolved grid. `assess_predictive_observation` already let that error propagate, and it still does.

| case | predictive UQ result |
|---|---|
| F5 thin ridge | refused (test) |
| K2 C2 predictions | refused (test) |
| TCR wide (healthy) | works; epistemic sd within 2% of the linearized value |
| TCR narrow at 161 nodes (weak but resolved) | works; within 5% |
| too few nodes to fit a curvature (fewer than 2·(p+1)(p+2)/2 admissible nodes) | keeps its documented **exact discrete-mixture** meaning; tests cover 2 nodes and 5 nodes. `assess_identifiability` refuses the same posteriors |

## 6. Case before and after

**Status.** "Before" is the frozen rule; predictive UQ never refused before the repair.

| case | before | after |
|---|---|---|
| **F5** (bounds grid, 201/401/801 nodes) | PARAMETERS_NOT_IDENTIFIABLE, \|ρ\| = 1.0 | **refused**, A = 0.0083 / 0.033 / 0.132; predictive refused |
| **TCR wide 41** | PARAMETERS_IDENTIFIABLE | PARAMETERS_IDENTIFIABLE, A = 69.5 |
| **TCR narrow 41** | PARAMETERS_WEAKLY_IDENTIFIABLE, \|ρ\| = 0.9968 | **refused**, A = 6.13 |
| TCR narrow 81 / 161 | — | PARAMETERS_WEAKLY_IDENTIFIABLE, A = 24.7 / 98.7 |
| **K2 MULTI** | PARAMETERS_NOT_IDENTIFIABLE, \|ρ\| = 0.99998, ESS 1.42 | **refused** (ESS below 3); predictive refused |
| **K2 WEAK_C2** | PARAMETERS_NOT_IDENTIFIABLE | **refused**, A = 4.47 |

**Accuracy against the reference.** F5, TCR and Battery are compared with an exact reference; K2 with its proxy.

| case | marginal mean error | marginal sd ratio | thin-direction sd | reading |
|---|---|---|---|---|
| F5 (all three grids) | 1.11 sd | 0.56× | 0.83× | materially wrong |
| TCR wide 41 | 10⁻⁹ sd | — | 1.000× | right |
| TCR narrow 41 | — | 0.996× | 0.68× | materially wrong |
| TCR narrow 81 / 161 | — | — | 1.000× | right |
| K2 MULTI (proxy) | — | 0.94× | 0.16× | materially wrong |
| K2 WEAK_C2 | — | — | — | no reference committed |

**Battery.** Six B3 grid models were checked against the exact linear Gaussian. All were IDENTIFIABLE → IDENTIFIABLE:

| model | grid | A | ESS | agreement with exact |
|---|---|---|---|---|
| P2 | 25³ | 157.9 | 299 | 10⁻⁸ |
| P3 | 13⁴ | 88.8 | 644 | 1.3 × 10⁻⁴ (sd) |
| P1 | — | 415.9 | — | 10⁻⁸ |
| P4 | 9⁵ | 39.5 | — | 5 × 10⁻⁵ |
| T3 | — | 157.9 | — | 10⁻⁸ |
| T5 | 9⁵ | 39.5 | — | 5 × 10⁻⁵ |

Battery B1 and B2 audit scripts were re-run in a scratch worktree at the repair commit. Their RESULTS.json files are identical to the committed ones apart from wall-clock fields.

## 7. Parameterization invariance

- **Units:** rescaling a parameter by ×10 or ×100 leaves the lattice the same in steps, so A is identical. This holds for:
  - F5: refused at ×1, ×10 and ×100;
  - a healthy correlated Gaussian: kept at ×1, ×10 and ×100.

  No verdict flips on units.
- **Rotated or whitened frames** are a **different lattice**, not new units. An axis-aligned grid in principal-axis or whitened coordinates samples the thin direction with its own step, so A legitimately differs:
  - the F5 posterior on principal or whitened axes with a thin step of 6 sd is refused;
  - the same frames at 61 nodes over ±6 sd are resolved and kept.

  Where rotated and original grids disagree, it is because they sample the posterior differently, and each verdict is right for its own lattice.
- **A linear map of a grid's points** (not a new grid) is not a tensor lattice, so no step exists to check. It is refused as unverifiable (see §8).

## 8. False positives

- **Held-back healthy synthetic:** 9 of 135 are refused by the repaired `assess_identifiability`, i.e. 6.7%.
  - All 9 were **already** refused by the frozen rule.
  - The new checks alone refuse 2 of 135 (1.5%): 1-D grids at spacing 2 sd with ESS < 2, where the moment error is ≤ 6%. For **predictive UQ** these 2 are new refusals.
- **Real:** the six B3 *linearly mapped* grids (§23 parameterization readout) are now refused as "not an axis-aligned tensor lattice", although their moments are right.
  - The B3 conclusion stands (ERRATA E5).
  - Remedy: assess in grid coordinates and map moments.
- **Shape probes that are not false positives:** a flat non-identified axis, a bound-truncated posterior and two broad modes are **answered** (tests). A first version refused them; it was fixed before any assurance ran (commit 0c691f9).

## 9. False negatives

**Observed:** none.

- All 153 held-back materially wrong cases were refused.
- All 7 real materially wrong grids were refused.
- Two thin tilted modes are refused (test).

**Known limits, not observed failures:**

- The check reads one local quadratic about the top node. A strongly non-Gaussian posterior, such as a banana or thin modes far apart with unequal heights, is checked only through that quadratic.
- T was selected on Gaussian families. The low-side margin is 9.21 against 7.74.
- The enumeration aborts at 10⁶ nodes and refuses when it does.

## 10. Public API, serialization, identity

| item | result |
|---|---|
| public API changes | **none**. Only private module-level names were added; `engcore.inference.__init__` and `engcore.uq.__init__` are byte-identical to the baseline |
| frozen symbol count | **194** (unchanged) |
| total public | 205 |
| experimental | 11 |
| frozen API digest | `c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929` (unchanged) |
| wheel/source frozen API parity | MATCH (194 / 194) |
| wheel smoke (`-S -E`) | wheel install refuses a thin tilted ridge and classifies a healthy grid |
| serialization / identity / exceptions / ordering | freeze verifier `contract.serialization`, `contract.identity`, `contract.exceptions` and `contract.ordering` all PASS; `identity_semantics_hold` and `serialization_semantics_hold` PASS |

**Behaviour change.** This is recorded as a correctness repair: grids that the frozen rule accepted with wrong moments now raise the existing `GridResolutionError`. Error type, signatures and admission semantics for resolved grids are unchanged.

## 11. Tests changed

Three pre-existing tests used grids the repair refuses. Each grid is materially wrong against exact quadrature (`AFFECTED_TESTS.json`):

| test | old grid | thin-direction sd | new grid |
|---|---|---|---|
| TCR narrow | 41 nodes | 0.68× | 81 nodes |
| TCR held-out case C | 21 nodes | 0.055× | 81 nodes; the 21-node grid is now asserted refused |
| coverage-study determinism | 11 nodes | 0.58× | 15 nodes, the study default |

No materiality bound was moved.

## 12. Errata

See `ERRATA.md`:

- **E1:** TCR narrow design.
- **E2:** TCR held-out case C, whose stated rationale was wrong.
- **E3:** coverage determinism grid.
- **E4:** K2.
  - The A5 gain magnitude is overstated about 56×; the PASS verdict likely stands.
  - The MULTI covariance, determinant and correlation are unreliable.
  - C2 epistemic predictive sd is 0.17× (total predictive sd 22% low).
  - A6, A3/A4, A1/A2 and A7–A9 stand.
  - K3, K3.1 and K4 are affected and unquantified.
- **E5:** B3 mapped-grid readout (conclusion stands).

Original artifacts are unchanged.

## 13. Mutations

**Repair matrix** (`audit/ridge_mutations.py`, scratch worktree, control 127 passed): **8 of 8 killed**.

| id | mutation | killed by |
|---|---|---|
| RIDGE-1 | remove aliasing check | F5 refusal |
| RIDGE-2 | diagonal covariance only | F5 refusal |
| RIDGE-3 | axis lattice vectors only | F5 refusal |
| RIDGE-4 | no scale normalization | resolved TCR narrow classified |
| RIDGE-5 | ESS ≈ 1 passes | one-node-mass regression |
| RIDGE-6 | predictive ignores refusal | fit-failure predictive refusal |
| RIDGE-7 | threshold comparison reversed | resolved TCR narrow classified |
| RIDGE-8 | fit failure treated as PASS | collinear-node refusal |

**Certified harness** (`tests/mutation_guards.py`, 79 mutants): control GREEN, 79 of 79 killed (§14).

**Correction to a commit message.** Commit 83090a6's message says "all eleven materially wrong grids refused". The count of materially wrong real grids is **seven**: F5 ×3, TCR narrow 41, case C 21, coverage 11 and K2 MULTI. All seven are refused.

## 14. Assurance

| check | result |
|---|---|
| FAST (`-m "not expensive and not campaign"`), after the reissue | **5008 passed, 5 skipped, 0 failed** (baseline 4976 passed) |
| FULL, after the reissue | **5554 passed, 5 skipped, 0 failed** (baseline 5522 passed) |
| certified 79 (`tests/mutation_guards.py`, scratch worktree at bccbbf7; src and tests identical to the certified commit) | control GREEN (470 passed), **79 of 79 killed**, 0 survivors. Log: `MUTATION_HARNESS_79.log`, sha256 `283f5767…`. Harness files byte-identical to the pinned identity |
| certificate | **reissued once** on the final candidate, `ad52a907` (76 files, aggregate `ddd86ca2e023bd15764413e071a0644524cc7c8a80776edf364941e002e5a026`, assurance `certification/v1_thin_ridge_repair_assurance.json`); `--verify`: certificate matches the tree, OK |
| freeze verify | **OK**, DESCENDANT mode. `contract.api`, `contract.serialization`, `contract.identity`, `contract.ordering`, `contract.exceptions`, `experimental.visibly_classified`, `certificate.verifies` and `bytes.pinned_contract_files` all PASS |
| certification and freeze-manifest suites, after the reissue | 50 passed, 2 skipped |

Before the reissue, FAST (5005 passed) and FULL (5551 passed) each had the same three certificate identity failures. They were caused only by the changed inference area:

- `test_the_certificate_describes_this_tree`;
- `test_the_tree_is_core_freeze_v1`;
- `test_a_descendant_that_keeps_the_contract_still_verifies`.

**Named suites** (`SUITES.json`):

| suite | passed |
|---|---|
| grid resolution | 32 |
| inference (TCR) | 153 |
| predictive UQ / adequacy | 47 |
| battery | 265 |
| capability boundary | 308 |
| contract guard | 305 |
| core API stability | 138 |
| mutation-harness self guard | 6 |
| field profile | 147 |
| field | 124 |
| scientific truth | 293 |

All named suites were green except the certification suite before the reissue (1 failed). After the reissue the certification and freeze-manifest suites give 50 passed, 2 skipped.

## Files changed

**Core** (2 files):

- `src/engcore/inference/calibration.py`: private diagnostic plus wiring in `assess_identifiability`.
- `src/engcore/uq/predictive.py`: refusal in `posterior_predictive_uq`.

**Tests:**

- `tests/inference/test_grid_resolution_repair.py` (new);
- `tests/inference/fixtures/grid_resolution/*` (new: K2 multi and weak C2, Battery P2 and P3, PROVENANCE.json);
- `tests/inference/test_tcr_calibration.py`, `tests/inference/test_tcr_heldout_uq.py`, `tests/inference/test_reproducibility_and_evidence.py` (resolved grids).

**Evidence** (`benchmarks/core_v1_thin_ridge_repair/`):

- THRESHOLD_PROTOCOL.json, THRESHOLD_SELECTION.json, AFFECTED_TESTS.json, REGRESSION_MATRIX.json;
- RIDGE_MUTATIONS.json, MUTATION_HARNESS_79.log, SUITES.json, WHEEL_PARITY.json;
- ERRATA.md, REPAIR_REPORT.md;
- `audit/`: build_fixtures, select_threshold, affected_tests, regression_matrix, ridge_mutations, suites, build_assurance.

**Certification:**

- `certification/v1_thin_ridge_repair_assurance.json` (new);
- `certification/current_core_v2.json` (reissued).

The frozen API manifests, the freeze manifest and the pinned contract files are unchanged.

## 15. Exact V1 claim after repair

A `PosteriorGrid` posterior that Core V1 classifies (`assess_identifiability`) or propagates (`posterior_predictive_uq`) meets all of the following:

- it lies on an axis-aligned tensor lattice;
- its ESS is at least p + 1;
- its locally fitted posterior curvature has a lattice aliasing number of at least 2 ln 100 along **every** integer lattice direction, off-axis ones included;
- it also passes the frozen ESS-and-spacing rule (identifiability only).

Otherwise it raises `GridResolutionError`. The one exception is a predictive posterior too small to fit a curvature, which keeps its exact discrete-mixture meaning.

The claim is validated for:

- 2- to 5-parameter grids;
- Gaussian and near-Gaussian posteriors;
- flat, bounded and broad-bimodal shapes.

It does not certify UQ for problems whose grids cannot be built. The V1 grid route remains limited to small p, around ≤ 5.

## 16. What still requires Core V2

- Scalable, non-grid posterior UQ for p > ~5, from the Battery B3 CORE_GAP_CANDIDATE and the HD-UQ review. This round does not add it.
- Resolution checks for non-lattice point sets, or for linearly mapped lattices with a carried basis.
- A resolution check that is not a single local quadratic: multimodal or strongly non-Gaussian posteriors.
- Hybrid routing between grid and non-grid UQ.
- Restating K2's MULTI covariance and C2 predictive sd, and K3, K3.1 and K4's grid-based predictive numbers. These need a resolved grid or a non-grid route: a Domain re-run on V1, or V2.
