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

## 4. Results

(filled in after the sealed run; see `results/EVALUATION.md`)
