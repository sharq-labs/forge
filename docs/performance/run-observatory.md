---
ai_schema_version: 1
doc_id: FORGE-RUN-OBSERVATORY-V1
doc_kind: POLICY_GUIDE
doc_status: ACTIVE
authority_scope: NONE
source_ref: not-applicable
evidence_level: NOT_EVIDENCE
last_reviewed: 2026-10-22
supersedes: none
---

# FORGE Run Observatory v1 — the universal run ledger

> **Developer and performance infrastructure. Not scientific evidence, not certification.** A receipt
> records what ran, on which code and machine, what it cost and how it ended. It issues no scientific
> verdict, and nothing in FORGE reads a receipt to decide one. It grants no execution authority:
> `docs/work/ACTIVE_PLAN.md` remains the only work queue, and `docs/project/PERFORMANCE.md` still owns
> how performance is measured, labelled and claimed. A number taken from a receipt is `MEASURED` only in
> that policy's sense (command, SHA, environment and date are in the receipt) and only for that machine.

Code: `tools/run_observatory/`. Tests: `tests/test_run_observatory.py`, `tests/test_run_observatory_process.py`.

## 1. Purpose

One wrapper composes around any existing command (pytest tiers, benchmarks, replays, solvers, data
pipelines) without replacing it, and leaves an immutable, queryable record:

```bash
python -m tools.run_observatory run --kind BENCHMARK --name k2 -- python path/to/benchmark.py
```

The child is started from an argument list (no shell string is ever rebuilt), its stdout/stderr pass
through to the terminal, and the wrapper exits with the child's exit code.

## 2. The non-authority boundary

The observatory may say only these things:

| Axis | Readings |
|---|---|
| run result | `RUN_PASS`, `RUN_FAIL`, `RUN_ERROR`, `RUN_INTERRUPTED` |
| performance | `PERFORMANCE_IMPROVED`, `UNCHANGED`, `PERFORMANCE_REGRESSION`, `NOT_ENOUGH_REPEATS`, `NOT_COMPARABLE` |
| replay | `REPLAY_EXACT`, `REPLAY_MISMATCH`, `NOT_CHECKED` |
| failure set | `NO_NEW_FAILURES`, `NEW_FAILURES`, `NOT_CHECKED` |
| comparability | `EXACT_COMPARABLE`, `CONFIG_VARIANT`, `CODE_VARIANT`, `ENVIRONMENT_VARIANT`, `WORKLOAD_VARIANT`, `NOT_COMPARABLE` |

`SUPPORTED`, `REFUSED`, `MODEL_ADEQUATE`, `DISCOVERY_CONFIRMED` and the other scientific verdicts belong
to FORGE's scientific authorities; a test holds the observatory's vocabularies disjoint from them, and
another holds that the package imports nothing from `engcore`. One collision is deliberate and narrow:
each *metric* carries a capability label `SUPPORTED` / `PARTIAL` / `UNSUPPORTED` saying whether the
platform could measure it. That label describes the measurement, never anything the number is about.

`RUN_PASS` means exit code 0 under the adapter's exit-code contract. It is not "GREEN": a failing exit
is always `RUN_FAIL` or `RUN_ERROR`, and `NO_NEW_FAILURES` is reported only after an actual comparison of
two collected failure sets.

## 3. Run kinds

`TEST`, `FAST`, `SCIENTIFIC`, `REPLAY`, `BENCHMARK`, `SOLVER`, `PROVIDER`, `DATA_PIPELINE`, `CAMPAIGN`,
`FORMAL`, `CERTIFICATION`, `UTILITY` (default; `TEST` with `--adapter pytest`). The kind is a label for
querying. Recording a `CERTIFICATION` run certifies nothing.

## 4. Receipt schema (`forge.run_observatory.receipt/v1`)

