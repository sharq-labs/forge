# Core Gap Review 2 — Thin-Ridge Posterior Resolution

Branch `claude/core-gap-thin-ridge-review` · baseline `bbe5d4a` · **read-only**: no file under `src/` changed; no manifest or certificate touched

```
python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py phase1
python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py family
python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py parameterization
python -X utf8 benchmarks/core_gap_thin_ridge/audit/k2_grid.py --workers 12 --out <scratch>/k2_grid.npz   # ~29 min
python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py regression
python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py regression_k2 --k2 <scratch>/k2_grid.npz
python -X utf8 benchmarks/core_gap_thin_ridge/audit/tcr_truth.py
python -X utf8 benchmarks/core_gap_thin_ridge/audit/predictive_impact.py --k2 <scratch>/k2_grid.npz
python -X utf8 -m pytest benchmarks/core_gap_thin_ridge/tests -q          # 11 tests
```

**What every grid result is.**

- **Source:** the frozen `gaussian_grid_posterior`, `assess_identifiability` and `posterior_grid_diagnostics`.
- **Synthetic targets:** embedded as admitted linear observations (y = L⁻¹θ, unit σ), so the frozen likelihood *is* the target Gaussian.

**Materiality rule.**

- **Declared before any run:** grid mean error > 0.1 true sd, or grid/true sd outside [0.9, 1.1], on the **marginals**.
- **Added after Phase 4, labelled `post_hoc_thin` everywhere:** the same test applied to the sd and mean along the **true thin principal direction**. Phase 4 showed a grid can get every marginal right and still collapse the best-determined combination onto one node.

## 1. FINAL VERDICT

**THIN-RIDGE BLIND SPOT CONFIRMED — V1 REPAIR REQUIRED**

**The frozen guard violates its documented contract.** `GridResolutionError`'s docstring says the refusal exists because an unresolved grid produces "FALSE PRECISION, in the direction that looks like certainty." On thin rotated ridges it produces exactly that, silently.

**The damage reaches evidence that is already committed:**

- **K2, the frozen scored kinetics experiment,** reproduced exactly. It carries a **6× understatement of epistemic predictive sd** for its C2 observables, and a covariance determinant about **56× too small**. The guard accepted a posterior with **ESS 1.42**.
- **The TCR narrow-span test design** has its thin direction at **0.68×** truth.

**Why repair in V1, before V2:**

- **V2 would rely on this route:** the planned router keeps the grid as the trusted route for weak and bounded problems, the exact regime where this fails.
- **No frozen contract has to change:** the repair touches no frozen API, serialization, identity or freeze-contract fact.
- **What it does need:** a trust-semantics compatibility review and a certificate reissue, because `inference/**` is certified scope.

## 2. REPRODUCTION RESULT

`PHASE1_REPRODUCTION.json`.

**Setup:**

- **Case:** the exact HD-UQ case F5, with the committed observations reused byte for byte.
- **Model:** y = t₁ + t₂x, x ∈ linspace(10, 10.05, 6), σ = 0.01.
- **Prior:** flat on [−50, 50] × [−5, 5].
- **Parameter count:** p = 2.

| quantity | value |
|---|---|
| true covariance | [[5.7429, −0.57286], [−0.57286, 0.057143]] |
| correlation | **−0.9999985** |
| principal-axis widths (sd) | **4.05 × 10⁻⁴** and **2.408** (condition 3.5 × 10⁷) |
| thin direction | (−0.0993, −0.9951) |
| conditional sd of t₁ given t₂ | 0.00408 |
| marginal sd | 2.396, 0.2390 |
| grid spacing (declared-bounds window) | 0.5 / 0.25 / 0.125 in t₁ and 0.05 / 0.025 / 0.0125 in t₂, at 201 / 401 / 801 per axis |

**`GRID_STABLE_BUT_WRONG` occurs,** proved by the artifact rather than inferred. At all three resolutions, the declared-bounds grid is:

