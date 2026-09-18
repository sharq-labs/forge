"""CORE-8 -- uncertainty transport from Core records to SRIA channels, without invention.

A Core :class:`~engcore.scientific.results.uncertainty.Uncertainty` says *how
much* and, since CORE-016, *of what* (``source_kind``). SRIA budgets by
*channel*. The translation between them is one table --
:data:`~engcore.sria.uncertainty.CHANNEL_OF_SOURCE` -- and this module is the
only generic way the claim layer applies it. Every record lands in exactly one
of four states, and three of them put nothing in a channel:

``UNKNOWN``       never quantified. No channel; the channel reads UNKNOWN.
``ATTRIBUTED``    quantified, and its source names exactly one channel. Filed there.
``UNATTRIBUTED``  quantified, source UNSPECIFIED. Nothing says which channel it
                  is, so it is filed under none -- the number is kept in the
                  transport record for a reader, never counted as a channel's.
``MIXTURE``       quantified, source COMBINED. Already a mixture of channels;
                  filing it under one would count what it contains twice.

What this guarantees
--------------------
* UNKNOWN stays UNKNOWN; a missing record is never zero.
* A COMBINED record never enters a single channel.
* The source kind is load-bearing: a NUMERICAL record can never satisfy a
  MODEL_FORM demand, because it is filed only under NUMERICAL.
* Two records claiming one channel with different values are refused, not
  averaged.

The same rules apply to any producer: a credibility report's per-value record,
or the named records of a posterior-predictive result (``PARAMETER`` epistemic
interval plus ``COMBINED`` total) -- the epistemic part is filed, the total is a
listed MIXTURE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.uncertainty import Uncertainty, UncertaintySource
from ..sria.uncertainty import CHANNEL_OF_SOURCE, UncertaintyChannel
from .errors import ClaimLayerError


class TransportState(str, Enum):
    UNKNOWN = "unknown"
    ATTRIBUTED = "attributed"
    UNATTRIBUTED = "unattributed"
    MIXTURE = "mixture"


class UncertaintyTransportError(ClaimLayerError):
    """Two records claim one channel with different content."""


@dataclass(frozen=True)
class TransportedRecord:
    name: str
    state: TransportState
    channel: UncertaintyChannel | None
    record: Uncertainty

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "channel": None if self.channel is None else self.channel.value,
            "record": self.record.to_dict(),
        }


@dataclass(frozen=True)
class UncertaintyTransport:
    """The channel mapping of a set of records, and what was left out and why."""

    records: tuple[TransportedRecord, ...]

    @property
    def channels(self) -> dict[UncertaintyChannel, Uncertainty]:
        return {r.channel: r.record for r in self.records if r.state is TransportState.ATTRIBUTED}

    @property
    def excluded(self) -> tuple[TransportedRecord, ...]:
        return tuple(r for r in self.records if r.state in (TransportState.UNATTRIBUTED, TransportState.MIXTURE))

    def state_of(self, channel: UncertaintyChannel) -> str:
        return "quantified" if channel in self.channels else "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "channels": {c.value: "quantified" if c in self.channels else "unknown" for c in UncertaintyChannel},
        }


def classify_record(name: str, record: Uncertainty) -> TransportedRecord:
    if not isinstance(record, Uncertainty):
        raise TypeError(f"uncertainty {name!r} must be an Uncertainty record")
    if not record.is_quantified:
        return TransportedRecord(name, TransportState.UNKNOWN, None, record)
    source = UncertaintySource(record.source_kind)
    if source is UncertaintySource.COMBINED:
        return TransportedRecord(name, TransportState.MIXTURE, None, record)
    channel = CHANNEL_OF_SOURCE.get(source)
    if channel is None:
        return TransportedRecord(name, TransportState.UNATTRIBUTED, None, record)
    return TransportedRecord(name, TransportState.ATTRIBUTED, channel, record)


def transport(records: Mapping[str, Uncertainty]) -> UncertaintyTransport:
    """Classify named records and file the attributable ones. Deterministic, name order."""
    classified = tuple(classify_record(name, records[name]) for name in sorted(records))
    seen: dict[UncertaintyChannel, TransportedRecord] = {}
    for item in classified:
        if item.state is not TransportState.ATTRIBUTED:
            continue
        existing = seen.get(item.channel)
        if existing is not None and existing.record != item.record:
            raise UncertaintyTransportError(
                f"{existing.name!r} and {item.name!r} both claim channel {item.channel.value!r} with different "
                f"records; one channel carries one uncertainty and nothing here can say which"
            )
        seen[item.channel] = item
    return UncertaintyTransport(classified)


def report_transport(report: Any, quantity: str) -> UncertaintyTransport:
    """The transport of one reported value's record (absent record: UNKNOWN, never zero)."""
    record = report.uncertainty.get(quantity)
    return transport({quantity: record if record is not None else Uncertainty.unknown("the report declares none")})


__all__ = [
    "TransportState",
    "TransportedRecord",
    "UncertaintyTransport",
    "UncertaintyTransportError",
    "classify_record",
    "report_transport",
    "transport",
]
