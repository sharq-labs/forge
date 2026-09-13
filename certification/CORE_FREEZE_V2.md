# Core Freeze V2 — Scalable Hybrid Uncertainty Quantification

**Where:** branch `claude/core-v2-hybrid-uq` · tag `v2.0-core-freeze` · manifest `certification/core_freeze_v2.json` · assurance `certification/core_freeze_v2_assurance.json`.

**Verification:**

```
python -m tools.certification.core_freeze_v2 --verify     # V2 contract + assurance; runs the V1 verifier inside
python -m tools.certification.core_freeze --verify        # Core Freeze V1, unchanged, still OK
python -m tools.certification.core_certificate --verify
```

## 1. Verdict

**CORE FROZEN — V2**

- V2 is additive, and V1 history is not rewritten.
- The V1 manifest, V1 assurance and `v1.0-core-freeze` tag are untouched, and the V1 verifier still passes.

## 2. Commits

| | |
|---|---|
| `V2_BASELINE` | `7519aee559750f51bfc58aea12ab29ec199743f4`: V1 plus the certified thin-ridge repair; FAST 5008, FULL 5554, both verifiers OK |
| API design + compatibility proof | `d19e0b7`, committed before any implementation |
| implementation | `f9c5e58`; route corrections from real domains in `86c336b` |
| assured candidate | `7876bd9f3e22…` |
| `src/` tree object | `bbd0cc9d5dbf5eab6bdade8d2edbc574dcddb9fe`, identical at `86c336b`, the candidate and the tag |
| evidence and certification commits | `6e9c1e8`, `624b7cf`, `939ba1a`, `bcd6440`, `278b91b`, `cdf0cf3`, and the commit that adds this report (named by the tag) |

**Where each assurance run was made.** The certified 79 ran at `3ca1c82`, the HD matrix at `3d4cabf` and the wheel at `5d0ced5`. All three have the candidate's `src` tree and byte-identical pinned harness files. The named suites, FAST and FULL ran on the candidate itself.

## 3. Public API

| surface | modules | frozen | total | frozen digest |
|---|---|---|---|---|
| V1 (unchanged) | 7 | **194** | 205 | `c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929` |
| **V2** | 7 + `engcore.hybrid_uq` | **221** | 232 | **`fd7d3f9f3f7d641e7484df15dd6ae4ac09cf4b072a19f230d6fcfb75fc9f37cb`** |

**How V1 stays unchanged.** No V1 canonical module exports a V2 name. `api_snapshot.build()` still yields the V1 snapshot byte-for-byte, and both pinned V1 files compare equal. Every V1 frozen entry is byte-identical inside the V2 snapshot (`tests/test_core_v2_compatibility.py`, `v1.symbols_preserved`).

**The 27 new frozen symbols** (`engcore.hybrid_uq`):

- **Vocabulary:** `ApproximationClass`, `RouteClaim`, `RouteReason`, `RouteDecision`, `HybridUQError`, `RouteRefusedError`, `PARAMETER_UNCERTAINTY`, `MEASUREMENT_UNCERTAINTY`, `MODEL_DISCREPANCY_NOT_MODELLED`, `UNCERTAINTY_SOURCES`, `GRID_ROUTE_MAXIMUM_PARAMETERS`
- **Sensitivity:** `LocalSensitivity`, `reconstruct_local_sensitivity`
- **Local route:** `MultistartPolicy`, `RouteDiagnostics`, `ParameterInterval`, `LocalGaussianPosterior`, `local_gaussian_posterior`
- **Identifiability:** `RoutedIdentifiability`, `assess_routed_identifiability`
- **Predictive:** `RoutedPredictiveUncertainty`, `linearized_predictive_uq`, `grid_predictive_uncertainty`
- **Routing:** `GridRebuildPolicy`, `HybridUQResult`, `route_uncertainty`, `routed_predictive_uncertainty`

**Other properties of the addition:**

- No new exception root: both V2 errors descend from `engcore.uq.UQProblemError`.
- New layer `hybrid_uq`, directly above `uq`. It imports only `scientific`, `inference` and `uq`.

**V1 files touched, and nothing else in V1:**

- `src/engcore/api_snapshot.py`: `V2_CANONICAL_MODULES` and a keyword-only `modules=` argument with a V1 default;
- the layering and policy tests: the new layer, and V2 module names allowed in prose;
- `docs/CORE_FREEZE_POLICY.md`: new §12; the FROZEN-STATE table is unchanged;
- `tools/certification/core_certificate.py`: new certified area.

## 4. Approximation classes and routes

