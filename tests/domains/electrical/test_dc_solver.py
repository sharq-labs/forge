"""Analytical reference cases and failure behaviour for the DC solver.

Every expected value below is derived by hand from circuit theory in the
comment above it. None is produced by running the MNA solver — otherwise a
stamping bug and the test would agree with each other and both be wrong.
"""

from __future__ import annotations

import sys

from src.engcore.domains.electrical.dc import (
    DCCircuit,
    DCCurrentSource,
    DCVoltageSource,
    ElectricalDCSolver,
    ElectricalNode,
    Resistor,
    solve_circuit,
)
from src.engcore.scientific import ConvergenceState, Quantity, ValidationOutcome

GND = ElectricalNode("gnd", is_reference=True)
TOL = 1e-9


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


def _close(quantity: Quantity, expected: float, unit: str, tol: float = TOL) -> bool:
    return abs(quantity.magnitude_in(unit) - expected) <= tol


def _solved(circuit: DCCircuit, run_id: str = "t"):
    result = solve_circuit(circuit, run_id=run_id)
    assert result.convergence is ConvergenceState.CONVERGED, result.warnings
    assert result.validation.status is ValidationOutcome.PASS
    return result


# =====================================================================
# CASE A — single resistor load
# 10 V across 1 kohm.  I = V/R = 10/1000 = 10 mA.  P = I^2 R = 0.1 W.
# =====================================================================

def test_case_a_single_resistor_load():
    circuit = DCCircuit(
        circuit_id="case_a",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt")),
        ),
    )
    result = _solved(circuit, "case-a")
    assert _close(result.value("node_voltage:n1"), 10.0, "volt")
    assert _close(result.value("node_voltage:gnd"), 0.0, "volt")
    assert _close(result.value("resistor_current:R1"), 0.010, "ampere")
    assert _close(result.value("resistor_power:R1"), 0.100, "watt")
    # The source current is defined leaving the positive node through the
    # source, so a delivering source reports a negative branch current.
    assert _close(result.value("source_current:V1"), -0.010, "ampere")
    assert _close(result.value("source_power:V1"), -0.100, "watt")
    assert _close(result.value("total_source_delivered_power"), 0.100, "watt")


# =====================================================================
# CASE B — equal divider.  10 V over R1 = R2 = 1 kohm in series.
# I = 10/2000 = 5 mA;  V(mid) = I*R2 = 5 V.
# =====================================================================

def test_case_b_equal_voltage_divider():
    circuit = DCCircuit(
        circuit_id="case_b",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(1.0, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(1.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "top", "gnd", Quantity(10.0, "volt")),
        ),
    )
    result = _solved(circuit, "case-b")
    assert _close(result.value("node_voltage:mid"), 5.0, "volt")
    assert _close(result.value("resistor_current:R1"), 0.005, "ampere")
    assert _close(result.value("resistor_current:R2"), 0.005, "ampere")


# =====================================================================
# CASE C — unequal divider.  12 V, R1 = 1 kohm (top->mid), R2 = 3 kohm.
# V(mid) = 12 * 3/(1+3) = 9 V;  I = 12/4000 = 3 mA.
# P(R1) = I^2*1000 = 9 mW;  P(R2) = I^2*3000 = 27 mW.
# =====================================================================

def test_case_c_unequal_voltage_divider():
    circuit = DCCircuit(
        circuit_id="case_c",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(1.0, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),
        ),
    )
    result = _solved(circuit, "case-c")
    assert _close(result.value("node_voltage:mid"), 9.0, "volt")
    assert _close(result.value("resistor_current:R1"), 0.003, "ampere")
    assert _close(result.value("resistor_power:R1"), 0.009, "watt")
    assert _close(result.value("resistor_power:R2"), 0.027, "watt")


# =====================================================================
# CASE D — parallel branches.  12 V across R1 = 2 kohm and R2 = 4 kohm.
# I1 = 12/2000 = 6 mA;  I2 = 12/4000 = 3 mA;  total 9 mA.
# =====================================================================

