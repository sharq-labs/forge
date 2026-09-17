"""Uncertainty that crosses the same declared boundary as a quantity.

``QuantityTransfer`` already makes a cross-domain value explicit: which
quantity moved, from which result, at which instant, under which declared
conversion. Uncertainty must follow that exact record rather than being copied
through a parallel dictionary keyed by a coincidentally matching name.

This belongs in :mod:`engcore.uq`, not in the scientific composition package:
composition declares that a quantity crossed; UQ consumes that declaration and
propagates evidence about uncertainty across it. Keeping those responsibilities
separate also preserves the composition package's intentionally pinned surface.

The module propagates the uncertainty representations the core already knows:
UNKNOWN stays UNKNOWN; STANDARD uncertainty is converted as a delta and scaled
by deterministic declared conversion efficiency; INTERVAL uncertainty keeps
absolute-bound conversion semantics. It invents no distribution, correlation,
or efficiency uncertainty the transfer record does not carry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..scientific.composition.transfer import BUDGET_TOLERANCE, QuantityTransfer
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind
from ..scientific.serialization import require_schema_any, schema_string
from ..scientific.units.quantity import Quantity
from ..scientific.units.validation import require_same_dimension

UNCERTAINTY_TRANSFER_SCHEMA = schema_string("uncertainty_transfer")
#: Bumped to /2 by `completeness`, and written only when the propagation was
#: NOT complete: a record with nothing missing keeps its /1 bytes.
UNCERTAINTY_TRANSFER_SCHEMA_V2 = schema_string("uncertainty_transfer", 2)

#: What the propagated width leaves out, said in the record rather than in a note.
#:
#: R-58 (I-27 part B): a conversion's efficiency was treated as exact, and the
#: only sign of it was prose in ``notes``. A consumer reading a standard
#: uncertainty had no way to know the number it held was a LOWER BOUND on the
#: width -- which is what it is when a factor the value passed through carries
#: an uncertainty nobody declared.
TRANSFER_COMPLETE = "complete"
TRANSFER_LOWER_BOUND_EFFICIENCY = "lower_bound_efficiency_uncertainty_undeclared"
TRANSFER_COMPLETENESS = (TRANSFER_COMPLETE, TRANSFER_LOWER_BOUND_EFFICIENCY)

#: How far two spellings of one value may differ and still be the same value:
#: the composition package's own allowance for one unit conversion, reused
#: rather than a second number.
_MEETING_TOLERANCE = BUDGET_TOLERANCE


def _delta_magnitude_in(value: Quantity, unit: str) -> float:
    """Convert an uncertainty width using scale only, not an absolute offset."""
    require_same_dimension(
        value,
        Quantity(1.0, unit),
        context="uncertainty delta conversion",
    )
    one = Quantity(1.0, value.units).magnitude_in(unit)
    zero = Quantity(0.0, value.units).magnitude_in(unit)
    return float(value.magnitude) * abs(one - zero)


def _source_unit(transfer: QuantityTransfer) -> str:
    if transfer.source_value is not None:
        return transfer.source_value.units
    return transfer.dependency.unit_exemplar


def _agree_relatively(left: float, right: float) -> bool:
    """One relative criterion, with no absolute floor; a scale of zero is exact equality (R-60's rule)."""
    scale = max(abs(left), abs(right))
    return abs(left - right) <= _MEETING_TOLERANCE * scale


def _entering_value(transfer: QuantityTransfer) -> Quantity:
    """What the uncertainty handed in is an uncertainty OF.

    For a conversion that is the value that ENTERED it: the source uncertainty describes the input, and the
    propagation is what carries it across. For a transport nothing changes form, so the crossed value is
    both.
    """
    if transfer.source_value is not None:
        return transfer.source_value
    return transfer.value


def _require_the_interval_contains_the_value(
    transfer: QuantityTransfer, source_uncertainty: Uncertainty
) -> None:
    """R-58 claim (a): an interval that does not contain its own value is another quantity's interval.

    The audited record propagated [10, 11] K for a crossing of 350 K and round-tripped. Containment is
    checked ABSOLUTELY, in the interval's own unit, so an interval scale and an absolute one cannot differ
    by the offset between them.
    """
    lower, upper = source_uncertainty.lower, source_uncertainty.upper
    if lower is None or upper is None:  # pragma: no cover - the record refuses this at construction
        return
    entering = _entering_value(transfer)
    unit = lower.units
    require_same_dimension(
        entering, lower, context="cross-domain interval containment"
    )
    value = entering.magnitude_in(unit)
    low = lower.magnitude_in(unit)
    high = upper.magnitude_in(unit)
    inside = (low <= value <= high) or _agree_relatively(value, low) or _agree_relatively(value, high)
    if not inside:
        raise InvalidScientificProblem(
            f"the interval [{low}, {high}] {unit} does not contain "
            f"{value} {unit}, the value that crossed for "
            f"{transfer.dependency.source_quantity!r} at {transfer.instant}. An "
            f"interval that does not contain its own value is not a statement "
            f"about that value, and propagating it would carry another "
            f"quantity's uncertainty across this crossing"
        )


def _transfer_reference_candidates(
    transfer: QuantityTransfer, upstream: "QuantityTransfer | None" = None
) -> tuple[str, ...]:
    """Everything the crossing itself names, for an attribution to be one of.

    ``upstream`` is the crossing that FEEDS this one inside a chain. Its attribution is what this module
    itself wrote one step earlier, and a chain is exactly the case where the uncertainty entering a
    crossing legitimately came from the crossing before it -- which the chain has already required to meet
    this one by name, by instant and by value.
    """
    dependency = transfer.dependency
    candidates = {
        transfer.source_record_id,
        dependency.source_problem_id,
        dependency.source_quantity,
        f"{dependency.source_problem_id}.{dependency.source_quantity}",
        dependency.name,
    }
    if upstream is not None:
        candidates.add(f"transfer:{upstream.source_record_id}")
    return tuple(sorted(candidate for candidate in candidates if str(candidate).strip()))


def _require_the_uncertainty_names_the_source(
    transfer: QuantityTransfer,
    source_uncertainty: Uncertainty,
    upstream: "QuantityTransfer | None" = None,
) -> None:
    """R-58 claims (b) and (c): the handed-in uncertainty was tied to the crossing by nothing.

    A 1e-6 K uncertainty from another run, or one attributed to 'some-other-quantity', was accepted and
    then relabelled as coming from this crossing's source record. An attribution is accepted when the
    crossing itself names it -- the source record id, the source problem, the source quantity, or the
    declaration's own name.
    """
    attribution = str(source_uncertainty.source or "").strip()
    candidates = _transfer_reference_candidates(transfer, upstream)
    if not attribution or not any(candidate in attribution for candidate in candidates):
        raise InvalidScientificProblem(
            f"the source uncertainty is attributed to {source_uncertainty.source!r}, which names nothing "
            f"this crossing names ({', '.join(candidates)}). An uncertainty bound to nothing is the "
            f"parallel dictionary keyed by a coincidentally matching name that this record exists to "
            f"replace: it would be propagated across the crossing and then read as the crossing's own"
        )


def _completeness_of(transfer: QuantityTransfer, source_uncertainty: Uncertainty) -> str:
    """Whether the propagated width leaves anything out, as a word in the record.

    A transport has no factor, so nothing is missing. A conversion whose efficiency declares no uncertainty
    leaves that uncertainty out of the width, which makes the width a LOWER BOUND; and an INTERVAL keeps
    absolute-bound semantics, so a declared efficiency uncertainty is not combined into it either -- doing
    that needs a distribution nobody declared.
    """
    conversion = transfer.dependency.conversion
    if conversion is None or conversion.efficiency is None:
        return TRANSFER_COMPLETE
    if conversion.efficiency_uncertainty is None:
        return TRANSFER_LOWER_BOUND_EFFICIENCY
    if source_uncertainty.kind is UncertaintyKind.INTERVAL:
        return TRANSFER_LOWER_BOUND_EFFICIENCY
    return TRANSFER_COMPLETE


def _attribution(transfer: QuantityTransfer, source_uncertainty: Uncertainty) -> str:
    """R-58 claim (b): BOTH provenances, because a propagated uncertainty has two.

    What it was an uncertainty of, and the crossing it came through. Writing only the second is what made
    another quantity's uncertainty read as this run's.
    """
    return f"transfer:{transfer.source_record_id}|from:{source_uncertainty.source}"


def _factor(transfer: QuantityTransfer) -> float:
    conversion = transfer.dependency.conversion
    if conversion is None:
        return 1.0
    if conversion.efficiency is None:
        raise InvalidScientificProblem(
            f"cannot propagate uncertainty across conversion {conversion.name!r}: "
            "its efficiency is undeclared, so the transferred quantity is not "
            "a deterministic mapping the UQ layer can propagate through"
        )
    return float(conversion.efficiency)


@dataclass(frozen=True)
class UncertaintyTransfer:
    """The uncertainty counterpart of one exact :class:`QuantityTransfer`."""

    transfer: QuantityTransfer
    source_uncertainty: Uncertainty
    uncertainty: Uncertainty
    #: What the propagated width leaves out. See ``TRANSFER_COMPLETENESS``. It
    #: is derived from the transfer and the source uncertainty, and a record
    #: that states another value is refused rather than corrected.
    completeness: str = TRANSFER_COMPLETE
    #: The crossing that FED this one, inside a chain.
    #:
    #: R-58: a chain is the one case where the uncertainty entering a crossing
    #: legitimately came from the crossing before it, carrying that crossing's
    #: attribution rather than this one's. The record says which crossing that
    #: was, so the attribution rule can be applied to a chain link by reading
    #: the record rather than by trusting the caller who built it.
    upstream: QuantityTransfer | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.transfer, QuantityTransfer):
            raise InvalidScientificProblem("uncertainty transfer requires QuantityTransfer")
        if not isinstance(self.source_uncertainty, Uncertainty):
            raise InvalidScientificProblem("source_uncertainty must be Uncertainty")
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem("uncertainty must be Uncertainty")
        if self.upstream is not None and not isinstance(self.upstream, QuantityTransfer):
            raise InvalidScientificProblem("upstream must be a QuantityTransfer when given")
        expected = propagate_transfer_uncertainty(
            self.transfer,
            self.source_uncertainty,
            upstream=self.upstream,
        )
        if expected != self.uncertainty:
            raise InvalidScientificProblem(
                "uncertainty transfer does not follow from its QuantityTransfer "
                "and source uncertainty"
            )
        derived = _completeness_of(self.transfer, self.source_uncertainty)
        if str(self.completeness) != derived:
            raise InvalidScientificProblem(
                f"uncertainty transfer states completeness "
                f"{self.completeness!r} where the transfer and the source "
                f"uncertainty give {derived!r}. What a propagated width leaves "
                f"out follows from the crossing, and a record may not say "
                f"otherwise about its own arithmetic"
            )

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return self.transfer.key

    def to_dict(self) -> dict[str, Any]:
        return {
            # /2 only when something IS missing: a complete record says nothing
            # new and keeps its /1 bytes.
            "schema": (
                UNCERTAINTY_TRANSFER_SCHEMA
                if self.completeness == TRANSFER_COMPLETE and self.upstream is None
                else UNCERTAINTY_TRANSFER_SCHEMA_V2
            ),
            "transfer": self.transfer.to_dict(),
            "source_uncertainty": self.source_uncertainty.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
            **(
                {}
                if self.completeness == TRANSFER_COMPLETE
                else {"completeness": self.completeness}
            ),
            **({} if self.upstream is None else {"upstream": self.upstream.to_dict()}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyTransfer":
        version = require_schema_any(
            payload, (UNCERTAINTY_TRANSFER_SCHEMA, UNCERTAINTY_TRANSFER_SCHEMA_V2)
        )
        completeness = str(payload.get("completeness", TRANSFER_COMPLETE)).strip()
        upstream = payload.get("upstream")
        if upstream is not None and version != UNCERTAINTY_TRANSFER_SCHEMA_V2:
            raise InvalidScientificProblem(
                f"uncertainty transfer payload declares schema {version!r} and "
                f"carries an upstream crossing, which "
                f"{UNCERTAINTY_TRANSFER_SCHEMA_V2!r} introduced"
            )
        if completeness != TRANSFER_COMPLETE and version != UNCERTAINTY_TRANSFER_SCHEMA_V2:
            raise InvalidScientificProblem(
                f"uncertainty transfer payload declares schema {version!r} and "
                f"a completeness of {completeness!r}, which "
                f"{UNCERTAINTY_TRANSFER_SCHEMA_V2!r} introduced"
            )
        if completeness not in TRANSFER_COMPLETENESS:
            raise InvalidScientificProblem(
                f"uncertainty transfer payload declares completeness "
                f"{completeness!r}, which is none of {TRANSFER_COMPLETENESS}"
            )
        return cls(
            transfer=QuantityTransfer.from_dict(payload["transfer"]),
            source_uncertainty=Uncertainty.from_dict(payload["source_uncertainty"]),
            uncertainty=Uncertainty.from_dict(payload["uncertainty"]),
            completeness=completeness,
            upstream=(
                None if upstream is None else QuantityTransfer.from_dict(upstream)
            ),
        )


def propagate_transfer_uncertainty(
    transfer: QuantityTransfer,
    source_uncertainty: Uncertainty,
    *,
    upstream: QuantityTransfer | None = None,
) -> Uncertainty:
    """Propagate one uncertainty through the deterministic transfer mapping."""
    if not isinstance(transfer, QuantityTransfer):
        raise InvalidScientificProblem("propagation requires QuantityTransfer")
    if not isinstance(source_uncertainty, Uncertainty):
        raise InvalidScientificProblem("propagation requires Uncertainty")

    if source_uncertainty.kind is not UncertaintyKind.UNKNOWN:
        # An UNKNOWN uncertainty asserts nothing about any value, so there is
        # nothing to bind and nothing to contain; it propagates as the honest
        # absence it already is, with the source's own words carried in a note.
        _require_the_uncertainty_names_the_source(transfer, source_uncertainty, upstream)
    if source_uncertainty.kind is UncertaintyKind.INTERVAL:
        _require_the_interval_contains_the_value(transfer, source_uncertainty)

    conversion = transfer.dependency.conversion
    method_prefix = "cross_domain_transport"
    if conversion is not None:
        method_prefix = f"cross_domain_conversion:{conversion.name}"

    if source_uncertainty.kind is UncertaintyKind.UNKNOWN:
        return Uncertainty.unknown(
            notes=(
                f"uncertainty remained unknown while transferring "
                f"{transfer.dependency.source_problem_id}."
                f"{transfer.dependency.source_quantity} -> "
                f"{transfer.dependency.target_problem_id}."
                f"{transfer.dependency.target_quantity} at {transfer.instant}; "
                f"source said: {source_uncertainty.notes or 'not evaluated'}"
            )
        )

    factor = _factor(transfer)
    source_unit = _source_unit(transfer)
    target_unit = transfer.value.units

    if source_uncertainty.kind is UncertaintyKind.STANDARD:
        standard = source_uncertainty.standard_uncertainty
        assert standard is not None
        require_same_dimension(
            standard,
            Quantity(1.0, source_unit),
            context="cross-domain standard uncertainty",
        )
        source_delta = _delta_magnitude_in(standard, source_unit) * abs(factor)
        efficiency_note = (
            "conversion efficiency treated as deterministic because the "
            "conversion record carries no uncertainty for it"
        )
        width = _efficiency_width(transfer)
        if width is not None:
            # First-order propagation of a product, in RELATIVE terms: the only
            # combination a record carrying two standard uncertainties supports.
            # It assumes the efficiency's uncertainty is independent of the
            # input's, which is RECORDED here and in the method rather than
            # established -- nothing in these records establishes independence.
            entering = _entering_value(transfer).magnitude_in(source_unit)
            if entering != 0.0:
                relative_input = _delta_magnitude_in(standard, source_unit) / abs(entering)
                relative_efficiency = width / abs(factor)
                combined = math.sqrt(relative_input ** 2 + relative_efficiency ** 2)
                source_delta = combined * abs(entering * factor)
            efficiency_note = (
                f"the declared efficiency uncertainty {width} was combined in "
                f"quadrature with the input's, which assumes the two are "
                f"independent; that independence is recorded here and is "
                f"established nowhere"
            )
        as_source = Quantity(source_delta, source_unit)
        propagated_delta = _delta_magnitude_in(as_source, target_unit)
        propagated = Quantity(propagated_delta, target_unit)
        return Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=propagated,
            source=_attribution(transfer, source_uncertainty),
            source_kind=source_uncertainty.source_kind,  # CORE-016: a transfer changes units, not what it is
            method=(
                method_prefix
                if _efficiency_width(transfer) is None
                else f"{method_prefix}+efficiency_uncertainty_in_quadrature"
            ),
            notes=(
                f"propagated from {source_uncertainty.method or 'declared source method'}; "
                "standard uncertainty was converted as a delta (scale only); "
                f"{efficiency_note}"
            ),
        )

    if source_uncertainty.kind is UncertaintyKind.INTERVAL:
        lower, upper = source_uncertainty.lower, source_uncertainty.upper
        assert lower is not None and upper is not None
        require_same_dimension(
            lower,
            Quantity(1.0, source_unit),
            context="cross-domain interval lower",
        )
        require_same_dimension(
            upper,
            Quantity(1.0, source_unit),
            context="cross-domain interval upper",
        )
        low_mag = lower.magnitude_in(source_unit) * factor
        high_mag = upper.magnitude_in(source_unit) * factor
        lo, hi = sorted((low_mag, high_mag))
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(lo, source_unit).to(target_unit),
            upper=Quantity(hi, source_unit).to(target_unit),
            confidence_level=source_uncertainty.confidence_level,
            source=_attribution(transfer, source_uncertainty),
            source_kind=source_uncertainty.source_kind,  # CORE-016: a transfer changes units, not what it is
            method=method_prefix,
            notes=(
                f"propagated interval from {source_uncertainty.method or 'declared source method'}; "
                "no distribution or correlation was inferred, so a declared "
                "efficiency uncertainty is not combined into these bounds and "
                "the record says so in its completeness"
            ),
        )

    raise InvalidScientificProblem(
        f"unsupported uncertainty kind {source_uncertainty.kind!r}"
    )


