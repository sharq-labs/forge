# Reviewer E: Build vs Buy, hand-built algorithm correctness, compatibility

Target: `D:/forge-main-337519d1` at HEAD `abed661f`. This was a read-only audit. No FORGE code was imported or run.
Every numeric claim below comes from my own stdlib-only script,
`scratchpad/audit/reviewer_E_derivations.py`, run with `python -I -S`. Each such number is an INDEPENDENT
DERIVATION: the script restates the arithmetic at the cited lines. None of it is EXECUTED_REPRODUCED.

## Findings

---------------------------------------------------------------------------------------------------------------------
### E-01: The MCP "95 %" predictive interval holds only 0.95 − 0.95/n of the declared mass (0.920 at the default n = 32)

1. **ID:** E-01. **new_or_known:** NEW. O-4 (UQ computed in the MCP layer) is about layering. This finding is a wrong number.
2. **Category:** UQ interval estimator / false precision.
3. **Location:**
   - `src/engcore/mcp/probabilistic_uq.py:122,138-141` (`np.quantile(magnitudes, tail)` and `np.quantile(magnitudes, 1 - tail)`, default method).
   - The samples come from `:47` (`base_quantiles = (arange(n) + 0.5) / n`).
   - Reached through `src/engcore/mcp/server.py:885-918` (`answer_engineering_uncertainty`, default `sample_count=32`, `credible_mass=0.95`).
4. **Governing contract:**
   - The record carries `"credible_mass": mass` and the method name `deterministic_latin_hypercube_empirical_central_interval`.
   - The docstring says "Empirical central intervals".
   - `tests/mcp/test_probabilistic_uq.py:61-69` pins the type-7 arithmetic (301.5 / 304.5) and says nothing about coverage.
5. **Invariant violated:** the reported interval is narrower than the probability it states. CLAUDE.md: "Missing uncertainty never becomes zero". Here part of the uncertainty is silently dropped.
6. **Root cause:**
   - The inputs are placed at the stratum midpoints, which are the Hazen plotting positions (i + 0.5)/n.
   - The interval is then read with NumPy's default `linear` (type 7) quantile, which assumes positions i/(n − 1).
   - For an order-preserving output, the type-7 tail position p(n − 1) maps to input quantile p + (0.5 − p)/n. Both tails are therefore pulled inward by 0.475/n.
7. **Minimal trigger:** any `answer_engineering_uncertainty` call with one uncertain input and a QoI monotone in it, for example a linear response. It is worst at small `sample_count` (4 is accepted, `:40`).
8. **Expected vs observed:** expected mass 0.95. Observed:

   | n | Uniform input | Normal input |
   | --- | --- | --- |
   | 4 | 0.7125 | 0.7234 (interval ±1.088 sd) |
   | 8 | 0.8313 | 0.8447 |
   | 32 (default) | 0.9203 | 0.9255 (interval ±1.783 sd, not ±1.960) |
   | 256 | 0.9463 | 0.9464 |

   The uniform figures equal the closed form 0.95 − 0.95/n exactly (derivations §2).
9. **Reasoning:**
   - Sorted sample u_(i) = (i + 0.5)/n.
   - Type-7 quantile at p: index p(n − 1), so value = (p(n − 1) + 0.5)/n = p + (0.5 − p)/n.
   - Mass between the two tails = 1 − 2[0.025 + 0.475/n] = 0.95 − 0.95/n.
   - The same holds for any strictly monotone f, because the interval is computed on f's values at the same order statistics. For a linear f the interpolation is exact.
10. **Evidence class:** SOURCE_PROVEN (path `server.py:895-917` → `probabilistic_uq.py:122-141`, traced line by line), plus an independent derivation. The NumPy default is library behaviour I did not execute. The arithmetic of the pinned test (301.5 for 4 points at mass 0.5) confirms type 7.
11. **Affected:** the `answer_engineering_uncertainty` MCP tool (electrothermal and battery systems), every QoI interval in `engineering_probabilistic_uq/1`.
12. **False-support risk:** medium. The interval is decision support that a client compares against limits, and it understates spread by about 9 % in sd at n = 32. No verdict in `src` consumes it (`evaluate_context` uses the scenario envelope).
13. **Replay/provenance:** the stored intervals are reproducible and wrong. A fix moves every stored `lower`/`upper`.
14. **Compatibility:** output values change for the same schema. The `/1` schema label should bump or record the method.
15. **Certification:** `src/engcore/mcp/**` is certificate `scope.out` (`current_core_v2.json:12608`). No recertification is needed.
16. **Genesis impact:** none.
17. **Minimal reproduction (NOT executed):**
    - Call `predictive_intervals([... 32 answers whose QoI is the uniform input itself ...], credible_mass=0.95)` and compute `upper - lower` against 0.95.
    - Cost: under 1 s, no solver.
    - Expected: 0.9203.
    - Run it in a disposable worktree.
18. **Smallest correct repair:** read the interval with `method="hazen"` (positions (i + 0.5)/n, which match this design exactly), or `inverted_cdf` on the equal-mass atoms. Record the method string. Keep the pinned test, with values recomputed and a coverage assertion added.
19. **Owner approval:** yes. This is an output-semantics change on an MCP tool (no certificate change).
20. **Self-challenge:**
    - *Argument:* "Empirical interval of a deterministic sample" is just a convention.
    - *Answer:* it fails because the record states `credible_mass`, and the design is exactly stratified with known plotting positions. The estimator contradicts the design it was paired with, for every n, in the dangerous direction.

