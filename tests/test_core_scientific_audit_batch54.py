"""Core re-audit 2026-09-16, batch 54: a quantified uncertainty says what it is an uncertainty OF.

Problem R-43 (the audit's findings 51 and 86), improvement I-25 part C -- the reach ledger's row for R-43
names I-25 as what closes it -- under benchmarks/core_v4_false_confidence/BATCH54_THRESHOLD_PROTOCOL.json.

Batch 8 gave the credibility report an `uncertainty` field carrying `source_kind`, declared PARAMETER and
COMBINED on the two V1 predictive intervals, and wrote the map that refuses a record filed under a channel
its own source contradicts. Its own status line says what stayed open: UNSPECIFIED is NAMED rather than
refused, the map accepts it in every row because every producer emitted it, and nothing carries a V1
interval into a declaration -- so the producer and the budget are two unconnected halves and the SRIA budget
marks aleatoric or model_form KNOWN from a record that never said it was either.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from engcore.scientific.units.quantity import Quantity
from engcore.sria import uncertainty as sria_uncertainty
from engcore.sria.uncertainty import (
    CHANNEL_ACCEPTS_SOURCE,
    UncertaintyChannel,
    UncertaintyContractError,
    require_source_fits_channel,
)


def _standard(**overrides) -> Uncertainty:
    fields = dict(
        kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(0.5, "kelvin"),
        source="calibration:T", method="posterior_std",
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


# ---------------------------------------------------------------------------
# a_quantified_uncertainty_says_what_it_is_of
# ---------------------------------------------------------------------------
def test_r43_an_unknown_uncertainty_still_says_nothing_and_that_is_honest():
    """The control, and what every domain solver in this repository emits."""
    unknown = Uncertainty.unknown("no quantification is performed on this metric")
    assert unknown.source_kind is UncertaintySource.UNSPECIFIED
    assert unknown.is_quantified is False


def test_r43_a_declared_standard_uncertainty_is_unchanged():
    """The control: a record that says what it is of."""
    assert _standard(source_kind=UncertaintySource.MEASUREMENT).source_kind is (
        UncertaintySource.MEASUREMENT)


@pytest.mark.xfail(strict=True, reason="R-43 finding 51 as audited: source_kind has no producer, so a quantified record that says nothing about what it is an uncertainty OF is accepted -- and a discretization estimate is then indistinguishable from a measurement standard deviation")
def test_r43_a_standard_uncertainty_with_no_declared_source_is_refused():
    with pytest.raises(ScientificCoreError, match="source_kind|what it is"):
        _standard()


@pytest.mark.xfail(strict=True, reason="R-43: and an interval likewise, which is the kind the production predictive path emits")
def test_r43_an_interval_with_no_declared_source_is_refused():
    with pytest.raises(ScientificCoreError, match="source_kind|what it is"):
        _interval()


@pytest.mark.xfail(strict=True, reason="R-43: a stored record with no declared source reads back the same way, because from_dict builds through the constructor")
def test_r43_a_stored_quantified_record_with_no_declared_source_is_refused_on_read():
    payload = _standard(source_kind=UncertaintySource.MEASUREMENT).to_dict()
    payload.pop("source_kind", None)
    payload["schema"] = "uncertainty/1"
    with pytest.raises(ScientificCoreError, match="source_kind|what it is"):
        Uncertainty.from_dict(payload)


# ---------------------------------------------------------------------------
# an_unattributed_quantified_channel_is_refused_where_it_is_aggregated
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-43 finding 51's budget claim as audited: CHANNEL_ACCEPTS_SOURCE lists UNSPECIFIED in every row, so the SRIA budget marks aleatoric or model_form KNOWN from a record that never said it was either")
def test_r43_the_channel_map_no_longer_accepts_an_undeclared_source():
    for channel, accepted in CHANNEL_ACCEPTS_SOURCE.items():
        assert UncertaintySource.UNSPECIFIED not in accepted, channel


def test_r43_a_record_declaring_another_channel_is_still_refused_where_it_is_filed():
    """The control the map is for, and the audited consequence in one line: a NUMERICAL-only record
    filed under ALEATORIC is a numerical estimate counted as measurement scatter. After the rule above,
    an UNATTRIBUTED quantified record cannot be built at all, which is the stronger statement -- so what
    this test guards is the half that remains expressible."""
    with pytest.raises(UncertaintyContractError, match="aleatoric"):
        require_source_fits_channel(
            UncertaintyChannel.ALEATORIC,
            _standard(source_kind=UncertaintySource.NUMERICAL),
            where="test",
        )


def test_r43_an_unknown_record_may_still_be_filed_under_a_channel():
    """The control: filing 'nobody evaluated this' under a channel is how a declaration says so."""
    require_source_fits_channel(
        UncertaintyChannel.MODEL_FORM, Uncertainty.unknown("not evaluated"), where="test")


# ---------------------------------------------------------------------------
# a_predictive_interval_can_be_carried_into_a_declaration
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-43 as audited: nothing carries a V1 interval into an UncertaintyDeclaration, so the producer and the budget are two unconnected halves and the map has nothing production-made to check")
def test_r43_a_predictive_record_is_carried_onto_the_channel_it_names():
    carry = getattr(sria_uncertainty, "channels_from_predictive_uncertainty", None)
    if carry is None:
        pytest.fail("there is no way to carry a declared V1 uncertainty onto the channel its own "
                    "source_kind names, so the producer and the budget stay unconnected")
    parameter = _interval(source_kind=UncertaintySource.PARAMETER)
    channels = carry({"T": parameter})
    assert channels == {UncertaintyChannel.EPISTEMIC_PARAMETER: parameter}


@pytest.mark.xfail(strict=True, reason="R-43: and a COMBINED record is a mixture of channels, which no channel may accept")
def test_r43_a_combined_record_is_refused_rather_than_filed():
    carry = getattr(sria_uncertainty, "channels_from_predictive_uncertainty", None)
    if carry is None:
        pytest.fail("no carrying function exists, so nothing refuses a COMBINED record at that boundary")
    with pytest.raises(UncertaintyContractError, match="COMBINED|combined"):
        carry({"T": _interval(source_kind=UncertaintySource.COMBINED)})


@pytest.mark.xfail(strict=True, reason="R-43: an UNKNOWN record carries no channel, and skipping it is what lets a production record with unquantified metrics be carried at all")
def test_r43_an_unknown_record_carries_no_channel():
    carry = getattr(sria_uncertainty, "channels_from_predictive_uncertainty", None)
    if carry is None:
        pytest.fail("no carrying function exists")
    assert carry({"T": Uncertainty.unknown("not evaluated")}) == {}
