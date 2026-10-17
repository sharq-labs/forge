"""Executable field mapping across structured and unstructured supports.

The runtime keeps field values content-addressed. This module resolves them only
while a transfer is being executed, validates the source/target support, maps
the values, then stores a new content-addressed FieldRecord.

``CONSERVATIVE_CELL`` (Phase 1 BR2) is a first-order remap by exact cell
intersection, implemented for exactly these supports: two axis-aligned
structured grids (any spacing and origin), and any pair of planar 2D supports
whose cells are triangles, strictly convex quadrilaterals or structured
rectangles.  Both supports must cover each other; 3D cells, non-convex cells,
node fields, offset-scale units and any extrapolation are refused.  It never
falls back to the nearest-site path.  Intersection candidates are found by
bounding boxes, so the polygon path is O(source cells x target cells) in the
worst case and is meant for interface meshes of moderate size.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

import numpy as np
import scipy.sparse as sp

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
from ...scientific.units.quantity import is_ratio_scale


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


#: Geometric round-off allowance on the COVERAGE of a cell by the cells that
#: overlap it, relative to the cell's own measure.  Intersections of float64
#: rectangles and convex polygons are not exact; this is not a physical
#: tolerance, it never admits extrapolation (a larger deficit is refused) and
#: every measured deficit is recorded in the mapping provenance.
CONSERVATIVE_COVERAGE_ROUNDOFF = 1e-9

#: The conservative method this module implements, as recorded in provenance.
CONSERVATIVE_METHOD = "first_order_intersection_remap"


def _interval_overlaps(source_edges: np.ndarray, target_edges: np.ndarray) -> sp.csr_matrix:
    """Exact overlap lengths of two sorted 1D partitions, as a sparse (n_source, n_target) matrix."""
    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    for a in range(len(source_edges) - 1):
        lo, hi = float(source_edges[a]), float(source_edges[a + 1])
        first = max(0, int(np.searchsorted(target_edges, lo, side="right")) - 1)
        for b in range(first, len(target_edges) - 1):
            t_lo, t_hi = float(target_edges[b]), float(target_edges[b + 1])
            if t_lo >= hi:
                break
            length = min(hi, t_hi) - max(lo, t_lo)
            if length > 0.0:
                rows.append(a)
                cols.append(b)
                values.append(length)
    return sp.csr_matrix(
        (values, (rows, cols)), shape=(len(source_edges) - 1, len(target_edges) - 1)
    )


def _structured_overlap(source: StructuredMesh, target: StructuredMesh) -> sp.csr_matrix:
    """Cell-overlap areas of two axis-aligned rectangle grids (row-major cell order, y rows)."""
    sx, sy = (np.asarray(axis, dtype=np.float64) for axis in source.axis_coordinates())
    tx, ty = (np.asarray(axis, dtype=np.float64) for axis in target.axis_coordinates())
    # kron(Oy, Ox)[ay*ncx_s + ax, jy*ncx_t + jx] = Oy[ay, jy] * Ox[ax, jx]: the
    # overlap of two rectangles is the product of their axis overlaps.
    return sp.kron(_interval_overlaps(sy, ty), _interval_overlaps(sx, tx), format="csr")


def _signed_area(polygon: np.ndarray) -> float:
    x, y = polygon[:, 0], polygon[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _convex_cells(mesh: MeshSupport, resolver: BulkDataResolver) -> list[np.ndarray]:
    """Every cell of a 2D support as a counter-clockwise convex polygon; anything else is refused."""
    if isinstance(mesh, StructuredMesh):
        xs, ys = (np.asarray(axis, dtype=np.float64) for axis in mesh.axis_coordinates())
        return [
            np.array(((xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])))
            for j in range(len(ys) - 1)
            for i in range(len(xs) - 1)
        ]
    if mesh.cell_type not in (CellType.TRIANGLE, CellType.QUADRILATERAL):
        raise InvalidScientificProblem(
            f"conservative_cell mapping is implemented for 2D triangle and convex quadrilateral cells and "
            f"axis-aligned structured grids; mesh {mesh.mesh_id!r} has {mesh.cell_type.value} cells"
        )
    coords, cells = _unstructured_geometry(mesh, resolver)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise InvalidScientificProblem(
            f"conservative_cell mapping needs planar 2D coordinates; mesh {mesh.mesh_id!r} has "
            f"coordinates of shape {coords.shape}"
        )
    polygons: list[np.ndarray] = []
    for index, cell in enumerate(coords[cells]):
        polygon = np.array(cell, dtype=np.float64)
        area = _signed_area(polygon)
        if not math.isfinite(area) or area == 0.0:
            raise InvalidScientificProblem(
                f"mesh {mesh.mesh_id!r} cell {index} is degenerate (signed area {area!r})"
            )
        if area < 0.0:
            polygon = polygon[::-1].copy()
        edges = np.roll(polygon, -1, axis=0) - polygon
        turns = edges[:, 0] * np.roll(edges, -1, axis=0)[:, 1] - edges[:, 1] * np.roll(edges, -1, axis=0)[:, 0]
        if np.any(turns <= 0.0):
            raise InvalidScientificProblem(
                f"mesh {mesh.mesh_id!r} cell {index} is not strictly convex; the intersection remap "
                f"is implemented for convex cells only"
            )
        polygons.append(polygon)
    return polygons


def _clip(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman intersection of two counter-clockwise convex polygons."""
    output = [point for point in subject]
    count = len(clip)
    for k in range(count):
        if not output:
            break
        a, b = clip[k], clip[(k + 1) % count]
        ex, ey = b[0] - a[0], b[1] - a[1]
        points, output = output, []
        for index, current in enumerate(points):
            previous = points[index - 1]
            s_cur = ex * (current[1] - a[1]) - ey * (current[0] - a[0])
            s_prev = ex * (previous[1] - a[1]) - ey * (previous[0] - a[0])
            if s_cur >= 0.0:
                if s_prev < 0.0:
                    output.append(previous + (s_prev / (s_prev - s_cur)) * (current - previous))
                output.append(current)
            elif s_prev >= 0.0:
                output.append(previous + (s_prev / (s_prev - s_cur)) * (current - previous))
    return np.array(output) if len(output) >= 3 else np.zeros((0, 2))