---------------------------------------------------------------------------------------------------------------------
### E-02: The "independent" stratified inputs are deterministically correlated, up to r = −1, giving zero-width intervals

1. **ID:** E-02. **new_or_known:** NEW. The root cause (lattice permutation) is distinct from O-4 and E-01.
2. **Category:** sampling design / dependence structure.
3. **Location:**
   - `src/engcore/mcp/probabilistic_uq.py:54-59`: `stride = 2*column + 1` (bumped to be coprime with n), `quantiles = base[(arange(n)*stride + column) % n]`.
4. **Governing contract:**
   - Docstring `:33`: "Deterministic stratified samples; never infer a dependence structure".
   - `dependence` must be `'independent'` (`:34-38`).
   - Output `"conditional_on": "declared independent input distributions"` (`:153`).
5. **Invariant violated:**
   - The declared independence is replaced by an undeclared, deterministic dependence.
   - "Missing uncertainty never becomes zero": a sum of two inputs can come out with sd exactly 0.
6. **Root cause:**
   - Each column is the rank-1 lattice permutation i ↦ s_c·i + c (mod n), so any two columns are related by an affine congruence.
   - When s_c ≡ −1 (mod n), the column is the reversed rank order of column 0 (for example column 3 at n = 4, stride 7 ≡ 3 ≡ −1).
   - When s_c ≡ ±1 for two columns, they are cyclic shifts of each other, or reversals.
   - Nothing checks or breaks this (no random pairing, no correlation control).
7. **Minimal trigger:** `sample_count=4` with three or more uncertain inputs (columns 1 and 2: r = −1.000). Also `sample_count=6` with four inputs, or 8 with six. At the default n = 32, any two inputs have r = +0.290 between columns 0 and 1, and r ≈ ±0.50 between column 0 and columns 15 and 16.
8. **Expected vs observed (derivations §1):**
   - Expected: sample correlation near 0 (random LHS gives |r| ~ 1/√(n − 1)).
   - Observed:

     | n | k | Worst pair | r |
     | --- | --- | --- | --- |
     | 4 | 3 | (1, 2) | −1.000 |
     | 4 | 4 | (0, 3) | −1.000 |
     | 6 | 4 | (2, 3) | −1.000 |
     | 8 | 6 | (2, 5) | −1.000 |
     | 32 | 2 | (0, 1) | +0.290 |
     | 32 | 17 | (0, 16) | −0.501 |

   - Y = X0 + X3 for two U(0, 1) inputs at n = 4: sample sd 0.0000 against the independent 0.408.
   - At n = 32, Y = X0 + X16: sd 0.293, which is 28 % understated.
9. **Reasoning:** the permutations are explicit integer maps. The correlations are exact sample statistics of those maps, independent of FORGE code beyond the cited lines.
10. **Evidence class:** SOURCE_PROVEN, plus an independent derivation.
11. **Affected:** the `answer_engineering_uncertainty` tool, for any QoI that depends on two or more uncertain inputs.
12. **False-support risk:**
    - High for small-n / many-input requests, where a zero or near-zero spread is reported with "completed" status.
    - Medium at the default n = 32 (±0.5 correlation for wide input sets; 0.29 always between the first two).
13. **Replay/provenance:** the samples are recorded per run, so the dependence is auditable after the fact. Nothing flags it.
14. **Compatibility:** the samples change on repair.
15. **Certification:** scope.out (MCP).
16. **Genesis impact:** none.
17. **Minimal reproduction (NOT executed):**
    - Call `build_deterministic_samples` with three U(0, 1) inputs, `sample_count=4`.
    - Parse the magnitudes and compute the correlation of inputs 2 and 3.
    - Expected: −1. Cost: under 1 s.
18. **Smallest correct repair:** a seeded random LHS pairing, or `scipy.stats.qmc.LatinHypercube(strength=1, optimization="random-cd")`, or a scrambled Sobol / Owen-scrambled design, with the seed recorded. In addition, refuse the request, or record a downgrade, when the max |r| between columns exceeds a declared bound.
19. **Owner approval:** yes (MCP output semantics).
20. **Self-challenge:**
    - *Argument:* any finite design has non-zero sample correlation.
    - *Answer:* the cases above are exact ±1 dependences produced deterministically by the construction, not sampling noise. The reported "conditional_on independent" statement is false for those designs. The argument survives only for the moderate-correlation cases, which are therefore graded medium rather than high.

---------------------------------------------------------------------------------------------------------------------
### E-03: The single-mode multistart is confined to a line in the high-index parameters (unscrambled, unskipped Halton)

1. **ID:** E-03. **new_or_known:** NEW. §8.5 lists the Halton "×2 duplicate" only as a consolidation item.
2. **Category:** global-search coverage / mode-uniqueness evidence.
3. **Location:**
   - `src/engcore/hybrid_uq/local_gaussian.py:98-119` (`_PRIMES`, `_prime`, `_radical_inverse`: no scrambling, no skip, base = d-th prime).
   - `:478-493` (`_point`, index 1..`starts`).
   - `:363-364` (`_minimum_starts = max(6, 2p + 2)`).
   - `:1959-1968` (replacements continue the same sequence).
4. **Governing contract:**
   - Module docstring `:17-19`: "no SUPPORTED claim assumes a single mode nobody looked past".
   - Audit HUQ-01 at `:328-332`.
   - `MultistartPolicy` docstring `:442`.
