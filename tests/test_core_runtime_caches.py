"""Part K: every Core cache, audited, and a clear that cannot go stale.

The Sprint 7 bug this exists to prevent from recurring
-------------------------------------------------------
``clear_unit_caches`` cleared two of the module's four memos. The two it missed
sat IN FRONT of the two it cleared, so a caller who cleared the caches still
got answers without a parse -- and a performance guard that counted parses
measured zero where it expected one. A clear that does not clear everything is
worse than none, because what it leaves behind is invisible.

The fix at the time was to add the two missing names. That fix is only as good
as the next person remembering, so the real guard is
:func:`test_clear_unit_caches_clears_every_memo_in_the_module`: it ENUMERATES
the module's ``lru_cache`` objects and fails if any survives a clear. A memo
added later is covered by it without anybody updating a list.
"""

from __future__ import annotations

import functools

import pytest

from engcore.scientific.units import quantity as q
from engcore.scientific.units.quantity import (
    Quantity,
    clear_unit_caches,
    unit_cache_stats,
)


def module_memos():
    """Every ``lru_cache``-wrapped callable defined in the quantity module.

    Found by attribute walk rather than by a hand-written list, which is the
    whole point: the list is what went stale last time.
    """
    found = {}
    for name in dir(q):
        value = getattr(q, name)
        if hasattr(value, "cache_clear") and hasattr(value, "cache_info"):
            found[name] = value
    return found


def test_the_module_exposes_the_memos_this_audit_expects():
    """If a memo is added or removed, this fails and the audit gets revisited."""
    assert set(module_memos()) == {
        "_canonical_unit",
        "_canonical_dimensionality",
        "_normalized",
        "_conversion_rule",
        "_compatible",
        "base_unit",
        "is_ratio_scale",
    }, sorted(module_memos())


def test_clear_unit_caches_clears_every_memo_in_the_module():
    """The structural guard. Not a list -- an enumeration.

    It earned its place on the first run: it found `base_unit` and
    `is_ratio_scale` surviving a clear, which had been true since both were
    written. Every memo here derives a fact from the registry and sits in front
    of it, so all of them must go when a caller deliberately resets.
    """
    populated = module_memos()

    # Populate every one of them through the public surface.
    a, b = Quantity(1.0, "ohm"), Quantity(1.0, "kiloohm")
    a.is_compatible_with(b)
    a.to("kiloohm")
    a.is_compatible_with("volt")
    q.base_unit("kiloohm")
    q.is_ratio_scale("degC")
    q.dimensionality("ohm")

    filled = [n for n, m in populated.items() if m.cache_info().currsize > 0]
    assert filled, "nothing was populated, so this test would pass vacuously"

    clear_unit_caches()

    survivors = {
        name: memo.cache_info().currsize
        for name, memo in populated.items()
        if memo.cache_info().currsize > 0
    }
    assert not survivors, (
        f"clear_unit_caches() left {survivors} populated. A memo in front of "
        f"another means a caller who cleared still gets an answer without a "
        f"parse -- the Sprint 7 defect exactly"
    )


def test_the_stats_surface_reports_every_clearable_memo():
    """A cache nobody can see the hit rate of is a cache nobody can audit."""
    clear_unit_caches()
    a = Quantity(1.0, "ohm")
    a.is_compatible_with("volt")
    a.is_compatible_with("volt")
    stats = unit_cache_stats()
    for key in (
        "hits", "misses", "currsize", "maxsize",
        "normalized_hits", "normalized_misses",
        "conversion_rule_hits", "conversion_rule_misses",
        "compatible_hits", "compatible_misses",
    ):
        assert key in stats, key
    assert stats["compatible_hits"] >= 1


# =====================================================================
# The compatibility memo answers exactly what it replaced
# =====================================================================

CASES = [
    ("ohm", "ohm", True),
    ("ohm", "kiloohm", True),
    ("ohm", "volt", False),
    ("volt", "ampere*ohm", True),        # Ohm's law: composite vs base
    ("kelvin", "degC", True),            # same dimension, different zero
    ("meter", "second", False),
    ("dimensionless", "dimensionless", True),
    ("watt", "volt*ampere", True),
]


@pytest.mark.parametrize("source,target,expected", CASES)
def test_the_memo_agrees_with_the_unmemoized_computation(source, target, expected):
    """Cached and uncached must be the same answer, on a miss and on a hit."""
    clear_unit_caches()
    direct = q.dimension_of(source) == q.dimension_of(target)
    assert direct is expected, (source, target)

    clear_unit_caches()
    first = q._compatible(source, target)     # miss
    second = q._compatible(source, target)    # hit
    assert first is second is expected


def test_the_fast_path_for_identical_units_agrees_with_the_slow_one():
    """`self.units == target` short-circuits; it must not change the answer."""
    for unit in ("ohm", "kelvin", "degC", "volt*ampere", "dimensionless"):
        value = Quantity(1.0, unit)
        assert value.is_compatible_with(value.units) is True
        assert q._compatible(value.units, value.units) is True


def test_an_unparsable_unit_still_raises_rather_than_caching_a_false():
    """A memo must not turn a refusal into a quiet `False`."""
    from engcore.scientific.errors import UnitCompatibilityError

    value = Quantity(1.0, "ohm")
    with pytest.raises(UnitCompatibilityError):
        value.is_compatible_with("not-a-unit")
    with pytest.raises(UnitCompatibilityError):
        value.require_compatible("not-a-unit")


def test_compatibility_is_symmetric():
    for source, target, expected in CASES:
        assert q._compatible(source, target) is q._compatible(target, source)


def test_clearing_does_not_change_any_answer():
    """The observable behaviour is identical with a cold and a warm cache."""
    cold = []
    for source, target, _ in CASES:
        clear_unit_caches()
        cold.append(q._compatible(source, target))
    warm = [q._compatible(source, target) for source, target, _ in CASES]
    assert cold == warm
