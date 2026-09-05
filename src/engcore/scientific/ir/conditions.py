"""Initial and boundary conditions as first-class objects.

No PDE machinery is implemented here. The point is that conditions stop being
anonymous dictionaries: a future field solver can rely on a stable, typed,
unit-carrying representation, and V0 problems can already declare them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity

INITIAL_CONDITION_SCHEMA = schema_string("initial_condition")
BOUNDARY_CONDITION_SCHEMA = schema_string("boundary_condition")


class BoundaryKind(str, Enum):
    """Generic boundary-condition families.

    ``OTHER`` exists so a domain can carry a kind we have not modelled without
    forcing a core change; the domain records specifics in ``coefficients``.
    """

    DIRICHLET = "dirichlet"
    NEUMANN = "neumann"
    ROBIN = "robin"
    PERIODIC = "periodic"
    OTHER = "other"


@dataclass(frozen=True)
class InitialCondition:
    """State of a variable at the start of a time-dependent problem."""

    variable: str
    value: Quantity
    time: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        variable = str(self.variable).strip()
        if not variable:
            raise InvalidScientificProblem(
                "initial condition must reference a variable name"
            )
        object.__setattr__(self, "variable", variable)
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                f"initial condition for {variable!r} requires a Quantity value"
            )
        if self.time is not None and not isinstance(self.time, Quantity):
            raise InvalidScientificProblem(
                f"initial condition for {variable!r}: time must be a Quantity"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INITIAL_CONDITION_SCHEMA,
            "variable": self.variable,
            "value": self.value.to_dict(),
            "time": self.time.to_dict() if self.time else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InitialCondition":
        require_schema(payload, INITIAL_CONDITION_SCHEMA)
        time = payload.get("time")
        return cls(
            variable=payload["variable"],
            value=Quantity.from_dict(payload["value"]),
            time=Quantity.from_dict(time) if time else None,
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class BoundaryCondition:
    """Condition imposed on a region of a problem domain.

    ``region`` is an opaque label owned by the domain (a mesh tag, a port
    name, a surface id). The core does not interpret it.
    """

    name: str
    variable: str
    kind: BoundaryKind
    region: str
    value: Quantity | None = None
    coefficients: Mapping[str, Quantity] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        for label, text in (("name", self.name), ("variable", self.variable),
                            ("region", self.region)):
            if not str(text).strip():
                raise InvalidScientificProblem(
                    f"boundary condition requires a non-empty {label}"
                )
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "variable", str(self.variable).strip())
        object.__setattr__(self, "region", str(self.region).strip())
        object.__setattr__(self, "kind", BoundaryKind(self.kind))

        coefficients = dict(self.coefficients)
        for key, coefficient in coefficients.items():
            if not isinstance(coefficient, Quantity):
                raise InvalidScientificProblem(
                    f"boundary condition {self.name!r}: coefficient {key!r} "
                    f"must be a Quantity"
                )
        object.__setattr__(self, "coefficients", coefficients)

        if self.value is not None and not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                f"boundary condition {self.name!r}: value must be a Quantity"
            )
        # Periodic conditions carry no value; Dirichlet/Neumann require one.
        if self.kind in (BoundaryKind.DIRICHLET, BoundaryKind.NEUMANN):
            if self.value is None:
                raise InvalidScientificProblem(
                    f"boundary condition {self.name!r}: kind "
                    f"{self.kind.value!r} requires a value"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BOUNDARY_CONDITION_SCHEMA,
            "name": self.name,
            "variable": self.variable,
            "kind": self.kind.value,
            "region": self.region,
            "value": self.value.to_dict() if self.value else None,
            "coefficients": {
                k: self.coefficients[k].to_dict()
                for k in sorted(self.coefficients)
            },
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BoundaryCondition":
        require_schema(payload, BOUNDARY_CONDITION_SCHEMA)
        value = payload.get("value")
        return cls(
            name=payload["name"],
            variable=payload["variable"],
            kind=BoundaryKind(payload["kind"]),
            region=payload["region"],
            value=Quantity.from_dict(value) if value else None,
            coefficients={
                k: Quantity.from_dict(v)
                for k, v in (payload.get("coefficients") or {}).items()
            },
            description=payload.get("description", ""),
        )