5. **Invariant violated:**
   - The "a single mode" diagnostic's evidence is weaker than its record says.
   - A `MULTISTART_NO_SECOND_MODE` claim at the canonical minimum search can rest on starts that never leave a 1-D ray of a parameter pair.
   - CLAUDE.md: "Removing evidence must not increase assurance". Here a degenerate search counts as a full one.
6. **Root cause:**
   - With N ≤ b_d, the radical inverse in base b_d is u_d(i) = i/b_d.
   - For two high dimensions whose bases both exceed N, every start satisfies u_b = (b_a/b_b)·u_a.
   - The minimum search (2p + 2 starts) is smaller than the p-th prime from p ≥ 5, so the last dimensions are collinear. This is the well-known small-N pathology of the unscrambled Halton sequence. SciPy's `qmc.Halton` scrambles by default for this reason.
7. **Minimal trigger:** p ≥ 6 parameters at the canonical policy (`starts=6` is raised to `2p + 2` only through the shortfall rule, which callers satisfy by passing 2p + 2).
8. **Expected vs observed (derivations §3).** Expected: starts spread over the box. Observed:

   | p | Starts | Starts on one ray in the last two dims | Off-diagonal quadrant starts | Worst pairwise \|r\| |
   | --- | --- | --- | --- | --- |
   | 6 | 14 | 10 (bases 11, 13) | 3 | — |
   | 8 | 18 | 16 | 3 | — |
   | 10 | 22 | 22 (u9 = (23/29)·u8) | 3 | 1.000 (dims 8, 9) |

9. **Reasoning:** for i < b, the radical inverse is the single digit i/b. So two dimensions with b_a, b_b > N lie on the ray through the origin with slope b_a/b_b. The interior map at `:488` is affine per dimension, so collinearity survives it.
10. **Evidence class:**
    - Start geometry: SOURCE_PROVEN (the code at `:113-119` and `:487-488`, re-derived).
    - Consequence (a missed second mode, then SUPPORTED): STATIC_SUSPICION. I did not construct a forward model and run the route.
11. **Affected:** every LOCAL_GAUSSIAN route with p ≥ 6 (`engcore.hybrid_uq`, Core Freeze V3 module), and the router's grid design, which seeds boxes from `_modes`.
12. **False-support risk:** medium. It needs a second mode off the explored ray that TRF does not drift to from the ray starts. In 2-D projections, the off-diagonal quadrants hold 3 starts at p = 6, 8 and 10.
13. **Replay/provenance:** the policy record (`multistart_*` keys) does not record the sequence quality, so a replayed record cannot reveal the confinement.
14. **Compatibility:** a scrambled or leaped sequence changes every multistart record. The policy `scheme` needs a new value (`"halton_in_inference_bounds"` is validated at `:466`).
15. **Certification:** `local_gaussian.py` is digest-pinned (`current_core_v2.json:11513`). This is the frozen V3 module, so the change is a recertification and a freeze-compatibility review (memory: Core Freeze V3).
16. **Genesis impact:** none directly.
17. **Minimal reproduction (NOT executed):**
    - Construct p = 6 with a separable forward whose χ² has a second, equal-depth basin at (u5, u6) ≈ (0.85, 0.15) and the estimate near (0.5, 0.5).
    - Run `local_gaussian_posterior(..., multistart=MultistartPolicy(starts=14))`.
    - Expected: uniqueness `MULTISTART_NO_SECOND_MODE` if no start reaches the basin.
    - Cost: seconds with an analytic forward. Run it in a disposable worktree.
18. **Smallest correct repair:**
    - Add a new scheme `"scrambled_halton_in_inference_bounds/2"`, seeded by the parameter-set digest, through `scipy.stats.qmc.Halton(scramble=True, seed=...)`, or an in-tree Owen/permutation scramble.
    - Or record the start set's minimum projected discrepancy, and downgrade (`MULTISTART_INCOMPLETE`) when two dimensions are collinear.
    - Keep the `/1` scheme readable.
19. **Owner approval:** yes. OD-3 recertification plus Core Freeze compatibility.
20. **Self-challenge:**
    - *Argument:* the multistart is only a heuristic, and local optimizers drift away from their starts.
    - *Answer:* the claim the record makes, a searched-for second mode not found at the declared minimum search, is a statement about coverage. At p = 10 the 22 starts span a set of codimension at least 1 by construction. The argument lowers the confidence in the consequence (STATIC_SUSPICION), not the geometric fact.
    - *Note:* `design/sampling.py:42-58,156-163` has the same unscrambled construction. There it only orders D2 candidates in a "search_record_not_validation" loop, so I rate it an OBSERVATION. Booleans in a dimension with base b ≥ 11 come out False for the first ⌈b/2⌉ − 1 indices, then True.

---------------------------------------------------------------------------------------------------------------------
### E-04: The sparse-discovery holdout gate is an absolute 0.05 on a unitless target, chosen against the same holdout

1. **ID:** E-04. **new_or_known:** NEW. It follows the memory pattern "Absolute tolerances hid failing checks", in a new location.
2. **Category:** model-selection criterion / holdout integrity / scale dependence.
3. **Location:**
   - `src/engcore/scientific/discovery/symbolic_regression.py:19` (`holdout_rmse_limit: float = 0.05`).
   - `:20` (`minimum_holdout_improvement = 0.0`).
   - `:84-115` (every candidate scored on the holdout and labelled SURVIVED / FAILED there).
   - `:136-146` (ranked on the same holdout).
   - `src/engcore/scientific/discovery/dataset.py:15-38,44,116-117`: features must be dimensionless (`:32`), but `target` is a bare float tuple with no unit or dimension check.
   - Consumer: `src/engcore/scientific/discovery/campaign.py:68-76` → `DiscoveryDecision.HOLDOUT_SURVIVOR`.
