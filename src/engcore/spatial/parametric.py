"""Parametric geometry: unit-aware parameters, templates and identity-bound variants.

Forge owns the CONTRACT of a parametric geometry -- which parameters exist,
their kinds, units and bounds, which builder realizes them and what identity
the result has.  Forge does not own a CAD kernel: a builder is a small pure
function over the primitives of :mod:`.geometry`, or a call into an external
CAD provider whose output arrives as an imported shape with a receipt.

A :class:`GeometryVariant` binds:

* the template identity (parameters + builder id/version);
* the exact parameter values (canonical units);
* the resulting :class:`~.geometry.GeometryModel` digest;
* the generator identity and a :class:`~.geometry.GeometryReceipt`.

Builder code is identified by ``builder_id`` and ``builder_version``; the
code itself is not hashed.  Changing a builder without bumping its version
is a broken contract, exactly like editing a frozen symbol.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.ir.variables import ScientificVariable, VariableKind, VariableRole
from ..scientific.units.quantity import Quantity, dimensionality
from .geometry import GeometryModel, GeometryReceipt, GeometryRefusal, _ident

PARAMETRIC_TEMPLATE_SCHEMA = "engcore.spatial.parametric_geometry/1"
GEOMETRY_VARIANT_SCHEMA = "engcore.spatial.geometry_variant/1"


class ParameterKind(str, Enum):
    LENGTH = "length"
    WIDTH = "width"
    HEIGHT = "height"
    RADIUS = "radius"
    THICKNESS = "thickness"
    ANGLE = "angle"
    POSITION = "position"
    ORIENTATION = "orientation"


_LENGTH_KINDS = {ParameterKind.LENGTH, ParameterKind.WIDTH, ParameterKind.HEIGHT, ParameterKind.RADIUS,
                 ParameterKind.THICKNESS, ParameterKind.POSITION}
_ANGLE_UNITS = ("radian", "degree", "turn", "arcminute", "arcsecond", "milliradian")
_POSITIVE_KINDS = {ParameterKind.LENGTH, ParameterKind.WIDTH, ParameterKind.HEIGHT, ParameterKind.RADIUS, ParameterKind.THICKNESS}


def canonical_unit(kind: ParameterKind) -> str:
    return "m" if kind in _LENGTH_KINDS else "rad"


@dataclass(frozen=True)
class GeometryParameter:
    """One declared geometric parameter with kind, canonical unit and closed bounds."""

    name: str
    kind: ParameterKind
    lower: Quantity
    upper: Quantity
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ident(self.name, "parameter name"))
        kind = ParameterKind(self.kind)
        object.__setattr__(self, "kind", kind)
        unit = canonical_unit(kind)
        for label in ("lower", "upper"):
            q = getattr(self, label)
            if not isinstance(q, Quantity) or q.dimensionality != dimensionality(unit):
                raise GeometryRefusal(f"parameter {self.name!r} {label} bound must be a Quantity in a {kind.value} unit")
            if kind not in _LENGTH_KINDS and str(q.units) not in _ANGLE_UNITS:
                raise GeometryRefusal(f"parameter {self.name!r} {label} bound must be an angle unit, not {q.units}")
            object.__setattr__(self, label, q.to(unit))
        if not self.upper.magnitude > self.lower.magnitude:
            raise GeometryRefusal(f"parameter {self.name!r} needs upper > lower")
        if kind in _POSITIVE_KINDS and not self.lower.magnitude > 0:
            raise GeometryRefusal(f"{kind.value} parameter {self.name!r} must be bounded away from zero (lower > 0)")

    @property
    def unit(self) -> str:
        return canonical_unit(self.kind)

    def admit(self, value: Quantity) -> Quantity:
        """The value in canonical units, or a refusal.  Out-of-bounds values are refused, never clipped."""
        if not isinstance(value, Quantity) or value.dimensionality != dimensionality(self.unit):
            raise GeometryRefusal(f"parameter {self.name!r} requires a {self.kind.value} Quantity")
        if self.kind not in _LENGTH_KINDS and str(value.units) not in _ANGLE_UNITS:
            raise GeometryRefusal(f"parameter {self.name!r} requires an angle unit, not {value.units}")
        v = value.to(self.unit)
        if not (self.lower.magnitude <= v.magnitude <= self.upper.magnitude):
            raise GeometryRefusal(f"parameter {self.name!r}={v.magnitude} {self.unit} lies outside "
                                  f"[{self.lower.magnitude}, {self.upper.magnitude}] {self.unit}")
        return v

    def as_design_variable(self, prefix: str = "") -> ScientificVariable:
        """The same parameter as a DESIGN ScientificVariable, so a DesignSpace can vary it."""
        return ScientificVariable(name=f"{prefix}{self.name}", unit=self.unit, kind=VariableKind.CONTINUOUS, role=VariableRole.DESIGN,
                                  lower=self.lower, upper=self.upper, description=self.description or f"geometry {self.kind.value}")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind.value, "unit": self.unit, "lower": self.lower.magnitude, "upper": self.upper.magnitude}


Builder = Callable[[Mapping[str, Quantity]], GeometryModel]


class GeometryBuilderRegistry:
    """Explicit builder registry: ``(builder_id, version) -> pure function``.  Never falls back."""

    def __init__(self) -> None:
        self._builders: dict[tuple[str, str], Builder] = {}

    def register(self, builder_id: str, version: str, builder: Builder) -> None:
        key = (_ident(builder_id, "builder_id"), str(version).strip())
        if not key[1]:
            raise GeometryRefusal("builder version is required")
        if key in self._builders:
            raise GeometryRefusal(f"builder {key} is already registered")
        self._builders[key] = builder

    def get(self, builder_id: str, version: str) -> Builder:
        try:
            return self._builders[(builder_id, version)]
        except KeyError:
            raise GeometryRefusal(f"no geometry builder {builder_id!r} version {version!r} is registered; none is substituted") from None


@dataclass(frozen=True)
class ParametricGeometry:
    """A parameterized geometry template.  Identity = parameters + builder identity."""

    template_id: str
    version: str
    parameters: tuple[GeometryParameter, ...]
    builder_id: str
    builder_version: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "template_id", _ident(self.template_id, "template_id"))
        if not str(self.version).strip() or not str(self.builder_version).strip():
            raise GeometryRefusal("parametric geometry requires version and builder_version")
        object.__setattr__(self, "builder_id", _ident(self.builder_id, "builder_id"))
        params = tuple(sorted(self.parameters, key=lambda p: p.name))
        if not params or any(not isinstance(p, GeometryParameter) for p in params) or len({p.name for p in params}) != len(params):
            raise GeometryRefusal("parametric geometry needs unique GeometryParameter records")
        object.__setattr__(self, "parameters", params)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PARAMETRIC_TEMPLATE_SCHEMA, "template_id": self.template_id, "version": self.version,
                "parameters": [p.to_dict() for p in self.parameters], "builder_id": self.builder_id, "builder_version": self.builder_version}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def design_variables(self, prefix: str = "") -> tuple[ScientificVariable, ...]:
        return tuple(p.as_design_variable(prefix) for p in self.parameters)

    def admit(self, values: Mapping[str, Quantity]) -> dict[str, Quantity]:
        """Complete, in-bounds, canonical-unit values.  Missing parameters are refused (never defaulted)."""
        declared = {p.name: p for p in self.parameters}
        missing = sorted(set(declared) - set(values))
        extra = sorted(set(values) - set(declared))
        if missing or extra:
            raise GeometryRefusal(f"template {self.template_id!r}: missing {missing}, undeclared {extra}")
        return {name: declared[name].admit(values[name]) for name in sorted(declared)}

    def instantiate(self, values: Mapping[str, Quantity], registry: GeometryBuilderRegistry) -> tuple[GeometryModel, "GeometryVariant"]:
        admitted = self.admit(values)
        model = registry.get(self.builder_id, self.builder_version)(dict(admitted))
        if not isinstance(model, GeometryModel):
            raise GeometryRefusal(f"builder {self.builder_id!r} returned {type(model).__name__}, not a GeometryModel")
        canonical = {k: v.magnitude for k, v in admitted.items()}
        receipt = GeometryReceipt(
            provider_id=f"forge-builder:{self.builder_id}", provider_version=self.builder_version, operation="parametric_build",
            input_digests={"template": self.digest, "parameters": canonical_digest(canonical)},
            output_digests={"geometry": model.digest, "shape": model.shape_digest})
        return model, GeometryVariant(self.template_id, self.version, self.digest, canonical, model.digest, model.shape_digest,
                                      self.builder_id, self.builder_version, receipt)


@dataclass(frozen=True)
class GeometryVariant:
    """One instantiated parameter set and the exact geometry it produced."""

    template_id: str
    template_version: str
    template_digest: str
    parameter_values: Mapping[str, float]   # canonical units (m / rad)
    geometry_digest: str
    shape_digest: str
    builder_id: str
    builder_version: str
    receipt: GeometryReceipt

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_values", dict(sorted((str(k), float(v)) for k, v in dict(self.parameter_values).items())))
        if self.receipt.output_digests.get("geometry") != self.geometry_digest:
            raise GeometryRefusal("variant receipt does not record the variant's geometry digest")

    @property
    def variant_id(self) -> str:
        return canonical_digest({"template": self.template_digest, "parameters": dict(self.parameter_values),
                                 "geometry": self.geometry_digest})

    def to_dict(self) -> dict[str, Any]:
        return {"schema": GEOMETRY_VARIANT_SCHEMA, "variant_id": self.variant_id, "template_id": self.template_id,
                "template_version": self.template_version, "template_digest": self.template_digest,
                "parameter_values": dict(self.parameter_values), "geometry_digest": self.geometry_digest, "shape_digest": self.shape_digest,
                "builder_id": self.builder_id, "builder_version": self.builder_version, "receipt": self.receipt.to_dict()}

    def verify(self, template: ParametricGeometry, registry: GeometryBuilderRegistry) -> GeometryModel:
        """Replay: rebuild from the template and refuse any identity drift."""
        if template.digest != self.template_digest:
            raise GeometryRefusal("variant was produced by another template")
        model, again = template.instantiate({k: Quantity(v, template_param_unit(template, k)) for k, v in self.parameter_values.items()}, registry)
        if again.geometry_digest != self.geometry_digest:
            raise GeometryRefusal("rebuilding the variant produced a different geometry; the builder changed without a version bump")
        if again.to_dict() != self.to_dict():  # shape digest, builder identity and receipt are identity too, not only the geometry
            drift = sorted(k for k, v in again.to_dict().items() if self.to_dict().get(k) != v)
            raise GeometryRefusal(f"the stored variant does not match its replay in {drift}")
        return model


def template_param_unit(template: ParametricGeometry, name: str) -> str:
    for p in template.parameters:
        if p.name == name:
            return p.unit
    raise GeometryRefusal(f"template has no parameter {name!r}")
