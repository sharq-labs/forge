"""Runtime values for content-addressed unstructured mesh geometry."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..scientific.errors import InvalidScientificProblem
from ..scientific.fields import CellType, UnstructuredMesh
from ..scientific.units.quantity import Quantity, dimensionality
from .resolver import BulkDataResolver
from .store import BulkDataStore, store_values


@dataclass(frozen=True)
class UnstructuredMeshData:
    """Validated coordinates/connectivity before or after storage."""

    mesh_id: str
    cell_type: CellType
    coordinates: np.ndarray
    connectivity: np.ndarray
    coordinate_unit: str = "meter"
    description: str = ""

    def __post_init__(self) -> None:
        mesh_id = str(self.mesh_id).strip()
        if not mesh_id:
            raise InvalidScientificProblem(
                "unstructured mesh data requires mesh_id"
            )
        cell_type = CellType(self.cell_type)
        coordinate_unit = str(self.coordinate_unit).strip()
        if dimensionality(coordinate_unit) != dimensionality("meter"):
            raise InvalidScientificProblem(
                "unstructured mesh coordinate_unit must be a length unit"
            )

        coords = np.array(
            self.coordinates,
            dtype=np.float64,
            copy=True,
        )
        if (
            coords.ndim != 2
            or coords.shape[1] != cell_type.spatial_dimension
            or coords.shape[0] < cell_type.vertices
        ):
            raise InvalidScientificProblem(
                f"{cell_type.value} mesh coordinates must have shape "
                f"(node_count, {cell_type.spatial_dimension}) with at "
                f"least {cell_type.vertices} nodes; got {coords.shape}"
            )
        if not np.all(np.isfinite(coords)):
            raise InvalidScientificProblem(
                "unstructured mesh coordinates must be finite"
            )

        zero = Quantity(0.0, coordinate_unit).magnitude_in("meter")
        one = Quantity(1.0, coordinate_unit).magnitude_in("meter")
        coords = coords * (one - zero) + zero

        raw_cells = np.array(
            self.connectivity,
            dtype=np.float64,
            copy=True,
        )
        if (
            raw_cells.ndim != 2
            or raw_cells.shape[1] != cell_type.vertices
            or raw_cells.shape[0] < 1
        ):
            raise InvalidScientificProblem(
                f"{cell_type.value} connectivity must have shape "
                f"(cell_count, {cell_type.vertices}); got "
                f"{raw_cells.shape}"
            )
        if not np.all(np.isfinite(raw_cells)):
            raise InvalidScientificProblem(
                "unstructured mesh connectivity must be finite"
            )
        rounded = np.rint(raw_cells)
        if not np.array_equal(raw_cells, rounded):
            first = np.argwhere(raw_cells != rounded)[0]
            raise InvalidScientificProblem(
                f"connectivity value at "
                f"{tuple(int(i) for i in first)} is not an exact integer"
            )
        cells = rounded.astype(np.int64)
        if np.any(cells < 0) or np.any(cells >= len(coords)):
            first = np.argwhere(
                (cells < 0) | (cells >= len(coords))
            )[0]
            value = int(cells[tuple(first)])
            raise InvalidScientificProblem(
                f"connectivity index {value} at "
                f"{tuple(int(i) for i in first)} is outside "
                f"[0, {len(coords)})"
            )

        coords.setflags(write=False)
        cells.setflags(write=False)
        object.__setattr__(self, "mesh_id", mesh_id)
        object.__setattr__(self, "cell_type", cell_type)
        object.__setattr__(self, "coordinates", coords)
        object.__setattr__(self, "connectivity", cells)
        object.__setattr__(self, "coordinate_unit", "meter")
        object.__setattr__(
            self, "description", str(self.description).strip()
        )

    @property
    def node_count(self) -> int:
        return int(self.coordinates.shape[0])

    @property
    def cell_count(self) -> int:
        return int(self.connectivity.shape[0])

    def store(self, store: BulkDataStore) -> UnstructuredMesh:
        coordinate_reference = store_values(
            store,
            f"{self.mesh_id}:coordinates",
            self.coordinates.reshape(-1),
            unit="meter",
        )
        connectivity_reference = store_values(
            store,
            f"{self.mesh_id}:connectivity",
            self.connectivity.astype(
                np.float64, copy=False
            ).reshape(-1),
            unit="dimensionless",
        )
        return UnstructuredMesh(
            mesh_id=self.mesh_id,
            cell_type=self.cell_type,
            node_count=self.node_count,
            cell_count=self.cell_count,
            coordinates=coordinate_reference,
            connectivity=connectivity_reference,
            description=self.description,
        )

    @classmethod
    def from_record(
        cls,
        mesh: UnstructuredMesh,
        resolver: BulkDataResolver,
    ) -> "UnstructuredMeshData":
        if not isinstance(mesh, UnstructuredMesh):
            raise InvalidScientificProblem(
                "unstructured mesh data requires UnstructuredMesh"
            )
        coordinates = np.asarray(
            resolver.resolve(mesh.coordinates),
            dtype=np.float64,
        ).reshape(
            mesh.node_count,
            mesh.spatial_dimension,
        )
        connectivity = np.asarray(
            resolver.resolve(mesh.connectivity),
            dtype=np.float64,
        ).reshape(
            mesh.cell_count,
            mesh.vertices_per_cell,
        )
        made = cls(
            mesh_id=mesh.mesh_id,
            cell_type=mesh.cell_type,
            coordinates=coordinates,
            connectivity=connectivity,
            coordinate_unit="meter",
            description=mesh.description,
        )
        if (
            made.node_count != mesh.node_count
            or made.cell_count != mesh.cell_count
        ):
            raise InvalidScientificProblem(
                "resolved unstructured mesh counts disagree with record"
            )
        return made
