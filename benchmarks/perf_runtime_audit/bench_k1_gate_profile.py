"""PERF-0 — where the verification gate's time actually goes.

Profiles the gate on the *oscillatory* configuration used by the suite's single
slowest test, which declares ``n_output_points=20001`` — ten times the domain
default. That makes it the configuration where both suspected costs are largest:
the duplicated finest integration, and the conversion of the dense trajectory
into Python lists.

Measurement only. The gate is executed exactly as the suite executes it.

    python benchmarks/perf_runtime_audit/bench_k1_gate_profile.py
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from src.engcore.domains.kinetics.cstr import solver as cstr_solver  # noqa: E402
from src.engcore.domains.kinetics.cstr.validation import (  # noqa: E402
    run_verification_gate,
)

# The oscillatory configuration from
# tests/domains/kinetics/test_cstr_domain.py — reproduced here rather than
# imported so the benchmark cannot drift the test's fixtures.
from tests.domains.kinetics.test_cstr_domain import (  # noqa: E402
    operation,
    reactor,
)


def build_oscillatory():
    return reactor(
        "oscillatory", op=operation(tc=305.0, end=6000.0), t0=300.0, npts=20001
    )


def time_gate(repeats: int) -> dict[str, Any]:
    run = build_oscillatory()
    samples: list[float] = []
    report = None
    for _ in range(repeats):
        started = time.perf_counter()
        report = run_verification_gate(run, run_id_prefix="osc-gate")
        samples.append(time.perf_counter() - started)
    samples.sort()
    return {
        "median_s": statistics.median(samples),
        "min_s": samples[0],
        "max_s": samples[-1],
        "repeats": repeats,
        "tolerance_independent": report.tolerance_independent,
        "levels_earned": [level.value for level in report.levels_earned],
        "rungs": len(report.rungs),
    }


def profile_gate() -> str:
    run = build_oscillatory()
    profiler = cProfile.Profile()
    profiler.enable()
    run_verification_gate(run, run_id_prefix="osc-gate")
    profiler.disable()
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(28)
    return stream.getvalue()


def measure_list_conversion(n: int, repeats: int) -> dict[str, Any]:
    """Cost of the ndarray -> Python list conversion the solver performs.

    Three arrays of ``n`` points each, which is exactly what ``solve`` builds
    for ``grid_time_s``, ``grid_concentration_mol_per_m3`` and
    ``grid_temperature_k`` on every completed solve.
    """
    arrays = [np.linspace(0.0, 1.0, n) for _ in range(3)]
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        converted = [[float(v) for v in a] for a in arrays]
        samples.append(time.perf_counter() - started)
        del converted
    samples.sort()

    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    converted = [[float(v) for v in a] for a in arrays]
    after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    del converted

    return {
        "points_per_array": n,
        "arrays": 3,
        "median_s": statistics.median(samples),
        "min_s": samples[0],
        "python_float_objects": 3 * n,
        "traced_bytes": int(after - before),
        "ndarray_bytes": int(sum(a.nbytes for a in arrays)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "gate_oscillatory_20001_points": time_gate(args.repeats),
        "list_conversion": {
            "default_2001": measure_list_conversion(2001, 20),
            "oscillatory_20001": measure_list_conversion(20001, 10),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.profile:
        text = profile_gate()
        print(text)
        payload["cprofile_top"] = text
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
