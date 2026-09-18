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
from typing import Any, ClassVar, Mapping

from ..errors import InvalidScientificProblem
from ..models.definition import BindingIssue, BindingIssueKind
from ..serialization import require_schema_any, schema_string
from ..units.quantity import Quantity, dimensionality
from .dependency import QuantityDependency

#: Bumped to /2 by `source_value`. Additive for a transport, required for a
#: conversion: a /1 record of a conversion carries no input, so the budget it
#: claims cannot be checked against what crossed, and it is refused on read
#: rather than believed.
QUANTITY_TRANSFER_SCHEMA = schema_string("quantity_transfer", 2)
QUANTITY_TRANSFER_SCHEMA_V1 = schema_string("quantity_transfer")
#: Bumped to /3 by `value_origin`, and written only when the origin is not the
#: default: a transfer that read its value out of the record it names states
#: nothing new and keeps its /2 bytes.
QUANTITY_TRANSFER_SCHEMA_V3 = schema_string("quantity_transfer", 3)

#: Where the value in a transfer came from, relative to the record it names.
#:
#: R-61 (I-27 part A): `source_record_id` was required to be non-empty and
#: checked against nothing, and one production crossing in this repository
#: names the record of the problem an ambient condition was imposed ON, while
#: taking the value from the system's configuration -- the quantity is a
#: CONTROL input of that problem and not a number it produced. Both kinds of
#: crossing looked identical, so neither could be checked. A transfer now says
#: which it is, and `check_against_result` asks the named record the matching
#: question.
TRANSFER_VALUE_READ_FROM_THE_RECORD = "read_from_the_record"
TRANSFER_VALUE_CONFIGURED_INPUT = "configured_input"
TRANSFER_VALUE_ORIGINS = (
    TRANSFER_VALUE_READ_FROM_THE_RECORD,
    TRANSFER_VALUE_CONFIGURED_INPUT,
)

