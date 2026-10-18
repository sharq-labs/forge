# Cross-review X2: adversarial check of B-01..B-04, E-01..E-04 (D-08), E-06

Target: `D:/forge-main-337519d1` at HEAD `abed661f`. This was a read-only review. I executed no FORGE code, imported nothing
from engcore and ran no pytest. Every source citation below comes from a file I read myself in this session.

Every number comes from my own script, `scratchpad/audit/x2_derivations.py`. It is stdlib only and ran under
`python.exe -I -S`. I wrote it from the cited lines myself and did not rerun the reviewers' scripts. Its numbers are
**independent derivations**; none of them is EXECUTED_REPRODUCED.

## Verdict table

| ID | Original severity | X2 verdict | X2 severity | Evidence class |
|---|---|---|---|---|
| B-01 | MAJOR | CONFIRMED | MAJOR (latent) | SOURCE_PROVEN |
| B-02 | MINOR | CONFIRMED_REDUCED_SEVERITY | OBSERVATION | SOURCE_PROVEN |
| B-03 | MINOR | CONFIRMED | MINOR | SOURCE_PROVEN + derivation |
| B-04 | MINOR | CONFIRMED | MINOR | SOURCE_PROVEN + derivation |
| E-01 | MAJOR | CONFIRMED_REDUCED_SEVERITY | MINOR | SOURCE_PROVEN + derivation |
| E-02 | MAJOR | CONFIRMED (and worse than reported at the default n) | MAJOR | SOURCE_PROVEN + derivation |
| E-03 | MAJOR | CONFIRMED_REDUCED_SEVERITY | MINOR. Geometry proven; consequence PLAUSIBLE_UNPROVEN | SOURCE_PROVEN / STATIC_SUSPICION |
| E-04 / D-08 | MAJOR | CONFIRMED_REDUCED_SEVERITY; part known (holdout reuse acknowledged in code) | MINOR | SOURCE_PROVEN + derivation |
| E-06 | MINOR | CONFIRMED | MINOR | SOURCE_PROVEN |

No finding was REFUTED. None is a DUPLICATE_OF_KNOWN. I grepped `REMEDIATION_2026-10-18.md`,
`GENESIS_STEP0_A1_READINESS_REVIEW.md`, `PROGRESS.md`, `POST_MERGE_REMEDIATION_VERIFICATION.md`,
`P0_SCIENTIFIC_CORRECTNESS_CLOSURE.md`, `FINAL_OWNER_DISPOSITIONS_2026_10_18.md` and `ACTIVE_PLAN.md` for:
- arbitration and coincident points;
- non-convex cells;
- common mode;
- FTCS / amplitude_decay;
- is_point;
- lattice / stride / quantile;
- Halton.

Two partial overlaps, neither a duplicate:
- **E-04.** In-code acknowledgement in `sria/decision/discovery_adapter.py` (docstring of `generated_to_sria_hypothesis`).
- **B-01.** A sibling gap in `docs/work/archive/PROGRESS_BUILD_PHASE_BIG2_TO_BIG13.md:787-789`. That gap is a different mechanism: "removing one of two conflicting data turns UNKNOWN into KNOWN".

---

## B-01: interpolation arbitrates coincident tabulated points by claim_id — CONFIRMED, MAJOR (latent)

**Independent trace** of `materials/properties.py`:
1. `:272` sorts data by `claim_id`.
2. `:309` keeps that order for `candidates`.
3. `:330-342` appends points in that order.
4. `:347` sorts by position (a stable sort).
5. `:348-353` take `below[-1]` and `above[0]`.

Re-derived for a=10 and b=20 at 300 K, c=30 at 400 K, with the state at 350 K:
- `lo` = b and the result is 25.0, KNOWN/INTERPOLATED.
- `claim_digests` = {b, c} (`:300`, from `used=(lo, hi)` at `:367`), so a is not listed.
- If the values are swapped between the ids, the result is 20.0.
- At T = 300 K the same set refuses: `:319-321`, "sources are not arbitrated".

