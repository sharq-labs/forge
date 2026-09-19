"""Residual-form representation and evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, require_spread_unit
from .ast import BinaryExpression, BinaryOperator, Equation, Expression
from .evaluation import evaluate_equation

RESIDUAL_DEFINITION_SCHEMA = schema_string("equation_residual_definition")


def residual_expression(equation: Equation) -> Expression:
    if not isinstance(equation, Equation):
        raise TypeError("residual_expression requires Equation")
    return BinaryExpression(BinaryOperator.SUBTRACT, equation.left, equation.right)


@dataclass(frozen=True)
class ResidualDefinition:
    residual_id: str
    equation: Equation
    scale: Quantity | None = None

    def __post_init__(self) -> None:
        rid=str(self.residual_id).strip()
        if not rid or not isinstance(self.equation, Equation):
            raise InvalidScientificProblem("residual definition requires id and Equation")
        object.__setattr__(self, "residual_id", rid)
        if self.scale is not None:
            if not isinstance(self.scale, Quantity):
                raise InvalidScientificProblem("residual scale must be Quantity")
            require_spread_unit(self.scale.units, context=f"residual {rid!r} scale")
            if self.scale.magnitude <= 0:
                raise InvalidScientificProblem("residual scale must be positive")

    def evaluate(self, bindings: Mapping[str, Quantity], *,
                 derivative_bindings: Mapping[str, Quantity] | None = None) -> Quantity:
        evaluation=evaluate_equation(
            self.equation, bindings, derivative_bindings=derivative_bindings
        )
        if self.scale is None:
            return evaluation.residual
        try:
            magnitude=evaluation.residual.magnitude_as_spread_in(self.scale.units)/self.scale.magnitude
        except (UnitCompatibilityError, ValueError) as exc:
            raise InvalidScientificProblem(
                f"residual scale is incompatible with equation residual: {exc}"
            ) from exc
        return Quantity.dimensionless(magnitude)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RESIDUAL_DEFINITION_SCHEMA, "residual_id": self.residual_id,
            "equation": self.equation.to_dict(),
            "scale": None if self.scale is None else self.scale.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResidualDefinition":
        require_schema(payload, RESIDUAL_DEFINITION_SCHEMA)
        scale=payload.get("scale")
        return cls(payload["residual_id"], Equation.from_dict(payload["equation"]),
                   Quantity.from_dict(scale) if scale is not None else None)
