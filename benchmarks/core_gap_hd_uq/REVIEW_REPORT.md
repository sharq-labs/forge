# Core Gap Review — High-Dimensional Uncertainty Quantification

Branch `claude/core-gap-hd-uq-review` · baseline `10291d2` (B3 head) · **read-only review** · Core Freeze V1 untouched

```
python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py failure        # Phase 10
python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py battery        # Phases 1, 6, 9  (~25 min serial)
python -X utf8 benchmarks/core_gap_hd_uq/audit/explain_p9.py                # the one declared-tolerance miss
python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py tcr            # Phase 7
python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py kinetics       # Phase 7  (~12 min, serial CSTR)
python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py scaling        # Phases 1, 11
python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py compatibility  # Phases 2, 3, 8
python -X utf8 -m pytest benchmarks/core_gap_hd_uq/tests -q                 # 19 tests
```

**What exists, and what does not.**

- **The candidate route is a probe, not a backend.** It lives in `audit/local_gaussian_probe.py` and uses only the frozen public API. Nothing under `src/` imports it.
- **No Core file was edited.**

## 1. FINAL VERDICT

**CORE GAP CONFIRMED — REQUIRES CORE FREEZE V2**

**The gap is real and generic:**

- **Battery (p = 41):** it forced a domain-side route.
- **Kinetics (p = 2):** each CSTR forward evaluation costs ~0.7 s, so the frozen grid took 11,163 solves.
- **TCR (p = 2):** grid and candidate route agree; it adds cross-domain reuse, not cost pressure.

**The extension is scientifically additive.** No existing symbol, signature, record, digest, verdict or grid behaviour would change.

**It still cannot be delivered as a Core Freeze V1 descendant.** Every way of making it a public or certified Core contract fails a check the V1 verifier treats as **binding in DESCENDANT mode**:

- **public API:** `contract.api` and `bytes.pinned_contract_files`;
- **certified scope:** `certificate.verifies`.

The one location that passes the verifier, a non-exported module under `uq/`, is rejected on scientific grounds (§21).

**STOPPED.** Nothing was implemented.

## 2. EXACT GENERIC GAP

`engcore.inference` / `uq` / `adequacy` have **no way to produce parameter covariance, marginal intervals, identifiability or predictive uncertainty except by enumerating a tensor grid**. `PosteriorGrid` is the only covariance in the Core.

- `assess_identifiability`, `posterior_predictive_uq` and `assess_predictive_observation` each take a `PosteriorGrid`.
- `calibrate` computes, and then discards, the optimizer's Jacobian.

**The smallest generic capability** (details in `COMPATIBILITY.json` → `phase2_generic_requirement`):

- **Given:** the `calibrate` estimate, the forward evaluator `calibrate` already takes, observations and declared sigmas, parameter identities with bounds and transforms, and optionally a predictive evaluator.
- **Produce, under a named approximation class:**
  - covariance, correlations and marginal intervals;
  - identifiability under the **frozen thresholds** in the declared parameterization;
  - linearized predictive mean and sds;
  - explicit refusals and downgrades.
- **Cost:** O(p) forward evaluations, never m^p.

**Not required by B3:** full-Hessian Laplace, MCMC, sparse grids, non-Gaussian likelihoods, discrepancy models, autodiff.

## 3. B3 REPRODUCTION

`BATTERY_B3_REFERENCE.json`. The tolerances were declared in `review_battery.py` before the comparison ran.

| model | p | probe claim | vs B3 linear-Gaussian route | vs frozen Core grid |
|---|---|---|---|---|
| P1 | 2 | SUPPORTED | ✔ (mean 6e-7 sd, sd 3e-12) | ✔ mean 0.000 sd, sd ratio 1.0000, χ² 366.38 = 366.38, adequacy equal |
| P2 | 3 | SUPPORTED | ✔ | ✔ χ² 258.64 = 258.64 |
| P3 | 4 | SUPPORTED | ✔ | ✔ sd ratio 1.0001, predictive sd 1.6e-5, χ² 149.58 / 149.57 |
| P4 | 5 | SUPPORTED | ✔ | ✔ χ² 112.14 = 112.14 |
| T3 | 3 | SUPPORTED | ✔ | ✔ χ² 278.72 = 278.72 |
| T5 | 5 | SUPPORTED | ✔ | ✔ χ² 47.01 = 47.01, ADEQUATE = ADEQUATE |
| P5, T6, T11, T21 | 6–21 | SUPPORTED | ✔ | — (no grid) |
| P7, P9 | 8, 10 | DOWNGRADED (`GLOBAL_UNIQUENESS_NOT_ASSESSED`) | P7 ✔; **P9 ✘ χ² 4.7e-6 > declared 1e-6** | — |
| **T41** | **41** | **SUPPORTED** | **✔ mean 2.2e-9 sd, sd 2.3e-11, predictive sd 1.5e-11, χ² 5.9e-10** | — |

