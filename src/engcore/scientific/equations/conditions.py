"""Typed initial and boundary conditions for algebraic/differential laws."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from .ast import Equation
from .dimensions import require_equation_dimensions
from .evaluation import EquationEvaluation, evaluate_equation

CONDITION_BINDING_SCHEMA = schema_string("equation_condition_binding")
EQUATION_CONDITION_SCHEMA = schema_string("scientific_equation_condition")


class ConditionKind(str, Enum):
    INITIAL = "initial"
    BOUNDARY = "boundary"


@dataclass(frozen=True)
class ConditionBinding:
    symbol: str
    value: Quantity

    def __post_init__(self) -> None:
        symbol=str(self.symbol).strip()
        if not symbol or not isinstance(self.value, Quantity):
            raise InvalidScientificProblem("condition binding requires symbol and Quantity")
        object.__setattr__(self, "symbol", symbol)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CONDITION_BINDING_SCHEMA, "symbol": self.symbol, "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConditionBinding":
        require_schema(payload, CONDITION_BINDING_SCHEMA)
        return cls(payload["symbol"], Quantity.from_dict(payload["value"]))


@dataclass(frozen=True)
class EquationCondition:
    condition_id: str
    kind: ConditionKind
    equation: Equation
    at: tuple[ConditionBinding, ...]
    region: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        cid=str(self.condition_id).strip()
        if not cid or not isinstance(self.equation, Equation):
            raise InvalidScientificProblem("equation condition requires id and typed Equation")
        object.__setattr__(self, "condition_id", cid)
        object.__setattr__(self, "kind", ConditionKind(self.kind))
        object.__setattr__(self, "at", tuple(self.at))
        if not self.at or any(not isinstance(x, ConditionBinding) for x in self.at):
            raise InvalidScientificProblem("initial/boundary condition requires typed location bindings")
        names=[x.symbol for x in self.at]
        if len(names)!=len(set(names)):
            raise InvalidScientificProblem("condition location binds one symbol more than once")

    def require_contract(self, symbol_units: Mapping[str, str]) -> None:
        unknown=sorted((set(self.equation.symbols)|{x.symbol for x in self.at})-set(symbol_units))
        if unknown:
            raise InvalidScientificProblem(f"condition {self.condition_id!r} references undeclared symbols {unknown}")
        for item in self.at:
            require_same_dimension(item.value, symbol_units[item.symbol],
                                   context=f"condition {self.condition_id!r} location {item.symbol!r}")
        require_equation_dimensions(self.equation, symbol_units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EQUATION_CONDITION_SCHEMA, "condition_id": self.condition_id,
            "kind": self.kind.value, "equation": self.equation.to_dict(),
            "at": [x.to_dict() for x in self.at], "region": self.region,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EquationCondition":
        require_schema(payload, EQUATION_CONDITION_SCHEMA)
        return cls(
            payload["condition_id"], ConditionKind(payload["kind"]),
            Equation.from_dict(payload["equation"]),
            tuple(ConditionBinding.from_dict(x) for x in payload.get("at", ())),
            payload.get("region", ""), payload.get("description", ""),
        )


def evaluate_condition(
    condition: EquationCondition,
    bindings: Mapping[str, Quantity],
    *,
    derivative_bindings: Mapping[str, Quantity] | None = None,
) -> EquationEvaluation:
    merged=dict(bindings)
    for fixed in condition.at:
        existing=merged.get(fixed.symbol)
        if existing is not None:
            if not isinstance(existing, Quantity):
                raise InvalidScientificProblem("condition base binding must be Quantity")
            try:
                actual=existing.magnitude_in(fixed.value.units)
            except UnitCompatibilityError as exc:
                raise InvalidScientificProblem(str(exc)) from exc
            if not math.isclose(actual, fixed.value.magnitude, rel_tol=1e-12, abs_tol=1e-15):
                raise InvalidScientificProblem(
                    f"binding for {fixed.symbol!r} conflicts with condition location"
                )
        merged[fixed.symbol]=fixed.value
    return evaluate_equation(
        condition.equation, merged, derivative_bindings=derivative_bindings
    )