| class | exact posterior? | produced when |
|---|---|---|
| `POSTERIOR_GRID` | no: a discretization, used only after the repaired V1 checks accept it | a grid is supplied and accepted, or rebuilt from the local covariance and accepted |
| `LOCAL_GAUSSIAN_APPROXIMATION` | no | local validity diagnostics SUPPORT it (or DOWNGRADE it, with reasons) |
| `LINEARIZED_PREDICTIVE_UQ` | no | predictions from a non-refused local posterior |

**Routing rule** (deterministic, order fixed; every route tried is recorded in `considered`):

1. **Grid as supplied:** p ≤ 5 and the frozen `assess_identifiability` accepts it.
2. **Local Gaussian:** SUPPORTED.
3. **Grid rebuilt from the local covariance:** p ≤ 5. The router checks containment, converges at declared bounds, and needs V1 acceptance, with up to 3 V1-driven refinements.
4. **Local Gaussian:** DOWNGRADED.
5. **Otherwise REFUSED:** no mean, covariance or identifiability.

**Grid route status.** The repaired V1 behaviour is unchanged. The router never accepts a grid V1 refuses (HD-8 is killed). For grid *design* only, it uses two private V1 helpers (`_minimum_aliasing_number`, `_ALIASING_NUMBER_MINIMUM`); acceptance is always the frozen public function.

## 5. Local-route validity diagnostics

Thresholds are recorded in every `RouteDiagnostics`.

**Refusals:**

| code | condition |
|---|---|
| `CALIBRATION_NOT_CONVERGED` | the calibration did not converge |
| `FORWARD_INADMISSIBLE_NEAR_ESTIMATE` | a forward point near the estimate is inadmissible (`InferenceAdmissibilityError` counts as refusal of the point) |
| `NO_RESIDUAL_DEGREES_OF_FREEDOM` | p ≥ n |
| `STRUCTURALLY_UNIDENTIFIABLE` | rank < p |
| `NUMERICALLY_SINGULAR_JACOBIAN` | equilibrated cond > 6.7e7 |
| `PARAMETER_AT_BOUND` | Gauss–Newton step > 0.05 sd through a bound |
| `NOT_STATIONARY` | step > 0.05 sd otherwise |
| `NOT_A_LOCAL_MINIMUM` | a ±2 sd probe lowers χ² |
| `NONLINEAR_BEYOND_LOCAL_GAUSSIAN` | index > 0.5 |
| `SECOND_MODE_FOUND` | multistart finds another optimum of comparable fit |
| `BETTER_OPTIMUM_FOUND` | multistart finds a better optimum |

**Downgrades:**

| code | condition |
|---|---|
| `BOUND_WITHIN_3_SD` | a bound lies within 3 sd |
| `NONLINEAR_WITHIN_2_SD` | index > 0.1 |
| `NONLINEARITY_PROBE_INCOMPLETE` | a probe could not be evaluated |
| `POORLY_SCALED_PARAMETERIZATION` | raw cond > 6.7e7 while the equilibrated condition is fine |
| `GLOBAL_UNIQUENESS_NOT_ASSESSED` | no multistart was run |
| `MULTISTART_INCOMPLETE` | fewer than half the starts converged |
| `PREDICTIVE_NONLINEAR` | predictive nonlinearity above threshold |

**Multistart** (mandatory for a SUPPORTED claim):

- deterministic Halton starts in the central 80% of the inference-space box, run through the frozen `calibrate`;
- inadmissible starts are retracted toward the estimate and recorded;
- an optimum is "materially different" when Mahalanobis² > χ²_p(0.999);
- it counts as a second mode when its χ² is within χ²_p(0.99) of the best, and as a better optimum when its χ² is lower by more than that.

**Design amendments, recorded in `docs/CORE_V2_API_DESIGN.md`:**

1. **Rebuilt-grid containment and bound-truncation convergence.** Without them F1 lost its tail (θ₁ mean 3.31 vs 3.43), and F2 was biased 0.27 sd at the bound.
2. **Retraction of inadmissible starts.** Without it every Battery B3 model was capped at MULTISTART_INCOMPLETE.
3. **`InferenceAdmissibilityError` is a refusal of the point.** The TCR evaluator raises it.

## 6. Cross-domain results

### Battery B3, T41 flagship (`BATTERY_T41.json`)

**Setup:** p = 41, no grid, frozen `calibrate` and the production adapter.

