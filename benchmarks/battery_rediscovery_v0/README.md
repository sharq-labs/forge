# BR-BATT-REDISC-01: battery historical-rediscovery development pilot

Branch `research/battery-rediscovery-pilot-v0` (worktree `D:/forge-redisc`), base `origin/main` `12862b0b`. Local
only. This is a **development** experiment. It is not a formal Genesis run, a certification, a discovery claim,
evidence that D5 is closed, or a substitute for the formal campaign. Family-3a (`a6200e5c`,
`feat/genesis-lite-v03-clean-n1`) was not touched.

## 1. What is being asked

Two battery problems from earlier FORGE work are posed again, blinded, to the Minimal Mind and to four baselines:

| Problem | Data (pseudonymised in the pack) | Split, reused unchanged |
|---|---|---|
| P1 | three sibling cells, constant-current discharge then rest, ~19 s sampling | calibration: early cycles of cells A, B; within-cell held-out: their next cycles; cross-cell held-out: early cycles of cell C |
| P2 | one cell, HPPC pulses at 0.1 s plus a 1C discharge, measured OCV | calibration: pulses at two current levels; within-cell held-out: pulses at two other levels plus the 1C discharge; no second cell |

The questions are MODEL_ADEQUACY, IDENTIFIABILITY (R0, R1, C1 of the declared Thevenin 1RC), WITHIN_CELL_GENERALIZATION,
CROSS_CELL_TRANSFER, MODEL_DISCREPANCY, and CORRECT_REFUSAL across them. Every answer is SUPPORTED, NOT_SUPPORTED,
REVIEW, NOT_ASSESSABLE or REFUSED, and the last three never count as support.

## 2. Arms

- **MIND**: `engcore.mind.minimal`, copied byte-exact from `e2b8037c` (blob ids checked by a test; its own 27 tests
  pass on this base). It is run through a declared adapter, `candidate/mind_arm.py`:
  - a passive-pool world serves the nearest unused recorded sample within 0.05 ln and never interpolates;
  - a RELAXATION probe answers IDENTIFIABILITY;
  - one PREDICTION probe per held-out subset answers WITHIN and CROSS;
  - ADEQUACY and DISCREPANCY ask about a model family the Mind cannot represent, so they are NOT_ASSESSABLE by
    construction, and the Mind produces no R0/R1/C1.
- **FIXED_FIT**: fits the 1RC and judges held-out predictions against the declared bar. It runs no applicability,
  identifiability or residual check.
- **CAREFUL_BASELINE**: the same fit, plus the declared applicability rule and basic identifiability checks (bound,
  inflated Gauss-Newton sd, correlation, multistart agreement) and a residual-structure check.
- **ALWAYS_FIT** and **ALWAYS_REFUSE**.
- The strongest existing FORGE baseline is the historical preregistered pipeline. It is the source of the truth
  column, so it is not run as an arm: it would agree with history by construction.

## 3. Firewall, freeze, seal

1. `build_pack.py` reads only the pinned split DATA files. It pseudonymises every source identity and writes
   `evaluator/IDENTITY_MAP.json`, which is evaluator-only.
2. `freeze.py` writes `PLAN.json`, holding every rule, the scoring, the conclusion rule and the sha256 of every file.
   The plan is committed before any arm sees the real pack.
3. `sandbox_run.py` runs the arms under a Python audit hook that records every opened path and every loaded module.
4. `seal.py` re-checks the freeze, then runs the pre-seal leakage audit (`leakage.py`): an identity/verdict token scan
   of every candidate-visible file, a whitelist of pack keys, and a runtime path/module check. It writes `SEAL.json`,
   which is then committed.
5. `evaluator/truth.py` refuses to read any historical record unless the committed seal verifies. The post-seal audit
   repeats the scan with the historical parameter values.

## 4. Results (sealed run `e1be5910`, evaluated after the seal)

| Reading | Conclusion | Files |
|---|---|---|
| Preregistered (frozen audit) | **LEAKAGE_INVALIDATED** | `results/EVALUATION.{json,md}`, `results/LEAKAGE_POST_SEAL.json` (unchanged) |
| AMENDMENT_01 (post-seal, owner-requested, disclosed) | **REPRESENTATION_BOTTLENECK** | `results/AMENDMENT_01.json`, `results/EVALUATION_AMENDMENT_01.{json,md}`, `results/LEAKAGE_POST_SEAL_AMENDMENT_01.json` |

