# Genesis-lite v0.3 development cost pilot, 2026-10-28

DEVELOPMENT_ONLY, COST_MEASUREMENT_ONLY. Not a formal campaign, not a benchmark result, not a rate or a lift.

## What ran

- Code: `5daaba81` (clean tree), `benchmarks.genesis_lite.pilot_v3 --arms all --workers 4` on WSL2 Ubuntu 24.04,
  Python 3.12.3, 20 CPUs, inside a 30-minute hard cap (owner-approved).
- 16 arms (13 v0.2 arms + PySR, PySINDy, BoTorch development baselines), 10 campaigns x 4 presentations x 3 seeds,
  world sets paired across arms; all proposers ran `in_process`.
- 1920 / 1920 campaigns completed and VALID in 675.68 s; 0 evaluator disagreements, 0 library failures.
- Raw runs: `runs.jsonl` (7.7 MB) kept outside the repository; its sha256 is in `runs.jsonl.sha256`.

## Files

| File | Produced by | Note |
|---|---|---|
| `environment.json` | the run (`5daaba81`) | `worker_thread_limits` were *requested*; see the thread caveat |
| `summary.json` | the run's own summarizer (`5daaba81`, pre-fix) | kept as produced |
| `summary_resummarized.json` | `pilot_v3.resummarize` at `ef0cc2f0` from the same `runs.jsonl` | binds the runs.jsonl, original summary, run and summarizer identities in `resummarized_from` |

## Caveats

- **Threads (review round 3, I-1, confirmed by execution):** at `5daaba81` the thread limits were set only in the worker
  initializer, after numpy had been imported; a reproduction measured **20 BLAS threads per worker** (torch 1). The
  per-campaign walls, and therefore the cost estimate, were measured under that oversubscription. Fixed in `ea894e61`
  (limits set in the parent before the pool: 1 BLAS thread). Not re-measured.
- **Estimate scope:** the 3.67 h figure (2400 campaigns per arm, 4 workers) covers these baseline arms only, in-process.
  The Minimal Mind arm and proposer-process isolation overhead are UNMEASURED. Walls were measured inside one of 4
  concurrent workers, not single-worker.
- **Memory:** `ru_maxrss` is a whole-life high-water mark of each pooled worker (about 1191 MiB), not a per-arm figure.
- **Credit:** reported only as DEVELOPMENT_DESCRIPTIVE paired means; not a rate, a ranking or a lift.
- The development identity `3f385361...` recorded on every run did not yet include `pilot_v3.py` (added in `ea894e61`).
