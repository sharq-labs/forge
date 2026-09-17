"""Core re-audit 2026-09-16, batch 47: what a crossing's own record binds.

Problems R-60 (finding 73), R-61 (findings 74 and 75) and R-64 (finding 78), improvement I-27 part A of
two, under benchmarks/core_v4_false_confidence/BATCH47_THRESHOLD_PROTOCOL.json.

The conversion budget is floored at one unit of an exemplar the conversion author chose, so a small crossing
carries the whole input against a declared half. Agreement compares unit STRINGS, so one value spelled twice
makes a whole ProvenanceRecord unconstructible -- and a stale instant and the final one coexist, with the
canonical order putting iteration 9 after iteration 10. And energy crossing as a flux density needs no
declared conversion at all, while plain watt is refused.
"""

from __future__ import annotations

import pytest

from engcore.scientific.composition.conversion import EnergyConversion, LossPath
from engcore.scientific.composition.dependency import QuantityDependency
from engcore.scientific.composition.transfer import (
    QuantityTransfer,
    require_agreeing_transfers,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

HALF = EnergyConversion(
    name="half_arrives", input_form="electrical", output_form="thermal",
    unit_exemplar="gigawatt", efficiency=0.5,
    losses=(LossPath(form="radiation", fraction=0.5),),
)


def _symbol(module_path: str, name: str):
    """The symbol, or None -- so a missing name is an assertion and not an ImportError."""
    import importlib

    return getattr(importlib.import_module(module_path), name, None)


def _dependency(*, unit_exemplar: str = "kelvin", conversion=None, **overrides):
    fields = dict(
        source_problem_id="thermal.a", source_quantity="temperature",
        target_problem_id="electrical.b", target_quantity="ambient_temperature",
        unit_exemplar=unit_exemplar, conversion=conversion,
    )
    fields.update(overrides)
    return QuantityDependency(**fields)


def _transfer(dependency=None, **overrides):
    fields = dict(
        dependency=dependency if dependency is not None else _dependency(),
        value=Quantity(300.0, "kelvin"), source_record_id="thermal-result", instant="coupled_iteration:10",
    )
    fields.update(overrides)
    return QuantityTransfer(**fields)


# ---------------------------------------------------------------------------
# the_conversion_budget_is_purely_relative
# ---------------------------------------------------------------------------
def test_r60_an_honest_conversion_transfer_is_unchanged():
    """The control: half of a gigawatt arriving as half a gigawatt."""
    dependency = _dependency(unit_exemplar="gigawatt", conversion=HALF)
    transfer = QuantityTransfer(
        dependency=dependency, value=Quantity(0.5, "gigawatt"), source_value=Quantity(1.0, "gigawatt"),
        source_record_id="electrical-result", instant="stage:1",
    )
    assert transfer.value.magnitude_in("gigawatt") == pytest.approx(0.5)


@pytest.mark.xfail(strict=True, reason="R-60 finding 73 as audited: the budget check floors its scale at 1.0 of the conversion's exemplar unit, so below one exemplar unit it is an absolute 1e-9 criterion")
def test_r60_a_small_crossing_carrying_everything_is_refused():
    """As audited: 1 mW in, 1 mW out, against a declared efficiency of 0.5 and a gigawatt exemplar."""
    dependency = _dependency(unit_exemplar="gigawatt", conversion=HALF)
    with pytest.raises(InvalidScientificProblem, match="budgets|disagree"):
        QuantityTransfer(
            dependency=dependency, value=Quantity(1.0, "milliwatt"), source_value=Quantity(1.0, "milliwatt"),
            source_record_id="electrical-result", instant="stage:1",
        )


@pytest.mark.xfail(strict=True, reason="R-60: below the floor, an arrival of zero against a declared half also passes")
def test_r60_a_small_crossing_carrying_nothing_is_refused():
    dependency = _dependency(unit_exemplar="gigawatt", conversion=HALF)
    with pytest.raises(InvalidScientificProblem, match="budgets|disagree"):
        QuantityTransfer(
            dependency=dependency, value=Quantity(0.0, "watt"), source_value=Quantity(1.0, "milliwatt"),
            source_record_id="electrical-result", instant="stage:1",
        )


def test_r60_a_crossing_of_exactly_nothing_still_agrees_with_a_budget_of_nothing():
    """The control at the limit: zero in, zero out, which the relative rule must still accept."""
    dependency = _dependency(unit_exemplar="gigawatt", conversion=HALF)
    transfer = QuantityTransfer(
        dependency=dependency, value=Quantity(0.0, "watt"), source_value=Quantity(0.0, "watt"),
        source_record_id="electrical-result", instant="stage:1",
    )
    assert transfer.value.magnitude_in("watt") == 0.0


# ---------------------------------------------------------------------------
# transfer_agreement_compares_values_and_not_unit_strings
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-61 finding 74 as audited: agreement is dataclass equality over Quantity(magnitude, units-string), so 300.0 kelvin and 26.85 degC are 'two different values'")
def test_r61_one_value_spelled_in_two_units_agrees():
    """As audited: the refusal even printed '300.0 kelvin and 300.0 kelvin'."""
    dependency = _dependency()
    kelvin = _transfer(dependency)
    celsius = _transfer(dependency, value=Quantity(26.85, "degC"))
    try:
        agreed = require_agreeing_transfers((kelvin, celsius))
    except InvalidScientificProblem as refusal:
        agreed = ()
        assert not str(refusal), f"one value spelled twice was refused: {refusal}"
    assert len(agreed) == 1


def test_r61_two_genuinely_different_values_are_still_refused():
    """The control, and the reason the rule compares values rather than dropping the check."""
    dependency = _dependency()
    with pytest.raises(InvalidScientificProblem, match="different values"):
        require_agreeing_transfers((_transfer(dependency), _transfer(dependency, value=Quantity(400.0, "kelvin"))))


# ---------------------------------------------------------------------------
# two_record_ids_carrying_one_value_agree
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-61 finding 74's second claim: one value read from two result ids at one instant is refused as a contradiction")
def test_r61_one_value_from_two_records_agrees():
    dependency = _dependency()
    left = _transfer(dependency, source_record_id="thermal-result-a")
    right = _transfer(dependency, source_record_id="thermal-result-b")
    try:
        agreed = require_agreeing_transfers((left, right))
    except InvalidScientificProblem as refusal:
        agreed = ()
        assert not str(refusal), f"one value read from two records was refused: {refusal}"
    assert len(agreed) == 1


@pytest.mark.xfail(strict=True, reason="R-61: the refusal message prints the two values and never the record ids they came from")
def test_r61_the_refusal_names_the_records_that_disagree():
    dependency = _dependency()
    left = _transfer(dependency, source_record_id="thermal-result-a")
    right = _transfer(dependency, source_record_id="thermal-result-b", value=Quantity(400.0, "kelvin"))
    with pytest.raises(InvalidScientificProblem, match="thermal-result-a"):
        require_agreeing_transfers((left, right))


# ---------------------------------------------------------------------------
# one_run_records_one_instant_per_dependency
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-61 finding 75 as audited: require_agreeing_transfers keys on the instant, so a stale iteration 9 and the final iteration 10 coexist in one record")
def test_r61_a_stale_instant_cannot_sit_beside_the_final_one():
    """As audited: and the canonical sort puts 'coupled_iteration:9' AFTER 'coupled_iteration:10',
    so a consumer keeping the last transfer per component selects the stale 400 K over the final 300 K."""
    dependency = _dependency()
    final = _transfer(dependency, instant="coupled_iteration:10")
    stale = _transfer(dependency, instant="coupled_iteration:9", value=Quantity(400.0, "kelvin"))
    with pytest.raises(InvalidScientificProblem, match="instant"):
        require_agreeing_transfers((final, stale))


# ---------------------------------------------------------------------------
# a_transfer_says_where_its_value_came_from_and_can_be_checked_against_it
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-61 finding 75 as audited: source_record_id is checked for being non-empty and against nothing else, and there is no API to check a transfer against the record it names")
def test_r61_a_transfer_can_be_checked_against_the_record_it_names():
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ScientificResult

    if not hasattr(QuantityTransfer, "check_against_result"):
        pytest.fail("QuantityTransfer has no check_against_result: a transfer names a record and "
                    "nothing can ask the record whether it says so")
    other = ScientificResult(
        result_id="some-other-result", values={"temperature": Quantity(999.0, "kelvin")},
        models=(("synthetic.thermal", "1"),),
        validity_not_assessed={"synthetic.thermal": "a fixture: nothing asked"},
        provenance=ProvenanceRecord(run_id="other-run", models=(("synthetic.thermal", "1"),)),
    )
    issues = _transfer().check_against_result(other)
    assert issues, "a transfer naming 'thermal-result' is not about a result called 'some-other-result'"


@pytest.mark.xfail(strict=True, reason="R-61 finding 75 in production: ambient_transfers names the thermal result_id while taking the value from the system configuration, and nothing in the record says so")
def test_r61_a_configured_input_crossing_declares_that_it_is_one():
    origins = _symbol("engcore.scientific.composition.transfer", "TRANSFER_VALUE_ORIGINS")
    if origins is None:
        pytest.fail("no declared value origin: a transfer that read its value out of the record it names "
                    "and one that carries a configured input look identical")
    assert "configured_input" in origins


# ---------------------------------------------------------------------------
# energy_derived_dimensions_are_energy_crossings
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("unit_exemplar", ["watt / meter ** 2", "watt / meter", "watt / meter ** 3",
                                           "joule / kilogram"],
                         ids=["heat_flux", "line_power", "volumetric_source", "specific_energy"])
@pytest.mark.xfail(strict=True, reason="R-64 finding 78 as audited: the fail-closed guard matches only exactly [energy] or [power], so every flux density crosses as lossless transport while plain watt is refused")
def test_r64_an_energy_derived_crossing_with_no_declaration_is_refused(unit_exemplar):
    with pytest.raises(InvalidScientificProblem, match="energy"):
        _dependency(unit_exemplar=unit_exemplar)


def test_r64_plain_power_is_still_refused_without_a_conversion():
    """The control: the rule the audit found working stays working."""
    with pytest.raises(InvalidScientificProblem, match="energy crossing"):
        _dependency(unit_exemplar="watt")


@pytest.mark.xfail(strict=True, reason="R-64: with no way to declare either a conversion or a transport for an energy-derived dimension, the guard above could only be a wall")
def test_r64_an_energy_derived_crossing_can_declare_a_transport():
    import dataclasses

    names = {field.name for field in dataclasses.fields(QuantityDependency)}
    assert "transport_declaration" in names, (
        "there is no way to declare that an energy-derived crossing is a transport, so the refusal above "
        "would be a wall rather than a rule")
    dependency = _dependency(unit_exemplar="watt / meter ** 2",
                             transport_declaration="a boundary flux transported whole; no form changes")
    assert dependency.unit_exemplar == "watt / meter ** 2"


@pytest.mark.xfail(strict=True, reason="R-64: EnergyConversion refuses any exemplar that is not exactly an energy or a power, so a flux density cannot declare a conversion either")
def test_r64_an_energy_derived_crossing_can_declare_a_conversion():
    try:
        flux_half = EnergyConversion(
            name="half_the_flux_arrives", input_form="incident", output_form="absorbed",
            unit_exemplar="watt / meter ** 2", efficiency=0.5,
            losses=(LossPath(form="reflected", fraction=0.5),),
        )
    except InvalidScientificProblem as refusal:
        flux_half = None
        assert flux_half is not None, f"a flux density cannot declare a conversion either: {refusal}"
    dependency = _dependency(unit_exemplar="watt / meter ** 2", conversion=flux_half)
    assert dependency.conversion is flux_half