- **accepted** by the frozen guard;
- **bit-stable:** identical moments;
- **materially wrong.**

## 3. TRUSTED REFERENCE

**Mean (3.05527, 0.095442); sd (2.39644, 0.239046).**

It was computed two independent ways, which agree to 1 × 10⁻¹⁴:

- the analytic linear-Gaussian posterior (box probability mass 1.0);
- dense 2001 × 2001 quadrature in **principal-axis** coordinates, truncated to the box.

## 4. GRID RESULT

| grid | mean | sd | ESS | spacing / marginal sd |
|---|---|---|---|---|
| declared bounds, 201² | (0.403, 0.360) | (1.348, 0.1348) | 9.6 | 0.371 |
| declared bounds, 401² | identical | identical | 19.1 | 0.185 |
| declared bounds, 801² | identical | identical | 38.2 | 0.093 |
| same, offset half a step on **both** axes | identical | identical | — | — |
| ±6 marginal sd, 201–801² | (3.055, 0.0954) | (2.396, 0.2390) | 59–236 | 0.015–0.06 |

## 5. MATERIAL ERROR

**On the declared-bounds grids:**

- **mean:** off by **1.11 true sd**;
- **sd:** **0.563×** truth on both marginals, which is false precision;
- **thin direction:** sd **0.83×**, mean off by **0.75 thin sd**.

**Predictive effect.** For y at the centre of the data (the best-determined combination), the frozen `posterior_predictive_uq` returns epistemic sd:

- **0.83×** truth on the bounds grid;
- **0.00085×** truth on the ±6 sd grid, whose marginals are *correct*. That is 1,000× false precision on a grid that passes every marginal check.

## 6. CURRENT GUARD RESULT

**ACCEPT at every resolution, and in every parameterization.**

- **Reported status:** `PARAMETERS_NOT_IDENTIFIABLE`.
- **Refusal:** no `GridResolutionError`.
- **Why it passes its own test:** it refuses only when ESS < 8 **and** max spacing/marginal-sd ≥ 1. Here ESS ≥ 9.6 and spacing ≤ 0.37.

## 7. WHY THE CURRENT GUARD MISSES IT

`posterior_grid_diagnostics` (`src/engcore/inference/calibration.py`) compares each **axis** step hᵢ with that axis's **marginal** sd, √Σᵢᵢ.

**The lattice-sum identity.** By Poisson summation, a lattice sum of a Gaussian equals its integral plus one aliasing term per non-zero reciprocal-lattice vector k = 2π n / h (n ∈ ℤᵖ). Each term's amplitude is **exp(−kᵀΣk / 2)**.

- **What the current test covers:** only k along a coordinate axis, where kᵀΣk = (2π σᵢ / hᵢ)². spacing/sd < 1 means ≥ 39.5 there.
- **What it misses:** an off-axis n whose k points along the **thin** eigenvector. Then kᵀΣk ≈ λ_min |k|², which can be ≪ 1 while every marginal is wide.

**On F5:**

- the ridge slope is dt₁/dt₂ = −10.025;
- one t₂ step moves the ridge by 1.0025 t₁ steps at **every** nested refinement;
- so n = (1, 1) gives kᵀΣk = **0.132**, an aliasing amplitude of 0.94.

**Why it is resolution-stable:** halving both steps preserves that ratio, so the sampled phase pattern repeats. A diagonal half-step offset preserves it too.

**How far refinement is from helping.** The minimizing vector is n = ±(1, 1) at every resolution, and A only quadruples per halving:

| points per axis | A |
|---|---|
| 201 | 0.0083 |
| 401 | 0.033 |
| 801 | 0.132 |

Extrapolating, A would first exceed the declared threshold at roughly **13,000 points per axis**.

**The missing quantity** is not correlation or condition number by itself. It is the **minimum over reciprocal-lattice vectors of kᵀΣk**, which combines:

