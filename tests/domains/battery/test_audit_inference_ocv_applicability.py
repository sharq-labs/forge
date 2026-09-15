"""INF-09: the applicability an OCV adequacy record carries is a typed assessment, not a caller's string.

``assess_ocv_empirical_adequacy(applicability_status="in_domain (trust me)")``
returned MODEL_EMPIRICALLY_ADEQUATE with ``model_applicable_status`` reading
"in_domain (trust me)": the record put an unverifiable sentence where the model's
applicability verdict belongs, beside the empirical verdict it is meant to be
read with.
"""

from __future__ import annotations

import pytest

from engcore.domains.battery import cell as battery_cell
from engcore.domains.battery.empirical import (
    ConditioningDirection,
    MeasuredOcvPoint,
    OcvEmpiricalAssessment,
    OcvEmpiricalStatus,
    assess_ocv_empirical_adequacy,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.units.quantity import Quantity as Q

CELL = battery_cell.CellSpecification(
    cell_id="AUDIT", nominal_capacity=Q(1.1, "ampere_hour"), internal_resistance=Q(0.0126, "ohm"),
    open_circuit_voltage_at_empty=Q(3.2197, "volt"), open_circuit_voltage_at_full=Q(3.3609, "volt"),
)
AGREEING = [
    MeasuredOcvPoint(Q(z, "dimensionless"), Q(3.2197 + 0.1412 * z, "volt"), Q(0.001, "volt"),
                     ConditioningDirection.DISCHARGE, f"synthetic:{z}")
    for z in (0.0, 0.4, 0.6)
]


def _applicability():
    load = battery_cell.DischargeLoad(
        load_id="L", current=Q(0.22, "ampere"), initial_state_of_charge=Q(1.0, "dimensionless"),
        cell_temperature=Q(296.15, "kelvin"), duration=Q(3.0, "hour"),
    )
    problem = battery_cell.build_battery_problem(CELL, load)
    return battery_cell.assess_rint_validity(
        problem, state_of_charge=Q(0.4, "dimensionless"), discharge_current=load.current,
        cell_temperature=load.cell_temperature,
    )


@pytest.mark.parametrize("claim", ["in_domain (trust me)", "in_domain", "violated"])
def test_a_caller_string_is_not_an_applicability_verdict(claim):
    with pytest.raises(InvalidScientificProblem, match="ValidityAssessment"):
        assess_ocv_empirical_adequacy(CELL, AGREEING, applicability_status=claim)


def test_the_models_own_assessment_is_carried_as_its_status():
    applicability = _applicability()
    result = assess_ocv_empirical_adequacy(CELL, AGREEING, applicability_status=applicability)
    assert result.status is OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE
    assert result.applicability_status == applicability.status.value
    assert result.to_dict()["model_applicable_status"] == applicability.status.value


def test_an_outside_domain_assessment_is_carried_and_not_consulted():
    outside = ValidityAssessment(status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN, violated=("cell_temperature",))
    result = assess_ocv_empirical_adequacy(CELL, AGREEING, applicability_status=outside)
    assert result.status is OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE
    assert result.applicability_status == "outside_validated_domain"


def test_a_record_cannot_be_built_with_an_invented_status():
    with pytest.raises(InvalidScientificProblem, match="applicability"):
        OcvEmpiricalAssessment(status=OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE, alpha=0.01,
                               applicability_status="in_domain (trust me)")
