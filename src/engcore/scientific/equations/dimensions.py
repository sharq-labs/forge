"""Symbolic dimensional reasoning for the equation IR.

Only dimensions are manipulated here; scale and magnitude are deliberately
absent.  Pint remains the authority for parsing units and mapping them to
physical dimensions.  This module turns that mapping into an exact rational
vector so algebra over dimensions is deterministic and serializable.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from ..units.quantity import dimension_of
from .ast import (
    BinaryExpression,
    BinaryOperator,
    Constant,
    DerivativeExpression,
    Equation,
    Expression,
    FunctionExpression,
    FunctionName,
    PowerExpression,
    Symbol,
    UnaryExpression,
)
from .errors import EquationDimensionError

DIMENSION_VECTOR_SCHEMA = schema_string("dimension_vector")
DIMENSION_REPORT_SCHEMA = schema_string("equation_dimension_report")


def _fraction(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise EquationDimensionError("invalid_dimension_exponent", "dimension exponent cannot be bool")
    if isinstance(value, int):
        return Fraction(value, 1)
    try:
        return Fraction(str(value))
    except Exception as exc:
        raise EquationDimensionError(
            "invalid_dimension_exponent",
            f"cannot represent dimension exponent {value!r} exactly",
        ) from exc


@dataclass(frozen=True)
class DimensionVector:
    exponents: tuple[tuple[str, Fraction], ...] = ()

    def __post_init__(self) -> None:
        merged: dict[str, Fraction] = {}
        for raw_name, raw_exponent in tuple(self.exponents):
            name = str(raw_name)
            exponent = _fraction(raw_exponent)
            merged[name] = merged.get(name, Fraction(0, 1)) + exponent
        normalized = tuple(
            (name, exponent)
            for name, exponent in sorted(merged.items())
            if exponent != 0
        )
        object.__setattr__(self, "exponents", normalized)

    @classmethod
    def dimensionless(cls) -> "DimensionVector":
        return cls(())

    @classmethod
    def from_unit(cls, unit: str) -> "DimensionVector":
        raw = dimension_of(unit)
        return cls(tuple((str(name), _fraction(exp)) for name, exp in raw.items()))

    @property
    def is_dimensionless(self) -> bool:
        return not self.exponents

    def multiply(self, other: "DimensionVector") -> "DimensionVector":
        return DimensionVector(self.exponents + other.exponents)

    def divide(self, other: "DimensionVector") -> "DimensionVector":
        return DimensionVector(
            self.exponents + tuple((name, -exp) for name, exp in other.exponents)
        )

    def power(self, exponent: Fraction) -> "DimensionVector":
        exact = _fraction(exponent)
        return DimensionVector(tuple((name, exp * exact) for name, exp in self.exponents))

    def render(self) -> str:
        if self.is_dimensionless:
            return "dimensionless"
        parts = []
        for name, exponent in self.exponents:
            if exponent.denominator == 1:
                parts.append(f"{name}^{exponent.numerator}")
            else:
                parts.append(
                    f"{name}^({exponent.numerator}/{exponent.denominator})"
                )
        return " * ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DIMENSION_VECTOR_SCHEMA,
            "exponents": [
                {
                    "dimension": name,
                    "numerator": exponent.numerator,
                    "denominator": exponent.denominator,
                }
                for name, exponent in self.exponents
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DimensionVector":
        require_schema(payload, DIMENSION_VECTOR_SCHEMA)
        values = []
        for item in payload.get("exponents", ()):
            values.append(
                (
                    str(item["dimension"]),
                    Fraction(int(item["numerator"]), int(item["denominator"])),
                )
            )
        return cls(tuple(values))


@dataclass(frozen=True)
class DimensionReport:
    valid: bool
    left: DimensionVector | None
    right: DimensionVector | None
    issue_code: str | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise EquationDimensionError(
                "invalid_dimension_report",
                "dimension report valid flag must be bool",
            )
        if self.valid:
            if self.left is None or self.right is None or self.left != self.right:
                raise EquationDimensionError(
                    "invalid_dimension_report",
                    "a valid dimension report requires equal recorded left/right dimensions",
                )
            if self.issue_code is not None:
                raise EquationDimensionError(
                    "invalid_dimension_report",
                    "a valid dimension report cannot carry an issue code",
                )
        elif not str(self.issue_code or "").strip():
            raise EquationDimensionError(
                "invalid_dimension_report",
                "an invalid dimension report must state an issue code",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DIMENSION_REPORT_SCHEMA,
            "valid": self.valid,
            "left": self.left.to_dict() if self.left is not None else None,
            "right": self.right.to_dict() if self.right is not None else None,
            "issue_code": self.issue_code,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DimensionReport":
        require_schema(payload, DIMENSION_REPORT_SCHEMA)
        left = payload.get("left")
        right = payload.get("right")
        return cls(
            valid=payload["valid"],
            left=DimensionVector.from_dict(left) if left is not None else None,
            right=DimensionVector.from_dict(right) if right is not None else None,
            issue_code=payload.get("issue_code"),
            message=payload.get("message", ""),
        )


def infer_dimension(
    expression: Expression,
    symbol_units: Mapping[str, str],
) -> DimensionVector:
    if isinstance(expression, Symbol):
        unit = symbol_units.get(expression.name)
        if unit is None:
            raise EquationDimensionError(
                "unknown_symbol",
                f"equation symbol {expression.name!r} has no declared unit",
            )
        return DimensionVector.from_unit(unit)

    if isinstance(expression, Constant):
        return DimensionVector.from_unit(expression.value.units)

    if isinstance(expression, UnaryExpression):
        return infer_dimension(expression.operand, symbol_units)

    if isinstance(expression, BinaryExpression):
        left = infer_dimension(expression.left, symbol_units)
        right = infer_dimension(expression.right, symbol_units)
        if expression.operator in (BinaryOperator.ADD, BinaryOperator.SUBTRACT):
            if left != right:
                raise EquationDimensionError(
                    "dimension_mismatch",
                    f"{expression.operator.value} requires equal dimensions; "
                    f"left is {left.render()}, right is {right.render()}",
                )
            return left
        if expression.operator is BinaryOperator.MULTIPLY:
            return left.multiply(right)
        if expression.operator is BinaryOperator.DIVIDE:
            return left.divide(right)
        raise AssertionError("closed BinaryOperator exhausted")

    if isinstance(expression, PowerExpression):
        return infer_dimension(expression.base, symbol_units).power(expression.exponent)

    if isinstance(expression, DerivativeExpression):
        result = infer_dimension(expression.operand, symbol_units)
        for variable in expression.variables:
            unit = symbol_units.get(variable)
            if unit is None:
                raise EquationDimensionError(
                    "unknown_derivative_variable",
                    f"derivative variable {variable!r} has no declared unit",
                )
            result = result.divide(DimensionVector.from_unit(unit))
        return result

    if isinstance(expression, FunctionExpression):
        argument = infer_dimension(expression.argument, symbol_units)
        if expression.function is FunctionName.SQRT:
            return argument.power(Fraction(1, 2))
        if not argument.is_dimensionless:
            raise EquationDimensionError(
                "dimensionless_required",
                f"{expression.function.value} requires a dimensionless argument; "
                f"found {argument.render()}",
            )
        return DimensionVector.dimensionless()

    raise TypeError(f"unsupported equation expression {type(expression).__name__}")


def assess_equation_dimensions(
    equation: Equation,
    symbol_units: Mapping[str, str],
) -> DimensionReport:
    left: DimensionVector | None = None
    right: DimensionVector | None = None
    try:
        left = infer_dimension(equation.left, symbol_units)
        right = infer_dimension(equation.right, symbol_units)
        if left != right:
            return DimensionReport(
                valid=False,
                left=left,
                right=right,
                issue_code="equation_side_mismatch",
                message=(
                    f"equation sides differ dimensionally: "
                    f"{left.render()} != {right.render()}"
                ),
            )
        return DimensionReport(valid=True, left=left, right=right)
    except EquationDimensionError as exc:
        return DimensionReport(
            valid=False,
            left=left,
            right=right,
            issue_code=exc.code,
            message=str(exc),
        )


def require_equation_dimensions(
    equation: Equation,
    symbol_units: Mapping[str, str],
) -> DimensionReport:
    report = assess_equation_dimensions(equation, symbol_units)
    if not report.valid:
        raise EquationDimensionError(
            report.issue_code or "invalid_equation_dimensions",
            report.message or "equation is dimensionally invalid",
        )
    return report
