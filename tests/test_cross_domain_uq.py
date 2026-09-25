"""Quantified uncertainty follows the same declared path as transferred values."""

from __future__ import annotations

import pytest

from engcore.scientific.composition.conversion import EnergyConversion, LossPath
from engcore.scientific.composition.dependency import QuantityDependency
from engcore.scientific.composition.transfer import QuantityTransfer
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity
from engcore.uq.cross_domain import (
    UncertaintyTransfer,
    make_uncertainty_transfer,
    propagate_transfer_uncertainty,
    propagate_uncertainty_chain,
)


def _transport(
    source_problem: str = "thermal.a",
    source_quantity: str = "temperature",
    target_problem: str = "thermal.b",
    target_quantity: str = "temperature_in",
    *,
    value: Quantity | None = None,
    instant: str = "iteration:4",
) -> QuantityTransfer:
    dependency = QuantityDependency(
        source_problem_id=source_problem,
        source_quantity=source_quantity,
        target_problem_id=target_problem,
        target_quantity=target_quantity,
        unit_exemplar="kelvin",
    )
    return QuantityTransfer(
        dependency=dependency,
        value=value or Quantity(300.0, "kelvin"),
        source_record_id=f"result:{source_problem}",
        instant=instant,
    )


def _standard(value: float = 2.0, unit: str = "kelvin", source: str | None = None) -> Uncertainty:
    # R-58 (I-27 part B): a source uncertainty must be attributed to something the crossing itself names,
    # or it is the parallel dictionary keyed by a coincidentally matching name that this module replaces.
    # The default names the quantity; the chain and conversion cases pass their own.
    return Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(value, unit),
        source=source or "calibration:temperature",
        method="posterior_std",
    )


def test_standard_uncertainty_crosses_plain_domain_transport():
    transfer = _transport()
    propagated = propagate_transfer_uncertainty(transfer, _standard())
    assert propagated.kind is UncertaintyKind.STANDARD
    assert propagated.standard_uncertainty is not None
    assert propagated.standard_uncertainty.magnitude_in("kelvin") == pytest.approx(2.0)
    # R-58: the propagated record now carries BOTH provenances -- what the uncertainty was an uncertainty
    # of, and the crossing it came through. Writing only the second is what made another quantity's
    # uncertainty read as this run's.
    assert propagated.source == "transfer:result:thermal.a|from:calibration:temperature"
    assert propagated.method == "cross_domain_transport"


def test_standard_uncertainty_uses_delta_conversion_for_offset_units():
    # 2 K of uncertainty is a 2 degree-Celsius WIDTH. Treating it as an
    # absolute value would produce roughly -271.15 degree_Celsius, which is the
    # exact category error this test prevents.
    transfer = _transport(value=Quantity(26.85, "degree_Celsius"))
    propagated = propagate_transfer_uncertainty(transfer, _standard(2.0, "kelvin"))
    spread = propagated.standard_uncertainty
    assert spread is not None
    # A spread cannot be stated on an absolute affine coordinate, so it is
    # carried on the dimension's base unit -- and it is 2 wide on either scale.
    assert spread.units == "kelvin"
    assert spread.magnitude == pytest.approx(2.0)
    assert spread.magnitude_as_spread_in("delta_degC") == pytest.approx(2.0)


def test_interval_bounds_are_absolute_values_and_keep_offset_semantics():
    transfer = _transport(value=Quantity(26.85, "degree_Celsius"))
    source = Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(298.0, "kelvin"),
        upper=Quantity(302.0, "kelvin"),
        confidence_level=0.95,
        # R-58: attributed to the record the crossing names, and an interval that must contain the value
        # it is about -- 26.85 degC is 300 K, inside [298, 302] K.
        source="posterior of result:thermal.a",
        method="credible_interval",
    )
    propagated = propagate_transfer_uncertainty(transfer, source)
    assert propagated.lower is not None and propagated.upper is not None
    assert propagated.lower.magnitude_in("degree_Celsius") == pytest.approx(24.85)
    assert propagated.upper.magnitude_in("degree_Celsius") == pytest.approx(28.85)
    assert propagated.confidence_level == 0.95


