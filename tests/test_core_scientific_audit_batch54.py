"""Core re-audit 2026-09-16, batch 54: an unattributed uncertainty is not a channel's number.

Problem R-43 (the audit's findings 51 and 86), improvement I-25 part C -- the reach ledger's row for R-43
names I-25 as what closes it -- under benchmarks/core_v4_false_confidence/BATCH54_THRESHOLD_PROTOCOL.json.

Batch 8 gave the credibility report an `uncertainty` field carrying `source_kind`, declared PARAMETER and
COMBINED on the two V1 predictive intervals, and wrote the map that refuses a record filed under a channel
its own source contradicts. Its own status line says what stayed open: UNSPECIFIED is NAMED rather than
acted on, so the SRIA budget marks aleatoric or model_form KNOWN from a record that never said it was
either and root-sum-squares them into a total; and nothing carries a V1 interval into a declaration, so
the producer and the budget are two unconnected halves.

Amendments 1 and 2 in the protocol record why the refusal is at AGGREGATION rather than at construction:
the SHA-256-pinned E1 and E2 experiment harnesses file quantified channel records that declare no source,
and their bytes may not be edited.

Recorded as strict xfails in commit 23d3ae84, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import pytest

from engcore.scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from engcore.scientific.units.quantity import Quantity
from engcore.sria import uncertainty as sria_uncertainty
from engcore.sria.assurance.uncertainty_budget import (
    BudgetError,
    ChannelEntry,
    ChannelState,
    UncertaintyBudget,
)
from engcore.sria.uncertainty import (
    DiscrepancyKind,
    ModelDiscrepancy,
    SubjectModel,
    UncertaintyChannel,
    UncertaintyContractError,
    UncertaintyDeclaration,
)


def _standard(magnitude: float = 0.5, unit: str = "volt", **overrides) -> Uncertainty:
    fields = dict(
        kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(magnitude, unit),
        source="solver estimate", method="linear-system residual bound",
    )
    fields.update(overrides)
    return Uncertainty(**fields)


def _interval(**overrides) -> Uncertainty:
    fields = dict(
        kind=UncertaintyKind.INTERVAL, lower=Quantity(299.0, "kelvin"),
        upper=Quantity(301.0, "kelvin"), confidence_level=0.95,
        source="posterior:T", method="credible_interval",
    )
    fields.update(overrides)
    return Uncertainty(**fields)


def _declaration(**channels) -> UncertaintyDeclaration:
    return UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.ZERO_DECLARED, rationale="declared zero"),
        channels={UncertaintyChannel(k): v for k, v in channels.items()},
    )


def _budget(*entries) -> UncertaintyBudget:
    return UncertaintyBudget(value_name="v", entries=tuple(entries), declaration=_declaration())


def _entry(channel: UncertaintyChannel, record: Uncertainty) -> ChannelEntry:
    return ChannelEntry(channel=channel, state=ChannelState.KNOWN, uncertainty=record)


# ---------------------------------------------------------------------------
# an unattributed quantified channel is not aggregated into a total
# ---------------------------------------------------------------------------
def test_r43_a_declared_channel_still_aggregates():
    """The control: two channels that say what they are of combine as they always did."""
    budget = _budget(
        _entry(UncertaintyChannel.NUMERICAL, _standard(source_kind=UncertaintySource.NUMERICAL)),
        _entry(UncertaintyChannel.ALEATORIC,
               _standard(0.25, source_kind=UncertaintySource.MEASUREMENT)),
    )
    record = budget.aggregate(
        [UncertaintyChannel.NUMERICAL, UncertaintyChannel.ALEATORIC],
        assumptions=("channels are independent",), allow_cross_kind=True,
    )
    assert record.rule == "root_sum_square"


def test_r43_an_unattributed_quantified_channel_cannot_be_aggregated():
    """The audited harm: 'the SRIA budget marks aleatoric and model_form known from a numerical-only
    record' -- and then root-sum-squares them into a number attributed to channels nobody attributed."""
    budget = _budget(
        _entry(UncertaintyChannel.NUMERICAL, _standard(source_kind=UncertaintySource.NUMERICAL)),
        _entry(UncertaintyChannel.MODEL_FORM, _standard(0.25)),
    )
    assert budget.declaration is not None
    with pytest.raises(BudgetError, match="declares no source_kind"):
        budget.aggregate(
            [UncertaintyChannel.NUMERICAL, UncertaintyChannel.MODEL_FORM],
            assumptions=("channels are independent",), allow_cross_kind=True,
        )


