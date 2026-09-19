"""Numerical evaluation of typed equation expressions.

Evaluation is intentionally separate from dimensional validation.  The law
layer validates its symbolic contract first, then this module evaluates only
typed Quantity bindings.  An evaluated equation is not evidence and does not
produce a scientific verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, registry
from .ast import (
    BinaryExpression,
    BinaryOperator,
    Constant,
    Equation,
    Expression,
    FunctionExpression,
    FunctionName,
    PowerExpression,
    Symbol,
    UnaryExpression,
    UnaryOperator,
)
from .dimensions import DimensionVector
from .errors import EquationEvaluationError

EQUATION_EVALUATION_SCHEMA = schema_string("equation_evaluation")


def _power(value: Quantity, exponent: Fraction) -> Quantity:
    try:
        backend_value = registry().Quantity(value.magnitude, value.units)
        powered = backend_value ** float(exponent)
        magnitude = float(powered.magnitude)
        if not math.isfinite(magnitude):
            raise ValueError("non-finite result")
        return Quantity(magnitude, str(powered.units))
    except Exception as exc:
        raise EquationEvaluationError(
            "power_evaluation_failed",
            f"cannot raise {value.units!r} quantity to {exponent}: {exc}",
        ) from exc


def _dimensionless_magnitude(value: Quantity, function: FunctionName) -> float:
    if not DimensionVector.from_unit(value.units).is_dimensionless:
        raise EquationEvaluationError(
            "dimensionless_required",
            f"{function.value} requires a dimensionless argument, got {value.units!r}",
        )
    return value.magnitude_in("dimensionless")


def evaluate_expression(
    expression: Expression,
    bindings: Mapping[str, Quantity],
) -> Quantity:
    if isinstance(expression, Symbol):
        value = bindings.get(expression.name)
        if value is None:
            raise EquationEvaluationError(
                "missing_symbol",
                f"no value was supplied for equation symbol {expression.name!r}",
            )
        if not isinstance(value, Quantity):
            raise EquationEvaluationError(
                "untyped_binding",
                f"equation symbol {expression.name!r} requires Quantity, "
                f"got {type(value).__name__}",
            )
        return value

    if isinstance(expression, Constant):
        return expression.value

    if isinstance(expression, UnaryExpression):
        value = evaluate_expression(expression.operand, bindings)
        if expression.operator is UnaryOperator.NEGATE:
            return Quantity(-value.magnitude, value.units)
        if expression.operator is UnaryOperator.ABSOLUTE:
            return Quantity(abs(value.magnitude), value.units)
        raise AssertionError("closed UnaryOperator exhausted")

    if isinstance(expression, BinaryExpression):
        left = evaluate_expression(expression.left, bindings)
        right = evaluate_expression(expression.right, bindings)
        try:
            if expression.operator is BinaryOperator.ADD:
                return left + right
            if expression.operator is BinaryOperator.SUBTRACT:
                return left - right
            if expression.operator is BinaryOperator.MULTIPLY:
                return left * right
            if expression.operator is BinaryOperator.DIVIDE:
                if right.magnitude == 0:
                    raise EquationEvaluationError(
                        "division_by_zero", "equation division by zero"
                    )
                return left / right
        except EquationEvaluationError:
            raise
        except UnitCompatibilityError as exc:
            raise EquationEvaluationError("unit_error", str(exc)) from exc
        raise AssertionError("closed BinaryOperator exhausted")

    if isinstance(expression, PowerExpression):
        return _power(evaluate_expression(expression.base, bindings), expression.exponent)

    if isinstance(expression, FunctionExpression):
        value = evaluate_expression(expression.argument, bindings)
        if expression.function is FunctionName.SQRT:
            if value.magnitude < 0:
                raise EquationEvaluationError(
                    "function_domain_error", "sqrt requires a non-negative magnitude"
                )
            return _power(value, Fraction(1, 2))

        magnitude = _dimensionless_magnitude(value, expression.function)
        functions = {
            FunctionName.EXP: math.exp,
            FunctionName.LOG: math.log,
            FunctionName.SIN: math.sin,
            FunctionName.COS: math.cos,
            FunctionName.TAN: math.tan,
        }
        try:
            result = float(functions[expression.function](magnitude))
        except (ValueError, OverflowError) as exc:
            raise EquationEvaluationError(
                "function_domain_error",
                f"{expression.function.value} failed for {magnitude!r}: {exc}",
            ) from exc
        if not math.isfinite(result):
            raise EquationEvaluationError(
                "non_finite_result",
                f"{expression.function.value} produced a non-finite result",
            )
        return Quantity.dimensionless(result)

    raise TypeError(f"unsupported equation expression {type(expression).__name__}")


@dataclass(frozen=True)
class EquationEvaluation:
    left: Quantity
    right: Quantity
    residual: Quantity

    def __post_init__(self) -> None:
        for label, value in (
            ("left", self.left),
            ("right", self.right),
            ("residual", self.residual),
        ):
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"equation evaluation {label} must be a Quantity"
                )
        try:
            self.left.require_compatible(self.right, context="equation evaluation sides")
            expected = self.left - self.right
            expected.require_compatible(
                self.residual,
                context="equation evaluation residual",
            )
            recorded = self.residual.magnitude_in(expected.units)
        except UnitCompatibilityError as exc:
            raise InvalidScientificProblem(
                f"equation evaluation carries incompatible quantities: {exc}"
            ) from exc
        if not math.isclose(
            recorded,
            expected.magnitude,
            rel_tol=1e-12,
            abs_tol=1e-15,
        ):
            raise InvalidScientificProblem(
                "equation evaluation residual does not equal left - right"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EQUATION_EVALUATION_SCHEMA,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "residual": self.residual.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EquationEvaluation":
        require_schema(payload, EQUATION_EVALUATION_SCHEMA)
        return cls(
            left=Quantity.from_dict(payload["left"]),
            right=Quantity.from_dict(payload["right"]),
            residual=Quantity.from_dict(payload["residual"]),
        )


def evaluate_equation(
    equation: Equation,
    bindings: Mapping[str, Quantity],
) -> EquationEvaluation:
    left = evaluate_expression(equation.left, bindings)
    right = evaluate_expression(equation.right, bindings)
    try:
        left.require_compatible(right, context="equation residual")
        residual = left - right
    except UnitCompatibilityError as exc:
        raise EquationEvaluationError("equation_side_mismatch", str(exc)) from exc
    return EquationEvaluation(left=left, right=right, residual=residual)