- the covariance eigenvalues;
- the principal-axis widths;
- the ridge **orientation relative to the lattice**;
- the step sizes.

**A second defect in the same guard.** The "ESS < 8 **and** spacing ≥ 1" conjunction accepts K2's ESS of 1.42. The guard's comment justifies small ESS as "sharply informative and correctly sized", but that reasoning is marginal. The lattice has only ~1.3 nodes inside the posterior's *joint* volume, because |Σ|^½ is tiny.

## 8. CORRELATION THRESHOLD WHERE FAILURE APPEARS

`PHASE3_FAMILY.json`, correlation family. Equal marginals; windows ±6 and ±20 sd; 11–161 points per axis; 4 lattice phases each; 40 cases per ρ.

| ρ | guard false accepts, declared (marginal) rule | guard false accepts, post-hoc thin rule |
|---|---|---|
| 0, 0.5 | 0 | 0 |
| 0.9 | 0 | 1 |
| 0.99 | 0 | **8** |
| 0.999 | **1** | **20** |
| 0.9999 | **3** | **24** |

**Reading the table:**

- **Marginal errors** appear from ρ ≈ 0.999.
- **Thin-direction errors** appear from ρ ≈ 0.9 on coarse grids and become common from ρ ≈ 0.99.

**ρ alone does not decide.** Axis-aligned thin ridges never fail (§9), which is why the aliasing number, not ρ, is the separating quantity.

## 9. RIDGE WIDTH THRESHOLD

**Rotation family** (principal widths 1 and w; 0–90°; 21 and 81 points per axis; 3 phases):

| thin width w | 0° and 90° (axis-aligned) | 10°–80° (oblique) |
|---|---|---|
| 1 | correct | correct |
| 0.1 | correct | 6 / 24 false accept (thin rule), at 30°–45° |
| 0.01 | correct | **24 / 24** false accept (thin rule) |
| 0.001 | correct | **24 / 24** false accept (thin rule) |

**Width relative to step does not separate on its own.**

- False accepts occur for thin-sd / step ≤ **0.38** (thin rule) and ≤ 0.096 (marginal rule).
- Correct accepts exist down to **0.0024**, on axis-aligned ridges.

**The true-Σ aliasing number separates cleanly** under the thin rule: every false accept has **A ≤ 7.9**, and every correct accept has **A ≥ 7.9**.

## 10. PARAMETERIZATION SENSITIVITY

`PHASE4_PARAMETERIZATION.json`. The same physical F5 posterior and prior box, 801 points per axis over the box's bounding window in each coordinate system.

| coordinates | guard | marginals (declared) | thin direction (post hoc) | D |
|---|---|---|---|---|
| original (t₁, t₂) | ACCEPT | **wrong** (1.11 sd, 0.56×) | wrong (0.83×) | **0.132, refuse** |
| principal-axis rotated | ACCEPT (thin-axis spacing/sd = ∞, ESS 68) | right | **collapsed (0.0×)** | **0.0105, refuse** |
| whitened | ACCEPT (same) | right | **collapsed** | **0.0105, refuse** |
| t₂ × 100 | ACCEPT | wrong (identical to original) | wrong | **0.132, refuse** |

**What changes with parameterization:**

- **Which quantities are wrong changes; the guard's verdict does not.** It accepts all four.
- **Per-axis rescaling:** leaves the guard and D unchanged. D is exactly invariant under per-axis rescaling, because n/h scales by 1/c and Σ by c².
- **Rotation:** turns marginal errors into thin-direction collapse.

**Scaling family** (same Gaussian, t₂ scaled by c, one fixed common window):

- At **c = 1**, 41 points per axis: guard **ACCEPT**, a false accept under the thin rule.
- At **c = 10**: guard **REFUSE**.

The guard's verdict flips **solely because of scaling**. D is 0.877 in both.

## 11. BEST CANDIDATE DIAGNOSTIC

