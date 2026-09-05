"""The validation layer must actually catch wrong answers.

A validation suite that only ever runs against correct solutions proves
nothing. Each test here feeds a *deliberately corrupted* solution vector to
the checks and asserts that the relevant check fails — which is only possible
because the checks are reconstructed from circuit elements rather than from
the MNA matrix that produced the solution.
"""

from __future__ import annotations

import sys

import numpy as np

from src.engcore.domains.electrical.dc import (
    DCCircuit,
    DCCurrentSource,
    DCValidationSettings,
    DCVoltageSource,
    ElectricalDCSolver,
    ElectricalNode,
    Resistor,
    assemble,
    build_dc_problem,
    build_validation_report,
    solve_circuit,
)
from src.engcore.domains.electrical.dc.validation import (
    check_kcl,
    check_linear_residual,
    check_power_balance,
    check_resistor_relation,
    check_voltage_sources,
)
from src.engcore.scientific import Quantity, ValidationOutcome

GND = ElectricalNode("gnd", is_reference=True)
SETTINGS = DCValidationSettings()


def _divider_system():
    circuit = DCCircuit(
        circuit_id="divider",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(1.0, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),
        ),
    )
    system = assemble(circuit)
    # Hand-derived exact solution: node order (mid, top), then I(V1).
    # V(top) = 12, V(mid) = 9, I = -(12/4000) = -3 mA leaving the + node.
    solution = np.array([9.0, 12.0, -0.003])
    assert system.node_order == ("mid", "top")
    return system, solution


def test_checks_pass_on_the_exact_analytical_solution():
    system, solution = _divider_system()
    for check in (
        check_linear_residual(system, solution, SETTINGS),
        check_kcl(system, solution, SETTINGS),
        check_resistor_relation(system, solution, SETTINGS),
        check_voltage_sources(system, solution, SETTINGS),
        check_power_balance(system, solution, SETTINGS),
    ):
        assert check.outcome is ValidationOutcome.PASS, check.detail


def test_kcl_check_detects_a_corrupted_node_voltage():
    """Perturb V(mid) only: KCL at that node must break."""
    system, solution = _divider_system()
    corrupted = solution.copy()
    corrupted[0] += 0.5           # V(mid) = 9.5 V, physically inconsistent
    check = check_kcl(system, corrupted, SETTINGS)
    assert check.outcome is ValidationOutcome.FAIL
    assert "mid" in check.detail
    assert check.residual > SETTINGS.kcl_atol_ampere


def test_voltage_source_check_detects_a_violated_constraint():
    system, solution = _divider_system()
    corrupted = solution.copy()
    corrupted[1] = 11.0           # V(top) no longer equals the 12 V source
    check = check_voltage_sources(system, corrupted, SETTINGS)
    assert check.outcome is ValidationOutcome.FAIL
    assert check.residual > SETTINGS.source_atol_volt


def test_power_balance_detects_a_corrupted_source_current():
    """Corrupt only the source branch current: KCL and power balance break
    while the source-voltage relation stays satisfied."""
    system, solution = _divider_system()
    corrupted = solution.copy()
    corrupted[2] = -0.010         # claim 10 mA instead of 3 mA
    assert check_voltage_sources(system, corrupted, SETTINGS).outcome is (
        ValidationOutcome.PASS
    )
    assert check_power_balance(system, corrupted, SETTINGS).outcome is (
        ValidationOutcome.FAIL
    )
    assert check_kcl(system, corrupted, SETTINGS).outcome is ValidationOutcome.FAIL


def test_linear_residual_detects_a_wrong_solution():
    system, solution = _divider_system()
    check = check_linear_residual(system, solution + 1.0, SETTINGS)
    assert check.outcome is ValidationOutcome.FAIL
    assert check.residual > check.tolerance


def test_kcl_is_not_merely_the_matrix_row():
    """A solution can satisfy A x = z for a *wrongly stamped* system while
    violating physically reconstructed KCL. Here the resistor is stamped with
    the wrong conductance; the residual check passes on the corrupted system
    but the independent KCL check fails."""
    circuit = DCCircuit(
        circuit_id="wrong_stamp",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(1.0, "milliampere")),
        ),
    )
    system = assemble(circuit)
    # Corrupt the assembled matrix as a faulty stamp would, then solve it.
    system.matrix[0, 0] = 1.0 / 500.0          # pretends R = 500 ohm
    solution = np.array([system.rhs[0] / system.matrix[0, 0]])   # = 0.5 V

    assert check_linear_residual(system, solution, SETTINGS).outcome is (
        ValidationOutcome.PASS
    )
    # Physically: 1 mA through 1 kohm must give 1 V, not 0.5 V.
    kcl = check_kcl(system, solution, SETTINGS)
    assert kcl.outcome is ValidationOutcome.FAIL
    assert kcl.residual > SETTINGS.kcl_atol_ampere


def test_report_records_not_run_for_absent_element_classes():
    circuit = DCCircuit(
        circuit_id="only_current",
        nodes=(GND, ElectricalNode("n1")),
        resistors=(Resistor("R1", "n1", "gnd", Quantity(1.0, "kohm")),),
        current_sources=(
            DCCurrentSource("I1", "gnd", "n1", Quantity(1.0, "milliampere")),
        ),
    )
    result = solve_circuit(circuit, run_id="no-vsource")
    checks = {c.name: c for c in result.validation.checks}
    assert checks["voltage_source_relation"].outcome is ValidationOutcome.NOT_RUN
    # a NOT_RUN check contributes no evidence and no level
    assert result.validation.status is ValidationOutcome.PASS


def test_dimensional_check_rejects_a_mislabelled_metric():
    system, solution = _divider_system()
    solver = ElectricalDCSolver()
    problem = build_dc_problem(system.circuit)
    solver.bind_circuit(system.circuit, problem.problem_id)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    metrics = solver.extract_metrics(prepared, raw)

    metrics["resistor_power:R1"] = Quantity(1.0, "ampere")   # wrong dimension
    report = build_validation_report(system, solution, metrics, SETTINGS)
    dimensional = {c.name: c for c in report.checks}["dimensional_consistency"]
    assert dimensional.outcome is ValidationOutcome.FAIL
    assert "resistor_power:R1" in dimensional.detail
    # a failed dimensional check must not establish its level
    from src.engcore.scientific import ValidationLevel
    assert ValidationLevel.DIMENSIONALLY_VALID not in report.attained_levels


def test_tolerances_are_centralised_and_recorded():
    settings = DCValidationSettings()
    mapping = settings.as_mapping()
    assert set(mapping) == {
        "residual_atol", "residual_rtol", "kcl_atol_ampere",
        "ohm_atol_volt", "source_atol_volt", "power_atol_watt",
    }
    assert all(value > 0 for value in mapping.values())

    result = solve_circuit(_divider_system()[0].circuit, run_id="tol")
    assert result.provenance.tolerances == mapping


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
    print(f"dc validation: {'FAIL' if failures else 'PASS'} "
          f"({total - failures}/{total})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