def test_case_d_parallel_branches():
    circuit = DCCircuit(
        circuit_id="case_d",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(
            Resistor("R1", "n1", "gnd", Quantity(2.0, "kohm")),
            Resistor("R2", "n1", "gnd", Quantity(4.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(12.0, "volt")),
        ),
    )
    result = _solved(circuit, "case-d")
    assert _close(result.value("resistor_current:R1"), 0.006, "ampere")
    assert _close(result.value("resistor_current:R2"), 0.003, "ampere")
    assert _close(result.value("source_current:V1"), -0.009, "ampere")


# =====================================================================
# CASE E — current source into a resistor.
# 2 mA injected at n1, 3 kohm to ground:  V = I*R = 0.002*3000 = 6 V.
# Source delivers P = V*I = 12 mW.
# =====================================================================

def test_case_e_current_source_and_resistor():
    circuit = DCCircuit(
        circuit_id="case_e",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(3.0, "kohm")),),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(2.0, "milliampere")),
        ),
    )
    result = _solved(circuit, "case-e")
    assert _close(result.value("node_voltage:n1"), 6.0, "volt")
    assert _close(result.value("resistor_power:R1"), 0.012, "watt")
    # absorbed by the source = (V_from - V_to)*I = (0 - 6)*0.002 = -12 mW
    assert _close(result.value("current_source_power:I1"), -0.012, "watt")


# =====================================================================
# CASE F — mixed sources.
# V1 = 10 V at n1; R1 = 1 kohm n1->n2; R2 = 1 kohm n2->gnd;
# I1 = 1 mA injected at n2.
# KCL at n2: (V2-10)/1000 + V2/1000 - 0.001 = 0
#         => (V2-10) + V2 - 1 = 0  =>  2*V2 = 11  =>  V2 = 5.5 V
# I(R1) = (10-5.5)/1000 = 4.5 mA;  I(R2) = 5.5/1000 = 5.5 mA
# =====================================================================

def test_case_f_mixed_voltage_and_current_sources():
    circuit = DCCircuit(
        circuit_id="case_f",
        nodes=(GND, ElectricalNode("n1"), ElectricalNode("n2")),
        resistors=(
            Resistor("R1", "n1", "n2", Quantity(1.0, "kohm")),
            Resistor("R2", "n2", "gnd", Quantity(1.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt")),
        ),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n2", Quantity(1.0, "milliampere")),
        ),
    )
    result = _solved(circuit, "case-f")
    assert _close(result.value("node_voltage:n2"), 5.5, "volt")
    assert _close(result.value("resistor_current:R1"), 0.0045, "ampere")
    assert _close(result.value("resistor_current:R2"), 0.0055, "ampere")
    # V1 supplies only the R1 branch: 4.5 mA leaves n1 through R1, so the
    # source branch current is -4.5 mA.
    assert _close(result.value("source_current:V1"), -0.0045, "ampere")


# =====================================================================
# CASE G — negative source polarity.
# V1 = -5 V at n1 w.r.t. ground, 1 kohm load.
# V(n1) = -5 V;  I(R1) = -5/1000 = -5 mA (flows gnd -> n1);
# P(R1) = (-5)*(-0.005) = 25 mW, still positive (absorbed).
# =====================================================================

def test_case_g_negative_source_polarity():
    circuit = DCCircuit(
        circuit_id="case_g",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(-5.0, "volt")),
        ),
    )
    result = _solved(circuit, "case-g")
    assert _close(result.value("node_voltage:n1"), -5.0, "volt")
    assert _close(result.value("resistor_current:R1"), -0.005, "ampere")
    assert _close(result.value("resistor_power:R1"), 0.025, "watt")
    assert result.value("resistor_power:R1").magnitude > 0.0


def test_reversed_source_terminals_flip_sign_only():
    """Swapping + and - terminals negates the node voltage and current."""
    def build(positive, negative):
        return solve_circuit(
            DCCircuit(
                circuit_id="polarity",
                nodes=(GND, ElectricalNode("n1")),
                resistors=(
                    Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),
                ),
                voltage_sources=(
                    DCVoltageSource("V1", positive, negative, Quantity(5.0, "volt")),
                ),
            ),
            run_id="pol",
        )

    forward = build("n1", "gnd")
    reverse = build("gnd", "n1")
    assert _close(forward.value("node_voltage:n1"), 5.0, "volt")
    assert _close(reverse.value("node_voltage:n1"), -5.0, "volt")
    # dissipation is polarity independent
    assert _close(forward.value("resistor_power:R1"), 0.025, "watt")
    assert _close(reverse.value("resistor_power:R1"), 0.025, "watt")


# =====================================================================
# CASE H — unit equivalence.
# The same physical circuit expressed in different units must give the
# same physics: 10 V / 1 kohm  ==  10000 mV / 1000 ohm.
# =====================================================================

