"""The unit memo must be invisible: same answers, same refusals, same records.

WHY THIS MODULE EXISTS
----------------------
A cache is the most dangerous kind of optimization in this repository, and the
performance round's own rule is that one may only be added where the cache
identity can be *proven* complete. This is that proof, written as tests rather
than as a paragraph.

WHAT IS CACHED, AND WHY THE KEY IS COMPLETE
--------------------------------------------
``_canonical_unit(text)`` maps a unit string to its canonical spelling and its
dimensionality. It is a pure function of the string and the registry, and the
registry is a constant for the life of the process: built once behind an
``is None`` guard *and a lock*, with no path anywhere that replaces it, sealed
before it is published, with every mutating route refused and that enumeration
exercised by ``test_core_guards``.

The lock is load-bearing rather than defensive. Without it the ``is None``
guard was a test and an assignment with a registry build between them, so
concurrent first use built one registry per racing thread and replaced the
published one each time -- which is precisely the "nothing replaces it"
premise this memo's safety argument stands on.
``tests/test_unit_registry_initialization`` pins that.

So the key -- the string -- is the entire varying input. **Nothing about a
model, a threshold, a context, a solver or a verdict participates in the value**,
which is why the completeness question a scientific-identity cache must answer
does not arise: this caches a lexical fact about a unit string, not a scientific
conclusion.

These tests hold that claim to account from the outside: every assertion below
compares a cached answer against a freshly computed one, or checks that a
refusal still refuses.
"""

from __future__ import annotations

import pytest

from src.engcore.scientific.errors import (
    UnitCompatibilityError,
    UnitRegistryMutationError,
)
from src.engcore.scientific.units.quantity import (
    Quantity,
    clear_unit_caches,
    dimension_of,
    dimensionality,
    normalize_unit,
    registry,
    registry_fingerprint,
    unit_cache_stats,
    verify_registry_unmutated,
)

#: Spellings that must canonicalise, including aliases, prefixes, composites and
#: two different spellings of one dimension.
UNITS = [
    "kelvin", "K", "millikelvin", "degR",
    "watt", "volt", "ampere", "ohm", "second", "hour", "meter",
    "joule/kelvin", "watt/kelvin", "watt/meter/kelvin",
    "meter**2", "meter**3", "1/kelvin", "dimensionless",
    "ampere*ohm", "watt/meter**2/kelvin", "kg*m/s**2",
]


@pytest.mark.parametrize("unit", UNITS)
def test_a_cached_answer_equals_a_freshly_computed_one(unit):
    """The whole safety claim, per unit, in both directions.

    Computed cold (cache cleared), then warm, then cold again. All three must
    agree -- and the last one matters: it proves the cleared state is reachable
    and produces the same answer, so the memo is not the only thing that has
    ever been right.
    """
    clear_unit_caches()
    cold_normal, cold_dim, cold_text = (
        normalize_unit(unit), dimension_of(unit), dimensionality(unit)
    )

    warm_normal, warm_dim, warm_text = (
        normalize_unit(unit), dimension_of(unit), dimensionality(unit)
    )
    assert warm_normal == cold_normal
    assert warm_dim == cold_dim
    assert warm_text == cold_text

    clear_unit_caches()
    assert normalize_unit(unit) == cold_normal
    assert dimension_of(unit) == cold_dim
    assert dimensionality(unit) == cold_text


def test_the_memo_does_not_merge_units_that_differ():
    """A cache that collided would make two dimensions equal. It does not."""
    clear_unit_caches()
    assert dimension_of("kelvin") != dimension_of("volt")
    assert dimension_of("meter") != dimension_of("meter**2")
    assert normalize_unit("kelvin") != normalize_unit("millikelvin")
    # ...and the compatibility that SHOULD hold still does. `ampere * ohm` and
    # `volt` are the same dimension and must stay so, which is the case the
    # dimensionality comparison was originally written for.
    assert dimension_of("ampere*ohm") == dimension_of("volt")
    assert Quantity(1.0, "ampere*ohm").is_compatible_with("volt")