| Section | Content |
|---|---|
| `run_id` | `<UTC yyyymmddThhmmssZ>-<16 hex random>`: sortable, unique, never the timestamp alone |
| `run_kind`, `name`, `tags` | caller labels |
| `parent` | `parent_run_id`, `replay_of`, `comparison_group` |
| `git` | repository root, branch, exact `head_sha`, `tree_id`, `tree_clean` / `TREE_CLEAN`, `uncommitted_diff_sha256`, `untracked_sha256`, `code_identity` |
| `workload` | `workload_id`, its four component digests and their readable inputs (§5) |
| `environment` | `environment_id` and the facts it hashes (§6) |
| `command` | redacted argv, adapter-added arguments, resolved executable and its SHA-256, cwd, `shell: false` |
| `timing` | UTC start/end stamps, monotonic `wall_seconds`, the process-tree CPU record |
| `resources` | one record per metric: `value`, `support`, `method`, `scope`, `unit`, `note` (§8) |
| `counters` | declared / child-reported / adapter counters, derived rates, rejected names, conflicts (§9) |
| `outputs` | stdout/stderr raw SHA-256 and size, stored redacted log path and SHA-256, redaction count; declared artifacts by SHA-256 |
| `result` | status, exit code, raw return code, `terminated_by_signal`, adapter outcomes, notes |
| `comparison` | baseline, class, differing axes, deltas, performance reading, noise band, both runs' host load, policy, result delta, failure set (§7) |
| `host_load` | machine-wide CPU busy fraction, cores busy outside the run, available memory: context only (§7) |
| `replay` | declared and expected output/trace identities, `EXACT` / `MISMATCH` / `NOT_CHECKED` |
| `cost` | `NOT_AVAILABLE` by default; caller-declared amounts are always `ESTIMATED` (no billing source exists in v1) |
| `partial` | true for interrupted and recovered runs |
| `integrity` | `sha256` over the canonical JSON (sorted keys, compact, ASCII) of everything else, including `sealed_by` (`RUNNER` / `RECOVERY`) |

Large outputs are never embedded: logs and artifacts are referenced by path and SHA-256. A sealed
receipt is written once (hard-link publish, never over an existing file) and marked read-only. Editing
it breaks its seal (`INTEGRITY_FAILED`); editing *and* re-sealing it is caught by the digest the SQLite
index kept (`LEDGER_MISMATCH`).

## 5. Workload identity

`WORKLOAD_ID` is the SHA-256 of four component digests:

- `command`: adapter, program name (no directory, no `.exe`), arguments, working directory;
- `inputs`: content of every `--input` (a file, or a directory as a manifest of relative path + SHA-256);
- `declared`: `--declare KEY=VALUE` identities (benchmark PLAN id, provider/model version);
- `config`: content of every `--config`, `--seed` values, and the SHA-256 of the values of
  `PYTHONHASHSEED`, `PYTHONOPTIMIZE`, the BLAS/OpenMP thread counts, and any `--workload-env NAME`.

