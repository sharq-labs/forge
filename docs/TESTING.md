# Testing

How to run the suite during development, and which subset to trust for what.

This is engineering telemetry, not scientific evidence. The wall-clock figures
below are **not reproducible across machines**, and the archived audit in
[archive/performance-runtime-audit.md](archive/performance-runtime-audit.md)
measured a 9–14% spread for *identical* code on the hardware they were taken
on. That audit was archived on 2026-09-08 because it is anchored to two commits
that are not in this repository; the 9–14% is quoted here as the shape of the
problem, not as a figure about this tree. Treat them as
approximately one significant figure; the test counts are exact.

**Current versus historical.** Every count and timing under
[Current measurements](#current-measurements-2026-10-12) was measured in one pass on
2026-10-12 on the machine described there, against `origin/main` `305928f9` and
branch `perf/test-loop-cleanup`. Everything under
[Historical results](#historical-results) is kept as a record of earlier runs on
other hardware and smaller suites; none of it was re-measured, and none of it
predicts a run today. A count elsewhere in this file is current only if it says
so. Nothing checks these numbers, which is how the 2026-09-08 counts (2570 /
3091 / 3095) were still printed as current when the suite had grown past 10,000.

Nothing in the tiering changes what a test asserts. No test was deleted,
skipped, weakened, reordered, or had a tolerance loosened. Tiers only decide
**which** tests you run **now**; the FULL suite still runs every one of them and
is the gate for a milestone freeze.

---

## Scientific diagnostic tool

A stored assessment can be explained without changing its verdict:

```bash
python tools/forge_diagnose.py assessment.json
python tools/forge_diagnose.py assessment.json --sensitivity sensitivity.json
python tools/forge_diagnose.py assessment.json --sensitivity sensitivity.json --robustness robustness.json
```

The CLI first verifies the assessment (or replay bundle) against the current registry. Optional sensitivity/robustness artifacts must be digest-sealed and bound to the same assessment, plan and capability.

The report combines evidence gaps, explicit assumptions, admissible model-data
comparisons and the existing next-experiment plan. It distinguishes recorded
blocking conditions from repair hypotheses. A hypothesis is never evidence,
local sensitivity is never causality, and a corrective action never guarantees
that reassessment will become SUPPORTED.

---

## Impact query tool

Stored assessment records can be queried without rerunning physics:

```bash
python tools/forge_impact.py query assessment.json --kind model --key thermal.model
python tools/forge_impact.py query assessment.json --kind trust_registry --key <recorded-registry-digest>
python tools/forge_impact.py detect assessment.json
```

`query` asks which assessments depend on a declared identity. `detect`
compares stored capability/policy/trust identities with the current production
registries and returns a reassessment report. Neither command edits historical
decisions or changes scientific standing.

---

## Fast changed-file gate

```bash
python tools/forge_check.py --changed --workers 4          # what changed since main, including uncommitted edits
python tools/forge_check.py --changed --dry-run --list     # show the selection and why, run nothing
python tools/forge_check.py --regression --workers 4       # the fixed scientific regression pack
python tools/forge_check.py --changed --workers safe-auto  # developer only: 8/6/4/2/1 from CPUs and free memory
python tools/forge_check.py --dev                          # one command after editing (below)
python tools/forge_check.py --scientific                   # developer aid: affected expensive tests too, when narrowable
```

**`--dev`** is the one command to run after an edit: the `--changed` gate with
safe-auto workers (an explicit `--workers` wins), a timing report under
`~/.cache/forge/timing/` (`FORGE_TIMING_DIR` moves it), a warning-only comparison
with the previous report, and a closing block:

```text
CHANGE CLASS: domain_local
AFFECTED: 49 test modules reached; 143 targets selected
RUN: changed gate -> PASS
EXPENSIVE AFFECTED: 7 (7 not run)
NEXT REQUIRED: FAST + SCIENTIFIC
```

`NEXT REQUIRED` follows the minimum-gate table (`tools/test_impact.next_required`):
FAST for anything but documentation; SCIENTIFIC for shared, trust, configuration or
unknown reach and whenever an affected test is expensive; a forge-scientific-review
for trust/authority; RECERTIFICATION for any certification-pinned path. It never
runs those gates for you.

**`--scientific`** (developer aid, never a gate) also runs the affected expensive
tests (`-m "not campaign"`), but only where the reach can be bounded. It refuses
(exit 2, prints the whole-tier command) for trust/authority, shared scientific code,
test infrastructure (any `conftest.py`, `pyproject.toml`, the selector itself),
unclassified paths and any change whose reach could not be established. The
certification overlay never hides what a path is: a pinned domain module may be
narrowed, and RECERTIFICATION is still owed. Measured 2026-10-13 (`-n 8`, one probe
edit each): documentation 13.5 s; `domains/battery/thevenin.py` 63.7 s (49 modules
reached, 7 expensive); `providers/process.py` 69.9 s (99 reached, 7 expensive);
units, authority and `tests/conftest.py` refused. The full SCIENTIFIC tier was 267 s.
With the CSTR mutation G9c applied, `--scientific` selected and ran
`tests/domains/kinetics/test_cstr_domain.py` (expensive), which failed. A selective
run discharges nothing: SCIENTIFIC is still owed before review, merge or freeze.

**Timing telemetry and the slowdown guard** (`tools/test_timing.py`). Any pytest run
can record a report with `-p tools.test_timing --timing-report=PATH`; `python -m
tools.test_timing compare OLD NEW` lists only large slowdowns and exits 1 if any,
`history` lists recorded runs. A report is developer telemetry: machine-specific,
never evidence, never certification, never read to decide a result. A change is
flagged only when it clears both bars -- a module x2 and +5 s, a test x2 and +3 s,
the whole run x1.4 (same worker count and tests). Measured noise between identical
warm FAST runs: modules within 2.5 s, tests within 1.8 s, whole runs of identical
code up to x1.25; none of six real run pairs (including a cold first run) was
flagged, a synthetic x2.2 module was.

`--changed` runs the union of:

1. the repository/layer guards (`ARCHITECTURE_TESTS`);
2. the fixed scientific regression sentinels from
   `tests/scientific_regression/manifest.json` chosen by path tags, or the whole
   pack when a changed path cannot be classified;
3. every changed test module;
4. every test module the change can **reach** (`tools/test_impact.py`): by import
   (any chain of first-party imports, function-level imports, package
   `__init__` chains, dotted module names in strings, a deleted module traced by
   name), by naming the changed file's path, by a governing `conftest.py`, or --
   for any `src/` change -- by walking the source tree (the guards an import graph
   cannot see). A change no rule reaches is reported as unresolved and selects the
   whole pack.

Affected tests that are `expensive` are **listed, not run** -- run SCIENTIFIC, or
pass `--with-expensive`. Each changed path is printed with its class (from
repository ownership: `doc_only`, `test_only`, `local_nonscientific`,
`domain_local`, `scientific_shared`, `trust_or_authority`,
`test_infrastructure`, `certification_pinned`, `unclassified`) and the minimum
gate it calls for. Any path the CI recertification classifier
(`tools/certification/recertification_scope.py`) treats as a trigger is printed
under `RECERTIFICATION_REQUIRED`: this gate never replaces the owner-run hardened
recertification. `--committed-only` ignores staged, unstaged and untracked files.

Why step 4 exists: before it, an edit to `src/engcore/domains/battery/thevenin.py`
ran the tag sentinels and never `tests/domains/test_battery_thevenin.py`. The
gate over-selects on purpose -- an extra test costs seconds, a missed one is
false confidence. Measured cost per change class is under
[Current measurements](#current-measurements-2026-10-12).

**Impact cache.** `--changed` keeps each file's import facts in
`~/.cache/forge/test_impact/` (outside the repository), keyed by the sha256 of
the file's bytes and by the extractor's own source and the interpreter version.
Every run still lists, reads and hashes every file and recomputes roots, module
names, resolution and the reverse graph, so a change to any file, an added,
deleted or renamed file, `pyproject.toml` or a `conftest.py` cannot be answered
from the cache; a doubtful cache is a miss. `FORGE_IMPACT_CACHE=<file>` moves
it, `FORGE_IMPACT_CACHE=off` disables it. Measured (2026-10-13, one `selection.py`
edit, `--dry-run`): 6.37 s median before, 1.81 s warm, 6.6 s on the first (cold)
run; identical selections for four probe edits.

**`--workers safe-auto`** (developer convenience, never CI policy) picks 8, 6, 4,
2 or 1 workers from half the logical CPUs and the available memory, and prints
the choice and why; an integer `--workers` is unchanged. The memory budget
(650 MB per worker for FAST-tier selections, 1,000 MB with `--with-expensive`,
plus 2 GB headroom) is measured, see `tools/local_workers.py`. Without `psutil`
it falls back to 4.

This command is a development aid only. It does **not** replace FAST,
SCIENTIFIC, FULL or hardened recertification.

---

## The tiers

The current counts and timings are under
[Current measurements](#current-measurements-2026-10-12). The tables that used to
stand here are under [Historical results](#historical-results).

The markers are assigned centrally in [`tests/conftest.py`](../tests/conftest.py)
and registered in `pyproject.toml`. They are applied from `conftest.py` rather
than with `@pytest.mark` decorators for a specific reason: two test modules are
SHA-256 pinned by frozen experiments —

```
experiments/electrical_e2/e2_config.py  pins  tests/test_sria_e1_electrical.py
experiments/electrical_e3/e3_config.py  pins  tests/test_sria_e2_model_adequacy.py
```

— and both need tier labels. Editing either file would break the pin that makes
"E1 was not edited under E2" a checkable claim. Marking from `conftest.py` leaves
every existing test file byte-identical.

### What the markers mean

`expensive`
: The test executes scientific work costing seconds — it reproduces a frozen
  experiment, drives a domain solver, or runs a design study.

`campaign`
: A subset of `expensive`: a large design/discovery campaign, or a full
  stiff-solver ladder run to its budget. Just four tests, carrying 428 s of the
  578 s FULL runtime — 74% of the suite in four tests, one of them 46% alone.

The criterion is **what the test does**, not what it costs. Cheap scientific
tests are deliberately unmarked: the electrical DC solver tests and the 1-D
conduction tests execute real domain numerics and stay in FAST, because that
execution costs milliseconds and the coverage is worth having every time.

---

## Where the counts were measured, and what changes them

The current counts were measured on **Windows 11 with WSL**, where the
ngspice provider's default invocation — `("wsl.exe", "-e", "ngspice")`,
`ngspice.py:191` — resolves without configuration. Nothing was deselected and
no environment variable was set, so every count here is the whole suite.

**On Linux the numbers are three lower per tier.** The provider is discovered
through `CRAFTY_NGSPICE_ARGV` (`ngspice.py:206-213` — note the variable still
carries the old product name; renaming it is deferred because
`test_j2_the_invocation_is_configuration_and_reads_the_environment` pins it),
so a native run needs:

```bash
sudo apt-get install -y ngspice
CRAFTY_NGSPICE_ARGV=ngspice python -m pytest -m "not campaign" -q -n 4 --dist loadfile \
  --deselect tests/test_heterogeneous_ngspice.py::test_a_the_provider_is_a_real_external_process \
  --deselect tests/test_heterogeneous_ngspice.py::test_g2_a_genuine_non_zero_exit_is_a_provider_failure \
  --deselect tests/test_heterogeneous_ngspice.py::test_j_relocating_the_provider_leaves_the_result_byte_identical
```

Those three assert the WSL default invocation itself and are Windows-only.
They are **deselected for the measurement, never skipped in the suite** — the
markers in `conftest.py` are untouched and a Windows run still executes them.
`.github/workflows/tests.yml` deselects these three and three more (see
[Standard commands](#standard-commands)).

---

## Standard commands

Run every tier from the repository root **without a path argument**. CI does
(`python -m pytest -m ...`), and so it also collects `benchmarks/*/tests`,
`flagships/tests` and `providers/*/tests`. `python -m pytest tests/ -m "not expensive"`
-- the command this section used to print -- collects 9,463 tests
instead of 10,033: it silently left out 570 of them.

### 1. Changed / targeted -- after every edit

```bash
python tools/forge_check.py --changed --workers 4
```

### 2. FAST -- a checkpoint before you push

```bash
python -m pytest -m "not expensive" -q -n 4 --dist loadfile
```

10,033 tests on `origin/main` `305928f9`. Exactly CI's command.

### 3. SCIENTIFIC -- before review of a scientific or core change

The command CI runs (`.github/workflows/tests.yml`), deselects included:

```bash
python -m pytest -m "not campaign" -q -n 4 --dist loadfile \
  --deselect tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared \
  --deselect tests/test_heterogeneous_ngspice.py::test_a_the_provider_is_a_real_external_process \
  --deselect tests/test_heterogeneous_ngspice.py::test_g2_a_genuine_non_zero_exit_is_a_provider_failure \
  --deselect tests/test_heterogeneous_ngspice.py::test_j_relocating_the_provider_leaves_the_result_byte_identical \
  --deselect benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates \
  --deselect benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates
```

10,611 tests collected before the deselects. The two
`test_rebuilding_everything...` tests rebuild into a private copy under
`tmp_path` since 2026-10-13 and leave the tree byte-identical (see
[Parallel safety](#parallel-safety)); CI still deselects them because they fail
on their own pre-existing grounds (the pinned scientific-core digest no longer
matches the tree), not because they write.

### 4. FULL -- milestone / freeze

```bash
python -m pytest -q -n 8 --dist loadfile
```

10,615 tests collected. Not run in this pass. If a parallel run and a
sequential run (`python -m pytest -q -rsxX`) ever disagree, the sequential run is
right.

### 5. Hybrid regression

**Not required**, with one exception documented under
[Parallel safety](#parallel-safety): the two benchmark rebuild tests.

---

## Choosing targeted tests

Do not derive the set by hand. `python tools/forge_check.py --changed --dry-run --list`
prints the affected set and why each module is in it (`imports ...`,
`mentions ...`, `governed by ...`, `reads source files by path`). For a domain or
experiment you touched, its expensive tests are printed as left out; run them
with `--with-expensive` or as part of SCIENTIFIC.

---

## The development workflow

```text
code change
      ↓
CHANGED / TARGETED   forge_check --changed      every edit         (about 15-65 s at --workers 4 for the measured classes)
      ↓
FAST                 -m "not expensive"         before push        (161.1 / 163.3 s at -n 4, 101.1 s at -n 8)
      ↓
SCIENTIFIC           -m "not campaign" + CI deselects   before review   (245-276 s at -n 4)
      ↓
FULL                 no selection               milestone / freeze  (not measured in this pass)
```

Times are this pass's measurements on the machine under
[Current measurements](#current-measurements-2026-10-12); expect a ~10% run-to-run
spread. **Do not run FULL after every small edit.** **Do run FULL before a
freeze**: the master context requires full repository regression as a milestone
completion condition, and the tiering does not relax that.

---

## What FAST does not cover

FAST is a real suite — 10,033 tests including the entire scientific-core contract
layer, the SRIA architecture layer, the design layer, campaign persistence,
serialization, registries, error taxonomy and the dependency-direction guards.
It is not a smoke test. But it deliberately omits these risk classes:

| Not covered by FAST | Caught by |
|---|---|
| Frozen experiment **reproduction** — a change that alters an experiment's outputs or config hash | SCIENTIFIC |
| Domain **solver numerics** at cost — CSTR verification gates, stiffness measurement, tolerance ladders | SCIENTIFIC |
| Solver **work counts** — the PERF-1 regression gate in `test_cstr_solver_work.py` | SCIENTIFIC |
| **Cross-experiment** consistency — T2 reusing T1's forward maps, E3's scope mapping from E2 | SCIENTIFIC |
| Design **campaign population statistics** — the 1000-candidate MVR0/MVR1 counts | FULL |
| **Oracle agreement and convergence** studies in `benchmarks/scientific_truth`, the B2 flagship result **reproduction**, the multiscale long-horizon and resume proofs, and the resolved-grid **positive controls** (19 tests, `EXPENSIVE_TESTS`) | SCIENTIFIC |

**Refusals stay in FAST even when they cost seconds.** A test whose subject is a
refusal, a forgery, a context or identity binding, or the separation of two
scientific verdicts is never moved out of FAST for speed. FAST is the only tier
CI runs on Python 3.11 (SCIENTIFIC runs on 3.12 only), so moving one would
silently drop its 3.11 execution.

One class **is** retained in FAST on purpose: the **frozen-artifact digest
guards**. Every `expensive` module keeps an allowlist of static guards — tests
that only hash pinned files, scan source for forbidden imports, or check that
nothing wrote to `src/`. Those cost nothing and catch the failure mode this
repository cares most about, including a line-ending regression breaking the
SHA-256 pins (see `.gitattributes`). So FAST still tells you immediately if a
frozen artifact changed underneath you — it just will not re-derive it.

---

## Parallel execution

`pytest-xdist` is a **development dependency only** (`pyproject.toml`,
`[project.optional-dependencies] dev`). No production code imports it, and the
suite must stay green without it.

```bash
python -m pip install -e ".[dev]"     # or: pip install "pytest-xdist>=3.5"
```

### `--dist loadfile` is not optional

Several test modules memoize a whole experiment in module-level state:

* `_RESULT` globals in `test_sria_e2_model_adequacy.py`,
  `test_sria_e3_adequacy_obligation.py` and `test_electrical_v01_demo.py`;
* cached forward maps inside the experiment packages themselves —
  `test_t2_uses_t1s_forward_maps_unchanged` asserts `from_t2 is from_t1`.

Each xdist worker is a separate process with its own copy of that state. Under
the default `--dist load` (per-test round-robin), *every worker that receives
any test from such a module re-executes the whole experiment*. Grouping by file
with `--dist loadfile` keeps each module on one worker, so the experiment runs
once per module as it does sequentially.

This is a correctness-neutral, performance-critical setting: results are
identical either way, but the measured cost is not.

### Why more workers stops helping

The suite's runtime is extremely concentrated. In the measurement below — older
hardware, a 1520-test suite, not re-run since — **1470 of 1520 tests ran in
18.75 s combined (3.3%)**, while a single test —
`test_full_studies_a_and_b_use_same_universe_and_a_reproduces_mvr0` — took
**260.71 s (46.3%)**. The concentration is structural and still holds; the
numbers are that run's.

That test is an indivisible unit of work. No worker count can make the FULL
suite finish faster than it does, so parallel FULL is bounded below by ~261 s
and the best achievable speedup is about **2.2×**, reached by the time there are
enough workers to overlap the other long tests with it. Adding workers past that
buys nothing and costs memory.

### Current worker scaling (2026-10-12)

FAST (`-m "not expensive"`, 10,033 tests), `--dist loadfile`, on the
machine under [Current measurements](#current-measurements-2026-10-12), before
this pass's optimizations. Every run had the identical failure set.

| `-n` | Wall | Process-tree CPU | Peak RSS | Summed test time | Busy max / mean |
|---|---|---|---|---|---|
| 1 | 589.2 s | 405.6 s | 1.10 GB | 566.4 s | -- |
| 2 | 302.9 s | 424.8 s | 1.73 GB | 571.9 s | 1.00 |
| 4 | 176.5-195.9 s | 487-537 s | 2.6-3.3 GB | 639-705 s | 1.01-1.02 |
| 6 | 151.4 s | 619.8 s | 3.71 GB | 790.3 s | 1.02 |
| 8 | 139.9 s | 686.4 s | 3.93 GB | 850.1 s | 1.19 |
| 4, `--dist load` | 189.8 s | 485.5 s | 2.40 GB | 629.0 s | 1.11 |
| 12 | not run: ~9 GB was free, and the memory per worker measured here puts 12 workers at the edge of it | | | | |

"Summed test time" grows with the worker count: past four workers, tests
contend for CPU, disk and process start-up, so each test gets slower. The knee
is **6-8 workers on this 16-core / 32 GB machine**; after this pass's fixture
change removed the 98 s critical-path module, `-n 8` fell from 139.9 s to
101.1 s and its load imbalance from 1.19 to 1.03. `--dist load`
was no faster than `loadfile` on FAST (189.8 s against 176.5-195.9 s) and is wrong for
the memoizing modules, so `loadfile` stays. Keep `-n 4` in CI (4-core runners).

### Historical sweep

**A historical record, deliberately not rewritten.** The worker sweep and the
memory sampling below were run once, on different hardware, against a
1526-test FULL suite. Their test counts are part of the measurement, so they
are left as they were rather than restated at today's count — rewriting them
would claim nine configurations were re-run when none were. What they
establish — that `--dist loadfile` matters, that the speedup saturates, that
`-n auto` runs the machine out of memory — is structural and still holds.

Machine: 16 physical cores / 24 logical processors, 31.7 GB RAM (~11.9 GB free),
Windows 11, Python 3.14.2, pytest 9.0.2, pytest-xdist 3.8.0. FULL suite,
`--dist loadfile` unless noted.

| Workers | Tests | Runtime | Result | Notes |
|---|---|---|---|---|
| 1 (sequential) | 1526 | 578.3 s | 1526 passed | reference |
| 4 | 1526 | 289.6 s | 1526 passed | 2.00× |
| **8** | 1526 | **273.2 s** | 1526 passed | **2.12× — recommended** |
| 12 | 1526 | 279.6 s | 1526 passed | 2.07× |
| 16 | 1526 | 270.6 s | 1526 passed | 2.14× |
| auto (24) | 1517 | 293.9 s | **9 FAILED** | `MemoryError` — see below |
| auto (24), repeat | 1526 | 288.3 s | 1526 passed | same command, different outcome |
| 8, repeat | 1526 | 290.8 s | 1526 passed | 6.5% spread vs first run |
| 12, repeat | 1526 | 295.7 s | 1526 passed | 5.7% spread vs first run |
| 12, `--dist load` | 1526 | 315.0 s | 1526 passed | **13% slower than `loadfile`** |

**Read the spread before reading the ranking.** Repeating `-n 8` gave 273.2 s
and 290.8 s; `-n 12` gave 279.6 s and 295.7 s. The run-to-run spread (~6%) is
larger than the gap between 8, 12 and 16 workers. **Those three are
statistically indistinguishable on this machine**, exactly as the ~261 s
critical-path floor predicts. Anyone quoting "16 is fastest" from the single
270.6 s reading is reading noise.

### `-n auto` is not safe here

`-n auto` selects 24 workers. On its first run, 9 tests in
`test_sria_falsification_transport.py` failed with
`numpy._core._exceptions._ArrayMemoryError: Unable to allocate 92.8 MiB for an
array with shape (301, 40401)`. On an identical rerun, all 1526 passed.

That is **intermittent, memory-driven failure, not a test defect**. Each worker
is a separate process carrying its own interpreter, NumPy/SciPy/scikit-learn
and its own copy of those arrays. Sampling total Python RSS and free system RAM
once per 1.5 s during a FULL run:

| Workers | Peak Python RSS | Min free RAM | Result |
|---|---|---|---|
| 8 | 1.75 GB | 10.98 GB | 1526 passed |
| 16 | 3.08 GB | 10.07 GB | 1526 passed |
| 24 | 4.88 GB | **0.00 GB** | **11 failed** |

Memory grows at roughly 200 MB per worker. At 24 the machine ran out: free RAM
reached zero, 11 tests failed, and the sampling script's own WMI query returned
`Out of memory`. Across three runs at 24 workers, two failed (9 and 11 tests)
and one passed.

Nothing in the failing tests is shared state, and they pass at every bounded
worker count. A suite that passes only sometimes is worse than a slower one that
always passes.

**A second instance, 2026-09-06, confirming the diagnosis.** On a 24-logical-core
machine, `-m "not expensive" -n auto` failed one test —
`test_sria_campaign_persistence_v03_scaling.py::test_event_records_are_exactly_linear_at_one_thousand_checkpoints`
— with `MemoryError` raised inside `json.encoder`. The same test passes alone in
1.2 s, and the whole FAST tier passes at `-n 4`.

The useful part is the size of that test. Measured with `tracemalloc`, it peaks
at **11.2 MB** and serializes a **2.1 MB** blob. It is not a heavy test, and
nothing about it is near a memory limit on its own. It failed because the
*machine* was out of memory when it happened to be the one allocating.

That is the point: at `-n auto` the victim is arbitrary. The first instance
blamed NumPy allocations in `test_sria_falsification_transport.py`; this one
blames the JSON encoder in an 11 MB test in a different tier. Neither test is at
fault, and chasing either as a test defect is wasted work. The failure is the
worker count.

**Use `-n 8`.** It was the fastest measured configuration, it uses a third of
the memory of `-n auto`, and it is already past the point where extra workers
stop helping. On a machine with more RAM per core, `-n 16` would be equally
reasonable — the constraint here is memory, not cores.

---

## Parallel safety

Re-audited 2026-10-12. The table that stood here said "Writes into the repo
tree: None" and "Subprocesses: One"; both had stopped being true.

| Hazard | Finding (2026-10-12) |
|---|---|
| Writes into the repo tree | **None since 2026-10-13.** The two rebuild tests (`benchmarks/empirical_validation/...` and `benchmarks/model_measurement_validation/...::test_rebuilding_everything_reproduces_the_published_gates`) used to rewrite 17 committed JSON files in place, and a concurrent `tests/claims/test_offline_revalidation.py` replay correctly reported `NOT_REPRODUCIBLE`. Each round's audit package now writes its top-level artifacts through `ARTIFACT_DIR`; the tests point it at a `tmp_path` copy and assert the committed round directory is byte-identical afterwards. SCIENTIFIC without the deselects leaves the tree byte-identical (measured). |
| Working-directory mutation | `monkeypatch.chdir` in two modules -- restored per test. No bare `os.chdir`. |
| Environment mutation | `monkeypatch.setenv` in three modules -- restored per test. |
| Temporary paths | `tmp_path` / `tmp_path_factory` / `tempfile`; unique per test and per worker. No hard-coded temp path. |
| Subprocesses | Many, all into temp directories: `git` in the certification suites' synthetic repositories (since 2026-10-12 built once per module and copied per test), ngspice, provider probes. |
| Module-level memoization | Process-local; `--dist loadfile` keeps each memoizing module on one worker. |
| Bytecode caches | Not a safety hazard, a cost: with `PYTHONDONTWRITEBYTECODE` set (some sandboxed shells set it), no `.pyc` and no rewritten-assertion cache is written, and collection costs ~20 s per process instead of ~8 s. |

---

## Keeping the tiers honest

`tests/test_tier_classification.py` asserts that every module path, campaign
test name and static-guard name in `conftest.py` still exists. Without it a
rename would silently move a test between tiers — a campaign test rejoining
FAST, or worse, a frozen-experiment reproduction quietly dropping out of
SCIENTIFIC. The guard runs in FAST.

If you add a test that runs an experiment, a solver or a design study, add its
module to `EXPENSIVE_MODULES`. **Unclassified tests default to FAST**, which is
the safe direction: a new test is covered by the routine loop until someone
measures it and argues otherwise.

When the cost sits in individual tests rather than in a module-level memoized
experiment, label the test in `EXPENSIVE_TESTS` instead (a node id, or
`module::function` for every case), and label every test that reads the same
fixture or memoized build with it, or the cost hops into its neighbour. The
refusal rule above still applies. `test_tier_classification.py` checks that
each key names a test that exists, that no test is classified twice, and that
the matching rule labels exactly what it names.

**Drift is the failure mode, not a one-off.** Between 2026-09-08 and 2026-10-12
the suite grew from ~3,100 to ~10,400 tests, nobody extended the tables, and
FAST quietly absorbed about 680 s of solver work. Re-measure FAST with
`--durations=30` when the count moves by more than a few hundred tests.

---

## CI

Four workflows exist: `tests.yml` (FAST on Python 3.11 and 3.12, SCIENTIFIC on
3.12 with the six deselects listed under [Standard commands](#standard-commands)),
`recertify-hardened-core.yml` (owner-triggered hardened recertification),
`trust-mutations.yml` and `branch-policy.yml`. **All four are
`workflow_dispatch`-only** (since `35d21685`, 2026-10-06): nothing runs on a pull
request or a push, so a PR is classified by
`tools/certification/recertification_scope.py` only when someone runs the
workflow by hand. The authoritative path is local assurance
(`docs/assurance/BRANCH_PROTECTION.md`). The FULL tier is run manually before a
freeze.

Worker counts in the sections above are **local recommendations**. The workflow
is different: it pins `-n 4 --dist loadfile` on both jobs, and that pinning is
deliberate.

**Do not put `-n auto` in the workflow.** It sizes itself from the runner, which
makes the memory ceiling a property of whatever hardware the job happens to land
on rather than of the command. Memory grows at roughly 200 MB per worker
(measured above), so a job that is comfortable on a 4-core runner walks straight
into the exhaustion documented in "`-n auto` is not safe here" the moment it
lands on a larger one — and GitHub's larger runners are opt-in per label, so
that change can be made by someone editing `runs-on` and nothing else. A pinned
count keeps the memory ceiling in the command where it can be read.

`--dist loadfile` matters more in CI than the worker count does. Without it,
every worker that receives any test from a memoizing module re-executes that
module's whole experiment (see "`--dist loadfile` is not optional"). The
SCIENTIFIC job is where those modules live, so omitting it there multiplies the
expensive work by the worker count.

Every command in this document is path-independent and runs the same on Linux CI
as locally.

---

## Current measurements (2026-10-12)

Machine: Windows 11 Pro 10.0.26200, Intel (16 physical / 24 logical cores),
31.7 GB RAM (about 9 GB free during the runs), CPython 3.14.2, pytest 9.1.1,
pytest-xdist 3.8.0, ngspice reachable through WSL. Tree: `origin/main`
`305928f9` ("before") and branch `perf/test-loop-cleanup` ("after"). Bytecode
caching on (a developer shell); harness `-p no:cacheprovider`. Wall-clock spread
for identical runs here: about 10%.

**Failure sets.** On this host every FAST run, before and after, had the same
151 failures and 21 errors: Windows / Python 3.14
environment (mutation-workspace POSIX contracts, local-assurance source gates,
formal-xdist, escrow and authority subprocess tests) and the known certificate
and freeze-manifest drift. A faster run with a different failure set would not
count; none was accepted.

| Measurement | Before | After |
|---|---|---|
| Collection, whole suite, one process (bytecode warm / `PYTHONDONTWRITEBYTECODE=1`) | 8.0 s / 18-20 s | no measurable change: pytest-reported 5.4-5.5 s vs 5.6-6.3 s before, interleaved, within noise |
| FAST, `-n 4 --dist loadfile` (10,033 tests before) | 195.9 / 176.5 / 195.0 s (three runs) | 161.1 / 163.3 s |
| FAST, `-n 8 --dist loadfile` | 139.9 s | 101.1 s |
| SCIENTIFIC as CI runs it, `-n 4` | 308.2 / 303.9 s | 245.4 / 275.7 s |
| SCIENTIFIC without the deselects, `-n 4` (rewrites 17 JSONs) | 336.3 s | 284.0 s (2 extra failures: the race under Parallel safety) |
| certificate_lineage + skip_admission + hardening_assurance, serial | 172-176 s | 30-34 s |
| FULL | not measured | not measured |

Changed-file gate, `forge_check --changed --workers 4`, one throwaway edit per class:

| Change (class) | Old gate: tests, wall | New gate: tests, wall | What the old gate did not run |
|---|---|---|---|
| `domains/battery/thevenin.py` (domain_local) | 165, 11.2 s | 1,858, 52.5 s | the model's own `tests/domains/test_battery_thevenin.py`, and every source-walking guard |
| `claims/selection.py` (scientific_shared) | 241, 12.0 s | 3,839, 63.7 s | the 160+ modules importing the claim runtime |
| `authority/ledger.py` (trust_or_authority) | 241, 10.7 s | 2,047, 55.3 s | the authority, escrow and campaign suites |
| `docs/TESTING.md` (doc_only) | 56, 6.1 s | 184, 15.3 s | tests that read the document |

Wall time includes building the import graph (~5.8 s). The new gate's failures were the host's known environment set plus, for `selection.py`, two modules that could not run outside the full suite (fixed on this branch); none was caused by the probe edit.

The heaviest FAST modules before this pass were the certification suites
(`test_certificate_lineage` 98 s, `test_skip_admission` 56 s,
`test_hardening_assurance` 51 s of 705 s summed test time), all rebuilding the same
synthetic git repository per test.

---

## Historical results

Kept as a record; not re-measured; do not read them as predictions.

### Tier table, 2026-10-12, `88a258f2` (2-core Linux container)

> **Current counts and timings (2026-10-12, `88a258f2`, branch
> `perf/test-suite-runtime`).** MEASURED with `pytest <selection> --collect-only -q`
> and `python -m pytest -m "<selection>" -q -n 2 -p no:cacheprovider` on a 2-core
> Linux container, CPython 3.13.16, pytest 9.1.1, pytest-xdist 3.8.0, with `main`
> (`8b028dc`) measured back to back on the same host as the comparison. ngspice was
> absent (Linux, no `CRAFTY_NGSPICE_ARGV`), so its tests fail rather than run.
>
> | Tier | Tests | `main` wall, `-n 2` | this branch, `-n 2` |
> |---|---|---|---|
> | **FAST** | **9806** (of 10388) | 992 s | **476 s** |
> | **SCIENTIFIC** | **10384** | 1448 s | **1024 s** |
> | **FULL** | **10388** | not measured | not measured |
>
> Both runs of each tier had the identical failure set: the certificate and
> freeze-manifest drift `main` already carries, two mutation-workspace tests, and
> the ngspice tests. Wall-clock is one run on one host and carries the spread
> described at the top of this file. The table below is the 2026-09-06 record,
> kept as history; its counts are a third of today's suite.

Test counts measured 2026-09-06 (Windows 11 + WSL, Python 3.14.2, pytest 9.1.1;
see "Where the counts were measured"). Wall-clock columns are the *older*
measurement on different hardware and a 1526-test suite — kept for shape, not
for prediction, and not re-measured.

| Tier | Selection | Tests | Sequential † | Parallel † | Use it |
|---|---|---|---|---|---|
| **FAST** | `-m "not expensive"` | **2570** | 9.2 s | 7.3 s | after every ordinary code edit |
| **TARGETED** | a path | varies | seconds | — | the milestone you are working on |
| **SCIENTIFIC** | `-m "not campaign"` | **3091** | 137.7 s | 53.7 s | after a scientific/core change |
| **FULL** | *(no selection)* | **3095** | 578.3 s | 273.2 s | before a milestone freeze or merge |

† older hardware, smaller suite, not re-measured — see the note above.


### FAST share, 2026-09-08

FAST runs **83%** of the suite (2570 of 3095) and skips the four campaign
tests plus every frozen-experiment reproduction and domain-solver run. On the
hardware the timings above came from it was ~63× faster than sequential FULL;
that ratio has not been re-measured. Use it.


