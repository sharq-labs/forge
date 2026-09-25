"""Unit-aware spatial fields, region material bindings and field mappings.

Node and cell fields convert losslessly to the Core
:class:`~engcore.data.field.FieldValue` / ``FieldRecord`` pipeline
(:meth:`SpatialField.to_core`), which remains the storage/summary authority.
This module adds what the Core field record deliberately left out: facet/edge
locations, rank with a coordinate-frame binding, discretization metadata and a
derivation label that keeps mapped/interpolated values distinguishable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

import numpy as np

from ..data.field import FieldValue
from ..materials import MaterialPropertySet, MaterialState, ResolvedProperty
from ..scenarios.timeline import canonical_digest
from ..scientific.fields import FieldDefinition, FieldLocation
from ..scientific.units.quantity import Quantity, is_ratio_scale, normalize_unit
from .mesh import GroupKind, SpatialMesh, SpatialRefusal, SpatialRegion, _bytes_digest, _identifier


class Location(str, Enum):
    NODE = "node"
    CELL = "cell"
    FACET = "facet"   # the mesh's declared (tagged) boundary facets
    EDGE = "edge"     # every unique cell edge (2D) / face (3D)


class Rank(str, Enum):
    SCALAR = "scalar"
    VECTOR = "vector"
    TENSOR = "tensor"


class Derivation(str, Enum):
    PRESCRIBED = "prescribed"      # declared by a caller / scenario
    COMPUTED = "computed"          # produced by a solver on this mesh
    RESOLVED = "resolved"          # resolved from material data per region
    MAPPED = "mapped"              # produced by a FieldMapping from another field
    ASSUMED = "assumed"


@dataclass(frozen=True)
class Discretization:
    family: str        # e.g. "lagrange", "dg"
    order: int
    continuity: str    # "C0" | "discontinuous"

    def __post_init__(self) -> None:
        if self.continuity not in ("C0", "discontinuous") or not isinstance(self.order, int) or self.order < 0:
            raise SpatialRefusal("discretization needs continuity C0|discontinuous and a non-negative integer order")

    def to_dict(self) -> dict[str, Any]:
        return {"family": self.family, "order": self.order, "continuity": self.continuity}


@dataclass(frozen=True)
class SpatialFieldDefinition:
    field_id: str
    quantity_id: str
    unit: str
    location: Location
    rank: Rank
    frame_id: str | None = None
    discretization: Discretization | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "field_id", _identifier(self.field_id, "field_id"))
        object.__setattr__(self, "quantity_id", _identifier(self.quantity_id, "quantity_id"))
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        object.__setattr__(self, "location", Location(self.location))
        object.__setattr__(self, "rank", Rank(self.rank))
        if self.rank is Rank.SCALAR and self.frame_id is not None:
            raise SpatialRefusal("a scalar field has no frame")
        if self.rank is not Rank.SCALAR and not self.frame_id:
            raise SpatialRefusal(f"a {self.rank.value} field must name the coordinate frame of its components")
        if self.rank is not Rank.SCALAR and not is_ratio_scale(self.unit):
            raise SpatialRefusal("vector/tensor components cannot use an affine unit")

    def components(self, dimension: int) -> int:
        return {Rank.SCALAR: 1, Rank.VECTOR: dimension, Rank.TENSOR: dimension * dimension}[self.rank]

    def to_dict(self) -> dict[str, Any]:
        return {"field_id": self.field_id, "quantity_id": self.quantity_id, "unit": self.unit, "location": self.location.value, "rank": self.rank.value,
                "frame_id": self.frame_id, "discretization": None if self.discretization is None else self.discretization.to_dict()}


def _sites(mesh: SpatialMesh, location: Location) -> int:
    return {Location.NODE: mesh.node_count, Location.CELL: mesh.cell_count, Location.FACET: len(mesh.facets), Location.EDGE: len(mesh.edges())}[location]


class SpatialField:
    """Values of one definition on one exact mesh.  Immutable; content-addressed."""

    def __init__(self, definition: SpatialFieldDefinition, mesh: SpatialMesh, values: Any, derivation: Derivation,
                 provenance: tuple[str, ...] = ()) -> None:
        if not isinstance(definition, SpatialFieldDefinition) or not isinstance(mesh, SpatialMesh):
            raise SpatialRefusal("a field needs a SpatialFieldDefinition and a SpatialMesh")
        if definition.frame_id is not None and definition.frame_id != mesh.frame.frame_id:
            raise SpatialRefusal(f"field components are in frame {definition.frame_id!r}; the mesh is in {mesh.frame.frame_id!r}")
        comps = definition.components(mesh.frame.dimension)
        n = _sites(mesh, definition.location)
        expected = (n,) if comps == 1 else (n, comps)
        arr = np.array(values, dtype=np.float64, copy=True)
        if arr.shape != expected:
            raise SpatialRefusal(f"field {definition.field_id!r} at {definition.location.value} expects shape {expected}, got {arr.shape}")
        if not np.all(np.isfinite(arr)):
            raise SpatialRefusal(f"field {definition.field_id!r} has non-finite values")
        arr.setflags(write=False)
        self.definition, self.mesh, self.values = definition, mesh, arr
        self.derivation = Derivation(derivation)
        self.provenance = tuple(sorted(str(p) for p in provenance))
        if self.derivation in (Derivation.MAPPED, Derivation.RESOLVED) and not self.provenance:
            raise SpatialRefusal(f"a {self.derivation.value} field must carry the digest(s) of what produced it")

    @property
    def digest(self) -> str:
        return canonical_digest({"definition": self.definition.to_dict(), "mesh": self.mesh.digest, "values": _bytes_digest(self.values),
                                 "derivation": self.derivation.value, "provenance": list(self.provenance)})

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "spatial_field/1", "classification": "field_values_not_evidence", "digest": self.digest,
                "definition": self.definition.to_dict(), "mesh_digest": self.mesh.digest, "values": self.values.tolist(),
                "derivation": self.derivation.value, "provenance": list(self.provenance)}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any], mesh: SpatialMesh) -> "SpatialField":
        if p.get("mesh_digest") != mesh.digest:
            raise SpatialRefusal("serialized field belongs to a different mesh")
        d = p["definition"]
        disc = d["discretization"]
        made = cls(SpatialFieldDefinition(d["field_id"], d["quantity_id"], d["unit"], d["location"], d["rank"], d["frame_id"],
                                          None if disc is None else Discretization(**disc)),
                   mesh, p["values"], p["derivation"], tuple(p["provenance"]))
        if made.digest != p["digest"]:
            raise SpatialRefusal("serialized field digest does not match its content")
        return made

    def to_core(self) -> FieldValue:
        """The Core FieldValue on the Core support (node/cell only)."""
        if self.definition.location not in (Location.NODE, Location.CELL):
            raise SpatialRefusal("the Core field record holds node and cell fields only")
        support = self.mesh.core_support()
        core_def = FieldDefinition(self.definition.field_id, self.definition.unit, support.mesh_id,
                                   FieldLocation(self.definition.location.value), self.definition.components(self.mesh.frame.dimension))
        return FieldValue(core_def, support, self.values)


# --------------------------------------------------------------------------
# Material binding
# --------------------------------------------------------------------------


class RegionMaterialMap:
    """Exact BIG 5 material states bound to cell regions of one mesh."""

    def __init__(self, mesh: SpatialMesh, bindings: tuple[tuple[SpatialRegion, MaterialState], ...]) -> None:
        self.mesh = mesh
        owner = np.full(mesh.cell_count, -1, dtype=np.int64)
        items = []
        for i, (region, state) in enumerate(bindings):
            if not isinstance(state, MaterialState):
                raise SpatialRefusal("a region binds a MaterialState (exact identity + declared conditions)")
            cells = mesh.cell_indices(region)  # refuses foreign meshes and boundaries
            if np.any(owner[cells] >= 0):
                raise SpatialRefusal(f"region {region.name!r} overlaps a region already bound to a material")
            owner[cells] = i
            items.append((region, state))
        self.bindings = tuple(items)
        self._owner = owner
        owner.setflags(write=False)

    def state_of_cell(self, cell: int) -> MaterialState | None:
        """None means UNKNOWN: no material is bound there, and none is assumed."""
        i = int(self._owner[cell])
        return None if i < 0 else self.bindings[i][1]

    @property
    def digest(self) -> str:
        return canonical_digest({"mesh": self.mesh.digest, "bindings": [[r.name, s.digest] for r, s in self.bindings]})

    def property_field(self, property_sets: Mapping[str, MaterialPropertySet], property_id: str, unit: str,
                       field_id: str) -> tuple[SpatialField, tuple[ResolvedProperty, ...]]:
        """Cell field of a resolved material property; refuses any unbound or unresolved cell."""
        if np.any(self._owner < 0):
            raise SpatialRefusal(f"{int(np.sum(self._owner < 0))} cell(s) have no bound material; the property is UNKNOWN there")
        resolved = []
        per_binding = []
        for region, state in self.bindings:
            props = property_sets.get(state.material.digest)
            if props is None:
                raise SpatialRefusal(f"no property set for the material of region {region.name!r}")
            r = props.resolve(property_id, state)
            if r.status != "known":
                raise SpatialRefusal(f"{property_id} is UNKNOWN in region {region.name!r}: {r.reason}")
            resolved.append(r)
            per_binding.append(r.value.value.magnitude_in(unit))
        values = np.array([per_binding[i] for i in self._owner])
        definition = SpatialFieldDefinition(field_id, property_id, unit, Location.CELL, Rank.SCALAR)
        field = SpatialField(definition, self.mesh, values, Derivation.RESOLVED, tuple(r.digest for r in resolved) + (self.digest,))
        return field, tuple(resolved)


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


class Conservation(str, Enum):
    #: Holds by construction for the stated interpolant; stated with that scope.
    EXACT_FOR_P1_INTERPOLANT = "exact_for_p1_interpolant"
    #: No conservation property; any integral difference is reported, not fixed.
    NOT_CONSERVATIVE = "not_conservative"


@dataclass(frozen=True)
class MappingRecord:
    method: str
    source_field: str
    source_mesh: str
    target_mesh: str
    conservation: Conservation
    source_integral: float | None
    target_integral: float | None
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "mapped_interpolation_not_measurement", "method": self.method, "source_field": self.source_field,
                "source_mesh": self.source_mesh, "target_mesh": self.target_mesh, "conservation": self.conservation.value,
                "source_integral": self.source_integral, "target_integral": self.target_integral, "integral_unit": self.unit}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def _p1_integral(field: SpatialField) -> float | None:
    if field.definition.location is not Location.NODE or field.definition.rank is not Rank.SCALAR:
        return None
    if not is_ratio_scale(field.definition.unit) or field.mesh.cell_type.value != "triangle":
        return None
    return float(np.sum(field.mesh.cell_measures() * field.values[field.mesh.cells].mean(axis=1)))


def node_to_cell_average(field: SpatialField) -> tuple[SpatialField, MappingRecord]:
    """P1 node values -> cell means.  Exact cell average of the P1 interpolant on triangles only."""
    d = field.definition
    if d.location is not Location.NODE:
        raise SpatialRefusal("node_to_cell_average needs a node field")
    if field.mesh.cell_type.value != "triangle":
        raise SpatialRefusal("the vertex mean is the exact P1 cell average only on triangles; not claimed elsewhere")
    values = field.values[field.mesh.cells].mean(axis=1)
    integral_src = _p1_integral(field)
    integral_tgt = None if integral_src is None else float(np.sum(field.mesh.cell_measures() * (values if values.ndim == 1 else 0)))
    record = MappingRecord("p1_vertex_mean", field.digest, field.mesh.digest, field.mesh.digest, Conservation.EXACT_FOR_P1_INTERPOLANT,
                           integral_src, integral_tgt, f"({d.unit}) * meter ** 2")
    out = SpatialField(SpatialFieldDefinition(d.field_id + ".cell", d.quantity_id, d.unit, Location.CELL, d.rank, d.frame_id,
                                              Discretization("lagrange", 0, "discontinuous")),
                       field.mesh, values, Derivation.MAPPED, (record.digest, field.digest))
    return out, record


def interpolate_p1_to_mesh(field: SpatialField, target: SpatialMesh, *, tolerance: float = 1e-12) -> tuple[SpatialField, MappingRecord]:
    """Evaluate a P1 node field of a triangle mesh at every node of ``target``.

    Refused: a different coordinate frame, a non-triangle source, and any
    target node outside the source mesh (no extrapolation).  NOT conservative;
    the P1 integrals of source and result are reported for inspection only.
    """
    d = field.definition
    src = field.mesh
    if d.location is not Location.NODE or src.cell_type.value != "triangle":
        raise SpatialRefusal("P1 interpolation needs a node field on a triangle mesh")
    if target.frame != src.frame:
        raise SpatialRefusal("source and target meshes are in different coordinate frames; no transformation is declared")
    x = src.coordinates
    tri = x[src.cells]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
    out = []
    outside = 0
    for p in target.coordinates:
        l1 = ((b[:, 0] - p[0]) * (c[:, 1] - p[1]) - (c[:, 0] - p[0]) * (b[:, 1] - p[1])) / det
        l2 = ((c[:, 0] - p[0]) * (a[:, 1] - p[1]) - (a[:, 0] - p[0]) * (c[:, 1] - p[1])) / det
        l3 = 1.0 - l1 - l2
        inside = np.flatnonzero((l1 >= -tolerance) & (l2 >= -tolerance) & (l3 >= -tolerance))
        if inside.size == 0:
            outside += 1
            continue
        k = int(inside[0])  # any containing triangle gives the same P1 value (continuity)
        w = np.array([l1[k], l2[k], l3[k]])
        out.append(np.tensordot(w, field.values[src.cells[k]], axes=1))
    if outside:
        raise SpatialRefusal(f"{outside} target node(s) lie outside the source mesh; extrapolation is not authorized")
    tf = SpatialField(SpatialFieldDefinition(d.field_id, d.quantity_id, d.unit, Location.NODE, d.rank, d.frame_id, d.discretization),
                      target, np.array(out), Derivation.PRESCRIBED)  # temporary, for the integral only
    record = MappingRecord("p1_barycentric_interpolation", field.digest, src.digest, target.digest, Conservation.NOT_CONSERVATIVE,
                           _p1_integral(field), _p1_integral(tf), f"({d.unit}) * meter ** 2")
    mapped = SpatialField(tf.definition, target, tf.values, Derivation.MAPPED, (record.digest, field.digest))
    return mapped, record