**D — the lattice aliasing number,** A = min over n ∈ ℤᵖ \ {0} of (2π)² (n/h)ᵀ Σ_H (n/h).

**Where Σ_H comes from:** a least-squares quadratic fit to the grid's **own** `log_likelihood` values. The window is progressive, 50 → 500 → 5000 → all log-units, stopping at the first full-rank design.

**What D needs:**

- **Data:** only what `PosteriorGrid` already stores.
- **Forward evaluations:** none.
- **New Core primitive:** none, just a computation.
- **Cost:** O(N_nodes) plus a lattice search of (2n_max + 1)ᵖ terms (p = 2: 14,640; p = 5: 13⁵).
- **Invariance:** exactly invariant under per-axis rescaling; deliberately sensitive to lattice orientation.

**Fit quality on F5:** Σ_H recovered the true Σ to 10⁻¹⁰, and D = 0.132 matches the true-Σ value.

**Declared threshold:** A < 2 ln(10⁴) = 18.42 (aliasing amplitude 10⁻⁴).

**All six candidates, 402 family cases:**

| candidate | FN declared / thin | FP declared / thin | cost | new primitive | per-axis-scale invariant |
|---|---|---|---|---|---|
| current guard | 9 / **110** | 31 / 12 | trivial | — | **no** (§10) |
| A. grid-cov thin axis vs projected spacing | 0 / 0 | 184 / 64 | trivial | no | **no** (false alarm on healthy TCR wide) |
| B. grid-cov condition > 10⁴ | 16 / 48 | 109 / 21 | trivial | no | **no** |
| C. as A with Σ_H | 0 / 0 | 183 / 63 | fit | no | **no** |
| **D. aliasing number (Σ_H)** | **0 / 0** | 148 / **28** | fit + lattice search | no | **yes** |
| E. ESS / expected ESS(Σ_H) ∉ [0.5, 2] | 13 / 60 | 73 / 0 | fit | no | yes |
| F. half-step offset grid disagrees | 29 / 146 | 11 / 8 | **one more full grid** (K2: 11,163 CSTR solves) | no | yes |

**D's threshold is not settled.** Post hoc, and **not adopted**, 2 ln(10²) = 9.21 would give thin-rule 188 TP / **6 FP** / 0 FN. The declared 18.42 is conservative; setting the threshold is repair-review work.

## 12. FALSE POSITIVES

**D, at the declared threshold:**

- **Adversarial family:** 28 / 402 under the thin rule, all on resolved-but-close grids with A between 7.9 and 18.4. That is 148 under the marginal rule, because D also flags thin-direction aliasing the marginal rule does not count.
- **Healthy existing cases:** none. The ones it flags (TCR narrow, K2) turned out to be real thin-direction failures (§14, §16).

**The scale-dependent candidates A, B and C** falsely flag the healthy **TCR wide** grid. R_ref ~ 1 Ω and α ~ 0.004 /K, so eigen-structure in raw units is meaningless.

## 13. FALSE NEGATIVES

- **Current guard:** 9 (marginal rule) and **110** (thin rule) out of 402; it also misses the F5 case and K2.
- **D:** **0** under both rules.
- **E:** 60 (thin rule).
- **F:** 146, and it **cannot see F5 at all**, because a diagonal half-step offset is resonant with that ridge.

## 14. TCR REGRESSION

Test designs, truth and seed from `tests/inference/test_tcr_calibration.py`; the frozen 41 × 41 ±6 SE grid. Truth by 2001² principal-axis quadrature of the closed-form TCR law.

| design | guard | marginals vs truth | thin direction vs truth | D | E |
|---|---|---|---|---|---|
| WIDE | ACCEPT, IDENTIFIABLE | exact (10⁻⁹) | exact (1.000) | **69.5, pass** | 1.00, pass |
| NARROW | ACCEPT, WEAKLY | right (sd 0.996×) | **wrong (0.68×)** | **6.13, flag** (true-Σ 6.02) | 0.83, pass |

