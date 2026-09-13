"""Validity predicates for typed field and structured-mesh records.

The scalar validity layer deliberately accepts scalar declarations only.  This
module extends the *validity vocabulary* without weakening that boundary: raw
arrays are still not scientific values and are never scanned here.  A field is
assessed through :class:`~engcore.scientific.fields.result.FieldRecord`, the
O(1) control-plane record that binds a declaration, support identity, shape,
summary and content-addressed value reference.

The first slice is intentionally honest about the field IR that exists today:
``StructuredMesh`` is two-dimensional rectilinear and ``FieldDefinition``
represents vector/tensor-like values as a flat component count.  These
conditions verify exactly those facts; they do not claim unstructured-mesh or
full tensor-topology semantics that the underlying records cannot express.
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


def _clean_name(value: Any, *, label: str = "condition") -> str:
    text = str(value).strip()
    if not text:
        raise ModelValidityError(f"structured validity {label} requires a name")
    return text


def _clean_requires(name: str, values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ModelValidityError(
            f"condition {name!r}: requires must be a sequence of condition names, "
            "not a bare string"
        )
    required = tuple(str(item).strip() for item in values if str(item).strip())
    if name in required:
        raise ModelValidityError(
            f"condition {name!r} requires itself, which can never be established first"
        )
    repeated = duplicates(required)
    if repeated:
        raise ModelValidityError(
            f"condition {name!r} names {repeated} more than once in requires"
        )
    return required


def _typed_reason(context: Mapping[str, Any], name: str) -> UnknownReason:
    """Use the existing closed reason vocabulary at the typed boundary."""
    return (
        UnknownReason.NOT_SUPPLIED
        if context.get(name) is None
        else UnknownReason.UNREADABLE_SHAPE
    )


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ModelValidityError(f"{label} must be a positive int, got {value!r}")
    return value


def _optional_positive_int(value: Any, *, label: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, label=label)


def _strict_bool(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    return require_bool(payload, key, default, error=ModelValidityError)


@dataclass(frozen=True)
class FieldRangeCondition:
    """Require every represented field value to lie inside declared bounds.

    The check is O(1): the lower bound is tested against ``summary.minimum``
    and the upper bound against ``summary.maximum``.  The field bytes are not
    resolved or scanned.  A record containing non-finite values cannot prove a
    range claim, so it remains UNKNOWN; domains that need to distinguish that
    fact should also declare :class:`FieldFiniteCondition` and make this range
    depend on it with ``requires``.
    """

    name: str
    minimum: Quantity | None = None
    maximum: Quantity | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_name(self.name))
        object.__setattr__(self, "requires", _clean_requires(self.name, self.requires))
        for label in ("minimum_inclusive", "maximum_inclusive"):
            if not isinstance(getattr(self, label), bool):
                raise ModelValidityError(
                    f"condition {self.name!r}: {label} must be a boolean"
                )
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
            outcome = _base._within(
                value.summary.minimum,
                minimum=self.minimum,
                maximum=None,
                minimum_inclusive=self.minimum_inclusive,
                maximum_inclusive=True,
                name=self.name,
            )
            if outcome is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
                return outcome
        if self.maximum is not None:
            outcome = _base._within(
                value.summary.maximum,
                minimum=None,
                maximum=self.maximum,
                minimum_inclusive=True,
                maximum_inclusive=self.maximum_inclusive,
                name=self.name,
            )
            if outcome is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
                return outcome
        return ValidityStatus.IN_DOMAIN

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        return self.evaluate(context.get(self.name))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        value = context.get(self.name)
        # The v2 UNKNOWN vocabulary predates typed fields.  Until the reason
        # schema is widened, a non-finite typed record is conservatively kept
        # in the non-actionable bucket rather than misreported as NOT_SUPPLIED.
        if isinstance(value, FieldRecord) and not value.is_finite:
            return UnknownReason.UNREADABLE_SHAPE
        return _typed_reason(context, self.name)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.name})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_RANGE_CONDITION_SCHEMA,
            "name": self.name,
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
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_name(self.name))
        object.__setattr__(self, "requires", _clean_requires(self.name, self.requires))

    def evaluate(self, value: Any) -> ValidityStatus:
        if not isinstance(value, FieldRecord):
            return ValidityStatus.UNKNOWN
        return (
            ValidityStatus.IN_DOMAIN
            if value.is_finite
            else ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        )

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        return self.evaluate(context.get(self.name))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        return _typed_reason(context, self.name)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.name})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_FINITE_CONDITION_SCHEMA,
            "name": self.name,
            "requires": list(self.requires),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldFiniteCondition":
        require_schema(payload, FIELD_FINITE_CONDITION_SCHEMA)
        return cls(
            name=payload["name"],
            requires=tuple(payload.get("requires", ())),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class FieldStructureCondition:
    """Verify the structural facts the current field IR can actually express.

    ``components`` is the flat component count declared by ``FieldDefinition``.
    It covers scalar/vector/tensor-like component cardinality without pretending
    that the current IR knows whether nine components mean a 9-vector or a 3x3
    tensor.  ``spatial_rank`` is derived from the record shape after removing
    that component axis when components > 1.
    """

    name: str
    components: int | None = None
    spatial_rank: int | None = None
    location: FieldLocation | None = None
    mesh_id: str | None = None
    exact_shape: tuple[int, ...] | None = None
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_name(self.name))
        object.__setattr__(self, "requires", _clean_requires(self.name, self.requires))
        if self.components is not None:
            object.__setattr__(
                self, "components", _positive_int(self.components, label="components")
            )
        if self.spatial_rank is not None:
            if isinstance(self.spatial_rank, bool) or not isinstance(self.spatial_rank, int):
                raise ModelValidityError("spatial_rank must be a non-negative int")
            if self.spatial_rank < 0:
                raise ModelValidityError("spatial_rank must be a non-negative int")
        if self.location is not None:
            object.__setattr__(self, "location", FieldLocation(self.location))
        if self.mesh_id is not None:
            mesh_id = str(self.mesh_id).strip()
            if not mesh_id:
                raise ModelValidityError("mesh_id must be non-empty when declared")
            object.__setattr__(self, "mesh_id", mesh_id)
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
            value is None
            for value in (
                self.components,
                self.spatial_rank,
                self.location,
                self.mesh_id,
                self.exact_shape,
            )
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
        return self.evaluate(context.get(self.name))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        return _typed_reason(context, self.name)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.name})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_STRUCTURE_CONDITION_SCHEMA,
            "name": self.name,
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
        shape = payload.get("exact_shape")
        location = payload.get("location")
        return cls(
            name=payload["name"],
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
    """Validity limits over the structured 2-D mesh supported by the core today."""

    name: str
    min_nodes_x: int | None = None
    min_nodes_y: int | None = None
    max_spacing_x: Quantity | None = None
    max_spacing_y: Quantity | None = None
    requires: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_name(self.name))
        object.__setattr__(self, "requires", _clean_requires(self.name, self.requires))
        object.__setattr__(
            self,
            "min_nodes_x",
            _optional_positive_int(self.min_nodes_x, label="min_nodes_x"),
        )
        object.__setattr__(
            self,
            "min_nodes_y",
            _optional_positive_int(self.min_nodes_y, label="min_nodes_y"),
        )
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
            value is None
            for value in (
                self.min_nodes_x,
                self.min_nodes_y,
                self.max_spacing_x,
                self.max_spacing_y,
            )
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
        if self.max_spacing_x is not None:
            if value.spacing_x.compare(self.max_spacing_x) > 0:
                return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        if self.max_spacing_y is not None:
            if value.spacing_y.compare(self.max_spacing_y) > 0:
                return ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        return ValidityStatus.IN_DOMAIN

    def evaluate_in(self, context: Mapping[str, Any]) -> ValidityStatus:
        return self.evaluate(context.get(self.name))

    def explain_in(self, context: Mapping[str, Any]) -> UnknownReason:
        return _typed_reason(context, self.name)

    @property
    def context_keys(self) -> frozenset[str]:
        return frozenset({self.name})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MESH_RESOLUTION_CONDITION_SCHEMA,
            "name": self.name,
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
            min_nodes_x=payload.get("min_nodes_x"),
            min_nodes_y=payload.get("min_nodes_y"),
            max_spacing_x=Quantity.from_dict(sx) if sx else None,
            max_spacing_y=Quantity.from_dict(sy) if sy else None,
            requires=tuple(payload.get("requires", ())),
            description=payload.get("description", ""),
        )


def _register() -> None:
    """Extend the existing wire decoder without changing scalar semantics."""
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
