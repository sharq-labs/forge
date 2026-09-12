"""Conditions on a field, typed by what they impose and where.

The scalar IR already distinguishes the families — ``BoundaryKind`` has been
DIRICHLET, NEUMANN, ROBIN, PERIODIC and OTHER since before any field existed —
and that vocabulary is reused here rather than duplicated. What is new is the
other half of a field condition: *where* it applies is a resolvable region on a
declared support, and *what* it applies to is a declared field whose unit the
condition is checked against.

A condition therefore cannot be attached to an edge of a support it was not
declared on, cannot prescribe kelvin for a field measured in volts, and cannot
be one of two conditions silently competing for one edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any, Iterable, Mapping

from ..errors import InvalidScientificProblem
from ..ir.conditions import BoundaryKind
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from .definition import FieldDefinition
from .profiles import (
    SPATIAL_PROFILE_SCHEMA,
    SpatialProfile,
    as_profile,
    edge_axis,
    load_profile,
)
from .mesh import StructuredMesh
from .regions import MeshRegion
from .result import FieldRecord

FIELD_BOUNDARY_CONDITION_SCHEMA = schema_string("field_boundary_condition")
FIELD_INITIAL_CONDITION_SCHEMA = schema_string("field_initial_condition")

#: The families that carry a prescribed value on this support. ROBIN is
#: representable — it is in the vocabulary and round-trips — and carries
#: coefficients instead; whether a solver serves it is the solver's declaration
#: to make, not this record's.
VALUED_KINDS = (BoundaryKind.DIRICHLET, BoundaryKind.NEUMANN)

#: How far two conditions meeting at a corner may disagree about the value
#: there. Relative, because the fields this guards carry magnitudes in the
#: hundreds and an absolute bound would be a different rule at every scale.
CORNER_AGREEMENT_REL_TOL = 1e-9


def _read_value(payload: Any) -> "Quantity | SpatialProfile | None":
    """A serialized boundary value, whichever of the two spellings it is.

    Both carry their own schema, so the discriminator is the payload's own
    statement about itself rather than a guess from its shape.
    """
    if not payload:
        return None
    if payload.get("schema") == SPATIAL_PROFILE_SCHEMA:
        return load_profile(payload)
    return Quantity.from_dict(payload)


@dataclass(frozen=True)
class FieldBoundaryCondition:
    """One condition, on one field, over one region of its support."""

    name: str
    field_id: str
    region_id: str
    kind: BoundaryKind
    #: What this condition imposes. A ``Quantity`` is the constant case and is
    #: spelled, stored and serialized exactly as it was before profiles
    #: existed; a ``SpatialProfile`` is a law that varies along the edge. One
    #: slot rather than two, because "constant" is a law like any other and a
    #: consumer should never have to branch on which spelling it was handed —
    #: :attr:`law` answers for both.
    value: Quantity | SpatialProfile | None = None
    coefficients: Mapping[str, Quantity] = dataclass_field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("name", "field_id", "region_id"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise InvalidScientificProblem(
                    f"a field boundary condition requires a non-empty {label}"
                )
            object.__setattr__(self, label, text)
        object.__setattr__(self, "kind", BoundaryKind(self.kind))

        from ..results.immutable import freeze

        coefficients = dict(self.coefficients)
        for key, coefficient in coefficients.items():
            if not isinstance(coefficient, Quantity):
                raise InvalidScientificProblem(
                    f"field boundary condition {self.name!r}: coefficient "
                    f"{key!r} must be a Quantity"
                )
        object.__setattr__(self, "coefficients", freeze(coefficients))

        if self.value is not None:
            # Validates and refuses; the value is stored as it was given so a
            # constant still serializes as a bare quantity.
            as_profile(
                self.value,
                context=f"field boundary condition {self.name!r}: value must be "
                f"a Quantity or a SpatialProfile",
            )
        if self.kind in VALUED_KINDS and self.value is None:
            raise InvalidScientificProblem(
                f"field boundary condition {self.name!r}: kind "
                f"{self.kind.value!r} prescribes a value and none was given"
            )
        if self.kind is BoundaryKind.ROBIN and not self.coefficients:
            raise InvalidScientificProblem(
                f"field boundary condition {self.name!r}: a robin condition is "
                f"its coefficients, and none were declared"
            )

    @property
    def law(self) -> SpatialProfile:
        """This condition's value as a spatial law, constant or not.

        The one place the two spellings converge, so every consumer downstream
        handles exactly one type.
        """
        if self.value is None:
            raise InvalidScientificProblem(
                f"field boundary condition {self.name!r} of kind "
                f"{self.kind.value!r} prescribes no value and has no law"
            )
        return as_profile(self.value, context=f"condition {self.name!r}")

    @property
    def is_uniform(self) -> bool:
        """Whether this condition is the same at every point of its region."""
        return self.value is None or not self.law.axes

    # ---- what it must agree with -------------------------------------------
    def require_consistent(
        self, definition: FieldDefinition, region: MeshRegion, mesh: StructuredMesh
    ) -> None:
        """Refuse a condition that does not belong to this field, region and support.

        A Dirichlet condition **is** a value of the field, so its dimension is
        the field's, universally. A Neumann condition is a normal derivative or
        a flux, whose dimension depends on what the domain multiplies it by;
        the core checks it is a Quantity and leaves the dimension to the domain,
        exactly as the scalar IR already reasons about the same two families.
        """
        if definition.field_id != self.field_id:
            raise InvalidScientificProblem(
                f"condition {self.name!r} is declared on field "
                f"{self.field_id!r} and was checked against "
                f"{definition.field_id!r}"
            )
        if region.region_id != self.region_id:
            raise InvalidScientificProblem(
                f"condition {self.name!r} applies to region {self.region_id!r} "
                f"and was checked against {region.region_id!r}"
            )
        definition.require_support(mesh)
        region.require_support(mesh)
        if self.value is None:
            return
        law = self.law
        context = (
            f"field boundary condition {self.name!r} on field "
            f"{definition.field_id!r}"
        )
        if self.kind is BoundaryKind.DIRICHLET:
            law.require_output_dimension(definition.unit, context=context)
        # A law varying along the wrong coordinate is the failure a region-aware
        # boundary condition exists to catch: a profile of x bound to a left
        # edge would evaluate to one value along the whole of it, silently.
        law.require_axis(edge_axis(region.edge), context=context)
        law.require_covers(*region.span(mesh), context=context)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_BOUNDARY_CONDITION_SCHEMA,
            "name": self.name,
            "field_id": self.field_id,
            "region_id": self.region_id,
            "kind": self.kind.value,
            # Both a quantity and a profile serialize to a mapping carrying
            # its own schema, so one key holds either and a constant condition
            # written before profiles existed round-trips byte for byte.
            "value": self.value.to_dict() if self.value is not None else None,
            "coefficients": {
                key: self.coefficients[key].to_dict()
                for key in sorted(self.coefficients)
            },
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldBoundaryCondition":
        require_schema(payload, FIELD_BOUNDARY_CONDITION_SCHEMA)
        value = payload.get("value")
        return cls(
            name=payload["name"],
            field_id=payload["field_id"],
            region_id=payload["region_id"],
            kind=BoundaryKind(payload["kind"]),
            value=_read_value(value),
            coefficients={
                key: Quantity.from_dict(item)
                for key, item in (payload.get("coefficients") or {}).items()
            },
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class FieldInitialCondition:
    """The state of a field at the start of a march.

    Exactly one of ``uniform`` and ``record`` — a constant start is a Quantity
    and needs no array, and anything else is a field, which means bulk data
    behind a reference rather than values on this record.
    """

    field_id: str
    uniform: Quantity | None = None
    record: FieldRecord | None = None
    time: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        field_id = str(self.field_id).strip()
        if not field_id:
            raise InvalidScientificProblem(
                "a field initial condition requires a non-empty field_id"
            )
        object.__setattr__(self, "field_id", field_id)

        stated = [name for name, value in (("uniform", self.uniform), ("record", self.record)) if value is not None]
        if len(stated) != 1:
            raise InvalidScientificProblem(
                f"field initial condition for {field_id!r} states {stated or 'nothing'}; "
                f"exactly one of a uniform value or a field record is required"
            )
        if self.uniform is not None and not isinstance(self.uniform, Quantity):
            raise InvalidScientificProblem(
                f"field initial condition for {field_id!r}: uniform must be a Quantity"
            )
        if self.record is not None:
            if not isinstance(self.record, FieldRecord):
                raise InvalidScientificProblem(
                    f"field initial condition for {field_id!r}: record must be a "
                    f"FieldRecord"
                )
            if self.record.definition.field_id != field_id:
                raise InvalidScientificProblem(
                    f"field initial condition for {field_id!r} carries a record "
                    f"of {self.record.definition.field_id!r}"
                )
        if self.time is not None:
            if not isinstance(self.time, Quantity):
                raise InvalidScientificProblem(
                    f"field initial condition for {field_id!r}: time must be a Quantity"
                )
            require_same_dimension(
                self.time, "second",
                context=f"field initial condition for {field_id!r}: time",
            )

    def require_consistent(self, definition: FieldDefinition) -> None:
        if definition.field_id != self.field_id:
            raise InvalidScientificProblem(
                f"initial condition for {self.field_id!r} was checked against "
                f"field {definition.field_id!r}"
            )
        if self.uniform is not None:
            require_same_dimension(
                self.uniform, definition.unit,
                context=f"initial condition for field {definition.field_id!r}",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_INITIAL_CONDITION_SCHEMA,
            "field_id": self.field_id,
            "uniform": self.uniform.to_dict() if self.uniform is not None else None,
            "record": self.record.to_dict() if self.record is not None else None,
            "time": self.time.to_dict() if self.time is not None else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldInitialCondition":
        require_schema(payload, FIELD_INITIAL_CONDITION_SCHEMA)
        uniform = payload.get("uniform")
        record = payload.get("record")
        time = payload.get("time")
        return cls(
            field_id=payload["field_id"],
            uniform=Quantity.from_dict(uniform) if uniform else None,
            record=FieldRecord.from_dict(record) if record else None,
            time=Quantity.from_dict(time) if time else None,
            description=payload.get("description", ""),
        )


def require_complete_boundary(
    definition: FieldDefinition,
    mesh: StructuredMesh,
    regions: Iterable[MeshRegion],
    conditions: Iterable[FieldBoundaryCondition],
) -> None:
    """Every edge of the support carries exactly one condition on this field.

    Three refusals, and each one is a state a solve could otherwise reach:

    * a condition naming a region that is not on this support — nothing to
      impose it on;
    * two conditions on one region — a contradiction with a silent winner,
      which is the same defect as two boundary values at a corner;
    * an edge with no condition — an under-determined problem that a solver
      would answer anyway, with whatever its assembly happened to leave there.
    """
    by_id = {region.region_id: region for region in regions}
    for region in by_id.values():
        region.require_support(mesh)

    seen: dict[str, str] = {}
    for condition in conditions:
        if condition.field_id != definition.field_id:
            continue
        region = by_id.get(condition.region_id)
        if region is None:
            raise InvalidScientificProblem(
                f"condition {condition.name!r} applies to region "
                f"{condition.region_id!r}, which is not a region of support "
                f"{mesh.mesh_id!r}; declared: {sorted(by_id)}"
            )
        if condition.region_id in seen:
            raise InvalidScientificProblem(
                f"region {condition.region_id!r} carries two conditions on "
                f"field {definition.field_id!r}: {seen[condition.region_id]!r} "
                f"and {condition.name!r}. One edge, one condition"
            )
        seen[condition.region_id] = condition.name
        condition.require_consistent(definition, region, mesh)

    missing = sorted(set(by_id) - set(seen))
    if missing:
        raise InvalidScientificProblem(
            f"field {definition.field_id!r} has no condition on {missing}; an "
            f"edge without one leaves the problem under-determined, and a "
            f"solver would answer it anyway"
        )
    _require_corners_agree(definition, mesh, by_id, conditions)


def _require_corners_agree(
    definition: FieldDefinition,
    mesh: StructuredMesh,
    by_id: Mapping[str, MeshRegion],
    conditions: Iterable[FieldBoundaryCondition],
) -> None:
    """Two prescribed values meeting at a corner must be the same value.

    The defect this closes was real and silent. A corner node is on two edges,
    so when both prescribe a value the assembly pins it twice and the winner is
    whichever edge the solver happened to write last — an iteration order
    deciding a boundary value. The module docstring above already called that
    "the same defect" as two conditions on one region, and until now only the
    second half was refused.

    Only prescribed-value edges can conflict: a flux condition constrains a
    derivative and imposes nothing at the point itself, so a value edge meeting
    a flux edge is not a contradiction and is left alone.
    """
    prescribed = {
        condition.region_id: condition
        for condition in conditions
        if condition.field_id == definition.field_id
        and condition.kind is BoundaryKind.DIRICHLET
        and condition.value is not None
    }
    corners: dict[tuple[float, float], list[FieldBoundaryCondition]] = {}
    for region_id, condition in prescribed.items():
        region = by_id.get(region_id)
        if region is None:  # pragma: no cover - refused above
            continue
        for point in region.corner_points(mesh):
            corners.setdefault(point, []).append(condition)

    for (x, y), meeting in sorted(corners.items()):
        if len(meeting) < 2:
            continue
        first, *rest = meeting
        reference = first.law.evaluate(x=x, y=y)
        for other in rest:
            value = other.law.evaluate(x=x, y=y)
            tolerance = CORNER_AGREEMENT_REL_TOL * max(
                1.0, abs(reference), abs(value)
            )
            if abs(value - reference) > tolerance:
                raise InvalidScientificProblem(
                    f"conditions {first.name!r} and {other.name!r} meet at "
                    f"corner ({x:g}, {y:g}) of support {mesh.mesh_id!r} and "
                    f"prescribe {reference:g} and {value:g} "
                    f"{definition.unit} there. A corner node belongs to both "
                    f"edges, so one of these silently wins on whichever order "
                    f"the assembly happens to use"
                )
