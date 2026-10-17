"""Site measures of a field support, for measure-weighted residual norms (Phase 3 BR13).

``ResidualNorm.L2_MEASURE`` weights each stored value by the measure of the
region it represents, so a residual on a non-uniform support is not dominated
by where the sites happen to be dense.  The weights come from the SAME
validated cell geometry the conservative remap uses (``mapping._convex_cells``,
``mapping._tetrahedra``), so a support that remap refuses as degenerate or
non-convex is refused here too.

=========================  =====================================================  =========
support                    cell field weight / node field weight                  status
=========================  =====================================================  =========
structured rectilinear     dx * dy  /  tensor trapezoid (Q1 lumped mass)          supported
triangle                   area     /  area / 3 per vertex (P1 lumped mass)       supported
convex quadrilateral       area     /  refused                                     partial
tetrahedron                volume   /  volume / 4 per vertex (P1 lumped mass)     supported
hexahedron                 refused  /  refused                                     refused
=========================  =====================================================  =========

The P1 lumped nodal weight (row sum of the consistent mass matrix) is exact for
simplices and for axis-aligned rectangles; for a general quadrilateral the
bilinear row sums are not ``area / 4``, so node fields on quadrilaterals are
refused rather than approximated.  A weighted residual is still an
iterate-consistency measure, not a solution error (see ``convergence.py``).
"""

from __future__ import annotations

import numpy as np

from ...data.resolver import BulkDataResolver
from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields import CellType, FieldLocation, MeshSupport, StructuredMesh
from .mapping import _convex_cells, _signed_area, _tetrahedra, _unstructured_geometry

MEASURE_RULES = {
    ("structured", "cell"): "structured_cell_area",
    ("structured", "node"): "structured_node_trapezoid_q1_lumped",
    ("triangle", "cell"): "triangle_area",
    ("triangle", "node"): "triangle_p1_lumped_area_over_3",
    ("quadrilateral", "cell"): "convex_quadrilateral_area",
    ("tetrahedron", "cell"): "tetrahedron_volume",
    ("tetrahedron", "node"): "tetrahedron_p1_lumped_volume_over_4",
}


def _trapezoid(axis: np.ndarray) -> np.ndarray:
    widths = np.diff(axis)
    weights = np.zeros(axis.size)
    weights[:-1] += 0.5 * widths
    weights[1:] += 0.5 * widths
    return weights


def site_measures(mesh: MeshSupport, location: FieldLocation, resolver: BulkDataResolver) -> tuple[np.ndarray, str]:
    """``(weights, rule)``: one positive weight per stored site, in the site order of the field values."""
    location = FieldLocation(location)
    if isinstance(mesh, StructuredMesh):
        xs, ys = (np.asarray(axis, dtype=np.float64) for axis in mesh.axis_coordinates())
        if location is FieldLocation.CELL:
            weights = np.outer(np.diff(ys), np.diff(xs)).reshape(-1)
        else:
            weights = np.outer(_trapezoid(ys), _trapezoid(xs)).reshape(-1)
        kind = "structured"
    else:
        kind = mesh.cell_type.value
        rule = MEASURE_RULES.get((kind, location.value))
        if rule is None:
            raise InvalidScientificProblem(
                f"no measure-weighted norm is defined for {location.value} fields on {kind} support "
                f"{mesh.mesh_id!r}; supported: {sorted(MEASURE_RULES)}"
            )
        if mesh.cell_type is CellType.TETRAHEDRON:
            tets = _tetrahedra(mesh, resolver)  # degenerate cells refused
            cell = np.abs(np.einsum("ij,ij->i", tets[:, 1] - tets[:, 0],
                                    np.cross(tets[:, 2] - tets[:, 0], tets[:, 3] - tets[:, 0]))) / 6.0
        else:
            cell = np.array([_signed_area(polygon) for polygon in _convex_cells(mesh, resolver)])  # CCW, convex
        if location is FieldLocation.CELL:
            weights = cell
        else:
            _, cells = _unstructured_geometry(mesh, resolver)
            weights = np.zeros(mesh.node_count)
            np.add.at(weights, np.asarray(cells, dtype=np.int64).reshape(-1),
                      np.repeat(cell / cells.shape[1], cells.shape[1]))
    rule = MEASURE_RULES[(kind, location.value)]
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        # a node no cell touches carries no measure: its value would be unweighted
        raise InvalidScientificProblem(
            f"support {mesh.mesh_id!r} has a {location.value} site with no positive measure ({rule}); "
            f"a measure-weighted norm over it is undefined"
        )
    return weights, rule


def weighted_rms(values: np.ndarray, weights: np.ndarray, components: int) -> float:
    """``sqrt(sum_i w_i |v_i|^2 / sum_i w_i)`` with every component of a site sharing its weight."""
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    w = np.repeat(np.asarray(weights, dtype=np.float64), max(1, int(components)))
    if flat.size != w.size:
        raise InvalidScientificProblem(
            f"field has {flat.size} stored values; the support measures {w.size // max(1, int(components))} "
            f"sites x {components} component(s)"
        )
    total = float(np.sum(w))
    with np.errstate(over="ignore", invalid="ignore"):
        return float(np.sqrt(np.sum(w * flat * flat) / total))


__all__ = ["MEASURE_RULES", "site_measures", "weighted_rms"]
