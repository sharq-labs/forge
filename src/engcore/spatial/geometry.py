"""Provider-neutral geometry: canonical identity of bodies, regions, boundaries and interfaces.

This module is the spatial layer's DESIGN-side counterpart to :mod:`.mesh`.
A :class:`SpatialMesh` says which cells carry which tag; a
:class:`GeometryModel` says what those tags MEAN before any mesh exists:

* bodies with a declared shape, placed in declared coordinate frames;
* regions (sets of bodies), boundaries (sets of named body features) and
  interfaces (the faces two bodies share);
* explicit topology relations derived from those declarations;
* domain roles carried by one entity without duplicating it (one outer shell
  can be a CFD wall, an FEA surface and a convective boundary at once);
* material assignment (an exact :class:`~engcore.materials.MaterialIdentity`)
  and solver-boundary assignment (a condition REFERENCE, never a value).

What this module refuses to know: what a car, drone, wing, motor or duct is.
Shapes are geometric primitives (rectangle, disk, box, cylinder) or an
imported provider file; anything product-shaped is built from them by a
higher layer or by an external CAD provider.

Identity rules
--------------
* Lengths are converted to canonical metres before they enter identity, so
  ``25 mm`` and ``0.025 m`` are one geometry.
* Provider-native identities -- a Gmsh ``(dim, tag)``, an OpenCASCADE shape
  index -- never appear in a :class:`GeometryModel`. They live only in a
  :class:`ProviderEntityMap`, which is a translation record bound to one
  provider version and one geometry digest.
* Feature names are LOCAL to a shape kind (``xmin`` of a box is the face whose
  local x is minimal). They are geometric statements, not provider tags, so
  the same model meshed by two providers names the same faces.

A geometry record is a declaration. It is not evidence that the declared
object exists, is manufacturable, or behaves as any model predicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Any, Iterable, Mapping

from ..materials.identity import MaterialIdentity, MaterialState
from ..scenarios.timeline import canonical_digest
from ..scientific.units.quantity import Quantity, dimensionality
from .mesh import GroupKind, SpatialMesh, SpatialRefusal

GEOMETRY_MODEL_SCHEMA = "engcore.spatial.geometry_model/1"
PROVIDER_ENTITY_MAP_SCHEMA = "engcore.spatial.provider_entity_map/1"
MESH_BINDING_SCHEMA = "engcore.spatial.mesh_binding/1"
GEOMETRY_RECEIPT_SCHEMA = "engcore.spatial.geometry_receipt/1"

#: The classification every provider-side geometry record carries.
TRANSLATION_CLASSIFICATION = "provider_translation_not_evidence"

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_LENGTH = dimensionality("m")
_ANGLE = dimensionality("rad")


class GeometryRefusal(SpatialRefusal):
    """A geometry declaration that cannot be honoured without inventing something."""


def _ident(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise GeometryRefusal(f"{label} must be a typed identifier ([A-Za-z][A-Za-z0-9_.-]*), got {value!r}")
    return text


def _finite(value: float, label: str) -> float:
    v = float(value)
    if not math.isfinite(v):
        raise GeometryRefusal(f"{label} must be finite")
    return 0.0 if v == 0.0 else v  # -0.0 and 0.0 are one canonical value


def length_m(value: Quantity, label: str, *, positive: bool = False) -> float:
    """A declared length in canonical metres.  A bare number has no unit and is refused."""
    if not isinstance(value, Quantity):
        raise GeometryRefusal(f"{label} must be a Quantity with a length unit; a bare number has no unit")
    if value.dimensionality != _LENGTH:
        raise GeometryRefusal(f"{label} is {value.units}; a length unit is required")
    v = _finite(value.magnitude_in("m"), label)
    if positive and not v > 0.0:
        raise GeometryRefusal(f"{label} must be > 0 m")
    return v


_ANGLE_UNITS = frozenset({"radian", "degree", "arcminute", "arcsecond", "turn", "revolution", "milliradian"})


def angle_rad(value: Quantity, label: str) -> float:
    """A declared angle in radians.  A plain dimensionless number is not an angle and is refused."""
    if not isinstance(value, Quantity) or value.dimensionality != _ANGLE or str(value.units) not in _ANGLE_UNITS:
        raise GeometryRefusal(f"{label} must be a Quantity in an angle unit (rad, degree)")
    try:
        return _finite(value.magnitude_in("rad"), label)
    except GeometryRefusal:
        raise
    except Exception as exc:  # a dimensionless value that is not an angle unit
        raise GeometryRefusal(f"{label} must be an angle: {exc}") from exc


def _clean(v: float) -> float:
    """Canonical float: exact zeros for round-off below 1e-15 so quarter turns are exact."""
    v = float(v)
    return 0.0 if abs(v) < 1e-15 else v


# --------------------------------------------------------------------------
# Transforms and frames
# --------------------------------------------------------------------------

_IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@dataclass(frozen=True)
class Transform:
    """A rigid placement: ``x_parent = R @ x_child + t``.  Canonical metres and a proper rotation."""

    translation_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[tuple[float, float, float], ...] = _IDENTITY

    def __post_init__(self) -> None:
        t = tuple(_clean(_finite(v, "translation")) for v in self.translation_m)
        r = tuple(tuple(_clean(_finite(v, "rotation")) for v in row) for row in self.rotation)
        if len(t) != 3 or len(r) != 3 or any(len(row) != 3 for row in r):
            raise GeometryRefusal("a transform has a 3-vector translation and a 3x3 rotation")
        for i in range(3):
            for j in range(3):
                dot = sum(r[i][k] * r[j][k] for k in range(3))
                if abs(dot - (1.0 if i == j else 0.0)) > 1e-9:
                    raise GeometryRefusal("rotation is not orthonormal; scaling or shear is not a rigid placement")
        det = (r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1]) - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
               + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0]))
        if abs(det - 1.0) > 1e-9:
            raise GeometryRefusal("rotation has determinant -1; a reflection is not a rigid placement")
        object.__setattr__(self, "translation_m", t)
        object.__setattr__(self, "rotation", r)

    @classmethod
    def from_quantities(cls, translation: Iterable[Quantity] = (), *, axis: Iterable[float] = (0.0, 0.0, 1.0),
                        angle: Quantity | None = None) -> "Transform":
        """Translation as length Quantities; rotation by ``angle`` about the (normalized) ``axis``."""
        tr = tuple(translation) or (Quantity(0.0, "m"),) * 3
        if len(tr) != 3:
            raise GeometryRefusal("translation needs three length components")
        t = tuple(length_m(q, f"translation[{i}]") for i, q in enumerate(tr))
        if angle is None:
            return cls(t, _IDENTITY)
        a = angle_rad(angle, "rotation angle")
        ax = tuple(float(v) for v in axis)
        n = math.sqrt(sum(v * v for v in ax))
        if len(ax) != 3 or not n > 0 or not math.isfinite(n):
            raise GeometryRefusal("rotation axis must be a non-zero finite 3-vector")
        x, y, z = (v / n for v in ax)
        c, s, C = math.cos(a), math.sin(a), 1.0 - math.cos(a)
        rot = ((c + x * x * C, x * y * C - z * s, x * z * C + y * s),
               (y * x * C + z * s, c + y * y * C, y * z * C - x * s),
               (z * x * C - y * s, z * y * C + x * s, c + z * z * C))
        return cls(t, rot)

    @property
    def is_identity(self) -> bool:
        return self.translation_m == (0.0, 0.0, 0.0) and self.rotation == _IDENTITY

    def apply(self, point: Iterable[float]) -> tuple[float, float, float]:
        p = tuple(float(v) for v in point)
        if len(p) == 2:
            p = (p[0], p[1], 0.0)
        r, t = self.rotation, self.translation_m
        return tuple(sum(r[i][k] * p[k] for k in range(3)) + t[i] for i in range(3))  # type: ignore[return-value]

    def rotate(self, vector: Iterable[float]) -> tuple[float, float, float]:
        v = tuple(float(x) for x in vector)
        r = self.rotation
        return tuple(sum(r[i][k] * v[k] for k in range(3)) for i in range(3))  # type: ignore[return-value]

    def compose(self, child: "Transform") -> "Transform":
        """``self`` places a frame in its parent; ``child`` places a sub-frame in that frame."""
        r1, r2 = self.rotation, child.rotation
        rot = tuple(tuple(sum(r1[i][k] * r2[k][j] for k in range(3)) for j in range(3)) for i in range(3))
        return Transform(self.apply(child.translation_m), rot)

    def inverse(self) -> "Transform":
        rt = tuple(tuple(self.rotation[j][i] for j in range(3)) for i in range(3))
        t = self.translation_m
        return Transform(tuple(-sum(rt[i][k] * t[k] for k in range(3)) for i in range(3)), rt)

    def to_dict(self) -> dict[str, Any]:
        return {"translation_m": list(self.translation_m), "rotation": [list(row) for row in self.rotation]}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "Transform":
        return cls(tuple(p["translation_m"]), tuple(tuple(row) for row in p["rotation"]))


@dataclass(frozen=True)
class FrameDefinition:
    """A named frame placed in its parent frame.  ``parent_id == ''`` marks the model root frame."""

    frame_id: str
    parent_id: str = ""
    transform: Transform = field(default_factory=Transform)
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _ident(self.frame_id, "frame_id"))
        if self.parent_id:
            object.__setattr__(self, "parent_id", _ident(self.parent_id, "parent frame id"))
            if self.parent_id == self.frame_id:
                raise GeometryRefusal(f"frame {self.frame_id!r} cannot be its own parent")
        elif not self.transform.is_identity:
            raise GeometryRefusal(f"root frame {self.frame_id!r} has nothing to be placed in; its transform must be identity")
        if not isinstance(self.transform, Transform):
            raise GeometryRefusal("frame transform must be a Transform")

    def to_dict(self) -> dict[str, Any]:
        return {"frame_id": self.frame_id, "parent_id": self.parent_id, "transform": self.transform.to_dict()}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "FrameDefinition":
        return cls(p["frame_id"], p.get("parent_id", ""), Transform.from_dict(p["transform"]), p.get("description", ""))


# --------------------------------------------------------------------------
# Shapes
# --------------------------------------------------------------------------


class ShapeKind(str, Enum):
    RECTANGLE = "rectangle"   # 2D, corner at local origin, extents (length along x, width along y)
    DISK = "disk"             # 2D, centre at local origin
    BOX = "box"               # 3D, corner at local origin, extents (length x, width y, height z)
    CYLINDER = "cylinder"     # 3D, base centre at local origin, axis along local z
    IMPORTED = "imported"     # a provider file (STEP/BREP); features declared by selectors


#: Required dimensions, topological dimension, and the canonical local feature names of each primitive.
SHAPE_TABLE: dict[ShapeKind, tuple[tuple[str, ...], int, tuple[str, ...]]] = {
    ShapeKind.RECTANGLE: (("length", "width"), 2, ("xmin", "xmax", "ymin", "ymax")),
    ShapeKind.DISK: (("radius",), 2, ("rim",)),
    ShapeKind.BOX: (("length", "width", "height"), 3, ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")),
    ShapeKind.CYLINDER: (("radius", "height"), 3, ("side", "bottom", "top")),
}

IMPORT_FORMATS = ("step", "brep")


@dataclass(frozen=True)
class FeatureSelector:
    """A named feature of an IMPORTED shape: every boundary entity inside a local box (metres).

    Imported files carry no canonical face names, so the caller declares where
    each named feature lies.  An empty or ambiguous selection is refused by the
    provider; a selector is never widened to find something.
    """

    name: str
    lower_m: tuple[float, float, float]
    upper_m: tuple[float, float, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "feature selector name"))
        lo = tuple(_finite(v, "selector bound") for v in self.lower_m)
        hi = tuple(_finite(v, "selector bound") for v in self.upper_m)
        if len(lo) != 3 or len(hi) != 3 or any(b < a for a, b in zip(lo, hi)):
            raise GeometryRefusal(f"selector {self.name!r} needs lower <= upper in three coordinates")
        object.__setattr__(self, "lower_m", lo)
        object.__setattr__(self, "upper_m", hi)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "lower_m": list(self.lower_m), "upper_m": list(self.upper_m)}


@dataclass(frozen=True)
class ImportedSource:
    """An external geometry file bound by content, format and DECLARED length unit.

    Units are never guessed: ``declared_length_unit`` is required, and a
    provider that can read the file's own unit must refuse a disagreement.
    """

    file_digest: str
    format: str
    declared_length_unit: str
    dimension: int = 3
    import_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", str(self.file_digest)):
            raise GeometryRefusal("an imported geometry is bound by the sha256 of its bytes")
        fmt = str(self.format).strip().lower()
        if fmt not in IMPORT_FORMATS:
            raise GeometryRefusal(f"import format {self.format!r} is not supported; supported: {IMPORT_FORMATS}")
        object.__setattr__(self, "format", fmt)
        unit = str(self.declared_length_unit or "").strip()
        if not unit:
            raise GeometryRefusal("imported geometry has no declared length unit; units are never guessed")
        if dimensionality(unit) != _LENGTH:
            raise GeometryRefusal(f"declared unit {unit!r} is not a length unit")
        object.__setattr__(self, "declared_length_unit", unit)
        if self.dimension not in (2, 3):
            raise GeometryRefusal("imported geometry dimension must be 2 or 3")
        object.__setattr__(self, "import_options", dict(self.import_options))

    @property
    def scale_to_m(self) -> float:
        return Quantity(1.0, self.declared_length_unit).magnitude_in("m")

    def to_dict(self) -> dict[str, Any]:
        return {"file_digest": self.file_digest, "format": self.format, "declared_length_unit": self.declared_length_unit,
                "scale_to_m": self.scale_to_m, "dimension": self.dimension, "import_options": dict(sorted(self.import_options.items()))}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "ImportedSource":
        return cls(p["file_digest"], p["format"], p["declared_length_unit"], p.get("dimension", 3), p.get("import_options", {}))


@dataclass(frozen=True)
class Shape:
    """A primitive with canonical-metre dimensions, or an imported file with declared selectors."""

    kind: ShapeKind
    dimensions_m: Mapping[str, float] = field(default_factory=dict)
    source: ImportedSource | None = None
    selectors: tuple[FeatureSelector, ...] = ()

    def __post_init__(self) -> None:
        kind = ShapeKind(self.kind)
        object.__setattr__(self, "kind", kind)
        dims = {str(k): _finite(v, f"{kind.value} {k}") for k, v in dict(self.dimensions_m).items()}
        if kind is ShapeKind.IMPORTED:
            if not isinstance(self.source, ImportedSource):
                raise GeometryRefusal("an imported shape needs its ImportedSource")
            if dims:
                raise GeometryRefusal("an imported shape's dimensions come from its file, not from declarations")
            sel = tuple(sorted(self.selectors, key=lambda s: s.name))
            if any(not isinstance(s, FeatureSelector) for s in sel) or len({s.name for s in sel}) != len(sel):
                raise GeometryRefusal("imported features need unique FeatureSelector names")
            object.__setattr__(self, "selectors", sel)
        else:
            if self.source is not None or self.selectors:
                raise GeometryRefusal("only an imported shape carries a source and selectors")
            required = SHAPE_TABLE[kind][0]
            if set(dims) != set(required):
                raise GeometryRefusal(f"{kind.value} needs exactly {required}; got {sorted(dims)}")
            if any(not v > 0 for v in dims.values()):
                raise GeometryRefusal(f"{kind.value} dimensions must be > 0 m")
        object.__setattr__(self, "dimensions_m", dict(sorted(dims.items())))

    @classmethod
    def rectangle(cls, length: Quantity, width: Quantity) -> "Shape":
        return cls(ShapeKind.RECTANGLE, {"length": length_m(length, "length", positive=True), "width": length_m(width, "width", positive=True)})

    @classmethod
    def disk(cls, radius: Quantity) -> "Shape":
        return cls(ShapeKind.DISK, {"radius": length_m(radius, "radius", positive=True)})

    @classmethod
    def box(cls, length: Quantity, width: Quantity, height: Quantity) -> "Shape":
        return cls(ShapeKind.BOX, {"length": length_m(length, "length", positive=True), "width": length_m(width, "width", positive=True),
                                   "height": length_m(height, "height", positive=True)})

    @classmethod
    def cylinder(cls, radius: Quantity, height: Quantity) -> "Shape":
        return cls(ShapeKind.CYLINDER, {"radius": length_m(radius, "radius", positive=True), "height": length_m(height, "height", positive=True)})

    @classmethod
    def imported(cls, source: ImportedSource, selectors: Iterable[FeatureSelector] = ()) -> "Shape":
        return cls(ShapeKind.IMPORTED, {}, source, tuple(selectors))

    @property
    def dimension(self) -> int:
        return self.source.dimension if self.kind is ShapeKind.IMPORTED else SHAPE_TABLE[self.kind][1]

    @property
    def features(self) -> tuple[str, ...]:
        if self.kind is ShapeKind.IMPORTED:
            return tuple(s.name for s in self.selectors)
        return SHAPE_TABLE[self.kind][2]

    def nominal_measure_m(self) -> float | None:
        """Exact area (2D, m^2) or volume (3D, m^3) of a primitive; None for an imported shape (unknown, not zero)."""
        d = self.dimensions_m
        if self.kind is ShapeKind.RECTANGLE:
            return d["length"] * d["width"]
        if self.kind is ShapeKind.DISK:
            return math.pi * d["radius"] ** 2
        if self.kind is ShapeKind.BOX:
            return d["length"] * d["width"] * d["height"]
        if self.kind is ShapeKind.CYLINDER:
            return math.pi * d["radius"] ** 2 * d["height"]
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "dimensions_m": dict(self.dimensions_m),
                "source": None if self.source is None else self.source.to_dict(),
                "selectors": [s.to_dict() for s in self.selectors]}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "Shape":
        src = p.get("source")
        return cls(ShapeKind(p["kind"]), p.get("dimensions_m", {}), None if src is None else ImportedSource.from_dict(src),
                   tuple(FeatureSelector(s["name"], tuple(s["lower_m"]), tuple(s["upper_m"])) for s in p.get("selectors", ())))


# --------------------------------------------------------------------------
# Bodies, regions, boundaries, interfaces
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Body:
    """One solid (3D) or sheet (2D) in a declared frame.

    ``part_id`` is the assembly-compatible identity: the component/part this
    body realizes (see :mod:`engcore.systems.assembly`).  ``void`` marks a
    tool body: it is subtracted from the bodies that list it in ``cutouts``
    and is never meshed.
    """

    body_id: str
    shape: Shape
    frame_id: str
    placement: Transform = field(default_factory=Transform)
    part_id: str = ""
    void: bool = False
    cutouts: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_id", _ident(self.body_id, "body_id"))
        object.__setattr__(self, "frame_id", _ident(self.frame_id, "body frame_id"))
        if not isinstance(self.shape, Shape) or not isinstance(self.placement, Transform):
            raise GeometryRefusal("a body needs a Shape and a Transform placement")
        if self.part_id:
            object.__setattr__(self, "part_id", _ident(self.part_id, "part_id"))
        cut = tuple(sorted(_ident(c, "cutout body id") for c in self.cutouts))
        if len(set(cut)) != len(cut) or self.body_id in cut:
            raise GeometryRefusal(f"body {self.body_id!r} cutouts must be unique other bodies")
        if self.void and cut:
            raise GeometryRefusal("a void (tool) body cannot itself have cutouts")
        if self.shape.dimension == 2:
            r, t = self.placement.rotation, self.placement.translation_m
            if t[2] != 0.0 or r[2] != (0.0, 0.0, 1.0) or r[0][2] != 0.0 or r[1][2] != 0.0:
                raise GeometryRefusal(f"2D body {self.body_id!r} may only translate in-plane and rotate about z")
        object.__setattr__(self, "cutouts", cut)

    @property
    def dimension(self) -> int:
        return self.shape.dimension

    def to_dict(self) -> dict[str, Any]:
        return {"body_id": self.body_id, "shape": self.shape.to_dict(), "frame_id": self.frame_id, "placement": self.placement.to_dict(),
                "part_id": self.part_id, "void": self.void, "cutouts": list(self.cutouts)}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "Body":
        return cls(p["body_id"], Shape.from_dict(p["shape"]), p["frame_id"], Transform.from_dict(p["placement"]),
                   p.get("part_id", ""), bool(p.get("void", False)), tuple(p.get("cutouts", ())), p.get("description", ""))


@dataclass(frozen=True, order=True)
class FeatureRef:
    """A named local feature of a body (a face in 3D, an edge in 2D)."""

    body_id: str
    feature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_id", _ident(self.body_id, "feature body_id"))
        object.__setattr__(self, "feature", _ident(self.feature, "feature name"))

    @property
    def entity_id(self) -> str:
        return f"feature:{self.body_id}/{self.feature}"

    def to_dict(self) -> dict[str, Any]:
        return {"body_id": self.body_id, "feature": self.feature}


@dataclass(frozen=True)
class Region:
    """A named set of (non-void) bodies: the cells a mesh will tag with this name."""

    name: str
    bodies: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "region name"))
        b = tuple(sorted(_ident(x, "region body") for x in self.bodies))
        if not b or len(set(b)) != len(b):
            raise GeometryRefusal(f"region {self.name!r} needs unique bodies")
        object.__setattr__(self, "bodies", b)

    @property
    def entity_id(self) -> str:
        return f"region:{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "bodies": list(self.bodies)}


@dataclass(frozen=True)
class Boundary:
    """A named set of body features: the facets a mesh will tag with this name."""

    name: str
    features: tuple[FeatureRef, ...]
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "boundary name"))
        f = tuple(sorted(self.features))
        if not f or any(not isinstance(x, FeatureRef) for x in f) or len(set(f)) != len(f):
            raise GeometryRefusal(f"boundary {self.name!r} needs unique FeatureRef members")
        object.__setattr__(self, "features", f)

    @property
    def entity_id(self) -> str:
        return f"boundary:{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "features": [x.to_dict() for x in self.features]}


@dataclass(frozen=True)
class Interface:
    """The faces two bodies share.  Which faces those are is a provider fact, checked, never assumed."""

    name: str
    body_a: str
    body_b: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "interface name"))
        a, b = sorted((_ident(self.body_a, "interface body"), _ident(self.body_b, "interface body")))
        if a == b:
            raise GeometryRefusal(f"interface {self.name!r} must join two different bodies")
        object.__setattr__(self, "body_a", a)
        object.__setattr__(self, "body_b", b)

    @property
    def entity_id(self) -> str:
        return f"interface:{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "body_a": self.body_a, "body_b": self.body_b}


# --------------------------------------------------------------------------
# Roles and bindings
# --------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class RoleAssignment:
    """One domain role carried by one canonical entity.  An entity may carry many (one per domain)."""

    entity_id: str
    domain: str
    role: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"(region|boundary|interface|body|feature):[A-Za-z][A-Za-z0-9_./-]*", str(self.entity_id)):
            raise GeometryRefusal(f"role target {self.entity_id!r} is not a canonical entity id")
        object.__setattr__(self, "domain", _ident(self.domain, "role domain"))
        object.__setattr__(self, "role", _ident(self.role, "role"))

    def to_dict(self) -> dict[str, Any]:
        return {"entity_id": self.entity_id, "domain": self.domain, "role": self.role}


@dataclass(frozen=True)
class MaterialBinding:
    """An exact material bound to a region.  The state (conditions) is optional; nothing is defaulted."""

    region: str
    material: MaterialIdentity
    state: MaterialState | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "region", _ident(self.region, "material binding region"))
        if not isinstance(self.material, MaterialIdentity):
            raise GeometryRefusal("a material binding names an exact MaterialIdentity")
        if self.state is not None:
            if not isinstance(self.state, MaterialState):
                raise GeometryRefusal("material binding state must be a MaterialState")
            if self.state.material != self.material:
                raise GeometryRefusal(f"region {self.region!r}: the bound state is of another material")

    def to_dict(self) -> dict[str, Any]:
        return {"region": self.region, "material_digest": self.material.digest, "material": self.material.to_dict(),
                "state_digest": None if self.state is None else self.state.digest}


@dataclass(frozen=True, order=True)
class BoundaryBinding:
    """A solver-boundary assignment: which condition KIND applies on a boundary, and where its value lives.

    ``condition_ref`` names the record that carries the sourced value (a
    ``SourcedQuantity``, an environment channel, a coupling port).  This record
    never carries a value, so a boundary cannot acquire a default here.
    """

    boundary: str
    domain: str
    condition_kind: str
    condition_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "boundary", _ident(self.boundary, "bound boundary"))
        object.__setattr__(self, "domain", _ident(self.domain, "boundary binding domain"))
        object.__setattr__(self, "condition_kind", _ident(self.condition_kind, "condition kind"))
        ref = str(self.condition_ref or "").strip()
        if not ref:
            raise GeometryRefusal(f"boundary {self.boundary!r} ({self.domain}) names no condition record; a condition is never implied")
        object.__setattr__(self, "condition_ref", ref)

    def to_dict(self) -> dict[str, Any]:
        return {"boundary": self.boundary, "domain": self.domain, "condition_kind": self.condition_kind, "condition_ref": self.condition_ref}


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------


class RelationKind(str, Enum):
    FRAME_PARENT = "frame_parent"          # frame -> parent frame
    PLACED_IN = "placed_in"                # body -> frame
    BOUNDED_BY = "bounded_by"              # body -> its feature
    SUBTRACTS = "subtracts"                # body -> void tool body
    REGION_CONTAINS = "region_contains"    # region -> body
    BOUNDARY_CONTAINS = "boundary_contains"  # boundary -> feature
    INTERFACE_JOINS = "interface_joins"    # interface -> body
    REALIZES_PART = "realizes_part"        # body -> part id


@dataclass(frozen=True, order=True)
class TopologyRelation:
    kind: str
    source: str
    target: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "source": self.source, "target": self.target}


@dataclass(frozen=True)
class GeometryEntity:
    """A canonical geometry entity: identity, topological dimension, and what declares it."""

    entity_id: str
    dimension: int
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {"entity_id": self.entity_id, "dimension": self.dimension, "kind": self.kind}


@dataclass(frozen=True)
class GeometryModel:
    """Immutable, provider-neutral geometry declaration with content-derived identity."""

    model_id: str
    version: str
    dimension: int
    frames: tuple[FrameDefinition, ...]
    bodies: tuple[Body, ...]
    regions: tuple[Region, ...] = ()
    boundaries: tuple[Boundary, ...] = ()
    interfaces: tuple[Interface, ...] = ()
    roles: tuple[RoleAssignment, ...] = ()
    materials: tuple[MaterialBinding, ...] = ()
    boundary_bindings: tuple[BoundaryBinding, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _ident(self.model_id, "model_id"))
        version = str(self.version).strip()
        if not version:
            raise GeometryRefusal("geometry model requires a version")
        object.__setattr__(self, "version", version)
        if self.dimension not in (2, 3):
            raise GeometryRefusal("geometry dimension must be 2 or 3")
        frames = self._unique("frames", self.frames, FrameDefinition, lambda f: f.frame_id)
        roots = [f for f in frames if not f.parent_id]
        if len(roots) != 1:
            raise GeometryRefusal(f"a geometry model has exactly one root frame; found {len(roots)}")
        fmap = {f.frame_id: f for f in frames}
        for f in frames:
            seen = {f.frame_id}
            cur = f
            while cur.parent_id:
                if cur.parent_id not in fmap:
                    raise GeometryRefusal(f"frame {cur.frame_id!r} names unknown parent {cur.parent_id!r}")
                if cur.parent_id in seen:
                    raise GeometryRefusal("frame tree contains a cycle")
                seen.add(cur.parent_id)
                cur = fmap[cur.parent_id]
        bodies = self._unique("bodies", self.bodies, Body, lambda b: b.body_id)
        if not bodies:
            raise GeometryRefusal("a geometry model needs at least one body")
        bmap = {b.body_id: b for b in bodies}
        for b in bodies:
            if b.frame_id not in fmap:
                raise GeometryRefusal(f"body {b.body_id!r} is placed in unknown frame {b.frame_id!r}")
            if b.dimension != self.dimension:
                raise GeometryRefusal(f"body {b.body_id!r} is {b.dimension}D in a {self.dimension}D model; mixed dimensions are refused")
            for c in b.cutouts:
                if c not in bmap or not bmap[c].void:
                    raise GeometryRefusal(f"body {b.body_id!r} cuts {c!r}, which is not a declared void body")
        if all(b.void for b in bodies):
            raise GeometryRefusal("every body is a void tool body; there is nothing to mesh")
        regions = self._unique("regions", self.regions, Region, lambda r: r.name)
        boundaries = self._unique("boundaries", self.boundaries, Boundary, lambda r: r.name)
        interfaces = self._unique("interfaces", self.interfaces, Interface, lambda r: r.name)
        names = [x.name for x in (*regions, *boundaries, *interfaces)]
        if len(names) != len(set(names)):
            raise GeometryRefusal("region, boundary and interface names share one namespace and must be unique")
        for r in regions:
            for b in r.bodies:
                if b not in bmap or bmap[b].void:
                    raise GeometryRefusal(f"region {r.name!r} names {b!r}, which is not a meshed body")
        for bd in boundaries:
            for f in bd.features:
                if f.body_id not in bmap:
                    raise GeometryRefusal(f"boundary {bd.name!r} names unknown body {f.body_id!r}")
                if f.feature not in bmap[f.body_id].shape.features:
                    raise GeometryRefusal(f"boundary {bd.name!r}: {bmap[f.body_id].shape.kind.value} {f.body_id!r} has no feature "
                                          f"{f.feature!r} (features: {bmap[f.body_id].shape.features})")
        for itf in interfaces:
            for b in (itf.body_a, itf.body_b):
                if b not in bmap or bmap[b].void:
                    raise GeometryRefusal(f"interface {itf.name!r} names {b!r}, which is not a meshed body")
        roles = tuple(sorted(self.roles))
        if any(not isinstance(r, RoleAssignment) for r in roles):
            raise GeometryRefusal("roles must be RoleAssignment records")
        if len({(r.entity_id, r.domain) for r in roles}) != len(roles):
            raise GeometryRefusal("an entity carries at most one role per domain")
        known = {e.entity_id for e in self._entities(bodies, regions, boundaries, interfaces)}
        for r in roles:
            if r.entity_id not in known:
                raise GeometryRefusal(f"role {r.domain}:{r.role} targets unknown entity {r.entity_id!r}")
        materials = self._unique("materials", self.materials, MaterialBinding, lambda m: m.region)
        rmap = {r.name: r for r in regions}
        owner: dict[str, str] = {}
        for m in materials:
            if m.region not in rmap:
                raise GeometryRefusal(f"material bound to unknown region {m.region!r}")
            for b in rmap[m.region].bodies:
                prev = owner.get(b)
                if prev is not None and prev != m.material.digest:
                    raise GeometryRefusal(f"body {b!r} is bound to two different materials through overlapping regions")
                owner[b] = m.material.digest
        bbs = tuple(sorted(self.boundary_bindings))
        if any(not isinstance(x, BoundaryBinding) for x in bbs) or len({(x.boundary, x.domain) for x in bbs}) != len(bbs):
            raise GeometryRefusal("boundary bindings must be unique per (boundary, domain)")
        bnames = {b.name for b in boundaries} | {i.name for i in interfaces}
        for x in bbs:
            if x.boundary not in bnames:
                raise GeometryRefusal(f"boundary binding names unknown boundary/interface {x.boundary!r}")
        object.__setattr__(self, "frames", frames)
        object.__setattr__(self, "bodies", bodies)
        object.__setattr__(self, "regions", regions)
        object.__setattr__(self, "boundaries", boundaries)
        object.__setattr__(self, "interfaces", interfaces)
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "materials", materials)
        object.__setattr__(self, "boundary_bindings", bbs)

    @staticmethod
    def _unique(label: str, values: Iterable[Any], typ: type, key) -> tuple[Any, ...]:
        items = tuple(values)
        if any(not isinstance(x, typ) for x in items):
            raise GeometryRefusal(f"{label} must be {typ.__name__} records")
        if len({key(x) for x in items}) != len(items):
            raise GeometryRefusal(f"{label} identities must be unique")
        return tuple(sorted(items, key=key))

    # ---- derived structure ------------------------------------------------
    @staticmethod
    def _entities(bodies, regions, boundaries, interfaces) -> tuple[GeometryEntity, ...]:
        out = []
        for b in bodies:
            d = b.dimension
            out.append(GeometryEntity(f"body:{b.body_id}", d, "void_body" if b.void else "body"))
            out.extend(GeometryEntity(FeatureRef(b.body_id, f).entity_id, d - 1, "feature") for f in b.shape.features)
        if bodies:
            d = bodies[0].dimension
            out.extend(GeometryEntity(r.entity_id, d, "region") for r in regions)
            out.extend(GeometryEntity(x.entity_id, d - 1, "boundary") for x in boundaries)
            out.extend(GeometryEntity(x.entity_id, d - 1, "interface") for x in interfaces)
        return tuple(sorted(out, key=lambda e: e.entity_id))

    def entities(self) -> tuple[GeometryEntity, ...]:
        return self._entities(self.bodies, self.regions, self.boundaries, self.interfaces)

    def relations(self) -> tuple[TopologyRelation, ...]:
        """Every topology relation the declarations imply, in canonical order."""
        rel = []
        for f in self.frames:
            if f.parent_id:
                rel.append(TopologyRelation(RelationKind.FRAME_PARENT.value, f"frame:{f.frame_id}", f"frame:{f.parent_id}"))
        for b in self.bodies:
            rel.append(TopologyRelation(RelationKind.PLACED_IN.value, f"body:{b.body_id}", f"frame:{b.frame_id}"))
            rel.extend(TopologyRelation(RelationKind.BOUNDED_BY.value, f"body:{b.body_id}", FeatureRef(b.body_id, f).entity_id)
                       for f in b.shape.features)
            rel.extend(TopologyRelation(RelationKind.SUBTRACTS.value, f"body:{b.body_id}", f"body:{c}") for c in b.cutouts)
            if b.part_id:
                rel.append(TopologyRelation(RelationKind.REALIZES_PART.value, f"body:{b.body_id}", f"part:{b.part_id}"))
        for r in self.regions:
            rel.extend(TopologyRelation(RelationKind.REGION_CONTAINS.value, r.entity_id, f"body:{b}") for b in r.bodies)
        for x in self.boundaries:
            rel.extend(TopologyRelation(RelationKind.BOUNDARY_CONTAINS.value, x.entity_id, f.entity_id) for f in x.features)
        for i in self.interfaces:
            rel.extend(TopologyRelation(RelationKind.INTERFACE_JOINS.value, i.entity_id, f"body:{b}") for b in (i.body_a, i.body_b))
        return tuple(sorted(rel))

    def body(self, body_id: str) -> Body:
        for b in self.bodies:
            if b.body_id == body_id:
                return b
        raise GeometryRefusal(f"geometry has no body {body_id!r}")

    def region(self, name: str) -> Region:
        for r in self.regions:
            if r.name == name:
                return r
        raise GeometryRefusal(f"geometry has no region {name!r}")

    def roles_of(self, entity_id: str) -> dict[str, str]:
        return {r.domain: r.role for r in self.roles if r.entity_id == entity_id}

    def entities_with_role(self, domain: str, role: str) -> tuple[str, ...]:
        return tuple(r.entity_id for r in self.roles if r.domain == domain and r.role == role)

    def frame_to_root(self, frame_id: str) -> Transform:
        """Placement of ``frame_id`` in the root frame (composed down the frame tree)."""
        fmap = {f.frame_id: f for f in self.frames}
        if frame_id not in fmap:
            raise GeometryRefusal(f"unknown frame {frame_id!r}")
        chain = []
        cur = fmap[frame_id]
        while cur.parent_id:
            chain.append(cur.transform)
            cur = fmap[cur.parent_id]
        out = Transform()
        for t in reversed(chain):
            out = out.compose(t)
        return out

    def body_to_root(self, body_id: str) -> Transform:
        b = self.body(body_id)
        return self.frame_to_root(b.frame_id).compose(b.placement)

    @property
    def root_frame(self) -> str:
        return next(f.frame_id for f in self.frames if not f.parent_id)

    def meshed_bodies(self) -> tuple[Body, ...]:
        return tuple(b for b in self.bodies if not b.void)

    def unbound_material_bodies(self) -> tuple[str, ...]:
        """Meshed bodies with no material: UNKNOWN material, reported, never defaulted."""
        bound = {b for m in self.materials for b in self.region(m.region).bodies}
        return tuple(b.body_id for b in self.meshed_bodies() if b.body_id not in bound)

    def material_of_body(self, body_id: str) -> MaterialBinding | None:
        for m in self.materials:
            if body_id in self.region(m.region).bodies:
                return m
        return None

    # ---- identity and serialization ---------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GEOMETRY_MODEL_SCHEMA, "model_id": self.model_id, "version": self.version, "dimension": self.dimension,
            "length_unit": "meter",
            "frames": [f.to_dict() for f in self.frames], "bodies": [b.to_dict() for b in self.bodies],
            "regions": [r.to_dict() for r in self.regions], "boundaries": [b.to_dict() for b in self.boundaries],
            "interfaces": [i.to_dict() for i in self.interfaces], "roles": [r.to_dict() for r in self.roles],
            "materials": [m.to_dict() for m in self.materials], "boundary_bindings": [b.to_dict() for b in self.boundary_bindings],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def shape_digest(self) -> str:
        """Identity of the SHAPE alone (frames + bodies): what a mesh generator consumes.

        Renaming a region or binding a different material changes ``digest``
        but not ``shape_digest``, so a mesh of the same shape can be reused
        only through an explicit :class:`MeshBinding` to the new model.
        """
        return canonical_digest({"dimension": self.dimension, "frames": [f.to_dict() for f in self.frames],
                                 "bodies": [b.to_dict() for b in self.bodies]})

    def serialize(self) -> dict[str, Any]:
        """``to_dict`` plus the digest, for storage.  Material states are carried separately by their owners."""
        payload = self.to_dict()
        payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, p: Mapping[str, Any], *, material_states: Mapping[str, MaterialState] | None = None) -> "GeometryModel":
        """Rebuild a model; ``material_states`` maps state digests to states when bindings carry one."""
        if p.get("schema") != GEOMETRY_MODEL_SCHEMA:
            raise GeometryRefusal("unsupported geometry model schema")
        if p.get("length_unit", "meter") != "meter":
            raise GeometryRefusal("serialized geometry lengths are canonical metres")
        states = dict(material_states or {})
        mats = []
        for m in p.get("materials", ()):
            ident = MaterialIdentity.from_dict(m["material"])
            if ident.digest != m["material_digest"]:
                raise GeometryRefusal("serialized material identity does not match its digest")
            sd = m.get("state_digest")
            if sd is not None and sd not in states:
                raise GeometryRefusal(f"material state {sd[:12]} of region {m['region']!r} was not supplied; it is not reconstructed")
            mats.append(MaterialBinding(m["region"], ident, states.get(sd) if sd else None))
        model = cls(
            p["model_id"], p["version"], p["dimension"],
            tuple(FrameDefinition.from_dict(f) for f in p["frames"]), tuple(Body.from_dict(b) for b in p["bodies"]),
            tuple(Region(r["name"], tuple(r["bodies"])) for r in p.get("regions", ())),
            tuple(Boundary(b["name"], tuple(FeatureRef(f["body_id"], f["feature"]) for f in b["features"])) for b in p.get("boundaries", ())),
            tuple(Interface(i["name"], i["body_a"], i["body_b"]) for i in p.get("interfaces", ())),
            tuple(RoleAssignment(r["entity_id"], r["domain"], r["role"]) for r in p.get("roles", ())),
            tuple(mats),
            tuple(BoundaryBinding(b["boundary"], b["domain"], b["condition_kind"], b["condition_ref"]) for b in p.get("boundary_bindings", ())),
        )
        if "digest" in p and p["digest"] != model.digest:
            raise GeometryRefusal("serialized geometry digest does not match its content")
        return model

    def __hash__(self) -> int:
        return hash(self.digest)


# --------------------------------------------------------------------------
# Provider translation records
# --------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class EntityMapping:
    """One canonical entity and the provider entities that realize it, as ``(dim, tag)`` pairs."""

    forge_entity: str
    provider_entities: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        ents = tuple(sorted((int(d), int(t)) for d, t in self.provider_entities))
        if not ents or len(set(ents)) != len(ents):
            raise GeometryRefusal(f"{self.forge_entity!r} maps to no (or duplicate) provider entities; an empty mapping is refused")
        object.__setattr__(self, "provider_entities", ents)

    def to_dict(self) -> dict[str, Any]:
        return {"forge_entity": self.forge_entity, "provider_entities": [list(x) for x in self.provider_entities]}


@dataclass(frozen=True)
class ProviderEntityMap:
    """How one provider version realized one geometry's canonical entities.  A translation detail.

    Provider tags are meaningful only inside this record: another provider,
    another version or another geometry gets another map, and nothing outside
    the provider adapter reads a tag as identity.
    """

    provider_id: str
    provider_version: str
    geometry_digest: str
    mappings: tuple[EntityMapping, ...]

    def __post_init__(self) -> None:
        m = tuple(sorted(self.mappings))
        if len({x.forge_entity for x in m}) != len(m):
            raise GeometryRefusal("each canonical entity is mapped once")
        object.__setattr__(self, "mappings", m)

    def provider_entities_of(self, forge_entity: str) -> tuple[tuple[int, int], ...]:
        for x in self.mappings:
            if x.forge_entity == forge_entity:
                return x.provider_entities
        raise GeometryRefusal(f"no provider entity realizes {forge_entity!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PROVIDER_ENTITY_MAP_SCHEMA, "classification": TRANSLATION_CLASSIFICATION, "provider_id": self.provider_id,
                "provider_version": self.provider_version, "geometry_digest": self.geometry_digest,
                "mappings": [x.to_dict() for x in self.mappings]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class GeometryReceipt:
    """What a geometry/mesh provider did: inputs and outputs by digest, options, provider identity."""

    provider_id: str
    provider_version: str
    operation: str
    input_digests: Mapping[str, str]
    output_digests: Mapping[str, str]
    options: Mapping[str, Any] = field(default_factory=dict)
    provider_digest: str = ""

    def __post_init__(self) -> None:
        for label in ("provider_id", "provider_version", "operation"):
            if not str(getattr(self, label) or "").strip():
                raise GeometryRefusal(f"geometry receipt requires {label}")
        if not self.input_digests or not self.output_digests:
            raise GeometryRefusal("a receipt binds at least one input and one output digest")
        object.__setattr__(self, "input_digests", dict(sorted(self.input_digests.items())))
        object.__setattr__(self, "output_digests", dict(sorted(self.output_digests.items())))
        object.__setattr__(self, "options", dict(sorted(self.options.items())))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": GEOMETRY_RECEIPT_SCHEMA, "classification": TRANSLATION_CLASSIFICATION, "provider_id": self.provider_id,
                "provider_version": self.provider_version, "provider_digest": self.provider_digest, "operation": self.operation,
                "input_digests": dict(self.input_digests), "output_digests": dict(self.output_digests),
                "options_digest": canonical_digest(dict(self.options)), "options": dict(self.options)}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class MeshBinding:
    """Explicit geometry -> mesh mapping: which mesh physical group realizes which canonical entity.

    The binding is checked against BOTH records it joins: every named group
    must exist on the mesh with the right kind, and every region/boundary/
    interface it maps must be declared by the geometry.  The model's meshed
    regions must all be realized; a region the mesh lost is a refusal, not a
    smaller region.
    """

    geometry_digest: str
    mesh_digest: str
    groups: Mapping[str, str]   # canonical entity id -> mesh physical group name
    entity_map_digest: str
    receipt_digest: str

    def __post_init__(self) -> None:
        g = {str(k): str(v) for k, v in dict(self.groups).items()}
        if not g or len(set(g.values())) != len(g):
            raise GeometryRefusal("a mesh binding maps each canonical entity to its own physical group")
        object.__setattr__(self, "groups", dict(sorted(g.items())))

    def validate(self, model: GeometryModel, mesh: SpatialMesh) -> "MeshBinding":
        if model.digest != self.geometry_digest:
            raise GeometryRefusal("mesh binding belongs to another geometry")
        if mesh.digest != self.mesh_digest:
            raise GeometryRefusal("mesh binding belongs to another mesh")
        groups = {grp.name: grp for grp in mesh.groups}
        declared = {r.entity_id: GroupKind.CELLS for r in model.regions}
        declared.update({b.entity_id: GroupKind.FACETS for b in model.boundaries})
        declared.update({i.entity_id: GroupKind.FACETS for i in model.interfaces})
        for entity, name in self.groups.items():
            if entity not in declared:
                raise GeometryRefusal(f"mesh binding maps {entity!r}, which the geometry does not declare")
            if name not in groups or groups[name].kind is not declared[entity]:
                raise GeometryRefusal(f"{entity!r} -> group {name!r} is absent from the mesh or of the wrong kind")
        missing = sorted(set(declared) - set(self.groups))
        if missing:
            raise GeometryRefusal(f"the mesh realizes no group for {missing}; a lost entity is refused, never dropped")
        return self

    def mesh_region(self, mesh: SpatialMesh, entity_id: str):
        if mesh.digest != self.mesh_digest:
            raise GeometryRefusal("mesh binding belongs to another mesh")
        if entity_id not in self.groups:
            raise GeometryRefusal(f"{entity_id!r} is not mapped onto this mesh")
        return mesh.region(self.groups[entity_id])

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MESH_BINDING_SCHEMA, "geometry_digest": self.geometry_digest, "mesh_digest": self.mesh_digest,
                "groups": dict(self.groups), "entity_map_digest": self.entity_map_digest, "receipt_digest": self.receipt_digest}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "MeshBinding":
        if p.get("schema") != MESH_BINDING_SCHEMA:
            raise GeometryRefusal("unsupported mesh binding schema")
        return cls(p["geometry_digest"], p["mesh_digest"], p["groups"], p["entity_map_digest"], p["receipt_digest"])


def region_material_map(model: GeometryModel, mesh: SpatialMesh, binding: MeshBinding,
                        states: Mapping[str, MaterialState] | None = None):
    """The BIG 5 :class:`~engcore.spatial.fields.RegionMaterialMap` implied by the geometry's material bindings.

    A region's state comes from its binding, or from ``states[region]`` when
    the binding names only the identity; a state of another material is
    refused.  A region with no state is refused (its conditions are UNKNOWN
    and are not defaulted).
    """
    from .fields import RegionMaterialMap

    binding.validate(model, mesh)
    supplied = dict(states or {})
    pairs = []
    for m in model.materials:
        state = m.state if m.state is not None else supplied.get(m.region)
        if state is None:
            raise GeometryRefusal(f"region {m.region!r} binds {m.material.family} with no declared state; conditions are never defaulted")
        if state.material != m.material:
            raise GeometryRefusal(f"region {m.region!r}: supplied state is of another material than the geometry binds")
        pairs.append((binding.mesh_region(mesh, f"region:{m.region}"), state))
    return RegionMaterialMap(mesh, tuple(pairs))