**TCR narrow is a true positive for D, not a false alarm.** Epistemic predictive sd for R at 300.25 K comes out at **0.68×** truth.

## 15. BATTERY REGRESSION

B3's committed grids, rebuilt serially through the production adapter:

| model | grid | guard | D | A–E |
|---|---|---|---|---|
| P2 | 25³ | ACCEPT, IDENTIFIABLE | **157.9, pass** | all pass |
| P3 | 13⁴ | ACCEPT, IDENTIFIABLE | **88.8, pass** | all pass |

The HD-UQ review showed both agree with the exact linear-Gaussian route to 10⁻⁴ sd. **No false positive.**

## 16. KINETICS REGRESSION

**The grid.** The frozen K2 61 × 61 grid was regenerated with K2's own builder:

- **run:** 3,721 points, 11,163 condition solves, 35 rejected — exactly the committed counts; 1,733 s on 12 workers;
- **reproduction:** the posterior reproduces `k2_report.md`'s mean and sd to 10⁻⁹, for both MULTI and the weak C2 subset.

| posterior | guard | ESS | spacing/sd | D | thin direction |
|---|---|---|---|---|---|
| MULTI | **ACCEPT** (NOT_IDENTIFIABLE) | **1.42** | 0.50, 0.84 | **2.17, flag** | grid sd **0.16×** the proxy (0.00099 vs 0.0061) |
| WEAK_C2 | ACCEPT | 11.6 | 0.06, 0.11 | 4.47, flag | not verified (bounded, non-Gaussian) |

**Reference:** a **proxy**, not exact truth — the HD-UQ local Gaussian, whose importance-sampling ESS was 0.997.

**Predictive effect (frozen `posterior_predictive_uq` vs the linearized proxy), epistemic sd ratio:**

| observable | ratio |
|---|---|
| C1 | 0.84 |
| **C2** | **0.17** |
| C3 | 0.95 |

**For C2 concentration:** epistemic sd 0.27 vs 1.65 against observation σ = 2.0, so the **total** predictive sd is **22 % too small**.

**K2's A5 check (determinant ratio ≤ 0.5)** still PASSES:

| | multi-condition determinant | ratio | reported gain |
|---|---|---|---|
| committed grid | 0.0018 | 4.66 × 10⁻⁴ | "2147×" |
| proxy (s₁²s₂²(1 − ρ²)) | ≈ 0.10 | ≈ 0.026 | about 56× smaller |

**The reported magnitude is inflated roughly 56×.**

## 17. PROPOSED HYBRID ROUTING RULE

Conceptual; **not implemented**.

1. **Small p → try `POSTERIOR_GRID`, but trust it only if all three hold:**
   - (a) the existing guard accepts;
   - (b) the aliasing number A(Σ_H, lattice) clears a reviewed threshold;
   - (c) the log-likelihood quadratic fit exists and is locally concave. Otherwise report `GRID_RESOLUTION_UNVERIFIED`, never a verdict.
2. **The grid fails (b) and the local-Gaussian route is SUPPORTED** (rank, bounds, nonlinearity, multistart) → **prefer `LOCAL_GAUSSIAN_APPROXIMATION`.**
   - This is the thin-but-locally-Gaussian case: F5, TCR narrow, likely K2 MULTI.
   - The local route is exact or near-exact there, and the grid is not.
3. **The grid fails (b) and the local route is refused** (bounded, multimodal, strongly nonlinear) → **re-grid along Σ_H's principal axes** with thin-axis step ≲ √λ_min.
   - D generalizes to a rotated lattice basis B through k = 2π B⁻ᵀn.
   - The existing axis-marginal spacing check must **not** be used there: it is vacuous on a rotated grid (HD-UQ review).
