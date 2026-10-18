"""Executable scalar interface declarations; domain laws and evidence stay outside."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..semantics import ConservedQuantity, QuantitySemantics, QuantityRole
from ..serialization import require_schema
from ..units.quantity import Quantity, dimensionality, is_ratio_scale
from .definition import FieldDefinition, FieldLocation
from .mesh import StructuredMesh
from .semantics import FieldKind, InterfaceConvention


class InterfaceRepresentation(str, Enum):
    NORMAL_DENSITY = "normal_density"
    INTEGRATED = "integrated"


class InterfaceRelation(str, Enum):
    CONTINUOUS_ORIENTED_FLUX = "continuous_oriented_flux"
    EQUAL_AND_OPPOSITE_OUTWARD = "equal_and_opposite_outward"


class InterfaceCoverage(str, Enum):
    FULL = "full"


class InterfaceMapping(str, Enum):
    COMMON_PLANE_RECTANGLES = "common_plane_rectangles"


def _dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


@dataclass(frozen=True)
class InterfaceTransfer:
    source: InterfaceConvention
    target: InterfaceConvention
    quantity: QuantitySemantics
    conserved_quantity: ConservedQuantity
    representation: InterfaceRepresentation
    relation: InterfaceRelation
    coverage: InterfaceCoverage
    method: InterfaceMapping
    plane_origin_m: tuple[float, float, float]
    u_axis: tuple[float, float, float]
    v_axis: tuple[float, float, float]

    def __post_init__(self) -> None:
        for name, enum in (("representation", InterfaceRepresentation), ("relation", InterfaceRelation),
                           ("coverage", InterfaceCoverage), ("method", InterfaceMapping)):
            object.__setattr__(self, name, enum(getattr(self, name)))
        if not isinstance(self.quantity, QuantitySemantics) or not isinstance(self.conserved_quantity, ConservedQuantity):
            raise InvalidScientificProblem("interface requires exact quantity and conserved measure meanings")
        for convention in (self.source, self.target):
            if not isinstance(convention, InterfaceConvention) or len(convention.normal) != 3:
                raise InvalidScientificProblem("surface flux requires explicit 3D normal and orientation conventions")
        if self.source.coordinate_frame != self.target.coordinate_frame:
            raise InvalidScientificProblem("unqualified interface frame projection")
        for name in ("plane_origin_m", "u_axis", "v_axis"):
            vector = tuple(float(x) for x in getattr(self, name))
            if len(vector) != 3 or not all(math.isfinite(x) for x in vector):
                raise InvalidScientificProblem("interface plane vectors must be finite 3-vectors")
            object.__setattr__(self, name, vector)
        if any(abs(_dot(axis, axis)-1) > 1e-12 for axis in (self.u_axis, self.v_axis)) or abs(_dot(self.u_axis, self.v_axis)) > 1e-12:
            raise InvalidScientificProblem("interface plane requires orthonormal parameter axes")
        u, v = self.u_axis, self.v_axis
        cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        if any(abs(abs(_dot(c.normal, cross))-1) > 1e-12 for c in (self.source, self.target)):
            raise InvalidScientificProblem("unqualified oblique interface normal projection")
        if self.relation is InterfaceRelation.EQUAL_AND_OPPOSITE_OUTWARD and _dot(self.source.normal, self.target.normal) > -1+1e-12:
            raise InvalidScientificProblem("equal-and-opposite outward flux requires opposing normals")
        if self.representation is InterfaceRepresentation.NORMAL_DENSITY:
            unit = (Quantity(1, self.quantity.unit) * Quantity(1, "m**2")).units
            if QuantityRole.DENSITY not in self.quantity.roles or self.quantity.conserved_quantity is not None:
                raise InvalidScientificProblem("normal density requires a declared density role and separate integrated measure")
        else:
            unit = self.quantity.unit
            if QuantityRole.INTEGRATED not in self.quantity.roles or self.quantity.conserved_quantity != self.conserved_quantity:
                raise InvalidScientificProblem("integrated interface quantity must name its exact conserved measure")
        if dimensionality(unit) != dimensionality(self.conserved_quantity.unit):
            raise InvalidScientificProblem("interface representation and conserved measure dimensions disagree")

    @property
    def sign(self) -> int:
        return self.source.orientation * self.target.orientation * (1 if _dot(self.source.normal, self.target.normal) > 0 else -1)

    def admit(self, source: FieldDefinition, source_mesh, target: FieldDefinition, target_mesh, mapping) -> None:
        from ..multiphysics.mapping import FieldMappingMethod, ExtrapolationPolicy
        if not all(isinstance(m, StructuredMesh) and m.spatial_dimension == 2 for m in (source_mesh, target_mesh)):
            raise InvalidScientificProblem("interface execution supports qualified structured planar rectangles only")
        if mapping is None or mapping.method not in (FieldMappingMethod.IDENTITY, FieldMappingMethod.CONSERVATIVE_CELL) or mapping.extrapolation is not ExtrapolationPolicy.REFUSE:
            raise InvalidScientificProblem("interface requires full-coverage identity or qualified conservative overlap")
        if mapping.method is FieldMappingMethod.IDENTITY and source_mesh.fingerprint() != target_mesh.fingerprint():
            raise InvalidScientificProblem("interface identity requires identical support")
        if mapping.relative_error_limit is not None and not mapping.verify_round_trip:
            raise InvalidScientificProblem("interface error limit requires roundtrip verification")
        kind = FieldKind.NORMAL_FLUX if self.representation is InterfaceRepresentation.NORMAL_DENSITY else FieldKind.INTERFACE
        for field, mesh, convention in ((source, source_mesh, self.source), (target, target_mesh, self.target)):
            field.require_support(mesh)
            if (field.semantics is None or field.semantics.kind is not kind
                    or field.semantics.quantity != self.quantity or field.semantics.interface != convention):
                raise InvalidScientificProblem("interface field meaning, kind or convention differs from executable contract")
            if field.components != 1 or field.location is not FieldLocation.CELL:
                raise InvalidScientificProblem("interface supports scalar normal CELL values; vector projection is unsupported")
            if not is_ratio_scale(field.unit):
                raise InvalidScientificProblem("interface flux requires ratio-scale units")
            if convention.support_id != mesh.mesh_id or convention.support_fingerprint != mesh.fingerprint():
                raise InvalidScientificProblem("interface support identity mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "interface_transfer/1", "source": self.source.to_dict(), "target": self.target.to_dict(),
                "quantity": self.quantity.to_dict(), "conserved_quantity": self.conserved_quantity.to_dict(),
                "representation": self.representation.value, "relation": self.relation.value,
                "coverage": self.coverage.value, "method": self.method.value, "plane_origin_m": list(self.plane_origin_m),
                "u_axis": list(self.u_axis), "v_axis": list(self.v_axis)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InterfaceTransfer":
        require_schema(payload, "interface_transfer/1")
        return cls(InterfaceConvention.from_dict(payload["source"]), InterfaceConvention.from_dict(payload["target"]),
                   QuantitySemantics.from_dict(payload["quantity"]), ConservedQuantity.from_dict(payload["conserved_quantity"]),
                   payload["representation"], payload["relation"], payload["coverage"], payload["method"],
                   tuple(payload["plane_origin_m"]), tuple(payload["u_axis"]), tuple(payload["v_axis"]))
