"""Phase 13: a voltage cutoff on a DECLARED OCV curve, with no chord anywhere.

Before B2 the battery validity derivations inverted the CHORD for every cell,
including a cell that declared a curve -- whose chord endpoints are read off
that curve and whose chord it therefore replaced. Both cutoff conditions
answered for a curve cell from the linear model, while the solver refused the
same combination as unmigrated. That silent linear fallback is what these tests
exist to keep out.

The SOLVER's refusal is deliberately unchanged: it is pinned by a certified
Core harness test, and the Core is frozen. The last test here asserts it still
refuses, so the boundary is stated where it holds.
"""

from __future__ import annotations

import pytest

from engcore.domains.battery import cell as battery_cell
from engcore.domains.battery import context as ctx
from engcore.domains.battery.solver import evaluate_step
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.curves import (
    DeclaredCurve,
    Interpolation,
    PiecewiseForm,
    PolynomialForm,
    TabulatedForm,
)
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.units.quantity import Quantity as Q

LOAD = dict(current=Q(1.0, "ampere"), internal_resistance=Q(0.05, "ohm"))  # I R = 50 mV


def curve(form, lower=0.0, upper=1.0):
    return DeclaredCurve(
        quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE, against_unit="dimensionless",
        unit="volt", lower=lower, upper=upper, form=form,
    )


def on_curve(cutoff_v, c, **overrides):
    kwargs = {**LOAD, **overrides}
    return ctx.voltage_cutoff_state_of_charge_on_curve(cutoff_voltage=Q(cutoff_v, "volt"), curve=c, **kwargs)


KNEE = curve(TabulatedForm(((0.0, 2.9), (0.1, 3.25), (1.0, 3.4))))


# =====================================================================
# the same semantics as the chord
# =====================================================================

@pytest.mark.parametrize("cutoff", [2.96, 3.1, 3.2, 3.34])
def test_a_degree_one_curve_reproduces_the_chord_inversion(cutoff):
    linear = curve(PolynomialForm((3.0, 0.4)))
    expected = ctx.voltage_cutoff_state_of_charge(
        cutoff_voltage=Q(cutoff, "volt"), ocv_at_empty=Q(3.0, "volt"), ocv_at_full=Q(3.4, "volt"), **LOAD
    ).magnitude
    result = on_curve(cutoff, linear)
    assert result.status is ValidityStatus.IN_DOMAIN
    assert result.value.magnitude == pytest.approx(expected, abs=1e-12)


def test_a_table_is_inverted_exactly_on_its_segment():
    result = on_curve(3.2, KNEE)  # target OCV 3.25 V, the knee sample itself
    assert result.status is ValidityStatus.IN_DOMAIN
    assert result.value.magnitude == pytest.approx(0.1, abs=1e-15)
    mid = on_curve(3.275, KNEE)  # target 3.325 V, halfway along 3.25 -> 3.40
    assert mid.value.magnitude == pytest.approx(0.55, abs=1e-12)


def test_the_cutoff_rises_with_current_as_the_physics_requires():
    light = on_curve(3.2, KNEE, current=Q(0.2, "ampere")).value.magnitude
    heavy = on_curve(3.2, KNEE, current=Q(2.0, "ampere")).value.magnitude
    assert heavy > light


# =====================================================================
# boundaries and refusals
# =====================================================================

def test_a_target_exactly_at_the_curve_ends_is_inside():
    assert on_curve(2.85, KNEE).value.magnitude == pytest.approx(0.0, abs=1e-15)
    assert on_curve(3.35, KNEE).value.magnitude == pytest.approx(1.0, abs=1e-15)


@pytest.mark.parametrize("cutoff", [2.85 - 1e-9, 3.35 + 1e-9, 1.0, 4.0])
def test_a_target_outside_the_curve_is_refused_not_extrapolated(cutoff):
    result = on_curve(cutoff, KNEE)
    assert result.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert result.value is None
    assert "not extrapolated" in result.reason


def test_a_step_table_names_no_single_state_of_charge():
    step = curve(TabulatedForm(((0.0, 2.9), (1.0, 3.4)), Interpolation.PREVIOUS))
    result = on_curve(3.1, step)
    assert result.value is None and "step function" in result.reason


def test_a_table_that_does_not_rise_strictly_is_refused():
    flat = curve(TabulatedForm(((0.0, 2.9), (0.5, 3.3), (0.6, 3.3), (1.0, 3.4))))
    result = on_curve(3.2, flat)
    assert result.value is None and "several states of charge" in result.reason


def test_a_non_monotone_polynomial_is_refused():
    humped = curve(PolynomialForm((3.0, 1.2, -1.0)))  # peaks at z = 0.6, falls after
    result = on_curve(3.0, humped)
    assert result.value is None and "not strictly increasing" in result.reason