4. **Governing contract:** `campaign.py:56-60` says "candidate failed the reserved holdout set". The holdout is presented as reserved.
5. **Invariant violated:**
   - "Verification does not become validation". A holdout reused for selection over up to 2000 candidates is not a reserved test.
   - The survival decision moves under a restatement of the target's scale.
6. **Root cause:** the absolute RMSE threshold has no reference scale (no σ, no target spread). The holdout serves as both selection set and acceptance set. The improvement floor is 0.
7. **Minimal trigger:** a target expressed with magnitudes around 1e-3, for example a dimensionless group or a value in a large unit. Then baseline RMSE < 0.05, and every candidate with holdout_rmse ≤ baseline is SURVIVED_HOLDOUT. Conversely, with magnitudes around 1e3 nothing survives.
8. **Expected vs observed:**
   - Expected: survival invariant to target scale, and a holdout untouched by selection.
   - Observed: survival flips with scale, and the best-of-2000 holdout score is reported as the reserved-holdout result.
9. **Reasoning:**
   - RMSE scales linearly with the target, and the limit does not.
   - With m candidates, the minimum holdout RMSE is an optimistically biased order statistic, so with m in the hundreds a pure-noise feature set can pass.
10. **Evidence class:** SOURCE_PROVEN (scale dependence and holdout reuse, from `:84-115`). The magnitude of the optimism bias is not derived numerically (no numpy without site-packages).
11. **Affected:** `engcore.scientific.discovery` (`discover_sparse_equations`, `review_discovery_candidate`).
12. **False-support risk:** low-medium. HOLDOUT_SURVIVOR still says "lacks independent verification", and INDEPENDENTLY_REPRODUCED needs a bound VerificationRunRecord.
13. **Replay/provenance:** the candidate fingerprint embeds `candidate_id` with the enumeration counter (`:117`) and LAPACK-derived float coefficients, so the fingerprint is BLAS-sensitive across platforms (OBSERVATION).
14. **Compatibility:** changing the gate changes candidate statuses and fingerprints.
15. **Certification:** pinned (`current_core_v2.json:10866`).
16. **Genesis impact:** none (not the Genesis-lite arms).
17. **Minimal reproduction (NOT executed):** build the same dataset twice, target × 1 and target × 1e-3. Compare the number of SURVIVED_HOLDOUT candidates. Cost: under 1 s. Expected: 0 against all candidates.
18. **Smallest correct repair:**
    - Express the limit relative to a declared target σ or the calibration spread, and require a unit/dimension for the target.
    - Select on calibration CV only and keep the holdout for a single final check, as `benchmarks/genesis_lite/arms.py` already does (`_cv_mse` then `_gate`).
    - Record the multiplicity (`claims.multiplicity` exists).
19. **Owner approval:** yes (certified file).
20. **Self-challenge:**
    - *Argument:* this is a candidate generator, not authority.
    - *Answer:* the label it produces, SURVIVED_HOLDOUT, is an evidential statement that downstream review repeats ("survived reserved holdout"). The argument lowers severity to MINOR/MAJOR boundary. I keep MAJOR for the holdout-reuse plus scale combination and grade the false-support risk low-medium.

**Severity:** MAJOR (scientific-design). The owner may reasonably downgrade it to MINOR given the HOLDOUT_SURVIVOR wording.

---------------------------------------------------------------------------------------------------------------------
### E-05: Sparse discovery ranks a perfect-holdout survivor last (`holdout_rmse or inf`)

1. **ID:** E-05. **new_or_known:** NEW.
2. **Category:** ranking / falsy-zero bug.
3. **Location:** `src/engcore/scientific/discovery/symbolic_regression.py:142`: `(item.holdout_rmse or float("inf")) + penalty*complexity`.
4. **Governing contract:** the ranking order is "survivors first, then holdout RMSE plus complexity penalty". `candidate.py:31,66-72` allows `holdout_rmse` to be `None` or a float ≥ 0.
5. **Invariant violated:** the ranking is not monotone in the score. A better candidate sorts worse.
6. **Root cause:** `0.0 or inf` evaluates to `inf`. The `or` was meant for `None`.
7. **Minimal trigger:** a survivor whose holdout residuals are exactly 0.0, for example noise-free synthetic data whose law is in the feature set and exactly representable.
8. **Expected vs observed:** expected key 0.0001 (1 term). Observed key inf (derivations §4), so it is ranked after every other survivor.
9. **Reasoning:** Python truthiness. `1e-300` gives the correct key, and `0.0` does not.
10. **Evidence class:** SOURCE_PROVEN for the mapping. Reachability (an exactly-zero float RMSE from `lstsq`) is plausible but not demonstrated.
11. **Affected:** consumers of the order of `discover_sparse_equations` (tests; any caller taking `[0]` as best).
12. **False-support risk:** low (it penalises the correct law).
13. **Replay/provenance:** none.
14. **Compatibility:** ordering only.
15. **Certification:** pinned (`:10866`).
16. **Genesis impact:** none.
17. **Minimal reproduction (NOT executed):** construct `DiscoveredEquationCandidate`s with `holdout_rmse=0.0` and `0.01`, both SURVIVED, and sort with the same key. Expected: the 0.0 candidate last.
18. **Smallest correct repair:** `math.inf if item.holdout_rmse is None else item.holdout_rmse`.
19. **Owner approval:** yes (certified file; trivial).
20. **Self-challenge:**
    - *Argument:* exact 0.0 never happens in float least squares.
    - *Answer:* it is rare but possible, for example when target and feature are identical integer-valued vectors and the solution comes out exact. Severity stays MINOR because of the rarity.

