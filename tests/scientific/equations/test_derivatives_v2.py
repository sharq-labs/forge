import pytest

from engcore.scientific.equations import (
    Constant, DerivativeExpression, Equation, Symbol, evaluate_equation, infer_dimension,
)
from engcore.scientific.equations.errors import EquationEvaluationError
from engcore.scientific.units.quantity import Quantity


def test_derivative_round_trip_dimension_and_explicit_solver_binding():
    derivative=DerivativeExpression(Symbol("T"),("t",))
    restored=DerivativeExpression.from_dict(derivative.to_dict())
    assert restored==derivative and restored.order==1
    assert infer_dimension(derivative,{"T":"kelvin","t":"second"}) == infer_dimension(
        Constant(Quantity(1,"kelvin / second")),{}
    )
    equation=Equation(derivative,Constant(Quantity(-2,"kelvin / second")))
    bindings={"T":Quantity(300,"kelvin"),"t":Quantity(1,"second")}
    with pytest.raises(EquationEvaluationError,match="explicit solver"):
        evaluate_equation(equation,bindings)
    evaluation=evaluate_equation(
        equation,bindings,
        derivative_bindings={derivative.binding_key:Quantity(-2,"kelvin / second")},
    )
    assert evaluation.residual.magnitude_in("kelvin / second")==pytest.approx(0)


def test_derivative_binding_with_wrong_dimension_is_refused():
    derivative=DerivativeExpression(Symbol("T"),("t",))
    equation=Equation(derivative,Constant(Quantity(0,"kelvin / second")))
    with pytest.raises(EquationEvaluationError,match="expected"):
        evaluate_equation(
            equation,{"T":Quantity(300,"kelvin"),"t":Quantity(0,"second")},
            derivative_bindings={derivative.binding_key:Quantity(1,"volt")},
        )
