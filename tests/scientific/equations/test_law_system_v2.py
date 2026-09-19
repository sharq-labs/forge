import pytest

from engcore.scientific.equations import (
    BinaryExpression, BinaryOperator, CheckableAssumption, ConditionBinding,
    ConditionKind, Constant, DerivativeExpression, Equation, EquationCondition,
    EquationSymbol, ExpressionConstraint, LawDefinition, RelationOperator,
    ScientificLawSystem, Symbol, UnaryExpression, UnaryOperator, AssumptionStatus,
)
from engcore.scientific.units.quantity import Quantity


def system():
    derivative=DerivativeExpression(Symbol("T"),("t",))
    equation=Equation(
        derivative,
        UnaryExpression(
            UnaryOperator.NEGATE,
            BinaryExpression(BinaryOperator.MULTIPLY,Symbol("k"),Symbol("T")),
        ),
    )
    law=LawDefinition(
        "cooling","Cooling",equation,
        (EquationSymbol("T","kelvin"),EquationSymbol("t","second"),EquationSymbol("k","1 / second")),
    )
    assumption=CheckableAssumption(
        "positive-k",
        ExpressionConstraint("k-positive",Symbol("k"),RelationOperator.GREATER_THAN,
                             Constant(Quantity(0,"1 / second"))),
    )
    initial=EquationCondition(
        "initial",ConditionKind.INITIAL,
        Equation(Symbol("T"),Constant(Quantity(300,"kelvin"))),
        (ConditionBinding("t",Quantity(0,"second")),),
    )
    return ScientificLawSystem(law,(assumption,),(initial,)),derivative


def test_law_system_binds_assumptions_conditions_and_differential_evidence():
    law_system,derivative=system()
    bindings={"T":Quantity(300,"kelvin"),"t":Quantity(0,"second"),"k":Quantity(0.1,"1 / second")}
    assert law_system.assess_assumptions(bindings)[0].status is AssumptionStatus.SATISFIED
    evaluation=law_system.law.evaluate(
        bindings,derivative_bindings={derivative.binding_key:Quantity(-30,"kelvin / second")}
    )
    assert evaluation.residual.magnitude_in("kelvin / second")==pytest.approx(0)
    assert ScientificLawSystem.from_dict(law_system.to_dict()).to_dict()==law_system.to_dict()


def test_law_system_rejects_dimensionally_invalid_machine_assumption():
    law_system,_=system()
    bad=CheckableAssumption(
        "bad",
        ExpressionConstraint(
            "bad-dimension",Symbol("k"),RelationOperator.LESS_EQUAL,
            Constant(Quantity(1,"kelvin")),
        ),
    )
    with pytest.raises(Exception):
        ScientificLawSystem(law_system.law,(bad,),law_system.conditions)
