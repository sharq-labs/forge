"""Viewable field files (VTU for ParaView) and the few generic field reductions the flagships need.

A VTU written here is a PRESENTATION artifact.  It is not evidence and nothing reads it back as such.  It
carries what identifies it: an XML comment with the caller's metadata, the mesh digest and the per-field
units, and array names that include the unit.  ``write_vtu`` returns the file bytes; a run bundle lists them
by their sha256.  Files are ASCII XML written as bytes (LF), so the digest is stable across platforms for
identical numbers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import numpy as np

from ..scientific.errors import InvalidScientificProblem

_VTK_TYPE = {"triangle": 5, "quadrilateral": 9}


def _ascii(a: np.ndarray) -> str:
    return " ".join(repr(float(x)) for x in np.asarray(a, dtype=float).ravel())


def write_vtu(mesh, *, point_data: Mapping[str, tuple[str, Any]] | None = None, cell_data: Mapping[str, tuple[str, Any]] | None = None,
              metadata: Mapping[str, Any]) -> bytes:
    """Serialize a 2-D Forge mesh with fields to VTU bytes.  ``*_data`` map a name to (unit, values); ``metadata`` is recorded verbatim."""
    ctype = getattr(mesh.cell_type, "value", str(mesh.cell_type)).lower()
    if ctype not in _VTK_TYPE:
        raise InvalidScientificProblem(f"VTU export supports triangle and quadrilateral cells, not {ctype!r}")
    n, c = mesh.node_count, mesh.cell_count
    points = np.zeros((n, 3))
    points[:, : mesh.coordinates.shape[1]] = mesh.coordinates
    cells = np.asarray(mesh.cells, dtype=np.int64)
    per = cells.shape[1]
    lines = ['<?xml version="1.0"?>', "<!-- forge presentation artifact, not evidence: " + json.dumps(
        {**dict(metadata), "mesh_digest": mesh.digest,
         "fields": {**{k: u for k, (u, _) in (point_data or {}).items()}, **{k: u for k, (u, _) in (cell_data or {}).items()}}},
        sort_keys=True, default=str).replace("--", "- -") + " -->",
        '<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">', "<UnstructuredGrid>",
        f'<Piece NumberOfPoints="{n}" NumberOfCells="{c}">', "<Points>", '<DataArray type="Float64" NumberOfComponents="3" format="ascii">',
        _ascii(points), "</DataArray>", "</Points>", "<Cells>", '<DataArray type="Int64" Name="connectivity" format="ascii">',
        " ".join(str(int(x)) for x in cells.ravel()), "</DataArray>", '<DataArray type="Int64" Name="offsets" format="ascii">',
        " ".join(str(per * (i + 1)) for i in range(c)), "</DataArray>", '<DataArray type="UInt8" Name="types" format="ascii">',
        " ".join(str(_VTK_TYPE[ctype]) for _ in range(c)), "</DataArray>", "</Cells>"]

    def block(tag: str, data: Mapping[str, tuple[str, Any]] | None, count: int) -> None:
        if not data:
            return
        lines.append(f"<{tag}>")
        for name, (unit, values) in data.items():
            arr = np.asarray(values, dtype=float)
            if arr.shape[0] != count or not np.all(np.isfinite(arr)):
                raise InvalidScientificProblem(f"field {name!r} does not have {count} finite entries")
            comps = 1 if arr.ndim == 1 else arr.shape[1]
            if comps == 2:
                arr = np.hstack([arr, np.zeros((count, 1))])
                comps = 3
            safe = f"{name} [{unit}]".replace("&", "and").replace("<", "lt").replace('"', "'")
            lines.extend([f'<DataArray type="Float64" Name="{safe}" NumberOfComponents="{comps}" format="ascii">', _ascii(arr), "</DataArray>"])
        lines.append(f"</{tag}>")

    block("PointData", point_data, n)
    block("CellData", cell_data, c)
    lines += ["</Piece>", "</UnstructuredGrid>", "</VTKFile>", ""]
    return "\n".join(lines).encode("ascii")


def values_digest(values: Any) -> str:
    return hashlib.sha256(np.ascontiguousarray(np.asarray(values, dtype="<f8")).tobytes()).hexdigest()


def extrema(values: Any) -> tuple[float, float]:
    a = np.asarray(values, dtype=float)
    if a.size == 0 or not np.all(np.isfinite(a)):
        raise InvalidScientificProblem("extrema of an empty or non-finite field are refused")
    return float(a.min()), float(a.max())


def l2_norm(values: Any, weights: Any | None = None) -> float:
    """Weighted L2 norm; weights are cell measures / lumped node areas when the field is an integral quantity."""
    a = np.asarray(values, dtype=float)
    w = np.ones(a.shape[0]) if weights is None else np.asarray(weights, dtype=float)
    if w.shape[0] != a.shape[0] or np.any(w < 0):
        raise InvalidScientificProblem("norm weights must be non-negative and one per entry")
    sq = (a * a).sum(axis=1) if a.ndim == 2 else a * a
    return float(np.sqrt((sq * w).sum()))
