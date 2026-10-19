# ODC-04a — realised design dependence in the MCP probabilistic UQ tool: owner approved Option D; implemented, uncommitted

> **Status 2026-10-19:** the owner approved Option D with t = 0.64. It is implemented failing-first in `D:/forge-buy01`
> and is uncommitted, uncertified (OD-3) and not run on the supported Python 3.11/3.12. Evidence is in
> `docs/work/PROGRESS.md` under the same date. The text below is the proposal as approved, kept unchanged.

Scope: `src/engcore/mcp/probabilistic_uq.py` on branch `fix/buy01-fda04-fda14-qmc` (worktree `D:/forge-buy01`, base
`origin/main` `d3c9cd45`, uncommitted). ODC-14a (refuse a tail below 0.5/n) was approved by the owner on 2026-10-19,
and is implemented as it stands. **This document changes no code.** It proposes the ODC-04a decision and records
the evidence for it. All numbers are from scripts run on 2026-10-19 (Windows, Python 3.14.2, SciPy 1.18.1, NumPy
2.5.2, seed 20261019), not the supported 3.11/3.12 interpreter. The scripts are listed at the end.

## The question

BUY-01 replaced the /1 lattice (FDA-04: exact anti-correlated column pairs) with a seeded SciPy midpoint Latin
hypercube. It refuses only an exactly rank-identical or rank-reversed column pair. Random column permutations are
not independent in any finite sample. The realised rank correlation of a pair is ordinary sampling noise, with sd
about 1/sqrt(n-1), and it propagates into the output as if the caller had declared it. ODC-04a decides what the tool
does about that: report it, refuse above a bound, reduce it by design, or a combination.

## What a bound can and cannot protect

Inputs are mapped through their marginal quantiles. On the rank (copula) scale, let R be the design's realised rank
correlation matrix. For an output that is linear in standardised inputs, Y = c^T Z, the design variance is
c^T R c, against a true c^T c. So **the design's sd for every linear output lies within [sqrt(lambda_min(R)),
sqrt(lambda_max(R))] times the true sd**, and the lower end is reached. With n <= k, lambda_min = 0, so some
linear output has zero design variance. That is FDA-04 in its general form.

The bound does **not** extend to nonlinear outputs. The Ishigami check below shows that decorrelating the design
leaves a nonlinear output's sd error unchanged. Any bound is therefore a guard against the FDA-04 class of failure
(additive cancellation that reads as missing uncertainty). It is not an accuracy or coverage statement, and it is
labelled as such.

A max pairwise |rho| does not capture this. At n=32, k=17, the shipped design has max |rho| = 0.47, but
lambda_min = 0.15: a combination of inputs exists whose design sd is 0.39 of the truth. Many moderate correlations
compound; one pairwise threshold does not see that.

## Evidence

### E1 — the shipped design behaves like random permutations, and a bound on it refuses erratically

Shipped design (midpoint LHS, no decorrelation). sd ratio = design sd / true sd for U(0,1) inputs.

| k | n=32 max abs rho | n=32 lambda_min | n=32 worst-linear sd ratio | n>=32 worst max abs rho | n>=32 worst pair-cancel sd ratio |
|---|---|---|---|---|---|
| 2 | 0.065 | 0.935 | 0.967 | 0.453 | 0.739 |
| 3 | 0.105 | 0.830 | 0.911 | 0.453 | 0.739 |
| 5 | 0.447 | 0.505 | 0.711 | 0.453 | 0.739 |
| 10 | 0.447 | 0.294 | 0.542 | 0.515 | 0.696 |
| 17 | 0.467 | 0.150 | 0.387 | 0.531 | 0.685 |
| 25 | 0.481 | 0.010 | 0.102 | 0.575 | 0.652 |

Under any bound, admission is **not monotone in n** for the shipped design. With lambda_min >= 0.64 and k=2, n=32 is
admitted, but a refusal reappears at some n up to 44. With k=5, admission is not guaranteed until n >= 85, and with
k=17 it is not reached at any n <= 256. A caller who raises `sample_count` can turn an answer into a refusal. That
is an indefensible user contract, and it argues for reducing the correlation, not only bounding it.