| | T41 through V2 | B3 committed domain route |
|---|---|---|
| decision / claim | LOCAL_GAUSSIAN / SUPPORTED, multistart no second mode (6/6 converged; each start retracted 1–2×) | — |
| route runtime | 62.7 s | — |
| forward evaluations | 2195 (165 Jacobian + diagnostics, 2030 multistart) + 165 predictive | — |
| memory (tracemalloc) | 0.57 MB heap | — |
| posterior sd | 0.0091 – 0.0220 V; max \|correlation\| 0.66 | agreement 2.3e-11 relative |
| posterior mean | — | agreement 2.2e-9 sd |
| 95% interval, knot 0 | [2.5868, 2.6562] V | — |
| predictive total sd | 0.0120 – 0.0303 V (parameter sd 0.0061 – 0.0151 V) | agreement 1.5e-11 relative |
| held-out | RMSE 7.547 mV, χ² 2.1999 on 33, coverage 33/33 | χ² agreement 5.9e-10 |
| identifiability | knot voltages IDENTIFIABLE, successive differences NOT_IDENTIFIABLE, distinct parameterization identities | equal |

**All 13 scored models** are SUPPORTED; 12 of 13 are within B3's declared tolerance.

- **P9 misses** the χ² tolerance: 4.7e-6 against 1e-6. This is the known centring difference between `calibrate` and closed-form WLS. The tolerance was not moved.
- All six models with a committed CORE_GRID agree with it.

### TCR (`TCR.json`, `tests/hybrid_uq/test_hybrid_uq_tcr.py`)

The same design is compared against the exact posterior (dense quadrature) and a resolved grid.

| design | V2 claim | mean shift vs exact | sd ratio vs exact | identifiability V2 / resolved grid |
|---|---|---|---|---|
| WIDE (8 T, 300–440 K) | SUPPORTED | 0.0011, 0.0020 sd | 1.000, 1.000 | IDENTIFIABLE / IDENTIFIABLE |
| NARROW (6 T, 299–301.5 K) | SUPPORTED | 0.0054, 0.0107 sd | 1.000, 0.9998 | WEAKLY / WEAKLY |

The router given the 41-node narrow grid follows V1's refusal and uses the local route. The wide 41-node grid is used as supplied.

### Kinetics K2 (`KINETICS_K2.json`)

**MULTI:**

- **Route:** SUPPORTED, no second mode. 4 of 6 starts converged to the same optimum, one to a worse local optimum (χ² 2700), and 2 did not converge within 400 evaluations.
- **Cost:** 607 evaluations (1821 CSTR solves), 4558 s serial.
- **Diagnostics:** nonlinearity index 0.072; equilibrated cond 53, raw cond 8.7e3.
- **Against the converged reference grid:** mean shift 0.050 / 0.051 sd (the MAP versus the posterior mean), sd ratio 0.998, determinant ratio 0.997.

**The route's covariance:**

| quantity | value |
|---|---|
| covariance | [[0.026093, 8.5150], [8.5150, 2782.7]] |
| determinant | 0.10223 |
| correlation | 0.99930 |

**Identifiability:** (ln k₀, E/R) is NOT_IDENTIFIABLE; (ln k(326.8 K), E/R) is WEAKLY_IDENTIFIABLE.

**Parameterization:**

- k₀ natural with IDENTITY: **REFUSED**, nonlinearity 24.9, raw cond 1.0e8;
- k₀ declared LOG: DOWNGRADED only for no multistart, and it reproduces the ln k₀ sd.

**WEAK_C2:** refused (NO_RESIDUAL_DEGREES_OF_FREEDOM). Its reference grid shows an exact ridge at T* = 324.37 K, the C2 reactor temperature.

## 7. Corrected K2 values

Errata E4 is restated with measured values (addendum in `benchmarks/core_v1_thin_ridge_repair/ERRATA.md`).

| quantity | committed (aliased) | V2 route | converged reference |
|---|---|---|---|
| MULTI covariance | [[0.02311, 7.528], [7.528, 2452.0]] | [[0.02609, 8.515], [8.515, 2782.7]] | [[0.02618, 8.545], [8.545, 2792.6]] |
| MULTI determinant | 0.001812 | 0.10223 | 0.10253 |
| MULTI correlation | 0.999984 | 0.999296 | 0.999299 |
| C2 C_A epistemic predictive sd | ≈0.27 | 1.649 | 1.648 |
| C2 C_A total predictive sd | ≈2.02 | 2.592 | 2.592 |
| C2 T epistemic predictive sd | — | 0.1116 K | 0.1115 K |
| WEAK_C2 determinant | 3.891 | refused | 7.469 |
| A5 ratio (≤ 0.5) | 4.66e-4 | — | **0.0137 (PASS)** |
| A5 gain | 2147× | — | **72.8×** |