**P9 misses its declared tolerance.** The tolerance was not moved.

- **Cause:** the two routes are centred at different estimates, 2.7e-7 V apart: the frozen `calibrate` estimate for the probe, the closed-form WLS estimate for B3's route.
- **Check:** re-centred at the WLS estimate, P9's χ² agreement becomes 2.0e-10, and every model is ≤ 1e-9 (`explain_p9.py`).

**P7 and P9 downgrades.** Their affine-verification residual (1.7e-6, 1.4e-5) exceeds the 1e-6 tolerance: finite-difference rounding on ill-conditioned high-degree node polynomials. The probe therefore cannot credit "declared affine". That is conservative, not a refusal.

**T41 flagship.** The probe reproduces B3's T41 and all its derived quantities:

| quantity | value |
|---|---|
| held-out RMSE | 7.547 mV |
| χ² | 2.19986 on 33 |
| coverage | 33/33 |
| adequacy | ADEQUATE |
| identifiability | IDENTIFIABLE |
| successive-difference parameterization | NOT_IDENTIFIABLE (as B3) |

**Verification tiers on T41, through the real adapter:**

| tier | cost | result |
|---|---|---|
| importance reweighting (option C) | 2,000 forward calls | ESS **1.000** |
| full finite-difference Hessian (option A) | 3,444 χ² calls | Laplace / Gauss-Newton sd ratio **1 ± 2e-11** |

## 4. PARAMETER COUNT WHERE GRID BECOMES IMPRACTICAL

**p = 6** on this 32 GB host, for the B3 forward cost. **p = 7** is out of reach on any single machine.

- **Grid rule:** 9 points per axis over ±4 marginal SE; 67 calibration + 33 held-out observations; production adapter at 0.0235 s per grid row serial (all 100 predictions).
- **Measured serial:** p = 2, 3, 4.
- **Committed B3 run:** p = 5, on 12 workers.
- **Projected:** p ≥ 6, from the p = 4 per-row cost and memory, and labelled PROJECTED in `SCALING.json`.

| p | grid points | production predictions | wall (serial) | calibration-table memory |
|---|---|---|---|---|
| 2 | 81 | 8,100 | **1.8 s** measured | +2.1 MB RSS |
| 3 | 729 | 72,900 | **16.3 s** measured | +13.3 MB |
| 4 | 6,561 | 656,100 | **154 s** measured | +145 MB (21.6 kB/row) |
| 5 | 59,049 | 5.9 M | **213–228 s on 12 workers** (B3) | 1.2 GiB projected |
| 6 | 531,441 | 53 M | 3.5 h projected | **10.7 GiB** projected |
| 7 | 4.8 M | 478 M | 31 h projected | **96 GiB** projected |
| 10 | 3.5 × 10⁹ | 3.5 × 10¹¹ | 2.3 × 10⁴ h | 7 × 10⁴ GiB |
| 41 | 1.3 × 10³⁹ | 1.3 × 10⁴¹ | — | — |

**The threshold depends on forward cost.** For kinetics (K2) the grid was already the dominant cost at **p = 2**: 3,721 points × 3 CSTR solves, 1,357 s on 24 workers.

## 5. EXISTING CORE PRIMITIVES

Full inventory in `COMPATIBILITY.json` → `phase3_existing_primitives`.

**Reusable:**

