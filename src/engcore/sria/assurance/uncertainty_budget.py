"""M3A — assembling and auditing an uncertainty budget.

This is **not** a second uncertainty system. M1 already owns the vocabulary
(:class:`~engcore.sria.uncertainty.UncertaintyChannel`,
:class:`~engcore.sria.uncertainty.UncertaintyDeclaration`,
:class:`~engcore.sria.uncertainty.ModelDiscrepancy`) and the Scientific Core
owns per-value magnitudes (:class:`~engcore.scientific.results.uncertainty.Uncertainty`,
whose ``UNKNOWN`` is already first-class). M3A adds only the missing piece:
a way to state, per channel, *what is known about it*, and to refuse the
arithmetic that quietly destroys that information.

The rules exist because each of them is a real way budgets go wrong.

**UNKNOWN is not zero.** A channel nobody evaluated and a channel evaluated to
zero are different scientific statements, and the difference is precisely the
one that matters when someone asks whether a result can be trusted. There is
no code path here that turns the former into the latter.

**Decomposed is primary.** A single total is a lossy summary; the channels are
the finding. Aggregation is offered only when it is defensible, and when
offered it records its rule and assumptions rather than returning a bare
number.

**Incomparable quantities do not add.** Variances, intervals and one-sided
bounds have different semantics; adding a standard uncertainty to an interval
half-width produces something with no interpretation. Units must match
dimensionally too — this is enforced by the Core's dimensional comparison, not
by string equality.

**Channels stay distinct.** Model-form uncertainty is not parameter
uncertainty; numerical convergence error is not scientific variability.
Collapsing them lets a tight solver tolerance masquerade as physical
confidence. :meth:`UncertaintyBudget.aggregate` therefore refuses to combine
across channel *kinds* by default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ...scientific.errors import UnitCompatibilityError
from ...scientific.results.uncertainty import Uncertainty, UncertaintyKind
from ...scientific.serialization import require_schema, schema_string
from ...scientific.units.quantity import Quantity
from ..uncertainty import (
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyChannel,
    UncertaintyDeclaration,
)

CHANNEL_ENTRY_SCHEMA = schema_string("sria_uncertainty_channel_entry")
BUDGET_SCHEMA = schema_string("sria_uncertainty_budget")

#: Where surrogate/approximation error belongs in V0.1. Stated once, here, so
#: it cannot drift: a surrogate's approximation error is an artifact of how the
#: answer was computed, not of the physics, so it is NUMERICAL. No frozen
#: contract says otherwise.
SURROGATE_APPROXIMATION_CHANNEL = UncertaintyChannel.NUMERICAL


class ChannelState(str, Enum):
    """What is known about one uncertainty channel.

    ``UNKNOWN`` is a legitimate scientific result and a legitimate terminal
    state. It is not a placeholder to be filled in with zero later.
    """

    KNOWN = "known"                 # quantified with a stated method
    BOUNDED = "bounded"             # a defensible bound, not a full estimate
    UNKNOWN = "unknown"             # not evaluated — honest and valid
    NOT_APPLICABLE = "not_applicable"  # channel cannot arise for this result


class BudgetError(Exception):
    """An uncertainty budget that cannot be assembled honestly."""


class IncomparableUncertainty(BudgetError):
    """Two uncertainty quantities with different semantics or dimensions."""


@dataclass(frozen=True)
class ChannelEntry:
    """One channel of the budget, with its state made explicit."""

    channel: UncertaintyChannel
    state: ChannelState
    uncertainty: Uncertainty = field(default_factory=Uncertainty.unknown)
    rationale: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel", UncertaintyChannel(self.channel))
        object.__setattr__(self, "state", ChannelState(self.state))

        if not isinstance(self.uncertainty, Uncertainty):
            raise BudgetError("channel entry requires an Uncertainty record")

        quantified = self.uncertainty.is_quantified
        if self.state is ChannelState.KNOWN and not quantified:
            raise BudgetError(
                f"channel {self.channel.value!r} is declared KNOWN but carries "
                f"no quantified uncertainty; 'known' must mean measured"
            )
        if self.state is ChannelState.UNKNOWN and quantified:
            raise BudgetError(
                f"channel {self.channel.value!r} is declared UNKNOWN but "
                f"carries a value; use KNOWN or BOUNDED"
            )
        if self.state is ChannelState.NOT_APPLICABLE:
            if quantified:
                raise BudgetError(
                    f"channel {self.channel.value!r} is NOT_APPLICABLE but "
                    f"carries a value"
                )
            if not str(self.rationale).strip():
                raise BudgetError(
                    f"declaring channel {self.channel.value!r} NOT_APPLICABLE "
                    f"requires a rationale; 'this channel cannot arise' is a "
                    f"scientific claim, not a default"
                )
        if self.state is ChannelState.BOUNDED and not quantified:
            raise BudgetError(
                f"channel {self.channel.value!r} is BOUNDED but carries no bound"
            )

    @property
    def is_quantified(self) -> bool:
        return self.state in (ChannelState.KNOWN, ChannelState.BOUNDED)

    @property
    def blocks_quantitative_claims(self) -> bool:
        """UNKNOWN blocks any claim that requires this channel quantified."""
        return self.state is ChannelState.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHANNEL_ENTRY_SCHEMA,
            "channel": self.channel.value,
            "state": self.state.value,
            "uncertainty": self.uncertainty.to_dict(),
            "rationale": self.rationale,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChannelEntry":
        require_schema(payload, CHANNEL_ENTRY_SCHEMA)
        return cls(
            channel=UncertaintyChannel(payload["channel"]),
            state=ChannelState(payload["state"]),
            uncertainty=Uncertainty.from_dict(payload["uncertainty"]),
            rationale=payload.get("rationale", ""),
            source=payload.get("source", ""),
        )


@dataclass(frozen=True)
class AggregationRecord:
    """The rule and assumptions behind an aggregated total.

    An aggregate without its rule is a number nobody can check, so this is
    returned *with* the value rather than alongside it.
    """

    rule: str
    assumptions: tuple[str, ...]
    channels_combined: tuple[UncertaintyChannel, ...]
    total: Quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "assumptions": list(self.assumptions),
            "channels_combined": [c.value for c in self.channels_combined],
            "total": self.total.to_dict(),
        }


@dataclass(frozen=True)
class UncertaintyBudget:
    """The decomposed uncertainty for one reported value.

    Decomposition is the primary representation. ``aggregate`` is available
    when justified and never happens implicitly.
    """

    value_name: str
    entries: tuple[ChannelEntry, ...]
    declaration: UncertaintyDeclaration
    notes: str = ""

    def __post_init__(self) -> None:
        if not str(self.value_name).strip():
            raise BudgetError("uncertainty budget requires a value_name")
        if not isinstance(self.declaration, UncertaintyDeclaration):
            raise BudgetError(
                "an uncertainty budget must carry the M1 UncertaintyDeclaration "
                "it derives from, including the model-discrepancy statement"
            )
        entries = tuple(self.entries)
        seen = [e.channel for e in entries]
        duplicates = {c for c in seen if seen.count(c) > 1}
        if duplicates:
            # Double counting starts here, so it is refused here.
            raise BudgetError(
                f"channel(s) {sorted(c.value for c in duplicates)} appear more "
                f"than once; a channel counted twice inflates every aggregate "
                f"derived from it"
            )
        object.__setattr__(self, "entries", entries)

    # ---- views ----------------------------------------------------------
    def entry(self, channel: UncertaintyChannel) -> ChannelEntry:
        """The entry for a channel; UNKNOWN when never declared.

        A channel nobody mentioned is reported as UNKNOWN rather than omitted,
        so a missing channel cannot silently vanish from an audit.
        """
        channel = UncertaintyChannel(channel)
        for entry in self.entries:
            if entry.channel is channel:
                return entry
        return ChannelEntry(
            channel=channel,
            state=ChannelState.UNKNOWN,
            rationale="channel was never declared for this result",
        )

    @property
    def declared_channels(self) -> tuple[UncertaintyChannel, ...]:
        return tuple(e.channel for e in self.entries)

    @property
    def missing_channels(self) -> tuple[UncertaintyChannel, ...]:
        """Channels of the closed vocabulary with no explicit entry."""
        declared = set(self.declared_channels)
        return tuple(c for c in UncertaintyChannel if c not in declared)

    @property
    def unknown_channels(self) -> tuple[UncertaintyChannel, ...]:
        return tuple(
            c
            for c in UncertaintyChannel
            if self.entry(c).state is ChannelState.UNKNOWN
        )

    @property
    def quantified_channels(self) -> tuple[UncertaintyChannel, ...]:
        return tuple(c for c in UncertaintyChannel if self.entry(c).is_quantified)

    @property
    def model_discrepancy(self) -> ModelDiscrepancy:
        return self.declaration.discrepancy

    @property
    def declares_zero_discrepancy(self) -> bool:
        """True when the campaign asserted model-form discrepancy is zero.

        Surfaced as a property rather than buried in the declaration because a
        critic has to be able to see and challenge it.
        """
        return self.model_discrepancy.kind is DiscrepancyKind.ZERO_DECLARED

    def requires_quantification(
        self, channels: Iterable[UncertaintyChannel]
    ) -> tuple[UncertaintyChannel, ...]:
        """Which of the required channels are not quantified."""
        return tuple(
            UncertaintyChannel(c)
            for c in channels
            if not self.entry(c).is_quantified
        )

    # ---- aggregation (never implicit) -----------------------------------
    @staticmethod
    def _standard_magnitude(entry: ChannelEntry, reference_units: str | None):
        """Extract a comparable standard uncertainty, or refuse."""
        record = entry.uncertainty
        if record.kind is UncertaintyKind.STANDARD:
            quantity = record.standard_uncertainty
        elif record.kind is UncertaintyKind.INTERVAL:
            raise IncomparableUncertainty(
                f"channel {entry.channel.value!r} carries an INTERVAL; an "
                f"interval half-width and a standard uncertainty are different "
                f"quantities and adding them has no interpretation"
            )
        else:
            raise IncomparableUncertainty(
                f"channel {entry.channel.value!r} is not quantified"
            )

        if reference_units is None:
            return quantity, quantity.units
        try:
            converted = quantity.to(reference_units)
        except Exception as exc:  # dimensional mismatch surfaces from the core
            raise IncomparableUncertainty(
                f"channel {entry.channel.value!r} has units {quantity.units!r} "
                f"which cannot be combined with {reference_units!r}"
            ) from exc
        return converted, reference_units

    def aggregate(
        self,
        channels: Iterable[UncertaintyChannel],
        *,
        rule: str = "root_sum_square",
        assumptions: Iterable[str] = (),
        allow_cross_kind: bool = False,
    ) -> AggregationRecord:
        """Combine selected channels, recording the rule and assumptions.

        Refuses by default to combine channels of different kinds. Root-sum-
        square across independent sources is defensible; root-sum-square of a
        numerical tolerance and a model-form bound quietly asserts that a
        tighter solver tolerance makes the physics more certain.
        """
        selected = [UncertaintyChannel(c) for c in channels]
        if not selected:
            raise BudgetError("aggregate requires at least one channel")

        entries = [self.entry(c) for c in selected]
        unquantified = [e.channel.value for e in entries if not e.is_quantified]
        if unquantified:
            raise BudgetError(
                f"cannot aggregate: channel(s) {sorted(unquantified)} are not "
                f"quantified. An UNKNOWN channel is not zero, and treating it "
                f"as zero would understate the total"
            )

        kinds = {e.channel for e in entries}
        if len(kinds) > 1 and not allow_cross_kind:
            raise BudgetError(
                f"refusing to combine distinct channels "
                f"{sorted(k.value for k in kinds)} without an explicit "
                f"allow_cross_kind and a stated independence assumption; "
                f"model-form and numerical uncertainty are not interchangeable"
            )

        if rule != "root_sum_square":
            raise BudgetError(
                f"unsupported aggregation rule {rule!r}; V0.1 implements "
                f"root_sum_square only"
            )

        reference_units: str | None = None
        magnitudes: list[float] = []
        for entry in entries:
            quantity, reference_units = self._standard_magnitude(
                entry, reference_units
            )
            magnitudes.append(float(quantity.magnitude))

        total = math.sqrt(sum(m * m for m in magnitudes))
        stated = tuple(assumptions)
        if not stated:
            raise BudgetError(
                "root_sum_square requires the independence assumption to be "
                "stated explicitly; an unstated assumption cannot be reviewed"
            )

        return AggregationRecord(
            rule=rule,
            assumptions=stated,
            channels_combined=tuple(selected),
            total=Quantity(total, reference_units or "dimensionless"),
        )

    # ---- serialization --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": BUDGET_SCHEMA,
            "value_name": self.value_name,
            "entries": [e.to_dict() for e in self.entries],
            "declaration": self.declaration.to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyBudget":
        require_schema(payload, BUDGET_SCHEMA)
        return cls(
            value_name=payload["value_name"],
            entries=tuple(
                ChannelEntry.from_dict(e) for e in payload.get("entries", ())
            ),
            declaration=UncertaintyDeclaration.from_dict(payload["declaration"]),
            notes=payload.get("notes", ""),
        )


def budget_from_declaration(
    value_name: str,
    declaration: UncertaintyDeclaration,
    *,
    states: Mapping[UncertaintyChannel, ChannelState] | None = None,
    rationales: Mapping[UncertaintyChannel, str] | None = None,
) -> UncertaintyBudget:
    """Build a budget from an M1 declaration, deriving states from the data.

    Derived, not asserted: a channel is KNOWN only when its record is actually
    quantified. Callers may override a state (to BOUNDED or NOT_APPLICABLE)
    but cannot promote an unquantified channel to KNOWN — ``ChannelEntry``
    refuses that.
    """
    states = dict(states or {})
    rationales = dict(rationales or {})
    entries: list[ChannelEntry] = []

    for channel in UncertaintyChannel:
        record = declaration.channels.get(channel)
        if record is None and channel not in states:
            continue    # undeclared: reported as UNKNOWN by ``entry``
        record = record if record is not None else Uncertainty.unknown()
        state = states.get(
            channel,
            ChannelState.KNOWN if record.is_quantified else ChannelState.UNKNOWN,
        )
        entries.append(
            ChannelEntry(
                channel=channel,
                state=state,
                uncertainty=record,
                rationale=rationales.get(channel, ""),
                source=record.source,
            )
        )

    return UncertaintyBudget(
        value_name=value_name,
        entries=tuple(entries),
        declaration=declaration,
    )
