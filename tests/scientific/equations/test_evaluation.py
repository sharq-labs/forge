from __future__ import annotations

import math

import pytest

from engcore.scientific import Quantity
from engcore.scientific.equations import (
    BinaryExpression,
    BinaryOperator,
    Equation,
    EquationEvaluationError,
    FunctionExpression,
    FunctionName,
    Symbol,
    evaluate_equation,
    evaluate_expression,
)


def test_ohms_law_evaluates_to_zero_residual():
    equation = Equation(
        Symbol("voltage"),
        BinaryExpression(
            BinaryOperator.MULTIPLY,
            Symbol("current"),
            Symbol("resistance"),
        ),
    )
    result = evaluate_equation(
        equation,
        {
            "voltage": Quantity(10, "volt"),
            "current": Quantity(2, "ampere"),
            "resistance": Quantity(5, "ohm"),
        },
    )
    assert result.residual.is_compatible_with("volt")
    assert abs(result.residual.magnitude_in("volt")) < 1e-12


def test_sqrt_preserves_the_correct_result_dimension():
    result = evaluate_expression(
        FunctionExpression(FunctionName.SQRT, Symbol("area")),
        {"area": Quantity(9, "meter ** 2")},
    )
    assert result.is_compatible_with("meter")
    assert result.magnitude_in("meter") == pytest.approx(3.0)


def test_transcendental_function_requires_dimensionless_value():
    with pytest.raises(EquationEvaluationError) as caught:
        evaluate_expression(
            FunctionExpression(FunctionName.SIN, Symbol("length")),
            {"length": Quantity(1, "meter")},
        )
    assert caught.value.code == "dimensionless_required"


def test_dimensionless_exp_is_evaluated_numerically():
    result = evaluate_expression(
        FunctionExpression(FunctionName.EXP, Symbol("x")),
        {"x": Quantity.dimensionless(1)},
    )
    assert result.units == "dimensionless"
    assert result.magnitude == pytest.approx(math.e)


def test_division_by_zero_is_refused_explicitly():
    expression = BinaryExpression(BinaryOperator.DIVIDE, Symbol("x"), Symbol("y"))
    with pytest.raises(EquationEvaluationError) as caught:
        evaluate_expression(
            expression,
            {"x": Quantity(1, "meter"), "y": Quantity(0, "second")},
        )
    assert caught.value.code == "division_by_zero"