def test_case_h_unit_equivalence():
    def build(voltage, resistance, current):
        return solve_circuit(
            DCCircuit(
                circuit_id="case_h",
                nodes=(GND, ElectricalNode("n1"), ElectricalNode("n2")),
                resistors=(
                    Resistor("R1", "n1", "n2", resistance),
                    Resistor("R2", "n2", "gnd", resistance),
                ),
                voltage_sources=(DCVoltageSource("V1", "n1", "gnd", voltage),),
                current_sources=(
                    DCCurrentSource("I1", "gnd", "n2", current),
                ),
            ),
            run_id="case-h",
        )

    si = build(
        Quantity(10.0, "volt"), Quantity(1000.0, "ohm"), Quantity(0.001, "ampere")
    )
    scaled = build(
        Quantity(10000.0, "millivolt"),
        Quantity(1.0, "kohm"),
        Quantity(1.0, "milliampere"),
    )
    for metric in sorted(si.values):
        assert abs(
            si.value(metric).magnitude_in(si.value(metric).units)
            - scaled.value(metric).to(si.value(metric).units).magnitude
        ) <= 1e-9, metric


def test_component_insertion_order_does_not_change_physics():
    def build(order):
        resistors = {
            "R1": Resistor("R1", "n1", "mid", Quantity(1.0, "kohm")),
            "R2": Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        }
        return solve_circuit(
            DCCircuit(
                circuit_id="order",
                nodes=(GND, ElectricalNode("n1"), ElectricalNode("mid")),
                resistors=tuple(resistors[k] for k in order),
                voltage_sources=(
                    DCVoltageSource("V1", "n1", "gnd", Quantity(12.0, "volt")),
                ),
            ),
            run_id="order",
        )

    forward = build(("R1", "R2"))
    backward = build(("R2", "R1"))
    assert _close(forward.value("node_voltage:mid"), 9.0, "volt")
    assert forward.value("node_voltage:mid") == backward.value("node_voltage:mid")


# =====================================================================
# Failure and singular behaviour
# =====================================================================

def test_floating_subnetwork_is_reported_as_failure_not_guessed():
    """n1-n2 are connected to each other but not to the reference: the
    system is singular and has no unique solution."""
    circuit = DCCircuit(
        circuit_id="floating",
        nodes=(GND, ElectricalNode("n1"), ElectricalNode("n2")),
        resistors=(Resistor("R1", "n1", "n2", Quantity(1.0, "kohm")),),
    )
    result = solve_circuit(circuit, run_id="floating")
    assert result.convergence is ConvergenceState.FAILED
    assert result.validation.status is ValidationOutcome.FAIL
    assert result.values == {}          # no invented numbers
    assert not result.is_usable


def test_contradictory_voltage_sources_are_not_resolved_by_the_solver():
    """Two ideal sources imposing different voltages across the same node
    pair is inconsistent; the solver must not choose one."""
    circuit = DCCircuit(
        circuit_id="contradiction",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt")),
            DCVoltageSource("V2", "n1", "gnd", Quantity(5.0, "volt")),
        ),
    )
    result = solve_circuit(circuit, run_id="contradiction")
    assert result.convergence is ConvergenceState.FAILED
    assert result.values == {}
    assert not result.is_usable


def test_identical_parallel_voltage_sources_are_still_singular():
    """Even when consistent, two ideal sources in parallel leave their
    individual currents indeterminate — still no unique solution."""
    circuit = DCCircuit(
        circuit_id="degenerate",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        voltage_sources=(
            DCVoltageSource("V1", "n1", "gnd", Quantity(10.0, "volt")),
            DCVoltageSource("V2", "n1", "gnd", Quantity(10.0, "volt")),
        ),
    )
    result = solve_circuit(circuit, run_id="degenerate")
    assert result.convergence is ConvergenceState.FAILED


def test_prepare_requires_a_bound_circuit():
    from src.engcore.domains.electrical.dc import build_dc_problem
    from src.engcore.domains.electrical.dc.solver import ElectricalDCError

    circuit = DCCircuit(
        circuit_id="unbound",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "ohm")),),
    )
    problem = build_dc_problem(circuit)
    solver = ElectricalDCSolver()
    _raises(ElectricalDCError, solver.prepare, problem)


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
    print(f"dc solver: {'FAIL' if failures else 'PASS'} "
          f"({total - failures}/{total})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