**Severity:** MINOR.

---------------------------------------------------------------------------------------------------------------------
### E-06: Point location over-covers non-convex quadrilaterals, so extrapolation is not refused

1. **ID:** E-06. **new_or_known:** NEW. DEFERRED_VALIDATION.md:220 and PROGRESS.md:5577 mention non-convex cells only for the *conservative* remap, which refuses them (`mapping.py:440-446`).
2. **Category:** geometry precision / support coverage.
3. **Location:**
   - `src/engcore/execution/multiphysics/mapping.py:208-216`: a quad is tested as triangles (0, 1, 2) ∪ (0, 2, 3).
   - Used by `_inside_unstructured` `:225-263`, which feeds `_support_coverage` `:286-300`, which feeds the extrapolation refusal `:833-848` and `extrapolated_count` `:949`.
   - The mesh record does no convexity check: `src/engcore/scientific/fields/unstructured.py:61-122` checks counts and units only.
4. **Governing contract:**
   - Module docstring `mapping.py:19`: "any extrapolation [is] refused".
   - `ExtrapolationPolicy.REFUSE`.
5. **Invariant violated:** target sites outside the source support are counted as covered, so the REFUSE policy does not refuse and `coverage_fraction` reads 1.0.
6. **Root cause:**
   - The diagonal split is valid only for convex quads.
   - With a reflex vertex at 1 or 3, the triangle (0, 1, 2) or (0, 2, 3) covers the notch outside the cell.
7. **Minimal trigger:**
   - A source QUADRILATERAL cell 0 = (0, 0), 1 = (2, 0), 2 = (2, 2), 3 = (1.5, 0.5). It is CCW, signed area +1, and reflex at vertex 3 (turn cross product −2).
   - A target site at (1.0, 0.6), which lies in the notch, outside the cell.
   - NEAREST mapping with REFUSE, the notch on the mesh boundary.
8. **Expected vs observed:**
   - Expected: the site is outside, so the mapping raises.
   - Observed: `_triangle_contains((1, 0.6), (0, 1, 2))` is True (u, v ≥ 0, u + v ≤ 1), so the site is "inside" and a nearest-site value is admitted.
9. **Reasoning:** barycentric test against the triangle (0, 0), (2, 0), (2, 2). The point (1, 0.6) satisfies 0 ≤ y ≤ x ≤ 2. The true cell is (0, 1, 2) minus (0, 2, 3), and the point lies inside (0, 2, 3), between y = x/3 and y = x.
10. **Evidence class:** SOURCE_PROVEN geometry. The reachability of a non-convex quad source mesh is STATIC_SUSPICION: `mesh_quality.py` flags NON_CONVEX, but I found no call on this path.
11. **Affected:** NEAREST and site-based mappings from unstructured quadrilateral supports (2-D). The 5-tet hex split `:191-197` has the analogous issue for warped hexes (hypothesis, below).
12. **False-support risk:** low (it needs a malformed mesh at a boundary). The mapped value carries no error bound anyway (`:959`).
13. **Replay/provenance:** `extrapolated_count` in the stored diagnostics is understated.
14. **Compatibility:** none for convex meshes.
15. **Certification:** pinned (`current_core_v2.json:11090,11943`).
16. **Genesis impact:** none.
17. **Minimal reproduction (NOT executed):** one-cell quad mesh as above, a target `StructuredMesh` or point site at (1, 0.6), `FieldMapper.execute` with NEAREST and REFUSE. Expected: no exception. Cost: under 1 s.
18. **Smallest correct repair:** refuse non-strictly-convex quads in `_inside_unstructured`, using the same turn test as `_convex_cells`, or test the quad by both diagonal splits' intersection.
19. **Owner approval:** yes (certified file).
20. **Self-challenge:**
    - *Argument:* non-convex quads are invalid meshes and should never reach here.
    - *Answer:* nothing on this path refuses them, and the conservative path in the same module does refuse them. It survives as MINOR.

**Severity:** MINOR.

---------------------------------------------------------------------------------------------------------------------
### E-07: Genesis-lite `_fit` residual sd uses ddof = 0 with p + 1 fitted parameters (factor 0.577 at budget 12)

1. **ID:** E-07. **new_or_known:** variant_of the known "ddof=0" Genesis gate item, which the brief and §8.5 attach to `_replicate_noise`. What is new: the *fit residual* `resid` at `benchmarks/genesis_lite/arms.py:92` (`np.std(y - X @ coef)`) also drops the p + 1 fitted degrees of freedom. `resid` drives three gate terms:
   - `se = resid*sqrt((p+1)/n)` (precision bar, `:147`);
   - the lack-of-fit term `resid <= 3.5*scale` (`:150`);
   - the noise fallback `scale = resid` when no replicate noise exists (`:148`).
