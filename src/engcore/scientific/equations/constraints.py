"""Typed symbolic relational constraints over Equation IR expressions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, base_unit, is_ratio_scale, require_spread_unit
from .ast import Expression, decode_expression, referenced_symbols, _require_expression
from .dimensions import DimensionVector, infer_dimension
from .errors import EquationDimensionError, EquationEvaluationError
from .evaluation import evaluate_expression

EXPRESSION_CONSTRAINT_SCHEMA = schema_string("equation_expression_constraint")
CONSTRAINT_EVALUATION_SCHEMA = schema_string("equation_constraint_evaluation")


class RelationOperator(str, Enum):
    LESS_EQUAL = "<="
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    GREATER_THAN = ">"
    EQUAL = "=="
    NOT_EQUAL = "!="


@dataclass(frozen=True)
class ExpressionConstraint:
    constraint_id: str
    left: Expression
    operator: RelationOperator
    right: Expression
    tolerance: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        cid = str(self.constraint_id).strip()
        if not cid:
            raise InvalidScientificProblem("expression constraint requires a non-empty id")
        object.__setattr__(self, "constraint_id", cid)
        _require_expression(self.left, context=f"constraint {cid!r} left")
        _require_expression(self.right, context=f"constraint {cid!r} right")
        object.__setattr__(self, "operator", RelationOperator(self.operator))
        if self.tolerance is not None:
            if not isinstance(self.tolerance, Quantity):
                raise InvalidScientificProblem("constraint tolerance must be a Quantity")
            try:
                require_spread_unit(self.tolerance.units, context=f"constraint {cid!r} tolerance")
            except UnitCompatibilityError as exc:
                raise InvalidScientificProblem(str(exc)) from exc
            if self.tolerance.magnitude < 0:
                raise InvalidScientificProblem("constraint tolerance must be non-negative")

    @property
    def symbols(self) -> frozenset[str]:
        return referenced_symbols(self.left) | referenced_symbols(self.right)

    def require_dimensions(self, symbol_units: Mapping[str, str]) -> DimensionVector:
        left = infer_dimension(self.left, symbol_units)
        right = infer_dimension(self.right, symbol_units)
        if left != right:
            raise EquationDimensionError(
                "constraint_dimension_mismatch",
                f"constraint {self.constraint_id!r} compares {left.render()} with {right.render()}",
            )
        if self.tolerance is not None:
            tolerance = DimensionVector.from_unit(self.tolerance.units)
            if tolerance != right:
                raise EquationDimensionError(
                    "constraint_tolerance_dimension_mismatch",
                    f"constraint {self.constraint_id!r} tolerance is {tolerance.render()}, expected {right.render()}",
                )
        return right

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPRESSION_CONSTRAINT_SCHEMA,
            "constraint_id": self.constraint_id,
            "left": self.left.to_dict(),
            "operator": self.operator.value,
            "right": self.right.to_dict(),
            "tolerance": None if self.tolerance is None else self.tolerance.to_dict(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExpressionConstraint":
        require_schema(payload, EXPRESSION_CONSTRAINT_SCHEMA)
        tolerance = payload.get("tolerance")
        return cls(
            payload["constraint_id"],
            decode_expression(payload["left"]),
            RelationOperator(payload["operator"]),
            decode_expression(payload["right"]),
            Quantity.from_dict(tolerance) if tolerance is not None else None,
            payload.get("description", ""),
        )


@dataclass(frozen=True)
class ConstraintEvaluation:
    constraint_id: str
    operator: RelationOperator
    left: Quantity
    right: Quantity
    tolerance: Quantity | None
    satisfied: bool
    margin: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.satisfied, bool):
            raise InvalidScientificProblem("constraint evaluation satisfied must be bool")
        object.__setattr__(self, "operator", RelationOperator(self.operator))
        for value in (self.left, self.right, self.margin):
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem("constraint evaluation quantities must be typed Quantity records")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONSTRAINT_EVALUATION_SCHEMA,
            "constraint_id": self.constraint_id,
            "operator": self.operator.value,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "tolerance": None if self.tolerance is None else self.tolerance.to_dict(),
            "satisfied": self.satisfied,
            "margin": self.margin.to_dict(),
        }


def evaluate_constraint(
    constraint: ExpressionConstraint,
    bindings: Mapping[str, Quantity],
    *,
    derivative_bindings: Mapping[str, Quantity] | None = None,
) -> ConstraintEvaluation:
    left = evaluate_expression(constraint.left, bindings, derivative_bindings=derivative_bindings)
    right = evaluate_expression(constraint.right, bindings, derivative_bindings=derivative_bindings)
    try:
        left.require_compatible(right, context=f"constraint {constraint.constraint_id!r}")
        measured = left.to(right.units)
    except UnitCompatibilityError as exc:
        raise EquationEvaluationError("constraint_dimension_mismatch", str(exc)) from exc
    tol = 0.0
    if constraint.tolerance is not None:
        try:
            tol = constraint.tolerance.magnitude_as_spread_in(right.units)
        except Exception as exc:
            raise EquationEvaluationError("constraint_tolerance_dimension_mismatch", str(exc)) from exc
    x, b = measured.magnitude, right.magnitude
    if constraint.operator is RelationOperator.LESS_EQUAL:
        boundary=b+tol; ok=x<=boundary; margin=boundary-x
    elif constraint.operator is RelationOperator.LESS_THAN:
        boundary=b-tol; ok=x<boundary; margin=boundary-x
    elif constraint.operator is RelationOperator.GREATER_EQUAL:
        boundary=b-tol; ok=x>=boundary; margin=x-boundary
    elif constraint.operator is RelationOperator.GREATER_THAN:
        boundary=b+tol; ok=x>boundary; margin=x-boundary
    elif constraint.operator is RelationOperator.EQUAL:
        margin=tol-abs(x-b); ok=abs(x-b)<=tol
    else:
        margin=abs(x-b)-tol; ok=abs(x-b)>tol
    margin_unit = right.units if is_ratio_scale(right.units) else base_unit(right.units)
    margin_q = Quantity(Quantity(margin, right.units).magnitude_as_spread_in(margin_unit), margin_unit)
    return ConstraintEvaluation(
        constraint.constraint_id, constraint.operator, measured, right,
        constraint.tolerance, bool(ok), margin_q,
    )
