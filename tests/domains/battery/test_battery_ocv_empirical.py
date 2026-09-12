"""Phase 12: MODEL_APPLICABLE and MODEL_EMPIRICALLY_ADEQUATE are different answers.

The B1 gap, reproduced on synthetic numbers and then closed: a cell whose
declared OCV misses measured OCV by hundreds of millivolts gets ZERO violated
applicability conditions -- and an empirical assessment that says INADEQUATE.
Absence of evidence is never adequate, and out-of-claim evidence is set aside
with a reason rather than scored.
"""

from __future__ import annotations

import pytest

from engcore.domains.battery import cell as battery_cell
from engcore.domains.battery import context as ctx
from engcore.domains.battery.empirical import (
    ConditioningDirection,
    MeasuredOcvPoint,
    OcvEmpiricalStatus,
    assess_ocv_empirical_adequacy,
)
from engcore.scientific.errors import InvalidScientificProblem, ScientificCoreError
from engcore.scientific.models.curves import DeclaredCurve, TabulatedForm
from engcore.scientific.units.quantity import Quantity as Q

CHORD_CELL = battery_cell.CellSpecification(
    cell_id="CHORD", nominal_capacity=Q(1.1, "ampere_hour"), internal_resistance=Q(0.0126, "ohm"),
    open_circuit_voltage_at_empty=Q(3.2197, "volt"), open_circuit_voltage_at_full=Q(3.3609, "volt"),
)


def point(z, volts, u=0.001, conditioning=ConditioningDirection.DISCHARGE, ref=None):
    return MeasuredOcvPoint(
        state_of_charge=Q(z, "dimensionless"), open_circuit_voltage=Q(volts, "volt"),
        standard_uncertainty=Q(u, "volt"), conditioning=conditioning,
        source_ref=ref or f"synthetic:ocv:{z}",
    )


def test_no_measured_evidence_is_never_adequate():
    result = assess_ocv_empirical_adequacy(CHORD_CELL, [])
    assert result.status is OcvEmpiricalStatus.NO_MEASURED_EVIDENCE
    assert not result.empirically_adequate


def test_only_charge_conditioned_evidence_is_outside_the_claim():
    result = assess_ocv_empirical_adequacy(
        CHORD_CELL, [point(0.4, 3.30, conditioning=ConditioningDirection.CHARGE)]
    )
    assert result.status is OcvEmpiricalStatus.EVIDENCE_OUTSIDE_CLAIM
    assert "hysteresis" in result.excluded[0]["reason"]
    assert not result.empirically_adequate


def test_evidence_that_agrees_within_uncertainty_is_adequate():
    agreeing = [point(z, 3.2197 + 0.1412 * z + 0.0005) for z in (0.0, 0.4, 0.6)]
    result = assess_ocv_empirical_adequacy(CHORD_CELL, agreeing)
    assert result.status is OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE
    assert result.degrees_of_freedom == 3


def test_the_b1_gap_applicable_with_no_violation_yet_empirically_inadequate():
    """B1's calibrated chord against B1's held-out numbers, as synthetic inputs.

    The applicability assessment finds nothing to object to; the empirical one
    says what the measurements say.
    """
    load = battery_cell.DischargeLoad(
        load_id="L", current=Q(0.22, "ampere"), initial_state_of_charge=Q(1.0, "dimensionless"),
        cell_temperature=Q(296.15, "kelvin"), duration=Q(3.0, "hour"),
    )
    problem = battery_cell.build_battery_problem(CHORD_CELL, load)
    applicability = battery_cell.assess_rint_validity(
        problem, state_of_charge=Q(0.4, "dimensionless"), discharge_current=load.current,
        cell_temperature=load.cell_temperature,
    )
    assert applicability.violated == ()

    held_out = [point(0.0, 2.8473, 0.0023), point(0.4, 3.2894, 0.00097), point(0.6, 3.2929, 0.00123)]
    result = assess_ocv_empirical_adequacy(
        CHORD_CELL, held_out, applicability_status=applicability.status.value
    )
    assert result.status is OcvEmpiricalStatus.EMPIRICALLY_INADEQUATE
    assert result.applicability_status == applicability.status.value
    assert result.to_dict()["model_applicable_status"] == applicability.status.value
    worst = min(result.scored, key=lambda row: row["residual_v"])
    assert worst["state_of_charge"] == 0.0 and worst["residual_v"] < -0.3


def test_applicability_is_carried_but_never_consulted():
    """An IN_DOMAIN applicability status does not rescue a failing cell."""
    failing = [point(0.0, 2.8473, 0.0023)]
    assert assess_ocv_empirical_adequacy(
        CHORD_CELL, failing, applicability_status="in_domain"
    ).status is OcvEmpiricalStatus.EMPIRICALLY_INADEQUATE


def test_a_curve_cell_is_scored_on_its_curve_not_on_the_chord_of_its_ends():
    curve_cell = battery_cell.CellSpecification(
        cell_id="CURVE", nominal_capacity=Q(1.1, "ampere_hour"), internal_resistance=Q(0.0126, "ohm"),
        open_circuit_voltage_curve=DeclaredCurve(
            quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE, against_unit="dimensionless",
            unit="volt", lower=0.0, upper=1.0,
            form=TabulatedForm(((0.0, 2.85), (0.2, 3.25), (1.0, 3.39))),
        ),
    )
    result = assess_ocv_empirical_adequacy(curve_cell, [point(0.2, 3.2504, 0.001)])
    assert result.status is OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE
    # the chord of the same ends would read 2.85 + 0.54 * 0.2 = 2.958 V here
    assert result.scored[0]["declared_v"] == pytest.approx(3.25)


def test_the_assessment_lists_what_it_scored_so_independence_can_be_checked():
    result = assess_ocv_empirical_adequacy(CHORD_CELL, [point(0.4, 3.2894, ref="S-OCV:held:0.4")])
    assert [row["source_ref"] for row in result.scored] == ["S-OCV:held:0.4"]
    assert "must not be supplied" in result.independence_note


@pytest.mark.parametrize("u", [0.0, -0.001, float("inf")])
def test_a_measurement_without_a_positive_finite_uncertainty_is_refused(u):
    """Zero and negative are refused here; infinity is refused one layer earlier,
    by Quantity itself. Either way the point is never built."""
    with pytest.raises(ScientificCoreError):
        point(0.4, 3.29, u=u)


def test_a_measurement_without_provenance_is_refused():
    with pytest.raises(InvalidScientificProblem, match="source_ref"):
        MeasuredOcvPoint(Q(0.4, "dimensionless"), Q(3.29, "volt"), Q(0.001, "volt"),
                         ConditioningDirection.DISCHARGE, "  ")