- the `calibrate` estimate, residuals, provenance and caller-supplied vector evaluator;
- `ParameterIdentity` / `ParameterBounds` / `ParameterTransform {IDENTITY, LOG}`;
- the **thresholds and classification rule** of `assess_identifiability` (the probe reads them from its signature rather than copying them);
- the `Uncertainty` record's `method` field;
- `PredictiveEvidenceIdentity`, which does not depend on the UQ method;
- `engcore.execution.run_sweep`, from the studies layer, for parallel Jacobian columns.

**Absent:**

- any numerical Jacobian (the `consensus` JACOBIAN is a route-independence label, not a derivative);
- Hessian, Fisher / information matrix, Laplace;
- any sampler;
- sparse structure;
- any reparameterization map between parameter sets;
- a delta method (one exists only in the EXPERIMENTAL TCR study oracle).

**Not reusable as-is:**

- **`PosteriorGrid`:** non-negative weights over enumerated points;
- **`assess_identifiability`:** takes a grid, and raises on grid geometry;
- **`QuantifiedPredictiveResult`:** `posterior_support_size >= 1` is a grid concept;
- **`calibrate(uncertainty_method=...)`:** a free-text provenance string with no computation behind any other value.

## 6. OPTIONS EVALUATED

| option | assumptions | failure modes (measured where marked ✔) | cost | bounds | nonlinearity | multimodality | identity/evidence fit |
|---|---|---|---|---|---|---|---|
| **A. Laplace** (full Hessian at the mode) | unimodal; posterior ≈ Gaussian at the mode | ✔ equals Gauss-Newton on affine models (T41: 1 ± 2e-11); ✔ on F1 (strong nonlinearity) sd ratio 0.91–0.97 against a grid 1.7× wider — curvature at the mode does not fix non-Gaussian tails | O(p²) evaluations (T41: 3,444) | ignores them | local curvature only | ✔ blind (F4) | as B |
| **B. Jacobian / Gauss-Newton linearized** | locally affine within ~2 sd; Gaussian noise; flat prior; interior optimum | ✔ exact on affine forms; ✔ refused/downgraded on every F case (§9); needs diagnostics to know | **O(p)** (T41: 165 calls) | must refuse at a bound and downgrade near one | exact only if affine; diagnosable along principal axes | blind without multistart | new records; evidence identity unchanged |
| **C. Adaptive sampling / importance reweighting** | Gaussian proposal covers the posterior | ✔ ESS collapses when the Gaussian is wrong (F1 0.21, F6-log 0.006); ✔ **ESS 1.0 on a mirror mode** (F4) — it cannot find mass the proposal never visits; degrades with p for any mismatch | O(M) evaluations (T41: 2,000; K2: 100 → 300 solves, 207 s) | handles by zero weight | corrects moderate nonlinearity (K2: sd ratio 1.06 → 0.98 against the grid) | blind to unvisited modes | good as a VERIFICATION tier |
| **D. Sparse grids** (Smolyak) | smooth, unimodal integrand in a box | negative quadrature weights violate `PosteriorGrid`'s `weights >= 0` invariant; no discrete marginal intervals; oscillation near bounds and kinks | level-2 nested Clenshaw–Curtis ≈ 2p² + 2p + 1 points (p = 41: 3,445), level 3 ≈ O(p³) | poor | limited by smoothness | fails | **incompatible with the existing posterior contract** |
| **E. Hybrid** | grid where feasible; B with mandatory diagnostics elsewhere; C optional | inherits B's refusals; grid remains for weak or bounded data (K2 C2-only) | O(m^p) for small p; O(p) + O(p) diagnostics otherwise | grid handles bounds; B refuses | B diagnoses; C verifies | multistart required | two approximation classes, never merged |

## 7. RECOMMENDED METHOD

**E — hybrid, with B as the scalable route and C as an optional verification tier.**

- **`POSTERIOR_GRID`** (unchanged) remains the route for low p. It is also the route wherever B refuses:
  - weak data where bounds shape the posterior (K2 C2-only);
  - active bounds;
  - multimodality;
  - strong nonlinearity.