#: How far the arriving value may miss the declared budget, relatively.
#: A representation allowance for the multiplication, not a modelling
#: tolerance: a crossing that misses its own declared efficiency by more than
#: this is not rounding, it is a different claim.
BUDGET_TOLERANCE = 1e-9


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
    #: What entered, when the declaration this realizes is a conversion.
    #:
    #: Required for a conversion and refused for a plain transport. A
    #: conversion's efficiency is a claim about a ratio, and a record carrying
    #: only one of the two numbers states nothing checkable -- which is how a
    #: declaration of 0.5 and a crossing that moved all of it would look
    #: identical to a reader.
    source_value: Quantity | None = None
    #: Whether the value was read out of the record named above, or imposed on
    #: the problem that record answers. See ``TRANSFER_VALUE_ORIGINS``.
    value_origin: str = TRANSFER_VALUE_READ_FROM_THE_RECORD

    #: The two declared origins, reachable from the published record itself.
    #: ClassVar, so they are not fields: a caller outside this package holds
    #: this class and nothing else, and a magic string at a call site would be
    #: the unchecked spelling this field exists to replace.
    VALUE_ORIGIN_READ_FROM_THE_RECORD: ClassVar[str] = TRANSFER_VALUE_READ_FROM_THE_RECORD
    VALUE_ORIGIN_CONFIGURED_INPUT: ClassVar[str] = TRANSFER_VALUE_CONFIGURED_INPUT

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

        origin = str(self.value_origin).strip()
        if origin not in TRANSFER_VALUE_ORIGINS:
            raise InvalidScientificProblem(
                f"a quantity transfer of {self.dependency.source_quantity!r} "
                f"declares value_origin {self.value_origin!r}, which is none of "
                f"{TRANSFER_VALUE_ORIGINS}. A record that names its own origin "
                f"in free text cannot be checked against the record it names"
            )
        object.__setattr__(self, "value_origin", origin)

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

        self._check_against_the_declared_budget()

    def _check_against_the_declared_budget(self) -> None:
        """What arrived must be what the declared conversion says arrives.

        THE BINDING. Everything the conversion record checks up to here is
        about its own declared numbers: that an efficiency and its loss paths
        sum to one. That is a statement about the declaration and says nothing
        about the run. A conversion declaring that half the energy arrives,
        realized by a transfer carrying the whole input, satisfies every check
        written before this one -- and every number downstream of it is then
        twice what the record claims.

        So the budget is spent here, against the value that actually crossed.
        """
        conversion = self.dependency.conversion

        if conversion is None:
            if self.source_value is not None:
                raise InvalidScientificProblem(
                    f"transfer of {self.dependency.source_quantity!r} carries "
                    f"a source_value and its declaration is a transport, not "
                    f"a conversion. Nothing changes form across it, so what "
                    f"entered is what arrived and a second number could only "
                    f"disagree with the first"
                )
            return

        if self.source_value is None:
            raise InvalidScientificProblem(
                f"transfer of {self.dependency.source_quantity!r} realizes "
                f"the energy conversion {conversion.name!r} and does not say "
                f"what entered it. The declared efficiency is a ratio, and a "
                f"record carrying only the arriving half states nothing any "
                f"reader can check: a conversion claiming "
                f"{conversion.efficiency!r} and a crossing that moved all of "
                f"it would look identical. Supply source_value"
            )
        if not isinstance(self.source_value, Quantity):
            raise InvalidScientificProblem(
                f"transfer of {self.dependency.source_quantity!r} carries a "
                f"source_value of {type(self.source_value).__name__}; what "
                f"entered a conversion is a Quantity or it is not checkable"
            )

        outcome = conversion.convert(self.source_value)
        if outcome.value is None:
            raise InvalidScientificProblem(
                f"transfer of {self.dependency.source_quantity!r} realizes "
                f"{conversion.name!r}, whose efficiency is not declared "
                f"({outcome.reason}). A crossing whose budget nobody stated "
                f"cannot be realized with a definite value: what arrived "
                f"would be believed on the strength of an assumption nobody "
                f"wrote down"
            )

        arrived = self.value.magnitude_in(conversion.unit_exemplar)
        budgeted = outcome.value.magnitude_in(conversion.unit_exemplar)
        # R-60 (I-27 part A): PURELY RELATIVE, with no floor. The floor used to
        # be one unit of `conversion.unit_exemplar`, and an exemplar is the
        # conversion author's choice of spelling rather than a scale of the
        # physics: pick an exemplar a billion times the crossing and the
        # criterion becomes an absolute one, so a crossing far below one
        # exemplar unit carried the whole input against a declared half and the
        # record then rendered a 50% loss beside a 100% arrival. A scale of zero
        # is reached only when nothing was budgeted and nothing arrived, where
        # the comparison is exact equality -- the limit of the relative rule
        # rather than an exception to it.
        scale = max(abs(budgeted), abs(arrived))
        if abs(arrived - budgeted) > BUDGET_TOLERANCE * scale:
            raise InvalidScientificProblem(
                f"transfer of {self.dependency.source_quantity!r} carries "
                f"{arrived} {conversion.unit_exemplar} where "
                f"{conversion.name!r} budgets "
                f"{budgeted} {conversion.unit_exemplar} -- "
                f"{self.source_value.magnitude_in(conversion.unit_exemplar)} "
                f"in at an efficiency of {conversion.efficiency}. The "
                f"declaration and the crossing disagree about how much "
                f"arrived, and the declaration is the one a reader is given"
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

    @property
    def realized_losses(self) -> Mapping[str, Quantity]:
        """What actually left by each declared loss path, for a report.

        Empty for a transport and for a lossless conversion. This is the half
        of a conversion a reader most needs and could least see: the energy
        that did not arrive is usually another domain's input, and until it is
        a number beside the crossing it is a fraction in a docstring.
        """
        conversion = self.dependency.conversion
        if conversion is None or self.source_value is None:
            return {}
        return dict(conversion.convert(self.source_value).losses)

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

    def check_against_result(self, result: Any) -> tuple[BindingIssue, ...]:
        """Ask the record this transfer names whether it says what the transfer says.

        R-61 (I-27 part A). ``source_record_id`` was required to be non-empty and checked against nothing,
        so a transfer naming any string at all and carrying any value constructed. This is the question a
        reader could not ask, and it is a METHOD rather than a constructor rule because the record does not
        hold the result: a transfer read back from a payload can only be checked by whoever holds the other
        half.

        What it asks depends on what the transfer declares about its own value. For
        ``read_from_the_record`` it asks that the result is the one named, that it carries the source
        quantity, and that the value there is the one that crossed -- the entering value for a conversion,
        the arriving one for a transport. For ``configured_input`` it asks the opposite question: a value
        imposed on the problem the result answers is not an output of it, so a result that DOES produce
        that quantity contradicts the declaration.
        """
        issues: list[BindingIssue] = []
        name = self.dependency.source_quantity
        result_id = str(getattr(result, "result_id", "") or "")
        if result_id != self.source_record_id:
            issues.append(BindingIssue(
                name=name, kind=BindingIssueKind.MISSING,
                detail=(f"the transfer names record {self.source_record_id!r} and this result is "
                        f"{result_id!r}: it is not the record the value is claimed to come from"),
            ))
            return tuple(issues)

        values = getattr(result, "values", {}) or {}
        if self.value_origin == TRANSFER_VALUE_CONFIGURED_INPUT:
            if name in values:
                issues.append(BindingIssue(
                    name=name, kind=BindingIssueKind.WRONG_SOURCE_KIND,
                    detail=(f"the transfer declares {name!r} a configured input of the problem "
                            f"{result_id!r} answers, and that result produces {name!r} as an output"),
                ))
            return tuple(issues)

        if name not in values:
            issues.append(BindingIssue(
                name=name, kind=BindingIssueKind.MISSING,
                detail=(f"record {result_id!r} carries no {name!r}, and the transfer says the value was "
                        f"read out of it"),
            ))
            return tuple(issues)

        stated = values[name]
        if not isinstance(stated, Quantity):
            issues.append(BindingIssue(
                name=name, kind=BindingIssueKind.WRONG_VALUE_TYPE,
                detail=f"record {result_id!r} carries {name!r} as {type(stated).__name__}, not a Quantity",
            ))
            return tuple(issues)

        unit = self.dependency.unit_exemplar
        if dimensionality(stated.units) != dimensionality(unit):
            issues.append(BindingIssue(
                name=name, kind=BindingIssueKind.WRONG_DIMENSION,
                detail=(f"record {result_id!r} carries {name!r} in {stated.units!r} where the declaration "
                        f"names {unit!r}"),
            ))
            return tuple(issues)

        crossed = self.value if self.source_value is None else self.source_value
        if not _agree_relatively(crossed.magnitude_in(unit), stated.magnitude_in(unit)):
            issues.append(BindingIssue(
                name=name, kind=BindingIssueKind.WRONG_VALUE_TYPE,
                detail=(f"the transfer says {crossed.magnitude_in(unit)} {unit} crossed out of record "
                        f"{result_id!r}, which states {stated.magnitude_in(unit)} {unit}"),
            ))
        return tuple(issues)

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            # /3 only when the origin is not the default one, for the reason the
            # dependency's own /3 is conditional: a record that says nothing new
            # keeps its bytes.
            "schema": (
                QUANTITY_TRANSFER_SCHEMA_V3
                if self.value_origin != TRANSFER_VALUE_READ_FROM_THE_RECORD
                else QUANTITY_TRANSFER_SCHEMA
            ),
            "dependency": self.dependency.to_dict(),
            "value": self.value.to_dict(),
            "source_record_id": self.source_record_id,
            "instant": self.instant,
            "source_value": (
                None if self.source_value is None else self.source_value.to_dict()
            ),
            # Derived, and written out because a reader cannot recompute it
            # without the conversion record in hand: where the energy that did
            # not arrive went, as quantities rather than fractions.
            "realized_losses": {
                form: quantity.to_dict()
                for form, quantity in sorted(self.realized_losses.items())
            },
            **(
                {}
                if self.value_origin == TRANSFER_VALUE_READ_FROM_THE_RECORD
                else {"value_origin": self.value_origin}
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityTransfer":
        require_schema_any(
            payload,
            (
                QUANTITY_TRANSFER_SCHEMA_V1,
                QUANTITY_TRANSFER_SCHEMA,
                QUANTITY_TRANSFER_SCHEMA_V3,
            ),
        )
        origin = str(
            payload.get("value_origin", TRANSFER_VALUE_READ_FROM_THE_RECORD)
        ).strip()
        if (
            origin != TRANSFER_VALUE_READ_FROM_THE_RECORD
            and payload["schema"] != QUANTITY_TRANSFER_SCHEMA_V3
        ):
            # A version without the field cannot have meant a non-default
            # origin, and reading one off an older record would be inventing
            # the very declaration whose absence is the finding.
            raise InvalidScientificProblem(
                f"quantity transfer payload declares schema {payload['schema']!r} "
                f"and a value_origin of {origin!r}, which "
                f"{QUANTITY_TRANSFER_SCHEMA_V3!r} introduced"
            )
        source_value = payload.get("source_value")
        # `realized_losses` is deliberately not read back: it is derived from
        # the conversion and the source value, and a record that took it from
        # the payload would let a hand-edited report state a loss the
        # declaration does not imply.
        return cls(
            dependency=QuantityDependency.from_dict(payload["dependency"]),
            value=Quantity.from_dict(payload["value"]),
            source_record_id=payload["source_record_id"],
            instant=payload["instant"],
            source_value=(
                None if source_value is None else Quantity.from_dict(source_value)
            ),
            value_origin=origin,
        )


def _agree_relatively(left: float, right: float) -> bool:
    """One relative criterion, with no absolute floor.

    A scale of zero needs no special case and deliberately does not get one: it is reached only when both
    numbers are zero, and then the comparison is exact equality, which is the limit of the relative rule
    rather than an exception to it.
    """
    scale = max(abs(left), abs(right))
    return abs(left - right) <= BUDGET_TOLERANCE * scale


def _transfers_state_one_value(left: "QuantityTransfer", right: "QuantityTransfer") -> bool:
    """R-61: do two transfers of one declaration at one instant state one value?

    Compared IN THE DECLARATION'S OWN EXEMPLAR UNIT, absolutely, so an interval scale and the absolute one
    cannot differ by the offset between them. The audited rule was dataclass equality over
    ``Quantity(magnitude, units-string)`` plus ``source_record_id``, which refused 300.0 kelvin beside
    26.85 degC as "two different values" -- and printed "300.0 kelvin and 300.0 kelvin" when one value was
    read from two records. Both are one value: a redundancy, not a contradiction. What still refuses is a
    real disagreement, and the source records are what its message names.
    """
    unit = left.dependency.unit_exemplar
    if not _agree_relatively(left.value.magnitude_in(unit), right.value.magnitude_in(unit)):
        return False
    if (left.source_value is None) != (right.source_value is None):
        return False
    if left.source_value is not None and right.source_value is not None:
        entered = left.dependency.unit_exemplar
        if not _agree_relatively(
            left.source_value.magnitude_in(entered), right.source_value.magnitude_in(entered)
        ):
            return False
    return left.value_origin == right.value_origin


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
    instants: dict[tuple[str, str, str, str], QuantityTransfer] = {}
    for transfer in transfers:
        if not isinstance(transfer, QuantityTransfer):
            raise InvalidScientificProblem(
                f"transfers must be QuantityTransfer records, got "
                f"{type(transfer).__name__}"
            )
        # R-61: one instant per declaration in one record. A stale iteration
        # sitting beside the final one is what let a consumer select the stale
        # value, and the canonical order made that the DEFAULT past nine
        # iterations, because 'coupled_iteration:9' sorts after
        # 'coupled_iteration:10'. With one instant per declaration no sort
        # order can pick the stale one, and this file deliberately does not
        # parse the instant, so an order over it is not ours to invent.
        declaration = transfer.key[:4]
        earlier = instants.get(declaration)
        if earlier is not None and earlier.instant != transfer.instant:
            raise InvalidScientificProblem(
                f"two instants of one crossing are in one record for "
                f"{transfer.dependency.source_quantity!r} -> "
                f"{transfer.dependency.target_quantity!r}: "
                f"{earlier.instant!r} carrying {earlier.value} and "
                f"{transfer.instant!r} carrying {transfer.value}. One of them "
                f"is stale, nothing here can say which -- the instant is the "
                f"source's own word and this record does not parse it -- and a "
                f"reader taking the last of them would be choosing by spelling"
            )
        instants.setdefault(declaration, transfer)
        existing = seen.get(transfer.key)
        if existing is None:
            seen[transfer.key] = transfer
            continue
        if existing == transfer:
            continue
        if _transfers_state_one_value(existing, transfer):
            continue
        raise InvalidScientificProblem(
            f"two different values crossed for "
            f"{transfer.dependency.source_quantity!r} -> "
            f"{transfer.dependency.target_quantity!r} at instant "
            f"{transfer.instant!r}: "
            f"{existing.value.magnitude_in(existing.dependency.unit_exemplar)} from record "
            f"{existing.source_record_id!r} and "
            f"{transfer.value.magnitude_in(transfer.dependency.unit_exemplar)} from record "
            f"{transfer.source_record_id!r}, in "
            f"{transfer.dependency.unit_exemplar}. One "
            f"of them is wrong and nothing here can say which"
        )
    return tuple(sorted(seen.values(), key=lambda t: t.key))