### E2 — decorrelating designs

Two designs keep the SciPy midpoint LHS marginals (one point per stratum, at its midpoint; checked) and only change
how the columns are paired:

- **IC — Iman–Conover restricted pairing**, identity target, one pass: van der Waerden scores of the ranks, Cholesky
  of their correlation, re-rank each column against the decorrelated scores (Iman & Conover 1982, Commun. Statist.
  Simul. Comput. 11(3):311–334). Deterministic given the seeded design. About 15 lines of NumPy, FORGE-native.
  Requires n > k.
- **CD — SciPy `LatinHypercube(optimization="random-cd")`**: minimises centred discrepancy by coordinate swaps. It is
  maintained by SciPy (BUY), and seeded from the same generator.

Cost of one design at n=256: shipped 0.2–0.4 ms; IC 0.3–1.4 ms; CD 239 ms (k=2), 892 ms (k=17), 1352 ms (k=50).
The tool runs n solver calls afterwards, so neither cost is decisive. CD's result depends on SciPy's optimiser
implementation, which is one more version-identity surface.

Admission under lambda_min >= t over every n in 4..256 (n > k). Each cell gives: designs admitted / total, the
smallest N with every n >= N admitted, and whether n=32 is admitted.

| k | shipped t=0.64 | IC t=0.5 | IC t=0.64 | IC t=0.8 | CD t=0.64 |
|---|---|---|---|---|---|
| 2 | 239/253, >=45, yes | 252/253, >=7, yes | 252/253, >=7, yes | 251/253, >=9, yes | 253/253, >=4, yes |
| 3 | 228/253, >=45, yes | 252/253, >=7, yes | 250/253, >=7, yes | 246/253, >=11, yes | 252/253, >=5, yes |
| 5 | 200/251, >=85, no | 249/251, >=9, yes | 247/251, >=10, yes | 240/251, >=26, yes | 250/251, >=7, yes |
| 10 | 99/246, >=246, no | 245/246, >=12, yes | 235/246, >=24, yes | 208/246, >=82, no | 237/246, >=24, yes |
| 17 | 1/239, never, no | 236/239, >=27, yes | 225/239, >=45, no | 165/239, >=154, no | 209/239, >=49, no |
| 25 | 0/231, never, no | 228/231, >=32, yes | 209/231, >=52, no | 99/231, >=207, no | 164/231, >=104, no |

At t=0.64, CD and IC are close for k <= 10. For k = 17 and 25, CD needs a larger n (49 and 104) than IC (45 and 52).
At n=256, k=50: lambda_min is 0.34 shipped, 0.78 IC and 0.42 CD.

Known IC limit: one pass is not a full decorrelation. At k=2, n=32 its correction was too small to swap any rank
(0 rows re-paired; |rho| stays 0.065). Iterating IC, or a pairing tuned on ranks rather than scores, would tighten
the small-correlation end. That is not proposed here.

### E3 — what decorrelation buys on outputs (n >= 32, k=3, relative error of the design sd)

| Output | Design | median | 95th pct | worst |
|---|---|---|---|---|
| Additive Y = X1+X2+X3 | shipped | 0.037 | 0.103 | 0.237 |
| | IC | 0.010 | 0.033 | 0.052 |
| | CD | 0.003 | 0.014 | 0.019 |
| Ishigami (a=7, b=0.1) | shipped | 0.031 | 0.110 | 0.183 |
| | IC | 0.037 | 0.112 | 0.169 |
| | CD | 0.031 | 0.079 | 0.182 |

The CD row samples every 8th n (29 designs); the others use every n (225). Decorrelation removes most of the additive
error, which is the FDA-04 class. It does not reduce a nonlinear output's error, which is ordinary finite-sample
error, already listed under `does_not_include` as "sampling error of the quantile estimate".

