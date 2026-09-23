"""Structural, serializable ODE/PDE problem contract built from typed derivatives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..results.immutable import freeze
from ..serialization import require_schema, schema_string
from ..units.validation import require_unit
from .ast import (
    BinaryExpression, BinaryOperator, Constant, DerivativeExpression, Equation,
    Expression, FunctionExpression, PowerExpression, Symbol, UnaryExpression,
)
from .conditions import EquationCondition
from .dimensions import require_equation_dimensions

DIFFERENTIAL_PROBLEM_SCHEMA=schema_string("scientific_differential_problem")


class DifferentialProblemKind(str, Enum):
    ODE="ode"
    PDE="pde"


def derivative(expression:Expression,*variables:str)->DerivativeExpression:
    return DerivativeExpression(expression,tuple(variables))


def ordinary_derivative(expression:Expression,variable:str,order:int=1)->DerivativeExpression:
    if isinstance(order,bool) or not isinstance(order,int) or order<1:
        raise InvalidScientificProblem("derivative order must be a positive integer")
    return DerivativeExpression(expression,(str(variable),)*order)


def partial_derivative(expression:Expression,*variables:str)->DerivativeExpression:
    return DerivativeExpression(expression,tuple(variables))


def _derivatives(expression:Expression)->tuple[DerivativeExpression,...]:
    if isinstance(expression,DerivativeExpression):
        return (expression,*_derivatives(expression.operand))
    if isinstance(expression,(Symbol,Constant)): return ()
    if isinstance(expression,UnaryExpression): return _derivatives(expression.operand)
    if isinstance(expression,BinaryExpression):
        return (*_derivatives(expression.left),*_derivatives(expression.right))
    if isinstance(expression,PowerExpression): return _derivatives(expression.base)
    if isinstance(expression,FunctionExpression): return _derivatives(expression.argument)
    raise TypeError(type(expression).__name__)


def laplacian(expression:Expression,coordinates:tuple[str,...])->Expression:
    coords=tuple(str(x).strip() for x in coordinates)
    if not coords or any(not x for x in coords) or len(coords)!=len(set(coords)):
        raise InvalidScientificProblem("laplacian requires unique non-empty coordinates")
    terms=[DerivativeExpression(expression,(x,x)) for x in coords]
    current:Expression=terms[0]
    for term in terms[1:]:
        current=BinaryExpression(BinaryOperator.ADD,current,term)
    return current


@dataclass(frozen=True)
class DifferentialProblem:
    problem_id:str
    equations:tuple[Equation,...]
    independent_variables:tuple[str,...]
    dependent_symbols:tuple[str,...]
    symbol_units:Mapping[str,str]
    conditions:tuple[EquationCondition,...]=()

    def __post_init__(self)->None:
        pid=str(self.problem_id).strip()
        independent=tuple(str(x).strip() for x in self.independent_variables)
        dependent=tuple(str(x).strip() for x in self.dependent_symbols)
        units={str(k).strip():require_unit(v,context=f"differential symbol {k!r}") for k,v in dict(self.symbol_units).items()}
        if not pid: raise InvalidScientificProblem("differential problem requires id")
        if not self.equations or any(not isinstance(e,Equation) for e in self.equations):
            raise InvalidScientificProblem("differential problem requires typed equations")
        if not independent or any(not x for x in independent) or len(independent)!=len(set(independent)):
            raise InvalidScientificProblem("independent variables must be non-empty and unique")
        if not dependent or any(not x for x in dependent) or len(dependent)!=len(set(dependent)):
            raise InvalidScientificProblem("dependent symbols must be non-empty and unique")
        if set(independent)&set(dependent):
            raise InvalidScientificProblem("independent and dependent symbols must be disjoint")
        object.__setattr__(self,"problem_id",pid)
        object.__setattr__(self,"equations",tuple(self.equations))
        object.__setattr__(self,"independent_variables",independent)
        object.__setattr__(self,"dependent_symbols",dependent)
        object.__setattr__(self,"symbol_units",freeze(units))
        object.__setattr__(self,"conditions",tuple(self.conditions))
        declared=set(units)
        needed=set(independent)|set(dependent)
        if not needed<=declared:
            raise InvalidScientificProblem(f"differential problem lacks units for {sorted(needed-declared)}")
        derivatives=tuple(
            d for equation in self.equations for side in (equation.left,equation.right)
            for d in _derivatives(side)
        )
        if not derivatives:
            raise InvalidScientificProblem("DifferentialProblem requires at least one derivative operator")
        for item in derivatives:
            unknown=set(item.variables)-set(independent)
            if unknown:
                raise InvalidScientificProblem(f"derivative uses undeclared independent variables {sorted(unknown)}")
        for equation in self.equations:
            unknown=set(equation.symbols)-declared
            if unknown:
                raise InvalidScientificProblem(f"differential equation references undeclared symbols {sorted(unknown)}")
            require_equation_dimensions(equation,units)
        ids=[c.condition_id for c in self.conditions]
        if len(ids)!=len(set(ids)):
            raise InvalidScientificProblem("differential problem contains duplicate condition ids")
        for condition in self.conditions:
            condition.require_contract(units)

    @property
    def kind(self)->DifferentialProblemKind:
        return DifferentialProblemKind.ODE if len(self.independent_variables)==1 else DifferentialProblemKind.PDE

    @property
    def derivative_order(self)->int:
        return max(
            d.order for equation in self.equations for side in (equation.left,equation.right)
            for d in _derivatives(side)
        )

    def structural_issues(self)->tuple[str,...]:
        issues=[]
        if not self.conditions: issues.append("no initial/boundary conditions are declared")
        if self.kind is DifferentialProblemKind.ODE and not any(c.kind.value=="initial" for c in self.conditions):
            issues.append("ODE declares no initial condition")
        if self.kind is DifferentialProblemKind.PDE and not any(c.kind.value=="boundary" for c in self.conditions):
            issues.append("PDE declares no boundary condition")
        return tuple(issues)

    def to_dict(self)->dict[str,Any]:
        return {
            "schema":DIFFERENTIAL_PROBLEM_SCHEMA,"problem_id":self.problem_id,
            "equations":[e.to_dict() for e in self.equations],
            "independent_variables":list(self.independent_variables),
            "dependent_symbols":list(self.dependent_symbols),
            "symbol_units":dict(sorted(self.symbol_units.items())),
            "conditions":[c.to_dict() for c in self.conditions],
            "kind":self.kind.value,"derivative_order":self.derivative_order,
            "structural_issues":list(self.structural_issues()),
        }

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"DifferentialProblem":
        require_schema(payload,DIFFERENTIAL_PROBLEM_SCHEMA)
        problem=cls(
            payload["problem_id"],tuple(Equation.from_dict(x) for x in payload.get("equations",())),
            tuple(payload.get("independent_variables",())),tuple(payload.get("dependent_symbols",())),
            dict(payload.get("symbol_units",{})),
            tuple(EquationCondition.from_dict(x) for x in payload.get("conditions",())),
        )
        derived={"kind":problem.kind.value,"derivative_order":problem.derivative_order,
                 "structural_issues":list(problem.structural_issues())}
        for key,value in derived.items():
            if key in payload and payload[key]!=value:
                raise InvalidScientificProblem(f"serialized differential {key} is forged or stale")
        return problem
