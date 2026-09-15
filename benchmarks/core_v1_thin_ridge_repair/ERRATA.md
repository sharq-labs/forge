# Errata: claims affected by the thin-ridge grid-resolution defect

**Round:** Core V1 certified repair: thin-ridge posterior resolution guard.

**Evidence:**

- `benchmarks/core_gap_thin_ridge`, review commit 273bfff;
- this round's `AFFECTED_TESTS.json` and `REGRESSION_MATRIX.json`.

**Policy:** the original artifacts are not edited. Each entry below records the following:

- the claim as it was committed;
- what was wrong, and how it was measured;
- the corrected reading;
- which conclusions still stand.

## The defect, in one paragraph

The frozen check refused a grid posterior only when both of these held:

- ESS < 8;
- some axis step was at least that axis's **marginal** sd.

By Poisson summation, a lattice aliases a Gaussian along every reciprocal vector 2πn/h, not only the axes. So a thin ridge tilted across the lattice passed the check. The grid then reported:

- a thin-direction sd that was too small;
- a correlation pushed toward ±1;
- an epistemic predictive sd that was too small.

These results were stable under nested refinement, and the check passed ESS 1.42. Marginal means and marginal sds were usually close to right, which is why nothing looked wrong. The repair refuses such grids (see `REPAIR_REPORT.md`).

---

## E1: TCR narrow-span test design (`tests/inference/test_tcr_calibration.py`)

**As committed.** The narrow design (six readings over 299–301.5 K) was assessed on a 41 × 41 grid spanning ±6 marginal SE. It was used as the example of a weakly identified posterior in these tests:

- `test_the_narrow_span_case_is_not_reported_as_identifiable`;
- `test_the_two_designs_do_not_report_the_same_confidence`;
- `test_calibration_and_identifiability_are_separate_verdicts`.

**What was wrong.** Measured against dense quadrature of the closed-form law:

| grid | aliasing number | thin-direction sd | marginal sd | grid correlation (exact −0.9931) |
|---|---|---|---|---|
| 41 × 41 | 6.13 | **0.68×** | 0.996× | −0.9968 |
| 81 × 81 | 24.7 | 1.000× | 1.000× | −0.9931 |

Epistemic predictive sd along the thin direction is understated by the same 0.68×.

**Corrected reading.** The design **is** weakly identified. The 81-node grid still classifies it as not IDENTIFIABLE, with |ρ| > 0.95 and a wider α interval than the wide design. So the three tests' conclusions stand. The 41-node grid overstated how thin the ridge is by about 1.5×. The tests now use 81 nodes.

**Still valid:**

- the wide-versus-narrow comparison;
- the separation of calibration from identifiability;
- every wide-span result, which was measured healthy with an aliasing number of 69.5.

## E2: TCR held-out case C (`tests/inference/test_tcr_heldout_uq.py`)

**As committed.** `test_case_c_a_broad_posterior_is_a_scientific_verdict_not_a_grid_refusal` used the narrow design on a 21 × 21 grid, seed 5. Its comment stated three things:

- "the grid step is 0.6 of the posterior's own standard deviation, so the grid resolves it perfectly well";
- ESS 5.9 was concentration "ACROSS its short axis, which is a fact about the science";
- this is "why the grid refusal requires two conditions rather than one".

**What was wrong.** The grid did not resolve the posterior:

- aliasing number 1.46;
- thin-direction sd **0.055×** exact;
- grid correlation −1.00000, where the exact value is −0.9933.

The step was 0.6 of the **marginal** sd, not of the thin principal sd. The low ESS was a symptom of aliasing, not a scientific fact. The rationale given for the two-condition rule is therefore wrong on this example.

**Corrected reading.** At 81 nodes (aliasing number 24.1, thin sd 1.000×) the posterior is resolved, and it is still classified WEAKLY or NOT identifiable. So the test's requirement stands: a broad posterior gets a verdict, and a collapsed one is refused.

The test now does two things:

- asserts that the 21-node grid **is** refused;
- reads the verdict from the 81-node grid.

The general point survives, but with a different reason: low ESS alone does not refuse. For example, the coverage-study grid at 15 nodes has ESS 6.3 and is resolved (aliasing number 9.9, thin sd 0.93×).

## E3: coverage-study determinism test (`tests/inference/test_reproducibility_and_evidence.py`)

**As committed.** `test_the_coverage_study_is_a_function_of_its_seed_schedule` ran `run_coverage_study` with `grid_points_per_axis=11`.

**What was wrong.** At 11 nodes the calibration posterior has these properties for seeds 11–13:

- aliasing number 5.0;
- thin sd 0.58×;
- ESS 3.1.

The frozen rule already refused it for identifiability. Predictive UQ had no check, so the coverage intervals were computed from understated epistemic sd.

**Corrected reading.** The test is about determinism, and that claim stands. It now uses 15 nodes, the study's default, which is resolved. `run_coverage_study`'s own default was never affected.

## E4: K2 kinetics multiparameter inference (`experiments/kinetics_k2/k2_report.md`, PASS / FROZEN)

K2's committed grid was regenerated with K2's own builder and reproduces the report to 10⁻⁹. The comparison reference is the committed local Gaussian proxy (HD-UQ review, importance-sampling ESS 0.997). It is a **proxy, not exact truth**.

