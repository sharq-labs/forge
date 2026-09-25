"""Core re-audit 2026-09-16, batch 48: an uncertainty that crossed is an uncertainty OF what crossed.

Problem R-58 (the audit's finding 71), improvement I-27 part B of three, under
benchmarks/core_v4_false_confidence/BATCH48_THRESHOLD_PROTOCOL.json.

`UncertaintyTransfer` checks only that the propagated record follows from whatever source uncertainty was
handed in. So an INTERVAL of [10, 11] K propagates for a transfer whose value is 350 K; an uncertainty about
another quantity, from another run, is accepted and then RELABELLED as coming from this crossing's source; a
chain carrying 350 K and then 400 K propagates one width along a path nothing travelled; and the only sign
that a conversion's efficiency uncertainty is missing is a note.

Recorded as strict xfails in commit 888cdcfb, each seen failing on its own assertion, before the fix.
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


def test_r58_an_interval_that_does_not_contain_the_value_is_refused():
    with pytest.raises(InvalidScientificProblem, match="interval|contain"):
        propagate_transfer_uncertainty(_transport(), _interval(10.0, 11.0))


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
def test_r58_an_uncertainty_about_another_quantity_is_refused():
    with pytest.raises(InvalidScientificProblem, match="source|names"):
        propagate_transfer_uncertainty(_transport(), _standard(1.0e-6, source="some-other-quantity"))


def test_r58_an_uncertainty_attributed_to_nothing_is_refused():
    with pytest.raises(InvalidScientificProblem, match="source|names"):
        propagate_transfer_uncertainty(_transport(), _standard(source=""))


def test_r58_the_attributions_the_record_itself_names_are_accepted():
    """The control: the candidates are what the crossing already names."""
    # Exact identities, alone or as the value of a `label:value` clause. Prose that merely CONTAINS one is not
    # an attribution (see test_r58_prose_containing_an_identity_is_not_an_attribution).
    for attribution in (RECORD, "thermal.a", "temperature", f"posterior:{RECORD}", "thermal.a.temperature"):
        assert propagate_transfer_uncertainty(_transport(), _standard(source=attribution)) is not None


def test_r58_prose_containing_an_identity_is_not_an_attribution():
    """An identity buried in a sentence names nothing: matching it as a substring is what spoofing exploits."""
    for attribution in (f"posterior of {RECORD}", f"{RECORD}_of_another_run", "posterior:temperature@thermal.a"):
        with pytest.raises(InvalidScientificProblem, match="names nothing"):
            propagate_transfer_uncertainty(_transport(), _standard(source=attribution))


# ---------------------------------------------------------------------------
# the_propagated_record_keeps_the_original_attribution
# ---------------------------------------------------------------------------
def test_r58_the_propagated_record_keeps_both_references():
    propagated = propagate_transfer_uncertainty(_transport(), _standard(source="posterior:thermal.a.temperature"))
    assert "posterior:thermal.a.temperature" in propagated.source, propagated.source
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


def test_r58_a_chain_whose_values_do_not_meet_is_refused():
    first = _transport("thermal.a", "thermal.b", target_quantity="temperature_in")
    second = _transport("thermal.b", "thermal.c", source_quantity="temperature_in",
                        target_quantity="temperature_in", value=Quantity(400.0, "kelvin"))
    with pytest.raises(InvalidScientificProblem, match="meet|value"):
        propagate_uncertainty_chain((first, second), _standard())


# ---------------------------------------------------------------------------
# an_undeclared_efficiency_uncertainty_is_structural
# ---------------------------------------------------------------------------
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
    # 100 W in at 0.8 is 80 W out. The relative widths are 5/100 = 0.05 and 0.04/0.8 = 0.05, and in
    # quadrature that is 0.05 * sqrt(2) = 0.0707106..., so the propagated width is 5.65685... W.
    #
    # The preregistered form of this test wrote 0.0640312 here, which is arithmetic this file got wrong
    # rather than a threshold: 0.04/0.8 is 0.05 and not 0.04. Corrected in place, with the reason, and
    # recorded as amendment 1 in BATCH48_THRESHOLD_PROTOCOL.json -- the RULE (relative quadrature) is the
    # one preregistered before anything was scored.
    assert item.uncertainty.standard_uncertainty is not None
    assert item.uncertainty.standard_uncertainty.magnitude_in("watt") == pytest.approx(
        80.0 * (2.0 ** 0.5) * 0.05)


def test_r58_a_transport_is_complete():
    item = make_uncertainty_transfer(_transport(), _standard())
    names = {field.name for field in dataclasses.fields(UncertaintyTransfer)}
    assert "completeness" in names, "a transport cannot say that nothing was missing"
    assert item.completeness == "complete"


# ---------------------------------------------------------------------------
# the remaining declared rules and the cases the batch's guard mutations need,
# written while running them rather than preregistered as reproductions
# ---------------------------------------------------------------------------
def test_r58_a_chain_link_records_the_crossing_that_fed_it():
    """A chain is the one case where the entering uncertainty carries the PREVIOUS crossing's attribution,
    so the record says which crossing that was instead of the caller being trusted for it."""
    first = _transport("thermal.a", "thermal.b", target_quantity="temperature_in")
    second = _transport("thermal.b", "thermal.c", source_quantity="temperature_in",
                        target_quantity="temperature_in")
    chain = propagate_uncertainty_chain((first, second), _standard())
    assert chain[0].upstream is None
    assert chain[1].upstream == first
    assert UncertaintyTransfer.from_dict(chain[1].to_dict()) == chain[1]


def test_r58_a_chain_link_taken_out_of_its_chain_is_refused():
    """And the record cannot keep the attribution while dropping the crossing that justified it."""
    first = _transport("thermal.a", "thermal.b", target_quantity="temperature_in")
    second = _transport("thermal.b", "thermal.c", source_quantity="temperature_in",
                        target_quantity="temperature_in", source_record_id="thermal-b-result")
    link = propagate_uncertainty_chain((first, second), _standard())[1]
    assert link.upstream is not None and link.upstream.source_record_id != link.transfer.source_record_id
    with pytest.raises(InvalidScientificProblem, match="names nothing"):
        UncertaintyTransfer(link.transfer, link.source_uncertainty, link.uncertainty, link.completeness)


def test_r58_a_record_cannot_state_a_completeness_its_own_arithmetic_denies():
    item = make_uncertainty_transfer(_converting_transfer(), _standard(5.0, "watt"))
    with pytest.raises(InvalidScientificProblem, match="completeness"):
        UncertaintyTransfer(item.transfer, item.source_uncertainty, item.uncertainty, "complete")


def test_r58_an_efficiency_uncertainty_as_wide_as_the_efficiency_is_refused():
    """A width that reaches the fraction it is about says the fraction is unknown, while looking measured."""
    with pytest.raises(InvalidScientificProblem, match="efficiency_uncertainty"):
        _conversion(efficiency_uncertainty=0.8)


def test_r58_an_efficiency_uncertainty_without_an_efficiency_is_refused():
    with pytest.raises(InvalidScientificProblem, match="uncertainty of nothing|efficiency_uncertainty"):
        EnergyConversion(name="unknown_efficiency", input_form="a", output_form="b",
                         unit_exemplar="watt", efficiency_uncertainty=0.05)


def test_r58_an_unknown_uncertainty_still_crosses_unbound():
    """UNKNOWN asserts nothing about any value, so there is nothing to bind and nothing to contain."""
    propagated = propagate_transfer_uncertainty(_transport(), Uncertainty.unknown("not evaluated"))
    assert propagated.kind is UncertaintyKind.UNKNOWN
    assert "not evaluated" in propagated.notes


def test_r58_an_interval_under_a_conversion_stays_a_lower_bound_even_when_the_efficiency_is_declared():
    """Combining a bound with a standard uncertainty needs a distribution nobody declared, and the record
    says so rather than quietly widening the bounds."""
    conversion = _conversion(efficiency_uncertainty=0.04)
    entering = Uncertainty(
        kind=UncertaintyKind.INTERVAL, lower=Quantity(95.0, "watt"), upper=Quantity(105.0, "watt"),
        confidence_level=0.95, source=RECORD, method="credible_interval",
    )
    item = make_uncertainty_transfer(_converting_transfer(conversion), entering)
    assert item.completeness == "lower_bound_efficiency_uncertainty_undeclared"


def test_r58_a_conversions_interval_is_about_the_input_and_not_the_output():
    """Found while running this batch's mutations: the case only the entering-value rule sees. [79, 81] W
    contains the 80 W that ARRIVED and not the 100 W that entered, and the interval is about the input."""
    entering = Uncertainty(
        kind=UncertaintyKind.INTERVAL, lower=Quantity(79.0, "watt"), upper=Quantity(81.0, "watt"),
        confidence_level=0.95, source=RECORD, method="credible_interval",
    )
    with pytest.raises(InvalidScientificProblem, match="does not contain"):
        propagate_transfer_uncertainty(_converting_transfer(), entering)


def test_r58_a_chain_across_two_records_still_propagates():
    """Also found there: a chain whose crossings name DIFFERENT records, which is the only case where the
    upstream crossing is what justifies the entering attribution."""
    first = _transport("thermal.a", "thermal.b", target_quantity="temperature_in")
    second = _transport("thermal.b", "thermal.c", source_quantity="temperature_in",
                        target_quantity="temperature_in", source_record_id="thermal-b-result")
    chain = propagate_uncertainty_chain((first, second), _standard())
    assert len(chain) == 2 and chain[1].upstream == first