**Attempts to disprove, and how each fared:**
- *An earlier guard refuses coincident positions?* No. `KnowledgeSnapshot.__post_init__` (`scientific/knowledge/snapshot.py:26-28`) refuses only duplicate ids. `MaterialPropertySet.__post_init__` (`properties.py:270-271`) refuses only a repeated `claim_id`. `InterpolationRule.__post_init__` (`:185-195`) checks only the method and the breakpoints. Coincident positions are constructible through the public API: the test helper `point()` at `tests/test_materials_engine.py:90-91` builds exactly such ranges.
- *Provenance discloses the conflict?* Partly. `set_digest` binds the whole set, so the dropped datum can be recovered from the set. However:
  - `claim_digests` and `sources` omit it.
  - `MaterialCoverageReport` promises at `materials/coverage.py:13-14` that "a conflict between admissible sources is listed as a conflict". Its `conflicted` property (`:71-74`) requires `rule is None`, so an interpolated result with a hidden conflict reads `conflicted=False` and lands in `interpolated`.
  - That is a second documented contract the path violates.
- *No consumer gives it standing?* This is the strongest counter-argument, and it **survives only as a latency argument**:
  - `ResolvedProperty.to_dict` labels the record `resolved_input_not_evidence` (`:238`), and its uncertainty is UNKNOWN (`:366`).
  - The only producers outside tests (`flagships/forge_flagships/geometry_slice.py:134`) build single-datum sets with **no** `InterpolationRule`.
  - Still, `spatial/fields.py:208-212` and `pde/cases.py:42,89` accept any `status == "known"` as a PDE coefficient. A contested value therefore enters a solve as a known number, chosen by identifier order.
  - The invariant is classified AUTHORITY_CRITICAL in `BR15_AUTHORITY_CLOSURE.md:54`.

**Verdict:** the mechanism is SOURCE_PROVEN, so MAJOR stands. There is no production interpolation user today, so the impact is latent. `properties.py` is certified (`current_core_v2.json:11985`).

## B-02: `is_point` uses float equality after an affine conversion — CONFIRMED_REDUCED_SEVERITY, OBSERVATION

**Re-derived:**
- 300 K in degC is `26.850000000000023`. That is ≠ 26.85 and not < 26.85, so the construction guard at `ranges.py:71-74` passes.
- `is_point` (`:80-82`) is then False, and the range is a sliver 2.3e-14 degC wide.
- 26.85 degC in K is exactly 300.0, so only the degC-lower/K-upper order produces the sliver.
- `properties.py:332` then skips the datum without recording it.

**Counter-argument (survives):** the trigger needs *one range* whose two bounds use different units:
- The idiomatic `point(var, q)` passes the same `Quantity` twice, so `is_point` is exact.
- The mixed-unit test (`tests/test_materials_engine.py:323-335`) mixes units *across* data, never within one range.
- A `from_dict` round trip keeps each bound's own unit, so it does not create the problem.
- The consequence is an INTERPOLATED value with UNKNOWN uncertainty that ignores one datum. No refusal turns into support.

I downgrade to OBSERVATION. A robust repair still applies: decide `is_point` with `_exact` in one ratio-scale unit.

## B-03: the DC residual gate scales with common-mode potential — CONFIRMED, MINOR

**Re-derived with exact Fractions** for the circuit nodes a, m, c, two 1 Ω resistors, and V_m corrupted by +0.1 mV (20 % of each branch current), using `dc/validation.py:294-316` row by row:

| V_cm | Residual gate | KCL imbalance |
|---|---|---|
| 0 | FAIL | — |
| 1 kV | FAIL | — |
| 1 MV | PASS (tol_m = 8e-3 against \|r_m\| = 2e-4) | 2e-4 A against a gross current of 1e-3 A, so it FAILs |

The gate first lets this corruption through at V_cm ≈ 25 kV. The NUM-01 docstring (`:83-93`) says the bound is "relative to the quantity it judges"; for the residual check under a common-mode offset that is false.