def test_r43_one_unattributed_channel_on_its_own_is_not_aggregated_either():
    budget = _budget(_entry(UncertaintyChannel.ALEATORIC, _standard(0.25)))
    with pytest.raises(BudgetError, match="declares no source_kind"):
        budget.aggregate([UncertaintyChannel.ALEATORIC])


def test_r43_an_unquantified_channel_keeps_its_own_refusal():
    """The control that must not be swallowed: an UNKNOWN channel is refused for not being a number at
    all, which is a different sentence from 'nobody said whose number it is'."""
    budget = _budget(
        ChannelEntry(channel=UncertaintyChannel.MODEL_FORM, state=ChannelState.UNKNOWN,
                     uncertainty=Uncertainty.unknown("not evaluated"),
                     rationale="no model-form budget was put on this result"),
    )
    with pytest.raises(BudgetError, match="not .*quantified"):
        budget.aggregate([UncertaintyChannel.MODEL_FORM])


def test_r43_an_unattributed_channel_is_still_declarable_and_named():
    """It may be declared and read -- the pinned E1 and E2 harnesses do exactly that -- and the
    declaration names it, which is what makes the refusal above readable rather than surprising."""
    declaration = _declaration(**{UncertaintyChannel.ALEATORIC.value: _standard(0.25)})
    assert declaration.unattributed_channels == (UncertaintyChannel.ALEATORIC,)


def test_r43_a_record_declaring_another_channel_is_still_refused_where_it_is_filed():
    """The rule batch 8 left in place, unchanged: a NUMERICAL record filed under ALEATORIC is a
    numerical estimate counted as measurement scatter."""
    with pytest.raises(UncertaintyContractError, match="aleatoric"):
        sria_uncertainty.require_source_fits_channel(
            UncertaintyChannel.ALEATORIC, _standard(source_kind=UncertaintySource.NUMERICAL),
            where="test",
        )


# ---------------------------------------------------------------------------
# a predictive interval can be carried into a declaration
# ---------------------------------------------------------------------------
def test_r43_a_predictive_record_is_carried_onto_the_channel_it_names():
    parameter = _interval(source_kind=UncertaintySource.PARAMETER)
    channels = sria_uncertainty.channels_from_predictive_uncertainty({"T": parameter})
    assert channels == {UncertaintyChannel.EPISTEMIC_PARAMETER: parameter}


def test_r43_a_combined_record_is_refused_rather_than_filed():
    with pytest.raises(UncertaintyContractError, match="combined|mixture"):
        sria_uncertainty.channels_from_predictive_uncertainty(
            {"T": _interval(source_kind=UncertaintySource.COMBINED)})


def test_r43_an_unknown_record_carries_no_channel():
    assert sria_uncertainty.channels_from_predictive_uncertainty(
        {"T": Uncertainty.unknown("not evaluated")}) == {}


def test_r43_an_unattributed_quantified_record_carries_no_channel_either():
    """And it is refused rather than skipped: skipping would drop a number silently, which is the shape
    of the defect one level down."""
    with pytest.raises(UncertaintyContractError, match="declares no source_kind"):
        sria_uncertainty.channels_from_predictive_uncertainty({"T": _standard(0.25)})


def test_r43_the_carried_channels_are_what_a_declaration_accepts():
    """The two halves, connected: what the producer declares is what the declaration files."""
    parameter = _interval(source_kind=UncertaintySource.PARAMETER)
    channels = sria_uncertainty.channels_from_predictive_uncertainty({"T": parameter})
    declaration = UncertaintyDeclaration(
        subject_model=SubjectModel.PREDICTION_MODEL,
        discrepancy=ModelDiscrepancy(kind=DiscrepancyKind.ZERO_DECLARED, rationale="declared zero"),
        channels=channels,
    )
    assert declaration.unattributed_channels == ()
    assert declaration.channel(UncertaintyChannel.EPISTEMIC_PARAMETER) == parameter
