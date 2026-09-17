"""Core re-audit 2026-09-16, batch 48: an uncertainty that crossed is an uncertainty OF what crossed.

Problem R-58 (the audit's finding 71), improvement I-27 part B of three, under
benchmarks/core_v4_false_confidence/BATCH48_THRESHOLD_PROTOCOL.json.

`UncertaintyTransfer` checks only that the propagated record follows from whatever source uncertainty was
handed in. So an INTERVAL of [10, 11] K propagates for a transfer whose value is 350 K; an uncertainty about
another quantity, from another run, is accepted and then RELABELLED as coming from this crossing's source; a
chain carrying 350 K and then 400 K propagates one width along a path nothing travelled; and the only sign
that a conversion's efficiency uncertainty is missing is a note.
"""

from __future__ import annotations

import dataclasses

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

RECORD = "thermal-result"


def _transport(source_problem: str = "thermal.a", target_problem: str = "electrical.b",
               *, source_quantity: str = "temperature", target_quantity: str = "ambient_temperature",
               value: Quantity | None = None, instant: str = "iteration:4",
               source_record_id: str = RECORD) -> QuantityTransfer:
    dependency = QuantityDependency(
        source_problem_id=source_problem, source_quantity=source_quantity,
        target_problem_id=target_problem, target_quantity=target_quantity, unit_exemplar="kelvin",
    )
    return QuantityTransfer(
        dependency=dependency, value=value or Quantity(350.0, "kelvin"),
        source_record_id=source_record_id, instant=instant,
    )


def _standard(value: float = 2.0, unit: str = "kelvin", **overrides) -> Uncertainty:
    fields = dict(
        kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(value, unit),
        source=RECORD, method="posterior_std",
    )
    fields.update(overrides)
    return Uncertainty(**fields)


def _interval(lower: float, upper: float, **overrides) -> Uncertainty:
    fields = dict(
        kind=UncertaintyKind.INTERVAL, lower=Quantity(lower, "kelvin"), upper=Quantity(upper, "kelvin"),
        confidence_level=0.95, source=RECORD, method="credible_interval",
    )
    fields.update(overrides)
    return Uncertainty(**fields)


def _conversion(**overrides) -> EnergyConversion:
    fields = dict(
        name="electrical_to_thermal", input_form="electrical", output_form="thermal",
        unit_exemplar="watt", efficiency=0.8, losses=(LossPath("radiated", 0.2),),
    )
    fields.update(overrides)
    return EnergyConversion(**fields)


def _converting_transfer(conversion=None, *, entered: float = 100.0) -> QuantityTransfer:
    conversion = conversion if conversion is not None else _conversion()
    dependency = QuantityDependency(
        source_problem_id="electrical.a", source_quantity="dissipated_power",
        target_problem_id="thermal.b", target_quantity="applied_power",
        unit_exemplar="watt", conversion=conversion,
    )
    return QuantityTransfer(
        dependency=dependency, value=Quantity(entered * conversion.efficiency, "watt"),
        source_value=Quantity(entered, "watt"), source_record_id=RECORD, instant="iteration:4",
    )


# ---------------------------------------------------------------------------
# an_interval_is_about_the_value_that_crossed
# ---------------------------------------------------------------------------
def test_r58_an_interval_around_the_value_still_crosses():
    """The control: 348 to 352 K about a crossing of 350 K."""
    propagated = propagate_transfer_uncertainty(_transport(), _interval(348.0, 352.0))
    assert propagated.lower is not None and propagated.lower.magnitude_in("kelvin") == pytest.approx(348.0)


@pytest.mark.xfail(strict=True, reason="R-58 finding 71 claim (a) as audited: an INTERVAL of [10, 11] K propagates for a transfer whose value is 350 K and round-trips")
def test_r58_an_interval_that_does_not_contain_the_value_is_refused():
    with pytest.raises(InvalidScientificProblem, match="interval|contain"):
        propagate_transfer_uncertainty(_transport(), _interval(10.0, 11.0))


@pytest.mark.xfail(strict=True, reason="R-58: for a conversion the interval is about what ENTERED, and nothing compared it with source_value either")
def test_r58_a_conversions_interval_is_about_what_entered_it():
    entering = Uncertainty(
        kind=UncertaintyKind.INTERVAL, lower=Quantity(10.0, "watt"), upper=Quantity(11.0, "watt"),
        confidence_level=0.95, source=RECORD, method="credible_interval",
    )
    with pytest.raises(InvalidScientificProblem, match="interval|contain"):
        propagate_transfer_uncertainty(_converting_transfer(), entering)


# ---------------------------------------------------------------------------
# the_source_uncertainty_names_the_crossings_source
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-58 finding 71 claim (c) as audited: a 1e-6 K NUMERICAL uncertainty from another run is accepted, because nothing ties the uncertainty to the crossing")
def test_r58_an_uncertainty_about_another_quantity_is_refused():
    with pytest.raises(InvalidScientificProblem, match="source|names"):
        propagate_transfer_uncertainty(_transport(), _standard(1.0e-6, source="some-other-quantity"))