2. **Category:** baseline gate calibration.
3. **Location:** `benchmarks/genesis_lite/arms.py:85-92,147-150` (prereg-pinned harness).
4. **Governing contract:** Genesis §10.5 (strongest applicable baseline; straw-man baseline = INVALID_BENCHMARK).
5. **Invariant violated:** the baseline's precision bar and lack-of-fit bar are miscalibrated, with a size that depends on budget.
6. **Root cause:** a biased residual sd: E[resid²] = σ²(n − p − 1)/n.
7. **Minimal trigger:** budget 12, three names: train = 6 rows, 4 fitted parameters, 2 residual dof.
8. **Expected vs observed:** the sd factor √((n − p − 1)/n) is 0.577 at budget 12 / 3 names, 0.707 at 12 / 2, 0.858 at 30 / 4, and 0.926 at 60 / 5 (derivations §6).
9. **Reasoning:** the standard OLS residual-variance bias.
10. **Evidence class:** SOURCE_PROVEN (arithmetic). The effect on arm credit is not measured.
11. **Affected:** every gated Genesis-lite arm (`monomial_enumeration`, `random_structures`, `greedy_forward`, `space_filling`, `extrapolating_fit`, `fit_all_gated`, `extrapolation_pair`).
12. **False-support risk:** low. It makes the arms *more* willing to propose a law, which can raise or lower their credit. It is a benchmark-calibration issue, not production.
13. **Replay/provenance:** none.
14. **Compatibility:** any change is a new benchmark identity (v0.3).
15. **Certification:** `benchmarks/**` is scope.out but prereg-pinned.
16. **Genesis impact:** Genesis-lite Step-1. Fold it into the AUDIT of gate constants before OD-19.
17. **Minimal reproduction (NOT executed):** synthetic log-linear data with known σ, 6 training rows, 4 parameters. Compare `resid` with σ over 10⁴ draws. Expected mean ratio ≈ 0.54–0.58.
18. **Smallest correct repair:** `np.sqrt(np.sum(r**2)/(n-p-1))`, together with the ddof fix in `_replicate_noise` (mean-zero pairs: `sqrt(sum(d^2)/(2m))`), in the v0.3 amendment.
19. **Owner approval:** yes (BVB-1 / OD-19).
20. **Self-challenge:** it is the same family as the known ddof item, so I report it as a variant, not a new finding. It survives as a variant only.

**Severity:** MINOR.

---------------------------------------------------------------------------------------------------------------------
### E-08 (OBSERVATION): Blindfold structure-digest exponent rounding is not a metric equivalence

1. **ID:** E-08. **new_or_known:** NEW as a consequence. §8.5 already notes that the docstring disclaims equivalence.
2. **Category:** canonical identity.
3. **Location:**
   - `src/engcore/blindfold/expression.py:174-175` (`round(k, 3)`, then drop zero).
   - Consumers: `escrow.py:559-562` (`structure_matches_hidden_law`), `roles.py:227`, and `sria/decision/hypotheses.py:385-386` (the claim digest drops `statement_payload` when a structure digest exists).
4. **Contract:** "canonicalization, not a proof of equivalence" (`:20-22`).
5. **Effect:**
   - k = 1.23449 and k = 1.23451 get different digests, while 1.23451 and 1.2354 get the same one (derivations §5).
   - k = 0.0004 rounds to 0 and the factor vanishes: x^0.0004 has the same structure as a constant, and x^1.0004 the same as x.
   - Two hypotheses differing by such a factor share a `claim_digest`, so "a refutation of one is a refutation of the other".
6. **Root cause:** decimal rounding as an identity; the bucket edges are arbitrary.
7. **Trigger:** proposer exponents within 5e-4 of a rounding edge, or |k| < 5e-4.
8. **Expected vs observed:** see 5.
9. **Reasoning:** as derived in §5.
10. **Evidence class:** SOURCE_PROVEN (rounding). The consequence is conservative in the falsification and novelty uses (the shared identity only *removes* support or novelty). `structure_match` feeds no credit (`roles.py:226-227` requires `passed`) and is not read by `benchmarks/genesis_lite` (grep).
11. **Affected:** see location.
12. **False-support risk:** none to low.
13–14. **Replay and compatibility:** any change moves `blindfold.structure` digests (prereg and certificate pinned).
15. **Certification:** pinned (`:11603`).
16. **Genesis impact:** none unless structure recovery becomes a scored metric.
17. **Minimal reproduction:** `structure_digest(pw(v('x'), 1.23449)) != structure_digest(pw(v('x'), 1.23451))`.
18. **Repair:** keep it, document the bucket edges, and use exact `Fraction` exponents or a tolerance-graph equivalence if structure ever becomes scored.
19. **Owner approval:** no (documentation).
20. **Self-challenge:** by design this is not an equivalence. Recorded so the lead does not mistake it for a metric.

---------------------------------------------------------------------------------------------------------------------
### E-09 (OBSERVATION): `evaluate_failure` silently truncates mismatched inputs

1. **ID:** E-09. **new_or_known:** NEW.
2. **Category:** metric robustness.
3. **Location:** `src/engcore/sria/calibration/failure_model.py:249-262`. `zip(probabilities, actuals)` has no length check, and the sums are divided by `len(actuals)`. Probabilities outside [0, 1] are dropped from the reliability table and not refused.
4. **Contract:** the docstring "Brier score, log loss and a reliability table".
5. **Effect:** a shorter probability list lowers both Brier and log-loss, so the model looks better.
6. **Root cause:** a missing length and range check.
7. **Trigger:** the caller passes fewer probabilities than records.
8. **Expected vs observed:** expected refusal, observed a smaller score.
9. **Reasoning:** the sums cover fewer pairs than the divisor counts.
10. **Evidence class:** SOURCE_PROVEN. The only callers I found are in tests (`tests/test_sria_m2b_calibration.py:414-417`).
11–16. **Impact:** low. Certified (pinned twice). No Genesis impact.
17. **Minimal reproduction:** `evaluate_failure("x", [1.0], [rec_success, rec_success])` gives Brier 0.0 against an expected refusal.
18. **Repair:** `if len(probabilities) != len(actuals) or any(not 0 <= p <= 1 ...): raise`.
19. **Owner approval:** yes (certified, trivial).
20. **Self-challenge:** no production caller, hence an OBSERVATION.

