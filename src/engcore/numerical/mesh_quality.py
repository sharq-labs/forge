"""Cell measures, orientation, inversion and shape quality of simplicial and quadrilateral meshes (Phase 3).

Pure geometry on plain arrays (coordinates in one length unit, connectivity as
vertex indices).  It measures and refuses; it never repairs a mesh.  Shared by
the measure-weighted coupling residual norm (BR13), mesh validity checks (BR16)
and moving-mesh kinematics (BR17).

Supported cells and what is computed exactly (up to round-off):

=============  ==========  ===========================================  =========================================
cell           coords      signed measure                               shape quality q in (0, 1]
=============  ==========  ===========================================  =========================================
interval       1D          x1 - x0                                       1 (a 1D cell has no shape)
triangle       2D          ((p1-p0) x (p2-p0)) / 2                       4 sqrt(3) |A| / sum of squared edge lengths
quadrilateral  2D          shoelace area (valid only if strictly convex)  min over corners of the scaled Jacobian
tetrahedron    3D          (p1-p0) . ((p2-p0) x (p3-p0)) / 6             12 (3 |V|)^(2/3) / sum of squared edges
=============  ==========  ===========================================  =========================================

``q = 1`` for the equilateral triangle, the square and the regular
tetrahedron; ``q -> 0`` as a cell degenerates.  A quadrilateral is VALID only
when strictly convex with a consistent orientation (otherwise its bilinear map
has a non-positive Jacobian somewhere); its corner scaled Jacobians are then
all positive.  Hexahedra are refused: positive corner Jacobians are necessary
but not sufficient for a valid trilinear map, and nothing here proves more.

A cell is DEGENERATE when ``|measure| <= 64 eps * h**d`` with ``h`` its longest
edge: below that the measure is not resolved in float64.  INVERSION is a sign
statement: relative to the positive orientation (counter-clockwise /
right-handed), or -- for a moving mesh -- relative to the same cell's sign in a
reference configuration (:func:`inverted_relative_to`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

import numpy as np

from .core import NumericalRefusal

#: the round-off floor of a cell measure, in units of eps * h**d
DEGENERACY_ULPS = 64.0

_VERTICES = {"interval": 2, "triangle": 3, "quadrilateral": 4, "tetrahedron": 4}
_DIMENSION = {"interval": 1, "triangle": 2, "quadrilateral": 2, "tetrahedron": 3}
_EDGES = {
    "interval": ((0, 1),),
    "triangle": ((0, 1), (1, 2), (2, 0)),
    "quadrilateral": ((0, 1), (1, 2), (2, 3), (3, 0)),
    "tetrahedron": ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)),
}


class MeshQualityRefusal(NumericalRefusal):
    """A mesh (or a moved configuration of one) that is degenerate, inverted or below the declared quality."""


def _arrays(cell_type: str, coordinates: Any, cells: Any) -> tuple[np.ndarray, np.ndarray]:
    if cell_type == "hexahedron":
        raise MeshQualityRefusal(
            "hexahedral cells are refused: positive corner Jacobians do not prove a valid trilinear map"
        )
    if cell_type not in _VERTICES:
        raise MeshQualityRefusal(f"unsupported cell type {cell_type!r}; supported: {sorted(_VERTICES)}")
    coords = np.asarray(coordinates, dtype=np.float64)
    if coords.ndim == 1:
        coords = coords.reshape(-1, 1)
    conn = np.asarray(cells)
    if conn.ndim != 2 or conn.shape[1] != _VERTICES[cell_type]:
        raise MeshQualityRefusal(f"{cell_type} connectivity must have shape (cells, {_VERTICES[cell_type]})")
    if coords.ndim != 2 or coords.shape[1] != _DIMENSION[cell_type]:
        raise MeshQualityRefusal(f"{cell_type} cells need {_DIMENSION[cell_type]}D coordinates; got shape {coords.shape}")
    if not np.all(np.isfinite(coords)):
        raise MeshQualityRefusal("mesh coordinates must be finite")
    if not np.issubdtype(conn.dtype, np.integer):
        if not np.all(np.isfinite(conn)) or not np.all(conn == np.round(conn)):
            raise MeshQualityRefusal("connectivity must hold integer vertex indices")
        conn = conn.astype(np.int64)
    if conn.size and (conn.min() < 0 or conn.max() >= coords.shape[0]):
        raise MeshQualityRefusal("connectivity references a vertex outside the coordinate array")
    if any(len(set(int(v) for v in row)) != conn.shape[1] for row in conn):
        raise MeshQualityRefusal("a cell repeats a vertex; it is degenerate by construction")
    return coords, conn.astype(np.int64)


def _cross2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def signed_measures(cell_type: str, coordinates: Any, cells: Any) -> np.ndarray:
    """Signed length / area / volume of every cell (positive = positive orientation)."""
    coords, conn = _arrays(cell_type, coordinates, cells)
    p = coords[conn]
    if cell_type == "interval":
        return p[:, 1, 0] - p[:, 0, 0]
    if cell_type == "triangle":
        return 0.5 * _cross2(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    if cell_type == "quadrilateral":
        x, y = p[..., 0], p[..., 1]
        return 0.5 * np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1)
    return np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0])) / 6.0


def _edge_lengths(cell_type: str, p: np.ndarray) -> np.ndarray:
    return np.stack([np.linalg.norm(p[:, b] - p[:, a], axis=-1) for a, b in _EDGES[cell_type]], axis=1)


def _corner_scaled_jacobians(p: np.ndarray) -> np.ndarray:
    """Per corner of a quadrilateral: sin of the corner angle with orientation sign, ``(e_next x e_prev)/(|..||..|)``."""
    nxt = np.roll(p, -1, axis=1) - p
    prv = np.roll(p, 1, axis=1) - p
    norms = np.linalg.norm(nxt, axis=-1) * np.linalg.norm(prv, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(norms > 0.0, _cross2(nxt, prv) / norms, 0.0)


def shape_quality(cell_type: str, coordinates: Any, cells: Any) -> np.ndarray:
    """Orientation-free shape quality in [0, 1] per cell (see the module table); 0 for a degenerate cell."""
    coords, conn = _arrays(cell_type, coordinates, cells)
    p = coords[conn]
    if cell_type == "interval":
        return np.where(np.abs(p[:, 1, 0] - p[:, 0, 0]) > 0.0, 1.0, 0.0)
    measure = np.abs(signed_measures(cell_type, coords, conn))
    squares = np.sum(_edge_lengths(cell_type, p) ** 2, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        if cell_type == "triangle":
            q = 4.0 * math.sqrt(3.0) * measure / squares
        elif cell_type == "tetrahedron":
            q = 12.0 * np.cbrt(3.0 * measure) ** 2 / squares
        else:
            corners = _corner_scaled_jacobians(p)
            sign = np.sign(signed_measures(cell_type, coords, conn))[:, None]
            q = np.min(corners * sign, axis=1)
    return np.clip(np.nan_to_num(q, nan=0.0), 0.0, 1.0)


@dataclass(frozen=True)
class MeshQualityPolicy:
    """What a mesh must satisfy.  ``minimum_quality`` has no default: how poor a cell may be is declared."""

    minimum_quality: float
    #: "positive": every cell positively oriented; "consistent": every cell the same sign (either)
    orientation: str = "consistent"

    def __post_init__(self) -> None:
        value = self.minimum_quality
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 < float(value) <= 1.0:
            raise NumericalRefusal("minimum_quality must lie in (0, 1]")
        object.__setattr__(self, "minimum_quality", float(value))
        if self.orientation not in ("positive", "consistent"):
            raise NumericalRefusal("orientation must be 'positive' or 'consistent'")

    def to_dict(self) -> dict[str, Any]:
        return {"minimum_quality": self.minimum_quality, "orientation": self.orientation}


class CellDefect(str, Enum):
    DEGENERATE = "degenerate"
    INVERTED = "inverted"
    NON_CONVEX = "non_convex"
    LOW_QUALITY = "low_quality"


@dataclass(frozen=True)
class MeshQualityReport:
    cell_type: str
    cell_count: int
    policy: MeshQualityPolicy
    minimum_quality: float
    defects: tuple[tuple[str, tuple[int, ...]], ...]

    @property
    def valid(self) -> bool:
        return not any(indices for _, indices in self.defects)

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "mesh_geometry_check_not_evidence", "cell_type": self.cell_type,
                "cell_count": self.cell_count, "policy": self.policy.to_dict(), "minimum_quality": self.minimum_quality,
                "defects": {kind: list(indices[:20]) for kind, indices in self.defects},
                "defect_counts": {kind: len(indices) for kind, indices in self.defects}, "valid": self.valid}


def degenerate_cells(cell_type: str, coordinates: Any, cells: Any) -> np.ndarray:
    """Indices of cells whose measure is not resolved in float64 (``|m| <= 64 eps h**d``)."""
    coords, conn = _arrays(cell_type, coordinates, cells)
    p = coords[conn]
    longest = np.max(_edge_lengths(cell_type, p), axis=1)
    floor = DEGENERACY_ULPS * np.finfo(np.float64).eps * longest ** _DIMENSION[cell_type]
    return np.flatnonzero(np.abs(signed_measures(cell_type, coords, conn)) <= floor)


def assess_mesh(cell_type: str, coordinates: Any, cells: Any, policy: MeshQualityPolicy) -> MeshQualityReport:
    """Degenerate, inverted, non-convex and low-quality cells under ``policy``."""
    coords, conn = _arrays(cell_type, coordinates, cells)
    measures = signed_measures(cell_type, coords, conn)
    degenerate = set(degenerate_cells(cell_type, coords, conn).tolist())
    live = np.array([i for i in range(len(conn)) if i not in degenerate], dtype=np.int64)
    if policy.orientation == "positive":
        inverted = [int(i) for i in live if measures[i] < 0.0]
    else:
        positive = int(np.sum(measures[live] > 0.0)) if live.size else 0
        majority = 1.0 if positive * 2 >= live.size else -1.0
        inverted = [int(i) for i in live if np.sign(measures[i]) != majority]
    non_convex: list[int] = []
    if cell_type == "quadrilateral" and live.size:
        corners = _corner_scaled_jacobians(coords[conn][live])
        signs = np.sign(measures[live])[:, None]
        non_convex = [int(live[k]) for k in np.flatnonzero(np.any(corners * signs <= 0.0, axis=1))]
    quality = shape_quality(cell_type, coords, conn)
    low = [int(i) for i in live if quality[i] < policy.minimum_quality and int(i) not in non_convex]
    defects = (
        (CellDefect.DEGENERATE.value, tuple(sorted(degenerate))),
        (CellDefect.INVERTED.value, tuple(inverted)),
        (CellDefect.NON_CONVEX.value, tuple(non_convex)),
        (CellDefect.LOW_QUALITY.value, tuple(low)),
    )
    return MeshQualityReport(cell_type, int(len(conn)), policy, float(np.min(quality)) if len(quality) else 0.0, defects)


def require_valid_mesh(cell_type: str, coordinates: Any, cells: Any, policy: MeshQualityPolicy) -> MeshQualityReport:
    """:func:`assess_mesh`, refusing any defect."""
    report = assess_mesh(cell_type, coordinates, cells, policy)
    if not report.valid:
        counts = {kind: len(indices) for kind, indices in report.defects if indices}
        raise MeshQualityRefusal(f"{cell_type} mesh refused: {counts} (policy {policy.to_dict()})")
    return report


def inverted_relative_to(reference: np.ndarray, current: np.ndarray, degenerate_floor: np.ndarray | None = None) -> np.ndarray:
    """Cells whose signed measure changed sign, or collapsed, between two configurations of one connectivity."""
    ref = np.asarray(reference, dtype=np.float64)
    cur = np.asarray(current, dtype=np.float64)
    if ref.shape != cur.shape:
        raise MeshQualityRefusal("two configurations of one mesh must have one measure per cell")
    floor = np.zeros_like(cur) if degenerate_floor is None else np.asarray(degenerate_floor, dtype=np.float64)
    return np.flatnonzero((np.sign(ref) != np.sign(cur)) | (np.abs(cur) <= floor))


__all__ = [
    "CellDefect",
    "DEGENERACY_ULPS",
    "MeshQualityPolicy",
    "MeshQualityRefusal",
    "MeshQualityReport",
    "assess_mesh",
    "degenerate_cells",
    "inverted_relative_to",
    "require_valid_mesh",
    "shape_quality",
    "signed_measures",
]
