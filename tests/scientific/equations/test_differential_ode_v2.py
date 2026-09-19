import pytest

from engcore.scientific.equations import (
    BinaryExpression, BinaryOperator, ConditionBinding, ConditionKind, Constant,
    DerivativeExpression, DifferentialProblem, DifferentialProblemKind, Equation,
    EquationCondition, Symbol, UnaryExpression, UnaryOperator,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def cooling_problem():
    rate=DerivativeExpression(Symbol("T"),("t",))
    rhs=UnaryExpression(
        UnaryOperator.NEGATE,
        BinaryExpression(BinaryOperator.MULTIPLY,Symbol("k"),Symbol("T")),
    )
    initial=EquationCondition(
        "initial",ConditionKind.INITIAL,
        Equation(Symbol("T"),Constant(Quantity(300,"kelvin"))),
        (ConditionBinding("t",Quantity(0,"second")),),
    )
    return DifferentialProblem(
        "cooling",(Equation(rate,rhs),),("t",),("T",),
        {"T":"kelvin","t":"second","k":"1 / second"},(initial,),
    )


def test_ode_contract_classifies_order_conditions_and_round_trips():
    problem=cooling_problem()
    assert problem.kind is DifferentialProblemKind.ODE
    assert problem.derivative_order==1
    assert problem.structural_issues()==()
    assert DifferentialProblem.from_dict(problem.to_dict()).to_dict()==problem.to_dict()


def test_differential_wire_kind_is_derived_not_trusted():
    payload=cooling_problem().to_dict();payload["kind"]="pde"
    with pytest.raises(InvalidScientificProblem,match="forged"):
        DifferentialProblem.from_dict(payload)
