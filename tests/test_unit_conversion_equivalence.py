"""The memoized conversion must return the backend's own bits, not near them.

Sprint 7. `Quantity.to` no longer builds a backend quantity per call: it looks
up a rule for the unit pair and either multiplies by a cached factor or hands
the magnitude to the backend's `convert` with both unit containers already
parsed.

The second path is the backend's arithmetic by construction. The first is a
claim, and this file is the measurement behind it: a multiplicative conversion
computed as `m * factor` returns the **same float** as the backend, bit for
bit, across every compatible pair of a broad unit set and a magnitude set
chosen to include the places floating point misbehaves.

Why bit equality and not a tolerance: a unit layer that returned a different
final bit than it did last week would move scientific values for no reason a
reader could see, and this repository's certificate already records exact float
boundary equality as a known limit. A tolerance here would hide exactly the
thing the test exists to detect.
"""

from __future__ import annotations

import random

import pytest

from engcore.scientific.units.quantity import (
    Quantity,
    _conversion_rule,
    normalize_unit,
    registry,
)

UNITS = (
    "ohm", "kohm", "megaohm", "volt", "millivolt", "ampere", "milliampere",
    "watt", "kilowatt", "joule", "kilojoule", "calorie", "meter", "millimeter",
    "centimeter", "inch", "foot", "second", "minute", "hour", "kelvin", "degC",
    "degF", "degR", "delta_degC", "delta_degF", "pascal", "bar", "psi",
    "kilogram", "gram", "mol", "millimole", "liter", "m**3", "cm**3",
    "watt/meter/kelvin", "joule/kelvin", "mol/m**3", "J/mol", "kg/m**3",
    "ampere_hour", "coulomb", "farad", "henry", "newton", "hertz",
    "dimensionless",
)

#: Chosen for the places floating point misbehaves, not for realism.
MAGNITUDES = (
    0.0, 1.0, -1.0, 0.5, 1 / 3, 2**-40, 2**-1000, 1e-300, 1e300, 1e-15, 1e15,
    3.14159265358979, 273.15, -40.0, 6.02e23, -1e-7,
)


def _random_magnitudes(count: int = 24) -> tuple[float, ...]:
    generator = random.Random(20260912)
    return tuple(generator.uniform(-1e9, 1e9) for _ in range(count))


def _compatible_pairs():
    backend = registry()
    for source in UNITS:
        for target in UNITS:
            try:
                canonical_source = normalize_unit(source)
                canonical_target = normalize_unit(target)
                backend.convert(
                    0.0,
                    backend.Unit(canonical_source)._units,  # noqa: SLF001
                    backend.Unit(canonical_target)._units,  # noqa: SLF001
                )
            except Exception:
                continue
            yield canonical_source, canonical_target


PAIRS = tuple(_compatible_pairs())


def test_the_pair_set_is_large_enough_to_mean_something():
    """A guard on the guard: an empty sweep would pass every assertion below."""
    assert len(PAIRS) >= 100, f"only {len(PAIRS)} compatible pairs were built"
    multiplicative = [p for p in PAIRS if _conversion_rule(*p)[0] is not None]
    affine = [p for p in PAIRS if _conversion_rule(*p)[0] is None]
    assert multiplicative, "no multiplicative pair was exercised"
    assert affine, "no affine pair was exercised — the fallback is untested"


def test_every_conversion_returns_the_backends_own_bits():
    """The load-bearing assertion, over every pair and every magnitude."""
    backend = registry()
    magnitudes = MAGNITUDES + _random_magnitudes()
    checked = 0
    differences: list[str] = []

    for source, target in PAIRS:
        for magnitude in magnitudes:
            try:
                expected = float(
                    backend.Quantity(magnitude, source).to(target).magnitude
                )
            except Exception:
                continue
            actual = Quantity(magnitude, source).magnitude_in(target)
            checked += 1
            if expected.hex() != actual.hex():
                differences.append(
                    f"{magnitude!r} {source} -> {target}: "
                    f"backend {expected!r}, memoized {actual!r}"
                )

    assert checked > 4000, f"only {checked} conversions were compared"
    assert not differences, (
        f"{len(differences)} of {checked} conversions differ from the backend:\n"
        + "\n".join(differences[:10])
    )


def test_a_multiplicative_rule_is_exactly_the_backends_factor():
    for source, target in PAIRS:
        factor, _, _ = _conversion_rule(source, target)
        if factor is None:
            continue
        backend_factor = float(
            registry().Quantity(1.0, source).to(target).magnitude
        )
        assert factor.hex() == backend_factor.hex(), f"{source} -> {target}"


def test_an_affine_pair_is_not_given_a_factor():
    """The split is the safety property, so it is asserted directly.

    `degF -> degC` computed as `m * (one - zero) + zero` matches the backend on
    4 magnitudes in 52. It must therefore never take the multiply path.
    """
    for source, target in (("degF", "degC"), ("degC", "kelvin"),
                           ("kelvin", "degC"), ("degF", "kelvin")):
        factor, _, _ = _conversion_rule(normalize_unit(source), normalize_unit(target))
        assert factor is None, f"{source} -> {target} was given a factor"


@pytest.mark.parametrize(
    "magnitude, source, target, expected",
    [
        (1.0, "kohm", "ohm", 1000.0),
        (12.0, "volt", "millivolt", 12000.0),
        (0.0, "degC", "kelvin", 273.15),
        (100.0, "degC", "kelvin", 373.15),
        (-40.0, "degF", "degC", -40.0),
        (1.0, "hour", "second", 3600.0),
    ],
)
def test_the_conversions_a_reader_can_check_by_hand(magnitude, source, target, expected):
    assert Quantity(magnitude, source).magnitude_in(target) == pytest.approx(expected)


def test_an_identity_conversion_still_returns_the_same_object():
    """The pre-existing short circuit is untouched by the memo."""
    quantity = Quantity(3.0, "kohm")
    assert quantity.to("kohm") is quantity
    assert quantity.to("kiloohm") is quantity


def test_an_incompatible_conversion_still_raises_before_the_memo():
    from engcore.scientific.errors import UnitCompatibilityError

    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "volt").magnitude_in("kelvin")


def test_an_unparsable_target_still_raises():
    from engcore.scientific.errors import UnitCompatibilityError

    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "volt").magnitude_in("not_a_unit_at_all")


def test_the_rule_memo_stays_bounded():
    """The same bound the other unit memos carry, for the same reason."""
    assert _conversion_rule.cache_info().maxsize == 4096