def test_two_spellings_of_one_unit_share_an_answer_without_sharing_a_key():
    """`K` and `kelvin` canonicalise together; that is correctness, not caching."""
    clear_unit_caches()
    assert normalize_unit("K") == normalize_unit("kelvin") == "kelvin"
    assert dimensionality("K") == dimensionality("kelvin")
    assert Quantity(1.0, "K").units == Quantity(1.0, "kelvin").units


@pytest.mark.parametrize("bad", ["", "   ", "\t", None])
def test_an_empty_unit_is_refused_identically_whether_warm_or_cold(bad):
    """An exception is not a cacheable value, and must not become one."""
    for _ in range(3):
        with pytest.raises(UnitCompatibilityError, match="non-empty string"):
            normalize_unit("" if bad is None else bad)
        with pytest.raises(UnitCompatibilityError, match="non-empty string"):
            dimension_of("" if bad is None else bad)


@pytest.mark.parametrize("bad", ["not_a_unit", "!!!", "kelvin/", "3 ** ** 2"])
def test_an_unparsable_unit_is_refused_every_time(bad):
    """`lru_cache` does not memoize exceptions, and this proves it here.

    A cache that stored a failure would be bad; one that stored a SUCCESS for a
    string that should fail would be worse. Repeated because the first call is
    the only one that would have populated a table.
    """
    for _ in range(3):
        with pytest.raises(UnitCompatibilityError, match="unparsable unit"):
            normalize_unit(bad)
        with pytest.raises(UnitCompatibilityError, match="unparsable unit"):
            dimension_of(bad)


def test_dimension_of_reports_an_empty_unit_the_way_normalize_unit_does():
    """The refusal a caller sees must not have changed shape.

    `dimension_of` normalises first precisely so that an empty or unparsable
    unit raises `normalize_unit`'s message rather than a message about
    dimensionality -- which is what a reader gets told, and is the difference
    between "you passed nothing" and "this unit has no dimension".
    """
    with pytest.raises(UnitCompatibilityError) as empty:
        dimension_of("")
    assert "non-empty string" in str(empty.value)

    with pytest.raises(UnitCompatibilityError) as unparsable:
        dimension_of("not_a_unit")
    assert "unparsable unit" in str(unparsable.value)


def test_the_memo_is_bounded():
    """Unbounded growth on attacker-controlled input is not acceptable.

    A miss costs what every call used to cost, so a bound trades a pathological
    memory profile for a pathological latency profile -- which is the right way
    round.
    """
    stats = unit_cache_stats()
    assert stats["maxsize"] is not None and stats["maxsize"] > 0


def test_the_registry_is_still_sealed_and_still_detectably_unmutated():
    """The memo rests on the seal, so the seal is asserted beside it.

    If this ever fails, the memo's safety argument fails with it -- and that is
    the point of putting them in one test.
    """
    verify_registry_unmutated()
    assert isinstance(registry_fingerprint(), str)
    with pytest.raises(UnitRegistryMutationError):
        registry().define("smoot = 1.702 * meter")
    verify_registry_unmutated()


def test_quantities_built_warm_equal_quantities_built_cold():
    """The record a run actually writes must not depend on cache state.

    This is the end the memo could realistically have broken: `Quantity`
    normalises its unit on construction, so a wrong cached spelling would
    produce records that differ between a warm and a cold process while every
    unit test passed.
    """
    clear_unit_caches()
    cold = [Quantity(float(i), unit) for i, unit in enumerate(UNITS)]
    warm = [Quantity(float(i), unit) for i, unit in enumerate(UNITS)]
    clear_unit_caches()
    cold_again = [Quantity(float(i), unit) for i, unit in enumerate(UNITS)]

    assert cold == warm == cold_again
    assert [q.to_dict() for q in cold] == [q.to_dict() for q in warm]
    assert [q.units for q in cold] == [q.units for q in cold_again]


def test_conversion_and_comparison_are_unaffected():
    """Arithmetic reads the memo through several paths; each must still be right."""
    clear_unit_caches()
    assert Quantity(1.0, "kelvin").to("millikelvin").magnitude == pytest.approx(1000.0)
    assert Quantity(1.0, "kelvin").magnitude_in("kelvin") == pytest.approx(1.0)
    assert (Quantity(1.0, "watt") + Quantity(2.0, "watt")).magnitude == pytest.approx(3.0)
    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "kelvin") + Quantity(1.0, "volt")
    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "kelvin").to("volt")


