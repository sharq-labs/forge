"""Offset-unit arithmetic delegates to the units backend (F06).

``Q(30, 'degC') - Q(20, 'degC')`` returned ``10 degC``, which converts to
**283.15 K** instead of a 10 K difference. The wrapper did converted-magnitude
arithmetic — subtract the numbers, keep the left operand's unit — which is
correct for every ratio-scale unit and wrong for every interval one, because on
an interval scale the difference of two absolute values is not an absolute
value. It lives on a different unit, and pint has one: ``delta_degC``.

The same error made ``Q(30, 'degC') + Q(20, 'degC')`` return ``50 degC``. That
is not a wrong number, it is a number that should not exist: adding two
absolute temperatures is meaningless, and inventing an answer for it is worse
than refusing.

This is exactly the kind of thing the module's own design position says it will
not do — "Pint owns the unit algebra; this module owns the *contract*" — so the
fix is to stop reimplementing it.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import UnitCompatibilityError
from engcore.scientific.units.quantity import Quantity as Q

K = "kelvin"


# =====================================================================
# The finding
# =====================================================================

def test_a_celsius_difference_is_a_temperature_difference():
    """10 degrees of difference, and it converts to 10 kelvin."""
    difference = Q(30.0, "degC") - Q(20.0, "degC")
    assert difference.magnitude == pytest.approx(10.0)
    assert difference.to(K).magnitude == pytest.approx(10.0)


def test_the_same_computation_in_kelvin_agrees():
    """The unit a caller happened to write must not change the answer."""
    in_celsius = (Q(30.0, "degC") - Q(20.0, "degC")).to(K)
    in_kelvin = Q(303.15, K) - Q(293.15, K)
    assert in_celsius.magnitude == pytest.approx(in_kelvin.magnitude, abs=1e-9)


def test_adding_two_absolute_temperatures_raises():
    """It has no meaning, so there is no value to return.

    Before, this produced ``50 degC``. A wrong number is recoverable; a
    meaningless one presented as a result is what this platform exists to
    refuse.
    """
    with pytest.raises(UnitCompatibilityError, match="offset|ambiguous"):
        Q(30.0, "degC") + Q(20.0, "degC")


def test_an_explicitly_declared_delta_still_works():
    """A difference declared as one behaves as one, in both directions."""
    warmer = Q(30.0, "degC") + Q(5.0, "delta_degC")
    assert warmer.magnitude == pytest.approx(35.0)
    assert warmer.units == Q(1.0, "degC").units

    cooler = Q(30.0, "degC") - Q(5.0, "delta_degC")
    assert cooler.magnitude == pytest.approx(25.0)

    assert (Q(5.0, "delta_degC") + Q(3.0, "delta_degC")).magnitude == (
        pytest.approx(8.0)
    )
    assert Q(5.0, "delta_degC").to(K).magnitude == pytest.approx(5.0)


def test_fahrenheit_behaves_the_same_way():
    """Not a Celsius special case: it is every interval scale."""
    difference = Q(80.0, "degF") - Q(50.0, "degF")
    assert difference.to(K).magnitude == pytest.approx(30.0 * 5.0 / 9.0)
    with pytest.raises(UnitCompatibilityError):
        Q(80.0, "degF") + Q(50.0, "degF")


def test_a_mixed_absolute_difference_is_still_a_difference():
    """degC minus kelvin is a difference and lands on a delta unit."""
    difference = Q(30.0, "degC") - Q(290.0, K)
    assert difference.to(K).magnitude == pytest.approx(303.15 - 290.0)


# =====================================================================
# Ratio-scale behaviour is unchanged
# =====================================================================

@pytest.mark.parametrize(
    "left,right,expected_units",
    [
        ((1.0, "meter"), (100.0, "centimeter"), "meter"),
        ((100.0, "centimeter"), (1.0, "meter"), "centimeter"),
        ((300.0, K), (290.0, K), K),
        ((2.0, "watt"), (0.5, "watt"), "watt"),
    ],
)
def test_ratio_scale_arithmetic_keeps_the_left_operands_unit(
    left, right, expected_units
):
    """The behaviour every existing caller depends on, unchanged.

    Delegating to the backend must not quietly renormalise units: pint's own
    rule for ratio-scale operands is the left operand's unit, which is what
    this wrapper already did.
    """
    total = Q(*left) + Q(*right)
    assert total.units == Q(1.0, expected_units).units
    difference = Q(*left) - Q(*right)
    assert difference.units == Q(1.0, expected_units).units


def test_ratio_scale_values_still_add_and_subtract_correctly():
    assert (Q(1.0, "meter") + Q(100.0, "centimeter")).magnitude == (
        pytest.approx(2.0)
    )
    assert (Q(300.0, K) - Q(290.0, K)).magnitude == pytest.approx(10.0)
    assert (Q(1.5, "kilowatt") + Q(500.0, "watt")).magnitude == (
        pytest.approx(2.0)
    )


def test_incompatible_dimensions_are_still_refused_by_this_module():
    """The contract's own error type, not the backend's."""
    with pytest.raises(UnitCompatibilityError, match="addition"):
        Q(1.0, "meter") + Q(1.0, "second")
    with pytest.raises(UnitCompatibilityError, match="subtraction"):
        Q(1.0, "meter") - Q(1.0, "second")


def test_a_result_is_still_a_finite_normalised_quantity():
    """Whatever the backend returns, this module's own invariants hold."""
    difference = Q(30.0, "degC") - Q(20.0, "degC")
    assert isinstance(difference, Q)
    assert difference.units == difference.units.strip()
    assert difference.to_dict()["units"] == difference.units
    # and it round-trips
    assert Q.from_dict(difference.to_dict()) == difference


