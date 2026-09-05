"""Objective representation.

Representation only: no optimization algorithm lives here, and the Scientific
Core never imports an optimizer. An objective names a metric that a result is
expected to carry, plus the direction of preference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.validation import require_unit

OBJECTIVE_SCHEMA = schema_string("objective_definition")


class ObjectiveDirection(str, Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@dataclass(frozen=True)
class ObjectiveDefinition:
    """``minimize mass``, ``maximize efficiency`` — declared, not computed."""

    name: str
    metric: str
    direction: ObjectiveDirection
    unit: str = "dimensionless"
    weight: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        metric = str(self.metric).strip()
        if not name:
            raise InvalidScientificProblem("objective name must be non-empty")
        if not metric:
            raise InvalidScientificProblem(
                f"objective {name!r} must reference a metric name"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "direction", ObjectiveDirection(self.direction))
        object.__setattr__(
            self, "unit", require_unit(self.unit, context=f"objective {name!r}")
        )
        if self.weight is not None:
            weight = float(self.weight)
            if not math.isfinite(weight):
                raise InvalidScientificProblem(
                    f"objective {name!r}: weight must be finite, got {weight!r}"
                )
            if not weight > 0.0:
                raise InvalidScientificProblem(
                    f"objective {name!r}: weight must be positive when given"
                )
            object.__setattr__(self, "weight", weight)

    @property
    def sense(self) -> int:
        """+1 when larger is better, -1 when smaller is better."""
        return 1 if self.direction is ObjectiveDirection.MAXIMIZE else -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBJECTIVE_SCHEMA,
            "name": self.name,
            "metric": self.metric,
            "direction": self.direction.value,
            "unit": self.unit,
            "weight": self.weight,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObjectiveDefinition":
        require_schema(payload, OBJECTIVE_SCHEMA)
        return cls(
            name=payload["name"],
            metric=payload["metric"],
            direction=ObjectiveDirection(payload["direction"]),
            unit=payload.get("unit", "dimensionless"),
            weight=payload.get("weight"),
            description=payload.get("description", ""),
        )
