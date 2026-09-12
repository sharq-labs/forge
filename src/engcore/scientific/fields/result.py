"""A solved field, as the control plane is allowed to hold it.

``ScientificResult.values`` is a mapping of ``Quantity``, and a field is not
one. The alternative this repository already refuses is putting the array in
``diagnostics`` or ``metadata``: DATA-BOUNDARY0 established that bulk data
leaves through a content-addressed reference, and this record is the field-aware
side of that boundary.

A :class:`FieldRecord` is O(1) in the size of the field it names. It carries:

* the field's declaration — meaning, unit, location, support;
* the fingerprint of the support, so the values cannot be re-attached to a
  different one;
* the shape, which the reference deliberately does not carry;
* a summary a reader can act on without resolving anything;
* the reference itself, which names the bytes and nothing about where they are.

It does not carry values, and it never will: the moment it did, every provenance
payload quoting a result would carry a mesh-sized array with it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..results.data_reference import ScientificDataReference
from .definition import FieldDefinition
from .mesh import StructuredMesh

FIELD_SUMMARY_SCHEMA = schema_string("field_summary")
FIELD_RECORD_SCHEMA = schema_string("field_record")


@dataclass(frozen=True)
class FieldSummary:
    """What a reader can learn about a field without resolving its bytes.

    Every entry is a ``Quantity`` in the field's own unit, which is what makes
    this a scientific statement rather than four floats. ``non_finite`` is a
    count rather than a flag: "how many" is the question a reader asks next,
    and a boolean would have to be widened the first time somebody asks it.
    """

    minimum: Quantity
    maximum: Quantity
    mean: Quantity
    l2_norm: Quantity
    non_finite: int = 0

    def __post_init__(self) -> None:
        for label in ("minimum", "maximum", "mean", "l2_norm"):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"field summary {label} must be a Quantity, got "
                    f"{type(value).__name__}"
                )
        count = self.non_finite
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise InvalidScientificProblem(
                f"field summary non_finite must be a non-negative int, got "
                f"{count!r}"
            )
        if self.maximum.magnitude_in(self.minimum.units) < self.minimum.magnitude:
            raise InvalidScientificProblem(
                f"field summary maximum {self.maximum} is below its minimum "
                f"{self.minimum}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_SUMMARY_SCHEMA,
            "minimum": self.minimum.to_dict(),
            "maximum": self.maximum.to_dict(),
            "mean": self.mean.to_dict(),
            "l2_norm": self.l2_norm.to_dict(),
            "non_finite": self.non_finite,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldSummary":
        require_schema(payload, FIELD_SUMMARY_SCHEMA)
        return cls(
            minimum=Quantity.from_dict(payload["minimum"]),
            maximum=Quantity.from_dict(payload["maximum"]),
            mean=Quantity.from_dict(payload["mean"]),
            l2_norm=Quantity.from_dict(payload["l2_norm"]),
            non_finite=payload.get("non_finite", 0),
        )


@dataclass(frozen=True)
class FieldRecord:
    """One solved field: its declaration, its support's identity, and where its bytes are."""

    definition: FieldDefinition
    mesh_fingerprint: str
    shape: tuple[int, ...]
    reference: ScientificDataReference
    summary: FieldSummary

    def __post_init__(self) -> None:
        if not isinstance(self.definition, FieldDefinition):
            raise InvalidScientificProblem(
                f"a field record carries a FieldDefinition, got "
                f"{type(self.definition).__name__}"
            )
        if not isinstance(self.reference, ScientificDataReference):
            raise InvalidScientificProblem(
                f"a field record names its values with a ScientificDataReference, "
                f"got {type(self.reference).__name__}; an array on this record "
                f"would put a mesh-sized payload in every record that quotes it"
            )
        if not isinstance(self.summary, FieldSummary):
            raise InvalidScientificProblem(
                f"a field record carries a FieldSummary, got "
                f"{type(self.summary).__name__}"
            )
        fingerprint = str(self.mesh_fingerprint).strip().lower()
        if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
            raise InvalidScientificProblem(
                f"a field record names its support by fingerprint; got "
                f"{self.mesh_fingerprint!r}"
            )
        object.__setattr__(self, "mesh_fingerprint", fingerprint)

        shape = tuple(self.shape)
        if not shape or any(
            isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in shape
        ):
            raise InvalidScientificProblem(
                f"a field record requires a shape of positive ints, got {self.shape!r}"
            )
        object.__setattr__(self, "shape", shape)

        expected = math.prod(shape)
        if self.reference.count != expected:
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} declares shape {shape} "
                f"({expected} values) and its reference names "
                f"{self.reference.count}; a shape and a count that disagree "
                f"describe two different fields"
            )
        if self.reference.unit != self.definition.unit:
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} is declared in "
                f"{self.definition.unit!r} and its values are named in "
                f"{self.reference.unit!r}"
            )

    # ---- checks a consumer makes -------------------------------------------
    def verify_against(self, mesh: StructuredMesh) -> None:
        """Refuse this record against a support it does not describe."""
        self.definition.require_support(mesh)
        if mesh.fingerprint() != self.mesh_fingerprint:
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} was solved on support "
                f"{self.mesh_fingerprint[:12]}… and was verified against "
                f"{mesh.fingerprint()[:12]}…; same name, different geometry or "
                f"resolution"
            )
        expected = self.definition.expected_shape(mesh)
        if tuple(self.shape) != tuple(expected):
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} carries shape {self.shape} "
                f"and this support expects {expected}"
            )

    @property
    def is_finite(self) -> bool:
        return self.summary.non_finite == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_RECORD_SCHEMA,
            "definition": self.definition.to_dict(),
            "mesh_fingerprint": self.mesh_fingerprint,
            "shape": list(self.shape),
            "reference": self.reference.to_dict(),
            "summary": self.summary.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldRecord":
        require_schema(payload, FIELD_RECORD_SCHEMA)
        shape: Sequence[Any] = payload.get("shape", ())
        return cls(
            definition=FieldDefinition.from_dict(payload["definition"]),
            mesh_fingerprint=payload["mesh_fingerprint"],
            shape=tuple(shape),
            reference=ScientificDataReference.from_dict(payload["reference"]),
            summary=FieldSummary.from_dict(payload["summary"]),
        )