4. **Neither route establishes resolution** → **refuse both**, with `GRID_RESOLUTION_UNVERIFIED` + `LOCAL_GAUSSIAN_REFUSED` and their reasons.
5. **Never** let "ESS ≥ 8" alone, or "spacing ≤ marginal sd" alone, certify a grid.

## 18. V1 CORRECTNESS IMPACT

**Classification: A — V1 correctness bug requiring repair before V2.**

**Why not B (a documented limitation):** it is not documented. The docstring promises refusal of exactly this false precision.

**Why not C (not material):**

- F5's marginals are off by 1.1 sd;
- TCR narrow's thin direction is at 0.68×;
- K2's C2 epistemic sd is at 0.17×, and its determinant is off by about 56×.

**What a repair would change:**

| aspect | change |
|---|---|
| existing public API | **none** (the check runs inside `assess_identifiability` / `posterior_grid_diagnostics`) |
| frozen-contract facts | **none** (`contract.ordering` covers sweep execution, not identifiability) |
| `GridResolutionError` behaviour | **yes:** it would now raise on thin rotated ridges. K2's scoring would raise at MULTI, and `test_the_narrow_span_case_is_not_reported_as_identifiable` would need re-deciding — both now demonstrably mis-resolved |
| existing result semantics | yes, for refused grids: no identifiability status is returned where one was |
| serialized records | none |
| scientific identity | none |
| certificate scope | **yes:** `src/engcore/inference/**` is `CORE_CERTIFIED`, so a certificate reissue is needed; the mutation harness is certification-pinned |

**Also outside the guard's reach today:** `posterior_predictive_uq` / `assess_predictive_observation` have **no** resolution guard, so callers that never call `assess_identifiability` get the understated predictive UQ with no signal. The repair review must decide whether predictive UQ checks resolution too.

**Behaviour is not frozen** (`docs/CORE_FREEZE_POLICY.md` §2), so none of this requires Freeze V2. It does require the §10 "trust or admission semantics" compatibility review.

## 19. V2 API IMPACT

- **For the repair itself:** none.
- **For V2 (additive):** a public resolution diagnostic (aliasing number, Σ_H, fit window) as a record, and the router of §17 naming `GRID_RESOLUTION_UNVERIFIED` as an approximation-class outcome. These belong with the HD-UQ V2 scope.

## 20. CORE FILES CHANGED

**0.** Nothing under `src/`, `tests/api`, `tools/certification` or `certification/` changed.

## 21. FILES CHANGED

All under `benchmarks/core_gap_thin_ridge/`:

- **`audit/`**
  - `thin_ridge.py`
  - `k2_grid.py`
  - `tcr_truth.py`
  - `predictive_impact.py`
- **Results**
  - `PHASE1_REPRODUCTION.json`
  - `PHASE3_FAMILY.json`
  - `PHASE4_PARAMETERIZATION.json`
  - `PHASE6_REGRESSION.json`
- **`tests/test_core_gap_thin_ridge_review.py`**
- **this report**

**Not committed:** the K2 grid (`k2_grid.npz`) is a regenerable scratch artifact.

## 22. RECOMMENDED NEXT ACTION

1. **Open a V1 certified-repair round** (compatibility review → fix → certificate reissue) for the resolution guard:
   - add the aliasing-number check (D) with a threshold chosen by that review;
   - stop the "ESS < 8 **and** spacing ≥ 1" conjunction from certifying ESS ≈ 1 grids;
   - decide whether `posterior_predictive_uq` must refuse unresolved grids.
2. **Record errata before or with the repair:**
   - **K2 (frozen scored experiment):** A5's determinant gain magnitude is overstated about 56×. Grid-based predictive epistemic sd for C2 is about 6× low (verdict still PASS; the magnitude is not).
   - **TCR narrow test design:** its grid's thin direction is 0.68× truth.
3. **Only then design Core V2's router** (§17). The grid can be the trusted route for weak or bounded problems only after this repair.
