# Genesis-lite v0.3: power and null-calibration study (ODC-O1b), 2026-10-20

**Status:** NON-FORMAL and SYNTHETIC. This is evidence for the owner about the v0.3 statistical rule under a stated synthetic
credit model. It is not a measurement of any arm, not a validation, and not a lift result. It read no hidden world, no pilot
record and no formal root.

**Authorisation:** owner D2 (2026-10-20).

**Rule measured:** the rule DECIDED by the owner on 2026-10-20:
- D1: the pair bound.
- D2: the root-keyed sign-flip p.
- D3: the comparison set and the caps.
- D3b-1: cell-level cap, implementation P2. A capped (kind, presentation) cell contributes min(0, its net difference) to the
  effect size and the per-kind non-inferiority. Significance comes from the uncapped differences only.
- D3b-2: per-kind non-inferiority margin 0.15, with every kind still required.

**Provenance** (`result.json` → `provenance`):

| | |
|---|---|
| HEAD | `f76c1ca966aac6dbdb9185c4d8e5dd836b50052a` |
| Tree | clean (`tree_clean: true`) |
| Code sha256: `power_study.py` | `ef54a3caf18cbf7299faa67ca3e03a1e5b44a60fcb04a7acac72bf97ca1320a0` |
| Code sha256: `analysis.py` | `a66c822f45f07998539a6476b925cd480c4c7872a29b180c1dc5b953ad833dcc` |
| Code sha256: v0.2 `analysis.py` | `76eea7c01fa971e2ce0a8f462ff79e7ab3eb1611ba6af8878994c84d8e01a0a9` |
| Python | 3.14.2 |
| numpy | 2.5.2 |
| Platform | Windows-11-10.0.26200-SP0 |
| Draft preregistration at run time | `b876b2fefcf2e49b105873f030c799356996cf63dca7cc59bf4b1e8695dcd6ba` (before this evidence digest was pinned into it) |
| Wall time | 2733.3 s |
| `result.json` sha256 | `a732df70f3a7540cbc4d96461af0b1c882b993f60b16890282b862c5b19b36fa` |

The `result.json` digest is pinned in `preregistration.POWER_STUDY_EVIDENCE_SHA256`. Two tests check it:
- `test_o1_power_study_evidence_is_pinned_and_says_what_the_ledger_quotes`
- `test_o1_power_study_evidence_measured_the_rule_that_is_in_the_tree` (the recorded code digests equal the git blobs at
  HEAD, and the live rule, docstrings aside, equals that code)

Command:

`python -m benchmarks.genesis_lite.v0_3.power_study --out <result.json> --reps 100 --null-reps 2000 --crosscheck-reps 20 --workers 4`

**Superseded runs, all measuring the pre-D3b rule (per-world-set min cap, 0.10 margins):**
- the first run at HEAD `27a5d6db`, from an uncommitted file;
- the post-review run at HEAD `70195498`, result sha256 `282b4213…8b36` (commit `2dbbd462`).

Their findings are what D3b-1 and D3b-2 decided on:
- With the per-world-set min, solved controls, independent outcomes and doubled discoverable success, claims were 0/100
  (pooled mean −1.20).
- The all-kind 0.10 conjunction failed 33/100 at equal skill.

**Credit model:** per-universe credits +1 / -1 only (the maximum-variance case); DEFAULT_CREDIT also has 0, +0.5 and -0.5 outcomes, so the power figures and the cap penalty hold for this model only

## Part A: null calibration of the D2 statistic

Method: the one-sided paired sign-flip p, with a fresh root-keyed Monte-Carlo stream per replicate, at the formal sizes
(600 / 2,400 world sets). Under P2 this is the statistic the decision uses: capped cells never enter it.

Brackets are exact 95 % Clopper-Pearson intervals.

| null | n | alpha 0.01 | alpha 0.05 | alpha 0.10 | Holm family-wise rate |
|---|---|---|---|---|---|
| exchangeable (in scope), 2000 reps | pooled | 0.0085 | 0.0490 [0.040, 0.059] | 0.0920 | 0.0450 [0.036, 0.055] |
| exchangeable, 2000 reps | one presentation | 0.0105 | 0.0460 | 0.0905 | |
| skewed mean-zero (outside the scope), 1000 reps | pooled | 0.0130 | 0.0640 [0.050, 0.081] | 0.1080 | 0.0420 |

**Reading.**
- The in-scope rates are consistent with nominal, resolved to about ±0.01. This is an implementation check of a guarantee that
  holds by construction.
- The skewed null is outside the covered scope. Its rates are not distinguishable from nominal at this replicate count.

## Part B: power of the whole decided v0.3 decision (100 reps per cell)

Each cell shows the claim rate with the mean pooled difference in parentheses.
- `careful` has discoverable success 0.2.
- The candidate has discoverable success 0.2 + delta and equals `careful` on every other kind.
- rho is the probability that the candidate's outcome copies `careful`'s.

