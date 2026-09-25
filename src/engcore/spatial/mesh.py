"""Tagged unstructured meshes: exact identity, frames, regions and boundaries.

Built on the Core's content-addressed mesh records rather than beside them:

* geometry/topology arrays are validated by
  :class:`~engcore.data.mesh.UnstructuredMeshData` (canonical metres, exact
  integer connectivity, in-range indices);
* the Core support is :class:`~engcore.scientific.fields.UnstructuredMesh`,
  whose fingerprint is computed from the coordinate/connectivity BYTES;
* this module adds what that record cannot say: which cells and boundary
  facets carry which physical tag, the region names bound to those tags, the
  coordinate frame, and the generator provenance.

:attr:`SpatialMesh.digest` folds the Core fingerprint together with the tag
arrays, facet arrays, group table and frame.  Caller-chosen names (mesh id,
file names) never participate: two identical geometries have one identity, and
an edited tag is a different mesh.  Regions carry that digest, so a region of
another mesh is refused rather than resolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re
from typing import Any, Mapping

import numpy as np

from ..data.mesh import UnstructuredMeshData
from ..data.store import InMemoryBulkStore
from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.fields import CellType, UnstructuredMesh

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


class SpatialRefusal(InvalidScientificProblem):
    """A spatial request that cannot be answered without inventing something."""


def _identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise SpatialRefusal(f"{label} must be a non-empty typed identifier")
    return text


def _bytes_digest(*arrays: np.ndarray) -> str:
    h = hashlib.sha256()
    for a in arrays:
        a = np.ascontiguousarray(a)
        h.update(str(a.dtype).encode() + str(a.shape).encode() + a.tobytes())
    return h.hexdigest()


@dataclass(frozen=True)
class CoordinateFrame:
    """The frame coordinates and vector/tensor components are expressed in."""

    frame_id: str
    dimension: int
    kind: str = "cartesian"
    length_unit: str = "meter"
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _identifier(self.frame_id, "frame_id"))
        if self.dimension not in (2, 3):
            raise SpatialRefusal("frame dimension must be 2 or 3")
        if self.kind != "cartesian":
            raise SpatialRefusal(f"unsupported frame kind {self.kind!r}; only cartesian is implemented")
        if self.length_unit != "meter":
            raise SpatialRefusal("mesh coordinates are canonical metres; the frame states that")

    def to_dict(self) -> dict[str, Any]:
        return {"frame_id": self.frame_id, "dimension": self.dimension, "kind": self.kind, "length_unit": self.length_unit}


class GroupKind(str, Enum):
    CELLS = "cells"      # a region of the domain
    FACETS = "facets"    # a boundary (or interface) made of facets


@dataclass(frozen=True, order=True)
class PhysicalGroup:
    name: str
    kind: GroupKind
    tag: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "group name"))
        object.__setattr__(self, "kind", GroupKind(self.kind))
        if isinstance(self.tag, bool) or not isinstance(self.tag, int) or self.tag < 1:
            raise SpatialRefusal("physical tags are positive integers (0 means untagged)")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind.value, "tag": self.tag}


@dataclass(frozen=True)
class MeshProvenance:
    """Which tool produced the arrays, with which options.  A tool, not an authority."""

    generator: str
    version: str
    options: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"generator": self.generator, "version": self.version, "options_digest": canonical_digest(dict(self.options)), "options": dict(self.options)}


@dataclass(frozen=True)
class SpatialRegion:
    """A named region/boundary bound to ONE mesh by its digest."""

    mesh_digest: str
    name: str
    kind: GroupKind
    tag: int

    def to_dict(self) -> dict[str, Any]:
        return {"mesh_digest": self.mesh_digest, "name": self.name, "kind": self.kind.value, "tag": self.tag}


_FACET_VERTICES = {CellType.TRIANGLE: 2, CellType.QUADRILATERAL: 2, CellType.TETRAHEDRON: 3, CellType.HEXAHEDRON: 4}


def _cell_facets(cell_type: CellType, cells: np.ndarray) -> np.ndarray:
    if cell_type in (CellType.TRIANGLE, CellType.QUADRILATERAL):
        n = cell_type.vertices
        pairs = [(i, (i + 1) % n) for i in range(n)]
        return np.concatenate([cells[:, [a, b]] for a, b in pairs])
    if cell_type is CellType.TETRAHEDRON:
        faces = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
        return np.concatenate([cells[:, list(f)] for f in faces])
    raise SpatialRefusal("facet extraction for hexahedra is not implemented")


class SpatialMesh:
    """An exact, tagged, framed mesh.  Immutable; identity is content-derived."""

    def __init__(
        self,
        *,
        coordinates: Any,
        cells: Any,
        cell_type: CellType,
        frame: CoordinateFrame,
        cell_tags: Any,
        facets: Any = None,
        facet_tags: Any = None,
        groups: tuple[PhysicalGroup, ...] = (),
        coordinate_unit: str = "meter",
        provenance: MeshProvenance | None = None,
    ) -> None:
        cell_type = CellType(cell_type)
        # Native-byte-order float64: providers (Gmsh, meshio) hand back explicit
        # little-endian buffers, which the Core bulk encoder rightly refuses to
        # reinterpret.  Values are unchanged; only the buffer format is normalized.
        coordinates = np.asarray(coordinates, dtype=np.float64)
        coordinates = np.ascontiguousarray(coordinates.astype(coordinates.dtype.newbyteorder("="), copy=True))
        data = UnstructuredMeshData("pending", cell_type, coordinates, cells, coordinate_unit)
        if not isinstance(frame, CoordinateFrame) or frame.dimension != cell_type.spatial_dimension:
            raise SpatialRefusal("mesh requires a CoordinateFrame of the cell type's spatial dimension")
        tags = np.array(cell_tags, dtype=np.int64, copy=True).reshape(-1)
        if tags.shape != (data.cell_count,) or np.any(tags < 0):
            raise SpatialRefusal(f"cell_tags must be {data.cell_count} non-negative integers")
        k = _FACET_VERTICES[cell_type]
        f = np.zeros((0, k), dtype=np.int64) if facets is None else np.array(facets, dtype=np.int64, copy=True)
        ft = np.zeros((0,), dtype=np.int64) if facet_tags is None else np.array(facet_tags, dtype=np.int64, copy=True).reshape(-1)
        if f.ndim != 2 or f.shape[1] != k or ft.shape != (f.shape[0],) or np.any(ft < 1):
            raise SpatialRefusal(f"facets must be (m, {k}) with m positive facet tags")
        if f.size and (np.any(f < 0) or np.any(f >= data.node_count)):
            raise SpatialRefusal("facet node index out of range")
        known = {tuple(sorted(r)) for r in _cell_facets(cell_type, data.connectivity).tolist()}
        for row in f.tolist():
            if tuple(sorted(row)) not in known:
                raise SpatialRefusal(f"declared facet {row} is not a facet of any cell")
        if f.size and len({tuple(sorted(r)) for r in f.tolist()}) != len(f):
            raise SpatialRefusal("a facet is declared twice; one facet cannot carry two tags")
        # canonical facet order: sort nodes within facet, then rows, so identity is order-independent
        if f.size:
            f = np.sort(f, axis=1)
            order = np.lexsort(tuple(f[:, i] for i in reversed(range(k))) + (ft,))
            f, ft = f[order], ft[order]
        groups = tuple(sorted(groups))
        if any(not isinstance(g, PhysicalGroup) for g in groups) or len({g.name for g in groups}) != len(groups):
            raise SpatialRefusal("physical groups must have unique names")
        if len({(g.kind, g.tag) for g in groups}) != len(groups):
            raise SpatialRefusal("two groups name the same tag of the same kind")
        for g in groups:
            present = tags if g.kind is GroupKind.CELLS else ft
            if not np.any(present == g.tag):
                raise SpatialRefusal(f"group {g.name!r} names tag {g.tag}, which no {g.kind.value} carries")
        core = data.store(InMemoryBulkStore())
        self._core_fingerprint = core.fingerprint()
        self._frame = frame
        self._groups = groups
        self._provenance = provenance
        self._digest = canonical_digest({
            "core_fingerprint": self._core_fingerprint,
            "cell_tags": _bytes_digest(tags), "facets": _bytes_digest(f, ft),
            "groups": [g.to_dict() for g in groups], "frame": frame.to_dict(),
        })
        self._data = UnstructuredMeshData(f"spatial-{self._digest[:24]}", cell_type, data.coordinates, data.connectivity)
        for arr in (tags, f, ft):
            arr.setflags(write=False)
        self._tags, self._facets, self._facet_tags = tags, f, ft

    # ---- identity -----------------------------------------------------------
    @property
    def digest(self) -> str:
        return self._digest

    @property
    def mesh_id(self) -> str:
        """Derived from content; never chosen by a caller."""
        return self._data.mesh_id

    @property
    def core_fingerprint(self) -> str:
        return self._core_fingerprint

    def core_support(self, store=None) -> UnstructuredMesh:
        """The Core support record (for FieldDefinition / FieldValue / FieldRecord)."""
        return self._data.store(store or InMemoryBulkStore())

    # ---- arrays -------------------------------------------------------------
    @property
    def coordinates(self) -> np.ndarray:
        return self._data.coordinates

    @property
    def cells(self) -> np.ndarray:
        return self._data.connectivity

    @property
    def cell_type(self) -> CellType:
        return self._data.cell_type

    @property
    def cell_tags(self) -> np.ndarray:
        return self._tags

    @property
    def facets(self) -> np.ndarray:
        return self._facets

    @property
    def facet_tags(self) -> np.ndarray:
        return self._facet_tags

    @property
    def frame(self) -> CoordinateFrame:
        return self._frame

    @property
    def groups(self) -> tuple[PhysicalGroup, ...]:
        return self._groups

    @property
    def provenance(self) -> MeshProvenance | None:
        return self._provenance

    @property
    def node_count(self) -> int:
        return self._data.node_count

    @property
    def cell_count(self) -> int:
        return self._data.cell_count

    def edges(self) -> np.ndarray:
        """Every unique cell edge (2D) / facet, sorted -- the EDGE location's sites."""
        all_f = np.sort(_cell_facets(self.cell_type, self.cells), axis=1)
        return np.unique(all_f, axis=0)

    def cell_measures(self) -> np.ndarray:
        """Area (2D) of every cell; triangles and convex quads."""
        x = self.coordinates
        c = self.cells
        if self.cell_type is CellType.TRIANGLE:
            a, b, d = x[c[:, 0]], x[c[:, 1]], x[c[:, 2]]
            return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (d[:, 1] - a[:, 1]) - (d[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
        if self.cell_type is CellType.QUADRILATERAL:
            p = x[c]
            return 0.5 * np.abs(np.sum(p[:, :, 0] * np.roll(p[:, :, 1], -1, axis=1) - np.roll(p[:, :, 0], -1, axis=1) * p[:, :, 1], axis=1))
        raise SpatialRefusal("cell measures are implemented for 2D cells only")

    # ---- regions ------------------------------------------------------------
    def region(self, name: str) -> SpatialRegion:
        for g in self._groups:
            if g.name == name:
                return SpatialRegion(self._digest, g.name, g.kind, g.tag)
        raise SpatialRefusal(f"mesh has no region/boundary named {name!r}")

    def _own(self, region: SpatialRegion) -> None:
        if not isinstance(region, SpatialRegion) or region.mesh_digest != self._digest:
            raise SpatialRefusal("region belongs to a different mesh; a tag of one mesh names nothing on another")
        if not any((g.name, g.kind, g.tag) == (region.name, region.kind, region.tag) for g in self._groups):
            raise SpatialRefusal(f"region {region.name!r} is not a declared group of this mesh; regions are obtained with mesh.region(name)")

    def cell_indices(self, region: SpatialRegion) -> np.ndarray:
        self._own(region)
        if region.kind is not GroupKind.CELLS:
            raise SpatialRefusal(f"{region.name!r} is a boundary, not a cell region")
        return np.flatnonzero(self._tags == region.tag)

    def facet_indices(self, region: SpatialRegion) -> np.ndarray:
        self._own(region)
        if region.kind is not GroupKind.FACETS:
            raise SpatialRefusal(f"{region.name!r} is a cell region, not a boundary")
        return np.flatnonzero(self._facet_tags == region.tag)

    def node_indices(self, region: SpatialRegion) -> np.ndarray:
        self._own(region)
        if region.kind is GroupKind.CELLS:
            return np.unique(self.cells[self.cell_indices(region)])
        return np.unique(self._facets[self.facet_indices(region)])

    # ---- serialization -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "spatial_mesh/1", "digest": self._digest, "core_fingerprint": self._core_fingerprint,
            "cell_type": self.cell_type.value, "frame": self._frame.to_dict(),
            "coordinates": self.coordinates.tolist(), "cells": self.cells.tolist(),
            "cell_tags": self._tags.tolist(), "facets": self._facets.tolist(), "facet_tags": self._facet_tags.tolist(),
            "groups": [g.to_dict() for g in self._groups],
            "provenance": None if self._provenance is None else self._provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "SpatialMesh":
        if p.get("schema") != "spatial_mesh/1":
            raise SpatialRefusal("unsupported spatial mesh schema")
        prov = p["provenance"]
        mesh = cls(
            coordinates=p["coordinates"], cells=p["cells"], cell_type=CellType(p["cell_type"]),
            frame=CoordinateFrame(p["frame"]["frame_id"], p["frame"]["dimension"], p["frame"]["kind"], p["frame"]["length_unit"]),
            cell_tags=p["cell_tags"], facets=p["facets"], facet_tags=p["facet_tags"],
            groups=tuple(PhysicalGroup(g["name"], g["kind"], g["tag"]) for g in p["groups"]),
            provenance=None if prov is None else MeshProvenance(prov["generator"], prov["version"], prov["options"]),
        )
        if mesh.digest != p["digest"]:
            raise SpatialRefusal("serialized mesh digest does not match its arrays")
        return mesh

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, SpatialMesh) and other.digest == self.digest

    def __hash__(self) -> int:
        return hash(self._digest)
