"""Duplicate detection on a snapshot's decision basis: same verdict, one pass.

``BeliefSnapshot.__post_init__`` used to find duplicate dependency keys with
``keys.count(k)`` inside a comprehension over the same keys — a quadratic scan in
a constructor. It is now a single pass with a seen-set.

The substitution is only legitimate if the *verdict and the message* are
unchanged, so that is what these tests pin: which keys are named, that they are
reported sorted, that every duplicate is named rather than only the first, and
that a basis of distinct keys is still accepted. They deliberately do not assert
timing.
"""

from __future__ import annotations

import pytest

from src.engcore.sria.decision import (
    BeliefSnapshot,
    DependencyIdentity,
    DependencyKind,
)


def dependency(dependency_id: str, version: str = "1") -> DependencyIdentity:
    return DependencyIdentity(
        dependency_id=dependency_id,
        kind=DependencyKind.OUTCOME_MODEL,
        version=version,
    )


def snapshot(basis: tuple[DependencyIdentity, ...]) -> BeliefSnapshot:
    return BeliefSnapshot(
        snapshot_id="snap", campaign_id="camp", decision_basis=basis
    )


def test_a_basis_of_distinct_keys_is_accepted() -> None:
    basis = tuple(dependency(f"dep_{i}") for i in range(64))
    assert len(snapshot(basis).decision_basis) == 64


def test_a_repeated_key_is_refused_and_named() -> None:
    repeated = dependency("outcome.model")
    with pytest.raises(ValueError) as caught:
        snapshot((repeated, dependency("other.model"), repeated))
    message = str(caught.value)
    assert "duplicate dependency keys" in message
    assert repeated.key in message
    # The key that appeared once must not be blamed.
    assert "other.model" not in message


def test_every_duplicate_is_named_not_only_the_first() -> None:
    a, b, c = dependency("aaa"), dependency("bbb"), dependency("ccc")
    with pytest.raises(ValueError) as caught:
        snapshot((a, b, c, a, b))
    message = str(caught.value)
    assert a.key in message
    assert b.key in message
    assert c.key not in message


def test_duplicates_are_reported_in_sorted_order() -> None:
    """A set has no order; the message must not inherit iteration order."""
    z, y, x = dependency("zzz"), dependency("yyy"), dependency("xxx")
    with pytest.raises(ValueError) as caught:
        snapshot((z, y, x, z, y, x))
    message = str(caught.value)
    positions = [message.index(k) for k in sorted([x.key, y.key, z.key])]
    assert positions == sorted(positions), (
        f"duplicate keys are not reported in sorted order: {message}"
    )


def test_a_key_repeated_many_times_is_reported_once() -> None:
    repeated = dependency("many")
    with pytest.raises(ValueError) as caught:
        snapshot(tuple(repeated for _ in range(16)))
    message = str(caught.value)
    assert message.count(repeated.key) == 1


def test_two_dependencies_differing_only_in_version_collide() -> None:
    """`key` is kind:dependency_id — version is not part of it.

    So pinning the same dependency at two versions is a duplicate, not two
    entries. Worth pinning explicitly: it is the case where "duplicate" is a
    judgement about identity rather than about a repeated object.
    """
    first = dependency("model", version="1")
    second = dependency("model", version="2")
    assert first.key == second.key
    with pytest.raises(ValueError, match="duplicate dependency keys"):
        snapshot((first, second))