def test_comparison_still_answers_which_is_larger():
    """``compare`` is untouched and still orders two absolute temperatures."""
    assert Q(30.0, "degC").compare(Q(20.0, "degC")) > 0
    assert Q(20.0, "degC").compare(Q(30.0, "degC")) < 0
    assert Q(303.15, K).compare(Q(30.0, "degC")) == pytest.approx(0.0, abs=1e-9)


# =====================================================================
# The sweep: what the domains do by hand, and why it stays
# =====================================================================

#: Every place in the domains that does arithmetic on a temperature magnitude
#: by hand, found by sweeping ``src/engcore`` for a ``+`` or ``-`` joining a
#: ``magnitude_in(TEMPERATURE_UNIT)`` call. The list is asserted below to be
#: exactly what is there, so a new site cannot appear unreviewed.
#:
#: **Most of these form a temperature difference** -- the operation this file
#: exists for, ambiguous on an offset scale and therefore done in kelvin by
#: hand rather than delegated. One does not, and is marked: the sweep is
#: deliberately wider than the hazard, because a regex that matched only
#: differences would be a regex that could be stepped around.
HAND_ROLLED_SITES = {
    "domains/thermal_models/context.py": {
        "steady_state_temperature",
        "surface_temperature_excursion",
        "capacity_excursion_ratio",
    },
    "domains/battery/context.py": {
        "discharge_temperature_position",
        # the shared helper behind internal_resistance_drift_ratio and
        # peukert_temperature_drift_ratio
        "_temperature_drift_ratio",
    },
    "domains/electrical/material.py": {
        # NOT a temperature difference. It forms 1 + alpha T, the offset of
        # `linear_resistance_ratio` read as a function of the reference
        # temperature, for the repair inversion in `domains/repair.py`. One
        # absolute temperature, multiplied by a coefficient per kelvin and
        # added to a dimensionless 1 -- there is no second temperature for the
        # scale origin to cancel against, so the offset hazard this file is
        # about does not arise. It is registered because the sweep found it,
        # and a site the sweep finds is a site somebody has to have looked at.
        "_ratio_offset_in_reference",
    },
}


@pytest.mark.parametrize(
    "left,right",
    [
        ((30.0, "degC"), (20.0, "degC")),
        ((303.15, K), (293.15, K)),
        ((30.0, "degC"), (293.15, K)),
        ((80.0, "degF"), (50.0, "degF")),
    ],
)
def test_converting_first_agrees_with_the_delegated_subtraction(left, right):
    """Why none of the hand-rolled sites was ever wrong, made checkable.

    Each of them converts **both** operands to kelvin and only then subtracts,
    which is arithmetically correct on any scale — it is subtracting in the
    original unit and keeping that unit that was wrong. This asserts the two
    agree, so the sweep's conclusion rests on a test rather than on reading.
    """
    by_hand = Q(*left).magnitude_in(K) - Q(*right).magnitude_in(K)
    delegated = (Q(*left) - Q(*right)).to(K).magnitude
    assert by_hand == pytest.approx(delegated, abs=1e-9)


def test_a_span_stays_on_a_ratio_scale_where_the_domains_put_it():
    """And why they are not replaced by the delegated form.

    A domain forming a span lands it on kelvin deliberately: the applicability
    modules refuse ``degC`` for a declared span on the stated ground that "its
    zero is conventional, so a difference expressed in it is not a value of
    that unit". The delegated subtraction lands a Celsius difference on
    ``delta_degree_Celsius`` — correct, and a different unit from the one those
    contracts require.

    The absolute case is the one that settles it. ``steady_state_temperature``
    is ``ambient + rise``; done by hand in kelvin that is right for any ambient,
    while delegating it would hand pint an absolute in ``degC`` plus a
    ``kelvin`` rise — which is the ambiguous offset operation pint refuses, and
    would turn a working call into an exception. So the hand-rolled sites are
    not made unnecessary by this fix, and none was removed.
    """
    celsius_difference = Q(30.0, "degC") - Q(20.0, "degC")
    assert "delta" in celsius_difference.units
    assert celsius_difference.to(K).magnitude == pytest.approx(10.0)

    # the absolute sum a domain performs by hand, and what delegation does
    assert (Q(293.15, K) + Q(10.0, K)).magnitude_in(K) == pytest.approx(303.15)
    with pytest.raises(UnitCompatibilityError):
        Q(20.0, "degC") + Q(10.0, K)


def test_the_sweep_is_complete():
    """The list above is what is actually in the tree, not a memory of it."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent / "src" / "engcore"
    pattern = re.compile(r"magnitude_in\(\s*TEMPERATURE_UNIT\s*\)")
    found: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        current = None
        for index, line in enumerate(lines):
            match = re.match(r"def (\w+)\(", line)
            if match:
                current = match.group(1)
            if not pattern.search(line):
                continue
            window = "\n".join(lines[max(0, index - 2): index + 3])
            if re.search(
                r"[-+]\s*\n?\s*\w+\.magnitude_in|magnitude_in\([^)]*\)\s*[-+]",
                window,
            ):
                key = path.relative_to(root).as_posix()
                found.setdefault(key, set()).add(current)
    assert found == HAND_ROLLED_SITES, found
