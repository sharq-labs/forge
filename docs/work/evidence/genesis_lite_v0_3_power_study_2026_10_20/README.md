# Genesis-lite v0.3: power and null-calibration study (ODC-O1b), 2026-10-20

**Status:** NON-FORMAL and SYNTHETIC. This is evidence for the owner about the v0.3 statistical rule under a stated synthetic
credit model. It is not a measurement of any arm, not a validation, and not a lift result. It read no hidden world, no pilot
record and no formal root.

**Authorisation:** owner D2 (2026-10-20), run after D3 (decided 2026-10-20).

**Provenance** (`result.json`, `provenance`):

| | |
|---|---|
| HEAD | `70195498bd82437e951e93df7f5594c71a1d4eda` |
| Tree | clean (`tree_clean: true`) |
| Code sha256 (`power_study.py`) | `ef54a3caf18cbf7299faa67ca3e03a1e5b44a60fcb04a7acac72bf97ca1320a0` |
| Code sha256 (`analysis.py`) | `f896bea914000c15f201c36e243aa2b480d6612e3f7660bcb7c97b36189e5242` |
| Python | 3.14.2 |
| numpy | 2.5.2 |
| Platform | Windows-11-10.0.26200-SP0 |
| Draft preregistration at run time | `455c9f3dfe32b5514f3dddf32631dbf69f003bf2870c6c6b2818e0612cd16fe1` (before the evidence digest was pinned into it) |
| Wall time | 1725.0 s |
| `result.json` sha256 | `282b42131b074a7b1c7f599e54f784f78ffc37763c185fc545a7b781b6ce8b36` (pinned in `preregistration.POWER_STUDY_EVIDENCE_SHA256`; checked by `test_o1_power_study_evidence_is_pinned_and_says_what_the_ledger_quotes`) |

Command:

`python -m benchmarks.genesis_lite.v0_3.power_study --out <result.json> --reps 100 --null-reps 2000 --crosscheck-reps 20 --workers 4`

A first run (HEAD `27a5d6db`, from an uncommitted study file) is superseded by this one. It was re-run after the scientific
review of 2026-10-20 to record provenance and a real bootstrap cross-check.

**Credit model:** per-universe credits +1 / -1 only (the maximum-variance case); DEFAULT_CREDIT also has 0, +0.5 and -0.5 outcomes, so the power figures and the cap penalty hold for this model only

## Part A: null calibration of the D2 statistic

Method: the one-sided paired sign-flip p, with a fresh root-keyed Monte-Carlo stream in every replicate, at the formal sizes
(600 world sets per presentation and 2,400 pooled).

Brackets are exact 95 % Clopper-Pearson intervals.

| null | n | alpha 0.01 | alpha 0.05 | alpha 0.10 | Holm family-wise rate (5-member family) |
|---|---|---|---|---|---|
| exchangeable (in scope), 2000 reps | pooled | 0.0090 | 0.0500 [0.041, 0.060] | 0.0935 | 0.0450 [0.036, 0.055] |
| exchangeable, 2000 reps | one presentation | 0.0105 | 0.0465 | 0.0900 | |
| skewed mean-zero (outside the scope), 1000 reps | pooled | 0.0130 | 0.0640 [0.050, 0.081] | 0.1060 | 0.0420 |

**Reading.**
- Under the exchangeable null, the rejection rates are consistent with nominal. At 2000 replicates this resolves the
  size only to about ±0.01.
- This is an implementation check of a guarantee that holds by construction ((b+1)/(M+1) with random sign vectors). It is
  not a new statistical result.
- The skewed null lies outside the covered scope. Its rates are not distinguishable from nominal at this replicate count.
  Nothing here establishes that the test is anti-conservative there.

## Part B: power of the whole v0.3 decision (100 reps per cell)

Each cell shows the claim rate with the mean pooled difference in parentheses.
- `careful` has discoverable success 0.2.
- The candidate has discoverable success 0.2 + delta and equals `careful` on every other kind.
- rho is the probability that the candidate's outcome copies `careful`'s, through a shared uniform.

