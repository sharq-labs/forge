"""One quantity that actually crossed — the realization of a declared dependency.

:class:`~engcore.scientific.composition.dependency.QuantityDependency` states
that a quantity of one problem supplies a quantity of another. It is a
declaration, readable before anything runs, and it deliberately carries no
value, no source record and no instant.

This is the other half, and the half a coupled run needs. When the value moves,
four things are true about the movement and none of them had anywhere to live:

    the value that crossed, the record it was read from, the instant it was
    read at, and the declaration it realizes

Why that matters, in one sentence from the case that forced it: a quantity
declared by one problem reached another problem's applicability assessment by
**matching component identifiers in a dict comprehension**. No record said it
crossed; no reader could tell that the second model's verdict depended on the
first one's declaration; nothing checked that the two sides meant the same
quantity, in the same units, at the same moment. It worked, and every property
that would let anybody verify it was absent.

What this record refuses
------------------------
* a value whose dimension is not the one the declaration named. "Both sides
  mean the same thing" stops being a hope and becomes a check.
* a transfer with no source record. A value that crossed from nowhere is the
  defect ``ProvenanceRecord`` was just taught to refuse about lineage, in the
  one place a number actually moves between domains.
* a transfer with no instant. A coupled loop iterates; a marching solve steps.
  A value read at iteration 3 and used at iteration 7 is a different value, and
  a record that cannot say which one it was cannot be checked by anybody.

What it deliberately does not carry
-----------------------------------
No interpolation, no unit conversion policy, no relaxation factor, no schedule,
no ordering, no staleness rule, no direction of causality beyond the one the
declaration already states. Those belong to a coupling *runtime*. This is the
smallest record that makes an existing crossing declared and checkable, and
``NEEDS.md`` C4 states what a general transfer contract would have to add.

On ``instant``
--------------
A string, in the source's own terms, and deliberately not a float time. The
crossings this repository actually has are indexed by a fixed-point iteration
and by an open-loop stage, neither of which is a time; a marching one would be
indexed by a step. Forcing all three onto a seconds axis would invent a common
clock that no consumer has, and it would be exactly the "general framework
built on the evidence of one consumer" this package's own docstring refuses.
What is enforced is that the instant is *stated*, that it is stated the same
way on both sides of one loop, and that two transfers of the same dependency at
the same instant carry the same value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality
from .dependency import QuantityDependency

QUANTITY_TRANSFER_SCHEMA = schema_string("quantity_transfer")


@dataclass(frozen=True)
class QuantityTransfer:
    """A declared dependency, realized: what crossed, from where, and when."""

    dependency: QuantityDependency
    value: Quantity
    #: The record the value was read out of — a ``ScientificResult.result_id``,
    #: or the run id of whatever produced it. Not the problem id: a problem is
    #: a question, and a question supplies no numbers.
    source_record_id: str
    #: When, in the source's own terms. See the module docstring.
    instant: str

    def __post_init__(self) -> None:
        if not isinstance(self.dependency, QuantityDependency):
            raise InvalidScientificProblem(
                f"a quantity transfer realizes a QuantityDependency, got "
                f"{type(self.dependency).__name__}. A value crossing a domain "
                f"boundary with no declaration behind it is the thing this "
                f"record exists to make impossible"
            )
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem(
                f"a quantity transfer carries a Quantity, got "
                f"{type(self.value).__name__}; a bare number crossing a domain "
                f"boundary carries no unit and no way to check it"
            )
        for label in ("source_record_id", "instant"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise InvalidScientificProblem(
                    f"a quantity transfer of "
                    f"{self.dependency.source_quantity!r} states no {label}. A "
                    f"value that crossed from nowhere, or at no stated moment, "
                    f"cannot be checked by anyone reading the record"
                )
            object.__setattr__(self, label, text)

        expected = dimensionality(self.dependency.unit_exemplar)
        actual = dimensionality(self.value.units)
        if expected != actual:
            raise InvalidScientificProblem(
                f"transfer of {self.dependency.source_quantity!r} from "
                f"{self.dependency.source_problem_id!r} carries "
                f"{self.value.units!r} [{actual}] where the declaration names "
                f"{self.dependency.unit_exemplar!r} [{expected}]. The two sides "
                f"do not mean the same thing"
            )

    # ---- reading -------------------------------------------------------
    @property
    def key(self) -> tuple[str, str, str, str, str]:
        """Identity: which declaration, at which instant."""
        return (
            self.dependency.source_problem_id,
            self.dependency.source_quantity,
            self.dependency.target_problem_id,
            self.dependency.target_quantity,
            self.instant,
        )

    def received_as(self, unit: str) -> Quantity:
        """The value, in the unit the receiving side works in.

        The one sanctioned way to take a crossed value out of its record. It
        converts rather than assuming, so a source reporting on an interval
        scale and a target working on the absolute one cannot silently differ
        by the offset between them -- which is the failure mode a dict of raw
        magnitudes keyed by component identifier has no way to have an opinion
        about.
        """
        return self.value.to(unit)

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": QUANTITY_TRANSFER_SCHEMA,
            "dependency": self.dependency.to_dict(),
            "value": self.value.to_dict(),
            "source_record_id": self.source_record_id,
            "instant": self.instant,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityTransfer":
        require_schema(payload, QUANTITY_TRANSFER_SCHEMA)
        return cls(
            dependency=QuantityDependency.from_dict(payload["dependency"]),
            value=Quantity.from_dict(payload["value"]),
            source_record_id=payload["source_record_id"],
            instant=payload["instant"],
        )


def require_agreeing_transfers(
    transfers: tuple["QuantityTransfer", ...]
) -> tuple["QuantityTransfer", ...]:
    """Deduplicate, and refuse a set that contradicts itself.

    Two transfers of the same declaration at the same instant state one fact.
    If they carry different values, one of the two is wrong and no rule here
    can say which -- so both are refused rather than one being picked by
    whichever was appended last. This is the same position ``ProvenanceRecord``
    takes about two bindings and ``_merged_validity`` takes about two verdicts.
    """
    seen: dict[tuple[str, str, str, str, str], QuantityTransfer] = {}
    for transfer in transfers:
        if not isinstance(transfer, QuantityTransfer):
            raise InvalidScientificProblem(
                f"transfers must be QuantityTransfer records, got "
                f"{type(transfer).__name__}"
            )
        existing = seen.get(transfer.key)
        if existing is None:
            seen[transfer.key] = transfer
            continue
        if existing == transfer:
            continue
        raise InvalidScientificProblem(
            f"two different values crossed for "
            f"{transfer.dependency.source_quantity!r} -> "
            f"{transfer.dependency.target_quantity!r} at instant "
            f"{transfer.instant!r}: {existing.value} and {transfer.value}. One "
            f"of them is wrong and nothing here can say which"
        )
    return tuple(sorted(seen.values(), key=lambda t: t.key))