def test_a_curve_that_jumps_over_the_target_is_refused():
    jump = curve(PiecewiseForm((0.5,), (PolynomialForm((3.0, 0.2)), PolynomialForm((3.3, 0.1)))))
    result = on_curve(3.15, jump)  # target 3.20 V lies in the gap 3.10 -> 3.35
    assert result.value is None and "discontinuity" in result.reason


def test_a_missing_input_is_unknown():
    result = ctx.voltage_cutoff_state_of_charge_on_curve(
        cutoff_voltage=None, curve=KNEE, **LOAD
    )
    assert result.status is ValidityStatus.UNKNOWN and result.value is None


def test_the_inversion_is_deterministic():
    polynomial = curve(PolynomialForm((2.9, 0.9, -0.4)))
    first = on_curve(3.1, polynomial).value.magnitude
    assert all(on_curve(3.1, polynomial).value.magnitude == first for _ in range(5))


# =====================================================================
# wired into the validity conditions
# =====================================================================

def knee_cell_and_load(cutoff_soc=0.3):
    cell = battery_cell.CellSpecification(
        cell_id="KNEE", nominal_capacity=Q(1.0, "ampere_hour"), internal_resistance=Q(0.05, "ohm"),
        open_circuit_voltage_curve=KNEE,
    )
    load = battery_cell.DischargeLoad(
        load_id="L", current=Q(1.0, "ampere"), initial_state_of_charge=Q(0.9, "dimensionless"),
        cell_temperature=Q(298.15, "kelvin"), duration=Q(60.0, "second"),
        cutoff_voltage=Q(3.2, "volt"), cutoff_state_of_charge=Q(cutoff_soc, "dimensionless"),
    )
    return cell, load


def runtime_verdict(cell, load):
    problem = battery_cell.build_battery_problem(cell, load)
    return battery_cell.assess_runtime_validity(
        problem, state_of_charge=load.initial_state_of_charge, discharge_current=load.current,
        cell_temperature=load.cell_temperature, open_circuit_voltage_curve=cell.open_circuit_voltage_curve,
    )


def test_the_cutoff_conditions_read_the_curve_not_the_chord_of_its_endpoints():
    """The fallback gave the WRONG verdict, not merely an imprecise number.

    On this knee the voltage cutoff bites at z = 0.1 on the curve and at z = 0.7
    on the chord of the same endpoints. Against a declared cutoff of 0.3 the
    curve says the two cutoffs are consistent (0.3 - 0.1 = +0.2) and the chord
    says they are not (0.3 - 0.7 = -0.4).
    """
    cell, load = knee_cell_and_load(cutoff_soc=0.3)
    chord_answer = ctx.voltage_cutoff_state_of_charge(
        cutoff_voltage=load.cutoff_voltage, current=load.current, internal_resistance=cell.internal_resistance,
        ocv_at_empty=cell.open_circuit_voltage_at_empty, ocv_at_full=cell.open_circuit_voltage_at_full,
    ).magnitude
    assert chord_answer == pytest.approx(0.7)
    verdict = runtime_verdict(cell, load)
    assert ctx.CUTOFF_CONSISTENCY_MARGIN in verdict.satisfied
    assert ctx.CUTOFF_CONSISTENCY_MARGIN not in verdict.violated


def test_a_curve_that_cannot_be_inverted_leaves_the_cutoff_conditions_unknown():
    step = curve(TabulatedForm(((0.0, 2.9), (1.0, 3.4)), Interpolation.PREVIOUS))
    cell = battery_cell.CellSpecification(
        cell_id="STEP", nominal_capacity=Q(1.0, "ampere_hour"), internal_resistance=Q(0.05, "ohm"),
        open_circuit_voltage_curve=step,
    )
    _, load = knee_cell_and_load()
    verdict = runtime_verdict(cell, load)
    assert ctx.CUTOFF_CONSISTENCY_MARGIN in verdict.unknown
    assert ctx.CUTOFF_REACHABILITY_MARGIN in verdict.unknown


def test_a_chord_cell_is_unchanged():
    chord = battery_cell.CellSpecification(
        cell_id="CHORD", nominal_capacity=Q(1.0, "ampere_hour"), internal_resistance=Q(0.05, "ohm"),
        open_circuit_voltage_at_empty=Q(2.9, "volt"), open_circuit_voltage_at_full=Q(3.4, "volt"),
    )
    _, load = knee_cell_and_load(cutoff_soc=0.3)
    problem = battery_cell.build_battery_problem(chord, load)
    verdict = battery_cell.assess_runtime_validity(
        problem, state_of_charge=load.initial_state_of_charge, discharge_current=load.current,
        cell_temperature=load.cell_temperature,
    )
    assert verdict.violated == (ctx.CUTOFF_CONSISTENCY_MARGIN,)


def test_the_solver_still_refuses_curve_and_cutoff_as_certified():
    """Unchanged on purpose: pinned by tests/test_core_guards.py, and the Core is frozen."""
    cell, load = knee_cell_and_load()
    with pytest.raises(InvalidScientificProblem, match="has not been migrated"):
        evaluate_step(cell, load)