| controls (careful's rate) | delta | rho 0 | rho 0.5 | rho 0.9 | rho 1.0 |
|---|---|---|---|---|---|
| solved (0.8 → CONTROL_SOLVED) | 0.0 | 0.00 (-1.60) | 0.00 (-0.80) | 0.00 (-0.16) | 0.00 (+0.00) |
| solved (0.8 → CONTROL_SOLVED) | 0.05 | 0.00 (-1.50) | 0.00 (-0.70) | 0.00 (-0.06) | 1.00 (+0.10) |
| solved (0.8 → CONTROL_SOLVED) | 0.1 | 0.00 (-1.40) | 0.00 (-0.60) | 0.47 (+0.04) | 1.00 (+0.20) |
| solved (0.8 → CONTROL_SOLVED) | 0.2 | 0.00 (-1.20) | 0.00 (-0.40) | 1.00 (+0.24) | 1.00 (+0.40) |
| unsolved (0.4) | 0.0 | 0.01 (-0.00) | 0.00 (-0.01) | 0.03 (+0.00) | 0.00 (+0.00) |
| unsolved (0.4) | 0.05 | 0.20 (+0.10) | 0.41 (+0.10) | 0.98 (+0.10) | 1.00 (+0.10) |
| unsolved (0.4) | 0.1 | 0.66 (+0.19) | 0.94 (+0.20) | 1.00 (+0.20) | 1.00 (+0.20) |
| unsolved (0.4) | 0.2 | 0.69 (+0.39) | 0.99 (+0.40) | 1.00 (+0.40) | 1.00 (+0.40) |

Two further cells:
- Unsolved controls, delta 0.2, rho 1, with 30 % of the truths out of family: claim rate 1.00 (pooled mean
  +0.28).
- Unsolved controls, delta 0.2, rho 1, with the representation arm solving discoverable at 0.8: 0.00, by
  design (§10.3).

## Findings (conditional on the ±1 credit model)

1. **False claims under the null.**
   - The informative null cells are those with unsolved controls, delta 0 and rho in {0, 0.5, 0.9}. They give
     4/300 claims; the exact 95 % interval is [0.004, 0.034].
   - The solved-controls delta-0 cells with rho < 1 are excluded because they are not null: the cap makes their mean
     negative by construction.
   - The rho = 1 cells are excluded because they are degenerate: every difference is 0, so p = 1.
2. **The cap form decides the claimable region (owner question D3b(a)).**
   - The FDA-06 / CONTROL_SOLVED cap is a per-world-set `min(mine, theirs)`, as in v0.2.
   - With ±1 credits a capped cell contributes −E[(ref − mine)⁺] = −2·p_ref·(1 − p_mine). That is −2p(1−p) for equal rates
     with independent outcomes.
   - With five solved control kinds at 0.8 this predicts −1.6 + 2·delta, which matches the observed pooled means.
   - A candidate whose outcomes are not near-copies of `careful`'s (rho ≤ 0.5) therefore does not claim, even when it
     doubles discoverable success. Claims need world-by-world dominance on the capped cells.
   - The `min` itself can only lower the candidate's credit. Whether the whole decision avoids false support is shown here
     only for this synthetic model.
3. **The kind non-inferiority conjunction caps power (owner question D3b(b)).**
   - Setting: unsolved controls, delta 0, rho 0 (per-kind statistics over that cell's replicates).
   - At equal skill, each control kind's 95 % lower bound sits about 0.056 below its mean. That is about two standard errors,
     with SE ≈ 0.028 at p = 0.4 and 2,400 world sets.
   - So the 0.10 margin fails about 6 % of the time per control kind, and about 26 % across the five control kinds.
     Discoverable fails rarely (≈ 0.9 %).
   - The independent-outcome cells therefore saturate below a claim rate of 1.

| kind | SD of the mean difference | mean (mean − lower95) | fail rate |
|---|---|---|---|
| confounded | 0.0257 | 0.0555 | 0.07 |
| discoverable | 0.0228 | 0.0454 | 0.01 |
| indistinguishable | 0.0287 | 0.0557 | 0.07 |
| insufficient_evidence | 0.0301 | 0.0559 | 0.10 |
| no_solution | 0.0278 | 0.0554 | 0.08 |
| spurious_correlate | 0.0294 | 0.0554 | 0.07 |

## Bootstrap cross-check

The vectorised bootstrap is the same estimator as v0.2's original, with a different random generator:
- B = 2,000 resamples of world sets;
- the floor 2.5 % order statistic at index max(int(0.025·B)−1, 0);
- a fixed seed.

Method: the SAME records and root were scored with both bootstraps, in cells near the decision boundary. Every lower bound
(pooled, presentations, kinds) and the claim were compared replicate by replicate.

| cell | reps | claims agree | max abs lower-bound gap | replicates where a pooled or kind threshold flips |
|---|---|---|---|---|
| controls_solved/delta=0.1/rho=0.9 | 20 | 19/20 | 0.0100 | 1 |
| controls_unsolved/delta=0.05/rho=0.5 | 20 | 20/20 | 0.0200 | 0 |

Note: the pooled mean does not depend on the bootstrap, so it is not part of the comparison.

**Reading:** the two bootstraps are statistically equivalent but NOT identical.
- Lower bounds differ by up to about 0.01.
- In replicates sitting on a threshold, that gap can flip a decision (1 of 20 in the boundary cell above).
- Part B claim rates near the boundary therefore carry this extra error of a few percentage points, on top of the binomial error of 100 replicates.
- Cells far from the boundary (claim rate 0 or 1) are not affected.
