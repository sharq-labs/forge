"""Where a tiny solve's time actually goes, measured rather than guessed.

Two questions, deliberately separated because they have different answers:

1. **Framework vs numerical share.** Measured on a real DC solve through the
   production path -- ``solve_circuit`` -- because that is the only shape that
   HAS a numerical part. The numerical part is the MNA assemble-and-solve; the
   framework part is everything the core does to turn that answer into an
   attributable, checked, serialized record.

2. **Which framework stage costs what.** Measured by cProfile over many
   repetitions, reported by cumulative and by self time, because the two answer
   different questions -- "what is this call tree worth" and "where is the
   interpreter actually spending cycles".

Nothing here edits a domain. ``solve_circuit`` is READ and CALLED.

    python -X utf8 benchmarks/core_runtime_finalization/audit/profile_hot_path.py
"""

from __future__ import annotations

import cProfile
import gc
import io
import json
import pathlib
import pstats
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from engcore.domains.electrical.dc.circuit import DCCircuit  # noqa: E402
from engcore.domains.electrical.dc.components import (  # noqa: E402
    DCVoltageSource, ElectricalNode, Resistor,
)
from engcore.domains.electrical.dc.problem import build_dc_problem  # noqa: E402
from engcore.domains.electrical.dc.solver import ElectricalDCSolver, solve_circuit  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402


def tiny_circuit() -> DCCircuit:
    """Three nodes, two resistors, one source. About as small as a solve gets."""
    return DCCircuit(
        circuit_id="perf.tiny",
        nodes=(
            ElectricalNode(node_id="gnd", is_reference=True),
            ElectricalNode(node_id="n1"),
            ElectricalNode(node_id="n2"),
        ),
        resistors=(
            Resistor(component_id="R1", node_a="n1", node_b="n2",
                     resistance=Quantity(4.7, "kiloohm")),
            Resistor(component_id="R2", node_a="n2", node_b="gnd",
                     resistance=Quantity(2.2, "kiloohm")),
        ),
        voltage_sources=(
            DCVoltageSource(component_id="V1", positive_node="n1",
                            negative_node="gnd", voltage=Quantity(12.0, "volt")),
        ),
        current_sources=(),
    )


def timed(operation, *, samples: int, warmup: int = 50) -> dict:
    """P50/P95/min over many samples, GC disabled inside the measured region.

    Repeated and percentile-reported rather than one-shot: this machine's
    clocks move under turbo and thermal control, and a single number is not
    reproducible even against itself.
    """
    for _ in range(warmup):
        operation()
    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        values = []
        for _ in range(samples):
            start = time.perf_counter()
            operation()
            values.append((time.perf_counter() - start) * 1000.0)
    finally:
        if was_enabled:
            gc.enable()
    values.sort()
    return {
        "samples": samples,
        "p50_ms": statistics.median(values),
        "p95_ms": values[int(0.95 * (len(values) - 1))],
        "min_ms": values[0],
        "mean_ms": statistics.fmean(values),
    }


def numerical_only(circuit: DCCircuit) -> dict:
    """The solve alone: prepare + solve, no result, no validation, no provenance."""
    solver = ElectricalDCSolver()
    problem = build_dc_problem(circuit)
    solver.bind_circuit(circuit, problem.problem_id)
    prepared = solver.prepare(problem)
    return timed(lambda: solver.solve(prepared), samples=3000)


def full_path(circuit: DCCircuit) -> dict:
    counter = {"n": 0}

    def once():
        counter["n"] += 1
        solve_circuit(circuit, run_id=f"perf-{counter['n']}")

    return timed(once, samples=600)


def profile(circuit: DCCircuit, repetitions: int = 400) -> tuple[str, str]:
    counter = {"n": 0}

    def body():
        for _ in range(repetitions):
            counter["n"] += 1
            solve_circuit(circuit, run_id=f"prof-{counter['n']}")

    profiler = cProfile.Profile()
    profiler.enable()
    body()
    profiler.disable()

    by_cumulative = io.StringIO()
    pstats.Stats(profiler, stream=by_cumulative).sort_stats("cumulative").print_stats(22)
    by_self = io.StringIO()
    pstats.Stats(profiler, stream=by_self).sort_stats("tottime").print_stats(22)
    return by_cumulative.getvalue(), by_self.getvalue()


def main() -> int:
    circuit = tiny_circuit()

    numeric = numerical_only(circuit)
    whole = full_path(circuit)
    framework_ms = whole["p50_ms"] - numeric["p50_ms"]
    share = framework_ms / whole["p50_ms"]

    print("=" * 72)
    print("TINY DC SOLVE -- framework vs numerical")
    print("=" * 72)
    print(f"  full path   p50 {whole['p50_ms']:.4f} ms   p95 {whole['p95_ms']:.4f}   "
          f"min {whole['min_ms']:.4f}   ({whole['samples']} samples)")
    print(f"  numerical   p50 {numeric['p50_ms']:.4f} ms   p95 {numeric['p95_ms']:.4f}   "
          f"min {numeric['min_ms']:.4f}   ({numeric['samples']} samples)")
    print(f"  framework   p50 {framework_ms:.4f} ms")
    print(f"  FRAMEWORK SHARE  {share*100:.1f} %      numerical {100-share*100:.1f} %")
    print(f"  throughput  {1000.0/whole['p50_ms']:.0f} solves/sec")

    cumulative, selftime = profile(circuit)
    print("\n" + "=" * 72)
    print("BY CUMULATIVE TIME")
    print("=" * 72)
    print(cumulative)
    print("=" * 72)
    print("BY SELF TIME")
    print("=" * 72)
    print(selftime)

    out = ROOT / "benchmarks" / "core_runtime_finalization" / "PROFILE.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(
        {"full_path": whole, "numerical": numeric,
         "framework_ms": framework_ms, "framework_share": share},
        indent=2).encode("utf-8"))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
