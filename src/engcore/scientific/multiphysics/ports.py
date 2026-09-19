"""Typed coupling ports for domain-neutral multiphysics composition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..fields.definition import FieldDefinition
from ..serialization import require_schema, schema_string
from ..units.quantity import dimensionality, normalize_unit

PORT_SCHEMA = schema_string("multiphysics_port")
PORT_REF_SCHEMA = schema_string("multiphysics_port_ref")


class PortDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class PortKind(str, Enum):
    SCALAR = "scalar"
    FIELD = "field"


class FieldAlgebra(str, Enum):
    """How multi-component field values transform between coordinate frames."""

    SCALAR = "scalar"
    VECTOR = "vector"
    TENSOR_2 = "tensor_2"
    CUSTOM = "custom"


@dataclass(frozen=True, order=True)
class PortRef:
    participant_id: str
    port_id: str

    def __post_init__(self) -> None:
        for name in ("participant_id", "port_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise InvalidScientificProblem(f"{name} must be non-empty")
            object.__setattr__(self, name, value)

    @property
    def key(self) -> str:
        return f"{self.participant_id}.{self.port_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PORT_REF_SCHEMA,
            "participant_id": self.participant_id,
            "port_id": self.port_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortRef":
        require_schema(payload, PORT_REF_SCHEMA)
        return cls(payload["participant_id"], payload["port_id"])


@dataclass(frozen=True)
class PortDefinition:
    """One scientific input/output boundary of an executable participant."""

    port_id: str
    direction: PortDirection
    kind: PortKind
    quantity: str
    unit: str
    field: FieldDefinition | None = None
    algebra: FieldAlgebra = FieldAlgebra.SCALAR
    coordinate_frame: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        port_id = str(self.port_id).strip()
        quantity = str(self.quantity).strip()
        if not port_id or not quantity:
            raise InvalidScientificProblem("a multiphysics port requires port_id and quantity")
        object.__setattr__(self, "port_id", port_id)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "direction", PortDirection(self.direction))
        object.__setattr__(self, "kind", PortKind(self.kind))
        object.__setattr__(self, "algebra", FieldAlgebra(self.algebra))
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        object.__setattr__(self, "coordinate_frame", str(self.coordinate_frame).strip())
        object.__setattr__(self, "description", str(self.description).strip())

        if self.kind is PortKind.SCALAR:
            if self.field is not None:
                raise InvalidScientificProblem(
                    f"scalar port {port_id!r} cannot carry a FieldDefinition"
                )
            if self.algebra is not FieldAlgebra.SCALAR:
                raise InvalidScientificProblem(
                    f"scalar port {port_id!r} must use scalar algebra"
                )
            if self.coordinate_frame:
                raise InvalidScientificProblem(
                    f"scalar port {port_id!r} cannot declare coordinate_frame; "
                    f"frame transforms apply to vector/tensor fields"
                )
            return

        if not isinstance(self.field, FieldDefinition):
            raise InvalidScientificProblem(
                f"field port {port_id!r} requires a FieldDefinition"
            )
        if dimensionality(self.field.unit) != dimensionality(self.unit):
            raise InvalidScientificProblem(
                f"field port {port_id!r} declares {self.unit!r} while its "
                f"field is {self.field.unit!r}"
            )

        components = self.field.components
        if self.algebra is FieldAlgebra.SCALAR and components != 1:
            raise InvalidScientificProblem(
                f"scalar field port {port_id!r} must have one component"
            )
        if self.algebra is FieldAlgebra.VECTOR and components not in (2, 3):
            raise InvalidScientificProblem(
                f"vector field port {port_id!r} must have 2 or 3 components"
            )
        if self.algebra is FieldAlgebra.TENSOR_2:
            dimension = math.isqrt(components)
            if dimension not in (2, 3) or dimension * dimension != components:
                raise InvalidScientificProblem(
                    f"rank-2 tensor field port {port_id!r} must store a full "
                    f"2x2 or 3x3 tensor (4 or 9 components), got {components}"
                )
        if (
            self.algebra in (FieldAlgebra.SCALAR, FieldAlgebra.CUSTOM)
            and self.coordinate_frame
        ):
            raise InvalidScientificProblem(
                f"{self.algebra.value} field port {port_id!r} cannot declare a "
                f"coordinate frame transform semantics"
            )

    @property
    def dimension(self) -> str:
        return dimensionality(self.unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PORT_SCHEMA,
            "port_id": self.port_id,
            "direction": self.direction.value,
            "kind": self.kind.value,
            "quantity": self.quantity,
            "unit": self.unit,
            "field": None if self.field is None else self.field.to_dict(),
            "algebra": self.algebra.value,
            "coordinate_frame": self.coordinate_frame,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortDefinition":
        require_schema(payload, PORT_SCHEMA)
        raw_field = payload.get("field")
        return cls(
            port_id=payload["port_id"],
            direction=PortDirection(payload["direction"]),
            kind=PortKind(payload["kind"]),
            quantity=payload["quantity"],
            unit=payload["unit"],
            field=None if raw_field is None else FieldDefinition.from_dict(raw_field),
            algebra=FieldAlgebra(payload.get("algebra", "scalar")),
            coordinate_frame=payload.get("coordinate_frame", ""),
            description=payload.get("description", ""),
        )