## Options

| Option | What it does | For | Against |
|---|---|---|---|
| A. Report only | Keep the |rho|=1 refusal; add lambda_min/lambda_max to `sample_design` | No refusals added | A completed answer can carry a 0.39 worst-linear sd ratio (k=17, n=32) with nothing stopping it |
| B. Pairwise bound on the shipped design | Refuse max abs rho > r* | Simple | Misses compounding (E1); admission not monotone in n |
| C. lambda_min bound on the shipped design | Refuse lambda_min < t | Covers every linear output | Not monotone in n; refuses most k >= 5 at the default n=32 |
| **D. IC re-pairing + lambda_min bound** | Decorrelate, then refuse lambda_min < t and n <= k | Admission near-monotone from small N; ~1 ms; marginals untouched | Native code (not BUY); one pass leaves small residual correlation |
| E. CD (SciPy random-cd) + lambda_min bound | Optimised LHS, then the same guard | BUY; best at small k | 0.2–1.4 s per design; weaker at k=50; optimiser is a version-identity surface |

## Recommendation (for the owner to accept, change or reject)

**Option D, with t = 0.64.** In words: with standardised inputs, refuse when some linear combination of the
declared inputs would have its sample sd understated by more than 20% (sqrt(0.64) = 0.8). The concrete changes:

1. After the seeded midpoint LHS, apply one Iman–Conover pass to the identity target. Marginals, stratification,
   seed and SciPy sampler stay as they are. Record `"pairing": "iman_conover_identity_vdw/1"` in the sampler identity.
2. Refuse `n <= k`, and refuse `lambda_min(R_rank) < 0.64`, with a message naming lambda_min and the input count.
   This subsumes today's exact |rho| = 1 refusal.
3. Always report `lambda_min`, `lambda_max`, the linear-output sd band `[sqrt(lambda_min), sqrt(lambda_max)]`, and the
   max |rho| pair, labelled `design_dependence_bound_linear_outputs_only`.
4. Schema stays `engineering_probabilistic_uq/2`. /2 has not been merged or published, so its values change once,
   before release. Merge still needs OD-3: forge_check classifies `server.py` and both test files certification_pinned.

Why 0.64 rather than 0.5 or 0.8, as a policy choice and not a derived constant:

- 0.5 (worst linear sd understated by 29%) is looser than the sd estimator's own sampling error at n=32,
  1/sqrt(2*31) = 12.7% for a normal output, by more than a factor of two.
- 0.8 (10.6%) refuses the default n=32 call for k=10 even with IC, and needs n >= 154 for k=17.
- 0.64 keeps the default call answering for k <= 10 with IC, and needs n >= 45 for k=17 and n >= 52 for k=25.

Risk policy sets the evidence bar; it is not evidence. The threshold is the owner's to choose.

Option E is the BUY alternative to D's native pairing. If the owner prefers a SciPy-maintained algorithm over 15
native lines, E works under the same guard, at the cost and identity surface measured above.

## Required verification if approved

- Failing-first tests: n <= k refused; the shipped k=17 n=32 design refused before IC and admitted after it, or
  refused with lambda_min stated; lambda_min reported; IC leaves every marginal's midpoint stratification unchanged;
  same seed gives the same design; FDA-04/14 tests unchanged and green.
- Property test over n in 4..256 for k in {2, 3, 5, 10, 17}: every admitted design has lambda_min >= t.
- MCP module, server and forge_check `--changed` suites, with the failure set compared against a pristine
  `origin/main` (as done for BUY-01).
- Supported-Python (3.11/3.12) run; OD-3 recertification. No coverage-calibration claim follows from any of this.

## Scripts (session scratch, not committed)

`odc04a_census.py` (E1, E2 summary, E3 inputs), `odc04a_checks.py` (IC sanity, timing, lambda_min admission),
`odc04a_nonlinear.py` (E3). Each imports the production design generator from the worktree
(`engcore.mcp.probabilistic_uq._unit_design`).