def test_deterministic_energy_conversion_scales_standard_uncertainty():
    conversion = EnergyConversion(
        name="electrical_to_mechanical",
        input_form="electrical",
        output_form="mechanical",
        unit_exemplar="watt",
        efficiency=0.8,
        losses=(LossPath("heat", 0.2),),
    )
    dependency = QuantityDependency(
        source_problem_id="electrical",
        source_quantity="input_power",
        target_problem_id="mechanical",
        target_quantity="shaft_power",
        unit_exemplar="watt",
        conversion=conversion,
    )
    transfer = QuantityTransfer(
        dependency=dependency,
        source_value=Quantity(100.0, "watt"),
        value=Quantity(80.0, "watt"),
        source_record_id="electrical:r1",
        instant="stage:1",
    )
    # R-58: attributed to what the crossing names -- here the source quantity of the declaration.
    propagated = propagate_transfer_uncertainty(
        transfer, _standard(5.0, "watt", source="calibration:input_power"))
    assert propagated.standard_uncertainty is not None
    assert propagated.standard_uncertainty.magnitude_in("watt") == pytest.approx(4.0)
    assert propagated.method == "cross_domain_conversion:electrical_to_mechanical"


def test_unknown_uncertainty_stays_unknown_instead_of_becoming_zero():
    source = Uncertainty.unknown("not measured")
    propagated = propagate_transfer_uncertainty(_transport(), source)
    assert propagated.kind is UncertaintyKind.UNKNOWN
    assert propagated.standard_uncertainty is None
    assert "not measured" in propagated.notes


def test_connected_chain_propagates_the_same_uncertainty_across_domains():
    first = _transport(
        source_problem="domain.a",
        source_quantity="x",
        target_problem="domain.b",
        target_quantity="y",
    )
    second = _transport(
        source_problem="domain.b",
        source_quantity="y",
        target_problem="domain.c",
        target_quantity="z",
    )
    # R-58: attributed to the quantity the first crossing carries, and the two crossings now have to meet
    # by VALUE as well as by name -- both transports carry 350 K, which is what a chain is.
    chain = propagate_uncertainty_chain((first, second), _standard(1.5, source="calibration:x"))
    assert len(chain) == 2
    assert chain[-1].uncertainty.standard_uncertainty is not None
    assert chain[-1].uncertainty.standard_uncertainty.magnitude_in("kelvin") == pytest.approx(1.5)


def test_disconnected_chain_is_refused_instead_of_matching_similar_units():
    first = _transport(
        source_problem="domain.a",
        source_quantity="x",
        target_problem="domain.b",
        target_quantity="y",
    )
    second = _transport(
        source_problem="domain.b",
        source_quantity="different_name",
        target_problem="domain.c",
        target_quantity="z",
    )
    with pytest.raises(InvalidScientificProblem, match="disconnected"):
        propagate_uncertainty_chain((first, second), _standard(source="calibration:x"))


def test_chain_cannot_jump_between_instants_without_a_temporal_model():
    first = _transport(
        source_problem="domain.a",
        source_quantity="x",
        target_problem="domain.b",
        target_quantity="y",
        instant="step:1",
    )
    second = _transport(
        source_problem="domain.b",
        source_quantity="y",
        target_problem="domain.c",
        target_quantity="z",
        instant="step:2",
    )
    with pytest.raises(InvalidScientificProblem, match="temporal evolution"):
        propagate_uncertainty_chain((first, second), _standard(source="calibration:x"))


def test_uncertainty_transfer_round_trip_recomputes_the_propagation():
    item = make_uncertainty_transfer(_transport(), _standard(0.5))
    restored = UncertaintyTransfer.from_dict(item.to_dict())
    assert restored == item


def test_hand_forged_propagated_uncertainty_is_refused():
    transfer = _transport()
    source = _standard(1.0)
    wrong = Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(99.0, "kelvin"),
        source="forged",
        method="forged",
    )
    with pytest.raises(InvalidScientificProblem, match="does not follow"):
        UncertaintyTransfer(transfer, source, wrong)


def test_source_uncertainty_attribution_does_not_accept_substring_spoofing():
    with pytest.raises(InvalidScientificProblem, match="names nothing"):
        propagate_transfer_uncertainty(
            _transport(),
            _standard(source="calibration:temperature_extra"),
        )