**Does a FAIL report's `attained_levels` reach any authority?** I traced it:
- `ValidationReport.attained_levels` (`scientific/results/validation.py:1123-1127`) does list NUMERICALLY_CONVERGED even when `status` is FAIL (`:1077-1078`).
- But `credibility/evidence.py:823-824` returns NOT_SUPPORTED on any FAIL **before** it reads the attained levels at `:866`.
- `inference/admissibility.py:269-273` requires `source_result.is_usable`.
- `claims/assessment.py:310` uses the attained levels only to list repairs.
- The MCP server (`mcp/server.py:482,518`) only displays them.

**Residual path (STATIC_SUSPICION, not traced end to end):** `claims/credibility_vector.py:1035-1038` admits *individually attested* PASS checks by digest. An authorized verifier who attested only the residual check, and not the failing KCL check, would back NUMERICALLY_CONVERGED for the VERIFICATION factor; `:661` still also demands a reference-verification level. That needs a trusted role to attest selectively, which is outside B-03.

MINOR stands. With SciPy's backward-stable solve the corruption does not arise; this gate is defence in depth that the KCL check already backs up. Certified (`current_core_v2.json:11912`).

## B-04: FTCS outside its envelope can pass every check — CONFIRMED, MINOR

**Re-derived:** I emulated both the banded stepper (`conduction1d_schemes.py:414-419`) and the default **sparse CSC** matvec (`:388-399`; `solve_with_realization` defaults to `sparse_scheme_solver()`, `:830`), seeded with `sin(pi x/L)` (`:366`).
- At n = 20, r = 0.55: 29 steps keep `max|u| ≤ 1 + 1e-9`, so `amplitude_decay` PASSes (`:636-651`), while the error is at least 10 % of the fundamental. The worst is k ≈ 225: max|u| = 0.91, error 0.88, fundamental 0.047. The field is round-off growth.
- At n = 40, r = 0.75: a single step (k = 52) has a 20 % max-node error.
- Both backends behave alike.

The reviewer's exact counts differ (17 steps, 12 %) because their error measure differs. The window exists either way.

**Counter-arguments:**
- (i) `require_admissible=False` is deliberate (`:825-828`). That fails as a defence: the returned result carries no realization assessment. `validity` at `:893-899` assesses only the model's α, and only `metadata.fourier_number` hints at the problem.
- (ii) The test pins catastrophic failure (`tests/test_model0r_differential.py:282-293`). That is true for its UNSTABLE configuration only, and it does not refute the window.
- (iii) There is no production caller (`git grep solve_with_realization` finds only the module and the tests). This survives, so the severity stays MINOR.

The docstring claim at `:606-609`, that the check "can catch a scheme used outside its stability envelope", is false for this window.

## E-01: stratum midpoints read with the type-7 quantile — CONFIRMED_REDUCED_SEVERITY, MINOR

**Re-derived:** the uniform mass equals 0.95 − 0.95/n exactly. The normal mass and half-widths:

| n | Normal mass | Half-width |
|---|---|---|
| 4 | 0.7234 | ±1.088 sd |
| 32 (default) | 0.9255 | ±1.783 sd |
| 256 | 0.9464 | ±1.930 sd |

Hazen positions recover 0.9500. The path is `mcp/probabilistic_uq.py:47` (midpoints) → `:138-141` (default `np.quantile`), reached from `mcp/server.py:895-917`. The pinned test `tests/mcp/test_probabilistic_uq.py:61-69` (301.5 / 304.5) confirms type 7.

**Counter-arguments that survive and lower the severity:**
- (i) The record is labelled `method: deterministic_latin_hypercube_empirical_central_interval` (`:143`) and "Empirical central intervals" (`:91`).
- (ii) No claim, credibility or verdict path consumes the interval. Each sample's own verdict is computed before it (`:98-112`), and `evaluate_context` is separate.
- (iii) The MCP layer is certificate scope.out.
- (iv) At the default n the bias (0.95 → 0.92) is of the same order as the sampling error an honest 32-point design would carry anyway.

