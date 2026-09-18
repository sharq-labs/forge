"""What has to be true before one solve's field can be another's input.

``QuantityDependency`` and ``QuantityTransfer`` state a scalar crossing: one
quantity of one problem supplies one quantity of another, checked by dimension.
A field crossing has three more questions in it, and a scalar contract answers
none of them: which support the values sit on, how many there are and where,
and whether the consumer's support is the same one.

The failure this prevents is specific. Two fields of equal length are two
arrays, and an array is assignable to an array — so a 32 x 32 field and a
16 x 64 field, or two 64 x 64 fields over different rectangles, line up
silently under any contract that compares shapes or counts. What must line up
is the *support*, and the support has an identity.

Four verdicts, because "no" has three different meanings here: the supports
already agree; they describe the same geometry at different resolution, so a
declared projection is what would make them agree; they agree and the units
differ by a conversion; or they describe different geometry, which no
interpolation repairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, canonical_magnitude, dimensionality
from .definition import FieldDefinition
from .mesh import CANONICAL_LENGTH, StructuredMesh
from .result import FieldRecord

FIELD_TRANSFER_SCHEMA = schema_string("field_transfer_contract")
FIELD_DEPENDENCY_SCHEMA = schema_string("field_dependency")


class TransferKind(str, Enum):
    """What kind of thing crosses.

    Stated rather than inferred: a consumer expecting a field and handed a
    scalar summary of it is a different mistake from a consumer expecting a
    scalar, and a record that carries neither cannot tell them apart.
    """

    SCALAR_TRANSFER = "scalar_transfer"
    FIELD_TRANSFER = "field_transfer"


class FieldTransferVerdict(str, Enum):
    """Whether the crossing may happen, and if not, what is missing."""

    COMPATIBLE = "compatible"
    REQUIRES_UNIT_CONVERSION = "requires_unit_conversion"
    REQUIRES_PROJECTION = "requires_projection"
    REFUSED = "refused"


@dataclass(frozen=True)
class FieldTransferContract:
    """One producer field, one consumer expectation, and what stands between them."""

    producer: FieldDefinition
    producer_fingerprint: str
    consumer: FieldDefinition
    consumer_fingerprint: str
    kind: TransferKind
    verdict: FieldTransferVerdict
    reason: str

    def __post_init__(self) -> None:
        for label in ("producer", "consumer"):
            value = getattr(self, label)
            if not isinstance(value, FieldDefinition):
                raise InvalidScientificProblem(
                    f"a field transfer contract's {label} is a FieldDefinition, "
                    f"got {type(value).__name__}"
                )
        object.__setattr__(self, "kind", TransferKind(self.kind))
        object.__setattr__(self, "verdict", FieldTransferVerdict(self.verdict))
        for label in ("producer_fingerprint", "consumer_fingerprint"):
            text = str(getattr(self, label)).strip().lower()
            if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
                raise InvalidScientificProblem(
                    f"a field transfer contract names each support by "
                    f"fingerprint; {label} is {getattr(self, label)!r}"
                )
            object.__setattr__(self, label, text)
        if not str(self.reason).strip():
            raise InvalidScientificProblem(
                "a field transfer contract states why it reached its verdict"
            )
        self._require_the_verdict_follows_from_the_records()

    #: How much crossability each verdict claims, weakest first. A contract may
    #: state a verdict no STRONGER than its own records permit; a weaker one is
    #: always allowed, because a caller may refuse for a reason the record does
    #: not carry and this record must stay able to say so.
    _STRENGTH = {
        FieldTransferVerdict.REFUSED: 0,
        FieldTransferVerdict.REQUIRES_PROJECTION: 1,
        FieldTransferVerdict.REQUIRES_UNIT_CONVERSION: 2,
        FieldTransferVerdict.COMPATIBLE: 3,
    }

    def _require_the_verdict_follows_from_the_records(self) -> None:
        """R-63 (I-25 part B): re-derive the verdict parts this record already carries.

        The contract holds both field definitions and both support fingerprints -- which is exactly what
        :func:`check_field_transfer` decides from, apart from the geometry behind the fingerprints. It
        checked the types, the fingerprint format and a non-empty reason, and never the verdict: a payload
        computed as REFUSED for 1 component against 3, kelvin against pascal, read back as COMPATIBLE with
        ``may_cross_directly`` True, and direct construction with invented fingerprints did the same.

        Only a verdict claiming MORE than the records allow is refused. What cannot be re-derived here is
        which REASON a refusal rests on: two supports covering different rectangles and two resolutions of
        one rectangle both show up as two different fingerprints, and telling them apart needs the meshes.
        """
        ceiling = FieldTransferVerdict.COMPATIBLE
        because = ""
        if self.producer.components != self.consumer.components:
            ceiling, because = (
                FieldTransferVerdict.REFUSED,
                f"the producer has {self.producer.components} component(s) and the consumer expects "
                f"{self.consumer.components}",
            )
        elif dimensionality(self.producer.unit) != dimensionality(self.consumer.unit):
            ceiling, because = (
                FieldTransferVerdict.REFUSED,
                f"the producer is measured in {self.producer.unit!r} and the consumer expects "
                f"{self.consumer.unit!r}",
            )
        elif self.producer_fingerprint != self.consumer_fingerprint:
            ceiling, because = (
                FieldTransferVerdict.REQUIRES_PROJECTION,
                f"the two supports are {self.producer_fingerprint[:12]}… and "
                f"{self.consumer_fingerprint[:12]}…, which are not one support",
            )
        elif self.producer.location is not self.consumer.location:
            ceiling, because = (
                FieldTransferVerdict.REQUIRES_PROJECTION,
                f"the producer stores values at {self.producer.location.value}s and the consumer expects "
                f"{self.consumer.location.value}s",
            )
        elif self.producer.unit != self.consumer.unit:
            ceiling, because = (
                FieldTransferVerdict.REQUIRES_UNIT_CONVERSION,
                f"one support and one dimension in two units ({self.producer.unit!r} against "
                f"{self.consumer.unit!r})",
            )
        if self._STRENGTH[self.verdict] > self._STRENGTH[ceiling]:
            raise InvalidScientificProblem(
                f"a field transfer contract states {self.verdict.value!r} and its own records permit no "
                f"more than {ceiling.value!r}: {because}. A verdict is what the record's reader acts on, "
                f"and this one claims a crossing the two declarations it carries do not allow"
            )

    @property
    def may_cross_directly(self) -> bool:
        """True only for COMPATIBLE. Everything else needs a declared step."""
        return self.verdict is FieldTransferVerdict.COMPATIBLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_TRANSFER_SCHEMA,
            "producer": self.producer.to_dict(),
            "producer_fingerprint": self.producer_fingerprint,
            "consumer": self.consumer.to_dict(),
            "consumer_fingerprint": self.consumer_fingerprint,
            "kind": self.kind.value,
            "verdict": self.verdict.value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldTransferContract":
        require_schema(payload, FIELD_TRANSFER_SCHEMA)
        return cls(
            producer=FieldDefinition.from_dict(payload["producer"]),
            producer_fingerprint=payload["producer_fingerprint"],
            consumer=FieldDefinition.from_dict(payload["consumer"]),
            consumer_fingerprint=payload["consumer_fingerprint"],
            kind=TransferKind(payload["kind"]),
            verdict=FieldTransferVerdict(payload["verdict"]),
            reason=payload["reason"],
        )


@dataclass(frozen=True)
class FieldDependency:
    """``target_problem.target_field`` is supplied by ``source_problem.source_field``.

    The same statement ``QuantityDependency`` makes for a scalar, for a thing
    that has a support. It is a *declaration*: it says what is expected to
    cross and in what form, and resolves nothing.

    ``kind`` is the field this record exists for. A consumer that wants the
    field and a consumer that wants a number summarising it are two different
    consumers, and until something states which, a produced field and its own
    mean are interchangeable at the boundary — a summary silently standing in
    for the distribution it summarises is the failure this names.
    """

    source_problem_id: str
    source_field: str
    target_problem_id: str
    target_field: str
    kind: TransferKind = TransferKind.FIELD_TRANSFER
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        for label in (
            "source_problem_id",
            "source_field",
            "target_problem_id",
            "target_field",
        ):
            text = str(getattr(self, label)).strip()
            if not text:
                raise InvalidScientificProblem(
                    f"a field dependency requires a non-empty {label}"
                )
            object.__setattr__(self, label, text)
        object.__setattr__(self, "kind", TransferKind(self.kind))
        object.__setattr__(
            self,
            "name",
            str(self.name).strip()
            or f"{self.source_problem_id}.{self.source_field}"
            f"->{self.target_problem_id}.{self.target_field}",
        )

    def admit(self, offered: Any) -> None:
        """Refuse a crossing whose *form* is not the form that was declared.

        Before any question about supports, units or resolution: is this even
        the kind of thing the consumer asked for? A ``FieldRecord`` offered to
        a scalar dependency and a ``Quantity`` offered to a field dependency
        are both wrong, and neither is caught by any check that compares
        dimensions — the mean of a temperature field is a temperature.
        """
        if self.kind is TransferKind.FIELD_TRANSFER:
            if isinstance(offered, Quantity):
                raise InvalidScientificProblem(
                    f"dependency {self.name!r} declares a field transfer and was "
                    f"offered the scalar {offered}; a summary of a field is not "
                    f"the field, and carries the same dimension as one"
                )
            if not isinstance(offered, FieldRecord):
                raise InvalidScientificProblem(
                    f"dependency {self.name!r} declares a field transfer and was "
                    f"offered {type(offered).__name__}"
                )
            if offered.definition.field_id != self.source_field:
                raise InvalidScientificProblem(
                    f"dependency {self.name!r} names {self.source_field!r} as its "
                    f"source and was offered {offered.definition.field_id!r}"
                )
            return
        if isinstance(offered, FieldRecord):
            raise InvalidScientificProblem(
                f"dependency {self.name!r} declares a scalar transfer and was "
                f"offered the field {offered.definition.field_id!r} on "
                f"{offered.shape}; which number of it was meant is not stated "
                f"anywhere, and picking one here would be inventing the answer"
            )
        if not isinstance(offered, Quantity):
            raise InvalidScientificProblem(
                f"dependency {self.name!r} declares a scalar transfer and was "
                f"offered {type(offered).__name__}"
            )

    def resolve(
        self,
        producer: FieldDefinition,
        producer_mesh: StructuredMesh,
        consumer: FieldDefinition,
        consumer_mesh: StructuredMesh,
    ) -> FieldTransferContract:
        """The contract for this declaration's two sides.

        Refuses a producer or consumer that is not the field this dependency
        names, so a contract cannot be obtained for one pair and quoted for
        another.
        """
        if self.kind is not TransferKind.FIELD_TRANSFER:
            raise InvalidScientificProblem(
                f"dependency {self.name!r} declares a {self.kind.value} and has "
                f"no field contract to resolve"
            )
        for label, definition, expected in (
            ("source", producer, self.source_field),
            ("target", consumer, self.target_field),
        ):
            if definition.field_id != expected:
                raise InvalidScientificProblem(
                    f"dependency {self.name!r} names {expected!r} as its {label} "
                    f"and was given {definition.field_id!r}"
                )
        return check_field_transfer(producer, producer_mesh, consumer, consumer_mesh)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_DEPENDENCY_SCHEMA,
            "source_problem_id": self.source_problem_id,
            "source_field": self.source_field,
            "target_problem_id": self.target_problem_id,
            "target_field": self.target_field,
            "kind": self.kind.value,
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldDependency":
        require_schema(payload, FIELD_DEPENDENCY_SCHEMA)
        return cls(
            source_problem_id=payload["source_problem_id"],
            source_field=payload["source_field"],
            target_problem_id=payload["target_problem_id"],
            target_field=payload["target_field"],
            kind=TransferKind(payload["kind"]),
            name=payload.get("name", ""),
            description=payload.get("description", ""),
        )


def _same_geometry(left: StructuredMesh, right: StructuredMesh) -> bool:
    """Same rectangle in space, whatever the resolution over it.

    THE SAME RULE THE FINGERPRINT READS (I-23, R-62). This compared the raw conversions with a
    tolerance of ``1e-12 * max(1.0, |x|)``, which below one metre is an ABSOLUTE 1e-12 m: two
    supports 10 nm and 10.0005 nm wide -- 5e-5 apart in relative terms -- answered "the same
    rectangle", and `check_field_transfer` then offered a declared projection for a difference no
    projection can close. A separate tolerance here is also a second rule that can disagree with
    the identity; `canonical_magnitude` is the one rule, so two meshes are the same rectangle
    exactly when the origin and extent parts of their fingerprints agree.
    """
    return all(
        canonical_magnitude(getattr(left, name), CANONICAL_LENGTH)
        == canonical_magnitude(getattr(right, name), CANONICAL_LENGTH)
        for name in ("length_x", "length_y", "origin_x", "origin_y")
    )


def check_field_transfer(
    producer: FieldDefinition,
    producer_mesh: StructuredMesh,
    consumer: FieldDefinition,
    consumer_mesh: StructuredMesh,
) -> FieldTransferContract:
    """Decide what stands between a produced field and a consumer's expectation.

    The order of the tests is the order the answers matter in. A dimension
    mismatch is not repairable by any amount of interpolation, so it is refused
    first; different geometry likewise. Only then is resolution asked about,
    because that is the one difference a declared projection can close.
    """
    producer.require_support(producer_mesh)
    consumer.require_support(consumer_mesh)

    def contract(verdict: FieldTransferVerdict, reason: str) -> FieldTransferContract:
        return FieldTransferContract(
            producer=producer,
            producer_fingerprint=producer_mesh.fingerprint(),
            consumer=consumer,
            consumer_fingerprint=consumer_mesh.fingerprint(),
            kind=TransferKind.FIELD_TRANSFER,
            verdict=verdict,
            reason=reason,
        )

    if producer.components != consumer.components:
        return contract(
            FieldTransferVerdict.REFUSED,
            f"the producer has {producer.components} component(s) and the "
            f"consumer expects {consumer.components}; these are different kinds "
            f"of field, not two resolutions of one",
        )
    if dimensionality(producer.unit) != dimensionality(consumer.unit):
        return contract(
            FieldTransferVerdict.REFUSED,
            f"the producer is measured in {producer.unit!r} and the consumer "
            f"expects {consumer.unit!r}; no projection repairs a dimension",
        )
    if not _same_geometry(producer_mesh, consumer_mesh):
        return contract(
            FieldTransferVerdict.REFUSED,
            f"support {producer_mesh.mesh_id!r} covers a different rectangle "
            f"than {consumer_mesh.mesh_id!r}; values of one geometry are not "
            f"values of another",
        )
    if producer.location is not consumer.location:
        return contract(
            FieldTransferVerdict.REQUIRES_PROJECTION,
            f"the producer stores values at {producer.location.value}s and the "
            f"consumer expects {consumer.location.value}s on the same geometry; "
            f"moving between them is an interpolation and must be declared",
        )
    if producer_mesh.fingerprint() != consumer_mesh.fingerprint():
        return contract(
            FieldTransferVerdict.REQUIRES_PROJECTION,
            f"one geometry at two resolutions "
            f"({producer_mesh.nodes_x}x{producer_mesh.nodes_y} against "
            f"{consumer_mesh.nodes_x}x{consumer_mesh.nodes_y}); a declared "
            f"projection is what makes these comparable, and matching lengths "
            f"would not",
        )
    if producer.unit != consumer.unit:
        return contract(
            FieldTransferVerdict.REQUIRES_UNIT_CONVERSION,
            f"one support and one dimension, in two units "
            f"({producer.unit!r} against {consumer.unit!r}); a conversion is "
            f"sufficient here and is still a step somebody has to take",
        )
    return contract(
        FieldTransferVerdict.COMPATIBLE,
        f"one support, one location, one unit: "
        f"{producer_mesh.fingerprint()[:12]}… in {producer.unit!r} at "
        f"{producer.location.value}s",
    )