| controls (careful's rate) | delta | rho 0 | rho 0.5 | rho 0.9 | rho 1.0 |
|---|---|---|---|---|---|
| solved (0.8 → CONTROL_SOLVED) | 0.0 | 0.00 (-0.091) | 0.00 (-0.064) | 0.00 (-0.028) | 0.00 (+0.000) |
| solved (0.8 → CONTROL_SOLVED) | 0.05 | 0.00 (+0.010) | 0.05 (+0.037) | 0.97 (+0.073) | 1.00 (+0.100) |
| solved (0.8 → CONTROL_SOLVED) | 0.1 | 0.42 (+0.110) | 0.92 (+0.134) | 1.00 (+0.174) | 1.00 (+0.200) |
| solved (0.8 → CONTROL_SOLVED) | 0.2 | 1.00 (+0.307) | 1.00 (+0.335) | 1.00 (+0.368) | 1.00 (+0.402) |
| unsolved (0.4) | 0.0 | 0.01 (-0.000) | 0.00 (-0.008) | 0.03 (+0.002) | 0.00 (+0.000) |
| unsolved (0.4) | 0.05 | 0.20 (+0.100) | 0.39 (+0.100) | 0.98 (+0.097) | 1.00 (+0.101) |
| unsolved (0.4) | 0.1 | 0.71 (+0.195) | 0.94 (+0.202) | 1.00 (+0.198) | 1.00 (+0.200) |
| unsolved (0.4) | 0.2 | 1.00 (+0.388) | 1.00 (+0.401) | 1.00 (+0.400) | 1.00 (+0.397) |

Two further cells:
- 30 % of truths out of family: 1.00 (pooled mean +0.280).
- The representation arm solves discoverable: 0.00, by design (§10.3).

## Findings (conditional on the ±1 credit model)

1. **False claims under equal skill.**
   - Unsolved controls, delta 0, rho in {0, 0.5, 0.9}: 4/300 claims (95 % interval [0.004, 0.034]).
   - Solved controls, the same cells: 0/300 claims (95 % interval [0.000, 0.012]).
   - The rho = 1 cells are degenerate: every difference is 0.
2. **The cell-level cap (D3b-1).**
   - A difference that lies only in capped cells can no longer win or lose by noise world set by world set.
   - With solved controls and independent outcomes, delta 0.2 now claims 1.00.
     Under the per-world-set min it claimed 0.00.
   - **A residual noise bias remains.** Each noisy capped cell contributes E[min(0, X)] = −σ_cell/√(2π) at equal skill.
     Summed over the 20 capped control cells (5 kinds × 4 presentations) this is about −0.09 per world set; observed
     -0.091 at solved/delta 0/rho 0.
   - So small gains with solved controls still do not claim: delta 0.05 at rho 0 gives
     0.00.
   - The bias shrinks as outcomes correlate and grows with the number of noisy capped cells.
   - This corrects the builder's earlier estimate to the owner ("about −0.006"), which omitted the sum over cells.
3. **No gain through a capped cell (P2).** Capped data never enter the sign-flip p. They enter the effect size only through
   min(0, net). Both properties are tested adversarially in `test_d3b_*`.
4. **Per-kind non-inferiority (D3b-2).**
   - At equal skill the conjunction of 0.15 margins failed in 0.00 of the replicates in the unsolved/delta-0/rho-0
     cell. Under 0.10 it failed 0.33.
   - Each kind's lower bound sits about 0.056 below its mean (SE ≈ 0.028), so 0.15 is about 3.4 SE beyond the bound.

| kind | SD of the mean difference | mean (mean − lower95) | fail rate |
|---|---|---|---|
| confounded | 0.0257 | 0.0556 | 0.00 |
| discoverable | 0.0228 | 0.0452 | 0.00 |
| indistinguishable | 0.0287 | 0.0557 | 0.00 |
| insufficient_evidence | 0.0301 | 0.0555 | 0.00 |
| no_solution | 0.0278 | 0.0558 | 0.00 |
| spurious_correlate | 0.0294 | 0.0556 | 0.00 |

5. **Coverage limits.**
   - The study fields two baselines; the real rule takes its maximum over about 20 registered arms. Selection on the same data
     raises the reference, so these power figures are optimistic.
   - That direction costs power in this synthetic model.
   - The final scientific review (2026-10-20, I-1) adds a caveat. Which cells are capped depends partly on the
     comparator's own outcomes, so the size of the significance test is conditional on that partition and can exceed
     nominal slightly. The study does not measure this.

## Bootstrap cross-check

**Note:** in this run the cross-check is uninformative. The representation arm's rates (0.1, and 0.8 in one cell) sit far
from the 0.5 threshold of `representation_limited`, so a zero gap is expected. Its threshold-flip count also uses a −0.1 kind
bound, a study constant from before D3b-2.

Under D3b-1 the decision's bootstrap is `analysis.capped_bootstrap_ci` (numpy). The study uses that production function
unchanged. The vectorised substitute now affects only v0.2's `representation_limited`. The cross-check scores the same records
and root with and without that substitute:

| cell | reps | claims agree | max abs lower-bound gap | threshold flips |
|---|---|---|---|---|
| controls_solved/delta=0.1/rho=0.9 | 20 | 20/20 | 0.0000 | 0 |
| controls_unsolved/delta=0.05/rho=0.5 | 20 | 20/20 | 0.0000 | 0 |
