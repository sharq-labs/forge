"""NUM-01 and NUM-02: DC tolerances judged against the circuit's own scale.

NUM-01 (probe ``agentD/num1.py``). Every DC validation tolerance was an absolute
1e-9 in amperes, volts or watts. A 1 V divider of two 1 GOhm resistors carries
0.5 nA, so a solution whose midpoint was corrupted from 0.5 V to 0.6 V left a
KCL imbalance of 2e-10 A, a linear residual of 2.2e-10 and a power imbalance of
2e-11 W -- all inside 1e-9 -- and the report read PASS with
NUMERICALLY_CONVERGED. The same corruption at 1 kOhm FAILed. A tolerance that
depends on the unit the circuit happens to be drawn in is not a tolerance.

NUM-02 (probe ``agentD/ind2.py``). The external route's admission gate
reconciled element currents and powers with ``atol = 1e-9``: at 1 nA a factor-2
current and a zero power were admitted.

The rule these tests pin: each bound is relative to the quantity it judges, and
an absolute term appears only as a floor scaled by the circuit's own current,
voltage or power -- so an honest nano-scale solve still passes and a corrupted
one fails.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.domains.electrical.dc import (
    DCCircuit,
    DCValidationSettings,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    assemble,
)
from engcore.domains.electrical.dc.components import VOLTAGE_UNIT
from engcore.domains.electrical.dc.validation import build_validation_report
from engcore.domains.electrical.ngspice import NgspiceDCSolver, NgspiceExecutionFailure
from engcore.scientific.results.validation import ValidationLevel, ValidationOutcome
from engcore.scientific.units.quantity import Quantity


def _divider(r: float, v: float) -> DCCircuit:
    return DCCircuit(
        circuit_id="g",
        nodes=(ElectricalNode("n0"), ElectricalNode("n1"), ElectricalNode("gnd", is_reference=True)),
        resistors=(
            Resistor("R1", "n0", "n1", Quantity(r, "ohm")),
            Resistor("R2", "n1", "gnd", Quantity(r, "ohm")),
        ),
        voltage_sources=(DCVoltageSource("V1", "n0", "gnd", Quantity(v, "volt")),),
    )


def _report(r: float, v: float, corrupt: dict[str, float] | None = None):
    system = assemble(_divider(r, v))
    solution = np.linalg.solve(system.matrix, system.rhs)
    for node, factor in (corrupt or {}).items():
        solution[list(system.node_order).index(node)] *= factor
    metrics = {
        f"node_voltage:{n}": Quantity(float(solution[i]), VOLTAGE_UNIT)
        for i, n in enumerate(system.node_order)
    }
    report = build_validation_report(system, solution, metrics, DCValidationSettings())
    return report, {c.name: c for c in report.checks}


# ---- NUM-01 -----------------------------------------------------------------------------
def test_probe_a_corrupted_gigaohm_solution_fails():
    report, checks = _report(1e9, 1.0, {"n1": 1.2})
    assert checks["linear_system_residual"].outcome is ValidationOutcome.FAIL
    assert checks["kirchhoff_current_law"].outcome is ValidationOutcome.FAIL
    assert checks["power_balance"].outcome is ValidationOutcome.FAIL
    assert report.status is ValidationOutcome.FAIL
    assert ValidationLevel.NUMERICALLY_CONVERGED not in report.attained_levels


def test_an_honest_gigaohm_solution_still_passes():
    report, checks = _report(1e9, 1.0)
    assert report.status is ValidationOutcome.PASS, {n: c.detail for n, c in checks.items()}
    assert ValidationLevel.NUMERICALLY_CONVERGED in report.attained_levels


def test_the_same_corruption_at_a_kilohm_still_fails():
    report, checks = _report(1e3, 1.0, {"n1": 1.2})
    assert report.status is ValidationOutcome.FAIL
    assert checks["kirchhoff_current_law"].outcome is ValidationOutcome.FAIL


@pytest.mark.parametrize("r, v", [(1.0, 1e-9), (1e3, 1e-6), (1e-3, 1e3), (1e6, 1e4)])
def test_honest_solves_pass_at_every_scale(r, v):
    report, checks = _report(r, v)
    assert report.status is ValidationOutcome.PASS, {n: c.detail for n, c in checks.items()}
    assert ValidationLevel.NUMERICALLY_CONVERGED in report.attained_levels


def test_a_corrupted_nanovolt_source_node_fails_the_source_relation():
    _, checks = _report(1.0, 1e-9, {"n0": 1.2})
    assert checks["voltage_source_relation"].outcome is ValidationOutcome.FAIL
    assert checks["linear_system_residual"].outcome is ValidationOutcome.FAIL


def test_bounds_scale_with_the_circuit_and_are_recorded():
    _, big = _report(1e3, 1.0, {"n1": 1.2})
    _, small = _report(1e9, 1.0, {"n1": 1.2})
    assert small["kirchhoff_current_law"].tolerance < big["kirchhoff_current_law"].tolerance
    assert small["power_balance"].tolerance < 1e-15


# ---- NUM-02 -----------------------------------------------------------------------------
@pytest.mark.parametrize("scale", [1.0, 1e-9, 1e-12, 1e3])
def test_probe_admission_refuses_a_factor_two_current_at_every_scale(scale):
    v, r = 1.0, 1.0 / scale
    i = v / r
    with pytest.raises(NgspiceExecutionFailure):
        NgspiceDCSolver._admit_element_power(component_id="R", v_drop=v, current=2 * i, power=v * 2 * i, ohms=r)


@pytest.mark.parametrize("scale", [1.0, 1e-9, 1e-12, 1e3])
def test_probe_admission_refuses_a_zero_power_at_every_scale(scale):
    v, r = 1.0, 1.0 / scale
    i = v / r
    with pytest.raises(NgspiceExecutionFailure):
        NgspiceDCSolver._admit_element_power(component_id="R", v_drop=v, current=i, power=0.0, ohms=r)


@pytest.mark.parametrize("scale", [1.0, 1e-9, 1e-12, 1e3])
def test_honest_element_values_are_admitted_at_every_scale(scale):
    v, r = 1.0, 1.0 / scale
    i = v / r
    # Printed to 13 significant digits by the provider: a relative wobble of 1e-13.
    NgspiceDCSolver._admit_element_power(
        component_id="R", v_drop=v, current=i * (1 + 1e-13), power=v * i * (1 - 1e-13), ohms=r
    )


def test_an_exactly_zero_element_is_admitted():
    NgspiceDCSolver._admit_element_power(component_id="R", v_drop=0.0, current=0.0, power=0.0, ohms=1e9)