- **`LOCAL_GAUSSIAN_APPROXIMATION`** = N(θ̂, (J_wᵀ J_w)⁻¹) at the frozen `calibrate` estimate. It comes with `LINEARIZED_PREDICTIVE_UQ` = g(θ̂), diag(G Σ Gᵀ) + σ².
- **Mandatory diagnostics:** rank, residual dof, numerical conditioning, bound activity and proximity, principal-axis nonlinearity at ±2 sd, predictive nonlinearity, and **multistart** for global uniqueness, or a verified affine declaration.
- **`IMPORTANCE_REWEIGHTED_VERIFICATION`** is optional, reported beside B and never replacing it.
- **Rejected:** A (O(p²) with no gain over B where B is valid, and it does not diagnose where B fails) and D (breaks the posterior-weight contract).

## 8. SCIENTIFIC ASSUMPTIONS

Of the recommended local route:

- Gaussian observation noise with declared sigmas;
- a flat prior inside the declared bounds;
- an interior, stationary optimum;
- the model locally affine in θ over the ±2 sd ellipsoid;
- a single posterior mode;
- a forward model smooth enough for central differences at 1e-5 × bound range;
- the covariance numerically representable (cond(J_w) ≤ 1/√ε).

Each assumption has a diagnostic, except "single mode", which only multistart can bound and never prove.

## 9. FAILURE MODES

`FAILURE_CASES.json`. Every reference is the frozen grid over analytic synthetic rows.

| case | probe claim | reason | Gaussian vs frozen grid |
|---|---|---|---|
| F1 strong nonlinearity (y = θ₂ e^(−θ₁x)) | **REFUSED** | NONLINEAR_BEYOND_LOCAL_GAUSSIAN (index 1.65) | grid θ₁ mean 3.43 vs 2.58, sd 1.75 vs 1.04; importance ESS 0.21 |
| F2 parameter at bound | **REFUSED** | PARAMETER_AT_BOUND | Gaussian sd 0.020 vs bounded-grid 0.006 |
| F3 nearly singular Jacobian | **REFUSED** | NUMERICALLY_SINGULAR_JACOBIAN (cond 6.7e9) | — |
| F4 mirror mode (y = θ²x), no multistart | **DOWNGRADED** | GLOBAL_UNIQUENESS_NOT_ASSESSED | grid mean 0.00 sd 1.01 vs Gaussian 1.006 ± 0.007; importance ESS 1.00 and Laplace = GN — **no local diagnostic sees it** |
| F4 mirror mode, with multistart | **REFUSED** | SECOND_MODE_FOUND (θ = −1.006) | — |
| F5 weak identifiability (x ∈ [10, 10.05]) | DOWNGRADED | route valid (affine); identifiability **NOT_IDENTIFIABLE** — two verdicts, never merged | see the finding below |
| F6 k linear | SUPPORTED | — | sd 0.0567 vs grid 0.0566 |
| F6 same model in log k | **REFUSED** | NONLINEAR_BEYOND_LOCAL_GAUSSIAN (index 1.55) | grid sd 3.52 vs 0.44 |

### Finding outside this review's scope: a frozen-grid blind spot

On F5, the frozen grid over the declared bounds returned **resolution-stable but wrong** moments:

| window | mean | sd |
|---|---|---|
| grid over declared bounds (201, 401 and 801 per axis) | (0.403, 0.360) | (1.35, 0.135) |
| exact answer | (3.055, 0.095) | (2.40, 0.239) |

**Why the grid is wrong:**

- The θ₁ step is 30–120× the ridge's conditional sd (0.004).
- ESS stays ≥ 9.6 and spacing/marginal-sd ≤ 0.37, so **`GridResolutionError` is never raised**. The guard measures spacing against the *marginal* sd, not the conditional width.

**Why the other answer is exact:** the model is affine and the bounds are > 19 sd away, so the Gaussian is the exact posterior. Importance ESS 1.0 and Laplace = GN confirm it. A ±6 sd window reproduces it at every resolution.

This is recorded with its evidence; it is a separate certified-Core issue, not part of the high-dimensional gap.

## 10. IDENTIFIABILITY BEHAVIOR

**Method:** the probe applies the frozen thresholds (width 1.0, correlation 0.95, condition 1e6) and the frozen classification rule to the Gaussian marginals.

**It matches the frozen grid's status on every comparable case:**