## 8. Failure cases (`FAILURE_CASES.json`)

Every expectation was declared before its case ran. **10 of 10 met.**

| case | local route | router |
|---|---|---|
| strong nonlinearity | REFUSED nonlinear | rebuilt grid within 0.05 sd of dense reference |
| parameter at bound | REFUSED at bound | rebuilt grid converged at the bound, within 0.05 sd |
| nearly singular Jacobian | REFUSED singular | REFUSED, no rebuild |
| mirror mode | REFUSED second mode | rebuilt grid (mean 0, sd 0.99 vs 1.01 reference) |
| two-parameter multimodal | REFUSED second mode | rebuilt grid within 0.05 sd |
| log parameterization of a linear model | REFUSED nonlinear | — |
| poorly scaled parameterization | DOWNGRADED poorly scaled | — |
| weak identification | SUPPORTED + NOT_IDENTIFIABLE (two verdicts) | — |
| thin correlated ridge + aliased bounds grid | SUPPORTED, exact | V1 refuses the grid → LOCAL_GAUSSIAN |
| mapped / non-tensor point set | — | V1 refuses → REFUSED alone, LOCAL_GAUSSIAN with local inputs |

## 9. Performance (`PERFORMANCE.json`)

**Workload:** TabulatedForm knots on the B3 data, production adapter.

**V2 route, measured:**

| p | calibration | diagnostics + Jacobian (4p+1) | route with multistart | predictive | heap |
|---|---|---|---|---|---|
| 2 | 0.25 s / 16 | 0.13 s / 9 | 2.3 s / 146 | 0.08 s / 9 | 0.09 MB |
| 5 | 0.61 s / 36 | 0.40 s / 21 | 5.2 s / 291 | 0.16 s / 21 | 0.12 MB |
| 10 | 1.21 s / 66 | 0.75 s / 41 | 9.6 s / 519 | 0.44 s / 41 | 0.17 MB |
| 20 | 2.88 s / 126 | 1.93 s / 81 | 23.5 s / 1081 | 0.83 s / 81 | 0.28 MB |
| 41 | 6.44 s / 252 | 4.24 s / 165 | 60.6 s / 2154 | 2.42 s / 165 | 0.56 MB |

**V1 grid** (9 per axis, ±4 SE):

| p | status | points | wall | heap |
|---|---|---|---|---|
| 2 | MEASURED, serial | 81 | 2.1 s | 2.0 MB |
| 3 | MEASURED, serial | 729 | 19.0 s | 15.9 MB |
| 4 | MEASURED, serial | 6561 | 178.8 s | 141 MB |
| 5 | B3's committed 12-worker run | 59049 | 213–228 s | — |
| 10 | PROJECTED | 3.5e9 | ≈3.0 years serial | — |
| 20 | PROJECTED | 1.2e19 | ≈1e10 years | — |
| 41 | PROJECTED | 1.3e39 | infeasible | — |

The p = 3 and p = 4 grids ran while the K2 reference grid was using 16 workers, so those wall times are high. The review measured 154 s at p = 4 on an idle host.

## 10. Serialization and identity

**Eight V2 records** have explicit schemas `hybrid_uq.<record>/1`:

- `LocalSensitivity`, `MultistartPolicy`, `RouteDiagnostics`, `ParameterInterval`;
- `LocalGaussianPosterior`, `RoutedIdentifiability`, `RoutedPredictiveUncertainty`, `HybridUQResult`.

**Serialization properties:**

- canonical JSON (sorted keys, `allow_nan=False`, non-finite floats as names);
- byte-identical round trips;
- readers refuse any unknown schema, and any record claiming `exact`;
- `GridRebuildPolicy` is export-only.

**Identity properties:**

- digests cover material fields only;
- evaluation counts are non-material, with paired tests in both directions;
- the parameterization label and digest are material, so two parameterizations never share an identity (HD-9 is killed);
- identity reference digests of literal fixtures are pinned in the manifest;
- fresh-process digest stability is tested under a different `PYTHONHASHSEED`;
- no V1 schema or digest changed.

## 11. Mutations

**Certified 79** (`MUTATION_HARNESS_79.log`): control GREEN (470 passed), **79/79 killed**, pinned harness files unchanged.

**HD matrix** (`HD_MUTATIONS.json`): control GREEN (93 passed), **10/10 killed**.

| id | mutation |
|---|---|
| HD-1 | bypass validity |
| HD-2 | ignore bound refusal |
| HD-3 | ignore singular Jacobian |
| HD-4 | remove multistart |
| HD-5 | mislabel as exact |
| HD-6 | drop parameter uncertainty |
| HD-7 | linear-sum merge |
| HD-8 | trust unresolved grid |
| HD-9 | ignore parameterization identity |
| HD-10 | predictive accepts refused route |

