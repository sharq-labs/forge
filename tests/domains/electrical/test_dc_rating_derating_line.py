"""A rated dissipation is a pair, and this is what changes when a caller says so.

The finding these tests close
------------------------------
``benchmarks/ai_designs/FINDINGS.md`` F1. Every resistor datasheet states its
rating as a pair — 0.25 W **at 70 °C**, falling along a derating curve to zero
at the permissible film temperature — and ``rated_power`` was a scalar carrying
no ambient. Six benchmark cases dissipating roughly twice their derated rating,
in a 120 °C ambient, came back SUPPORTED with nothing unknown. The tool was not
computing anything wrong; it had no field in which the question could be asked.

What is pinned here
-------------------
1. **Nothing moves for a payload that does not declare the pair.** This is the
   compatibility guarantee the frozen benchmark rests on, and it is asserted
   directly rather than inferred from that benchmark's score.
2. The two readings agree on the verdict everywhere the power form is defined,
   and the temperature form stays finite where the power form does not.
3. Half a line, a line with no rating, and an inverted line are refused at
   declaration.
4. A declared line with no ambient is UNKNOWN, not answered from the printed
   number.
5. The six cases from the finding are now refused, at the numbers the datasheets
   print.
"""

from __future__ import annotations

import math

import pytest

from engcore.domains.electrical.dc import models as dc
from engcore.domains.electrical.dc.models import (
    DISSIPATED_POWER_UTILIZATION,
    ComponentRating,
    resistor_rating_context,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

K = 273.15


def rating(rated_w, rated_c=None, zero_c=None, derating=dc.NO_DERATING):
    return ComponentRating(
        rated_power=Quantity(rated_w, "watt"),
        rated_power_temperature=(
            None if rated_c is None else Quantity(rated_c + K, "kelvin")
        ),
        zero_power_temperature=(
            None if zero_c is None else Quantity(zero_c + K, "kelvin")
        ),
        derating_factor=derating,
    )


def utilization(rating_, power_w, ambient_c=None):
    context = resistor_rating_context(
        rating=rating_,
        dissipated_power=Quantity(power_w, "watt"),
        voltage_across=Quantity(1.0, "volt"),
        ambient_temperature=(
            None if ambient_c is None else Quantity(ambient_c + K, "kelvin")
        ),
    )
    value = context.get(DISSIPATED_POWER_UTILIZATION)
    return None if value is None else value.magnitude_in("dimensionless")


# =====================================================================
# 1. The compatibility guarantee
# =====================================================================


@pytest.mark.parametrize("ambient_c", [-40, 25, 70, 120, 200, None])
@pytest.mark.parametrize("power_w", [0.001, 0.1, 0.25, 0.4])
def test_a_rating_without_the_pair_is_the_ratio_it_has_always_been(
    ambient_c, power_w
):
    """No pair declared, no change — at any ambient, including none at all.

    Every payload written before these fields existed declares a bare
    ``rated_power``, and this asserts that all of them still mean exactly what
    they meant. The frozen 2000-case benchmark rests on this, and it is checked
    here rather than left to be inferred from that benchmark's score.
    """
    assert utilization(rating(0.25), power_w, ambient_c) == pytest.approx(
        power_w / 0.25
    )


def test_the_ambient_is_ignored_entirely_when_no_line_is_declared():
    """The new argument is inert unless the declaration asks for it.

    A caller who supplies an ambient and no derating line has supplied a fact
    no condition reads. That is the correct behaviour: the ambient only becomes
    load-bearing once a rating says what it is stated against.
    """
    flat = rating(0.25)
    assert utilization(flat, 0.2, 25) == utilization(flat, 0.2, 500)


# =====================================================================
# 2. The two readings, where both are defined
# =====================================================================


def power_form(rated_w, rated_c, zero_c, ambient_c, power_w, derating=1.0):
    """P / (derating * P_eff) — the form the temperature ratio replaces."""
    effective = rated_w * (zero_c - ambient_c) / (zero_c - rated_c)
    if effective <= 0:
        return math.inf
    return power_w / (derating * effective)


@pytest.mark.parametrize("ambient_c", [-40, 0, 25, 70, 90, 120, 140, 154])
@pytest.mark.parametrize("power_w", [0.005, 0.05, 0.103, 0.204, 0.25, 0.5])
def test_the_temperature_form_and_the_power_form_agree_on_the_verdict(
    ambient_c, power_w
):
    """Same decision, everywhere the power form has one.

    The two ratios are different numbers away from the bound — one is a
    fraction of a temperature and the other a fraction of a power — and they
    cross 1 at the same place, which is the only property the condition uses.
    """
    got = utilization(rating(0.25, 70, 155), power_w, ambient_c)
    want = power_form(0.25, 70, 155, ambient_c, power_w)
    assert (got > 1.0) == (want > 1.0)
    assert (got == pytest.approx(1.0)) == (want == pytest.approx(1.0))


def test_the_two_forms_are_equal_exactly_at_the_bound():
    """At the rating temperature, dissipating the rating, both read 1."""
    assert utilization(rating(0.25, 70, 155), 0.25, 70) == pytest.approx(1.0)


@pytest.mark.parametrize("ambient_c", [155, 170, 400])
def test_the_utilization_stays_finite_where_the_power_form_is_not(ambient_c):
    """At and above the zero-power temperature the part may not be used at all.

    The power form is infinite or negative here and a condition forced to report
    a non-finite number has stopped measuring. The temperature form reports a
    real number above 1, which is a verdict rather than an error.
    """
    got = utilization(rating(0.25, 70, 155), 0.001, ambient_c)
    assert math.isfinite(got)
    assert got > 1.0


def test_the_implied_thermal_resistance_is_the_slope_of_the_printed_line():
    """A derating curve is a thermal resistance drawn as a line.

    Vishay CRCW0805: 0.25 W at 70 °C to zero at 155 °C is 340 K/W. Dissipating
    P raises the implied temperature by 340*P, and the utilization is that
    temperature over 155 °C absolute. Checked as arithmetic so the docstring's
    claim is a computation rather than an assertion.
    """
    implied_r_th = (155 - 70) / 0.25
    assert implied_r_th == pytest.approx(340.0)
    power = 0.1
    expected = (25 + K + implied_r_th * power) / (155 + K)
    assert utilization(rating(0.25, 70, 155), power, 25) == pytest.approx(expected)


def test_derating_factor_still_narrows_a_line():
    """The caller's own margin composes with the manufacturer's curve.

    ``derating_factor`` is the fraction of the published rating the caller
    elects to use. Against a line it divides the dissipation rather than
    multiplying the rating, which is the same statement rearranged, and a
    half-derated part uses more of its rating than a full one at the same load.
    """
    full = utilization(rating(0.25, 70, 155), 0.1, 25)
    half = utilization(rating(0.25, 70, 155, derating=0.5), 0.1, 25)
    assert half > full
    assert utilization(rating(0.25, 70, 155, derating=0.5), 0.05, 25) == (
        pytest.approx(full)
    )


# =====================================================================
# 3. What a malformed declaration does
# =====================================================================


@pytest.mark.parametrize(
    "kwargs, fragment",
    [
        (
            dict(rated_power=Quantity(0.25, "watt"),
                 rated_power_temperature=Quantity(343.15, "kelvin")),
            "must be declared together",
        ),
        (
            dict(rated_power=Quantity(0.25, "watt"),
                 zero_power_temperature=Quantity(428.15, "kelvin")),
            "must be declared together",
        ),
        (
            dict(rated_power_temperature=Quantity(343.15, "kelvin"),
                 zero_power_temperature=Quantity(428.15, "kelvin")),
            "without a rated_power",
        ),
        (
            dict(rated_power=Quantity(0.25, "watt"),
                 rated_power_temperature=Quantity(428.15, "kelvin"),
                 zero_power_temperature=Quantity(343.15, "kelvin")),
            "must be above",
        ),
        (
            dict(rated_power=Quantity(0.25, "watt"),
                 rated_power_temperature=343.15,
                 zero_power_temperature=Quantity(428.15, "kelvin")),
            "not a declaration",
        ),
    ],
)
def test_an_incomplete_or_inverted_line_is_refused(kwargs, fragment):
    """Half a line is not a weaker declaration, it is an incomplete one."""
    with pytest.raises(InvalidScientificProblem) as excinfo:
        ComponentRating(**kwargs)
    assert fragment in str(excinfo.value)


def test_a_declared_line_without_an_ambient_is_unknown_not_assumed():
    """The gap stays a gap.

    Answering from the printed number would answer a question the caller did
    not ask, and would do it silently — the same substitution the whole boundary
    exists to refuse.
    """
    assert utilization(rating(0.25, 70, 155), 0.2, ambient_c=None) is None
    # ...and the flat rating in the same circumstance is still answerable.
    assert utilization(rating(0.25), 0.2, ambient_c=None) == pytest.approx(0.8)


def test_a_rating_round_trips_through_its_dict_with_the_pair():
    original = rating(0.25, 70, 155)
    restored = ComponentRating.from_dict(original.to_dict())
    assert restored == original


# =====================================================================
# 4. The six cases from the finding
# =====================================================================

#: The six false accepts of `benchmarks/ai_designs/RESULTS.md` section 4, as
#: (part, printed rating W, rating ambient C, zero-power C, dissipation W).
#: Every rating and every knee is the number its datasheet prints; the
#: dissipations are what the benchmark's own runs converged to.
FINDING_CASES = [
    ("CRCW0805", 0.25, 70, 155, 0.2036),
    ("CRCW1206", 0.25, 70, 155, 0.2036),
    ("CRCW2010", 0.75, 70, 155, 0.6109),
    ("CRCW1210", 0.50, 70, 155, 0.4073),
    ("CRCW2512", 1.00, 70, 155, 0.8146),
    ("SFR25", 0.40, 70, 155, 0.3258),
]


@pytest.mark.parametrize(
    "part, rated_w, rated_c, zero_c, power_w", FINDING_CASES
)
def test_the_six_cases_the_benchmark_caught_are_refused_with_the_pair(
    part, rated_w, rated_c, zero_c, power_w
):
    """Under the printed rating, over the derated one, and now refused.

    Each dissipates under the wattage its datasheet prints — which is why the
    flat comparison accepted it — and roughly twice what that wattage derates
    to at the 120 °C ambient the case declares.
    """
    derated = rated_w * (zero_c - 120) / (zero_c - rated_c)
    assert power_w < rated_w, f"{part}: not under the printed rating"
    assert power_w > 1.5 * derated, f"{part}: not meaningfully over the derated one"

    assert utilization(rating(rated_w), power_w, 120) < 1.0     # the old reading
    assert utilization(rating(rated_w, rated_c, zero_c), power_w, 120) > 1.0


@pytest.mark.parametrize(
    "part, rated_w, rated_c, zero_c, power_w", FINDING_CASES
)
def test_the_same_parts_at_their_rating_ambient_are_still_accepted(
    part, rated_w, rated_c, zero_c, power_w
):
    """The change refuses hot parts, not these parts.

    At the ambient the rating is stated against, the same dissipation is inside
    the same rating. A fix that failed this would have replaced a false accept
    with a false reject.
    """
    assert utilization(rating(rated_w, rated_c, zero_c), power_w, rated_c) < 1.0
