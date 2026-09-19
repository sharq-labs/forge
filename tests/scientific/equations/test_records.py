from __future__ import annotations

import pytest

from engcore.scientific import Quantity
from engcore.scientific.equations import (
    DimensionReport,
    DimensionVector,
    EquationEvaluation,
    EquationDimensionError,
)
from engcore.scientific.errors import InvalidScientificProblem


def test_dimension_report_round_trip_preserves_validity_claim():
    vector = DimensionVector.from_unit("volt")
    report = DimensionReport(valid=True, left=vector, right=vector)
    assert DimensionReport.from_dict(report.to_dict()) == report


def test_forged_valid_dimension_report_with_mismatched_sides_is_refused():
    with pytest.raises(EquationDimensionError) as caught:
        DimensionReport(
            valid=True,
            left=DimensionVector.from_unit("meter"),
            right=DimensionVector.from_unit("second"),
        )
    assert caught.value.code == "invalid_dimension_report"


def test_invalid_dimension_report_must_name_the_failure():
    with pytest.raises(EquationDimensionError) as caught:
        DimensionReport(valid=False, left=None, right=None)
    assert caught.value.code == "invalid_dimension_report"


def test_equation_evaluation_round_trip_rechecks_residual_identity():
    record = EquationEvaluation(
        left=Quantity(10, "volt"),
        right=Quantity(8, "volt"),
        residual=Quantity(2, "volt"),
    )
    assert EquationEvaluation.from_dict(record.to_dict()) == record


def test_forged_equation_residual_is_refused():
    with pytest.raises(InvalidScientificProblem, match="left - right"):
        EquationEvaluation(
            left=Quantity(10, "volt"),
            right=Quantity(8, "volt"),
            residual=Quantity(3, "volt"),
        )