**Preregistered conclusion: LEAKAGE_INVALIDATED.** The trigger is an audit false positive.
- The post-seal numeric scan of P1's historical C1 = 760 F used the pattern `(?<![\d.])760(?![\d])`.
- In P2.json it matched one measured timestamp, `t = 760.006 s`, in the 1C discharge record (10 s sampling).
- The pattern excluded a following digit but not a following decimal point.
- That timestamp is raw data copied from the pinned split file. It is not a historical estimate, and it belongs to a
  different problem.
- Every other check passed:
  - the identity and verdict token scan;
  - the pack-key whitelist;
  - the runtime audit, for both the run and the replay: no path outside the declared roots, no evaluator or historical
    module, no identity token in the 181 platform files opened;
  - the 22 other value patterns.

**AMENDMENT_01.** At the owner's request, made after the seal and after the preregistered evaluation had been read:
- What changed:
  - `leakage.historical_value_tokens`: the lookahead is now `(?![\d.])`, so a match may not be followed by a decimal
    point either.
  - `run_evaluation --amendment` writes suffixed outputs.
  - The frozen-file test now admits exactly the files listed in `AMENDMENT_01.json`, each moving from its PLAN digest
    to its declared new digest. A new test pins that the amended pattern ignores `760.006` and still catches `760`.
- Rerun: only the post-seal audit and the evaluation. The amended audit is PASS on all 23 value patterns, with no
  static, schema or runtime finding.
- Unchanged: every candidate output and trace, the seal, the pre-seal audit, the truth mapping, the scoring, the
  conclusion rule, PLAN.json, and the three preregistered evaluation files (sha256 checked after the rerun).
- Known weakness: the scan matches only the exact 3- and 4-significant-digit form of each value. It now also misses
  such a form followed by a decimal point (e.g. `760.0`).
- The amendment was made knowing the amended conclusion it would produce (it is stated below). That makes it weaker
  evidence than a preregistered result. A clean confirmation needs a v0.1 plan frozen with the fixed audit and a fresh
  sealed run.

The scores below are identical in both readings. Only the conclusion differs.

| Arm | CORRECT | CORRECT_REFUSAL | FALSE_SUPPORT | FALSE_REFUSE | scored |
|---|---|---|---|---|---|
| MIND | 0 | 2 | 0 | 8 | 10 |
| FIXED_FIT | 3 | 1 | 6 | 0 | 10 |
| CAREFUL_BASELINE | 7 | 2 | 1 (P1 identifiability) | 0 | 10 |
| ALWAYS_FIT | 1 | 0 | 9 | 0 | 10 |
| ALWAYS_REFUSE | 0 | 2 | 0 | 8 | 10 |

**The Mind.**
- It ran end to end on both problems. Its dispositions are stable over seeds 0, 1 and 2.
- It sealed 207–278 pre-result predictions per probe and used 80 (P1) and 120 (P2) observations.
- Every answer it gave was non-committal: it never manufactured support.
- It answered nothing decisively, and 7 of its 10 non-committal answers have a representation or interface cause:
  - ADEQUACY and DISCREPANCY are not representable in its hypothesis space;
  - the P1 relaxation box is empty at ~19 s sampling;
  - SOC (P1) and the protocol's current level (P2) appear only as passive covariates, which the Mind reads as
    unidentifiable associations;
  - the P1 within-cell rivals were all set aside.
- The P2 relaxation law came out linear in ln t, so the Mind answered REVIEW where history found the parameters
  identifiable.

**Amended conclusion (AMENDMENT_01): REPRESENTATION_BOTTLENECK**, by the unchanged preregistered rule:
- the Mind's 2 correct answers are fewer than CAREFUL_BASELINE's 9;
- the trivial arms' best (2) is below 9, so the benchmark discriminates;
- 7 of the Mind's 10 scored answers are representation-caused, which is at least half.

**The baselines.**
- The independent fitter reproduces the historical estimates and held-out errors:
  - P1: R0 0.1317 Ω, R1 0.2258 Ω, C1 760 F; held-out RMSE 49.74 / 89.23 mV;
  - P2: R0 20.65 mΩ, R1 15.61 mΩ, τ 24.8 s; held-out pulses 12.55 mV, constant current 28.65 mV.
  - This agreement is consistency between implementations. It is not validation.
- CAREFUL_BASELINE's one false support is P1 identifiability. Its basic checks pass, but the forward-hold shift (16–29 %)
  and an OCV knot on its bound show the confounding that history's profile and hold diagnostics caught. The
  forward-hold shift is reported as a stability metric, but the CAREFUL decision does not use it.

**Replay:** 12/12 sealed outputs re-execute byte-identically, and 5/5 Mind traces replay VERIFIED from their recorded
observations.

Full tables: `results/EVALUATION.md` (preregistered) and `results/EVALUATION_AMENDMENT_01.md` (amended).