@pytest.mark.xfail(strict=True, reason="R-58: an uncertainty with no attribution at all propagates, and the propagated record then carries the transfer id as though it had one")
def test_r58_an_uncertainty_attributed_to_nothing_is_refused():
    with pytest.raises(InvalidScientificProblem, match="source|names"):
        propagate_transfer_uncertainty(_transport(), _standard(source=""))


def test_r58_the_attributions_the_record_itself_names_are_accepted():
    """The control: the candidates are what the crossing already names."""
    for attribution in (RECORD, "thermal.a", "temperature", f"posterior of {RECORD}"):
        assert propagate_transfer_uncertainty(_transport(), _standard(source=attribution)) is not None


# ---------------------------------------------------------------------------
# the_propagated_record_keeps_the_original_attribution
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-58 finding 71 claim (b) as audited: the propagated source is OVERWRITTEN with transfer:<id>, so the original attribution is gone")
def test_r58_the_propagated_record_keeps_both_references():
    propagated = propagate_transfer_uncertainty(_transport(), _standard(source="posterior:temperature@thermal.a"))
    assert "posterior:temperature@thermal.a" in propagated.source, propagated.source
    assert f"transfer:{RECORD}" in propagated.source, propagated.source


# ---------------------------------------------------------------------------
# a_chain_propagates_only_where_the_values_meet
# ---------------------------------------------------------------------------
def test_r58_a_chain_whose_values_meet_still_propagates():
    """The control: 350 K leaves the first crossing and 350 K enters the second."""
    first = _transport("thermal.a", "thermal.b", target_quantity="temperature_in")
    second = _transport("thermal.b", "thermal.c", source_quantity="temperature_in",
                        target_quantity="temperature_in")
    chain = propagate_uncertainty_chain((first, second), _standard())
    assert len(chain) == 2


@pytest.mark.xfail(strict=True, reason="R-58 finding 71 claim (d) as audited: the chain checks name connectivity and equal instants only, so 350 K then 400 K propagate the same 2 K")
def test_r58_a_chain_whose_values_do_not_meet_is_refused():
    first = _transport("thermal.a", "thermal.b", target_quantity="temperature_in")
    second = _transport("thermal.b", "thermal.c", source_quantity="temperature_in",
                        target_quantity="temperature_in", value=Quantity(400.0, "kelvin"))
    with pytest.raises(InvalidScientificProblem, match="meet|value"):
        propagate_uncertainty_chain((first, second), _standard())


# ---------------------------------------------------------------------------
# an_undeclared_efficiency_uncertainty_is_structural
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-58 as audited: with a conversion the efficiency is treated as exact while the output keeps kind STANDARD, and the only sign that its uncertainty is missing is a note")
def test_r58_a_conversion_with_no_declared_efficiency_uncertainty_says_so_structurally():
    entering = Uncertainty(
        kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(5.0, "watt"),
        source=RECORD, method="posterior_std",
    )
    item = make_uncertainty_transfer(_converting_transfer(), entering)
    names = {field.name for field in dataclasses.fields(UncertaintyTransfer)}
    assert "completeness" in names, (
        "the record says nothing structural about the efficiency uncertainty it did not propagate")
    assert item.completeness == "lower_bound_efficiency_uncertainty_undeclared"


@pytest.mark.xfail(strict=True, reason="R-58: there is nowhere to declare an efficiency uncertainty, so the propagated width can only ever be a lower bound")
def test_r58_a_declared_efficiency_uncertainty_is_propagated_in_quadrature():
    names = {field.name for field in dataclasses.fields(EnergyConversion)}
    assert "efficiency_uncertainty" in names, "an efficiency's own uncertainty has nowhere to be declared"
    conversion = _conversion(efficiency_uncertainty=0.04)
    entering = Uncertainty(
        kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(5.0, "watt"),
        source=RECORD, method="posterior_std",
    )
    item = make_uncertainty_transfer(_converting_transfer(conversion), entering)
    assert item.completeness == "complete"
    # 100 W in at 0.8 is 80 W out; 5/100 and 0.04/0.8 in quadrature is 0.0640312...
    assert item.uncertainty.standard_uncertainty is not None
    assert item.uncertainty.standard_uncertainty.magnitude_in("watt") == pytest.approx(80.0 * 0.06403124237)


@pytest.mark.xfail(strict=True, reason="R-58: a transport has no efficiency, so nothing was ever missing there -- and there was no field in which to say that either")
def test_r58_a_transport_is_complete():
    item = make_uncertainty_transfer(_transport(), _standard())
    names = {field.name for field in dataclasses.fields(UncertaintyTransfer)}
    assert "completeness" in names, "a transport cannot say that nothing was missing"
    assert item.completeness == "complete"