Paths under the repository or the run root are written as `{repo}/...` / `{run_root}/...`, so the same
workload has the same id in any checkout or worktree. Adapter report arguments (pytest's `--junitxml`)
are not workload. Secret values never enter it; a secret-named `--workload-env` is refused. For a very
large dataset, pass a manifest file as the `--input`: the manifest's content then binds the dataset.

## 6. Environment identity

`ENVIRONMENT_ID` hashes: OS name/release/build, architecture, Python implementation/version/compiler,
the observing interpreter's installed distributions (name==version digest), a salted host id, CPU model,
logical and physical cores, total RAM, GPU models (`nvidia-smi` only, else `UNSUPPORTED`), container/WSL/
virtualenv flags, and the SHA-256 of the child's resolved executable. The hostname appears only as
`sha256(salt + hostname)[:16]` with a random salt kept in the run root: pseudonymous, not anonymous. No
environment variable value, path list or credential is part of it.

Probing these facts costs ~0.3 s (distribution list, WMI on Windows, `nvidia-smi`), so they are cached
in `<run-root>/cache/`. An entry is reused only while its key is unchanged — interpreter path, version and
prefix, every site-packages directory's mtime (a package installed or removed), boot time to the minute
(a reboot, so an OS or hardware change), host, salt, the child executable's path/size/mtime and whether
`psutil` is available — and never after 24 h, which bounds what the key cannot see (a GPU driver updated
without a reboot). Cached and probed facts are byte-identical, so the `ENVIRONMENT_ID` does not depend
on the cache; each receipt says which it used (`environment.facts_source`: `CACHE` / `PROBED`).
`--refresh-env-cache` probes and rewrites the entry; `--no-env-cache` probes without it.

## 7. Comparability, deltas and the performance policy

| Class | When | Deltas | Performance reading |
|---|---|---|---|
| `EXACT_COMPARABLE` | same workload, environment and code identity | yes, `benchmark_speedup: true` | per policy |
| `CODE_VARIANT` | same workload and environment, different code | yes, each labelled `CODE_VARIANT` | per policy |
| `ENVIRONMENT_VARIANT` | same workload, different machine/interpreter | none | `NOT_COMPARABLE` |
| `CONFIG_VARIANT` | same command/inputs/declared, different config or seed | none | `NOT_COMPARABLE` |
| `WORKLOAD_VARIANT` | different command, inputs or declared identity | none | `NOT_COMPARABLE` |
| `NOT_COMPARABLE` | a partial run, or an unknown git identity | none | `NOT_COMPARABLE` |

A dirty tree's `code_identity` binds its diff and untracked files, so a dirty run is never exact with a
clean one. Every percentage carries its class. After each run the ledger picks a baseline: the latest
earlier run with the same workload, environment and code; else same workload and environment; else same
workload; else the same `--group` (or `--name`), so a changed workload is reported as a variant instead
of having no baseline. `--baseline none|RUN_ID` overrides.

Policy `forge.run_observatory.performance_policy` is versioned and recorded in every reading, with
any overrides (`--policy FILE`, `--policy-version`, `--regression-threshold-pct`,
`--improvement-threshold-pct`, `--min-absolute-seconds`, `--noise-min-history`,
`--noise-history-window`, `--noise-margin-pct`).

- **v1:** wall time must move by at least 25 % **and** 1.0 s against the single baseline run. The bars
  sit above the measured whole-run noise of identical warm FAST runs (up to x1.25, `docs/TESTING.md`).
- **v2 (default):** the v1 bars, **and** the candidate must leave the *noise band*: the last 10
  completed runs exactly comparable to the baseline (same workload, environment and code, same status,
  started before the candidate; the baseline included). A regression must be slower than the slowest
  of them by 5 %, an improvement faster than the fastest by 5 %; inside the band the reading is
  `UNCHANGED`. With fewer than 3 such runs there is no band, and a change that clears the bars reads
  `NOT_ENOUGH_REPEATS`: repeat the baseline before reading the delta. The receipt's
  `comparison.noise` holds the band (runs, min/max/median, spread, candidate vs median, `within_band`).

Why v2: on a loaded machine, two consecutive runs of identical code took 7.53 s and 9.49 s
(+25.9 %, +1.95 s) and v1 read `PERFORMANCE_REGRESSION`. Under v2 the same pair reads `UNCHANGED`:
9.49 s lies inside the band of five earlier identical runs (7.53–10.10 s). A real change on that
machine (−55.4 %, below the whole band) still reads `PERFORMANCE_IMPROVED`.

Result changes (status, exit code, outcome counts) are reported separately as `result_delta`.

**Machine load is context, never a reading.** Each receipt has `host_load`: system-wide CPU busy
time across the run window minus the run's own process tree (`other_busy_cores`), the machine's busy
fraction, and available memory at start (`psutil`, `GetSystemTimes` on Windows or `/proc/stat`;
`PARTIAL`, because it is two snapshots of machine-wide counters). It explains a slow run; it is never
attributed to the run and never changes a reading. `comparison.host_load` puts both runs' values side
by side.

## 8. Metrics and their limits

| Metric | Windows | Linux / macOS | Without psutil |
|---|---|---|---|
| `cpu_seconds` (user+system) | Job Object, whole tree incl. exited descendants: `SUPPORTED` | `getrusage(RUSAGE_CHILDREN)` delta: `PARTIAL` (orphans re-parented to init are lost) | same |
| `peak_rss_bytes` | max(sampled tree RSS sum, direct child peak working set): `PARTIAL` | max(sampled tree sum, largest single reaped descendant): `PARTIAL` | single-process peak only |
| `avg_rss_bytes` | sampled tree sum: `PARTIAL` | sampled: `PARTIAL` | `UNSUPPORTED` |
| `peak_tree_commit_bytes` | Job Object peak commit (not RSS): `SUPPORTED` | `UNSUPPORTED` | same |
| `io_read_bytes` / `io_write_bytes` | Job Object transfer bytes, all I/O incl. pipes: `SUPPORTED` | 512-byte block I/O of reaped descendants: `PARTIAL` | same |
| `process_count` | Job Object total: `SUPPORTED` | distinct sampled pids: `PARTIAL` | `UNSUPPORTED` on POSIX |
| `network_bytes`, `gpu_utilization` | `UNSUPPORTED` | `UNSUPPORTED` | `UNSUPPORTED` |

`UNSUPPORTED` always carries `value: null`, never zero. The Job Object sets no limit and allows
breakaway, so the child behaves as it would unobserved; a descendant that breaks away is not counted.
The job is attached right after process creation; a child cannot spawn anything in that window in
practice, but it is not formally excluded. Sampling (default every 0.1 s, `--sample-interval`) can miss
short spikes. `psutil` is optional (the `[benchmarks]` extra).

Timing: `wall_seconds` is `time.perf_counter_ns` (monotonic) from just before process creation to the
child's exit; the UTC stamps are labels and are never subtracted.

## 9. Counters and efficiency hooks

Counters are explicit, never scraped from log text. Sources, in increasing precedence: `--counter
NAME=N` (`DECLARED`), the child's report file (`CHILD_REPORTED`: the observatory sets
`FORGE_RUN_REPORT_FILE`; the child may write `{"counters": {...}, "output_identity": ..., "trace_identity": ...}`
there), and the adapter (`ADAPTER:PYTEST`). Conflicts are recorded.