def _polygon_overlap(
    source: list[np.ndarray], target: list[np.ndarray]
) -> sp.csr_matrix:
    """Exact (up to round-off) intersection areas of two convex 2D partitions."""
    lower = np.array([p.min(axis=0) for p in source])
    upper = np.array([p.max(axis=0) for p in source])
    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    for j, cell in enumerate(target):
        t_lower, t_upper = cell.min(axis=0), cell.max(axis=0)
        candidates = np.nonzero(np.all(lower < t_upper, axis=1) & np.all(upper > t_lower, axis=1))[0]
        origin = cell[0]
        local_target = cell - origin  # local frame: less cancellation far from the origin
        for i in candidates:
            piece = _clip(source[int(i)] - origin, local_target)
            if len(piece):
                area = _signed_area(piece)
                if area > 0.0:
                    rows.append(int(i))
                    cols.append(j)
                    values.append(area)
    return sp.csr_matrix((values, (rows, cols)), shape=(len(source), len(target)))


def _overlap_geometry(
    source_mesh: MeshSupport, target_mesh: MeshSupport, resolver: BulkDataResolver
) -> tuple[sp.csr_matrix, np.ndarray, np.ndarray, str]:
    """(overlap matrix, source cell measures, target cell measures, geometry name)."""
    if isinstance(source_mesh, StructuredMesh) and isinstance(target_mesh, StructuredMesh):
        sx, sy = (np.diff(np.asarray(a, dtype=np.float64)) for a in source_mesh.axis_coordinates())
        tx, ty = (np.diff(np.asarray(a, dtype=np.float64)) for a in target_mesh.axis_coordinates())
        return (
            _structured_overlap(source_mesh, target_mesh),
            np.outer(sy, sx).reshape(-1),
            np.outer(ty, tx).reshape(-1),
            "axis_aligned_rectangles",
        )
    for mesh in (source_mesh, target_mesh):
        if mesh.spatial_dimension != 2:
            raise InvalidScientificProblem(
                f"conservative_cell mapping is implemented in 2D only; mesh {mesh.mesh_id!r} is "
                f"{mesh.spatial_dimension}D (3D intersection is not implemented)"
            )
    source = _convex_cells(source_mesh, resolver)
    target = _convex_cells(target_mesh, resolver)
    return (
        _polygon_overlap(source, target),
        np.array([_signed_area(p) for p in source]),
        np.array([_signed_area(p) for p in target]),
        "convex_polygons_2d",
    )


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

        if definition.method is FieldMappingMethod.CONSERVATIVE_CELL:
            # never the site-based path below: a nearest-site value rescaled
            # to the global integral is not a conservative transfer
            return self._conservative(
                record, source, source_mesh, target_definition, target_mesh, definition
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

    def _conservative(
        self,
        record: FieldRecord,
        source: FieldValue,
        source_mesh: MeshSupport,
        target_definition: FieldDefinition,
        target_mesh: MeshSupport,
        definition: FieldMappingDefinition,
    ) -> FieldMappingResult:
        """First-order conservative remap by exact cell intersection (Phase 1 BR2).

        ``T_j = sum_i S_i |A_i n B_j| / |B_j|``: every source cell's integral
        ``S_i |A_i|`` is distributed over the target cells it overlaps, in
        proportion to the overlap measure.  When the two supports cover each
        other exactly, every source integral is accounted for locally and the
        total is conserved without any rescaling; a constant field maps to the
        same constant.  Anything the method cannot do honestly is refused:
        node fields, offset-scale units, partial coverage in either direction,
        3D cells and non-convex cells.
        """
        if (
            source.definition.location is not FieldLocation.CELL
            or target_definition.location is not FieldLocation.CELL
        ):
            raise InvalidScientificProblem(
                "conservative_cell mapping requires cell-centered "
                "source and target fields"
            )
        for unit in (record.definition.unit, target_definition.unit):
            if not is_ratio_scale(unit):
                # the integral of an offset-scale value depends on where its
                # zero was put: no conservation statement survives that
                raise InvalidScientificProblem(
                    f"conservative_cell mapping refuses offset-scale unit {unit!r}: the integral "
                    f"of a quantity whose zero is a convention is not conserved by any transfer; "
                    f"map an absolute-scale quantity (kelvin, or the extensive quantity itself)"
                )
        if source_mesh.spatial_dimension != target_mesh.spatial_dimension:
            raise InvalidScientificProblem(
                f"field mapping crosses spatial dimensions "
                f"{source_mesh.spatial_dimension}D -> {target_mesh.spatial_dimension}D"
            )
        overlap, source_measures, target_measures, geometry = _overlap_geometry(
            source_mesh, target_mesh, self.resolver
        )
        components = source.definition.components
        values = _component_view(source.values, components).reshape(-1, components)
        if values.shape[0] != overlap.shape[0] or len(target_measures) != overlap.shape[1]:
            raise InvalidScientificProblem(
                f"mapping {definition.mapping_id!r}: {values.shape[0]} source values for "
                f"{overlap.shape[0]} source cells and {target_definition.expected_count(target_mesh)} "
                f"target values for {overlap.shape[1]} target cells"
            )
        source_deficit = np.abs(1.0 - np.asarray(overlap.sum(axis=1)).reshape(-1) / source_measures)
        target_deficit = np.abs(1.0 - np.asarray(overlap.sum(axis=0)).reshape(-1) / target_measures)
        uncovered_targets = int(np.count_nonzero(target_deficit > CONSERVATIVE_COVERAGE_ROUNDOFF))
        if uncovered_targets:
            raise InvalidScientificProblem(
                f"mapping {definition.mapping_id!r} would extrapolate: {uncovered_targets}/"
                f"{len(target_measures)} target cells are not covered by source support "
                f"{source_mesh.mesh_id!r} (largest deficit {float(target_deficit.max()):.3g} of a cell)"
            )
        uncovered_sources = int(np.count_nonzero(source_deficit > CONSERVATIVE_COVERAGE_ROUNDOFF))
        if uncovered_sources:
            raise InvalidScientificProblem(
                f"mapping {definition.mapping_id!r} cannot conserve: {uncovered_sources}/"
                f"{len(source_measures)} source cells lie partly outside target support "
                f"{target_mesh.mesh_id!r} (largest deficit {float(source_deficit.max()):.3g} of a cell), "
                f"so part of their integral would be dropped"
            )

        mapped = np.asarray(overlap.T @ values) / target_measures[:, np.newaxis]
        source_integral = (values * source_measures[:, np.newaxis]).sum(axis=0)
        target_integral = (mapped * target_measures[:, np.newaxis]).sum(axis=0)
        # signed fields: the scale is the L1 mass, so a field that integrates
        # to zero is judged against its own magnitude, never divided by ~0
        scale = (np.abs(values) * source_measures[:, np.newaxis]).sum(axis=0)
        residual = np.abs(target_integral - source_integral)
        relative = [
            0.0 if s == 0.0 and r == 0.0 else (float(r / s) if s > 0.0 else math.inf)
            for r, s in zip(residual, scale)
        ]
        if not all(math.isfinite(x) for x in relative) or not np.all(np.isfinite(mapped)):
            raise InvalidScientificProblem(
                f"mapping {definition.mapping_id!r} produced a non-finite transfer or conservation residual"
            )
        conservation_error = max(relative)

        round_trip = None
        if definition.verify_round_trip:
            reverse = np.asarray(overlap @ mapped) / source_measures[:, np.newaxis]
            weights = source_measures[:, np.newaxis]
            numerator = math.sqrt(float(np.sum(weights * (values - reverse) ** 2)))
            denominator = max(
                math.sqrt(float(np.sum(weights * values ** 2))),
                np.finfo(np.float64).tiny,
            )
            round_trip = numerator / denominator
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
        result = FieldValue(
            target_definition,
            target_mesh,
            _restore_components(
                mapped,
                base_shape[:-1] if target_definition.components > 1 else base_shape,
                target_definition.components,
            ),
        )
        record_out, _ = result.store(self.store)
        provenance = {
            "method": CONSERVATIVE_METHOD,
            "geometry": geometry,
            "order": "first (piecewise-constant per cell)",
            "local_conservation": (
                "each source cell's integral is distributed over the target cells it "
                "overlaps by exact intersection measure; no global rescaling"
            ),
            "overlap_pairs": int(overlap.nnz),
            "coverage_roundoff_allowance": CONSERVATIVE_COVERAGE_ROUNDOFF,
            "max_source_coverage_deficit": float(source_deficit.max()) if source_deficit.size else 0.0,
            "max_target_coverage_deficit": float(target_deficit.max()) if target_deficit.size else 0.0,
            "conservation_absolute_residual": [float(x) for x in residual],
            "conservation_scale_l1": [float(x) for x in scale],
            "conservation_unit": f"{target_definition.unit} * meter ** 2",
            "round_trip_norm": "measure_weighted_l2" if round_trip is not None else None,
            "notice": (
                "conservation and round-trip residuals are diagnostics of this transfer; "
                "neither bounds the pointwise error of the transferred field"
            ),
        }
        return FieldMappingResult(
            record_out,
            MappingDiagnostics(
                mapping_id=definition.mapping_id,
                source_count=source.count,
                target_count=result.count,
                extrapolated_count=0,
                coverage_fraction=1.0,
                round_trip_relative_l2=round_trip,
                conservation_relative_error=conservation_error,
                provenance=provenance,
            ),
        )


# Backward-compatible name for code that only knew structured fields.
StructuredFieldMapper = FieldMapper