- all 6 B3 grid models;
- 8 of 8 parameterization comparisons (§11);
- TCR wide IDENTIFIABLE = IDENTIFIABLE;
- TCR narrow WEAKLY = WEAKLY;
- F1, F2, F5, F6-linear.

**It differs only where the posterior is not locally Gaussian:**

- **F4:** the grid sees two modes;
- **F6-log:** the grid is heavy-tailed.

In both, the route claim is REFUSED or DOWNGRADED. Identifiability and route validity are reported **separately**; F5 is valid-but-not-identifiable.

## 11. PARAMETERIZATION SENSITIVITY

**Linear reparameterizations of the same posterior, frozen grid vs probe, on B3 models:**

| model | voltages | successive differences | monomial coefficients |
|---|---|---|---|
| P2 | IDENTIFIABLE / IDENTIFIABLE | IDENTIFIABLE / IDENTIFIABLE | **WEAKLY / WEAKLY** |
| T3 | IDENTIFIABLE / IDENTIFIABLE | IDENTIFIABLE / IDENTIFIABLE | — |
| P3 | IDENTIFIABLE / IDENTIFIABLE | **WEAKLY / WEAKLY** | **WEAKLY / WEAKLY** |

**The probe alone, where no grid exists:** P4 differences NOT, P5–P9 differences and coefficients NOT, T5–T41 differences NOT. T41's voltages are IDENTIFIABLE, its differences **NOT_IDENTIFIABLE**.

**Nonlinear reparameterizations:**

- **Kinetics:** (log k₀, E/R) is **NOT_IDENTIFIABLE**: correlation 0.9993 and covariance cond 7.6e7. Re-expressed as (ln k(350 K), E/R) it is **WEAKLY_IDENTIFIABLE** (correlation 0.87). In natural k₀ units the route is **REFUSED**: NUMERICALLY_SINGULAR_JACOBIAN, from a k₀ ~ 10⁹ against E/R ~ 10⁴ scale disparity.
- **Synthetic F6:** k is SUPPORTED, log k is REFUSED.

**The route validity verdict, not only the identifiability verdict, depends on parameterization.** A Core route must record the parameterization it answered in.

## 12. BATTERY RESULT

See §3. The probe reproduces B3's committed linear-Gaussian T41 result, and all 13 models to ≤ 1e-9 once centred identically. It also reproduces the frozen Core grid on all 6 low-dimensional models (means 0.000 grid-sd, sd ratio 1.0000–1.0001, predictive sd ≤ 1.6e-5, identical χ² and adequacy).

| T41 route | wall | forward calls | memory |
|---|---|---|---|
| probe | **5.9 s** | 165 + 165 predictive | 0.3 MB heap |
| grid | impossible | 9⁴¹ points | — |

## 13. SECOND DOMAIN RESULT — TCR / material calibration

`DOMAIN_TCR.json`. Frozen experimental TCR study, with the designs, truth and seed of `tests/inference/test_tcr_calibration.py`.

| design | probe | identifiability probe / grid | mean shift (grid sd) | sd ratio probe/grid | probe cost | grid cost |
|---|---|---|---|---|---|---|
| WIDE (8 T, 300–440 K) | SUPPORTED, multistart no second mode | IDENTIFIABLE / IDENTIFIABLE | 0.001, 0.002 | 1.000, 1.000 | 9 calls, 0.07 s | 1,681 points, 1.4 s |
| NARROW (6 T, 299–301.5 K) | SUPPORTED | WEAKLY / WEAKLY | 0.007, 0.009 | 1.004, 1.004 | 9 calls, 0.08 s | 1,681 points, 1.1 s |

**Nonlinearity:** the bilinear model registers 3e-5 (wide) and 8.7e-3 (narrow).

**Slope parameterization** (R_ref, R_ref·α), which is affine: SUPPORTED, nonlinearity 5e-9, with identical identifiability verdicts.

**What this domain shows:** reuse of the same abstraction. It does not show cost pressure (p = 2).

## 14. THIRD DOMAIN RESULT — Kinetics / CSTR (K2)

`DOMAIN_KINETICS.json`. The frozen K2 forward model, conditions, truth and observation seed were reused read-only. The reference is the committed K2 scored grid: 61×61, 11,163 CSTR solves, 1,357 s on 24 workers.

