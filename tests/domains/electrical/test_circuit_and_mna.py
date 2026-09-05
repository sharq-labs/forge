"""Circuit invariants and MNA assembly.

Stamp expectations are written as **explicit matrices derived by hand** from
the documented formulation, never by calling the assembler and recording what
it produced.
"""

from __future__ import annotations

import sys

import numpy as np

from src.engcore.domains.electrical.dc import (
    DCCircuit,
    DCCurrentSource,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    assemble,
)
from src.engcore.scientific import InvalidScientificProblem, Quantity


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


GND = ElectricalNode("gnd", is_reference=True)


# ---- circuit invariants ------------------------------------------------

def test_circuit_requires_exactly_one_reference():
    _raises(
        InvalidScientificProblem, DCCircuit, circuit_id="c",
        nodes=(ElectricalNode("n1"), ElectricalNode("n2")),
    )
    _raises(
        InvalidScientificProblem, DCCircuit, circuit_id="c",
        nodes=(
            ElectricalNode("a", is_reference=True),
            ElectricalNode("b", is_reference=True),
        ),
    )
    ok = DCCircuit(circuit_id="c", nodes=(GND, ElectricalNode("n1")))
    assert ok.reference_node == "gnd"


def test_circuit_rejects_duplicate_ids():
    _raises(
        InvalidScientificProblem, DCCircuit, circuit_id="c",
        nodes=(GND, ElectricalNode("n1"), ElectricalNode("n1")),
    )
    # component ids must be unique across *all* component types
    _raises(
        InvalidScientificProblem, DCCircuit, circuit_id="c",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("X1", "n1", "gnd", Quantity(1.0, "ohm")),),
        voltage_sources=(
            DCVoltageSource("X1", "n1", "gnd", Quantity(1.0, "volt")),
        ),
    )


def test_circuit_rejects_unknown_node_reference():
    _raises(
        InvalidScientificProblem, DCCircuit, circuit_id="c",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "ghost", Quantity(1.0, "ohm")),),
    )


def test_circuit_ordering_is_deterministic_and_insertion_independent():
    nodes = (GND, ElectricalNode("b"), ElectricalNode("a"))
    resistors = (
        Resistor("R2", "a", "gnd", Quantity(1.0, "ohm")),
        Resistor("R1", "b", "gnd", Quantity(1.0, "ohm")),
    )
    circuit = DCCircuit(circuit_id="c", nodes=nodes, resistors=resistors)
    assert circuit.non_reference_node_ids == ("a", "b")

    reordered = DCCircuit(
        circuit_id="c",
        nodes=tuple(reversed(nodes)),
        resistors=tuple(reversed(resistors)),
    )
    assert reordered.non_reference_node_ids == circuit.non_reference_node_ids
    assert np.allclose(assemble(circuit).matrix, assemble(reordered).matrix)


def test_circuit_round_trip():
    circuit = DCCircuit(
        circuit_id="c", description="demo",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt")),
        ),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(1.0, "milliampere")),
        ),
    )
    restored = DCCircuit.from_dict(circuit.to_dict())
    assert restored.to_dict() == circuit.to_dict()
    assert restored.reference_node == "gnd"


# ---- MNA stamps (hand-derived expected matrices) -----------------------

def test_resistor_stamp_two_nodes():
    """R1 = 1 kohm between n1 and n2; R2 = 2 kohm from n2 to ground.

    Hand-derived (G1 = 1e-3 S, G2 = 5e-4 S), node order (n1, n2):
        A = [[ G1,      -G1      ],
             [-G1,   G1 + G2     ]]
    """
    circuit = DCCircuit(
        circuit_id="c",
        nodes=(GND, ElectricalNode("n1"), ElectricalNode("n2")),
        resistors=(
            Resistor("R1", "n1", "n2", Quantity(1.0, "kohm")),
            Resistor("R2", "n2", "gnd", Quantity(2.0, "kohm")),
        ),
    )
    system = assemble(circuit)
    expected = np.array([[1e-3, -1e-3], [-1e-3, 1e-3 + 5e-4]])
    assert system.node_order == ("n1", "n2")
    assert np.allclose(system.matrix, expected)
    assert np.allclose(system.rhs, np.zeros(2))


def test_voltage_source_stamp_shape_and_entries():
    """Single 10 V source and 1 kohm load; hand-derived:

        A = [[1e-3, 1],
             [1,    0]]      z = [0, 10]
    """
    circuit = DCCircuit(
        circuit_id="c",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt")),
        ),
    )
    system = assemble(circuit)
    assert system.size == 2 and system.n_nodes == 1 and system.n_sources == 1
    assert np.allclose(system.matrix, np.array([[1e-3, 1.0], [1.0, 0.0]]))
    assert np.allclose(system.rhs, np.array([0.0, 10.0]))


def test_current_source_stamp_sign_and_reversal():
    """2 mA from ground into n1 injects +2 mA at n1; reversing the terminals
    must flip the sign and nothing else."""
    def build(from_node, to_node):
        return assemble(
            DCCircuit(
                circuit_id="c",
                nodes=(GND, ElectricalNode("n1")),
                resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
                current_sources=(
                    DCCurrentSource(
                        "I1", from_node, to_node, Quantity(2.0, "milliampere")
                    ),
                ),
            )
        )

    forward = build("gnd", "n1")
    reverse = build("n1", "gnd")
    assert np.allclose(forward.rhs, np.array([2e-3]))
    assert np.allclose(reverse.rhs, np.array([-2e-3]))
    assert np.allclose(forward.matrix, reverse.matrix)


def test_matrix_dimensions_scale_with_nodes_and_sources():
    circuit = DCCircuit(
        circuit_id="c",
        nodes=(
            GND, ElectricalNode("n1"), ElectricalNode("n2"), ElectricalNode("n3"),
        ),
        resistors=(
            Resistor("R1", "n1", "n2", Quantity(1.0, "kohm")),
            Resistor("R2", "n2", "n3", Quantity(1.0, "kohm")),
            Resistor("R3", "n3", "gnd", Quantity(1.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(5.0, "volt")),
            DCVoltageSource("V2", "n2", "gnd", Quantity(2.0, "volt")),
        ),
    )
    system = assemble(circuit)
    assert system.n_nodes == 3 and system.n_sources == 2
    assert system.matrix.shape == (5, 5)
    assert system.voltage_source_order == ("V1", "V2")


def test_reference_node_is_eliminated_not_indexed():
    circuit = DCCircuit(
        circuit_id="c",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "ohm")),),
    )
    system = assemble(circuit)
    assert "gnd" not in system.node_index
    # the reference potential is exactly zero by definition, not solved for
    assert system.node_voltage(np.array([3.0]), "gnd") == 0.0
    assert system.node_voltage(np.array([3.0]), "n1") == 3.0


def _all_tests():
    module = sys.modules[__name__]
    return [
        (n, getattr(module, n))
        for n in sorted(dir(module))
        if n.startswith("test_") and callable(getattr(module, n))
    ]


def main() -> int:
    failures = 0
    for name, test in _all_tests():
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    total = len(_all_tests())
    print(f"circuit+mna: {'FAIL' if failures else 'PASS'} "
          f"({total - failures}/{total})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