The stated `credible_mass` is still wrong in a known direction, and badly so at the accepted n = 4. Hence MINOR, not dismissed. It compounds with E-02 on the same output.

## E-02: lattice permutations create exact ±1 dependence — CONFIRMED, MAJOR (the default case is worse than reported)

**Re-derived from `:54-59`:**
- At n = 4 the columns are 0: [0,1,2,3], 1: [1,0,3,2], 2: [2,3,0,1], 3: [3,2,1,0].
- X1 + X2 for U(0,1) inputs is [1,1,1,1], so sd = 0 and r = −1.
- The same exact pairs appear at n=6 (k=4), n=8 (k=6, pair (2,5)) and generally once k ≥ n/2 + 1 inputs; at n=8 a pair already appears at k=5.
- **New relative to E-02:** at the default n = 32 there is an *exact* r = −1 pair at k = 17, namely columns (15, 16): stride 31 ≡ −1 and stride 33 ≡ 1, with offsets summing to 31. E-02 reported only r ≈ −0.50 for (0, 16).
- With two inputs at the default n, r = +0.290.

**Guards:** there is no guard relating `sample_count` to the number of inputs. `:39-43` checks only 4 ≤ n ≤ 256 and a non-empty list, and `server.py:885-897` adds none.

**Counter-argument:** the output's `does_not_include: ["input correlation", ...]` (`:154-159`). It fails as a defence: that list disclaims *physical* correlation the caller did not model. The tool itself states `conditional_on: "declared independent input distributions"` (`:153`) while the design it built is deterministically dependent.

"Missing uncertainty never becomes zero" is directly violated: a "completed" interval of zero width is reported for a sum of two non-degenerate inputs at an accepted `sample_count`. MAJOR stands. MCP is scope.out, so no recertification is needed.

## E-03: unscrambled Halton starts are collinear in the high dimensions — CONFIRMED_REDUCED_SEVERITY, MINOR

**Re-derived** from `local_gaussian.py:113-119` and `:487-488` (affine per dimension), with N = 2p + 2 starts:

| p | Bases (last two dims) | Starts on one ray | Points in the half-plane u_b > u_a |
|---|---|---|---|
| 6 | (11, 13) | 10/14 | 2 |
| 8 | (17, 19) | 16/18 | 2 |
| 10 | (23, 29) | 22/22 | **0** |

At p = 10 one half-plane of the (u8, u9) projection is never sampled. Replacements continue the same sequence (`:1959-1968`), and `to_natural` is monotone per dimension, so the confinement survives both.

**Is a NO_SECOND_MODE claim evidence?** Yes, structurally. `_multistart_verdict` (`:400-434`) returns MULTISTART_NO_SECOND_MODE with no downgrade when the search is at the minimum and nothing was classified otherwise.

**Counter-arguments that lower the severity:**
- (i) The default `MultistartPolicy()` has 6 starts (`:455`), so every p ≥ 3 route is DOWNGRADED unless a caller explicitly passes 2p + 2 (`:378-383`). The router's canonical search is also the default (`router.py:817-819`).
- (ii) No `src` or `flagships` caller of `route_uncertainty` or `local_gaussian_posterior` exists outside `hybrid_uq` itself (`git grep`). Only `benchmarks/core_v2_hybrid_uq/**` uses it.
- (iii) Each start runs a full `calibrate` refit (`:1977`) that can leave the ray.
- (iv) A missed second mode needs a basin in the unsampled region that no refit drifts into. That is not demonstrated (PLAUSIBLE_UNPROVEN).

The geometry is a real weakness in a frozen V3 module, so the record overstates its search coverage. The false-support consequence is unproven and has no production consumer, so I grade it MINOR. A scrambled /2 scheme is still the right repair (OD-3 + freeze review).

## E-04 / D-08: absolute 0.05 holdout gate, holdout reused for ranking — CONFIRMED_REDUCED_SEVERITY, MINOR

