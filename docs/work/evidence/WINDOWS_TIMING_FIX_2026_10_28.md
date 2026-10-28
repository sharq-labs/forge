# Windows timing-test fixture boundary — 2026-10-28

Scope: bounded WP-02 test-environment repair under the current Scientific MVP
queue. Owner authorized continuing Windows development before the WSL stage,
and confirmed another session is concurrently editing discovery/analysis.
This repair touches only `tests/test_test_timing.py`; it does not take ownership
of that session's scientific changes. This is an execution record, not a queue.

HEAD: `dd567d53d2444950f57ffaeb9903c74d7c38f04d`, local `main`, dirty shared
working tree. Environment: native Windows, existing `.venv` Python 3.11.15.
The earlier FAST result remains historical to its measured working state;
no whole-tree green claim follows from this focused run.

## Reproduction and repair

Command before repair:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_test_timing.py::test_the_plugin_records_telemetry_and_never_changes_an_outcome -q
```

Result: **1 failed in 0.84 s**, parent pytest exit 1. The child returned exit 4
instead of the expected 1, before exercising the generated pass/fail fixture.
Previous isolated reproduction in this session identified collection of an
inaccessible unrelated Windows temporary-directory entry. The child had no
explicit root or conftest cutoff despite owning only one generated test file.

Repair: pass `--rootdir=<tmp_path>` and `--confcutdir=<tmp_path>` to that child
pytest invocation, retaining its explicit generated file, plugin, working
directory and every existing assertion. No production plugin, global pytest
configuration, tolerance, skip marker or required gate changed.

Command after repair:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_test_timing.py -q
git diff --check -- tests/test_test_timing.py
```

Result: **9 passed in 0.87 s**, pytest exit 0; diff check exit 0. The embedded
fixture still must return exit 1 with exactly one passed and one failed test;
the telemetry must preserve those outcomes and the existing timing threshold.

Scientific files were inspected but not edited in this continuation. The
ordering tests were also run before the timing repair: 6 passed in 0.54 s on
the then-visible concurrently edited tree, not an immutable scientific gate.

Full FAST rerun, SCIENTIFIC, Linux isolation and full assurance: **NOT RUN**.
No WSL installation, hidden final data access, campaign, commit, push or merge.
