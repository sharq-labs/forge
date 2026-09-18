"""Uncertainty channel contract — semantics only, no UQ engine.

The Scientific Core already answers *how much* uncertainty a value carries
(:class:`~engcore.scientific.results.uncertainty.Uncertainty`, with ``UNKNOWN``
as the honest default). It does not answer *what kind*, and lumping the kinds
together is how a model-form error silently becomes a noise estimate.

M1 reserves four channels and forces two declarations that are usually left
implicit:

* ``subject_model`` — is this uncertainty about the prediction, or about the
  observation process? Confusing the two is what makes calibration circular.
* ``discrepancy`` — model-form discrepancy must be declared, even when the
  declaration is "we are asserting zero". ``ZERO_DECLARED`` is a claim someone
  is accountable for; a missing field is not.

No inference is performed here. This module defines vocabulary and refuses
incomplete declarations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.immutable import freeze
from ..scientific.results.uncertainty import Uncertainty, UncertaintySource
from ..scientific.serialization import require_schema, schema_string
from .errors import UncertaintyContractError

UNCERTAINTY_DECLARATION_SCHEMA = schema_string("sria_uncertainty_declaration")
DISCREPANCY_SCHEMA = schema_string("sria_model_discrepancy")


class UncertaintyChannel(str, Enum):
    """Sources of uncertainty that must not be silently merged."""

    ALEATORIC = "aleatoric"
    EPISTEMIC_PARAMETER = "epistemic_parameter"
    MODEL_FORM = "model_form"
    NUMERICAL = "numerical"


#: Which :class:`~engcore.scientific.results.uncertainty.UncertaintySource` each channel accepts
#: (R-43, core re-audit 2026-09-16). The CORE-016 record exists to stop a discretization estimate
#: standing in for scientific uncertainty; a channel is the thing a budget root-sum-squares, so a
#: record filed under a channel its own declared source contradicts is refused rather than summed.
#:
#: COMBINED appears under no channel on purpose: it is already a mixture of channels, and
#: root-sum-squaring it with another would count what it contains twice.
#:
#: UNSPECIFIED is accepted everywhere and counts as UNATTRIBUTED rather than as compatible --
#: see :attr:`UncertaintyDeclaration.unattributed_channels`. Refusing it is the stricter reading,
#: and it is not taken here because every domain solver in this repository still emits the default,
#: so the refusal would fall on every existing declaration rather than on any wrong one.
#: R-43: a row lists the sources a channel is a channel OF, plus UNSPECIFIED.
#:
#: UNSPECIFIED stays ACCEPTED here, and batch 54 (I-25 part C) records why: the
#: SHA-256-pinned E1 and E2 experiment harnesses file quantified channel records
#: that declare no source, and the pinned bytes may not be edited -- so a
#: refusal at declaration time would make a pinned experiment unrunnable rather
#: than making anything more honest. What batch 54 closes instead is the harm
#: the audit measured: an unattributed record may no longer be COUNTED as a
#: channel's known uncertainty, which is where "aleatoric and model_form marked
#: known from a numerical-only record" came from.
CHANNEL_ACCEPTS_SOURCE: "Mapping[UncertaintyChannel, frozenset[UncertaintySource]]" = {
    UncertaintyChannel.ALEATORIC: frozenset(
        {UncertaintySource.UNSPECIFIED, UncertaintySource.MEASUREMENT}
    ),
    UncertaintyChannel.EPISTEMIC_PARAMETER: frozenset(
        {UncertaintySource.UNSPECIFIED, UncertaintySource.PARAMETER}
    ),
    UncertaintyChannel.MODEL_FORM: frozenset(
        {UncertaintySource.UNSPECIFIED, UncertaintySource.MODEL_FORM}
    ),
    UncertaintyChannel.NUMERICAL: frozenset(
        {UncertaintySource.UNSPECIFIED, UncertaintySource.NUMERICAL}
    ),
}

#: Which channel a declared source belongs in, derived from the map above so
#: the two cannot disagree.
CHANNEL_OF_SOURCE: "Mapping[UncertaintySource, UncertaintyChannel]" = {
    source: channel
    for channel, sources in CHANNEL_ACCEPTS_SOURCE.items()
    for source in sources
    # UNSPECIFIED is in every row above, for the reason stated there, and it is
    # a channel of nothing: it says which channels ACCEPT an unattributed
    # record, not which channel such a record belongs to.
    if source is not UncertaintySource.UNSPECIFIED
}


def channels_from_predictive_uncertainty(
    records: "Mapping[str, Uncertainty]",
) -> "dict[UncertaintyChannel, Uncertainty]":
    """Carry declared V1 uncertainty records onto the channels their own sources name (R-43).

    The producer and the budget were two unconnected halves: ``posterior_predictive_uq`` declares
    PARAMETER on its epistemic interval and COMBINED on its total, the budget accepts PARAMETER only
    under EPISTEMIC_PARAMETER, and nothing carried the one to the other -- so the map had nothing
    production-made to check.

    The channel is DERIVED from each record's own ``source_kind``, which is the only direction that
    cannot invent an attribution. An UNKNOWN record carries no channel and is skipped, because a
    production record whose metrics were never quantified is the ordinary case. A COMBINED record is
    refused with the reason the map already gives: it is a mixture of channels, and filing it under one
    counts what it contains twice.
    """
    channels: dict[UncertaintyChannel, Uncertainty] = {}
    for name, record in dict(records).items():
        if not isinstance(record, Uncertainty):
            raise UncertaintyContractError(
                f"{name!r} is not an Uncertainty record, so it names no channel"
            )
        if not record.is_quantified:
            continue
        source = UncertaintySource(record.source_kind)
        if source is UncertaintySource.UNSPECIFIED:
            # R-43 (I-25 part C): refused rather than skipped. Skipping would
            # drop a quantified number silently, which is the shape of the
            # defect one level down; and there is no channel to carry it to,
            # because the record does not say which channel's number it is.
            raise UncertaintyContractError(
                f"uncertainty {name!r} is quantified and declares no source_kind, so it names no "
                f"channel: nothing has said which channel's number it is. Declare UncertaintySource, "
                f"which is what tells a discretization estimate from a measurement standard deviation"
            )
        channel = CHANNEL_OF_SOURCE.get(source)
        if channel is None:
            raise UncertaintyContractError(
                f"uncertainty {name!r} is declared {source.value!r}, which belongs in no single "
                f"channel: a combined uncertainty is already a mixture of channels, and filing it under "
                f"one and root-sum-squaring it with another counts what it contains twice. Declare the "
                f"per-channel parts"
            )
        existing = channels.get(channel)
        if existing is not None and existing != record:
            raise UncertaintyContractError(
                f"two different records claim channel {channel.value!r}: {existing} and {record}. One "
                f"channel carries one uncertainty, and nothing here can say which of two it is"
            )
        channels[channel] = record
    return channels


def require_source_fits_channel(channel: "UncertaintyChannel", uncertainty: Uncertainty, *, where: str) -> None:
    """Refuse an uncertainty whose declared source contradicts the channel it is filed under (R-43).

    One rule, two callers: :class:`UncertaintyDeclaration`, where a channel is declared, and the assurance
    budget's ``ChannelEntry``, where it is aggregated. Stated here so the two cannot drift.
    """
    channel = UncertaintyChannel(channel)
    source = UncertaintySource(uncertainty.source_kind)
    accepted = CHANNEL_ACCEPTS_SOURCE[channel]
    if source in accepted:
        return
    if source is UncertaintySource.COMBINED:
        raise UncertaintyContractError(
            f"{where}: channel {channel.value!r} carries an uncertainty declared COMBINED. A combined "
            f"uncertainty is already a mixture of channels; filing it under one and root-sum-squaring it "
            f"with another counts what it contains twice. Declare the per-channel parts"
        )
    raise UncertaintyContractError(
        f"{where}: channel {channel.value!r} carries an uncertainty declared {source.value!r}, which is "
        f"not what that channel is. A {source.value} uncertainty filed under {channel.value!r} would be "
        f"aggregated as {channel.value} uncertainty it is not: the source_kind record exists to stop a "
        f"discretization estimate standing in for scientific uncertainty. "
        f"{channel.value!r} accepts {sorted(s.value for s in accepted)}"
    )


class SubjectModel(str, Enum):
    """Which model the uncertainty is a property of."""

    PREDICTION_MODEL = "prediction_model"
    OBSERVATION_MODEL = "observation_model"


class DiscrepancyKind(str, Enum):
    #: Nothing quantified or bounded model-form discrepancy for this claim.
    #: This is deliberately distinct from ZERO_DECLARED: absence of an
    #: estimate must never be turned into an assertion that discrepancy is zero.
    UNKNOWN = "unknown"
    ZERO_DECLARED = "zero_declared"
    CONSTRAINED_PRIOR = "constrained_prior"


@dataclass(frozen=True)
class ModelDiscrepancy:
    """An explicit statement about model-form discrepancy."""

    kind: DiscrepancyKind
    reference: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", DiscrepancyKind(self.kind))
        reference = str(self.reference).strip()
        if self.kind is DiscrepancyKind.CONSTRAINED_PRIOR and not reference:
            raise UncertaintyContractError(
                "CONSTRAINED_PRIOR discrepancy requires a reference: a prior "
                "nobody can point at is not a constraint"
            )
        object.__setattr__(self, "reference", reference)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DISCREPANCY_SCHEMA,
            "kind": self.kind.value,
            "reference": self.reference,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelDiscrepancy":
        require_schema(payload, DISCREPANCY_SCHEMA)
        return cls(
            kind=DiscrepancyKind(payload["kind"]),
            reference=payload.get("reference", ""),
            rationale=payload.get("rationale", ""),
        )


@dataclass(frozen=True)
class UncertaintyDeclaration:
    """Per-channel uncertainty plus the two mandatory declarations."""

    subject_model: SubjectModel
    discrepancy: ModelDiscrepancy
    channels: Mapping[UncertaintyChannel, Uncertainty] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_model", SubjectModel(self.subject_model))

        if not isinstance(self.discrepancy, ModelDiscrepancy):
            raise UncertaintyContractError(
                "uncertainty declaration requires an explicit ModelDiscrepancy; "
                "an absent declaration is not the same as declaring zero"
            )

        channels: dict[UncertaintyChannel, Uncertainty] = {}
        for key, value in self.channels.items():
            channel = UncertaintyChannel(key)
            if not isinstance(value, Uncertainty):
                raise UncertaintyContractError(
                    f"channel {channel.value!r} must carry an Uncertainty record"
                )
            # R-43: a record whose declared source names another channel is refused here,
            # where the channel is declared, and again in the budget that aggregates it.
            require_source_fits_channel(channel, value, where="uncertainty declaration")
            channels[channel] = value
        # Part of Evidence content identity: a channel must not change through a
        # caller alias after the evidence hash and admission were issued.
        object.__setattr__(self, "channels", freeze(channels))

    def channel(self, channel: UncertaintyChannel) -> Uncertainty:
        """Uncertainty for a channel; explicitly UNKNOWN when undeclared."""
        return self.channels.get(UncertaintyChannel(channel), Uncertainty.unknown())

    @property
    def unattributed_channels(self) -> tuple[UncertaintyChannel, ...]:
        """Quantified channels whose record declares no source (R-43).

        UNSPECIFIED is accepted -- every domain solver in this repository still emits it, and the
        SHA-256-pinned E1 and E2 harnesses file such records under channels -- and it is not the same as
        compatible. A budget built from these channels is summing numbers nobody has said are the
        channel's, and this property is what lets a reader see that rather than infer it from a default.

        Batch 54 (I-25 part C) is what makes it more than a report: ``UncertaintyBudget.aggregate``
        refuses to combine exactly these channels, so an unattributed number can be declared and read but
        not turned into a total presented as the channel's. It is derived, so a caller cannot set it.
        """
        return tuple(
            sorted(
                (
                    channel
                    for channel, record in self.channels.items()
                    if record.is_quantified
                    and UncertaintySource(record.source_kind) is UncertaintySource.UNSPECIFIED
                ),
                key=lambda c: c.value,
            )
        )

    @property
    def quantified_channels(self) -> tuple[UncertaintyChannel, ...]:
        return tuple(
            sorted(
                (c for c, u in self.channels.items() if u.is_quantified),
                key=lambda c: c.value,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_DECLARATION_SCHEMA,
            "subject_model": self.subject_model.value,
            "discrepancy": self.discrepancy.to_dict(),
            "channels": {
                c.value: self.channels[c].to_dict()
                for c in sorted(self.channels, key=lambda c: c.value)
            },
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UncertaintyDeclaration":
        require_schema(payload, UNCERTAINTY_DECLARATION_SCHEMA)
        return cls(
            subject_model=SubjectModel(payload["subject_model"]),
            discrepancy=ModelDiscrepancy.from_dict(payload["discrepancy"]),
            channels={
                UncertaintyChannel(k): Uncertainty.from_dict(v)
                for k, v in (payload.get("channels") or {}).items()
            },
            notes=payload.get("notes", ""),
        )