# ===================================================================== to()
#
# `Quantity.to` short-circuits when the target unit is the one already carried.
# Counted over one real coupled run: 549 of 552 calls (99.5 %) are that case,
# because callers reach for `magnitude_in(...)` to get a NUMBER out of a value
# rather than to move it between units.
#
# The risk is that a short-circuit and a real conversion stop agreeing, so every
# test below compares the fast path against the arithmetic it replaced.


def _reference_conversion(quantity: Quantity, unit: str) -> Quantity:
    """The pre-optimization body, kept here as the thing to agree with."""
    target = normalize_unit(unit)
    quantity.require_compatible(target, context="conversion")
    converted = registry().Quantity(quantity.magnitude, quantity.units).to(target)
    return Quantity(float(converted.magnitude), str(converted.units))


@pytest.mark.parametrize("unit", UNITS + ["degC", "degF"])
@pytest.mark.parametrize(
    "magnitude", [0.0, 1.0, -1.0, 273.15, 1e-30, 1e30, 3.14159265358979]
)
def test_an_identity_conversion_equals_the_round_trip_it_replaces(unit, magnitude):
    """The whole safety claim for the short-circuit, per unit and magnitude.

    Offset units are included deliberately: `degC` and `degF` are the ones where
    "convert to yourself" could plausibly not be the identity, because their
    conversion is affine rather than a scale factor.
    """
    quantity = Quantity(magnitude, unit)
    for spelling in {unit, normalize_unit(unit)}:
        fast = quantity.to(spelling)
        reference = _reference_conversion(quantity, spelling)
        assert fast == reference
        assert fast.magnitude == reference.magnitude
        assert fast.units == reference.units


def test_a_real_conversion_is_untouched():
    """The 0.5 % that is a genuine conversion must still be computed."""
    assert Quantity(1.0, "kelvin").to("millikelvin").magnitude == pytest.approx(1000.0)
    assert Quantity(1.0, "hour").to("second").magnitude == pytest.approx(3600.0)
    assert Quantity(0.0, "degC").to("kelvin").magnitude == pytest.approx(273.15)
    assert Quantity(1.0, "ampere*ohm").to("volt").magnitude == pytest.approx(1.0)
    # ...and each equals the reference arithmetic exactly.
    for unit, target in (("kelvin", "millikelvin"), ("hour", "second"),
                         ("degC", "kelvin"), ("meter", "millimeter")):
        quantity = Quantity(2.5, unit)
        assert quantity.to(target) == _reference_conversion(quantity, target)


def test_the_short_circuit_does_not_skip_a_refusal():
    """Skipping the compatibility check is only safe where it cannot fail.

    A unit is compatible with itself, so the check is redundant on that branch
    and only on that branch. An incompatible target and an unparsable one must
    still be refused, and `normalize_unit` still runs before the short-circuit
    so the second one is.
    """
    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "kelvin").to("volt")
    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "kelvin").to("not_a_unit")
    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "kelvin").to("")
    with pytest.raises(UnitCompatibilityError):
        Quantity(1.0, "kelvin").magnitude_in("volt")


def test_magnitude_in_agrees_with_conversion_on_both_paths():
    quantity = Quantity(300.0, "kelvin")
    assert quantity.magnitude_in("kelvin") == 300.0
    assert quantity.magnitude_in("K") == 300.0
    assert quantity.magnitude_in("millikelvin") == pytest.approx(300_000.0)
    assert quantity.magnitude_in("kelvin") == quantity.to("kelvin").magnitude


def test_an_identity_conversion_returns_an_equal_immutable_value():
    """Returning `self` is safe only because the record is frozen."""
    quantity = Quantity(300.0, "kelvin")
    same = quantity.to("kelvin")
    assert same == quantity
    with pytest.raises(Exception):
        same.magnitude = 1.0  # frozen, so the alias cannot be used to mutate
