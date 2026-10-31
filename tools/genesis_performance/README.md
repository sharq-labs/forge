# Public Julia performance controls

These commands produce **development software controls**, never a formal Genesis
measurement. No command accepts a root file. Campaign keys are published constants
in `performance_v4.py`; these worlds cannot count as hidden evaluation. Registered
algorithms, operators, seeds, six worlds and search budgets remain unchanged.

Executed results, exact source/asset identities, scaling and estimate limitations
are in the [2026-10-31 performance report](../../docs/performance/genesis-v04-performance-2026-10-31.md).

The scripts describe the measured WSL2 environment, with the code in
`/opt/forge-perf-20261031` and the existing interpreter in
`/opt/forge-mvp-20261028/.venv`. They deliberately refuse incompatible pinned Julia
versions. A different environment requires its own artifact and measurements.

## Separate build environment

PackageCompiler 2.4.4 was installed only in
`/opt/forge-sysimage-build-20261031/compiler`, with its own first depot. The
experiment's Project.toml and Manifest.toml were copied byte-for-byte into
`/opt/forge-sysimage-build-20261031/project`; the sealer checks their equality.
The compiler manifest in each asset records the full resolved build environment.
`setup_build.jl` is the explicit installation entrypoint, not a runtime action.

Copy the build scripts into that build directory, then run from **that directory**
so Julia's public synthetic CSV scratch output also stays there:

```bash
cd /opt/forge-sysimage-build-20261031
bash build.sh /opt/forge-sysimage-20261031/new-packages.so packages native
bash build.sh /opt/forge-sysimage-20261031/new-functions.so functions native
cd /opt/forge-perf-20261031
PYTHONPATH=src /opt/forge-mvp-20261028/.venv/bin/python -m tools.genesis_performance.seal_sysimage \
  /opt/forge-sysimage-20261031/new-functions.so \
  --build /opt/forge-sysimage-build-20261031 --mode functions --cpu-target native
```

Use a fresh destination for every build; do not overwrite sealed artifacts.
The sealer refuses an existing manifest. The manifest binds the binary, Julia
runtime, Python package source/version identities, Project/Manifest, compiler
environment, CPU target, thread settings and actual build-script bytes.

`link_sysimage.py` adapts PackageCompiler's link-only arguments to Julia's bundled
LLD. It rejects C compilation requests. This avoids installing a system toolchain;
the initially attempted GCCBootstrap executable required an unavailable musl loader.
The unused attempted dependency remains documented in the separate build manifest.

Function precompilation executes only the analytic arrays in
`precompile_workload.jl`, in PackageCompiler's tracing subprocess. No Forge world,
root, campaign result, fitted population or discovered law enters the image builder.
The generic CPU-target image failed exact-output comparison and is rejected.
Native images are specific to the measured CPU environment.

The optional `bridge` mode layers PythonCall/PySR call-site specializations on a
previously sealed, compatible native image. In a separate build directory with
the same copied compiler and runtime Project/Manifest files, run
`precompile_pysr.py OUTPUT.json` with `PYTHON_JULIACALL_TRACE_COMPILE` pointing to
`bridge-statements.jl` and `PYTHON_JULIACALL_SYSIMAGE` pointing to the parent image.
Use the existing pinned Python/Julia executables, offline project, private first
depot and one runtime thread, as in the controls. Only those compilation
statements enter the image builder; the tracing process and its fitted state exit.

```bash
bash build.sh /opt/forge-sysimage-20261031/new-bridge.so bridge native \
  /opt/forge-sysimage-20261031/functions-reviewed.so
PYTHONPATH=src /opt/forge-mvp-20261028/.venv/bin/python -m tools.genesis_performance.seal_sysimage \
  /opt/forge-sysimage-20261031/new-bridge.so --build /path/to/separate-build \
  --mode bridge --cpu-target native \
  --base-image /opt/forge-sysimage-20261031/functions-reviewed.so
```

The sealer checks the parent binary, runtime and package identities, CPU target
and runtime thread configuration before creating a child manifest. Sealing is
provenance, not acceptance: full Pareto, campaign trace and cleanup comparisons
must pass before adopting the image. Keep worker counts identical in each pair.

## Public comparisons

Run one batch at a time, without simultaneous tests/builds. `baseline` retains the
original JuliaCall default; `threads` explicitly sets one Julia and one GC thread.
`sysimage-NAME` loads `/opt/forge-sysimage-20261031/NAME.so`. `cache` is the separate
import-only native-cache control. Every proposer still gets a private writable
first depot, a fresh OS process and outside isolation verification.

Use `--executor bounded --deadline-seconds 3600` for scaling measurements through
the pilot's actual hard-deadline executor: a fresh trusted worker per campaign,
atomic result retention and no live workers left past the cutoff. The original
pool controls keep the deadline change separate from the A/B/C/D comparison.
Compare worker counts within the same executor and fixed task count. Summaries
distinguish retained record count from successfully completed records.

```bash
bash tools/genesis_performance/run_control.sh threads --mode campaign \
  --arms pysr_units pysr_symbolic --repeats 3 --workers 4 --out /root/public-control-new
FORGE_PERF_DIAGNOSTICS=1 bash tools/genesis_performance/run_control.sh sysimage-functions-reviewed \
  --mode fit --arms pysr_units pysr_symbolic --repeats 3 --workers 1 --out /root/public-profile-new
PYTHONPATH=src /opt/forge-mvp-20261028/.venv/bin/python -m tools.genesis_performance.analyse \
  /root/public-baseline /root/public-candidate --out /root/public-comparison.json
```

Output directories must not already exist. Keep the manifest, raw JSONL and
summary together. The comparison verifies the recorded JSONL digest and refuses
dirty measurements, duplicate tasks and incomplete trace evidence. It compares
queries/responses (excluding only random transport query IDs), proposals,
scores, refusals and failure classifications. Public comparisons confer no
validation, certification or permission to freeze preregistration.

Parent clocks and process-tree samples are timing authority. Python/Julia phase
labels and Julia compiler counters are explicitly untrusted diagnostic annotations;
their inclusive timings overlap. Scoring/adjudication phase labels come from the
trusted operator. Sampled RSS/PSS peaks are lower bounds, and RSS double-counts
shared pages. New measurements include manifest preflight in total batch elapsed
time; the original controls predate that accounting correction.

## Deadline and mutation controls

The public timing helper and the pilot hard-budget correction are separate paths.
The pilot kills workers at its monotonic cutoff and retains late/terminated/pending
records. Late completed records cannot count as within-budget VALID results.

```bash
PYTHONPATH=src /opt/forge-mvp-20261028/.venv/bin/python -m tools.genesis_performance.check_deadline
# Only in a disposable clean clone; evidence must be outside that clone:
PYTHONPATH=src /opt/forge-mvp-20261028/.venv/bin/python -m tools.genesis_performance.check_mutations \
  --out /root/public-mutations-new
```

The latter is a bounded development mutation set. It does not alter or discharge
the certified OD-3 mutation population. Formal runtime binding, preregistration
freeze, full OD-3, push and merge remain separate owner-controlled operations.