def _efficiency_width(transfer: QuantityTransfer) -> float | None:
    """The declared standard uncertainty of this crossing's efficiency, if any."""
    conversion = transfer.dependency.conversion
    if conversion is None:
        return None
    return conversion.efficiency_uncertainty


def make_uncertainty_transfer(
    transfer: QuantityTransfer,
    source_uncertainty: Uncertainty,
    *,
    upstream: QuantityTransfer | None = None,
) -> UncertaintyTransfer:
    return UncertaintyTransfer(
        transfer=transfer,
        source_uncertainty=source_uncertainty,
        uncertainty=propagate_transfer_uncertainty(
            transfer,
            source_uncertainty,
            upstream=upstream,
        ),
        completeness=_completeness_of(transfer, source_uncertainty),
        upstream=upstream,
    )


def propagate_uncertainty_chain(
    transfers: Sequence[QuantityTransfer],
    source_uncertainty: Uncertainty,
) -> tuple[UncertaintyTransfer, ...]:
    """Propagate uncertainty through a connected sequence of domain crossings."""
    transfers = tuple(transfers)
    if not transfers:
        return ()
    if not isinstance(source_uncertainty, Uncertainty):
        raise InvalidScientificProblem("uncertainty chain requires Uncertainty")
    for transfer in transfers:
        if not isinstance(transfer, QuantityTransfer):
            raise InvalidScientificProblem(
                "uncertainty chain contains non-transfer value"
            )

    propagated: list[UncertaintyTransfer] = []
    current = source_uncertainty
    previous: QuantityTransfer | None = None
    for transfer in transfers:
        if previous is not None:
            left = (
                previous.dependency.target_problem_id,
                previous.dependency.target_quantity,
            )
            right = (
                transfer.dependency.source_problem_id,
                transfer.dependency.source_quantity,
            )
            if left != right:
                raise InvalidScientificProblem(
                    f"uncertainty chain is disconnected: previous transfer ends at "
                    f"{left}, next begins at {right}"
                )
            # R-58 claim (d): the two crossings must meet by VALUE as well as
            # by name. Name connectivity says they are about the same quantity;
            # it does not say they are about the same number, and 350 K leaving
            # one crossing with 400 K entering the next is a path nothing
            # travelled -- along which the audited code propagated one width.
            met = _entering_value(transfer)
            unit = transfer.dependency.unit_exemplar
            if not _agree_relatively(
                previous.value.magnitude_in(unit), met.magnitude_in(unit)
            ):
                raise InvalidScientificProblem(
                    f"uncertainty chain does not meet: "
                    f"{previous.value.magnitude_in(unit)} {unit} left "
                    f"{previous.dependency.target_problem_id}."
                    f"{previous.dependency.target_quantity} and "
                    f"{met.magnitude_in(unit)} {unit} entered "
                    f"{transfer.dependency.source_problem_id}."
                    f"{transfer.dependency.source_quantity}. The two crossings "
                    f"name the same quantity and are about different numbers"
                )
            if previous.instant != transfer.instant:
                raise InvalidScientificProblem(
                    f"uncertainty chain crosses different instants "
                    f"{previous.instant!r} and {transfer.instant!r}; propagating "
                    "across them would require a temporal evolution model"
                )
        item = make_uncertainty_transfer(transfer, current, upstream=previous)
        propagated.append(item)
        current = item.uncertainty
        previous = transfer
    return tuple(propagated)


__all__ = [
    "UNCERTAINTY_TRANSFER_SCHEMA_V2",
    "TRANSFER_COMPLETENESS",
    "UncertaintyTransfer",
    "propagate_transfer_uncertainty",
    "make_uncertainty_transfer",
    "propagate_uncertainty_chain",
]