---------------------------------------------------------------------------------------------------------------------

## (a) Hypotheses I could not confirm

- **Pearson three-moment tail accuracy** (`local_gaussian.py:239-251`). The moment match is exact (re-derived below), but its error at the gate's α/2 = 0.005 tail for heavily unequal leverage weights is not quantified. That needs Imhof/Davies or a Monte Carlo with numpy. §8.5 DEFER of an oracle stands.
- **Hex point location by a fixed 5-tet split** (`mapping.py:191-222`). For a non-planar (trilinear) hex, the split depends on the diagonal choice and differs from the trilinear cell. Not traced to a reachable admission.
- **Normal inputs at stratum midpoints** (`probabilistic_uq.py:77`). The sample sd of ndtri((i + 0.5)/n) is below 1, so `standard_uncertainty` is slightly understated, by a smaller amount than E-01. Not quantified.
- **`studies/tcr.py:252` `default_rng(seed).normal`.** NumPy's NEP 19 does not guarantee Generator *distribution* streams across NumPy versions. If coverage-study outputs are pinned in committed JSON, a NumPy bump may move them. Not checked against the pinned files. This is related to the known "no frozen environment manifest".
- **Unbalanced ICC** (`calibration_study.py:819-829`) uses the mean group size m̄ where the ANOVA estimator uses m₀ = (N − Σmᵢ²/N)/(k − 1). It is exact for balanced repetitions (the production study is balanced). Not confirmed to matter.
- **Grid-resolution check on non-uniform axes** (`calibration.py:694-696`) uses the *largest* step per axis. I believe it is conservative (it lowers the aliasing number), but did not prove it for strongly graded axes.

## (b) Inspected and found sound (with the reason)

