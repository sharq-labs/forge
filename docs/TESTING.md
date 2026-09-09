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

**Counts and timings come from different measurements — read them
differently.** Every test count in this document was re-measured on
**2026-09-08** and is current, with
`pytest <selection> --collect-only -q` on a pristine `git archive` export of
`a35144e`. **Every one of them had gone stale**: the 2026-09-06 counts printed
here until then were FAST 1406, SCIENTIFIC 1924 and FULL 1928, against 2570,
3091 and 3095 today — the suite grew by 1167 tests and no count followed it.
Nothing checks these numbers, which is why they drifted; treat a count here as
current only as far as the date beside it.

Every wall-clock figure was measured earlier, on
different hardware and at a smaller suite (1526 FULL tests), and has *not* been
re-measured; each one is marked where it appears. A timing here tells you the
shape of the problem — which tier is worth running, why more workers stop
helping — and nothing reliable about how long your own run will take.

Nothing in the tiering changes what a test asserts. No test was deleted,
skipped, weakened, reordered, or had a tolerance loosened. Tiers only decide
**which** tests you run **now**; the FULL suite still runs every one of them and
is the gate for a milestone freeze.

---

## The tiers

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

FAST runs **83%** of the suite (2570 of 3095) and skips the four campaign
tests plus every frozen-experiment reproduction and domain-solver run. On the
hardware the timings above came from it was ~63× faster than sequential FULL;
that ratio has not been re-measured. Use it.

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

The counts in this document were measured on **Windows 11 with WSL**, where the
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
CRAFTY_NGSPICE_ARGV=ngspice python -m pytest -m "not campaign" -q -n auto \
  --deselect tests/test_heterogeneous_ngspice.py::test_a_the_provider_is_a_real_external_process \
  --deselect tests/test_heterogeneous_ngspice.py::test_g2_a_genuine_non_zero_exit_is_a_provider_failure \
  --deselect tests/test_heterogeneous_ngspice.py::test_j_relocating_the_provider_leaves_the_result_byte_identical
```

Those three assert the WSL default invocation itself and are Windows-only.
They are **deselected for the measurement, never skipped in the suite** — the
markers in `conftest.py` are untouched and a Windows run still executes them.
`.github/workflows/tests.yml` uses exactly this deselection list.

---

## Standard commands

Set `PY` to your interpreter (`python`, or an absolute path on Windows).

### 1. FAST development — after ordinary code edits

```bash
python -m pytest tests/ -m "not expensive" -q
```

**2570 tests** (measured 2026-09-08). This is the default loop for
AI-assisted development.

### 2. TARGETED milestone — the package you are changing

```bash
python -m pytest tests/test_model0r_realization_foundation.py -q
```

104 tests for that milestone (1.3 s, older hardware). Substitute the
milestone's own module. See "Choosing targeted tests" below.

### 3. SCIENTIFIC regression — after a scientific or core change

```bash
python -m pytest tests/ -m "not campaign" -q
```

**3091 tests** (measured 2026-09-08; 137.7 s sequential or 53.7 s with
`-n 12 --dist loadfile` on the older hardware). Every
frozen-experiment reproduction and domain solver test, without the four largest
campaigns. Dropping just those four removes 428 s of the 578 s FULL runtime.

### 4. FULL sequential regression — canonical truth

```bash
python -m pytest tests/ -q -rsxX --durations=30
```

**3095 tests** (measured 2026-09-08; 565.8 s on that machine, 578.3 s on the
older one). This is the fallback and the reference result. If a parallel run
and this run ever disagree, **this one is right**.

### 5. FULL parallel regression

```bash
python -m pytest tests/ -n 8 --dist loadfile -q
```

**3095 tests** (273.2 s, older hardware). **Use `-n 8`, not `-n auto`** — see
"Parallel execution" below, where `-n auto` is measured failing intermittently
with `MemoryError`. `--dist loadfile` is not optional.

### 6. Hybrid regression

**Not required.** No test in this suite is parallel-unsafe: no serial-only
subset exists, and every parallel run that completed produced the identical
full count. See "Parallel safety".

---

## Choosing targeted tests

Do not rely on recall for this. Derive the set:

1. **Start from the milestone's own module.** Milestones own a test file named
   after them — `tests/test_model0r_realization_foundation.py` for MODEL0-R,
   `tests/test_scientific_core.py` for scientific-core work.

2. **Add whoever imports what you changed.** For a change under
   `src/engcore/scientific/`:

   ```bash
   grep -rln "engcore\.scientific" tests/
   ```

   That is the affected set, mechanically, without guessing.

3. **Add the layer guards.** `tests/test_sria_m1.py` pins import direction and
   the no-LLM-dependency rule; `tests/test_core_v02_invariants.py` and
   `tests/test_core_v02_trust_invariants.py` pin the Core V0.2 contracts. These
   are in FAST already, so step 1 of the workflow covers them.

4. **If you touched a domain or an experiment,** run that domain's tests
   explicitly — they are `expensive` and therefore *not* in FAST:

   ```bash
   python -m pytest tests/domains/kinetics/ -q
   python -m pytest tests/test_thermal_t3_decision_aware_fidelity.py -q
   ```

---

## The development workflow

```text
code change
      ↓
FAST                      (9 s)     every edit
      ↓
TARGETED milestone tests  (1-3 s)   every edit to that milestone
      ↓
affected domain/experiment tests    when you touched a domain
      ↓
SCIENTIFIC                (138 s)   before milestone review
      ↓
FULL                      (578 s)   before freeze / merge  ← mandatory
```

**Do not run FULL after every small edit.** It costs 9½ minutes, and 46% of that
is a single multirotor design-campaign test that no scientific-core edit can
affect.

**Do run FULL before a freeze.** The master context requires full repository
regression as a milestone completion condition, and the tiering does not relax
that.

---

## What FAST does not cover

FAST is a real suite — 2570 tests including the entire scientific-core contract
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

### Measured

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

The suite was audited for shared state before parallelising. It is unusually
clean, and this is by design rather than luck — the codebase states the rule
explicitly ("the platform has no global mutable registry"; "no registry, global
or otherwise").

| Hazard | Finding |
|---|---|
| Working-directory mutation | **None.** No `os.chdir` or `monkeypatch.chdir` anywhere in `tests/`. |
| Environment mutation | **None.** The single `os.environ` use copies it for a subprocess. |
| Temporary paths | Safe. Only 5 modules use temp dirs, all via `tmp_path` or `tempfile.TemporaryDirectory()` — both unique per test and per worker. No hard-coded temp path. |
| Writes into the repo tree | **None.** Every test write goes to a temp directory. |
| Shared output files | **None.** |
| Ports, sockets, databases, file locks | **None.** |
| Random seeds | **No RNG in the test suite at all.** Nothing to seed, nothing to race. |
| Subprocesses | One, in `test_multirotor_mvr1.py`: a read-only `--help` invocation that writes nothing. |
| Duplicate module basenames | **None** — no import-mode collisions under xdist. |
| Global mutable state | Module-level memoization only (see above). Process-local, so workers cannot corrupt each other's copy; it costs repeated work, which `--dist loadfile` addresses. |
| Test-order dependencies | None observed. Test counts and results are identical sequentially and in parallel. |

**No hybrid serial/parallel split is required.** No test was found that fails
only under xdist.

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

---

## CI

`.github/workflows/tests.yml` is the only workflow. It runs the **FAST** tier on
every push and pull request, and the **SCIENTIFIC** tier on pushes to `main`
(with the three Windows-only ngspice tests deselected, exactly as listed above).
The FULL tier is run manually before a freeze.

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
