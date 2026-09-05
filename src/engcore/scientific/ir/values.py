"""Typed scientific values.

A scientific input is not always a dimensional quantity. A study legitimately
carries ``material = "aluminum"``, ``steady_state = True`` or
``segment_count = 5`` alongside ``mass = 2 kg``. Representing those as raw
Python objects would reopen the untyped-dictionary hole; representing them
only as Quantities would force fake units onto non-dimensional facts.

So there is a small closed union — and it is closed on purpose. Adding a kind
is a deliberate contract change, not something a caller can do by passing an
arbitrary object.

**Representability is not optimizability.** A categorical parameter can be
declared here today; nothing in this module implies that a search algorithm
can encode it. That remains a separate, explicit decision in the optimizer
adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, ScientificCoreError
from ..serialization import require_schema, schema_string
from ..units.quantity import QUANTITY_SCHEMA, Quantity

INTEGER_VALUE_SCHEMA = schema_string("integer_value")
BOOLEAN_VALUE_SCHEMA = schema_string("boolean_value")
CATEGORICAL_VALUE_SCHEMA = schema_string("categorical_value")


class ValueKind(str, Enum):
    """The closed set of scientific value kinds."""

    QUANTITY = "quantity"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"


@dataclass(frozen=True)
class IntegerValue:
    """A counted or indexed quantity with no physical dimension.

    Distinct from ``Quantity(5, "dimensionless")``: a count is exact and
    discrete, and rounding it would be a modelling error rather than a
    numerical one.
    """

    value: int
    description: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.value, bool):
            # bool is an int subclass in Python; silently accepting it would
            # erase the distinction this union exists to preserve.
            raise InvalidScientificProblem(
                "IntegerValue rejects bool; use BooleanValue"
            )
        if not isinstance(self.value, int):
            raise InvalidScientificProblem(
                f"IntegerValue requires an int, got {type(self.value).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INTEGER_VALUE_SCHEMA,
            "value": int(self.value),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IntegerValue":
        require_schema(payload, INTEGER_VALUE_SCHEMA)
        raw = payload["value"]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise InvalidScientificProblem(
                f"IntegerValue payload must hold an int, got {raw!r}"
            )
        return cls(value=raw, description=payload.get("description", ""))


@dataclass(frozen=True)
class BooleanValue:
    """A declared scientific flag (steady state, linearity, ...)."""

    value: bool
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.value, bool):
            raise InvalidScientificProblem(
                f"BooleanValue requires a bool, got {type(self.value).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BOOLEAN_VALUE_SCHEMA,
            "value": bool(self.value),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BooleanValue":
        require_schema(payload, BOOLEAN_VALUE_SCHEMA)
        raw = payload["value"]
        if not isinstance(raw, bool):
            raise InvalidScientificProblem(
                f"BooleanValue payload must hold a bool, got {raw!r}"
            )
        return cls(value=raw, description=payload.get("description", ""))


@dataclass(frozen=True)
class CategoricalValue:
    """A member of a named category (material, phase, regime, variant).

    ``vocabulary`` is optional but, when supplied, is enforced — a category
    outside its declared vocabulary is a specification error, not data.
    """

    value: str
    vocabulary: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidScientificProblem(
                "CategoricalValue requires a non-empty string"
            )
        object.__setattr__(self, "value", self.value.strip())
        vocabulary = tuple(self.vocabulary)
        if len(set(vocabulary)) != len(vocabulary):
            raise InvalidScientificProblem(
                "CategoricalValue vocabulary contains duplicates"
            )
        object.__setattr__(self, "vocabulary", vocabulary)
        if vocabulary and self.value not in vocabulary:
            raise InvalidScientificProblem(
                f"category {self.value!r} is not in its declared vocabulary "
                f"{sorted(vocabulary)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CATEGORICAL_VALUE_SCHEMA,
            "value": self.value,
            "vocabulary": list(self.vocabulary),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CategoricalValue":
        require_schema(payload, CATEGORICAL_VALUE_SCHEMA)
        return cls(
            value=payload["value"],
            vocabulary=tuple(payload.get("vocabulary", ())),
            description=payload.get("description", ""),
        )


ScientificValue = Quantity | IntegerValue | BooleanValue | CategoricalValue

_VALUE_KINDS: dict[type, ValueKind] = {
    Quantity: ValueKind.QUANTITY,
    IntegerValue: ValueKind.INTEGER,
    BooleanValue: ValueKind.BOOLEAN,
    CategoricalValue: ValueKind.CATEGORICAL,
}

_VALUE_DECODERS = {
    QUANTITY_SCHEMA: Quantity,
    INTEGER_VALUE_SCHEMA: IntegerValue,
    BOOLEAN_VALUE_SCHEMA: BooleanValue,
    CATEGORICAL_VALUE_SCHEMA: CategoricalValue,
}


def is_scientific_value(value: Any) -> bool:
    return type(value) in _VALUE_KINDS


def value_kind(value: Any) -> ValueKind:
    """The kind of a typed scientific value, or an error for anything else."""
    try:
        return _VALUE_KINDS[type(value)]
    except KeyError:
        raise InvalidScientificProblem(
            f"{type(value).__name__} is not a scientific value; supported "
            f"kinds are Quantity, IntegerValue, BooleanValue, CategoricalValue"
        ) from None


def require_scientific_value(value: Any, *, context: str) -> ScientificValue:
    """Validate that ``value`` is a member of the typed union."""
    if not is_scientific_value(value):
        raise InvalidScientificProblem(
            f"{context}: expected a typed scientific value "
            f"(Quantity / IntegerValue / BooleanValue / CategoricalValue), "
            f"got {type(value).__name__}"
        )
    return value


def encode_value(value: ScientificValue) -> dict[str, Any]:
    require_scientific_value(value, context="value encoding")
    return value.to_dict()


def decode_value(payload: Mapping[str, Any]) -> ScientificValue:
    """Rebuild a typed value, dispatching on its recorded schema."""
    if not isinstance(payload, Mapping):
        raise ScientificCoreError(
            f"scientific value payload must be a mapping, got "
            f"{type(payload).__name__}"
        )
    decoder = _VALUE_DECODERS.get(payload.get("schema"))
    if decoder is None:
        raise ScientificCoreError(
            f"unknown scientific value schema {payload.get('schema')!r}"
        )
    return decoder.from_dict(payload)


def as_context_value(value: ScientificValue) -> Any:
    """Plain form used by validity predicates.

    Quantities stay Quantities (range conditions are dimensional); the other
    kinds unwrap to the primitive their predicate expects.
    """
    kind = value_kind(value)
    if kind is ValueKind.QUANTITY:
        return value
    return value.value