| K2 claim | committed | corrected reading | still valid? |
|---|---|---|---|
| Multi-condition posterior covariance, determinant 0.00181, correlation 0.99998 | accepted by the frozen check | **Under-resolved.** ESS 1.42. Thin-direction sd 0.16× the proxy (0.00099 vs 0.0061). The determinant is ≈0.10 by the proxy. **The repair refuses this grid**, for ESS below p + 1. | **No:** the covariance, determinant and correlation of the MULTI grid are not reliable numbers. |
| A5 (identifiability gain vs weak C2, determinant ratio ≤ 0.5): ratio 4.66 × 10⁻⁴, "≈2147×" | PASS | Ratio ≈ 0.026 by the proxy, so the gain is **overstated about 56×**. The weak-C2 determinant (3.89) is itself from a grid with aliasing number 4.47, which **the repair also refuses**, and it has no reference. The corrected ratio is therefore an estimate, not a measurement. | **The PASS verdict likely stands:** 0.026 ≪ 0.5, with two orders of margin. **The magnitude "2147×" does not.** |
| A6 (ridge reduction vs weak C2), marginal sd reductions 7.87× and 7.85× | PASS | Marginal sds are within about 6% of the proxy. The weak marginals are unverified. | **Likely stands.** |
| A3 / A4 (truth inside 95% marginal intervals; posterior-mean accuracy) | PASS | Marginal means and marginal sds were not materially affected in the review. | **Stands**, subject to the weak-C2 caveat for any interval read from the weak posterior. |
| A1, A2, A7–A9 (admissibility, finiteness, repeated recovery, replay, parity) | PASS | Not a grid-resolution claim. | **Stands.** |
| Implicit: grid-based epistemic predictive sd for C2 | reported via downstream use | 0.17× the linearized proxy. The C2 concentration's **total** predictive sd is 22% too small. C1 is 0.84× and C3 is 0.95×. | **No** for C2's predictive sd magnitude. |

**Identifiability class.** Both K2 posteriors are strongly correlated, and "the multi-condition design contracts the ridge" is supported by the proxy: the determinant ratio is ≈0.026. What is not supported is the size of that contraction, and any quantitative use of the MULTI grid covariance.

**Downstream.** K3, K3.1 and K4 reuse the frozen K2 posterior support for posterior-predictive UQ and adequacy. Their grid-based epistemic predictive sds inherit the understatement. Under the repair they raise `GridResolutionError` instead of reporting.

This round did not re-run them, so their numbers are **not corrected here**. They are marked affected and unquantified. A resolved grid or a non-grid route would be needed to restate them.

## E5: Battery B3 parameterization-sensitivity readout (informational)

B3 §23 assessed identifiability on its grid posteriors **linearly mapped** into a second parameterization (`PosteriorGrid(points=posterior.points @ T.T)`). The mapped points are not an axis-aligned tensor lattice. The repair refuses them as unverifiable, not as wrong: the linear map of a resolved lattice is resolved.

The B3 primary grids are all measured healthy (`REGRESSION_MATRIX.json`), so §23's conclusion is **not** in error: identifiability verdicts depend on parameterization. The readout cannot be regenerated through `assess_identifiability` on a mapped grid. To regenerate it, assess in the grid's own coordinates and map moments (Σ′ = TΣTᵀ).

## Not affected

The following were checked and found unaffected:

- **Battery B1 and B2:** their audit scripts were re-run at the repair commit and reproduce the committed RESULTS.json exactly, except wall-clock fields.
- **Battery B3 primary grids P1, P2, P3, P4, T3, T5:** all correctly kept against their exact linear-Gaussian posteriors.
- **TCR wide-span results.**
- **The toy discrete posteriors** in the K3/K3.1/K4 unit tests. Exact discrete-mixture semantics are preserved for posteriors with too few nodes to fit a curvature.

---

## Addendum (Core V2 round): E4 restated with measured values

The E4 table above gave **estimates** against a local Gaussian proxy. They have now been **measured** with a converged reference and the Core V2 route (`benchmarks/core_v2_hybrid_uq/KINETICS_K2.json`).

**Method.**

- **Reference grids:** built in decorrelated coordinates (ln k(T*), E/R) with the frozen K2 forward model. Each grid was contained, accepted by the repaired V1 checks, and converged under nested refinement (moments moved < 0.05 sd).
- **V2 route:** `route_uncertainty` for MULTI, with a 6-start multistart.

| K2 quantity | committed (k2_report.md) | corrected: V2 route | corrected: converged reference grid |
|---|---|---|---|
| MULTI covariance | [[0.02311, 7.528], [7.528, 2452.0]] | [[0.02609, 8.515], [8.515, 2782.7]] | [[0.02618, 8.545], [8.545, 2792.6]] |
| MULTI determinant | 0.001812 | 0.10223 | **0.10253** |
| MULTI correlation | 0.999984 | 0.999296 | **0.999299** |
| C2 C_A epistemic predictive sd (mol/m³) | ≈0.27 (aliased grid) | 1.649 | **1.648** |
| C2 C_A total predictive sd (σ = 2.0) | ≈2.02 | 2.592 | **2.592** |
| C2 T epistemic predictive sd (K) | — | 0.1116 | **0.1115** |
| WEAK_C2 determinant | 3.891 | REFUSED (no residual dof) | **7.469** |
| A5 ratio multi/weak (criterion ≤ 0.5) | 4.66 × 10⁻⁴ | — | **0.0137 — PASS stands** |
| A5 gain weak/multi | "2147×" | — | **72.8×** |

**Two refinements to E4:**

1. The gain was overstated **29.5×**, not the ~56× the proxy suggested. The committed weak determinant was **also** too small (3.89 against 7.47), which partly offset the MULTI error.
2. The weak-C2 posterior is exactly a ridge. Both C2 observables depend on k only at the reactor temperature, T* = 324.37 K, so the data identify ln k(324.37 K) and the prior box bounds the rest.
