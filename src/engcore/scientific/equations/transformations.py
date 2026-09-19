"""Semantics-preserving symbolic transformations with explicit side conditions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .ast import (
    BinaryExpression, BinaryOperator, Constant, DerivativeExpression, Equation,
    Expression, FunctionExpression, PowerExpression, Symbol, UnaryExpression,
    UnaryOperator, decode_expression, referenced_symbols,
)

TRANSFORMATION_CONDITION_SCHEMA=schema_string("equation_transformation_condition")
TRANSFORMATION_RESULT_SCHEMA=schema_string("equation_transformation_result")


class TransformationPredicate(str, Enum):
    NONZERO = "nonzero"


@dataclass(frozen=True)
class TransformationCondition:
    predicate: TransformationPredicate
    expression: Expression

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicate", TransformationPredicate(self.predicate))

        if not isinstance(self.expression,(Symbol,Constant,UnaryExpression,BinaryExpression,PowerExpression,FunctionExpression,DerivativeExpression)):
            raise InvalidScientificProblem("transformation side condition requires typed expression")

    def to_dict(self)->dict[str,Any]:
        return {"schema":TRANSFORMATION_CONDITION_SCHEMA,
                "predicate":self.predicate.value,"expression":self.expression.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"TransformationCondition":
        require_schema(payload,TRANSFORMATION_CONDITION_SCHEMA)
        return cls(TransformationPredicate(payload["predicate"]),decode_expression(payload["expression"]))


@dataclass(frozen=True)
class TransformationResult:
    equation: Equation
    conditions: tuple[TransformationCondition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.equation, Equation):
            raise InvalidScientificProblem("transformation result requires Equation")
        object.__setattr__(self, "conditions", tuple(self.conditions))

        if any(not isinstance(c,TransformationCondition) for c in self.conditions):
            raise InvalidScientificProblem("transformation result conditions must be typed")

    def to_dict(self)->dict[str,Any]:
        return {"schema":TRANSFORMATION_RESULT_SCHEMA,"equation":self.equation.to_dict(),
                "conditions":[c.to_dict() for c in self.conditions]}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"TransformationResult":
        require_schema(payload,TRANSFORMATION_RESULT_SCHEMA)
        return cls(Equation.from_dict(payload["equation"]),
                   tuple(TransformationCondition.from_dict(c) for c in payload.get("conditions",())))


def _key(expression: Expression) -> str:
    return json.dumps(expression.to_dict(), sort_keys=True, separators=(",", ":"))


def _collect(expression: Expression, operator: BinaryOperator) -> list[Expression]:
    if isinstance(expression, BinaryExpression) and expression.operator is operator:
        return [*_collect(expression.left, operator), *_collect(expression.right, operator)]
    return [expression]


def _fold(operator: BinaryOperator, expressions: list[Expression]) -> Expression:
    current=expressions[0]
    for expression in expressions[1:]:
        current=BinaryExpression(operator,current,expression)
    return current


def canonicalize(expression: Expression) -> Expression:
    if isinstance(expression, (Symbol, Constant)):
        return expression
    if isinstance(expression, UnaryExpression):
        operand=canonicalize(expression.operand)
        if expression.operator is UnaryOperator.NEGATE and isinstance(operand, UnaryExpression) and operand.operator is UnaryOperator.NEGATE:
            return canonicalize(operand.operand)
        return UnaryExpression(expression.operator,operand)
    if isinstance(expression, BinaryExpression):
        left,right=canonicalize(expression.left),canonicalize(expression.right)
        if expression.operator in (BinaryOperator.ADD,BinaryOperator.MULTIPLY):
            items=[canonicalize(x) for x in _collect(BinaryExpression(expression.operator,left,right),expression.operator)]
            items.sort(key=_key)
            return _fold(expression.operator,items)
        return BinaryExpression(expression.operator,left,right)
    if isinstance(expression, PowerExpression):
        return PowerExpression(canonicalize(expression.base),expression.exponent)
    if isinstance(expression, FunctionExpression):
        return FunctionExpression(expression.function,canonicalize(expression.argument))
    if isinstance(expression, DerivativeExpression):
        return DerivativeExpression(canonicalize(expression.operand),expression.variables)
    raise TypeError(type(expression).__name__)


def canonicalize_equation(equation: Equation) -> Equation:
    return Equation(canonicalize(equation.left),canonicalize(equation.right))


def structurally_equivalent(left: Equation, right: Equation) -> bool:
    a,b=canonicalize_equation(left),canonicalize_equation(right)
    direct=a.to_dict()==b.to_dict()
    swapped=a.left.to_dict()==b.right.to_dict() and a.right.to_dict()==b.left.to_dict()
    return direct or swapped


def substitute(expression: Expression, replacements: Mapping[str, Expression]) -> Expression:
    if isinstance(expression, Symbol):
        return replacements.get(expression.name,expression)
    if isinstance(expression, Constant):
        return expression
    if isinstance(expression, UnaryExpression):
        return UnaryExpression(expression.operator,substitute(expression.operand,replacements))
    if isinstance(expression, BinaryExpression):
        return BinaryExpression(expression.operator,substitute(expression.left,replacements),substitute(expression.right,replacements))
    if isinstance(expression, PowerExpression):
        return PowerExpression(substitute(expression.base,replacements),expression.exponent)
    if isinstance(expression, FunctionExpression):
        return FunctionExpression(expression.function,substitute(expression.argument,replacements))
    if isinstance(expression, DerivativeExpression):
        # Differentiation variables name coordinates and are not renamed implicitly.
        return DerivativeExpression(substitute(expression.operand,replacements),expression.variables)
    raise TypeError(type(expression).__name__)


def substitute_equation(equation: Equation, replacements: Mapping[str, Expression]) -> Equation:
    return Equation(substitute(equation.left,replacements),substitute(equation.right,replacements))


def _count(expression: Expression, target: str) -> int:
    if isinstance(expression, Symbol):
        return int(expression.name==target)
    if isinstance(expression, Constant):
        return 0
    if isinstance(expression, UnaryExpression):
        return _count(expression.operand,target)
    if isinstance(expression, BinaryExpression):
        return _count(expression.left,target)+_count(expression.right,target)
    if isinstance(expression, PowerExpression):
        return _count(expression.base,target)
    if isinstance(expression, FunctionExpression):
        return _count(expression.argument,target)
    if isinstance(expression, DerivativeExpression):
        return _count(expression.operand,target)
    raise TypeError(type(expression).__name__)


def isolate_symbol(equation: Equation, target: str) -> TransformationResult:
    """Isolate one occurrence through reversible algebraic operations.

    Nonzero requirements introduced by division are returned as side conditions.
    Non-invertible functions/powers and multiple occurrences are refused rather
    than silently choosing a branch.
    """
    target=str(target).strip()
    if not target:
        raise InvalidScientificProblem("isolate_symbol requires a target")
    left_count,right_count=_count(equation.left,target),_count(equation.right,target)
    if left_count+right_count != 1:
        raise InvalidScientificProblem("safe isolation requires exactly one target occurrence")
    lhs,rhs=(equation.left,equation.right) if left_count else (equation.right,equation.left)
    conditions=[]

    def peel(node: Expression, other: Expression) -> Equation:
        if isinstance(node,Symbol) and node.name==target:
            return Equation(node,other)
        if isinstance(node,UnaryExpression) and node.operator is UnaryOperator.NEGATE:
            return peel(node.operand,UnaryExpression(UnaryOperator.NEGATE,other))
        if not isinstance(node,BinaryExpression):
            raise InvalidScientificProblem("target is inside an operation without a single-valued safe inverse")
        lc,rc=_count(node.left,target),_count(node.right,target)
        if lc+rc != 1:
            raise InvalidScientificProblem("safe isolation encountered multiple target occurrences")
        if node.operator is BinaryOperator.ADD:
            return peel(node.left if lc else node.right,
                        BinaryExpression(BinaryOperator.SUBTRACT,other,node.right if lc else node.left))
        if node.operator is BinaryOperator.SUBTRACT:
            if lc:
                return peel(node.left,BinaryExpression(BinaryOperator.ADD,other,node.right))
            return peel(node.right,BinaryExpression(BinaryOperator.SUBTRACT,node.left,other))
        if node.operator is BinaryOperator.MULTIPLY:
            factor=node.right if lc else node.left
            conditions.append(TransformationCondition(TransformationPredicate.NONZERO,factor))
            return peel(node.left if lc else node.right,BinaryExpression(BinaryOperator.DIVIDE,other,factor))
        if node.operator is BinaryOperator.DIVIDE:
            if lc:
                conditions.append(TransformationCondition(TransformationPredicate.NONZERO,node.right))
                return peel(node.left,BinaryExpression(BinaryOperator.MULTIPLY,other,node.right))
            conditions.append(TransformationCondition(TransformationPredicate.NONZERO,other))
            conditions.append(TransformationCondition(TransformationPredicate.NONZERO,node.right))
            return peel(node.right,BinaryExpression(BinaryOperator.DIVIDE,node.left,other))
        raise AssertionError("closed binary operator exhausted")

    isolated=peel(lhs,rhs)
    return TransformationResult(canonicalize_equation(isolated),tuple(conditions))


def scale_equation(equation: Equation, factor: Expression) -> TransformationResult:
    condition=TransformationCondition(TransformationPredicate.NONZERO,factor)
    return TransformationResult(
        Equation(BinaryExpression(BinaryOperator.MULTIPLY,equation.left,factor),
                 BinaryExpression(BinaryOperator.MULTIPLY,equation.right,factor)),
        (condition,),
    )
