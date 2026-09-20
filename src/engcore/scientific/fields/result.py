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
from ..serialization import require_schema, require_schema_any, schema_string
from ..units.quantity import Quantity
from ..results.data_reference import ScientificDataReference
from .definition import FieldDefinition
from .support import MeshSupport

FIELD_SUMMARY_SCHEMA = schema_string("field_summary")
#: Bumped to /2 by `magnitude_maximum`, and written only when a summary carries
#: one: a scalar field's summary keeps its /1 bytes.
FIELD_SUMMARY_SCHEMA_V2 = schema_string("field_summary", 2)
FIELD_RECORD_SCHEMA = schema_string("field_record")
#: Bumped to /2 by `summary_verified_against`, written only when the summary was
#: derived from the bytes the reference names.
FIELD_RECORD_SCHEMA_V2 = schema_string("field_record", 2)

#: How far a re-derived summary may differ from the recorded one, relatively.
#:
#: R-55 (I-25 part A): a representation allowance, not a modelling tolerance. A
#: sum is order-dependent in floating point and a store may hand the same values
#: back in a different layout; a summary that misses its own bytes by more than
#: a part in a billion is a different summary, not a rounding of this one. The
#: same magnitude this repository already uses for a unit conversion and for an
#: operating point.
SUMMARY_AGREEMENT_RTOL = 1e-9


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
    #: The largest per-node component magnitude, for a field with more than one
    #: component.
    #:
    #: R-55 (I-25 part A): ``minimum`` and ``maximum`` are the envelope over
    #: FLATTENED components, which for a vector field is a box and not a speed:
    #: a velocity of (1, 1, 1) m/s is inside a 1.2 m/s box per component while
    #: its magnitude is 1.732. A bound a declarer writes for a vector field is
    #: the bound on the magnitude, and it could not be recovered from the box,
    #: so it is recorded. ``None`` means nobody computed it, which is the
    #: honest state of every summary written before this field existed.
    magnitude_maximum: Quantity | None = None

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
        # R-55 (I-25 part A): statements the summary makes about itself that
        # cannot be true, and that need none of the field's bytes to refute.
        unit = self.minimum.units
        mean = self.mean.magnitude_in(unit)
        if not (self.minimum.magnitude <= mean <= self.maximum.magnitude_in(unit)):
            raise InvalidScientificProblem(
                f"field summary mean {self.mean} lies outside its own range "
                f"[{self.minimum}, {self.maximum}]; a mean of a set of values "
                f"is one of the places between the smallest and the largest"
            )
        if self.l2_norm.magnitude < 0.0:
            raise InvalidScientificProblem(
                f"field summary l2_norm {self.l2_norm} is negative; a norm is a "
                f"length and a length is not below zero"
            )
        if self.magnitude_maximum is not None:
            if not isinstance(self.magnitude_maximum, Quantity):
                raise InvalidScientificProblem(
                    f"field summary magnitude_maximum must be a Quantity, got "
                    f"{type(self.magnitude_maximum).__name__}"
                )
            if self.magnitude_maximum.magnitude_in(unit) < 0.0:
                raise InvalidScientificProblem(
                    f"field summary magnitude_maximum {self.magnitude_maximum} "
                    f"is negative; a magnitude is a length"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": (
                FIELD_SUMMARY_SCHEMA_V2
                if self.magnitude_maximum is not None
                else FIELD_SUMMARY_SCHEMA
            ),
            "minimum": self.minimum.to_dict(),
            "maximum": self.maximum.to_dict(),
            "mean": self.mean.to_dict(),
            "l2_norm": self.l2_norm.to_dict(),
            "non_finite": self.non_finite,
            **(
                {}
                if self.magnitude_maximum is None
                else {"magnitude_maximum": self.magnitude_maximum.to_dict()}
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldSummary":
        version = require_schema_any(
            payload, (FIELD_SUMMARY_SCHEMA, FIELD_SUMMARY_SCHEMA_V2)
        )
        magnitude = payload.get("magnitude_maximum")
        if magnitude is not None and version != FIELD_SUMMARY_SCHEMA_V2:
            raise InvalidScientificProblem(
                f"field summary payload declares schema {version!r} and carries "
                f"a magnitude_maximum, which {FIELD_SUMMARY_SCHEMA_V2!r} introduced"
            )
        return cls(
            minimum=Quantity.from_dict(payload["minimum"]),
            maximum=Quantity.from_dict(payload["maximum"]),
            mean=Quantity.from_dict(payload["mean"]),
            l2_norm=Quantity.from_dict(payload["l2_norm"]),
            non_finite=payload.get("non_finite", 0),
            magnitude_maximum=(
                None if magnitude is None else Quantity.from_dict(magnitude)
            ),
        )


@dataclass(frozen=True)
class FieldRecord:
    """One solved field: its declaration, its support's identity, and where its bytes are."""

    definition: FieldDefinition
    mesh_fingerprint: str
    shape: tuple[int, ...]
    reference: ScientificDataReference
    summary: FieldSummary
    #: The content digest of the bytes this summary was derived FROM.
    #:
    #: R-55 (I-25 part A): the summary is what every reader acts on without
    #: resolving a mesh-sized array, and nothing bound it to those bytes -- a
    #: record whose values hold a 900 K hot spot carried a summary saying 310 K
    #: with the reference digest unchanged, and the registered validity
    #: predicates answered from it. ``FieldValue.store`` writes this, so a
    #: summary derived from the field it names says so, and a predicate that
    #: would decide from an unbound one returns UNKNOWN instead. Empty means
    #: nobody bound it, which is the honest state of every record written
    #: before this field existed.
    summary_verified_against: str = ""

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

        # R-55 (I-25 part A): the summary is a statement about THIS field, and
        # it was checked against nothing here. A kelvin field summarized in
        # pascal, or counting more non-finite values than it has values, is a
        # record contradicting itself in a way no reader could see.
        declared = Quantity(1.0, self.definition.unit)
        for label in ("minimum", "maximum", "mean", "l2_norm", "magnitude_maximum"):
            entry = getattr(self.summary, label)
            if entry is None:
                continue
            if not entry.is_compatible_with(declared.units):
                raise InvalidScientificProblem(
                    f"field {self.definition.field_id!r} is declared in "
                    f"{self.definition.unit!r} and its summary states {label} as "
                    f"{entry}; a summary of a field is in the field's own dimension"
                )
        if self.summary.non_finite > self.reference.count:
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} names {self.reference.count} "
                f"value(s) and its summary counts {self.summary.non_finite} "
                f"non-finite one(s); a subset is not larger than the set"
            )
        digest = str(self.summary_verified_against).strip().lower()
        if digest and digest != self.reference.digest:
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} says its summary was derived "
                f"from bytes {digest[:12]}… and its reference names "
                f"{self.reference.digest[:12]}…; a binding to other bytes is not "
                f"a binding"
            )
        object.__setattr__(self, "summary_verified_against", digest)

    # ---- checks a consumer makes -------------------------------------------
    def verify_against(self, mesh: MeshSupport) -> None:
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

    @property
    def summary_is_bound_to_its_values(self) -> bool:
        """Whether this record's summary was derived from the bytes it names (R-55).

        What a validity predicate asks before deciding anything from a summary: a summary nobody bound is
        the record's own word about a mesh-sized array nobody read.
        """
        return bool(self.summary_verified_against) and (
            self.summary_verified_against == self.reference.digest
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": (
                FIELD_RECORD_SCHEMA_V2
                if self.summary_verified_against
                else FIELD_RECORD_SCHEMA
            ),
            "definition": self.definition.to_dict(),
            "mesh_fingerprint": self.mesh_fingerprint,
            "shape": list(self.shape),
            "reference": self.reference.to_dict(),
            "summary": self.summary.to_dict(),
            **(
                {}
                if not self.summary_verified_against
                else {"summary_verified_against": self.summary_verified_against}
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldRecord":
        version = require_schema_any(
            payload, (FIELD_RECORD_SCHEMA, FIELD_RECORD_SCHEMA_V2)
        )
        verified = str(payload.get("summary_verified_against", "")).strip()
        if verified and version != FIELD_RECORD_SCHEMA_V2:
            raise InvalidScientificProblem(
                f"field record payload declares schema {version!r} and carries a "
                f"summary_verified_against, which {FIELD_RECORD_SCHEMA_V2!r} introduced"
            )
        shape: Sequence[Any] = payload.get("shape", ())
        return cls(
            definition=FieldDefinition.from_dict(payload["definition"]),
            mesh_fingerprint=payload["mesh_fingerprint"],
            shape=tuple(shape),
            reference=ScientificDataReference.from_dict(payload["reference"]),
            summary=FieldSummary.from_dict(payload["summary"]),
            summary_verified_against=verified,
        )
