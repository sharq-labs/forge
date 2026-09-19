"""Typed, serializable expression tree for scientific equations.

The tree is deliberately closed and contains no executable strings.  Scientific
expressions are data: symbols, quantities, algebraic operators and a small
enumerated set of mathematical functions.  Nothing here calls eval/exec or
accepts arbitrary callables.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from .errors import EquationIRError

SYMBOL_SCHEMA = schema_string("equation_symbol")
CONSTANT_SCHEMA = schema_string("equation_constant")
UNARY_SCHEMA = schema_string("equation_unary")
BINARY_SCHEMA = schema_string("equation_binary")
POWER_SCHEMA = schema_string("equation_power")
FUNCTION_SCHEMA = schema_string("equation_function")
DERIVATIVE_SCHEMA = schema_string("equation_derivative")
EQUATION_SCHEMA = schema_string("scientific_equation")


class UnaryOperator(str, Enum):
    NEGATE = "negate"
    ABSOLUTE = "absolute"


class BinaryOperator(str, Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"


class FunctionName(str, Enum):
    SQRT = "sqrt"
    EXP = "exp"
    LOG = "log"
    SIN = "sin"
    COS = "cos"
    TAN = "tan"


@dataclass(frozen=True)
class Symbol:
    name: str

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise InvalidScientificProblem("equation symbol name must be non-empty")
        object.__setattr__(self, "name", name)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SYMBOL_SCHEMA, "name": self.name}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Symbol":
        require_schema(payload, SYMBOL_SCHEMA)
        return cls(name=payload["name"])


@dataclass(frozen=True)
class Constant:
    value: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem("equation constant must be a Quantity")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONSTANT_SCHEMA, "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Constant":
        require_schema(payload, CONSTANT_SCHEMA)
        return cls(value=Quantity.from_dict(payload["value"]))


@dataclass(frozen=True)
class UnaryExpression:
    operator: UnaryOperator
    operand: "Expression"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator", UnaryOperator(self.operator))
        _require_expression(self.operand, context="unary operand")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNARY_SCHEMA,
            "operator": self.operator.value,
            "operand": self.operand.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UnaryExpression":
        require_schema(payload, UNARY_SCHEMA)
        return cls(
            operator=UnaryOperator(payload["operator"]),
            operand=decode_expression(payload["operand"]),
        )


@dataclass(frozen=True)
class BinaryExpression:
    operator: BinaryOperator
    left: "Expression"
    right: "Expression"

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator", BinaryOperator(self.operator))
        _require_expression(self.left, context="binary left operand")
        _require_expression(self.right, context="binary right operand")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BINARY_SCHEMA,
            "operator": self.operator.value,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BinaryExpression":
        require_schema(payload, BINARY_SCHEMA)
        return cls(
            operator=BinaryOperator(payload["operator"]),
            left=decode_expression(payload["left"]),
            right=decode_expression(payload["right"]),
        )


def _coerce_exponent(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise InvalidScientificProblem("equation exponent cannot be bool")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value, 1)
    raise InvalidScientificProblem(
        "equation exponent must be an exact int or Fraction; floats are refused"
    )


@dataclass(frozen=True)
class PowerExpression:
    base: "Expression"
    exponent: Fraction

    def __post_init__(self) -> None:
        _require_expression(self.base, context="power base")
        object.__setattr__(self, "exponent", _coerce_exponent(self.exponent))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": POWER_SCHEMA,
            "base": self.base.to_dict(),
            "numerator": self.exponent.numerator,
            "denominator": self.exponent.denominator,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PowerExpression":
        require_schema(payload, POWER_SCHEMA)
        numerator = payload["numerator"]
        denominator = payload["denominator"]
        if isinstance(numerator, bool) or not isinstance(numerator, int):
            raise InvalidScientificProblem("power numerator must be an int")
        if isinstance(denominator, bool) or not isinstance(denominator, int):
            raise InvalidScientificProblem("power denominator must be an int")
        if denominator == 0:
            raise InvalidScientificProblem("power denominator cannot be zero")
        return cls(
            base=decode_expression(payload["base"]),
            exponent=Fraction(numerator, denominator),
        )


@dataclass(frozen=True)
class FunctionExpression:
    function: FunctionName
    argument: "Expression"

    def __post_init__(self) -> None:
        object.__setattr__(self, "function", FunctionName(self.function))
        _require_expression(self.argument, context="function argument")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FUNCTION_SCHEMA,
            "function": self.function.value,
            "argument": self.argument.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FunctionExpression":
        require_schema(payload, FUNCTION_SCHEMA)
        return cls(
            function=FunctionName(payload["function"]),
            argument=decode_expression(payload["argument"]),
        )


@dataclass(frozen=True)
class DerivativeExpression:
    """A typed ordinary/partial derivative.

    variables is the ordered differentiation sequence.  (x, x) is a second x
    derivative; (x, t) is a mixed partial.  This node records the operator only:
    numerical derivative values must come from a solver/discretization.
    """

    operand: "Expression"
    variables: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_expression(self.operand, context="derivative operand")
        variables = tuple(str(v).strip() for v in self.variables)
        if not variables or any(not v for v in variables):
            raise InvalidScientificProblem("equation derivative requires one or more variable names")
        object.__setattr__(self, "variables", variables)

    @property
    def order(self) -> int:
        return len(self.variables)

    @property
    def binding_key(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "derivative:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DERIVATIVE_SCHEMA,
            "operand": self.operand.to_dict(),
            "variables": list(self.variables),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DerivativeExpression":
        require_schema(payload, DERIVATIVE_SCHEMA)
        return cls(
            operand=decode_expression(payload["operand"]),
            variables=tuple(payload.get("variables", ())),
        )


Expression = Symbol | Constant | UnaryExpression | BinaryExpression | PowerExpression | FunctionExpression | DerivativeExpression
_EXPRESSION_TYPES = (
    Symbol,
    Constant,
    UnaryExpression,
    BinaryExpression,
    PowerExpression,
    FunctionExpression,
    DerivativeExpression,
)


def _require_expression(value: Any, *, context: str) -> Expression:
    if not isinstance(value, _EXPRESSION_TYPES):
        raise InvalidScientificProblem(
            f"{context}: expected a typed equation expression, got {type(value).__name__}"
        )
    return value


_DECODERS = {
    SYMBOL_SCHEMA: Symbol,
    CONSTANT_SCHEMA: Constant,
    UNARY_SCHEMA: UnaryExpression,
    BINARY_SCHEMA: BinaryExpression,
    POWER_SCHEMA: PowerExpression,
    FUNCTION_SCHEMA: FunctionExpression,
    DERIVATIVE_SCHEMA: DerivativeExpression,
}


def decode_expression(payload: Mapping[str, Any]) -> Expression:
    if not isinstance(payload, Mapping):
        raise EquationIRError(
            f"equation expression payload must be a mapping, got {type(payload).__name__}"
        )
    decoder = _DECODERS.get(payload.get("schema"))
    if decoder is None:
        raise EquationIRError(
            f"unknown equation expression schema {payload.get('schema')!r}"
        )
    return decoder.from_dict(payload)


def referenced_symbols(expression: Expression) -> frozenset[str]:
    _require_expression(expression, context="symbol walk")
    if isinstance(expression, Symbol):
        return frozenset({expression.name})
    if isinstance(expression, Constant):
        return frozenset()
    if isinstance(expression, UnaryExpression):
        return referenced_symbols(expression.operand)
    if isinstance(expression, BinaryExpression):
        return referenced_symbols(expression.left) | referenced_symbols(expression.right)
    if isinstance(expression, PowerExpression):
        return referenced_symbols(expression.base)
    if isinstance(expression, FunctionExpression):
        return referenced_symbols(expression.argument)
    if isinstance(expression, DerivativeExpression):
        return referenced_symbols(expression.operand) | frozenset(expression.variables)
    raise AssertionError("closed expression union exhausted")


@dataclass(frozen=True)
class Equation:
    left: Expression
    right: Expression

    def __post_init__(self) -> None:
        _require_expression(self.left, context="equation left side")
        _require_expression(self.right, context="equation right side")

    @property
    def symbols(self) -> frozenset[str]:
        return referenced_symbols(self.left) | referenced_symbols(self.right)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EQUATION_SCHEMA,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Equation":
        require_schema(payload, EQUATION_SCHEMA)
        return cls(
            left=decode_expression(payload["left"]),
            right=decode_expression(payload["right"]),
        )
