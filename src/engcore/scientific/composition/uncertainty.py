"""Uncertainty that crosses the same declared boundary as a quantity.

``QuantityTransfer`` already makes a cross-domain value explicit: which
quantity moved, from which result, at which instant, under which declared
conversion. Uncertainty must follow that exact record rather than being copied
through a parallel dictionary keyed by a coincidentally matching name.

This module propagates the uncertainty representations the core already knows:

* UNKNOWN stays UNKNOWN and records why no number can be propagated;
* STANDARD uncertainty is converted as a *delta* (scale only, never an offset)
  and scaled by a declared deterministic conversion efficiency;
* INTERVAL uncertainty has both absolute bounds converted/scaled monotonically.

No distribution is invented from an interval, no correlation is invented
between sources, and no uncertainty is assigned to an undeclared conversion
efficiency. Those require evidence the transfer record does not carry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..errors import InvalidScientificProblem
from ..results.uncertainty import Uncertainty, UncertaintyKind
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from .transfer import QuantityTransfer

UNCERTAINTY_TRANSFER_SCHEMA = schema_string("uncertainty_transfer")


def _delta_magnitude_in(value: Quantity, unit: str) -> float:
    """Convert an uncertainty width using scale only, not an absolute offset.

    ``Quantity.to`` correctly converts *values*, so 273.15 K becomes 0 °C. A
    standard uncertainty is a width: 1 K is a 1 °C width, not -272.15 °C. The
    scale is therefore the difference between converted one and converted zero.
    This also works for ordinary multiplicative units such as W/kW.
    """
    require_same_dimension(value, Quantity(1.0, unit), context="uncertainty delta conversion")
    one = Quantity(1.0, value.units).magnitude_in(unit)
    zero = Quantity(0.0, value.units).magnitude_in(unit)
    return float(value.magnitude) * abs(one - zero)


def _source_unit(transfer: QuantityTransfer) -> str:
    if transfer.source_value is not None:
        return transfer.source_value.units
    return transfer.dependency.unit_exemplar


def _factor(transfer: QuantityTransfer) -> float:
    conversion = transfer.dependency.conversion
    if conversion is None:
        return 1.0
    if conversion.efficiency is None:
        raise InvalidScientificProblem(
            f"cannot propagate uncertainty across conversion {conversion.name!r}: "
            "its efficiency is undeclared, so the transferred quantity is not "
            "a deterministic mapping the core can propagate through"
        )
    return float(conversion.efficiency)


@dataclass(frozen=True)
class UncertaintyTransfer:
    """The uncertainty counterpart of one exact :class:`QuantityTransfer`."""

    transfer: QuantityTransfer
    source_uncertainty: Uncertainty
    uncertainty: Uncertainty

    def __post_init__(self) -> None:
        if not isinstance(self.transfer, QuantityTransfer):
            raise InvalidScientificProblem("uncertainty transfer requires QuantityTransfer")
        if not isinstance(self.source_uncertainty, Uncertainty):
            raise InvalidScientificProblem("source_uncertainty must be Uncertainty")
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem("uncertainty must be Uncertainty")

        expected = propagate_transfer_uncertainty(self.transfer, self.source_uncertainty)
        if expected != self.uncertainty:
            raise InvalidScientificProblem(
                "uncertainty transfer does not follow from its QuantityTransfer "
                "and source uncertainty"
            )

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return self.transfer.key

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_TRANSFER_SCHEMA,
            "transfer": self.transfer.to_dict(),
            "source_uncertainty": self.source_uncertainty.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyTransfer":
        require_schema(payload, UNCERTAINTY_TRANSFER_SCHEMA)
        return cls(
            transfer=QuantityTransfer.from_dict(payload["transfer"]),
            source_uncertainty=Uncertainty.from_dict(payload["source_uncertainty"]),
            uncertainty=Uncertainty.from_dict(payload["uncertainty"]),
        )


def propagate_transfer_uncertainty(
    transfer: QuantityTransfer,
    source_uncertainty: Uncertainty,
) -> Uncertainty:
    """Propagate one uncertainty through the deterministic transfer mapping."""
    if not isinstance(transfer, QuantityTransfer):
        raise InvalidScientificProblem("propagation requires QuantityTransfer")
    if not isinstance(source_uncertainty, Uncertainty):
        raise InvalidScientificProblem("propagation requires Uncertainty")

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
        as_source = Quantity(source_delta, source_unit)
        propagated_delta = _delta_magnitude_in(as_source, target_unit)
        propagated = Quantity(propagated_delta, target_unit)
        return Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=propagated,
            source=f"transfer:{transfer.source_record_id}",
            method=method_prefix,
            notes=(
                f"propagated from {source_uncertainty.method or 'declared source method'}; "
                "standard uncertainty was converted as a delta (scale only); "
                "conversion efficiency treated as deterministic because the "
                "conversion record carries no uncertainty for it"
            ),
        )

    if source_uncertainty.kind is UncertaintyKind.INTERVAL:
        lower, upper = source_uncertainty.lower, source_uncertainty.upper
        assert lower is not None and upper is not None
        require_same_dimension(
            lower, Quantity(1.0, source_unit), context="cross-domain interval lower"
        )
        require_same_dimension(
            upper, Quantity(1.0, source_unit), context="cross-domain interval upper"
        )
        low_mag = lower.magnitude_in(source_unit) * factor
        high_mag = upper.magnitude_in(source_unit) * factor
        lo, hi = sorted((low_mag, high_mag))
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(lo, source_unit).to(target_unit),
            upper=Quantity(hi, source_unit).to(target_unit),
            confidence_level=source_uncertainty.confidence_level,
            source=f"transfer:{transfer.source_record_id}",
            method=method_prefix,
            notes=(
                f"propagated interval from {source_uncertainty.method or 'declared source method'}; "
                "no distribution or correlation was inferred"
            ),
        )

    raise InvalidScientificProblem(
        f"unsupported uncertainty kind {source_uncertainty.kind!r}"
    )


def make_uncertainty_transfer(
    transfer: QuantityTransfer,
    source_uncertainty: Uncertainty,
) -> UncertaintyTransfer:
    return UncertaintyTransfer(
        transfer=transfer,
        source_uncertainty=source_uncertainty,
        uncertainty=propagate_transfer_uncertainty(transfer, source_uncertainty),
    )


def propagate_uncertainty_chain(
    transfers: Sequence[QuantityTransfer],
    source_uncertainty: Uncertainty,
) -> tuple[UncertaintyTransfer, ...]:
    """Propagate uncertainty through a connected sequence of domain crossings.

    The chain is connected by exact problem/quantity identity and one instant.
    A transition to another instant would require a temporal evolution model,
    which this transfer record does not declare and this function refuses to
    invent.
    """
    transfers = tuple(transfers)
    if not transfers:
        return ()
    if not isinstance(source_uncertainty, Uncertainty):
        raise InvalidScientificProblem("uncertainty chain requires Uncertainty")
    for transfer in transfers:
        if not isinstance(transfer, QuantityTransfer):
            raise InvalidScientificProblem("uncertainty chain contains non-transfer value")

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
            if previous.instant != transfer.instant:
                raise InvalidScientificProblem(
                    f"uncertainty chain crosses different instants "
                    f"{previous.instant!r} and {transfer.instant!r}; propagating "
                    "across them would require a temporal evolution model"
                )
        item = make_uncertainty_transfer(transfer, current)
        propagated.append(item)
        current = item.uncertainty
        previous = transfer
    return tuple(propagated)


__all__ = [
    "UncertaintyTransfer",
    "propagate_transfer_uncertainty",
    "make_uncertainty_transfer",
    "propagate_uncertainty_chain",
]
