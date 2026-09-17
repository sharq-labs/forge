"""Core re-audit 2026-09-16, batch 29: a spread converts by the slope, and says which scale it is on.

Problem R-48 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-22 part D of
five, under benchmarks/core_v4_false_confidence/BATCH29_THRESHOLD_PROTOCOL.json. This part is the units
primitive and the oracle tolerance (the audit's finding 58); finding 99's consumers are part E.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ScientificValidationError, UnitCompatibilityError
from engcore.scientific.oracles import (
    OracleEvidenceSet,
    OracleKind,
    OracleObservation,
)
from engcore.scientific.results.validation import ValidationOutcome
from engcore.scientific.units import quantity as q
from engcore.scientific.units.quantity import Quantity


def _symbol(name: str):
    """Assert the named symbol exists, so a missing one fails ON AN ASSERTION."""
    assert hasattr(q, name), (
        f"engcore.scientific.units.quantity has no {name!r}; it is preregistered in "
        f"BATCH29_THRESHOLD_PROTOCOL.json"
    )
    return getattr(q, name)


def _spread(magnitude, unit, target):
    reader = getattr(Quantity(magnitude, unit), "magnitude_as_spread_in", None)
    assert reader is not None, (
        "Quantity has no magnitude_as_spread_in; the rule 'a_spread_is_converted_by_the_slope_only' "
        "in BATCH29_THRESHOLD_PROTOCOL.json needs it"
    )
    return reader(target)


def _oracle(expected, tolerance, *, metric="T"):
    return OracleEvidenceSet.create(
        oracle_id="lab.batch29",
        version="1",
        kind=OracleKind.EXPERIMENTAL_DATASET,
        reference="doi:10.example/batch29",
        observations=(
            OracleObservation(metric=metric, expected=expected, absolute_tolerance=tolerance),
        ),
    )


# ---------------------------------------------------------------------------
# a_spread_is_converted_by_the_slope_only
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: there is no spread conversion yet")
def test_r48_a_celsius_difference_is_a_kelvin_of_the_same_size():
    assert _spread(0.5, "delta_degC", "kelvin") == pytest.approx(0.5)
    assert _spread(0.5, "kelvin", "delta_degC") == pytest.approx(0.5)
    assert _spread(1.0, "delta_degF", "kelvin") == pytest.approx(5.0 / 9.0)
    assert _spread(1.0, "delta_degC", "delta_degF") == pytest.approx(1.8)


@pytest.mark.xfail(strict=True, reason="R-48: the backend refuses delta against absolute")
def test_r48_a_spread_can_be_read_against_an_offset_unit_without_the_backend_refusing():
    """`Quantity(1, 'delta_degC').magnitude_in('degC')` raises; the slope between them is 1."""
    assert _spread(2.0, "delta_degC", "degC") == pytest.approx(2.0)
    assert _spread(2.0, "degC", "kelvin") == pytest.approx(2.0)


@pytest.mark.xfail(strict=True, reason="R-48: the spread reader does not exist yet")
def test_r48_a_ratio_scale_spread_is_the_plain_conversion_it_always_was():
    """The control: nothing about a ratio scale changes, because there the offset is zero."""
    assert _spread(1000.0, "millimeter", "meter") == pytest.approx(1.0)
    assert _spread(2.0, "kelvin", "kelvin") == pytest.approx(2.0)
    assert _spread(1.0, "kiloohm", "ohm") == pytest.approx(1000.0)
    assert Quantity(0.5, "degC").magnitude_in("kelvin") == pytest.approx(273.65), (
        "magnitude_in still converts an ABSOLUTE value; the spread reader is a second way to read, "
        "not a change to the first"
    )


# ---------------------------------------------------------------------------
# a_spread_must_be_on_a_ratio_scale
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: the generic core has no spread guard")
def test_r48_a_spread_unit_whose_zero_is_a_convention_is_refused_by_name():
    require_spread_unit = _symbol("require_spread_unit")
    for unit in ("degC", "degF"):
        with pytest.raises(UnitCompatibilityError, match="delta_"):
            require_spread_unit(unit, context="a test")
    for unit in ("delta_degC", "kelvin", "ohm", "watt/kelvin"):
        require_spread_unit(unit, context="a test")


# ---------------------------------------------------------------------------
# an_ambiguous_conversion_is_this_packages_error
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: pint's DimensionalityError escapes untyped")
def test_r48_a_conversion_the_backend_refuses_is_this_packages_error():
    """delta_degC and degC have the same dimension, so `require_compatible` passes and pint then raises."""
    with pytest.raises(UnitCompatibilityError, match="delta"):
        Quantity(2.0, "delta_degC").to("degC")
    with pytest.raises(UnitCompatibilityError):
        Quantity(2.0, "delta_degC").magnitude_in("degC")


def test_r48_the_conversions_that_worked_still_work():
    """The control for the wrapping: only the failure's TYPE changes."""
    assert Quantity(1.0, "kiloohm").to("ohm") == Quantity(1000.0, "ohm")
    assert Quantity(20.0, "degC").magnitude_in("kelvin") == pytest.approx(293.15)
    with pytest.raises(UnitCompatibilityError, match="incompatible units"):
        Quantity(1.0, "ohm").to("volt")


