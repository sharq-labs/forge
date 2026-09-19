from engcore.scientific.equations import (
    BinaryExpression, BinaryOperator, Equation, NondimensionalizationResult,
    Symbol, VariableScale, infer_dimension, nondimensionalize_equation,
)
from engcore.scientific.units.quantity import Quantity
from engcore.scientific.errors import InvalidScientificProblem
import pytest


def test_ohm_law_nondimensionalization_produces_dimensionless_residual_equation():
    equation=Equation(
        Symbol("V"),
        BinaryExpression(BinaryOperator.MULTIPLY,Symbol("I"),Symbol("R")),
    )
    result=nondimensionalize_equation(
        equation,
        {"V":"volt","I":"ampere","R":"ohm"},
        (
            VariableScale("V","V_hat",Quantity(5,"volt")),
            VariableScale("I","I_hat",Quantity(1,"ampere")),
            VariableScale("R","R_hat",Quantity(5,"ohm")),
        ),
        Quantity(5,"volt"),
    )
    assert infer_dimension(result.equation.left,result.symbol_units).is_dimensionless
    assert NondimensionalizationResult.from_dict(result.to_dict()).to_dict()==result.to_dict()


def test_nondimensional_variable_scale_cannot_be_zero():
    with pytest.raises(InvalidScientificProblem,match="cannot be zero"):
        VariableScale("V","V_hat",Quantity(0,"volt"))


def test_nondimensional_equation_scale_must_match_residual_dimension():
    equation=Equation(Symbol("V"),Symbol("W"))
    with pytest.raises(InvalidScientificProblem,match="residual dimension"):
        nondimensionalize_equation(
            equation,{"V":"volt","W":"volt"},
            (VariableScale("V","V_hat",Quantity(5,"volt")),
             VariableScale("W","W_hat",Quantity(5,"volt"))),
            Quantity(1,"second"),
        )