**Re-derived** from `symbolic_regression.py:84-115`:
- Setup: 10 random N(0,1) features, 30 calibration and 15 holdout rows, all 175 subsets of 1 to 3 features, and a **pure-noise** target.
- Noise sd 0.01: 27 % of candidates are SURVIVED_HOLDOUT, and every one of 60 datasets has a survivor. Survivors sort first (`:136-146`), so the top-ranked candidate is always a noise "law".
- Noise sd 0.03: 28 %, and again 60/60 datasets.
- Noise sd 0.2: 0 %, and no dataset has a survivor.
- This matches D-08.
- Scale dependence is confirmed: the limit at `:19` is absolute, and `dataset.py:44,76-79` gives the target no unit and no scale. Dimensionless features (`:32`) do not normalize the target's magnitude.

**Counter-arguments that survive and lower the severity:**
- (i) `review_discovery_candidate` says only "survived holdout but lacks independent verification" (`campaign.py:68-76`).
- (ii) Inside a campaign, `HOLDOUT_SURVIVOR` additionally requires an explicit falsification record the candidate survived (`closed_loop.py:118-136`).
- (iii) The SRIA adapter (`sria/decision/discovery_adapter.py`, `generated_to_sria_hypothesis` docstring) forces every adapted candidate to PROPOSED. It says explicitly that a holdout scored inside the search is "not a sealed falsifier verdict". The holdout-reuse half is therefore already acknowledged in code.
- (iv) No production caller of `discover_sparse_equations` exists outside the package.

What remains new is the scale-dependent absolute limit with a zero improvement bar, which hands SURVIVED_HOLDOUT to noise. Hence MINOR. The file is certified (`current_core_v2.json:10866`).

## E-06: quad point location over-covers non-convex cells — CONFIRMED, MINOR

**Re-derived:**
- The quad (0,0), (2,0), (2,2), (1.5,0.5) has signed 2·area = +2 (CCW) and turns [1, 4, 1, −2], so it is reflex at vertex 3.
- For P = (1, 0.6), the code's split (0,1,2) ∪ (0,2,3) (`mapping.py:208-216`) says inside, a ray cast of the true polygon says outside, and the other diagonal split (0,1,3) ∪ (1,2,3) also says outside.
- On the path `_inside_unstructured` → `_support_coverage` → the REFUSE check (`:833-848`), nothing refuses non-convex quads. `_convex_cells` (`:410-446`) serves only the conservative path, and `numerical/mesh_quality.py:163-217` NON_CONVEX is not called here.

**Counter-argument:** a non-convex Q1 cell is an invalid mesh (it has a negative Jacobian corner). This lowers the likelihood but is not a guard. The module contract at `:19` ("any extrapolation [is] refused") and `extrapolated_count` are both wrong for such input. MINOR stands.

---

## Coverage notes
- **Read in full or at the cited ranges:**
  - `materials/properties.py`, `materials/ranges.py`, `materials/coverage.py`, `scientific/knowledge/snapshot.py`, `spatial/fields.py:180-216` and `pde/cases.py:1-100`.
  - `dc/validation.py:75-114,280-350`, `scientific/results/validation.py:1060-1169`, `credibility/evidence.py:800-880`, `credibility_vector.py:640-670,1020-1060` and `inference/admissibility.py:255-445`.
  - `conduction1d_schemes.py:236-305,361-421,495-660,791-926`.
  - `mcp/probabilistic_uq.py` (all), `mcp/server.py:885-925` and `tests/mcp/test_probabilistic_uq.py`.
  - `hybrid_uq/local_gaussian.py:90-120,320-510,1935-2004` and `router.py:800-835`.
  - `scientific/discovery/{symbolic_regression,dataset,campaign}.py`, `closed_loop.py:100-190` and `sria/decision/discovery_adapter.py`.
  - `execution/multiphysics/mapping.py:10-27,180-300,815-895`.
- **Not verified:** pint's exact offset-conversion arithmetic. I assumed `(v − 273.15)/1`, and 26.85 + 273.15 = 300.0 is consistent with that.
- **Not verified:** NumPy's `np.sin` versus `math.sin` at the last ulp in the B-04 emulation. That shifts where the window falls, not whether it exists.
