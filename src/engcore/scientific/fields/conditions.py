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


@dataclass(frozen=True)
class FieldBoundaryCondition:
    """One condition, on one field, over one region of its support."""

    name: str
    field_id: str
    region_id: str
    kind: BoundaryKind
    value: Quantity | None = None
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

        if self.value is not None and not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                f"field boundary condition {self.name!r}: value must be a Quantity"
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
        if self.kind is BoundaryKind.DIRICHLET:
            require_same_dimension(
                self.value,
                definition.unit,
                context=(
                    f"field boundary condition {self.name!r} on field "
                    f"{definition.field_id!r}"
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_BOUNDARY_CONDITION_SCHEMA,
            "name": self.name,
            "field_id": self.field_id,
            "region_id": self.region_id,
            "kind": self.kind.value,
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
            value=Quantity.from_dict(value) if value else None,
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
