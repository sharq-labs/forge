"""Core re-audit 2026-09-16, batch 30: every declared spread says it is one, and is read as one.

Problem R-48 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-22 part E of
five, under benchmarks/core_v4_false_confidence/BATCH30_THRESHOLD_PROTOCOL.json. This part is the audit's
finding 99; finding 58 was part D.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import pytest


from engcore.inference.grid import GaussianObservation, InferenceProblemError, ObservationSet
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.units.quantity import Quantity

from engcore.uq.predictive import PredictiveObservableSpec, UQProblemError

LE = ConstraintOperator.LESS_EQUAL


def _constraint(bound, tolerance):
    return ConstraintDefinition(
        name="t", metric="T", operator=LE, bound=bound, tolerance=tolerance
    )


def _observation(value, sigma):
    return GaussianObservation(
        condition_id="c", observable_name="T", value=value, sigma=sigma, source_ref="lab"
    )


def _sigmas(observation):
    return ObservationSet(observations=(observation,), dataset_id="d").numeric_vectors()[1]


# ---------------------------------------------------------------------------
# every_declared_spread_states_a_spread_unit
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: '2 degC' is accepted and read as 275.15 kelvin")
def test_r48_a_constraint_tolerance_on_an_offset_scale_is_refused_at_declaration():
    """'2 degC' read as 275.15 kelvin let a 600 kelvin reading satisfy a 358.15 kelvin limit."""
    with pytest.raises(InvalidScientificProblem, match="delta_"):
        _constraint(Quantity(358.15, "kelvin"), Quantity(2.0, "degC"))


@pytest.mark.xfail(strict=True, reason="R-48: '0.5 degC' is accepted and read as 273.65 kelvin")
def test_r48_an_observation_sigma_on_an_offset_scale_is_refused_at_declaration():
    """'0.5 degC' read as 273.65 kelvin gave a 50 kelvin misfit a chi-squared of 0.033."""
    with pytest.raises(InferenceProblemError, match="delta_"):
        _observation(Quantity(300.0, "kelvin"), Quantity(0.5, "degC"))


@pytest.mark.xfail(strict=True, reason="R-48: the predictive spec has no spread guard either")
def test_r48_a_predictive_observation_sigma_on_an_offset_scale_is_refused_at_declaration():
    with pytest.raises(UQProblemError, match="delta_"):
        PredictiveObservableSpec(
            observation_key="T",
            unit="kelvin",
            observation_sigma=Quantity(0.5, "degC"),
        )


# ---------------------------------------------------------------------------
# a_positivity_check_is_on_the_magnitude_as_declared
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: the sign is checked on the converted magnitude")
def test_r48_a_valid_tolerance_on_a_celsius_bound_is_not_called_negative():
    """2 kelvin read absolutely into degC is -271.15, and the record refused it for a sign."""
    constraint = _constraint(Quantity(85.0, "degC"), Quantity(2.0, "kelvin"))
    assert constraint.check(Quantity(86.0, "degC")).satisfied is True
    assert constraint.check(Quantity(88.0, "degC")).satisfied is False


@pytest.mark.xfail(strict=True, reason="R-48: positivity is checked on the converted magnitude")
def test_r48_a_valid_sigma_on_a_celsius_value_is_not_called_non_positive():
    observation = _observation(Quantity(26.85, "degC"), Quantity(0.5, "kelvin"))
    assert _sigmas(observation)[0] == pytest.approx(0.5)


def test_r48_a_genuinely_negative_spread_is_still_refused():
    """Controls: the sign checks still exist."""
    with pytest.raises(InvalidScientificProblem, match="non-negative"):
        _constraint(Quantity(358.15, "kelvin"), Quantity(-1.0, "kelvin"))
    with pytest.raises(InferenceProblemError, match="positive"):
        _observation(Quantity(300.0, "kelvin"), Quantity(0.0, "kelvin"))
    with pytest.raises(UQProblemError, match="positive"):
        PredictiveObservableSpec(
            observation_key="T", unit="kelvin", observation_sigma=Quantity(-1.0, "kelvin")
        )


# ---------------------------------------------------------------------------
# every_conversion_of_a_declared_spread_is_a_spread_conversion
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: the delta spelling is refused at every site")
def test_r48_the_physically_correct_declarations_work():
    """A delta_degC tolerance on a degC bound, and a delta_degC sigma on a degC value."""
    constraint = _constraint(Quantity(85.0, "degC"), Quantity(2.0, "delta_degC"))
    assert constraint.check(Quantity(86.0, "degC")).satisfied is True
    assert constraint.check(Quantity(88.0, "degC")).satisfied is False
    assert _sigmas(_observation(Quantity(26.85, "degC"), Quantity(0.5, "delta_degC")))[0] == (
        pytest.approx(0.5)
    )
    spec = PredictiveObservableSpec(
        observation_key="T", unit="degC", observation_sigma=Quantity(0.5, "delta_degC")
    )
    assert spec.observation_sigma.magnitude == pytest.approx(0.5)


def test_r48_a_fahrenheit_difference_is_five_ninths_of_a_kelvin_everywhere():
    """The one spread unit whose slope is not 1, so the slope is actually exercised."""
    assert _sigmas(_observation(Quantity(300.0, "kelvin"), Quantity(1.8, "delta_degF")))[0] == (
        pytest.approx(1.0)
    )
    constraint = _constraint(Quantity(358.15, "kelvin"), Quantity(1.8, "delta_degF"))
    assert constraint.check(Quantity(359.0, "kelvin")).satisfied is True
    assert constraint.check(Quantity(360.0, "kelvin")).satisfied is False


@pytest.mark.xfail(strict=True, reason="R-48: the digest reads the sigma's own unit absolutely")
def test_r48_the_split_content_digest_reads_a_sigma_as_a_difference():
    """Two readings that are the same measurement, spelled on two scales, are one content."""
    from engcore.inference import split

    kelvin = _observation(Quantity(300.0, "kelvin"), Quantity(0.5, "kelvin"))
    celsius = GaussianObservation(
        condition_id="other",
        observable_name="T",
        value=Quantity(26.85, "degC"),
        sigma=Quantity(0.5, "delta_degC"),
        source_ref="lab",
    )
    assert split._content_digest(kelvin) == split._content_digest(celsius), (
        "the same measurement written on two scales must digest the same, which is what the "
        "duplicate-across-the-split guard is for"
    )


# ---------------------------------------------------------------------------
# a_reported_margin_is_on_a_scale_that_can_carry_a_difference
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-48: the margin is labelled with the bound's offset unit")
def test_r48_a_reported_margin_is_a_difference_and_not_an_absolute_value():
    """A 12-degree margin labelled `12.0 degree_Celsius` reads as 285.15 kelvin to a consumer."""
    check = _constraint(Quantity(85.0, "degC"), Quantity(2.0, "delta_degC")).check(
        Quantity(75.0, "degC")
    )
    assert check.margin.magnitude == pytest.approx(12.0)
    assert check.margin.magnitude_in("kelvin") == pytest.approx(12.0), (
        f"a consumer converting the margin read {check.margin.magnitude_in('kelvin')} kelvin for a "
        f"12-degree margin"
    )


def test_r48_a_margin_on_a_ratio_scale_bound_keeps_its_unit_exactly():
    """The control, and the compatibility decision: every constraint in this tree is on a ratio scale."""
    check = _constraint(Quantity(358.15, "kelvin"), Quantity(2.0, "kelvin")).check(
        Quantity(350.0, "kelvin")
    )
    assert check.margin.units == "kelvin"
    assert check.margin.magnitude == pytest.approx(10.15)
    assert check.value == Quantity(350.0, "kelvin")
    ohms = _constraint(Quantity(10.0, "ohm"), Quantity(0.1, "ohm")).check(Quantity(9.0, "ohm"))
    assert ohms.margin.units == "ohm"
    assert ohms.margin.magnitude == pytest.approx(1.1)
    assert ohms.satisfied is True
