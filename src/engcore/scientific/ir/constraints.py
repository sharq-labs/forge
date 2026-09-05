"""Constraint representation.

Constraints are *typed references*, never executable strings: a constraint
names a metric, an operator, and a bound with units. There is no ``eval``,
no ``exec``, and no dynamic expression compilation anywhere in the core.

Symbolic expressions (``stress <= allowable_stress(T)``) are deferred; V0
covers the ``metric OP bound`` form that real studies overwhelmingly use.

Operator and tolerance semantics
--------------------------------
For a measured value ``x``, bound ``b`` and tolerance ``τ >= 0``:

===============  ==========================
``<=``           ``x <= b + τ``
``<``            ``x <  b - τ``
``>=``           ``x >= b - τ``
``>``            ``x >  b + τ``
``==``           ``|x - b| <= τ``
===============  ==========================

Tolerance therefore *relaxes* a non-strict bound and *tightens* a strict one;
at ``τ = 0`` every operator reduces to its exact mathematical meaning, so
``x < b`` correctly fails at ``x == b``.

Exact equality (``==`` with ``τ = 0``) is permitted, because a study may
legitimately demand it. For values produced by floating-point numerics a
non-zero tolerance is normally the scientifically appropriate choice.

``margin`` is expressed in the bound's units and is positive exactly when the
constraint is satisfied with room to spare, negative when violated, and zero
at the decision boundary (which for a strict operator means *not* satisfied).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension

CONSTRAINT_SCHEMA = schema_string("constraint_definition")
CONSTRAINT_CHECK_SCHEMA = schema_string("constraint_check")


class ConstraintOperator(str, Enum):
    LESS_EQUAL = "<="
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    GREATER_THAN = ">"
    EQUAL = "=="


@dataclass(frozen=True)
class ConstraintCheck:
    """Outcome of testing one constraint against one measured value."""

    constraint: str
    satisfied: bool
    margin: Quantity
    value: Quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONSTRAINT_CHECK_SCHEMA,
            "constraint": self.constraint,
            "satisfied": self.satisfied,
            "margin": self.margin.to_dict(),
            "value": self.value.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConstraintCheck":
        require_schema(payload, CONSTRAINT_CHECK_SCHEMA)
        return cls(
            constraint=payload["constraint"],
            satisfied=bool(payload["satisfied"]),
            margin=Quantity.from_dict(payload["margin"]),
            value=Quantity.from_dict(payload["value"]),
        )


@dataclass(frozen=True)
class ConstraintDefinition:
    """e.g. ``temperature <= 350 K``, ``voltage >= 4.8 V``."""

    name: str
    metric: str
    operator: ConstraintOperator
    bound: Quantity
    tolerance: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        metric = str(self.metric).strip()
        if not name:
            raise InvalidScientificProblem("constraint name must be non-empty")
        if not metric:
            raise InvalidScientificProblem(
                f"constraint {name!r} must reference a metric name"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "operator", ConstraintOperator(self.operator))
        if not isinstance(self.bound, Quantity):
            raise InvalidScientificProblem(
                f"constraint {name!r} bound must be a Quantity "
                f"(units are never implicit)"
            )
        if self.tolerance is not None:
            if not isinstance(self.tolerance, Quantity):
                raise InvalidScientificProblem(
                    f"constraint {name!r} tolerance must be a Quantity"
                )
            require_same_dimension(
                self.tolerance,
                self.bound,
                context=f"constraint {name!r} tolerance",
            )
            if self.tolerance.to(self.bound.units).magnitude < 0.0:
                raise InvalidScientificProblem(
                    f"constraint {name!r}: tolerance must be non-negative"
                )

    @property
    def unit(self) -> str:
        return self.bound.units

    def check(self, value: Quantity) -> ConstraintCheck:
        """Test a measured value. Raises on dimensional mismatch rather than
        silently comparing incompatible numbers."""
        require_same_dimension(
            value, self.bound, context=f"constraint {self.name!r} value"
        )
        measured = value.to(self.bound.units)
        tol = (
            self.tolerance.to(self.bound.units).magnitude
            if self.tolerance is not None
            else 0.0
        )
        x = measured.magnitude
        b = self.bound.magnitude

        # Strict and non-strict operators are genuinely different statements,
        # so tolerance acts in opposite directions: it *relaxes* a non-strict
        # bound (absorbing numerical noise at the boundary) and *tightens* a
        # strict one (demanding a real margin inside it). At tol == 0 each
        # reduces to its exact mathematical meaning.
        if self.operator is ConstraintOperator.LESS_EQUAL:
            limit = b + tol
            satisfied = x <= limit
            margin = limit - x
        elif self.operator is ConstraintOperator.LESS_THAN:
            limit = b - tol
            satisfied = x < limit
            margin = limit - x
        elif self.operator is ConstraintOperator.GREATER_EQUAL:
            limit = b - tol
            satisfied = x >= limit
            margin = x - limit
        elif self.operator is ConstraintOperator.GREATER_THAN:
            limit = b + tol
            satisfied = x > limit
            margin = x - limit
        else:  # EQUAL — exact equality is permitted when tol == 0
            margin = tol - abs(x - b)
            satisfied = abs(x - b) <= tol

        return ConstraintCheck(
            constraint=self.name,
            satisfied=bool(satisfied),
            margin=Quantity(margin, self.bound.units),
            value=measured,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONSTRAINT_SCHEMA,
            "name": self.name,
            "metric": self.metric,
            "operator": self.operator.value,
            "bound": self.bound.to_dict(),
            "tolerance": self.tolerance.to_dict() if self.tolerance else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConstraintDefinition":
        require_schema(payload, CONSTRAINT_SCHEMA)
        tolerance = payload.get("tolerance")
        return cls(
            name=payload["name"],
            metric=payload["metric"],
            operator=ConstraintOperator(payload["operator"]),
            bound=Quantity.from_dict(payload["bound"]),
            tolerance=Quantity.from_dict(tolerance) if tolerance else None,
            description=payload.get("description", ""),
        )
