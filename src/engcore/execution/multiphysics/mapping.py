"""Executable field mapping across structured and unstructured supports.

The runtime keeps field values content-addressed. This module resolves them only
while a transfer is being executed, validates the source/target support, maps
the values, then stores a new content-addressed FieldRecord.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

import numpy as np

from ...data.field import FieldValue
from ...data.mesh import UnstructuredMeshData
from ...data.resolver import BulkDataResolver
from ...data.store import BulkDataStore
from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields import (
    CellType,
    FieldDefinition,
    FieldLocation,
    FieldRecord,
    MeshSupport,
    StructuredMesh,
    UnstructuredMesh,
)
from ...scientific.multiphysics import (
    ExtrapolationPolicy,
    FieldMappingDefinition,
    FieldMappingMethod,
    MappingDiagnostics,
)


@dataclass(frozen=True)
class FieldMappingResult:
    record: FieldRecord
    diagnostics: MappingDiagnostics


def _component_view(values: np.ndarray, components: int) -> np.ndarray:
    return (
        values[..., np.newaxis]
        if components == 1
        else values
    )


def _restore_components(
    values: np.ndarray,
    base_shape: tuple[int, ...],
    components: int,
) -> np.ndarray:
    if components == 1:
        return values.reshape(base_shape)
    return values.reshape((*base_shape, components))


def _structured_axes(
    mesh: StructuredMesh,
    location: FieldLocation,
) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = mesh.axis_coordinates()
    x = np.asarray(xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    if location is FieldLocation.CELL:
        x = (x[:-1] + x[1:]) * 0.5
        y = (y[:-1] + y[1:]) * 0.5
    return x, y


def _structured_sites(
    mesh: StructuredMesh,
    location: FieldLocation,
) -> np.ndarray:
    x, y = _structured_axes(mesh, location)
    grid_x, grid_y = np.meshgrid(x, y)
    return np.column_stack((grid_x.reshape(-1), grid_y.reshape(-1)))


def _unstructured_geometry(
    mesh: UnstructuredMesh,
    resolver: BulkDataResolver,
) -> tuple[np.ndarray, np.ndarray]:
    data = UnstructuredMeshData.from_record(mesh, resolver)
    return data.coordinates, data.connectivity

def _unstructured_sites(
    mesh: UnstructuredMesh,
    location: FieldLocation,
    resolver: BulkDataResolver,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coords, cells = _unstructured_geometry(mesh, resolver)
    if location is FieldLocation.NODE:
        return coords, coords, cells
    centroids = np.mean(coords[cells], axis=1)
    return centroids, coords, cells


def _sites(
    mesh: MeshSupport,
    location: FieldLocation,
    resolver: BulkDataResolver,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    if isinstance(mesh, StructuredMesh):
        return _structured_sites(mesh, location), None, None
    sites, coords, cells = _unstructured_sites(
        mesh, location, resolver
    )
    return sites, coords, cells


def _triangle_contains(
    point: np.ndarray,
    triangle: np.ndarray,
    tolerance: float,
) -> bool:
    a, b, c = triangle
    v0 = c - a
    v1 = b - a
    v2 = point - a
    dot00 = float(np.dot(v0, v0))
    dot01 = float(np.dot(v0, v1))
    dot02 = float(np.dot(v0, v2))
    dot11 = float(np.dot(v1, v1))
    dot12 = float(np.dot(v1, v2))
    denominator = dot00 * dot11 - dot01 * dot01
    if abs(denominator) <= np.finfo(np.float64).tiny:
        return False
    inv = 1.0 / denominator
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return (
        u >= -tolerance
        and v >= -tolerance
        and u + v <= 1.0 + tolerance
    )


def _tetra_contains(
    point: np.ndarray,
    tetra: np.ndarray,
    tolerance: float,
) -> bool:
    base = tetra[0]
    matrix = np.column_stack(
        (tetra[1] - base, tetra[2] - base, tetra[3] - base)
    )
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) <= np.finfo(np.float64).tiny:
        return False
    weights = np.linalg.solve(matrix, point - base)
    w1, w2, w3 = (float(value) for value in weights)
    w0 = 1.0 - w1 - w2 - w3
    return all(
        value >= -tolerance and value <= 1.0 + tolerance
        for value in (w0, w1, w2, w3)
    )


_HEX_TETS = (
    (0, 1, 3, 4),
    (1, 2, 3, 6),
    (1, 4, 5, 6),
    (3, 4, 6, 7),
    (1, 3, 4, 6),
)


def _cell_contains(
    point: np.ndarray,
    vertices: np.ndarray,
    cell_type: CellType,
    tolerance: float,
) -> bool:
    if cell_type is CellType.TRIANGLE:
        return _triangle_contains(point, vertices, tolerance)
    if cell_type is CellType.QUADRILATERAL:
        return (
            _triangle_contains(
                point, vertices[[0, 1, 2]], tolerance
            )
            or _triangle_contains(
                point, vertices[[0, 2, 3]], tolerance
            )
        )
    if cell_type is CellType.TETRAHEDRON:
        return _tetra_contains(point, vertices, tolerance)
    return any(
        _tetra_contains(point, vertices[list(indices)], tolerance)
        for indices in _HEX_TETS
    )


def _inside_unstructured(
    points: np.ndarray,
    coords: np.ndarray,
    cells: np.ndarray,
    cell_type: CellType,
) -> np.ndarray:
    lower = np.min(coords, axis=0)
    upper = np.max(coords, axis=0)
    scale = max(
        1.0,
        float(np.max(np.abs(coords))),
        float(np.max(upper - lower)),
    )
    tolerance = 1e-12 * scale
    inside = np.zeros(len(points), dtype=bool)

    cell_vertices = coords[cells]
    cell_lower = np.min(cell_vertices, axis=1) - tolerance
    cell_upper = np.max(cell_vertices, axis=1) + tolerance

    for index, point in enumerate(points):
        candidates = np.where(
            np.all(point >= cell_lower, axis=1)
            & np.all(point <= cell_upper, axis=1)
        )[0]
        for cell_index in candidates:
            if _cell_contains(
                point,
                cell_vertices[cell_index],
                cell_type,
                tolerance,
            ):
                inside[index] = True
                break
    return inside


def _support_coverage(
    source_mesh: MeshSupport,
    target_sites: np.ndarray,
    resolver: BulkDataResolver,
) -> np.ndarray:
    if isinstance(source_mesh, StructuredMesh):
        xs, ys = source_mesh.axis_coordinates()
        lower = np.asarray((xs[0], ys[0]), dtype=np.float64)
        upper = np.asarray((xs[-1], ys[-1]), dtype=np.float64)
        scale = max(
            1.0,
            float(np.max(np.abs(np.concatenate((lower, upper))))),
        )
        tolerance = 1e-12 * scale
        return np.all(
            (target_sites >= lower - tolerance)
            & (target_sites <= upper + tolerance),
            axis=1,
        )

    coords, cells = _unstructured_geometry(
        source_mesh, resolver
    )
    if target_sites.shape[1] != source_mesh.spatial_dimension:
        raise InvalidScientificProblem(
            f"cannot map {target_sites.shape[1]}D target sites from "
            f"{source_mesh.spatial_dimension}D source mesh "
            f"{source_mesh.mesh_id!r}"
        )
    return _inside_unstructured(
        target_sites,
        coords,
        cells,
        source_mesh.cell_type,
    )


def _nearest_map(
    source_values: np.ndarray,
    source_sites: np.ndarray,
    target_sites: np.ndarray,
) -> np.ndarray:
    target = np.empty(
        (len(target_sites), source_values.shape[1]),
        dtype=np.float64,
    )
    for index, point in enumerate(target_sites):
        delta = source_sites - point
        distance2 = np.einsum("ij,ij->i", delta, delta)
        target[index] = source_values[int(np.argmin(distance2))]
    return target


def _bracket(
    axis: np.ndarray,
    value: float,
) -> tuple[int, int, float]:
    if value <= axis[0]:
        return 0, 0, 0.0
    if value >= axis[-1]:
        last = len(axis) - 1
        return last, last, 0.0
    right = int(np.searchsorted(axis, value, side="right"))
    left = right - 1
    span = float(axis[right] - axis[left])
    weight = (
        0.0 if span == 0.0 else float((value - axis[left]) / span)
    )
    return left, right, weight


def _bilinear_map(
    source: np.ndarray,
    source_mesh: StructuredMesh,
    source_location: FieldLocation,
    target_mesh: StructuredMesh,
    target_location: FieldLocation,
) -> np.ndarray:
    sx, sy = _structured_axes(source_mesh, source_location)
    tx, ty = _structured_axes(target_mesh, target_location)
    shaped = source.reshape(
        len(sy), len(sx), source.shape[1]
    )
    target = np.empty(
        (len(ty), len(tx), source.shape[1]),
        dtype=np.float64,
    )
    for j, y in enumerate(ty):
        y0, y1, wy = _bracket(sy, float(y))
        for i, x in enumerate(tx):
            x0, x1, wx = _bracket(sx, float(x))
            q00 = shaped[y0, x0]
            q10 = shaped[y0, x1]
            q01 = shaped[y1, x0]
            q11 = shaped[y1, x1]
            lower = (1.0 - wx) * q00 + wx * q10
            upper = (1.0 - wx) * q01 + wx * q11
            target[j, i] = (
                (1.0 - wy) * lower + wy * upper
            )
    return target.reshape(-1, source.shape[1])


def _triangle_area(vertices: np.ndarray) -> float:
    a, b, c = vertices
    if vertices.shape[1] == 2:
        return 0.5 * abs(
            float(
                (b[0] - a[0]) * (c[1] - a[1])
                - (b[1] - a[1]) * (c[0] - a[0])
            )
        )
    return 0.5 * float(
        np.linalg.norm(np.cross(b - a, c - a))
    )


def _tetra_volume(vertices: np.ndarray) -> float:
    a, b, c, d = vertices
    matrix = np.column_stack((b - a, c - a, d - a))
    return abs(float(np.linalg.det(matrix))) / 6.0


def _cell_measures(
    mesh: MeshSupport,
    resolver: BulkDataResolver,
) -> np.ndarray:
    if isinstance(mesh, StructuredMesh):
        area = (
            mesh.spacing_x.magnitude_in("meter")
            * mesh.spacing_y.magnitude_in("meter")
        )
        return np.full(mesh.cell_count, area, dtype=np.float64)

    coords, cells = _unstructured_geometry(mesh, resolver)
    vertices = coords[cells]
    measures = np.empty(mesh.cell_count, dtype=np.float64)
    for index, cell in enumerate(vertices):
        if mesh.cell_type is CellType.TRIANGLE:
            measure = _triangle_area(cell)
        elif mesh.cell_type is CellType.QUADRILATERAL:
            measure = (
                _triangle_area(cell[[0, 1, 2]])
                + _triangle_area(cell[[0, 2, 3]])
            )
        elif mesh.cell_type is CellType.TETRAHEDRON:
            measure = _tetra_volume(cell)
        else:
            measure = sum(
                _tetra_volume(cell[list(indices)])
                for indices in _HEX_TETS
            )
        if not math.isfinite(measure) or measure <= 0.0:
            raise InvalidScientificProblem(
                f"unstructured mesh {mesh.mesh_id!r} cell {index} "
                f"has non-positive measure {measure!r}"
            )
        measures[index] = measure
    return measures


def _conserve_integral(
    source_values: np.ndarray,
    target_values: np.ndarray,
    source_measures: np.ndarray,
    target_measures: np.ndarray,
) -> tuple[np.ndarray, float]:
    source_integral = np.sum(
        source_values * source_measures[:, np.newaxis],
        axis=0,
    )
    target_integral = np.sum(
        target_values * target_measures[:, np.newaxis],
        axis=0,
    )
    corrected = np.array(target_values, copy=True)
    tiny = np.finfo(np.float64).tiny

    for component in range(corrected.shape[1]):
        source_total = float(source_integral[component])
        target_total = float(target_integral[component])
        if abs(target_total) > tiny:
            corrected[:, component] *= source_total / target_total
        else:
            correction = (
                source_total
                / float(np.sum(target_measures))
            )
            corrected[:, component] += correction

    final_integral = np.sum(
        corrected * target_measures[:, np.newaxis],
        axis=0,
    )
    scale = np.maximum(np.abs(source_integral), tiny)
    error = float(
        np.max(np.abs(final_integral - source_integral) / scale)
    )
    return corrected, error


def _relative_l2(
    left: np.ndarray,
    right: np.ndarray,
) -> float:
    numerator = float(np.linalg.norm(left - right))
    denominator = max(
        float(np.linalg.norm(left)),
        np.finfo(np.float64).tiny,
    )
    return numerator / denominator


class FieldMapper:
    """Maps FieldRecord values across declared mesh supports."""

    def __init__(
        self,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> None:
        self.resolver = resolver
        self.store = store

    def execute(
        self,
        record: FieldRecord,
        source_mesh: MeshSupport,
        target_definition: FieldDefinition,
        target_mesh: MeshSupport,
        definition: FieldMappingDefinition,
    ) -> FieldMappingResult:
        source = FieldValue.from_record(
            record, source_mesh, self.resolver
        ).to_unit(target_definition.unit)
        if (
            source.definition.components
            != target_definition.components
        ):
            raise InvalidScientificProblem(
                "field mapping cannot change component count"
            )

        same_support = (
            source_mesh.fingerprint()
            == target_mesh.fingerprint()
        )
        if definition.method is FieldMappingMethod.IDENTITY:
            if (
                not same_support
                or source.definition.location
                is not target_definition.location
            ):
                raise InvalidScientificProblem(
                    "identity mapping requires identical support and "
                    "field location"
                )
            result = FieldValue(
                target_definition,
                target_mesh,
                source.values,
            )
            record_out, _ = result.store(self.store)
            return FieldMappingResult(
                record_out,
                MappingDiagnostics(
                    mapping_id=definition.mapping_id,
                    source_count=source.count,
                    target_count=result.count,
                    extrapolated_count=0,
                    coverage_fraction=1.0,
                    round_trip_relative_l2=(
                        0.0 if definition.verify_round_trip else None
                    ),
                    conservation_relative_error=0.0,
                ),
            )

        source_sites, _, _ = _sites(
            source_mesh,
            source.definition.location,
            self.resolver,
        )
        target_sites, _, _ = _sites(
            target_mesh,
            target_definition.location,
            self.resolver,
        )
        if source_sites.shape[1] != target_sites.shape[1]:
            raise InvalidScientificProblem(
                f"field mapping crosses spatial dimensions "
                f"{source_sites.shape[1]}D -> {target_sites.shape[1]}D"
            )

        inside = _support_coverage(
            source_mesh,
            target_sites,
            self.resolver,
        )
        outside_count = int(np.count_nonzero(~inside))
        if (
            outside_count
            and definition.extrapolation
            is ExtrapolationPolicy.REFUSE
        ):
            raise InvalidScientificProblem(
                f"mapping {definition.mapping_id!r} would extrapolate "
                f"{outside_count}/{len(target_sites)} target sites outside "
                f"source support {source_mesh.mesh_id!r}"
            )

        source_values = _component_view(
            source.values,
            source.definition.components,
        ).reshape(-1, source.definition.components)

        if definition.method is FieldMappingMethod.BILINEAR:
            if not isinstance(
                source_mesh, StructuredMesh
            ) or not isinstance(target_mesh, StructuredMesh):
                raise InvalidScientificProblem(
                    "bilinear mapping is defined only for structured "
                    "rectilinear supports"
                )
            mapped = _bilinear_map(
                source_values,
                source_mesh,
                source.definition.location,
                target_mesh,
                target_definition.location,
            )
        else:
            mapped = _nearest_map(
                source_values,
                source_sites,
                target_sites,
            )

        conservation_error = None
        if (
            definition.method
            is FieldMappingMethod.CONSERVATIVE_CELL
        ):
            if (
                source.definition.location is not FieldLocation.CELL
                or target_definition.location
                is not FieldLocation.CELL
            ):
                raise InvalidScientificProblem(
                    "conservative_cell mapping requires cell-centered "
                    "source and target fields"
                )
            source_measures = _cell_measures(
                source_mesh, self.resolver
            )
            target_measures = _cell_measures(
                target_mesh, self.resolver
            )
            mapped, conservation_error = _conserve_integral(
                source_values,
                mapped,
                source_measures,
                target_measures,
            )

        round_trip = None
        if definition.verify_round_trip:
            reverse_inside = _support_coverage(
                target_mesh,
                source_sites,
                self.resolver,
            )
            if (
                np.any(~reverse_inside)
                and definition.extrapolation
                is ExtrapolationPolicy.REFUSE
            ):
                raise InvalidScientificProblem(
                    f"mapping {definition.mapping_id!r} cannot perform "
                    "declared round-trip verification without extrapolation"
                )

            if (
                definition.method is FieldMappingMethod.BILINEAR
                and isinstance(source_mesh, StructuredMesh)
                and isinstance(target_mesh, StructuredMesh)
            ):
                reverse = _bilinear_map(
                    mapped,
                    target_mesh,
                    target_definition.location,
                    source_mesh,
                    source.definition.location,
                )
            else:
                reverse = _nearest_map(
                    mapped,
                    target_sites,
                    source_sites,
                )
            round_trip = _relative_l2(
                source_values,
                reverse,
            )
            if (
                definition.relative_error_limit is not None
                and round_trip > definition.relative_error_limit
            ):
                raise InvalidScientificProblem(
                    f"mapping {definition.mapping_id!r} round-trip "
                    f"relative L2 {round_trip:g} exceeds "
                    f"{definition.relative_error_limit:g}"
                )

        base_shape = target_definition.expected_shape(target_mesh)
        values = _restore_components(
            mapped,
            base_shape[:-1]
            if target_definition.components > 1
            else base_shape,
            target_definition.components,
        )
        result = FieldValue(
            target_definition,
            target_mesh,
            values,
        )
        record_out, _ = result.store(self.store)
        target_site_count = max(1, len(target_sites))
        return FieldMappingResult(
            record_out,
            MappingDiagnostics(
                mapping_id=definition.mapping_id,
                source_count=source.count,
                target_count=result.count,
                extrapolated_count=outside_count,
                coverage_fraction=(
                    1.0 - outside_count / target_site_count
                ),
                round_trip_relative_l2=round_trip,
                conservation_relative_error=conservation_error,
            ),
        )


# Backward-compatible name for code that only knew structured fields.
StructuredFieldMapper = FieldMapper
