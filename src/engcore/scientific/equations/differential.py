"""Structural ODE/PDE problem contract built from typed derivatives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..errors import InvalidScientificProblem
from .ast import (
    BinaryExpression, Constant, DerivativeExpression, Equation, Expression,
    FunctionExpression, PowerExpression, Symbol, UnaryExpression,
)
from .conditions import EquationCondition
from .dimensions import require_equation_dimensions


class DifferentialProblemKind(str, Enum):
    ODE = "ode"
    PDE = "pde"


def derivative(expression: Expression, *variables: str) -> DerivativeExpression:
    return DerivativeExpression(expression,tuple(variables))


def ordinary_derivative(expression: Expression, variable: str, order: int=1) -> DerivativeExpression:
    if isinstance(order,bool) or int(order)<1:
        raise InvalidScientificProblem("derivative order must be a positive integer")
    return DerivativeExpression(expression,(str(variable),)*int(order))


def partial_derivative(expression: Expression, *variables: str) -> DerivativeExpression:
    return DerivativeExpression(expression,tuple(variables))


def _derivatives(expression: Expression) -> tuple[DerivativeExpression,...]:
    if isinstance(expression,DerivativeExpression):
        return (expression,*_derivatives(expression.operand))
    if isinstance(expression,(Symbol,Constant)):
        return ()
    if isinstance(expression,UnaryExpression):
        return _derivatives(expression.operand)
    if isinstance(expression,BinaryExpression):
        return (*_derivatives(expression.left),*_derivatives(expression.right))
    if isinstance(expression,PowerExpression):
        return _derivatives(expression.base)
    if isinstance(expression,FunctionExpression):
        return _derivatives(expression.argument)
    raise TypeError(type(expression).__name__)


def laplacian(expression: Expression, coordinates: tuple[str,...]) -> Expression:
    coords=tuple(str(x).strip() for x in coordinates)
    if not coords or any(not x for x in coords):
        raise InvalidScientificProblem("laplacian requires one or more coordinates")
    terms=[DerivativeExpression(expression,(x,x)) for x in coords]
    current=terms[0]
    from .ast import BinaryOperator
    for term in terms[1:]:
        current=BinaryExpression(BinaryOperator.ADD,current,term)
    return current


@dataclass(frozen=True)
class DifferentialProblem:
    problem_id: str
    equations: tuple[Equation,...]
    independent_variables: tuple[str,...]
    dependent_symbols: tuple[str,...]
    symbol_units: dict[str,str]
    conditions: tuple[EquationCondition,...]=()

    def __post_init__(self) -> None:
        pid=str(self.problem_id).strip()
        if not pid:
            raise InvalidScientificProblem("differential problem requires id")
        object.__setattr__(self,"problem_id",pid)
        object.__setattr__(self,"equations",tuple(self.equations))
        object.__setattr__(self,"independent_variables",tuple(self.independent_variables))
        object.__setattr__(self,"dependent_symbols",tuple(self.dependent_symbols))
        object.__setattr__(self,"conditions",tuple(self.conditions))
        if not self.equations or any(not isinstance(e,Equation) for e in self.equations):
            raise InvalidScientificProblem("differential problem requires typed equations")
        if not self.independent_variables or len(set(self.independent_variables))!=len(self.independent_variables):
            raise InvalidScientificProblem("independent variables must be non-empty and unique")
        if not self.dependent_symbols or len(set(self.dependent_symbols))!=len(self.dependent_symbols):
            raise InvalidScientificProblem("dependent symbols must be non-empty and unique")
        if set(self.independent_variables)&set(self.dependent_symbols):
            raise InvalidScientificProblem("independent and dependent symbols must be disjoint")
        declared=set(self.symbol_units)
        needed=set(self.independent_variables)|set(self.dependent_symbols)
        if not needed<=declared:
            raise InvalidScientificProblem(f"differential problem lacks units for {sorted(needed-declared)}")
        derivatives=tuple(d for equation in self.equations for side in (equation.left,equation.right) for d in _derivatives(side))
        if not derivatives:
            raise InvalidScientificProblem("DifferentialProblem requires at least one derivative operator")
        for item in derivatives:
            unknown=set(item.variables)-set(self.independent_variables)
            if unknown:
                raise InvalidScientificProblem(f"derivative uses undeclared independent variables {sorted(unknown)}")
        for equation in self.equations:
            unknown=set(equation.symbols)-declared
            if unknown:
                raise InvalidScientificProblem(f"differential equation references undeclared symbols {sorted(unknown)}")
            require_equation_dimensions(equation,self.symbol_units)
        ids=[c.condition_id for c in self.conditions]
        if len(ids)!=len(set(ids)):
            raise InvalidScientificProblem("differential problem contains duplicate condition ids")
        for condition in self.conditions:
            condition.require_contract(self.symbol_units)

    @property
    def kind(self) -> DifferentialProblemKind:
        return DifferentialProblemKind.ODE if len(self.independent_variables)==1 else DifferentialProblemKind.PDE

    @property
    def derivative_order(self) -> int:
        return max(
            d.order for equation in self.equations for side in (equation.left,equation.right)
            for d in _derivatives(side)
        )

    def structural_issues(self) -> tuple[str,...]:
        issues=[]
        if not self.conditions:
            issues.append("no initial/boundary conditions are declared")
        if self.kind is DifferentialProblemKind.ODE and not any(c.kind.value=="initial" for c in self.conditions):
            issues.append("ODE declares no initial condition")
        if self.kind is DifferentialProblemKind.PDE and not any(c.kind.value=="boundary" for c in self.conditions):
            issues.append("PDE declares no boundary condition")
        return tuple(issues)
