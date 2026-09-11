"""What a field *is*, separately from what its values are.

``ScientificVariable`` declares a name, a unit and a role. That is a complete
statement about a scalar and an incomplete one about a field: it says nothing
about where the values sit, how many there are, or which support they belong
to. Those three are what make an array of numbers a field, and a record that
leaves them out forces every consumer to infer them from a length.

A :class:`FieldDefinition` is the declaration half. It carries no values, is
O(1), and is the thing a problem, a boundary condition, a result and a transfer
contract all point at.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import normalize_unit
from .mesh import StructuredMesh

FIELD_DEFINITION_SCHEMA = schema_string("field_definition")


class FieldLocation(str, Enum):
    """Where on the support a value sits.

    The distinction is not bookkeeping: a node field of a 16 x 16 support has
    256 values and a cell field has 225, so a record that does not state its
    location cannot be checked against its own support at all. ``FACE`` is
    deliberately absent — this vertical slice has no use for one, and an
    unused member is a promise nothing keeps.
    """

    NODE = "node"
    CELL = "cell"


@dataclass(frozen=True)
class FieldDefinition:
    """One field: what it means, in what unit, where, on which support.

    ``components`` is 1 for a scalar field. It exists because the difference
    between a scalar field and a vector field is a property of the field and
    not of the array that happens to arrive, and because a consumer expecting
    one and handed the other should be refused by a record rather than by a
    reshape.
    """

    field_id: str
    unit: str
    mesh_id: str
    location: FieldLocation = FieldLocation.NODE
    components: int = 1
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("field_id", "mesh_id"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise InvalidScientificProblem(
                    f"a field definition requires a non-empty {label}"
                )
            object.__setattr__(self, label, text)
        # Through the units contract, so `K` and `kelvin` are one declaration
        # and a field cannot be compared with itself under two spellings.
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        object.__setattr__(self, "location", FieldLocation(self.location))
        components = self.components
        if isinstance(components, bool) or not isinstance(components, int):
            raise InvalidScientificProblem(
                f"field {self.field_id!r}: components must be an int, got "
                f"{type(components).__name__}"
            )
        if components < 1:
            raise InvalidScientificProblem(
                f"field {self.field_id!r}: components must be >= 1, got {components}"
            )

    # ---- what it demands of a support --------------------------------------
    def require_support(self, mesh: StructuredMesh) -> None:
        if not isinstance(mesh, StructuredMesh):
            raise InvalidScientificProblem(
                f"field {self.field_id!r} is defined on a StructuredMesh, got "
                f"{type(mesh).__name__}"
            )
        if mesh.mesh_id != self.mesh_id:
            raise InvalidScientificProblem(
                f"field {self.field_id!r} is defined on mesh {self.mesh_id!r} "
                f"and was given {mesh.mesh_id!r}; a field of one support is "
                f"not a field of another"
            )

    def expected_shape(self, mesh: StructuredMesh) -> tuple[int, ...]:
        """The shape an array of this field on ``mesh`` must have."""
        self.require_support(mesh)
        base = mesh.node_shape if self.location is FieldLocation.NODE else mesh.cell_shape
        return base if self.components == 1 else (*base, self.components)

    def expected_count(self, mesh: StructuredMesh) -> int:
        """How many values that is. A count is derived, never declared."""
        self.require_support(mesh)
        sites = (
            mesh.node_count if self.location is FieldLocation.NODE else mesh.cell_count
        )
        return sites * self.components

    # ---- serialization ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_DEFINITION_SCHEMA,
            "field_id": self.field_id,
            "unit": self.unit,
            "mesh_id": self.mesh_id,
            "location": self.location.value,
            "components": self.components,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldDefinition":
        require_schema(payload, FIELD_DEFINITION_SCHEMA)
        return cls(
            field_id=payload["field_id"],
            unit=payload["unit"],
            mesh_id=payload["mesh_id"],
            location=FieldLocation(payload.get("location", FieldLocation.NODE)),
            components=payload.get("components", 1),
            description=payload.get("description", ""),
        )
