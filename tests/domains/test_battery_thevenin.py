"""Dynamic one-RC battery kernel tests."""

from __future__ import annotations

import math

import pytest

from engcore.domains.battery.cell import CellSpecification
from engcore.domains.battery.thevenin import (
    Thevenin1RCParameters,
    TheveninState,
    evaluate_thevenin_step,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def _cell() -> CellSpecification:
    return CellSpecification(
        cell_id="fixture-18650",
        nominal_capacity=Quantity(2.0, "ampere_hour"),
        internal_resistance=Quantity(0.05, "ohm"),
        open_circuit_voltage_at_full=Quantity(4.2, "volt"),
        open_circuit_voltage_at_empty=Quantity(3.0, "volt"),
        coulombic_efficiency=Quantity(1.0, "dimensionless"),
    )


def _rc() -> Thevenin1RCParameters:
    # tau = 0.02 * 500 = 10 s
    return Thevenin1RCParameters(
        polarization_resistance=Quantity(0.02, "ohm"),
        polarization_capacitance=Quantity(500.0, "farad"),
    )


def test_constant_current_step_matches_the_closed_form() -> None:
    result = evaluate_thevenin_step(
        _cell(),
        _rc(),
        TheveninState(
            Quantity(0.8, "dimensionless"),
            Quantity(0.0, "volt"),
        ),
        current=Quantity(2.0, "ampere"),
        duration=Quantity(10.0, "second"),
    )

    expected_soc = 0.8 - 2.0 * (10.0 / 3600.0) / 2.0
    expected_vp = 2.0 * 0.02 * (1.0 - math.exp(-1.0))
    expected_ocv = 3.0 + (4.2 - 3.0) * expected_soc
    expected_terminal = expected_ocv - 2.0 * 0.05 - expected_vp

    assert result.time_constant.magnitude_in("second") == pytest.approx(10.0)
    assert result.alpha == pytest.approx(math.exp(-1.0))
    assert result.final_state.state_of_charge.magnitude_in("dimensionless") == pytest.approx(expected_soc)
    assert result.final_state.polarization_voltage.magnitude_in("volt") == pytest.approx(expected_vp)
    assert result.open_circuit_voltage.magnitude_in("volt") == pytest.approx(expected_ocv)
    assert result.terminal_voltage.magnitude_in("volt") == pytest.approx(expected_terminal)


def test_rest_interval_relaxes_polarization_without_changing_soc() -> None:
    result = evaluate_thevenin_step(
        _cell(),
        _rc(),
        TheveninState(
            Quantity(0.6, "dimensionless"),
            Quantity(0.08, "volt"),
        ),
        current=Quantity(0.0, "ampere"),
        duration=Quantity(20.0, "second"),
    )

    assert result.final_state.state_of_charge.magnitude_in("dimensionless") == pytest.approx(0.6)
    assert result.final_state.polarization_voltage.magnitude_in("volt") == pytest.approx(
        0.08 * math.exp(-2.0)
    )
    assert result.terminal_voltage.magnitude_in("volt") < result.open_circuit_voltage.magnitude_in("volt")


def test_long_constant_current_step_approaches_ir1_polarization() -> None:
    result = evaluate_thevenin_step(
        _cell(),
        _rc(),
        TheveninState(
            Quantity(0.9, "dimensionless"),
            Quantity(0.0, "volt"),
        ),
        current=Quantity(1.0, "ampere"),
        duration=Quantity(100.0, "second"),
    )

    assert result.final_state.polarization_voltage.magnitude_in("volt") == pytest.approx(
        0.02, rel=1e-4
    )


def test_negative_current_is_refused_until_charge_physics_is_declared() -> None:
    with pytest.raises(InvalidScientificProblem, match="discharge/rest only"):
        evaluate_thevenin_step(
            _cell(),
            _rc(),
            TheveninState(Quantity(0.5, "dimensionless"), Quantity(0.0, "volt")),
            current=Quantity(-1.0, "ampere"),
            duration=Quantity(1.0, "second"),
        )


def test_step_that_leaves_soc_domain_is_refused_not_clipped() -> None:
    with pytest.raises(InvalidScientificProblem, match="leaves the declared charge state"):
        evaluate_thevenin_step(
            _cell(),
            _rc(),
            TheveninState(Quantity(0.001, "dimensionless"), Quantity(0.0, "volt")),
            current=Quantity(10.0, "ampere"),
            duration=Quantity(3600.0, "second"),
        )


def test_rc_parameters_must_be_strictly_positive() -> None:
    with pytest.raises(InvalidScientificProblem, match="strictly positive"):
        Thevenin1RCParameters(
            polarization_resistance=Quantity(0.0, "ohm"),
            polarization_capacitance=Quantity(500.0, "farad"),
        )
