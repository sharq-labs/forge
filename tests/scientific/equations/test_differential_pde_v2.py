from engcore.scientific.equations import (
    BinaryExpression, BinaryOperator, ConditionBinding, ConditionKind, Constant,
    DerivativeExpression, DifferentialProblem, DifferentialProblemKind, Equation,
    EquationCondition, Symbol, laplacian,
)
from engcore.scientific.units.quantity import Quantity


def test_two_space_dimensional_heat_equation_is_dimensionally_complete():
    time_rate=DerivativeExpression(Symbol("T"),("t",))
    diffusion=BinaryExpression(
        BinaryOperator.MULTIPLY,Symbol("alpha"),laplacian(Symbol("T"),("x","y"))
    )
    boundary=EquationCondition(
        "left-wall",ConditionKind.BOUNDARY,
        Equation(Symbol("T"),Constant(Quantity(300,"kelvin"))),
        (ConditionBinding("x",Quantity(0,"meter")),),"left",
    )
    initial=EquationCondition(
        "initial",ConditionKind.INITIAL,
        Equation(Symbol("T"),Constant(Quantity(300,"kelvin"))),
        (ConditionBinding("t",Quantity(0,"second")),),
    )
    problem=DifferentialProblem(
        "heat-2d",(Equation(time_rate,diffusion),),("x","y","t"),("T",),
        {"T":"kelvin","x":"meter","y":"meter","t":"second","alpha":"meter ** 2 / second"},
        (boundary,initial),
    )
    assert problem.kind is DifferentialProblemKind.PDE
    assert problem.derivative_order==2
    assert problem.structural_issues()==()
