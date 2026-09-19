from __future__ import annotations

from fractions import Fraction

import pytest

from engcore.scientific.equations import (
    BinaryExpression,
    BinaryOperator,
    Constant,
    Equation,
    FunctionExpression,
    FunctionName,
    PowerExpression,
    Symbol,
    UnaryExpression,
    UnaryOperator,
    decode_expression,
    referenced_symbols,
)
from engcore.scientific import Quantity
from engcore.scientific.errors import InvalidScientificProblem


def test_expression_tree_round_trips_without_executable_text():
    expression = BinaryExpression(
        BinaryOperator.MULTIPLY,
        UnaryExpression(UnaryOperator.ABSOLUTE, Symbol("current")),
        PowerExpression(Symbol("resistance"), Fraction(1, 1)),
    )
    rebuilt = decode_expression(expression.to_dict())
    assert rebuilt == expression
    assert referenced_symbols(rebuilt) == frozenset({"current", "resistance"})


def test_equation_round_trip_preserves_both_sides():
    equation = Equation(
        Symbol("voltage"),
        BinaryExpression(
            BinaryOperator.MULTIPLY,
            Symbol("current"),
            Symbol("resistance"),
        ),
    )
    assert Equation.from_dict(equation.to_dict()) == equation


def test_constants_are_typed_quantities():
    with pytest.raises(InvalidScientificProblem):
        Constant(3.0)  # type: ignore[arg-type]
    assert Constant(Quantity(3, "meter")).value.units == "meter"


def test_power_exponents_are_exact_not_floating_guesses():
    with pytest.raises(InvalidScientificProblem):
        PowerExpression(Symbol("x"), 0.5)  # type: ignore[arg-type]
    assert PowerExpression(Symbol("x"), Fraction(1, 2)).exponent == Fraction(1, 2)


def test_unknown_expression_schema_is_refused():
    with pytest.raises(Exception, match="unknown equation expression schema"):
        decode_expression({"schema": "made_up/99", "code": "__import__('os')"})


def test_function_names_are_closed_enum():
    with pytest.raises(ValueError):
        FunctionExpression("user_callable", Symbol("x"))  # type: ignore[arg-type]
