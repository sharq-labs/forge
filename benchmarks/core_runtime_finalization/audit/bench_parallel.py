"""Does parallel execution actually help. Measured, on three workload shapes.

Sprint 7 found thread-based execution SLOWER and shipped it anyway as an
option. This round has to decide whether to ship a process backend, keep
threads, or freeze sequential -- and the rule is that parallelism is not
shipped because it sounds useful.

Three shapes, because they have different answers:

A. TINY CPU-LIGHT   trivial per-case work; dominated by dispatch overhead
B. MEDIUM           one production DC solve per case; the real Core shape
C. HEAVY            a grid of DC solves per case; enough work to amortise

The process prototype here is NOT the shipped backend. It exists to answer
"would a process backend be worth building" before any is built. If the answer
is no, nothing gets built and the report says so.

    python -X utf8 benchmarks/core_runtime_finalization/audit/bench_parallel.py
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from engcore.execution.sweep import (  # noqa: E402
    FailurePolicy, SharedContext, SweepCase, SweepDefinition, run_sweep,
)


# --- the three workloads, defined at module scope so processes can pickle them

def tiny_operation(shared, case):
    """CPU-light: a little arithmetic and a dict. Dispatch dominates."""
    n = int(case.inputs["n"])
    return {"case": case.case_id, "value": sum(i * i for i in range(n))}


def medium_operation(shared, case):
    """One production DC solve: the shape the Core actually runs."""
    from bench_parallel_workload import one_dc_solve

    return one_dc_solve(int(case.inputs["seed"]))


def medium_full_operation(shared, case):
    """One DC solve returning the WHOLE ScientificResult -- the real payload."""
    from bench_parallel_workload import one_dc_solve_full

    return one_dc_solve_full(int(case.inputs["seed"]))


def heavy_operation(shared, case):
    """Twenty production DC solves per case: enough work to amortise dispatch."""
    from bench_parallel_workload import many_dc_solves

    return many_dc_solves(int(case.inputs["seed"]), 20)


WORKLOADS = {
    "A_tiny_cpu_light": (tiny_operation, {"n": 200}, 400),
    "B_medium_one_solve": (medium_operation, {"seed": 1}, 200),
    "C_heavy_twenty_solves": (heavy_operation, {"seed": 1}, 40),
    "D_medium_full_result": (medium_full_operation, {"seed": 1}, 200),
}


def definition(name, operation, inputs, cases) -> SweepDefinition:
    return SweepDefinition(
        sweep_id=f"par-{name}",
        operation=operation,
        cases=tuple(
            SweepCase(case_id=f"c{i}", inputs={**inputs, "seed": i})
            for i in range(cases)
        ),
        shared=SharedContext(),
        on_failure=FailurePolicy.CONTINUE,
        description=name,
    )


def timed(fn, *, rounds: int = 5) -> dict:
    """Best-of and median over repeated rounds: one wall-clock number is noise."""
    times = []
    fn()  # warm
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return {"median_s": statistics.median(times), "min_s": min(times)}


def run_threads(defn, workers):
    return timed(lambda: run_sweep(defn, workers=workers))


def _process_case(payload):
    """Top-level so it is picklable. Rebuilds the case inside the child."""
    name, case_id, inputs = payload
    operation, _, _ = WORKLOADS[name]
    case = SweepCase(case_id=case_id, inputs=inputs)
    return operation(SharedContext(), case)


def run_processes(name, defn, workers, *, reuse_pool: bool):
    """A PROTOTYPE, not a backend. Measures whether one would be worth building.

    Measured BOTH ways, because the difference is the whole question:

    ``reuse_pool=False``
        a pool per sweep -- what a naive backend does, and what a caller
        running one sweep actually pays, spin-up included.
    ``reuse_pool=True``
        a pool created once and reused -- the best case a process backend could
        ever reach, with startup and interpreter import amortised to zero.

    Deferring on the first number alone would be deferring on a measurement
    biased against processes. The second is the fair upper bound.
    """
    payloads = [(name, c.case_id, dict(c.inputs)) for c in defn.cases]
    chunk = max(1, len(payloads) // (workers * 4))

    if not reuse_pool:
        def once():
            with ProcessPoolExecutor(max_workers=workers) as pool:
                return list(pool.map(_process_case, payloads, chunksize=chunk))

        return timed(once, rounds=3)

    pool = ProcessPoolExecutor(max_workers=workers)
    try:
        # Warm the children: the first map pays interpreter start and every
        # import, which is exactly the cost this variant exists to exclude.
        list(pool.map(_process_case, payloads, chunksize=chunk))
        return timed(
            lambda: list(pool.map(_process_case, payloads, chunksize=chunk)),
            rounds=3,
        )
    finally:
        pool.shutdown(wait=True)


def main() -> int:
    results = {}
    print(f"{'workload':<24} {'backend':<12} {'workers':>7} {'median s':>10} "
          f"{'cases/sec':>10} {'speedup':>8}")
    print("-" * 78)

    for name, (operation, inputs, cases) in WORKLOADS.items():
        defn = definition(name, operation, inputs, cases)
        baseline = run_threads(defn, 1)
        results[name] = {"cases": cases, "sequential": baseline}
        print(f"{name:<24} {'sequential':<12} {1:>7} {baseline['median_s']:>10.4f} "
              f"{cases/baseline['median_s']:>10.1f} {1.0:>8.2f}")

        for workers in (2, 4):
            threaded = run_threads(defn, workers)
            results[name][f"threads_{workers}"] = threaded
            print(f"{name:<24} {'threads':<12} {workers:>7} {threaded['median_s']:>10.4f} "
                  f"{cases/threaded['median_s']:>10.1f} "
                  f"{baseline['median_s']/threaded['median_s']:>8.2f}")

        for reuse, label in ((False, "proc/new"), (True, "proc/reused")):
            for workers in (2, 4):
                try:
                    procs = run_processes(name, defn, workers, reuse_pool=reuse)
                except Exception as exc:  # noqa: BLE001 - reported, not hidden
                    print(f"{name:<24} {label:<12} {workers:>7} "
                          f"FAILED: {type(exc).__name__}: {exc}")
                    results[name][f"{label}_{workers}"] = {"error": str(exc)}
                    continue
                results[name][f"{label}_{workers}"] = procs
                print(f"{name:<24} {label:<12} {workers:>7} {procs['median_s']:>10.4f} "
                      f"{cases/procs['median_s']:>10.1f} "
                      f"{baseline['median_s']/procs['median_s']:>8.2f}")
        print()

    out = ROOT / "benchmarks" / "core_runtime_finalization" / "PARALLEL.json"
    out.write_bytes(json.dumps(results, indent=2).encode("utf-8"))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    raise SystemExit(main())