- Throughput: `tests`, `cases`, `experiments`, `solver_calls`, `cards`, `records`, `bytes_processed`
  → `<name>_per_second`, `GB_per_second`, derived only when the counter exists.
- Data efficiency (MegaCorpus hook): `dataset_available_bytes`, `dataset_read_bytes`,
  `derived_bytes_written`, `evidence_bytes`, `cache_bytes` → `data_fraction_read`, and
  `bytes_per_decision` when `decisions` is declared. No filesystem interception in v1.
- Scientific efficiency (future Mind / benchmark adapters): `hypotheses_proposed`,
  `hypotheses_falsified`, `experiments_requested`, `experiments_executed`, `solver_calls`,
  `evidence_records`, `decisions`. Typed and recorded only; nothing in the Mind is wired to them.
- Anything else must be named `custom.<name>`; an undeclared name is refused (CLI) or rejected and
  listed (child report).

The child also receives `FORGE_RUN_ID` and `FORGE_RUN_ARTIFACTS_DIR`. These three variables are the only
change to its environment.

## 10. Adapters

- `GENERIC_COMMAND` (default): exit 0 → `RUN_PASS`, other → `RUN_FAIL`, killed by a signal (POSIX) →
  `RUN_ERROR` with `terminated_by_signal`, Windows `STATUS_CONTROL_C_EXIT` → `RUN_INTERRUPTED`. On
  Windows a process killed by `TerminateProcess` is indistinguishable from one that exited with that code.
- `PYTEST` (`--adapter pytest`): pytest's exit contract (0 pass, 1 fail, 2 interrupted, 3/4 error, 5 no
  tests collected → fail), outcomes from pytest's own JUnit XML (`--junitxml` is appended into the run's
  artifacts unless the command already has one): passed, failed, errors, skipped, xfailed, the failure
  set (`classname::name`), `tests` counter. `xpassed` is `UNSUPPORTED`: JUnit records a non-strict xpass
  as a pass.
- `FORGE_REPLAY`: not implemented in v1. Replay runs use the generic replay fields: `--replay-of RUN_ID`
  with `--output-identity` / `--trace-identity` (or the child report file). The observatory compares the
  identities the domain supplies; what counts as an equivalent replay stays with the domain.

A v2 adapter subclasses `GenericCommand` in `tools/run_observatory/adapters.py`, overrides `prepare`
(report-only arguments), `classify` (exit contract and structured outcomes) and `counters`, and is
registered in `ADAPTERS`. It may never alter what the command computes.

## 11. Storage and concurrency