- **Leverage null cumulants** (`local_gaussian.py:159-213`). I re-derived c1, c2 and c3 for M = (I − H)D(I − H) by expanding tr((D − HD)^k) cyclically. tr(HD²) = Σhd², tr(HDHD) = tr(G²), and the three cross terms of c3 are each tr(G·G2). The Pearson parameters b = c3/c2, ν = c2³/c3² and a = c1 − bν match the mean, variance (2c2) and third cumulant (8c3) exactly. The round-off clamp is a derived floor.
- **Fincke–Pohst** (`calibration.py:755-804`). With q = UᵀU and U upper-triangular, the level-i term is (U_ii(n_i − c_i))² with c_i = −Σ_{j>i} U_ij n_j / U_ii. Enumeration from the top level is correct, the zero vector is excluded, and the bound shrinks monotonically. The aliasing number (2π)²nᵀSn equals kᵀΣk with k = 2πn/h in lattice units.
- **Lattice Hessian fit** (`calibration.py:699-752`). The coefficient mapping (diagonal 2·c, off-diagonal c) and P = −½(H + Hᵀ) are correct. Flat or convex directions are floored, which is the documented intent.
- **Weighted quantiles** (`grid.py:639-649`, `uq/predictive.py:226-241`). `searchsorted(cum, t, 'left')` is the inverted-CDF quantile, the same as NumPy `method="inverted_cdf"`. Clamping to n − 1 handles a cumulative sum short of 1.
- **Mixture-CDF bisection** (`uq/predictive.py:254-280`). The bracket [min − 12σ, max + 12σ] contains every tail ≥ ndtr(−12) ≈ 1.8e-33. The CDF is monotone, and 96 halvings reach below ulp.
- **Log-sum-exp** (`grid.py:709-721`). The max pivot over finite entries is correct, and inadmissible entries are set to −inf before the pivot.
- **Wilson** (`calibration_study.py:870-894`). Matches the standard score interval.
- **Refusal-fraction bound** (`:853-863`). |Δcoverage| ≤ f is correct for equal intervals per repetition.
- **Richardson/GCI** (`claims/numerical_uq.py:187-235`). Order = log(e₂/e₁)/log r, error = (f₂ − f₁)/(r^p − 1), extrapolate f₁ − error, and Fs = 1.25. min(p_obs, p_formal) is conservative. Oscillatory, diverging and round-off sequences give UNKNOWN.
- **Splitting estimate** (`execution/multiphysics/splitting.py:101-137`). Base-window error |d₁|·2^p/(2^p − 1) and order log₂(d₁/d₂) are correct for windows halving each level.
- **FD Jacobian step halving** (`hybrid_uq/sensitivity.py:99-186`). The Richardson error factors 4/3 (central) and 2 (one-sided) are correct. One-sided steps stay inside the bounds. Roundoff and resolvability refusals are present. The coarse estimate is accepted with a valid error estimate.
- **Curvature matrix and invariant basis** (`local_gaussian.py:1338-1468`). M_ij = (Q̄₊ − Q̄₋)/(2s²) is correct. The δ_k are cov-orthonormal (δᵢᵀΣ⁻¹δⱼ = δᵢⱼ), so the probe set is unit-invariant.
- **Laplace mass ratio** (`:1698-1724`). exp(−Δχ²/2)·sqrt(det I_min / det I_r) is correct, and an overflow is recorded as unavailable (fail-closed).
- **`isolate_symbol` and `canonicalize`** (`scientific/equations/transformations.py`). Each inverse step records the needed NONZERO side condition (the DIVIDE-by-target case records both). Commutative sorting applies only to ADD and MULTIPLY on scalars, and SUBTRACT forms are not merged, so there are only false negatives and no false equivalences. (The inventory's "mini-CAS over Fraction exponents" description is inaccurate: exponents are Fractions in `ast.py:144-187`, but `transformations.py` does no exponent algebra.)
- **Sutherland–Hodgman clip** (`mapping.py:451-471`) for CCW convex polygons, in a local frame. **Tet–tet overlap** (`:534-564`): the vertex set (vertices of each inside the other, plus edge–facet intersections of both) is complete for convex polytopes, and Qhull failure returns 0, which is then refused through the coverage deficit (fail-closed).
- **Interval overlap** (`mapping.py:374-393`, `numerical/interval_transfer.py:246-279`). Correct, with independent re-admission of coverage and totals.
- **`_dimensionless_groups`** (`blindfold/universe.py:171-190`). With `want=2`, "different support" implies linear independence, because two dependent vectors are proportional and so share support. It is a generator, not a π-theorem completeness claim, so its incompleteness is not a defect.
- **`random.Random(str)` seeding** across the blindfold, escrow and arms code is deterministic across CPython ≥ 3.2 (SHA-512 seeding). Seeds are per purpose (they include the kind, the universe or the observation sequence number). `eval_rng` omits the kind, but universe seeds are unique per index (`escrow.py:357`).
- **Grid spot-check RNG** (`router.py:533`, `_grid_evidence.py:136`). It is fresh per call, nonce-replayable, and enters no record (documented).
- **Design-effect ICC** (`calibration_study.py:783-830`). The one-way ANOVA estimator is clamped at ≥ 0 (fail-closed).

## Build-vs-buy table (my classification; all PROPOSED)

| Item | Decision | Separate axes |
| --- | --- | --- |
| `mcp/probabilistic_uq.py` LHS + quantile (E-01, E-02) | **REPLACE** with `scipy.stats.qmc.LatinHypercube` (seeded, `optimization="random-cd"`) + `np.quantile(method="hazen")` | Correctness: **yes** (two proven defects). Performance: none. Maintenance: removes the hand lattice. Independent baseline: n/a. SciPy is already a core dependency, MCP is scope.out, so no recertification. |
| `hybrid_uq` multistart Halton (E-03) | **WRAP** as a new scheme `/2` via `qmc.Halton(scramble=True, seed=digest)`; keep `/1` readable | Correctness: yes (search coverage). Certification: V3 freeze review + OD-3. Differential oracle: compare projected discrepancy of `/1` vs `/2` starts. |
| `design/sampling.py` Halton | **KEEP** now; consolidate with the above in the same batch | Maintenance only (candidate order, not evidence). |
| Pearson 3-moment null | **KEEP** + **AUDIT** oracle (Imhof/Davies, test-only) | Correctness unquantified in the far tail; frozen. |
| Fincke–Pohst, lattice Hessian, weighted quantile, mixture bisection, log-sum-exp, Wilson, GCI ×2, FD halving | **KEEP**; test-only oracles (`np.quantile(inverted_cdf)`, `scipy.special.logsumexp`, `brentq`, `binomtest().proportion_ci`, `scipy.differentiate`) | Correctness: sound by derivation. Oracles add independent evidence at no identity cost. Consolidating duplicates is maintenance (OD-3 batch). |
| `scientific/discovery/symbolic_regression.py` (E-04, E-05) | **KEEP** the algorithm; **REPAIR** gate and sort key; existing PySINDy **WRAP** stays DEFER | Correctness: yes (gate scale, holdout reuse, sort key). Discovery capability expansion: PySR/PySINDy, not needed to fix the defects. |
| `blindfold/expression.py` structure digest (E-08) | **KEEP**; SymPy test-only oracle | Identity semantics; prereg + certificate pinned. |
| `blindfold/universe.py` π-groups | **KEEP**; `pint.pi_theorem` test-only oracle optional | Sound for its generator role. |
| `mapping.py` point location (E-06) | **KEEP** + convexity refusal | Shapely or scipy.spatial would not add the issuance binding; the defect is a missing precondition, not the algorithm. |
| Conservative remap (clip, tet overlap, interval overlap) | **KEEP** | Sound; preCICE/ESMF would be a differential baseline only. |
| `sria/calibration/failure_model.py` (E-09) | **KEEP** + input checks; `sklearn.metrics` test-only oracle | sklearn is deliberately unimported in src (guard). |
| `uq/budget/coverage.py`, `claims/multiplicity.py` | **AUDIT** (already O-2 / O-3) | Not re-reported. |
| `claims/analysis/sensitivity.py` OAT | **DEFER** (SALib = capability expansion) | Sound as declared. Note that ±relative steps in an offset unit (°C) make the robustness envelope unit-dependent; the record states units, so this is an OBSERVATION. |
| Genesis-lite `_fit` / `_replicate_noise` / `_gate` (E-07) | **AUDIT**, then calibrated variant in v0.3 | Independent baseline strength; new identity. |
| Genesis-lite `_design_lhs` | **KEEP** (correct random-pairing LHS); optional `qmc` variant arm | Independent-baseline question, not correctness. |
