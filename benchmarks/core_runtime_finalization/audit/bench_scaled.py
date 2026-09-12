"""Part E: the same tiny solve at 100 / 1,000 / 10,000 / 100,000 evaluations.

Reports wall time, throughput and the framework/numerical split at each scale,
so a reader can see whether the per-evaluation cost is flat -- which is the
question, because a cost that grows with the count is a retention bug wearing a
performance costume.

    python -X utf8 benchmarks/core_runtime_finalization/audit/bench_scaled.py
"""

from __future__ import annotations

import gc
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bench_parallel_workload import circuit  # noqa: E402
from engcore.domains.electrical.dc.problem import build_dc_problem  # noqa: E402
from engcore.domains.electrical.dc.solver import (  # noqa: E402
    ElectricalDCSolver, solve_circuit,
)

SCALES = (100, 1_000, 10_000, 100_000)


def numerical_per_solve() -> float:
    """Seconds for prepare+solve alone, averaged over many repetitions."""
    base = circuit(0)
    solver = ElectricalDCSolver()
    problem = build_dc_problem(base)
    solver.bind_circuit(base, problem.problem_id)
    prepared = solver.prepare(problem)
    for _ in range(200):
        solver.solve(prepared)
    gc.collect()
    start = time.perf_counter()
    for _ in range(5_000):
        solver.solve(prepared)
    return (time.perf_counter() - start) / 5_000


def main() -> int:
    numeric = numerical_per_solve()
    rows = []
    print(f"{'evaluations':>12} {'wall s':>10} {'eval/sec':>11} "
          f"{'us/eval':>9} {'framework%':>11} {'numerical%':>11}")
    print("-" * 70)

    for count in SCALES:
        # Warm, then measure. Circuits vary by index so no cache makes later
        # evaluations free.
        for i in range(50):
            solve_circuit(circuit(i), run_id=f"warm-{i}")
        gc.collect()
        start = time.perf_counter()
        for i in range(count):
            solve_circuit(circuit(i), run_id=f"s-{count}-{i}")
        elapsed = time.perf_counter() - start

        per = elapsed / count
        share = (per - numeric) / per
        rows.append({
            "evaluations": count, "wall_s": elapsed,
            "per_eval_us": per * 1e6, "eval_per_sec": count / elapsed,
            "framework_share": share, "numerical_share": 1.0 - share,
        })
        print(f"{count:>12,} {elapsed:>10.3f} {count/elapsed:>11,.0f} "
              f"{per*1e6:>9.1f} {share*100:>10.1f}% {(1-share)*100:>10.1f}%")

    flat = rows[-1]["per_eval_us"] / rows[0]["per_eval_us"]
    print(f"\nper-evaluation cost at 100,000 relative to 100: {flat:.3f}x "
          f"({'flat' if 0.8 < flat < 1.25 else 'NOT FLAT -- investigate'})")

    out = ROOT / "benchmarks" / "core_runtime_finalization" / "SCALED.json"
    out.write_bytes(json.dumps(
        {"numerical_per_solve_us": numeric * 1e6, "rows": rows,
         "flatness_100k_over_100": flat}, indent=2).encode("utf-8"))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
