"""The DC workloads the parallel benchmark runs, importable from a child process.

Separate module so a ProcessPoolExecutor child can import it by name. Nothing
here edits a domain: `solve_circuit` is called, never modified.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from engcore.domains.electrical.dc.circuit import DCCircuit  # noqa: E402
from engcore.domains.electrical.dc.components import (  # noqa: E402
    DCVoltageSource, ElectricalNode, Resistor,
)
from engcore.domains.electrical.dc.solver import solve_circuit  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402


def circuit(seed: int) -> DCCircuit:
    """A tiny circuit whose element values depend on the seed.

    Varying by seed so a cache cannot make later cases free and flatter the
    parallel numbers.
    """
    return DCCircuit(
        circuit_id=f"par.{seed}",
        nodes=(
            ElectricalNode(node_id="gnd", is_reference=True),
            ElectricalNode(node_id="n1"),
            ElectricalNode(node_id="n2"),
        ),
        resistors=(
            Resistor(component_id="R1", node_a="n1", node_b="n2",
                     resistance=Quantity(4.7 + (seed % 10) * 0.1, "kiloohm")),
            Resistor(component_id="R2", node_a="n2", node_b="gnd",
                     resistance=Quantity(2.2 + (seed % 7) * 0.1, "kiloohm")),
        ),
        voltage_sources=(
            DCVoltageSource(component_id="V1", positive_node="n1",
                            negative_node="gnd",
                            voltage=Quantity(12.0 + (seed % 5), "volt")),
        ),
        current_sources=(),
    )


def one_dc_solve(seed: int) -> dict:
    result = solve_circuit(circuit(seed), run_id=f"par-{seed}")
    return {
        "result_id": result.result_id,
        "n2": result.value("node_voltage:n2").magnitude_in("volt"),
    }


def many_dc_solves(seed: int, count: int) -> dict:
    last = None
    for index in range(count):
        last = solve_circuit(circuit(seed * 1000 + index),
                             run_id=f"par-{seed}-{index}")
    return {
        "result_id": last.result_id,
        "n2": last.value("node_voltage:n2").magnitude_in("volt"),
        "solves": count,
    }


def one_dc_solve_full(seed: int):
    """The SAME solve, returning the whole ScientificResult.

    This is what a real process backend must transport. `one_dc_solve` returns
    a small summary dict, which understates the cost of the boundary by leaving
    out exactly the object the Core exists to produce.
    """
    return solve_circuit(circuit(seed), run_id=f"par-{seed}")


def many_dc_solves_full(seed: int, count: int):
    return [
        solve_circuit(circuit(seed * 1000 + index), run_id=f"par-{seed}-{index}")
        for index in range(count)
    ]
