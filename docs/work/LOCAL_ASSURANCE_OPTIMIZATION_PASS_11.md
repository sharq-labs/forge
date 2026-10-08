# Local Assurance optimization pass 11 — Formal hot-path audit

Source: 4f2cdf4b5c38b17bc3188967d15503d51b907bed (committed Passes 2–9). No source change in
this pass; the candidate below was benchmarked through an out-of-tree wrapper only.
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN. No certificate, commit, push, PR or merge.

## Profile of one Formal attempt (exact production TARGETS command, production workspace/env)

Serial unmutated run: wall 141.2 s; pytest 135.7 s; JUnit test time 130.4 s (call 122.6 s,
setup 7.5 s, teardown ~0); collection-only wall 6.2 s (5.65 s pytest-reported, ~4.2 %).
1140 nodeids. 4 of 48 modules carry 80 % of test time:

| Module | Tests | Time | Share | Dominant cost |
|---|---|---|---|---|
| tests/inference/test_grid_resolution_repair.py | 32 | 49.2 s | 37.7 % | two ~19 s grid/posterior tests + 7 s module-scoped fixtures |
| tests/test_core_guards.py | 265 | 29.7 s | 22.8 % | source/dependency scans (~5 s each) |
| tests/test_core_semantic_invariants.py | 112 | 21.2 s | 16.3 % | one 19 s nested-exemption test |
| tests/hybrid_uq/test_hybrid_uq_router.py | 26 | 18.8 s | 14.4 % | grid rebuild routes (~7.5 s each) |
| next 44 modules | 705 | 11.5 s | 8.8 % | — |

All of it imports and executes the mutated `engcore` tree, so it is MUST_REPEAT per mutation.
No SAFE_TO_SHARE_READONLY work of material size was found. Expensive fixtures are already
module-scoped and compute through mutated code: no safe fixture-scope change.

## Why CPU is idle

Measured with an external /proc sampler: one serial attempt uses 1.20 cores (one CPU-bound
Python thread under the GIL plus ~0.2 core of OpenBLAS threads); system busy 6 % on 20 CPUs.
Disk reads ~0 (page cache), subprocesses ~1 s per attempt (3 Python children), no sleeps, no
network, no pools. Four shards therefore occupy ~4.8 cores (~22 %): Formal is single-thread
CPU bound per shard. OpenBLAS starts 20 threads per process (threadpoolctl); peak 48–49
threads per pytest process. Per-attempt time rises from ~136 s alone to ~150–155 s at
mutation-workers=4 (+11–14 %); capping BLAS threads could recover at most that, changes the
numerical environment, and stays below the 15 % threshold: not recommended.

## Inner pytest-xdist (explicit `-p xdist.plugin`, autoload stays disabled)

Single unmutated attempt: serial 141.2 s; n=2 loadfile 84.5 s; n=4 loadfile 62.0 s;
n=4 loadscope 61.8 s; n=4 load 77.4 s. Every xdist control: 1140 nodeids, 0 per-nodeid
outcome differences from serial. loadfile is bounded below by the 49 s grid module.
Mutated-source visibility: with a marker appended to the worker `src/engcore/__init__.py` and
a diagnostic plugin, all four xdist workers imported `engcore` from the worker tree with the
marker; 664 engcore modules, none outside the worker cwd; rootdir = worker.
G1d (import refusal): serial and xdist both RED by the production rule (failed counts equal;
collection-error counts are multiplied per worker, 14 -> 56, in indented summary lines that
`parse_log` never reads).

**Infrastructure semantics differ without a guard.** A test that segfaults kills serial pytest
(exit -11 -> WorkspaceError, no credit). Under xdist the same crash becomes exit 1 with
`FAILED <nodeid>` and the production Formal rule credits RED — also with
`--max-worker-restart=0`. Plain xdist is therefore REJECTED. xdist always prints
`[gwN] node down: ...` and `worker 'gwN' crashed while running ...`; refusing the round on
those markers restored the serial semantics in a demonstration (plain xdist: credited RED;
candidate: refused as infrastructure).

## Candidate (not applied to source)

Formal flags + `-p xdist.plugin -n N --dist loadfile --max-worker-restart=0`, and Formal `_run`
raising WorkspaceError when its output matches
`\[gw\d+\] node down: |worker 'gw\d+' crashed while running |maximum crashed workers reached`.
Bounded benchmark (Pass 10 Formal workload: G1a, G1d, G2f, G27b, 4 shards, full controls,
mutation-workers=4, committed source in a clean clone), order baseline, n4, n2, baseline:

| Run | Formal wall | Mean CPU busy | Peak tree RSS | Verdicts / controls |
|---|---|---|---|---|
| baseline | 315.1 / 308.6 s | 22 % | 3.1 GB | 4 RED / 4 GREEN |
| candidate n=2 | 207.7 s (−33 %) | 40 % | 4.7 GB | identical / GREEN |
| candidate n=4 | 187.2 s (−40 %) | 63 % | 6.4 GB | identical / GREEN |

Before production use it needs: the crash refusal in `tests/mutation_guards.py::_run`, a pinned
spec that runs a REAL worker crash through the production command (so an xdist message change
fails closed in tests), the Pass 7 plugin policy amended to admit exactly `xdist.plugin`,
`forge-scientific-review`, and an owner certification decision (Formal invocation is
certification-controlled). Residual: cross-module process sharing differs from serial; the
control equivalence and four mutations do not prove all 284 verdicts are distribution-invariant.

## Other questions

- Controls: one per shard, ~150–155 s at mutation-workers=4, ~1.4 % of a 71-mutation shard.
  Identical TARGETS, same commit and copy function, same interpreter/env except shard paths.
  Each proves its own shard copy and environment are green. Sharing one control would need
  equal manifest digests across shards; saving <= ~1.4 %: not pursued (UNPROVEN, immaterial).
- Collection 4.2 % of an attempt and must re-import mutated code: not worth optimizing.
- Filesystem: scratch already on native ext4; disk reads ~0, workspace overhead ~1–2 %:
  tmpfs/reflink cannot be material.
- Shard count (analysis): 4 shards x 71, historical 104–159 s per mutation, 2.65–2.72 h per
  shard (2.9 % imbalance). 6 or 8 shards help only with 6 or 8 workers (1.83 h / 1.40 h
  modelled); at 4 workers 6 shards are slower (3.59 h). Not implemented.
- Per-mutation targets (analysis): 279 of 284 named guards resolve statically to one module;
  a minimal-module model needs 1.33 h instead of 10.78 h serial-equivalent (−88 %). It would
  drop the documented intent behind broad TARGETS and the import-refusal surfaces; it needs a
  separate certification decision. Not implemented.
- Fresh pytest process per attempt remains required; xdist workers are fresh per attempt.