| quantity | K2 grid (committed) | candidate route |
|---|---|---|
| calibration | — | frozen `calibrate`: CONVERGED in 21 evaluations = **63 solves**, 44 s |
| UQ cost | 11,163 solves | **27 solves** (+ 2 multistart refits) |
| claim | — | **SUPPORTED**; nonlinearity 0.072; multistart no second mode |
| mean (log k₀, E/R) | 20.979, 8775.1 | 20.948, 8765.4 (0.21, 0.20 grid-sd; MAP vs posterior mean) |
| sd | 0.152, 49.5 | 0.162, 52.8 (ratio **1.063, 1.065**) |
| correlation | 0.99998 | 0.9993 |
| importance tier (100 samples, 300 solves) | — | ESS 0.997; corrected sd 0.149, 48.4 (ratio **0.98**); mean shift toward the grid |
| identifiability | — | NOT (log k₀, E/R) → WEAKLY (ln k(350 K), E/R) |
| C2-only weak design (2 observations, p = 2) | grid posterior reported | **REFUSED**: NO_RESIDUAL_DEGREES_OF_FREEDOM, NUMERICALLY_SINGULAR_JACOBIAN — the grid is still required here |

**The capability is reusable beyond Battery.** It is needed wherever the forward model is expensive (kinetics, even at p = 2) or p is large (Battery), and it validates against the grid where both run (TCR).

## 15. GRID VS SCALABLE AGREEMENT

**Where the posterior is locally Gaussian, the routes agree:**

| domain | mean agreement | sd agreement | other |
|---|---|---|---|
| Battery, 6 models | ≤ 0.000 grid-sd | ratio 1.0000–1.0001 | identical identifiability and adequacy; identical parameterization verdicts |
| TCR | ≤ 0.009 grid-sd | ratio ≤ 1.004 | — |
| Kinetics, nonlinear | 0.21 sd | ratio 1.06 (importance-corrected 0.98) | — |

**Where it is not locally Gaussian, the routes disagree, and the probe refuses or downgrades every time:** F1, F2, F4, F6-log.

**The one exception is F5.** There the probe is right and the frozen grid over the declared bounds is wrong (§9).

## 16. PERFORMANCE SCALING

Same data, same adapter.

| p | local route wall | local forward calls (cal + predictive) | production predictions | heap peak | frozen grid wall |
|---|---|---|---|---|---|
| 2 | 0.20 s | 9 + 9 | 900 | 0.03 MB | 1.8 s measured |
| 5 | 0.48 s | 21 + 21 | 2,100 | 0.04 MB | 213–228 s (12 workers) |
| 10 | 1.07 s | 41 + 41 | 4,100 | 0.09 MB | 2.3 × 10⁴ h projected |
| 20 | 2.41 s | 81 + 81 | 8,100 | 0.21 MB | infeasible |
| 41 | 5.92 s | 165 + 165 | 16,500 | 0.31 MB | infeasible |

**Local route cost:** 4p + 1 calibration-set calls, every one of them diagnostic or Jacobian. No scientific check was weakened for speed. The memory figures come from a separate tracemalloc pass; tracemalloc never timed anything.

## 17. API IMPACT

**If implemented** (not done), an additive-only sketch:

- **`engcore.inference`:** an `ApproximationClass` enum, a local-Gaussian posterior record, its diagnostics record, a constructor function, and an identifiability function over it. Reuse the frozen thresholds; do not overload `assess_identifiability`, whose frozen signature takes a `PosteriorGrid`.
- **`engcore.uq`:** a linearized predictive function and result. `QuantifiedPredictiveResult` cannot be reused.
- **`engcore.adequacy`:** a scoring function for the linearized predictive that carries the approximation class.

**Counts:** about 8–10 new frozen symbols, **0 changed**.

**Effect on V1:** `frozen_count` 194 → ~203, `total_count` 205 → ~214, and the frozen digest moves.

## 18. SERIALIZATION IMPACT

- **Existing records:** unchanged.
- **New records** would need their own schema strings (e.g. `local_gaussian_posterior/1`). They grow the serialization inventory (61 round-trippable), which is itself a **binding** V1 contract fact (`contract.serialization`).
- **Legacy readers:** unaffected.

