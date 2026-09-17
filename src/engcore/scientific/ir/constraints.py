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

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..serialization import require_bool, require_schema, schema_string
from ..units.quantity import Quantity, base_unit, is_ratio_scale, require_spread_unit
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

    def __post_init__(self) -> None:
        """R-41: the verdict and the margin are one measurement, so they cannot disagree.

        This record had no constructor rule at all, and it is the single field a selection reads:
        `satisfied=True` beside a margin of -2.5 A was accepted, survived a round trip, and won the ranking.
        `ConstraintDefinition.check` computes the two together and for every operator the sign of the margin
        IS the verdict -- inside the bound is positive, outside is negative -- so a record where they
        disagree was not produced by it.

        Zero is accepted for either verdict, deliberately: at exactly the limit a non-strict operator is
        satisfied and a strict one is not, and a check does not carry its operator, so zero is the one value
        the two answers share.
        """
        name = str(self.constraint).strip()
        if not name:
            raise InvalidScientificProblem("a constraint check names the constraint it tested")
        object.__setattr__(self, "constraint", name)
        if not isinstance(self.satisfied, bool):
            raise InvalidScientificProblem(
                f"constraint check {name!r} reports satisfied={self.satisfied!r}, which is a "
                f"{type(self.satisfied).__name__}, not a verdict. A truthy value is not a statement that a "
                f"constraint held"
            )
        for label, quantity in (("margin", self.margin), ("value", self.value)):
            if not isinstance(quantity, Quantity):
                raise InvalidScientificProblem(
                    f"constraint check {name!r} carries {label}={quantity!r}, which is not a Quantity"
                )
        margin = float(self.margin.magnitude)
        if self.satisfied and margin < 0.0:
            raise InvalidScientificProblem(
                f"constraint check {name!r} reports the constraint satisfied and a margin of {self.margin}. "
                f"A negative margin is the measurement of being outside the bound: the verdict and the "
                f"number it comes from are one result and cannot disagree"
            )
        if not self.satisfied and margin > 0.0:
            raise InvalidScientificProblem(
                f"constraint check {name!r} reports the constraint violated and a margin of {self.margin}. "
                f"A positive margin is the measurement of being inside the bound"
            )

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
            # A VERDICT on the wire, not a declaration: "false" coerced to
            # True turns a violated constraint into a satisfied one, which is
            # the single most consequential inversion in this file.
            satisfied=require_bool(
                payload, "satisfied", False,
                error=InvalidScientificProblem,
                context=f"constraint check {payload.get('constraint')!r}",
            ),
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
            # A TOLERANCE IS A DIFFERENCE (I-22, R-48).
            #
            # It was converted with `.to(self.bound.units)`, the ABSOLUTE
            # conversion, and the sign was then checked on that number. A
            # '2 degC' tolerance on a 358.15 kelvin bound became 275.15 kelvin,
            # so a 600 kelvin reading SATISFIED a 358.15 kelvin limit and the
            # check reported a margin of 33.3 kelvin. Written the other way
            # round, a perfectly good 2 kelvin tolerance on an 85 degC bound
            # converted to -271.15 and was refused for being NEGATIVE.
            #
            # `require_spread_unit` is the rule the domains already applied to
            # a coupling tolerance and an excursion span; on a ratio scale a
            # magnitude's sign does not depend on the unit, so the check
            # belongs on the magnitude AS DECLARED.
            try:
                require_spread_unit(
                    self.tolerance.units, context=f"constraint {name!r} tolerance"
                )
            except UnitCompatibilityError as exc:
                raise InvalidScientificProblem(str(exc)) from exc
            if self.tolerance.magnitude < 0.0:
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
        # Read as a DIFFERENCE, which is what lets the delta spelling work at
        # all: `magnitude_in` has no conversion from delta_degC to degC and
        # raises. The declared unit is a ratio scale, so for every constraint
        # in this repository this is the identity. (I-22, R-48.)
        tol = (
            self.tolerance.magnitude_as_spread_in(self.bound.units)
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

        # A MARGIN IS A DIFFERENCE, AND ITS UNIT HAS TO BE ABLE TO SAY SO.
        #
        # Labelled with the bound's unit, a twelve-degree margin under an
        # 85 degC limit was `12.0 degree_Celsius`, and every consumer that
        # converted it read 285.15 kelvin. The bound's unit is kept when it is
        # a ratio scale -- which it is for every constraint this repository
        # declares, so no serialized check moves a byte -- and the dimension's
        # base unit is used when it is not. The base unit rather than a
        # synthesized `delta_` name, because the base unit is what the registry
        # already gives and inventing a unit NAME from a string is the kind of
        # guess this round is against. (I-22, R-48.)
        margin_unit = (
            self.bound.units
            if is_ratio_scale(self.bound.units)
            else base_unit(self.bound.units)
        )
        return ConstraintCheck(
            constraint=self.name,
            satisfied=bool(satisfied),
            margin=Quantity(
                Quantity(margin, self.bound.units).magnitude_as_spread_in(margin_unit),
                margin_unit,
            ),
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
