"""Content-addressed unstructured mesh support for external CFD/FEM solvers.

Coordinates and connectivity are bulk data and therefore never live inline in
scientific records. The mesh record carries their content identities, exact
counts and cell topology; execution adapters resolve and validate the arrays
when they need them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..results.data_reference import ScientificDataReference
from ..serialization import require_schema, schema_string
from ..units.quantity import dimensionality

UNSTRUCTURED_MESH_SCHEMA = schema_string("unstructured_mesh")


class CellType(str, Enum):
    TRIANGLE = "triangle"
    QUADRILATERAL = "quadrilateral"
    TETRAHEDRON = "tetrahedron"
    HEXAHEDRON = "hexahedron"

    @property
    def vertices(self) -> int:
        return {
            CellType.TRIANGLE: 3,
            CellType.QUADRILATERAL: 4,
            CellType.TETRAHEDRON: 4,
            CellType.HEXAHEDRON: 8,
        }[self]

    @property
    def spatial_dimension(self) -> int:
        return (
            2
            if self in {CellType.TRIANGLE, CellType.QUADRILATERAL}
            else 3
        )


@dataclass(frozen=True)
class UnstructuredMesh:
    """Unstructured support named by coordinate/connectivity content."""

    mesh_id: str
    cell_type: CellType
    node_count: int
    cell_count: int
    coordinates: ScientificDataReference
    connectivity: ScientificDataReference
    description: str = ""

    def __post_init__(self) -> None:
        mesh_id = str(self.mesh_id).strip()
        if not mesh_id:
            raise InvalidScientificProblem(
                "unstructured mesh requires mesh_id"
            )
        object.__setattr__(self, "mesh_id", mesh_id)
        object.__setattr__(self, "cell_type", CellType(self.cell_type))
        for label in ("node_count", "cell_count"):
            value = getattr(self, label)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise InvalidScientificProblem(
                    f"unstructured mesh {label} must be a positive int"
                )
        if not isinstance(self.coordinates, ScientificDataReference):
            raise InvalidScientificProblem(
                "unstructured mesh coordinates must be ScientificDataReference"
            )
        if not isinstance(self.connectivity, ScientificDataReference):
            raise InvalidScientificProblem(
                "unstructured mesh connectivity must be ScientificDataReference"
            )
        if dimensionality(self.coordinates.unit) != dimensionality("meter"):
            raise InvalidScientificProblem(
                "unstructured mesh coordinates must carry length units"
            )
        if self.coordinates.unit != "meter":
            raise InvalidScientificProblem(
                "unstructured mesh coordinate bytes must be canonical metres; "
                "normalize before storing so equivalent geometry has one identity"
            )
        if dimensionality(self.connectivity.unit) != "dimensionless":
            raise InvalidScientificProblem(
                "unstructured mesh connectivity must be dimensionless"
            )
        expected_coordinates = (
            self.node_count * self.spatial_dimension
        )
        if self.coordinates.count != expected_coordinates:
            raise InvalidScientificProblem(
                f"unstructured mesh has {self.node_count} nodes in "
                f"{self.spatial_dimension}D and needs "
                f"{expected_coordinates} coordinate values; reference names "
                f"{self.coordinates.count}"
            )
        expected_connectivity = (
            self.cell_count * self.vertices_per_cell
        )
        if self.connectivity.count != expected_connectivity:
            raise InvalidScientificProblem(
                f"unstructured mesh has {self.cell_count} "
                f"{self.cell_type.value} cells and needs "
                f"{expected_connectivity} connectivity values; reference names "
                f"{self.connectivity.count}"
            )
        object.__setattr__(
            self, "description", str(self.description).strip()
        )

    @property
    def topology(self) -> str:
        return "unstructured"

    @property
    def spatial_dimension(self) -> int:
        return self.cell_type.spatial_dimension

    @property
    def vertices_per_cell(self) -> int:
        return self.cell_type.vertices

    @property
    def node_shape(self) -> tuple[int]:
        return (self.node_count,)

    @property
    def cell_shape(self) -> tuple[int]:
        return (self.cell_count,)

    def fingerprint(self) -> str:
        payload = {
            "topology": self.topology,
            "cell_type": self.cell_type.value,
            "node_count": self.node_count,
            "cell_count": self.cell_count,
            "coordinates_digest": self.coordinates.digest,
            "connectivity_digest": self.connectivity.digest,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def same_support_as(self, other: Any) -> bool:
        return (
            isinstance(other, UnstructuredMesh)
            and self.fingerprint() == other.fingerprint()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNSTRUCTURED_MESH_SCHEMA,
            "mesh_id": self.mesh_id,
            "cell_type": self.cell_type.value,
            "node_count": self.node_count,
            "cell_count": self.cell_count,
            "coordinates": self.coordinates.to_dict(),
            "connectivity": self.connectivity.to_dict(),
            "description": self.description,
            "fingerprint": self.fingerprint(),
            "spatial_dimension": self.spatial_dimension,
            "vertices_per_cell": self.vertices_per_cell,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "UnstructuredMesh":
        require_schema(payload, UNSTRUCTURED_MESH_SCHEMA)
        made = cls(
            mesh_id=payload["mesh_id"],
            cell_type=CellType(payload["cell_type"]),
            node_count=payload["node_count"],
            cell_count=payload["cell_count"],
            coordinates=ScientificDataReference.from_dict(
                payload["coordinates"]
            ),
            connectivity=ScientificDataReference.from_dict(
                payload["connectivity"]
            ),
            description=payload.get("description", ""),
        )
        if (
            payload.get("fingerprint") is not None
            and payload["fingerprint"] != made.fingerprint()
        ):
            raise InvalidScientificProblem(
                "unstructured mesh fingerprint disagrees with referenced "
                "geometry/topology content"
            )
        if (
            payload.get("spatial_dimension") is not None
            and payload["spatial_dimension"] != made.spatial_dimension
        ):
            raise InvalidScientificProblem(
                "serialized unstructured mesh spatial_dimension disagrees "
                "with its cell type"
            )
        if (
            payload.get("vertices_per_cell") is not None
            and payload["vertices_per_cell"] != made.vertices_per_cell
        ):
            raise InvalidScientificProblem(
                "serialized unstructured mesh vertices_per_cell disagrees "
                "with its cell type"
            )
        return made
