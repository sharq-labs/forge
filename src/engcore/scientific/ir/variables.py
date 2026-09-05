"""Scientific variables and parameters.

A *variable* is something a study may vary or observe; a *parameter* is a
fixed configured value of the problem. Conflating the two is how design
spaces silently acquire constants — so they are distinct types here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, coerce_quantity
from ..units.validation import require_same_dimension, require_unit
from .values import (
    ScientificValue,
    ValueKind,
    as_context_value,
    decode_value,
    encode_value,
    require_scientific_value,
    value_kind,
)

VARIABLE_SCHEMA = schema_string("scientific_variable")
PARAMETER_SCHEMA = schema_string("scientific_parameter")


class VariableKind(str, Enum):
    """Value domain of a variable.

    V0 only *represents* the non-continuous kinds; mixed-variable search is
    deferred. Declaring them now keeps the contract stable when it arrives.
    """

    CONTINUOUS = "continuous"
    INTEGER = "integer"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"


class VariableRole(str, Enum):
    """What part the variable plays in a study."""

    DESIGN = "design"          # may be varied by a search
    STATE = "state"            # evolves during a solve
    OBSERVABLE = "observable"  # produced/measured, not chosen
    CONTROL = "control"        # externally imposed input


@dataclass(frozen=True)
class ScientificVariable:
    name: str
    unit: str
    kind: VariableKind = VariableKind.CONTINUOUS
    role: VariableRole = VariableRole.DESIGN
    lower: Quantity | None = None
    upper: Quantity | None = None
    categories: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise InvalidScientificProblem("variable name must be non-empty")
        object.__setattr__(self, "name", name)
        object.__setattr__(
            self, "unit", require_unit(self.unit, context=f"variable {name!r}")
        )
        object.__setattr__(self, "kind", VariableKind(self.kind))
        object.__setattr__(self, "role", VariableRole(self.role))
        object.__setattr__(self, "categories", tuple(self.categories))

        for label, bound in (("lower", self.lower), ("upper", self.upper)):
            if bound is None:
                continue
            if not isinstance(bound, Quantity):
                raise InvalidScientificProblem(
                    f"variable {name!r}: {label} bound must be a Quantity"
                )
            require_same_dimension(
                bound, self.unit, context=f"variable {name!r} {label} bound"
            )
            converted = bound.to(self.unit)
            if converted.magnitude != converted.magnitude or abs(
                converted.magnitude
            ) == float("inf"):
                raise InvalidScientificProblem(
                    f"variable {name!r}: {label} bound must be finite"
                )
            object.__setattr__(self, label, converted)

        if self.lower is not None and self.upper is not None:
            if self.upper.magnitude <= self.lower.magnitude:
                raise InvalidScientificProblem(
                    f"variable {name!r} requires upper > lower "
                    f"({self.lower} >= {self.upper})"
                )

        if self.kind is VariableKind.CATEGORICAL:
            if len(self.categories) < 2:
                raise InvalidScientificProblem(
                    f"categorical variable {name!r} requires >= 2 categories"
                )
            if len(set(self.categories)) != len(self.categories):
                raise InvalidScientificProblem(
                    f"categorical variable {name!r} has duplicate categories"
                )
        elif self.categories:
            raise InvalidScientificProblem(
                f"variable {name!r}: categories are only valid for "
                f"categorical variables"
            )

    @property
    def is_bounded(self) -> bool:
        return self.lower is not None and self.upper is not None

    def require_within_bounds(self, value: Quantity) -> Quantity:
        """Convert into the variable's unit and verify bound membership.

        Named for what it does: it *rejects* an out-of-bounds value rather
        than silently moving it. Explicit correction is the caller's job
        (see ``CandidateCodec.clip``).
        """
        converted = value.to(self.unit)
        if self.lower is not None and converted.magnitude < self.lower.magnitude:
            raise InvalidScientificProblem(
                f"variable {self.name!r}: {converted} below lower bound {self.lower}"
            )
        if self.upper is not None and converted.magnitude > self.upper.magnitude:
            raise InvalidScientificProblem(
                f"variable {self.name!r}: {converted} above upper bound {self.upper}"
            )
        return converted

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VARIABLE_SCHEMA,
            "name": self.name,
            "unit": self.unit,
            "kind": self.kind.value,
            "role": self.role.value,
            "lower": self.lower.to_dict() if self.lower else None,
            "upper": self.upper.to_dict() if self.upper else None,
            "categories": list(self.categories),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificVariable":
        require_schema(payload, VARIABLE_SCHEMA)
        lower = payload.get("lower")
        upper = payload.get("upper")
        return cls(
            name=payload["name"],
            unit=payload["unit"],
            kind=VariableKind(payload.get("kind", "continuous")),
            role=VariableRole(payload.get("role", "design")),
            lower=Quantity.from_dict(lower) if lower else None,
            upper=Quantity.from_dict(upper) if upper else None,
            categories=tuple(payload.get("categories", ())),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class ScientificParameter:
    """A fixed, configured value of a problem (not searched over).

    Accepts any member of the typed :data:`ScientificValue` union — a
    dimensional Quantity, or an integer count, flag or category. It does not
    accept raw Python objects: units are never implicit, and neither is type.
    """

    name: str
    value: ScientificValue
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise InvalidScientificProblem("parameter name must be non-empty")
        object.__setattr__(self, "name", name)
        require_scientific_value(self.value, context=f"parameter {name!r}")
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def kind(self) -> ValueKind:
        return value_kind(self.value)

    @property
    def is_quantity(self) -> bool:
        return self.kind is ValueKind.QUANTITY

    def context_value(self) -> Any:
        """Plain form for model validity predicates."""
        return as_context_value(self.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_SCHEMA,
            "name": self.name,
            "value": encode_value(self.value),
            "description": self.description,
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificParameter":
        require_schema(payload, PARAMETER_SCHEMA)
        return cls(
            name=payload["name"],
            value=decode_value(payload["value"]),
            description=payload.get("description", ""),
            metadata=dict(payload.get("metadata", {})),
        )


def build_quantity(value: Quantity | float | str, unit: str) -> Quantity:
    """Convenience re-export so IR builders need one import, not two."""
    return coerce_quantity(value, unit)
