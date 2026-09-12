"""The sprint's headline numbers: workload matrix, scaling, memory, workers.

Deterministic by construction — no RNG, no clock in any input, no case files —
so the same workload is built on every machine and two result files are
comparable. Run against a checkout:

    python benchmarks/performance_campaign/bench_campaign.py <label> [out.json]

The campaign path is driven through ``engcore.execution`` where it exists and
through a plain loop where it does not, so the same script measures a tree from
before this sprint and one from after it. What is compared is the work, not the
abstraction.
"""

from __future__ import annotations

import json
import pathlib
import platform
import sys
import time
import tracemalloc
from typing import Any, Callable

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from engcore.domains.electrical.dc import (  # noqa: E402
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    solve_circuit,
)
from engcore.scientific.units.quantity import Quantity  # noqa: E402

GND = ElectricalNode("gnd", is_reference=True)
R2 = Quantity(3.0, "kohm")
SUPPLY = Quantity(12.0, "volt")

try:
    from engcore.execution import (
        SharedContext,
        SweepDefinition,
        cases_from,
        run_sweep,
    )

    HAS_SWEEP = True
except Exception:  # a tree from before the sweep layer existed
    HAS_SWEEP = False


def build_circuit(case_id: str, r1_kohm: float) -> DCCircuit:
    return DCCircuit(
        circuit_id=f"divider-{case_id}",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(r1_kohm, "kohm")),
            Resistor("R2", "mid", "gnd", R2),
        ),
        voltage_sources=(DCVoltageSource("V1", "top", "gnd", SUPPLY),),
    )


def loop_campaign(count: int) -> int:
    """The baseline every tree can run: a plain loop."""
    done = 0
    for index in range(count):
        solve_circuit(build_circuit(f"{index:06d}", 1.0 + index * 0.001),
                      run_id=f"c{index:06d}")
        done += 1
    return done


def sweep_campaign(count: int, workers: int = 1) -> int:
    def operation(shared, case):
        return solve_circuit(
            build_circuit(case.case_id, case.inputs["r1_kohm"]), run_id=case.case_id
        )

    definition = SweepDefinition(
        sweep_id=f"dc-{count}",
        operation=operation,
        cases=cases_from("dc", [{"r1_kohm": 1.0 + i * 0.001} for i in range(count)]),
        shared=SharedContext({"r2": R2, "supply": SUPPLY}),
    )
    summary = run_sweep(definition, workers=workers)
    if summary.failed:
        raise SystemExit(f"{summary.failed} case(s) failed")
    return summary.succeeded


def timed(operation: Callable[[], Any]) -> dict[str, Any]:
    """Wall time with nothing else running.

    `tracemalloc` is deliberately NOT enabled here. It roughly halves
    throughput, and the first draft of this file measured time and memory in
    one pass — which reported the campaign at 760 cases/s while the worker
    measurement beside it, without tracemalloc, reported 1,970 for the same
    work. A number produced under a profiler describes the profiler.
    """
    started = time.perf_counter()
    produced = operation()
    return {"seconds": time.perf_counter() - started, "produced": produced}


def peak_memory(operation: Callable[[], Any]) -> int:
    """Peak allocation for the same work, measured in its own pass."""
    tracemalloc.start()
    try:
        operation()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def field_solves() -> dict[str, Any]:
    try:
        from engcore.domains.thermal_models.conduction2d import assemble, solve_steady_conduction
        from tests.manufactured_conduction2d import SINE_PLATE, square
    except Exception as exc:  # pragma: no cover
        return {"unavailable": str(exc)}

    rows: dict[str, Any] = {}
    for nodes in (32, 64, 128):
        problem = SINE_PLATE.problem(square(nodes))
        solve_steady_conduction(problem, run_id="warm")
        started = time.perf_counter()
        assemble(problem)
        assembly = time.perf_counter() - started
        whole = timed(lambda p=problem: solve_steady_conduction(p, run_id="bench"))
        rows[f"{nodes}x{nodes}"] = {
            "assemble_seconds": assembly,
            "solve_seconds": whole["seconds"],
        }
    return rows


def main(argv: list[str]) -> int:
    label = argv[1] if len(argv) > 1 else "unlabelled"
    out_path = pathlib.Path(argv[2]) if len(argv) > 2 else None

    # Warm every import and cache before anything is timed.
    loop_campaign(5)

    results: dict[str, Any] = {
        "label": label,
        "has_sweep": HAS_SWEEP,
        "machine": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "campaign_loop": {},
        "campaign_sweep": {},
        "workers": {},
        "field": {},
    }

    for count in (100, 1_000, 10_000):
        measured = timed(lambda c=count: loop_campaign(c))
        peak = peak_memory(lambda c=count: loop_campaign(c))
        results["campaign_loop"][str(count)] = {
            "seconds": measured["seconds"],
            "cases_per_second": count / measured["seconds"],
            "peak_bytes": peak,
        }
        print(
            f"loop  {count:>6}: {measured['seconds']:8.3f} s  "
            f"{count / measured['seconds']:>9,.0f} cases/s  "
            f"peak {peak / 1e6:7.1f} MB"
        )

    if HAS_SWEEP:
        for count in (100, 1_000, 10_000):
            measured = timed(lambda c=count: sweep_campaign(c))
            peak = peak_memory(lambda c=count: sweep_campaign(c))
            results["campaign_sweep"][str(count)] = {
                "seconds": measured["seconds"],
                "cases_per_second": count / measured["seconds"],
                "peak_bytes": peak,
            }
            print(
                f"sweep {count:>6}: {measured['seconds']:8.3f} s  "
                f"{count / measured['seconds']:>9,.0f} cases/s  "
                f"peak {peak / 1e6:7.1f} MB"
            )

        for workers in (1, 2, 4):
            measured = timed(lambda w=workers: sweep_campaign(2_000, workers=w))
            results["workers"][str(workers)] = {
                "seconds": measured["seconds"],
                "cases_per_second": 2_000 / measured["seconds"],
            }
            print(
                f"workers {workers}: {measured['seconds']:8.3f} s  "
                f"{2_000 / measured['seconds']:>9,.0f} cases/s"
            )

    results["field"] = field_solves()
    for name, row in results["field"].items():
        if isinstance(row, dict) and "assemble_seconds" in row:
            print(
                f"field {name:>9}: assemble {row['assemble_seconds'] * 1e3:7.1f} ms  "
                f"solve {row['solve_seconds'] * 1e3:7.1f} ms"
            )

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
