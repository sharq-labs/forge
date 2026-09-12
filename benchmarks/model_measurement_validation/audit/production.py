"""Thin adapters onto the production models. No arithmetic beyond declaring.

Nothing here computes a physical quantity. Each function builds an engcore
declaration from measured numbers and hands back what the Core returned. Any
arithmetic performed in this file would be arithmetic a comparison could
accidentally be made against instead of the Core.
"""

from __future__ import annotations

from engcore.scientific.units.quantity import Quantity as Q


def cell_with_chord(*, ocv_full_v: float, ocv_empty_v: float,
                    capacity_mah: float, resistance_mohm: float):
    from engcore.domains.battery.cell import CellSpecification
    from engcore.domains.battery.context import CellLimits

    return CellSpecification(
        cell_id="MV",
        nominal_capacity=Q(capacity_mah, "milliampere_hour"),
        internal_resistance=Q(resistance_mohm, "milliohm"),
        open_circuit_voltage_at_full=Q(ocv_full_v, "volt"),
        open_circuit_voltage_at_empty=Q(ocv_empty_v, "volt"),
        coulombic_efficiency=Q(1.0, "dimensionless"),
        limits=CellLimits(),
    )


def cell_with_curve(*, samples, capacity_mah: float, resistance_mohm: float,
                    source: str):
    """A cell whose open-circuit voltage is a declared measured curve.

    The model record says the chord governs 'unless the cell declares a curve
    for it, in which case the curve governs'. This is that route, exercised
    with real samples and with the interpolation stated rather than implied.
    """
    from engcore.domains.battery.cell import CellSpecification
    from engcore.domains.battery.context import CellLimits
    from engcore.scientific.models.curves import (
        DeclaredCurve,
        Interpolation,
        TabulatedForm,
    )

    ordered = tuple(sorted((float(s), float(v)) for s, v in samples))
    curve = DeclaredCurve(
        quantity="open_circuit_voltage_curve",
        against="state_of_charge",
        against_unit="dimensionless",
        unit="volt",
        lower=ordered[0][0],
        upper=ordered[-1][0],
        form=TabulatedForm(samples=ordered, interpolation=Interpolation.LINEAR),
        source=source,
    )
    return CellSpecification(
        cell_id="MV-curve",
        nominal_capacity=Q(capacity_mah, "milliampere_hour"),
        internal_resistance=Q(resistance_mohm, "milliohm"),
        open_circuit_voltage_at_full=None,
        open_circuit_voltage_at_empty=None,
        coulombic_efficiency=Q(1.0, "dimensionless"),
        limits=CellLimits(),
        open_circuit_voltage_curve=curve,
    )


def open_circuit_voltage(cell, state_of_charge: float):
    """What the Core says the open-circuit voltage is at this state of charge."""
    value = cell.open_circuit_voltage(Q(state_of_charge, "dimensionless"))
    return None if value is None else value.magnitude_in("volt")


def resistance_at(*, r0_ohm: float, alpha_per_k: float,
                  reference_celsius: float, celsius: float) -> float:
    from engcore.domains.electrical import material as M

    conductor = M.TemperatureDependentConductor(
        component_id="MV-PT100",
        reference_resistance=Q(r0_ohm, "ohm"),
        temperature_coefficient=Q(alpha_per_k, "1 / kelvin"),
        reference_temperature=Q(reference_celsius, "degC"),
        limits=M.MaterialLimits(),
    )
    problem = M.build_resistance_problem(conductor)
    solver = M.ResistancePropertySolver()
    solver.bind_conductor(conductor, problem.problem_id, temperature=Q(celsius, "degC"))
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    return solver.extract_metrics(prepared, raw)["resistance"].magnitude_in("ohm")