# ---------------------------------------------------------------------------
# an_oracle_tolerance_is_a_difference
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: a degC tolerance is accepted and read as 273.65 K")
def test_r48_an_oracle_tolerance_on_an_offset_scale_is_refused_at_declaration():
    with pytest.raises(ScientificValidationError, match="delta_"):
        _oracle(Quantity(300.0, "kelvin"), Quantity(0.5, "degC"))


def test_r48_a_273_kelvin_error_does_not_pass_a_half_degree_band():
    """The audited case: 0.5 degC read as 273.65 kelvin passed a prediction 273 kelvin wrong."""
    oracle = _oracle(Quantity(300.0, "kelvin"), Quantity(0.5, "delta_degC"))
    check = oracle.compare({"T": Quantity(573.0, "kelvin")}, name="oracle")
    assert check.outcome is ValidationOutcome.FAIL
    oracle_degf = _oracle(Quantity(300.0, "kelvin"), Quantity(1.0, "delta_degC"))
    assert oracle_degf.compare(
        {"T": Quantity(300.0 + 16.67, "kelvin")}, name="oracle"
    ).outcome is ValidationOutcome.FAIL


@pytest.mark.xfail(strict=True, reason="R-48: the sign check runs on the converted magnitude")
def test_r48_a_valid_band_on_an_expected_value_in_celsius_is_not_called_negative():
    """0.5 kelvin converted as an absolute temperature is -272.65 degC, and died on a sign check."""
    oracle = _oracle(Quantity(26.85, "degC"), Quantity(0.5, "kelvin"))
    assert oracle.compare({"T": Quantity(300.2, "kelvin")}, name="oracle").outcome is (
        ValidationOutcome.FAIL
    )
    assert oracle.compare({"T": Quantity(300.1, "kelvin")}, name="oracle").outcome is (
        ValidationOutcome.PASS
    )


@pytest.mark.xfail(strict=True, reason="R-48: the right spelling raises pint's DimensionalityError")
def test_r48_the_physically_correct_declaration_does_not_crash_untyped():
    """A delta_degC band on a degC expected value: the right spelling of the right thing."""
    oracle = _oracle(Quantity(26.85, "degC"), Quantity(0.5, "delta_degC"))
    assert oracle.compare({"T": Quantity(300.1, "kelvin")}, name="oracle").outcome is (
        ValidationOutcome.PASS
    )
    assert oracle.compare({"T": Quantity(301.0, "kelvin")}, name="oracle").outcome is (
        ValidationOutcome.FAIL
    )


def test_r48_a_negative_band_is_still_refused_and_a_ratio_scale_oracle_still_works():
    """Controls: the sign check still exists, and the ordinary oracle is untouched."""
    with pytest.raises(ScientificValidationError, match="non-negative"):
        _oracle(Quantity(300.0, "kelvin"), Quantity(-1.0, "kelvin"))
    oracle = _oracle(Quantity(3.70, "volt"), Quantity(0.05, "volt"), metric="voltage")
    assert oracle.compare({"voltage": Quantity(3.72, "volt")}, name="oracle").outcome is (
        ValidationOutcome.PASS
    )
    assert oracle.compare({"voltage": Quantity(3.90, "volt")}, name="oracle").outcome is (
        ValidationOutcome.FAIL
    )
