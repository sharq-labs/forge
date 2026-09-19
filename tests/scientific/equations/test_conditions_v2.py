import pytest

from engcore.scientific.equations import (
    ConditionBinding, ConditionKind, Constant, Equation, EquationCondition,
    Symbol, evaluate_condition,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def initial():
    return EquationCondition(
        "initial-T",ConditionKind.INITIAL,
        Equation(Symbol("T"),Constant(Quantity(300,"kelvin"))),
        (ConditionBinding("t",Quantity(0,"second")),),
    )


def test_initial_condition_contract_round_trip_and_evaluation():
    condition=initial()
    condition.require_contract({"T":"kelvin","t":"second"})
    assert EquationCondition.from_dict(condition.to_dict())==condition
    result=evaluate_condition(
        condition,{"T":Quantity(300,"kelvin"),"t":Quantity(0,"second")}
    )
    assert result.residual.magnitude_in("kelvin")==pytest.approx(0)


def test_condition_refuses_a_conflicting_location_binding():
    with pytest.raises(InvalidScientificProblem,match="conflicts"):
        evaluate_condition(
            initial(),{"T":Quantity(300,"kelvin"),"t":Quantity(1,"second")}
        )
