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
from ..units.quantity import dimensionality
from .definition import FieldDefinition
from .mesh import CANONICAL_LENGTH, StructuredMesh

FIELD_TRANSFER_SCHEMA = schema_string("field_transfer_contract")


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


def _same_geometry(left: StructuredMesh, right: StructuredMesh) -> bool:
    """Same rectangle in space, whatever the resolution over it."""
    return all(
        abs(
            getattr(left, name).magnitude_in(CANONICAL_LENGTH)
            - getattr(right, name).magnitude_in(CANONICAL_LENGTH)
        )
        <= 1e-12 * max(1.0, abs(getattr(left, name).magnitude_in(CANONICAL_LENGTH)))
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
