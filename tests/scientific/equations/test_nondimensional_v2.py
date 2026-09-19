from engcore.scientific.equations import (
    BinaryExpression, BinaryOperator, Equation, NondimensionalizationResult,
    Symbol, VariableScale, infer_dimension, nondimensionalize_equation,
)
from engcore.scientific.units.quantity import Quantity


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