## 19. IDENTITY IMPACT

**No material digest, identity field or pairing semantics changes.**

**What a new record would need:** its own identity with material fields (approximation class, estimate, covariance digest, diagnostics thresholds, parameterization), plus the paired material / non-material tests the policy requires.

## 20. TRUST/EVIDENCE IMPACT

**Unchanged:**

- **Admission:** `AdmittedForwardTable` / row admission is untouched. The new route must treat an inadmissible forward point (`None`) as a refusal, exactly as `calibrate` does.
- **Evidence identity:** `PredictiveEvidenceIdentity` has no method field, so a grid-scored and a local-Gaussian-scored assessment of the same observation share identity. That is correct, because the evidence is the observation.

**Needed:**

- the new assessment must carry its approximation class beside the evidence;
- `compare_log_predictive_scores` across approximation classes must report, or refuse, the class mismatch;
- the design decision behind that behaviour needs review.

## 21. CORE V1 COMPATIBLE?

**Semantically, for callers: yes.** The change is additive (MINOR under `docs/CORE_FREEZE_POLICY.md` §4).

**As a Core Freeze V1 descendant: no.** Every insertion path, checked against the verifier's code (`COMPATIBILITY.json`):

| path | V1 verifier |
|---|---|
| new FROZEN public symbols | **fails** `contract.api` (frozen_digest / frozen_count / total_count, `core_freeze.py:644`) and `bytes.pinned_contract_files` (`:686`), both binding |
| new EXPERIMENTAL public symbols | **fails** `contract.api` (total_count, experimental list) and pinned snapshot bytes |
| non-exported module in `inference/` or `adequacy/` | **fails** `certificate.verifies` (`:677`); both dirs are in `CORE_CERTIFIED` scope. Also carries no API promise |
| non-exported module in `uq/` | passes — **rejected**: the certificate excludes `uq/**` because it "computes nothing a verdict rests on"; identifiability gates claims |
| domain / benchmark code | passes — not Core; this is the gap |

## 22. CORE V2 REQUIRED?

**Yes: `CORE_FREEZE_V2_REQUIRED`.**

**What V2 would involve:**

- a new freeze manifest for the grown API and serialization inventory;
- a certificate reissue for new files under `inference/` and `adequacy/`, with the mutation harness extended through a certification round.

**What it would not involve:** no existing contract is broken, so V2 can be scoped **additive-only**.

## 23. FILES CHANGED

All under `benchmarks/core_gap_hd_uq/`:

- **`audit/`**
  - `local_gaussian_probe.py`
  - `run_review.py`
  - `review_battery.py`
  - `review_domains.py`
  - `review_scaling.py`
  - `review_compatibility.py`
  - `explain_p9.py`
- **Results**
  - `FAILURE_CASES.json`
  - `BATTERY_B3_REFERENCE.json`
  - `DOMAIN_TCR.json`
  - `DOMAIN_KINETICS.json`
  - `SCALING.json`
  - `COMPATIBILITY.json`
- **`tests/test_core_gap_hd_uq_review.py`**
- **this report**

## 24. CORE FILES CHANGED

**0.** No file under `src/`, `tests/api`, `tools/certification` or `certification/` changed.

## 25. RECOMMENDED NEXT ACTION

1. **Decide whether to open a Core Freeze V2 round, scoped additive-only.** Its contents: the hybrid route of §7 (`LOCAL_GAUSSIAN_APPROXIMATION` + `LINEARIZED_PREDICTIVE_UQ` + mandatory diagnostics, optional importance verification tier), with an API review first. Until then, B3's T41 uncertainty stays **domain-side and not Core-certified**, exactly as B3 reported.
2. **Before V2, as a separate certified-Core review:** the frozen grid's resolution guard compares spacing with *marginal* sd and misses thin correlated ridges (§9 finding). That is a trust issue in the existing route, independent of this gap.
3. **Design points to settle in the V2 API review:**
   - how cross-class predictive score comparison behaves;
   - whether multistart is mandatory or a declared-affine exemption is allowed;
   - how a route records the parameterization it answered in (§11).