## 12. Assurance on the candidate (`SUITES.json`)

**Tests:**

| check | result |
|---|---|
| FAST | **5117 passed**, 5 skipped |
| FULL | **5663 passed**, 5 skipped |
| focused `tests/hybrid_uq` | 97 |
| V1 thin-ridge regressions | 80 |
| battery | 265 |
| TCR | 156 |
| kinetics | 19 |
| serialization | 76 |
| identity | 58 |
| dependency / layering | 39 |
| API snapshot V1 | 51 |
| API snapshot V2 | 12 |
| contract guard | 305 |
| V1 freeze manifest | 22 + 1 skipped |
| certificate | 28 + 1 skipped |
| V2 freeze manifest | 6 + 1 skipped by design before the assurance record existed |

**Build and certification:**

| check | result |
|---|---|
| wheel (`WHEEL_V2.json`) | V1 parity **MATCH**, V2 parity **MATCH**; isolated `-S -E` smoke passes (supported affine route; structurally singular model refused) |
| certificate | reissued at `624b7cf`: 84 files, aggregate `090b37d95ee13190231657ba0871354451a6639febf6e70e7797a75586044256`, new certified area `routed_uncertainty`; `--verify` OK |
| freeze verify | V2 OK (DESCENDANT of candidate, every check PASS); V1 OK (DESCENDANT, `contract.api` PASS) |

## 13. Exact V2 capability claim

The claim as recorded in the manifest (`capability_claim`):

> Core V2 adds routed uncertainty quantification beside Core V1's grid route, for calibrations posed through `engcore.inference.calibrate` with declared Gaussian observation noise and a flat prior inside declared bounds.
>
> `route_uncertainty` is deterministic, records every route it considered, and returns one of:
>
> - **POSTERIOR_GRID**, when a supplied tensor grid of at most 5 parameters passes the repaired V1 resolution checks;
> - **LOCAL_GAUSSIAN_APPROXIMATION**, when its validity diagnostics support it: N(ẑ, (J_wᵀJ_w)⁻¹) in declared inference coordinates, O(p) forward evaluations plus a mandatory deterministic multistart;
> - **POSTERIOR_GRID rebuilt from the local covariance**, when a rebuild policy is supplied, p ≤ 5, and the rebuilt grid is contained, converged at declared bounds, and accepted by the V1 checks;
> - **the local Gaussian DOWNGRADED**, with its reasons;
> - **REFUSED**, with no numbers.
>
> Identifiability uses the frozen V1 thresholds and rule in a recorded parameterization. Predictive uncertainty keeps parameter and measurement uncertainty separate and names model discrepancy as not modelled. No approximation class is an exact posterior.

## 14. Non-claims

- Not an exact posterior, in any route.
- Global mode uniqueness is not proved: multistart bounds it, it does not prove it.
- There is no model-discrepancy estimate, no estimated noise, no non-Gaussian likelihood and no informative prior.
- There is no MCMC, full-Hessian Laplace, sparse-grid or importance-sampling posterior.
- There is no grid route above 5 parameters. Non-tensor or linearly mapped point sets are refused, not checked.
- There is no adequacy scoring over the linearized predictive in the frozen API; `engcore.adequacy` is unchanged.
- No V1 symbol, signature, default, enum, record schema, serialization or identity digest changed.
- The local-route thresholds are declared engineering thresholds, validated on Battery B3, TCR, K2 and synthetic failure cases; they are not universal guarantees.

## 15. What remains Domain-first

- **Domain adapters:**
  - analytic or retained Jacobians supplied as `LocalSensitivity` (the reconstruction costs 2p+1 evaluations);
  - admissible-region knowledge for multistart starts (retraction is generic but coarse);
  - multistart budgets per domain (the K2 multistart alone was 76 minutes serial).
- **Held-out adequacy and scoring** over the linearized predictive (Battery χ² and coverage are computed in the benchmark), and cross-class model comparison.
- **Weakly identified designs with no residual degrees of freedom** (K2 C2-only), which V2 refuses:
  - a resolved grid in decorrelated coordinates, as built here, is a domain construction;
  - V2's rebuild policy works only in declared coordinates.
- **Parameterization choices:** decorrelated or log coordinates, reference temperatures, knot versus difference reporting.
- **Restating K3, K3.1 and K4 predictive numbers** on the corrected K2 posterior.
- **Model-discrepancy modelling.**
