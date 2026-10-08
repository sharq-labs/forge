# Local Assurance optimization pass 12 — safe Formal pytest-xdist

Base: 4f2cdf4b5c38b17bc3188967d15503d51b907bed. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No certificate, certificate child, push, PR or merge. Formal population, TARGETS, shard
count, V4 and the default (one worker) Formal command are unchanged.

## Design

- `local_assurance run --formal-pytest-workers N` (default 1, distinct from `--workers` and
  `--mutation-workers`) -> `tests/mutation_guards.py --pytest-workers N`. Default: the
  historical command and transcript, byte for byte in shape (`_formal_command`).
- N > 1: explicit `-p xdist.plugin --tx N*popen//python=<shard interpreter> -X utf8
  --dist loadfile --max-worker-restart=0 -p tools.certification.formal_xdist_guard`.
  `--tx` (not `-n`) gives every worker the serial process's `-X utf8` without a new
  PYTHON* variable; autoload stays disabled.
- `tools/certification/formal_xdist_guard.py` (schema /2) observes xdist's structured
  controller signals: node ready/down with or without error, synthetic crash reports
  (`when="???"`), internal errors, per-worker collections, per-process interpreter, UTF-8
  mode and import origins (rootdir, src/ and pytest `pythonpath` roots), and writes one
  sentinel in the shard's owned artifacts. `problems()` admits an attempt only with a
  complete, clean sentinel; otherwise `_run` raises WorkspaceError (infrastructure, no
  credit). The 0/1/2 exit rule still applies first; stale sentinels are unlinked.
- Grouping: `--dist loadfile` assigns files by timing, so in xdist mode
  - a per-shard named-alone control collects TARGETS serially on the unmutated copy, selects
    each named guard's functions with the verdict rule's own match, and runs EACH set alone
    (`_alone_argv`, no cache), checking the copy is pristine before each; any failure voids;
  - a would-be named kill is credited only if the identical `_alone_argv` command fails with
    the named guard in the mutated worker, which must equal the pristine tree plus the exact
    post-edit entry of the declared file; else `RED (NOT CONFIRMED SERIALLY)`, no credit;
  - import-refusal mutations (credited on refusal text anywhere) run serially, as before,
    against the historical serial control, which runs in shards that contain one.
- Mutations of `tools/` are refused in xdist mode (the guard is imported from the worker copy).

## Crash and infrastructure semantics (real runtime specs, tests/test_formal_xdist.py)

| Scenario | Plain xdist | Forge |
|---|---|---|
| SIGSEGV in the named guard | exit 1 + `FAILED` -> would credit RED | refused: infrastructure events |
| worker lost before the target | — | refused: pytest infrastructure exit 5 |
| worker exits mid-test (`os._exit(0)`) | — | refused: infrastructure events |
| workers collect different tests | — | refused: not one identical test universe |
| foreign import (root package / pythonpath root) | — | refused: imported from outside the worker |
| worker internal error | — | refused: exit 3 / events |
| failure that exists only under xdist | credited | admitted, not confirmed -> no credit |
| target writes into the worker | credited | not confirmed -> no credit |
| named guard fails alone unmutated (incl. two-guard union-green case) | credited | round void |
| genuine named failure | credited | admitted and confirmed |

## Correctness evidence (bounded; not certification)

- Real 48 TARGETS, unmutated: serial collect 1140 nodeids / 48 modules, sha256
  b89b2506...; both xdist workers reported the identical count and hash; per-nodeid JUnit
  outcomes serial vs xdist+guard: 0 differences (1139 passed, 1 skipped); every worker in
  UTF-8 mode on the shard interpreter with 728/732 project modules all inside the worker.
- Verdicts serial vs xdist identical on every bounded run: 4 (G1a G1d G2f G27b), 16 (all
  4 import refusals, 7 scoped edits, 9 guard modules) and a representative 32 (31 named +
  G1d); all controls GREEN; every xdist named kill confirmed alone; no residue.

## Benchmarks (mutation-workers=4, Formal group only, same machine, back to back)

| Workload | Serial | xdist n=2 (final design) |
|---|---|---|
| 4 shards x 1 mutation | 305.1 s | 361.9 s (fixed per-shard costs dominate) |
| 4 shards x 4 (25 % import refusals) | 770.6 s | 713.5 s (-7 %) |
| 4 shards x 8 (31 named + 1 import) | 1431.5 s | **1116.9 s (-22.0 %)** |

Per component (representative run): xdist attempt ~99 s vs serial ~157 s; confirmation
~2.5 s per kill; named-alone control ~17-25 s per shard; extra serial control ~168 s only
in a shard with an import refusal. Peak tree RSS 4.75 GB (18.9 GB free), mean CPU busy
35.6 % vs 22.7 %. MODEL only (not measured): a 71-mutation shard ~3.1 h serial vs ~2.1 h.

## Failed approaches recorded

- Plain xdist and `--max-worker-restart=0`: a crash is credited (refuted by spec).
- Guard v1 used `-n N`: workers lacked `-X utf8`; replaced by `--tx`.
- Confirmation from FAILED lines of the xdist run (review 1) and union named-alone proof
  (review 3) were insufficient; replaced by per-set identical-command control.
- `pytest.importorskip("execnet")` in a new spec turned every Formal CONTROL red via the
  dependency guard in TARGETS; run the full TARGETS before benchmarking test changes.
- `pkill -f probe_bench.py` matched the invoking shell and orphaned shards; they were
  stopped through their own SIGTERM drain, and read-only seeds needed `chmod -R u+w`.

## Reviews

Five independent read-only hostile reviews; each finding fixed or recorded. Final: PASS,
no credit path. Residual (documented, not changed): the serial transcript parser takes the
last `::` of a FAILED line; HOME/XDG caches are not sealed (serial too); xdist can credit a
kill that serial file order would mask (the guard fails alone with only the mutation), so a
shard can pass under xdist where serial would not — an owner design decision.
