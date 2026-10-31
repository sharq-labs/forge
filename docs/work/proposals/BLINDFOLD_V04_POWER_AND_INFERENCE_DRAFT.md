---
ai_schema_version: 1
doc_id: FORGE-BLINDFOLD-V04-POWER-INFERENCE-DRAFT
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: 7d24c9485043ab31e49601c33a9334c1e6a44368
evidence_level: EXECUTED
last_reviewed: 2026-10-30
supersedes: none
---

# DRAFT A3: power and inference options for the Genesis-lite v0.4 preregistration (gap G1, decision D9)

**PROPOSED, for the owner's decision D9. It changes no statistics code.** The numbers here are development planning
inputs computed from one development pilot and from synthetic null laws. They are not a formal result, a lift claim
or Blindfold evidence. Scope: ACTIVE_PLAN "Blindfold Step 1 gap closure, Session A", phase A3.

## 1. What was executed

| Command (WSL Ubuntu 24.04, system `python3`, `nice -n 19`, during an OD-3 run) | Input | Result |
|---|---|---|
| `python3 docs/work/proposals/power_from_pilot.py /home/dev_kaeem/exc4-evidence/runs-b.jsonl` | EXC-4b runs, SHA-256 `8f72b352…9288588`, the same as the recorded `runs.jsonl.sha256` | exit 0; tables in §3 |
| `python3 -I docs/work/proposals/power_typeI_check.py 400` | synthetic null laws only | exit 0, 7.4 s; table in §4 |

Script digests: `power_from_pilot.py` `4f3dbfb6…f3180536`; `power_typeI_check.py` `43d62c7c…88bb167f`.

## 2. The unit, re-derived by reading

- `analysis_v3.compare_paired_scores` takes arm → independent unit → repeated setting → a six-kind **total** score in
  [-6, 6]. Paired differences therefore lie in [-12, 12]: range R = 24 (`analysis_v3.py`, `SCORE_BOUND`).
- In `pilot_v3`, one campaign = six universes, one of each kind. `master_seed = HMAC(root, campaign, presentation,
  seed)` (`pilot_v3.py:91`), so every (campaign, presentation, seed) is a fresh world set. In the pilot, all 720
  universe ids per arm were distinct. **Unit = one campaign**, so n = 120 per arm in EXC-4b.
- Formal plan in code: `FORMAL_CAMPAIGNS = 30 × 4 presentations × 20 seeds = 2400` campaigns per arm
  (`pilot_v3.py:46`), i.e. n = 2400 independent units if seeds and presentations keep producing fresh worlds.
- **Correction to revision 2 of the session prompt draft (G1):** that draft assumed n = 30 units. The formal plan
  in code has n = 2400. The power gap is real but smaller than stated there; §3 replaces those numbers.

## 3. Observed spreads (EXC-4b, DEVELOPMENT_DESCRIPTIVE, n = 120 units per arm)

Mean six-kind totals: mind_full +3.562, grammar_enumeration +3.467, careful +3.083, space_filling +3.100,
bo_botorch_variance +2.433, pysr_symbolic +1.546. Paired differences of mind_full versus:

| Baseline | mean / unit | sd |
|---|---:|---:|
| grammar_enumeration | +0.096 | 1.015 |
| space_filling | +0.463 | 0.899 |
| careful | +0.479 | 0.922 |
| mind_no_adaptive_selection (ablation) | −0.033 | 0.777 |
| mind_no_belief_update (ablation) | +0.071 | 0.737 |
| mind_no_falsifier (ablation) | −0.017 | 0.250 |

The median paired sd over grammar's comparisons is 1.066. Two development observations follow, neither a claim:
(a) on the six-kind total the Mind is +0.096 per unit over grammar, while on discoverable alone it is behind
(0.292 vs 0.350); (b) none of the three Mind ablations moves the total by more than 0.07 per unit, so no Mind
capability shows a contribution yet (Genesis §19 ablation gate).

### Units needed to reject at α = 0.05 (one-sided), lift per unit, sd = 1.066, k = Holm family size