```text
<run-root>/            --run-root, else $FORGE_RUN_ROOT, else ~/.forge-run-ledger
    ledger.sqlite      index (WAL); rebuildable from receipts/ with `reindex`
    host_salt          random salt for the host id
    cache/             environment-facts cache (§6); safe to delete
    receipts/          <run_id>.json sealed, read-only; <run_id>.pending.json while running
    receipts/quarantine/   unreadable pending files
    logs/              <run_id>.stdout.log / .stderr.log, redacted
    artifacts/<run_id>/    junit.xml, report.json
    summaries/         <run_id>.txt
```

The run root is refused inside the observed repository. It is safe to delete: nothing in FORGE reads it.
Receipts are the canonical records; SQLite is the searchable index. Writes are single `BEGIN IMMEDIATE`
transactions with a 30 s busy timeout and retry, so simultaneous completions serialize; receipt files
have unique names and are published by hard link. SQLite WAL needs a local filesystem (not a network
share).

Crash safety: a pending receipt exists from just before the child starts. Ctrl+C (SIGINT, SIGTERM, or
Ctrl+Break on Windows) gives the child `--grace-seconds` (default 10) to finish, then stops its tree
(Job Object termination on Windows, kill on POSIX) and seals a `RUN_INTERRUPTED`, `partial: true`
receipt. Signals that arrive while a receipt is being sealed are deferred. If the observer itself is
killed, `recover` seals the pending receipt (`sealed_by: RECOVERY`, no end time, metrics
`UNSUPPORTED`) once the observer's pid is gone; unreadable pending files are quarantined, never indexed.

Secrets: values of secret-named variables, secret-named flags and assignments, URL passwords,
`Authorization`/`Bearer` values and known token formats (OpenAI/Anthropic `sk-`, GitHub, AWS, Slack,
JWT, PEM keys) are replaced by `<REDACTED>` in the command, declared values, stored logs and error
messages. The raw-stream SHA-256 is kept so the original output stays identifiable without being stored.
The environment map is never persisted.

## 12. Usage

```bash
# a pytest selection, with outcome counts and a failure set
python -m tools.run_observatory run --adapter pytest --name obs-tests -- python -m pytest -q tests/test_run_observatory.py

# a benchmark bound to its plan, dataset and seed, with a trusted counter
python -m tools.run_observatory run --kind BENCHMARK --name k2 --group k2 --declare plan=K2-v1 \
    --input path/to/dataset-manifest.json --seed 7 --counter cases=1000 -- python path/to/benchmark.py

python -m tools.run_observatory list --failed
python -m tools.run_observatory history <WORKLOAD_ID>
python -m tools.run_observatory fastest <RUN_ID>
python -m tools.run_observatory compare <CANDIDATE> <BASELINE>
python -m tools.run_observatory verify --all
python -m tools.run_observatory recover
python -m tools.run_observatory reindex
```

Overhead: each observed run pays a fixed cost outside the measured window — interpreter start-up and
imports (~0.1 s), git identity (two `git` calls on a clean tree, four on a dirty one) and sealing; the
environment probe only on a cache miss. Measured on one loaded Windows machine: ~0.27 s per run with a
warm cache (0.54 s before the cache). A sub-second workload is visibly slower to run observed; its
recorded duration is not. Numbers and commands: `docs/work/PROGRESS.md` (BR-RUN-OBS-01).

## 13. Roadmap (descriptive only — not an execution queue)

- v1: universal execution ledger (this document).
- v2: solver / provider adapters with trusted counters and replay identities.
- v3: MegaCorpus / data-efficiency telemetry beyond declared counters.
- v4: dashboard and trends over the ledger.


### Stored-log framing and POSIX interrupts

Stored logs buffer incomplete lines, known multiline secrets and PEM blocks
before redaction. If pending input exceeds 1 MiB, remaining stored output is
omitted; `redaction_limit_omitted` records this explicitly. Raw hashes and
terminal passthrough still cover original bytes. An incomplete PEM at EOF is
redacted. This does not guarantee recognition of every possible secret format.

POSIX commands start in a separate session/process group. Interrupts are
forwarded to that group; escalation kills the group even after its direct child
exits. Descendants deliberately creating separate sessions are outside this
process-group contract; the observer is not a hostile-process sandbox.
