# Genesis-lite v0.3 development pilot with the Minimal Mind arms (EXC-2), 2026-10-29

DEVELOPMENT_ONLY, COST_MEASUREMENT_ONLY. Not a formal campaign, not a benchmark result, not a rate, a ranking or a lift,
and not A2 evidence (A1 PASS has not happened; EXC-2 forbids any A2, lift or superiority claim).

## What ran

- Code: `992deeba` (clean tree), `benchmarks.genesis_lite.pilot_v3 --arms all --workers 4` on WSL2 Ubuntu 24.04,
  Python 3.12.3, inside a 30-minute hard cap (owner-approved under EXC-2).
- 20 arms: 13 v0.2 arms, the PySR / PySINDy / BoTorch development baselines, and the Minimal Mind (MIND_VERSION 1.0.0,
  unchanged) with its three ablations, through `benchmarks/genesis_lite/mind_arm_v3.py`. 10 campaigns x 4 presentations
  x 3 seeds per arm, world sets paired across arms, all proposers `in_process`.
- 2400 / 2400 campaigns completed and VALID in 990.6 s; 120 paired world sets; 0 evaluator disagreements, 0
  inadmissible universes, 0 library or adapter failures, 0 Mind model refusals.
- One development identity on every run: `86893cff4a75…` (binds the v0.2 preregistration, the v0.3 files, `escrow_v3.py`
  and the Mind's engcore import closure: 191 substrate files with escrow_v3). Mind arms were submitted as `candidate` (full, 120) and `ablation`
  (360); the other arms as `baseline` (1920).
- Raw runs: `runs.jsonl` (11.3 MB) kept outside the repository at
  `/home/dev_kaeem/forge-mvp-20261028-evidence/pilot-v3-dev-mind-2026-10-29/`; its sha256 is in `runs.jsonl.sha256`.

## Files

| File | Produced by | Note |
|---|---|---|
| `environment.json` | the run (`992deeba`) | requested thread limits; see the thread caveat |
| `summary.json` | the run's own summarizer (`992deeba`) | kept as produced; sha256 `3c57d475…` |

## Descriptive observations (paired world sets, DEVELOPMENT_DESCRIPTIVE)

| Arm | paired mean credit | clean wall s / campaign |
|---|---|---|
| mind_no_falsifier | 3.600 | 2.21 |
| mind_no_belief_update | 3.575 | 2.54 |
| mind_no_adaptive_selection | 3.5625 | 2.32 |
| mind_full | 3.550 | 2.62 |
| careful | 3.2875 | 0.08 |
| space_filling | 3.2333 | 0.08 |
| bo_botorch_variance | 2.2917 | 16.89 |
| pysindy_stlsq | 1.9167 | 0.10 |
| pysr_symbolic | 1.5125 | 4.54 |

- The four Mind arms lie within 0.05 of one another, and the full Mind is the lowest of the four. **This pilot shows no
  contribution from adaptive selection, belief update or the falsifier.** No statistics were run; n = 120 campaigns per
  arm.
- Where the Mind arms differ from careful / space_filling is mostly in the confounded worlds (mind_full 105/120 answered
  `confounded`) and in refusals. On discoverable worlds mind_full recovered the law in 26/120 universes and answered
  `insufficient_evidence` in 92. On indistinguishable worlds it answered `insufficient_evidence` in 118/120 and never
  named a correct pair.
- **Experiment selection did not save queries.** Per-universe observation counts are identical for mind_full,
  mind_no_adaptive_selection and careful (min 12, mean 34.64, max 60, i.e. the whole budget). The Mind's early stop
  never fired here.

## Caveats

- **Threads:** 43 of 2400 runs recorded 20 BLAS threads in force, not 1. All were in 2 of the 4 workers, early in the
  run (runs.jsonl lines 32-89), spread across every arm (2-4 runs each). The remaining 2357 runs had 1. The cause is not
  established; a likely suspect is the juliacall/PySR import (stderr warns that torch was imported before juliacall).
  Not re-measured.
- **Estimate scope:** the 5.36 h figure (2400 campaigns per arm, 4 workers) covers the arms planned here, in-process.
  Proposer-process isolation overhead is UNMEASURED. Walls were measured inside one of 4 concurrent workers.
- **Memory:** `ru_maxrss` is a whole-life high-water mark of each pooled worker (about 1203 MiB), not a per-arm figure.
- **Agreement scope:** the escrow and the v0.3 evaluator share the pair/fraction rule text (escrow_v3), so 0
  disagreements check the interpreter and the plumbing, not the rule semantics.
- The answer mapping was frozen before this run (EXC-2) and must not be tuned on these results.