| lift / unit | k | Hoeffding (current) | empirical-Bernstein | normal approx. (80 % power, reference only) |
|---:|---:|---:|---:|---:|
| 0.25 | 1 | 13,805 | 1,234 | 113 |
| 0.25 | 3 | 18,867 | 1,601 | 161 |
| 0.25 | 20 | 27,609 | 2,236 | 243 |
| 0.50 | 1 | 3,452 | 550 | 29 |
| 0.50 | 3 | 4,717 | 714 | 41 |
| 0.50 | 20 | 6,903 | 996 | 61 |
| 1.00 | 3 | 1,180 | 329 | 11 |
| 1.00 | 20 | 1,726 | 459 | 16 |

The Hoeffding and empirical-Bernstein columns give the n at which an observed mean equal to the lift crosses the
bound (about 50 % power). The normal column is a large-sample 80 %-power reference and is **not** a finite-sample
guarantee.

**At the formal n = 2400 (arithmetic from the same formulas):** Hoeffding detects about 0.66 per unit (k = 1) to
0.85 (k = 20). Empirical-Bernstein detects about 0.18 (k = 3). The development gap of mind_full over grammar
(+0.096) is below both. A Mind that does not improve is correctly not certified; a real lift of roughly 0.2–0.5 per
unit is detectable only with a variance-adaptive bound.

## 4. Type-I check on synthetic null laws (E[D] = 0, the H0 boundary)

| Null law | n | Hoeffding | empirical-Bernstein | sign-flip randomization |
|---|---:|---:|---:|---:|
| symmetric two-point | 120 | 0.0000 | 0.0000 | 0.0500 |
| symmetric two-point | 480 | 0.0000 | 0.0000 | 0.0300 |
| skewed three-point | 120 | 0.0000 | 0.0000 | **0.1050** |
| skewed three-point | 480 | 0.0000 | 0.0000 | 0.0525 |
| pilot-like discrete | 120 | 0.0000 | 0.0000 | 0.0250 |
| pilot-like discrete | 480 | 0.0000 | 0.0000 | 0.0375 |

400 replicates per cell (standard error about 0.011 at 0.05). The sign-flip test is about twice the nominal rate
under a skewed mean-zero null, so it does not test H0: E[D] ≤ 0 (it tests symmetry about zero) and is **rejected as
a primary test**. Both bounds stay at or below α, as their theory says.

## 5. Options for D9

| Option | Change | Valid for H0: E[D] ≤ 0? | Detectable lift at n = 2400 | Cost |
|---|---|---|---|---|
| **A (recommended)** | Empirical-Bernstein bound (Maurer & Pontil 2009) on independent-unit paired totals; Holm over a **pre-declared** family of the strongest applicable baselines (proposed: grammar_enumeration, careful, space_filling); every other arm reported descriptively; per-kind non-inferiority on the control kinds (no loss allowed, P-1) as a separate gate | yes (finite-sample; i.i.d. units, bounded) | ≈ 0.18 / unit | formal plan as in code (≈ 50,400 campaigns for 21 arms) |
| B | Keep Hoeffding, raise n | yes | 0.25 / unit needs ≈ 19k–28k units | ~8–12× option A |
| C | Keep Hoeffding at n = 2400 | yes | ≈ 0.66–0.85 / unit | as in code; a modest real lift is invisible |
| rejected | sign-flip randomization | no (§4) | — | — |

Notes:
- Option A's pre-declared family must be fixed **before** any Mind evaluation and by a rule, not by looking at
  results. Proposed rule: the arms with the highest development six-kind total among non-Mind, non-floor arms in
  the two EXC-4 pilots. That uses only development data the Mind's formal worlds never touch. It is still a
  disclosed, data-informed choice.
- The i.i.d.-unit assumption requires fresh worlds for every (campaign, presentation, seed), which `master_seed`
  provides, and a stateless isolated proposer per campaign (gap G5).
- Step 1 itself tests nothing: it freezes the roster and reports baseline distributions. D9 freezes the **decision
  contract** Step 2 will use; that is why it must be decided now.

## 6. Cost note (ESTIMATE)

EXC-4b ran 2520 campaigns in 1079 s on 4 workers, in-process. 21 arms × 2400 campaigns ≈ 50,400 campaigns ≈ 6 h at the
same rate. Isolation overhead and the EXC-5 arm are UNMEASURED (phase A6 measures them).
