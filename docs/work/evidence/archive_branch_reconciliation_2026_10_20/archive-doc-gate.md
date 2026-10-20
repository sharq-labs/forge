# archive-doc-gate

```json
{
  "command": [
    "C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe",
    "tools/forge_check.py",
    "--changed",
    "--base",
    "origin/main"
  ],
  "cwd": "C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f",
  "environment": {
    "TMPDIR": "D:/tmp/archive-doc-gate",
    "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f",
    "PYTEST_ADDOPTS": "--basetemp=D:/tmp/archive-doc-gate/bt"
  },
  "exit_code": 1,
  "elapsed_seconds": 12.023089699912816,
  "completed_utc": "2026-10-20T19:21:14.494490+00:00",
  "output_sha256": "d3557cf8046f35f632278df199f51cd35e110c4570309d48bd23df060f56f2e0"
}
```

Rendered log (trailing whitespace stripped; raw digest above):

```text
........................................................................ [ 32%]
........................................................................ [ 65%]
....................................F............................F...... [ 98%]
...                                                                      [100%]
================================== FAILURES ===================================
__________ test_the_subprocess_escrow_keeps_its_secrets_in_the_child __________

    def test_the_subprocess_escrow_keeps_its_secrets_in_the_child():
>       t = SubprocessTransport()
            ^^^^^^^^^^^^^^^^^^^^^

tests\foundations\test_v2_blindfold.py:354:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <engcore.blindfold.escrow.SubprocessTransport object at 0x0000017D727ED550>
storage = None

    def __init__(self, storage: str | os.PathLike[str] | None = None) -> None:
        args = [sys.executable, "-I", "-m", "engcore.blindfold.escrow_server"] + (["--storage", str(storage)] if storage else [])
        self._proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        assert self._proc.stdout is not None
        hello = json.loads(self._proc.stdout.readline() or b"{}")
        if hello.get("protocol") != PROTOCOL or not hello.get("operator_token") or not hello.get("escrow_public"):
>           raise EscrowRefused("the escrow process did not complete its handshake")
E           engcore.blindfold.escrow.EscrowRefused: the escrow process did not complete its handshake

src\engcore\blindfold\escrow.py:638: EscrowRefused
---------------------------- Captured stderr call -----------------------------
C:\Users\dev_kaeem\Downloads\Compressed\phyx\.venv\Scripts\python.exe: Error while finding module specification for 'engcore.blindfold.escrow_server' (ModuleNotFoundError: No module named 'engcore.blindfold')

_ test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable _

    def test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable():
        without, _, _ = _explicit_runtime(_policy(minimum=0.1), end=2.0)
        remembered_runtime, src, sink = _explicit_runtime(WindowControlPolicy(_q(0.1), 0.5, 4, None, 2.0), end=2.0)
        plain, remembered = _run(without), _run(remembered_runtime)
        # nominal 0.5 s always fails (> 0.25 s): 8 subdivisions without memory; with growth 2, every other window
>       assert _subdivisions(plain) == 8 and _subdivisions(remembered) == 4
E       AssertionError: assert (7 == 8)
E        +  where 7 = _subdivisions(MultiphysicsRunRecord(run_id='wc', graph=PhysicsGraph(graph_id='wc-explicit', participants=(ParticipantSpec(participan...b0b488bfe16e27c9cb1fe030f456af6dc01', end_values=(), scenario_digest='')), termination=None, quantities_of_interest=()))

tests\test_multiphysics_window_control.py:298: AssertionError
=========================== short test summary info ===========================
FAILED tests/foundations/test_v2_blindfold.py::test_the_subprocess_escrow_keeps_its_secrets_in_the_child
FAILED tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable
2 failed, 217 passed in 8.96s
change classes (minimum gate beyond this one):
  doc_only               docs/archive/branch_deltas_2026_10_20/big-13-flagship-demonstrations/README.md -- this gate
  doc_only               docs/archive/branch_deltas_2026_10_20/big-13-flagship-demonstrations/historical.patch -- this gate
  doc_only               docs/archive/branch_deltas_2026_10_20/blind-rediscovery-benchmark-v1/README.md -- this gate
  doc_only               docs/archive/branch_deltas_2026_10_20/blind-rediscovery-benchmark-v1/historical.patch -- this gate
  doc_only               docs/archive/branch_deltas_2026_10_20/evidence-v11/README.md -- this gate
  doc_only               docs/archive/branch_deltas_2026_10_20/evidence-v11/historical.patch -- this gate
  doc_only               docs/archive/branch_deltas_2026_10_20/fix-bisect-table/README.md -- this gate
  doc_only               docs/archive/branch_deltas_2026_10_20/fix-bisect-table/historical.patch -- this gate
  doc_only               docs/work/ACTIVE_PLAN.md -- this gate
  doc_only               docs/work/PROGRESS.md -- this gate
affected test modules: 7 reached by import, mention or source scan
$ 'C:\Users\dev_kaeem\Downloads\Compressed\phyx\.venv\Scripts\python.exe' -m pytest -q tests/test_repository_architecture.py tests/test_core_api_layering.py tests/test_scientific_regression_manifest.py tests/test_forge_check.py tests/test_agent_workflow_contract.py tests/test_capability_completion.py benchmarks/battery_1rc_closure/tests/test_battery_1rc_closure.py benchmarks/battery_1rc_crosscell/tests/test_battery_1rc_crosscell.py benchmarks/battery_1rc_identifiability/tests/test_battery_1rc_identifiability.py tests/foundations/test_v2_blindfold.py tests/test_multiphysics_window_control.py
```
