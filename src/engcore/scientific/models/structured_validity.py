"""Validity predicates for typed field and structured-mesh records.

Raw arrays remain outside the control-plane validity contract.  Field checks
consume :class:`FieldRecord`, and mesh checks consume :class:`StructuredMesh`.
That preserves the typed scientific boundary while letting model applicability
reason about non-scalar results in O(1) from their records.

The field IR currently represents vector/tensor-like values as a flat component
count.  The conditions below verify exactly that representation; they do not
claim tensor topology or unstructured-mesh semantics the records cannot state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..errors import ModelValidityError, ScientificCoreError
from ..fields.definition import FieldLocation
from ..fields.mesh import CANONICAL_LENGTH, StructuredMesh
from ..fields.result import FieldRecord
from ..serialization import require_bool, require_schema, schema_string
from ..sequences import duplicates
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from . import definition as _base
from .definition import UnknownReason, ValidityStatus

FIELD_RANGE_CONDITION_SCHEMA = schema_string("validity_field_range_condition")
FIELD_FINITE_CONDITION_SCHEMA = schema_string("validity_field_finite_condition")
FIELD_STRUCTURE_CONDITION_SCHEMA = schema_string("validity_field_structure_condition")
MESH_RESOLUTION_CONDITION_SCHEMA = schema_string("validity_mesh_resolution_condition")


def _name(value: Any, *, label: str = "condition") -> str:
    text = str(value).strip()
    if not text:
        raise ModelValidityError(f"structured validity {label} requires a name")
    return text


def _source(value: Any | None, *, fallback: str, label: str) -> str:
    return fallback if value is None else _name(value, label=label)


def _requires(name: str, values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ModelValidityError(
            f"condition {name!r}: requires must be a sequence, not a bare string"
        )
    result = tuple(str(v).strip() for v in values if str(v).strip())
    if name in result:
        raise ModelValidityError(f"condition {name!r} cannot require itself")
    repeated = duplicates(result)
    if repeated:
        raise ModelValidityError(
            f"condition {name!r} names {repeated} more than once in requires"
        )
    return result


def _unknown_reason(context: Mapping[str, Any], key: str) -> UnknownReason:
    return (
        UnknownReason.NOT_SUPPLIED
        if context.get(key) is None
        else UnknownReason.UNREADABLE_SHAPE
    )


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ModelValidityError(f"{label} must be a positive int, got {value!r}")
    return value


def _optional_positive_int(value: Any, *, label: str) -> int | None:
    return None if value is None else _positive_int(value, label=label)


def _strict_bool(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    return require_bool(payload, key, default, error=ModelValidityError)


@dataclass(frozen=True)
class FieldRangeCondition:
    """Require the whole represented field envelope to lie within bounds.

    ``name`` identifies the condition; ``field`` identifies the context value.
    Keeping those separate allows finite/range/structure checks to target the
    same field without duplicating it under several context keys.
    """

    name: str
    field: str | None = None
    minimum: Quantity | None = None
    maximum: Quantity | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name))
        object.__setattr__(self, "field", _source(self.field, fallback=self.name, label="field"))
        object.__setattr__(self, "requires", _requires(self.name, self.requires))
        for flag in ("minimum_inclusive", "maximum_inclusive"):
            if not isinstance(getattr(self, flag), bool):
                raise ModelValidityError(f"condition {self.name!r}: {flag} must be boolean")
        if self.minimum is None and self.maximum is None:
            raise ModelValidityError(
                f"field range condition {self.name!r} needs a minimum or maximum"
            )
        for bound in (self.minimum, self.maximum):
            if bound is not None and not isinstance(bound, Quantity):
                raise ModelValidityError(
                    f"field range condition {self.name!r} bounds must be Quantities"
                )
        if self.minimum is not None and self.maximum is not None:
            require_same_dimension(
                self.minimum, self.maximum, context=f"field validity range {self.name!r}"
            )
            if self.maximum.magnitude_in(self.minimum.units) < self.minimum.magnitude:
                raise ModelValidityError(
                    f"field range condition {self.name!r}: maximum below minimum"
                )

    def evaluate(self, value: Any) -> ValidityStatus:
        if not isinstance(value, FieldRecord):
            return ValidityStatus.UNKNOWN
        if not value.is_finite:
            return ValidityStatus.UNKNOWN
        if self.minimum is not None:
            result = _base._within(
                value.summary.minimum,
                minimum=self.minimum,
                maximum=None,
                minimum_inclusive=self.minimum_inclusive,
                maximum_inclusive=True,
                name=self.name,
            )
            if result is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
                return result
        if self.maximum is not None:
            result = _base._within(
                value.summary.maximum,
                minimum=None,
                maximum=self.maximum,
                minimum_inclusive=True,
                maximum_inclusive=self.maximum_inclusive,
                name=self.name,
            )
            if result is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
                return result
        return ValidityStatus.IN_DOMAIN

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        return self.evaluate(context.get(self.field))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        value = context.get(self.field)
        if isinstance(value, FieldRecord) and not value.is_finite:
            # Kept non-actionable until the UNKNOWN reason schema is widened.
            return UnknownReason.UNREADABLE_SHAPE
        return _unknown_reason(context, self.field)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.field})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_RANGE_CONDITION_SCHEMA,
            "name": self.name,
            "field": self.field,
            "minimum": self.minimum.to_dict() if self.minimum else None,
            "maximum": self.maximum.to_dict() if self.maximum else None,
            "minimum_inclusive": self.minimum_inclusive,
            "maximum_inclusive": self.maximum_inclusive,
            "requires": list(self.requires),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldRangeCondition":
        require_schema(payload, FIELD_RANGE_CONDITION_SCHEMA)
        minimum, maximum = payload.get("minimum"), payload.get("maximum")
        return cls(
            name=payload["name"],
            field=payload.get("field"),
            minimum=Quantity.from_dict(minimum) if minimum else None,
            maximum=Quantity.from_dict(maximum) if maximum else None,
            minimum_inclusive=_strict_bool(payload, "minimum_inclusive", True),
            maximum_inclusive=_strict_bool(payload, "maximum_inclusive", True),
            requires=tuple(payload.get("requires", ())),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class FieldFiniteCondition:
    """Require a typed field record to report zero non-finite values."""

    name: str
    field: str | None = None
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name))
        object.__setattr__(self, "field", _source(self.field, fallback=self.name, label="field"))
        object.__setattr__(self, "requires", _requires(self.name, self.requires))

    def evaluate(self, value: Any) -> ValidityStatus:
        if not isinstance(value, FieldRecord):
            return ValidityStatus.UNKNOWN
        return (
            ValidityStatus.IN_DOMAIN
            if value.is_finite
            else ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        )

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        return self.evaluate(context.get(self.field))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        return _unknown_reason(context, self.field)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.field})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_FINITE_CONDITION_SCHEMA,
            "name": self.name,
            "field": self.field,
            "requires": list(self.requires),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldFiniteCondition":
        require_schema(payload, FIELD_FINITE_CONDITION_SCHEMA)
        return cls(
            name=payload["name"],
            field=payload.get("field"),
            requires=tuple(payload.get("requires", ())),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class FieldStructureCondition:
    """Verify shape facts the current field IR can state without guessing.

    ``components`` is a flat component count.  It can distinguish scalar from
    3-component vector or 9-component tensor-like fields, but cannot prove that
    nine components have a 3x3 tensor topology because ``FieldDefinition`` does
    not yet carry component-axis shape.  That limitation is explicit here.
    """

    name: str
    field: str | None = None
    components: int | None = None
    spatial_rank: int | None = None
    location: FieldLocation | None = None
    mesh_id: str | None = None
    exact_shape: tuple[int, ...] | None = None
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name))
        object.__setattr__(self, "field", _source(self.field, fallback=self.name, label="field"))
        object.__setattr__(self, "requires", _requires(self.name, self.requires))
        if self.components is not None:
            object.__setattr__(self, "components", _positive_int(self.components, label="components"))
        if self.spatial_rank is not None:
            if isinstance(self.spatial_rank, bool) or not isinstance(self.spatial_rank, int) or self.spatial_rank < 0:
                raise ModelValidityError("spatial_rank must be a non-negative int")
        if self.location is not None:
            object.__setattr__(self, "location", FieldLocation(self.location))
        if self.mesh_id is not None:
            object.__setattr__(self, "mesh_id", _name(self.mesh_id, label="mesh_id"))
        if self.exact_shape is not None:
            shape = tuple(self.exact_shape)
            if not shape or any(
                isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in shape
            ):
                raise ModelValidityError(
                    f"exact_shape must contain positive ints, got {self.exact_shape!r}"
                )
            object.__setattr__(self, "exact_shape", shape)
        if all(
            v is None
            for v in (self.components, self.spatial_rank, self.location, self.mesh_id, self.exact_shape)
        ):
            raise ModelValidityError(
                f"field structure condition {self.name!r} must constrain at least one fact"
            )

    def evaluate(self, value: Any) -> ValidityStatus:
        if not isinstance(value, FieldRecord):
            return ValidityStatus.UNKNOWN
        definition = value.definition
        if self.components is not None and definition.components != self.components:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.location is not None and definition.location is not self.location:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.mesh_id is not None and definition.mesh_id != self.mesh_id:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.exact_shape is not None and tuple(value.shape) != self.exact_shape:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.spatial_rank is not None:
            rank = len(value.shape) - (1 if definition.components > 1 else 0)
            if rank != self.spatial_rank:
                return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        return ValidityStatus.IN_DOMAIN

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        return self.evaluate(context.get(self.field))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        return _unknown_reason(context, self.field)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.field})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_STRUCTURE_CONDITION_SCHEMA,
            "name": self.name,
            "field": self.field,
            "components": self.components,
            "spatial_rank": self.spatial_rank,
            "location": self.location.value if self.location is not None else None,
            "mesh_id": self.mesh_id,
            "exact_shape": list(self.exact_shape) if self.exact_shape is not None else None,
            "requires": list(self.requires),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldStructureCondition":
        require_schema(payload, FIELD_STRUCTURE_CONDITION_SCHEMA)
        shape, location = payload.get("exact_shape"), payload.get("location")
        return cls(
            name=payload["name"],
            field=payload.get("field"),
            components=payload.get("components"),
            spatial_rank=payload.get("spatial_rank"),
            location=FieldLocation(location) if location is not None else None,
            mesh_id=payload.get("mesh_id"),
            exact_shape=tuple(shape) if shape is not None else None,
            requires=tuple(payload.get("requires", ())),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class MeshResolutionCondition:
    """Validity limits over the structured 2-D mesh represented by the core."""

    name: str
    mesh: str | None = None
    min_nodes_x: int | None = None
    min_nodes_y: int | None = None
    max_spacing_x: Quantity | None = None
    max_spacing_y: Quantity | None = None
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name))
        object.__setattr__(self, "mesh", _source(self.mesh, fallback=self.name, label="mesh"))
        object.__setattr__(self, "requires", _requires(self.name, self.requires))
        object.__setattr__(self, "min_nodes_x", _optional_positive_int(self.min_nodes_x, label="min_nodes_x"))
        object.__setattr__(self, "min_nodes_y", _optional_positive_int(self.min_nodes_y, label="min_nodes_y"))
        for label in ("max_spacing_x", "max_spacing_y"):
            value = getattr(self, label)
            if value is None:
                continue
            if not isinstance(value, Quantity):
                raise ModelValidityError(f"{label} must be a Quantity")
            require_same_dimension(value, CANONICAL_LENGTH, context=label)
            magnitude = value.magnitude_in(CANONICAL_LENGTH)
            if not math.isfinite(magnitude) or magnitude <= 0.0:
                raise ModelValidityError(f"{label} must be finite and positive")
        if all(
            v is None
            for v in (self.min_nodes_x, self.min_nodes_y, self.max_spacing_x, self.max_spacing_y)
        ):
            raise ModelValidityError(
                f"mesh resolution condition {self.name!r} must constrain something"
            )

    def evaluate(self, value: Any) -> ValidityStatus:
        if not isinstance(value, StructuredMesh):
            return ValidityStatus.UNKNOWN
        if self.min_nodes_x is not None and value.nodes_x < self.min_nodes_x:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.min_nodes_y is not None and value.nodes_y < self.min_nodes_y:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.max_spacing_x is not None and value.spacing_x.compare(self.max_spacing_x) > 0:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.max_spacing_y is not None and value.spacing_y.compare(self.max_spacing_y) > 0:
            return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        return ValidityStatus.IN_DOMAIN

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        return self.evaluate(context.get(self.mesh))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        return _unknown_reason(context, self.mesh)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.mesh})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MESH_RESOLUTION_CONDITION_SCHEMA,
            "name": self.name,
            "mesh": self.mesh,
            "min_nodes_x": self.min_nodes_x,
            "min_nodes_y": self.min_nodes_y,
            "max_spacing_x": self.max_spacing_x.to_dict() if self.max_spacing_x else None,
            "max_spacing_y": self.max_spacing_y.to_dict() if self.max_spacing_y else None,
            "requires": list(self.requires),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MeshResolutionCondition":
        require_schema(payload, MESH_RESOLUTION_CONDITION_SCHEMA)
        sx, sy = payload.get("max_spacing_x"), payload.get("max_spacing_y")
        return cls(
            name=payload["name"],
            mesh=payload.get("mesh"),
            min_nodes_x=payload.get("min_nodes_x"),
            min_nodes_y=payload.get("min_nodes_y"),
            max_spacing_x=Quantity.from_dict(sx) if sx else None,
            max_spacing_y=Quantity.from_dict(sy) if sy else None,
            requires=tuple(payload.get("requires", ())),
            description=payload.get("description", ""),
        )


def _register() -> None:
    additions = {
        FIELD_RANGE_CONDITION_SCHEMA: FieldRangeCondition,
        FIELD_FINITE_CONDITION_SCHEMA: FieldFiniteCondition,
        FIELD_STRUCTURE_CONDITION_SCHEMA: FieldStructureCondition,
        MESH_RESOLUTION_CONDITION_SCHEMA: MeshResolutionCondition,
    }
    for schema, decoder in additions.items():
        present = _base._CONDITION_DECODERS.get(schema)
        if present is not None and present is not decoder:
            raise ScientificCoreError(
                f"validity condition schema {schema!r} is already registered to "
                f"{present.__name__}; refusing an ambiguous wire format"
            )
        _base._CONDITION_DECODERS[schema] = decoder


_register()

__all__ = [
    "FieldRangeCondition",
    "FieldFiniteCondition",
    "FieldStructureCondition",
    "MeshResolutionCondition",
]
