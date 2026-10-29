# Genesis-lite v0.3 development pilot under a scarce budget (EXC-3), 2026-10-29

DEVELOPMENT_ONLY, DEVELOPMENT_DESCRIPTIVE. Not a formal campaign, not a benchmark result, not a rate, a ranking or a lift.
No statistics were computed. Not A2 evidence.

## Provenance: MIXED (read this first)

- **Started:** at `6f0bc58d` (clean /opt tree) on 2026-10-29 at 14:08:13 +03:00, with `--arms all --workers 4
  --deadline-seconds 2400 --budget-fractions 1.0,0.5,0.25` under `timeout 2700`. Exit 0; 1741.39 s; 7200 / 7200
  campaigns completed, 0 not run, 0 interrupted, 0 worker failures.
- **What changed mid-run:** at 14:22:54 a separate session (a fork of the session that ran this pilot) committed
  `56b33d42` to main, changing `benchmarks/genesis_lite/harness_v3.py`, `pilot_v3.py` and a test. At 14:22:55 it
  fast-forwarded the /opt tree to that commit. This session did not make that commit.
- **What was executed (inferred, not proven):** `6f0bc58d` code throughout. The same 4 worker processes ran every
  campaign (pids 2472/2475/2476/2477, each first seen at runs.jsonl lines 0-3, 0 worker failures). They imported
  `harness_v3` and `pilot_v3` once, at their first task, before the change, and Python does not re-import a loaded
  module. The commit changed no other module.
- **What was recorded:**
  - 3939 runs carry development identity `7d8b2e935c57…` (the `6f0bc58d` files).
  - 3261 runs carry `bc8c5eead863…`. `development_identity()` re-hashes the files on disk for every campaign, so these
    runs hash `56b33d42` files that they very likely did not execute.
  - `environment.json` records `git_head` `56b33d42…`, computed at the end of the run; it is not the code that ran.
- **Effect on results:** none is expected on scoring. `56b33d42` changes pseudonym keys below 1.0 and adds a
  per-universe cap check; the arms are stateless across campaigns and no run exceeded its cap (0 INVALID). The
  recorded provenance is nevertheless wrong for 3261 runs.
- **Owner decision (2026-10-29, in chat: "Accept with note"):** this run is accepted with the correction above, which
  binds its results to `6f0bc58d` as the inferred executed code; it was not re-run. EXC-3 is closed.

## Files

| File | Note |
|---|---|
| `summary.json` | the run's own summarizer (loaded at `6f0bc58d`); sha256 `3607e87b…` |
| `environment.json` | as written by the run; its `git_head` is the post-change HEAD (see above) |
| `runs.jsonl.sha256` | runs.jsonl (38.8 MB) is kept outside the repository at `/home/dev_kaeem/forge-mvp-20261028-evidence/pilot-v3-dev-scarce-2026-10-29/` |

## Design

- 20 arms × 10 campaigns × 4 presentations × 3 seeds, at each of three budget fractions on the same worlds: 2400
  campaigns per level and 120 paired world sets per level, all VALID at every level.
- Cap per universe = `min(budget, max(d + 2, floor(f × budget)))`. Realised mean cap / budget: 1.0 at 1.0, 0.5 at 0.5,
  **0.313 at 0.25** (the d + 2 floor).
- Every observing arm used its whole cap, every time: the observation counts are identical across arms at each level.
- The contrasts below are the pre-declared ones: a minus b, per universe, on universes where arm a's design leaves at
  least one selection query. "a ahead" and "b ahead" count universes.

## The pre-declared contrasts

**Mind: `mind_full` − `mind_no_adaptive_selection`** (design only)

| Level | n | a ahead | b ahead | mean difference |
|---|---|---|---|---|
| 0.25 | 333 | 24 | 22 | +0.008 |
| 0.5 | 491 | 22 | 39 | −0.037 |
| 1.0 | 720 | 28 | 40 | −0.020 |

No selection opportunity existed in 387 universes at 0.25 and 229 at 0.5. All of those were ties, as expected.

**`bo_botorch_variance` − `space_filling`** (design and analysis confounded)

| Level | n | a ahead | b ahead | mean difference |
|---|---|---|---|---|
| 0.25 | 242 | 10 | 54 | −0.203 |
| 0.5 | 491 | 25 | 80 | −0.139 |
| 1.0 | 582 | 17 | 84 | −0.143 |

On universes where BO had no selection query (budget 12 at 1.0, n = 138), BO was ahead: 26 vs 16, +0.101.

## Paired mean credit (DEVELOPMENT_DESCRIPTIVE)

| Arm | 0.25 | 0.5 | 1.0 |
|---|---|---|---|
| mind_no_belief_update | 2.467 | 2.929 | 3.333 |
| mind_no_falsifier | 2.442 | 2.904 | 3.400 |
| mind_full | 2.421 | 2.850 | 3.375 |
| mind_no_adaptive_selection | 2.400 | 3.000 | 3.496 |
| space_filling | 2.150 | 2.775 | 3.096 |
| careful | 2.104 | 2.733 | 3.100 |
| bo_botorch_variance | 1.742 | 2.208 | 2.521 |
| pysindy_stlsq | 1.658 | 1.867 | 2.025 |
| always_insufficient | 1.500 | 1.500 | 1.500 |
| pysr_symbolic | 1.496 | 1.517 | 1.692 |

## Observations (descriptive; not established causes)

1. **The Mind's adaptive experiment selection was not ahead of its own fixed space-filling design at any level.** Where
   it could select, it was even at 0.25 and behind at 0.5 and 1.0.
2. **BoTorch's posterior-sd selection was behind space_filling at every level where it selected.** It was ahead where it
   could not select, so the handicap appears with selection, not with its analysis. This is a hypothesis: the contrast
   is confounded.
3. **The Mind variants stay above the baselines at every level.** The lead comes from the shared analysis and
   conclusion rules, as in EXC-2.
4. **With scarce data the Mind more often answers `no_law` on worlds that do have a dependence or are not no_solution
   worlds:** 51 universes at 0.25, against 12 at 0.5 and 5 at 1.0. careful and space_filling answer `no_law` on such
   worlds 21-40 times at each level. A low-data `no_dependence` conclusion is a risk to examine. It is not to be tuned
   on these results.
5. **Threads:** 17 of 7200 runs recorded 20 BLAS threads (2 workers). The cause is not established.

The answer mapping, the Mind and the credit table were frozen before this run and must not be tuned on it.
