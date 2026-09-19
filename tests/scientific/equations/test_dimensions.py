from __future__ import annotations

from fractions import Fraction

import pytest

from engcore.scientific.equations import (
    BinaryExpression,
    BinaryOperator,
    DimensionVector,
    Equation,
    EquationDimensionError,
    FunctionExpression,
    FunctionName,
    PowerExpression,
    Symbol,
    assess_equation_dimensions,
    infer_dimension,
    require_equation_dimensions,
)


def test_ohms_law_is_dimensionally_valid():
    equation = Equation(
        Symbol("voltage"),
        BinaryExpression(
            BinaryOperator.MULTIPLY,
            Symbol("current"),
            Symbol("resistance"),
        ),
    )
    report = require_equation_dimensions(
        equation,
        {"voltage": "volt", "current": "ampere", "resistance": "ohm"},
    )
    assert report.valid
    assert report.left == report.right == DimensionVector.from_unit("volt")


def test_addition_rejects_incompatible_dimensions():
    expression = BinaryExpression(
        BinaryOperator.ADD,
        Symbol("length"),
        Symbol("time"),
    )
    with pytest.raises(EquationDimensionError) as caught:
        infer_dimension(expression, {"length": "meter", "time": "second"})
    assert caught.value.code == "dimension_mismatch"


def test_dimensionless_functions_reject_dimensional_arguments():
    expression = FunctionExpression(FunctionName.EXP, Symbol("length"))
    with pytest.raises(EquationDimensionError) as caught:
        infer_dimension(expression, {"length": "meter"})
    assert caught.value.code == "dimensionless_required"


def test_square_root_halves_dimension_exponents_exactly():
    expression = FunctionExpression(FunctionName.SQRT, Symbol("area"))
    inferred = infer_dimension(expression, {"area": "meter ** 2"})
    assert inferred == DimensionVector.from_unit("meter")


def test_fractional_power_uses_exact_rational_dimension_arithmetic():
    expression = PowerExpression(Symbol("volume"), Fraction(1, 3))
    inferred = infer_dimension(expression, {"volume": "meter ** 3"})
    assert inferred == DimensionVector.from_unit("meter")


def test_equation_side_mismatch_is_reported_without_a_fake_success():
    equation = Equation(Symbol("distance"), Symbol("duration"))
    report = assess_equation_dimensions(
        equation,
        {"distance": "meter", "duration": "second"},
    )
    assert not report.valid
    assert report.issue_code == "equation_side_mismatch"


def test_unknown_symbol_is_an_explicit_dimensional_failure():
    with pytest.raises(EquationDimensionError) as caught:
        infer_dimension(Symbol("missing"), {})
    assert caught.value.code == "unknown_symbol"
