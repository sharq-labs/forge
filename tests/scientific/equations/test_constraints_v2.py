import pytest

from engcore.scientific.equations import (
    Constant, ConstraintEvaluation, ExpressionConstraint, RelationOperator,
    Symbol, evaluate_constraint,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.equations.errors import EquationDimensionError
from engcore.scientific.units.quantity import Quantity


def test_symbolic_constraint_is_dimension_checked_and_executable():
    constraint=ExpressionConstraint(
        "temperature-limit",Symbol("T"),RelationOperator.LESS_EQUAL,
        Constant(Quantity(350,"kelvin")),Quantity(1,"kelvin"),
    )
    constraint.require_dimensions({"T":"kelvin"})
    result=evaluate_constraint(constraint,{"T":Quantity(351,"kelvin")})
    assert result.satisfied and result.margin.magnitude==pytest.approx(0)


def test_symbolic_constraint_rejects_dimension_mismatch():
    constraint=ExpressionConstraint(
        "bad",Symbol("T"),RelationOperator.LESS_EQUAL,Constant(Quantity(1,"volt"))
    )
    with pytest.raises(EquationDimensionError):
        constraint.require_dimensions({"T":"kelvin"})


def test_constraint_wire_verdict_is_rederived():
    constraint=ExpressionConstraint(
        "limit",Symbol("T"),RelationOperator.LESS_EQUAL,Constant(Quantity(350,"kelvin"))
    )
    payload=evaluate_constraint(constraint,{"T":Quantity(300,"kelvin")}).to_dict()
    payload["satisfied"]=False
    with pytest.raises(InvalidScientificProblem,match="verdict"):
        ConstraintEvaluation.from_dict(payload)
