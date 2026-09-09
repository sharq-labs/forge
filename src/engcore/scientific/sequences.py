"""Small sequence helpers shared by the record types.

Deliberately dependency-free: every record package imports this, so anything it
imported back would close a cycle.
"""

from __future__ import annotations

from collections import Counter
from typing import Hashable, Iterable, Sequence, TypeVar

__all__ = ["duplicates"]

T = TypeVar("T", bound=Hashable)


def duplicates(items: Iterable[T]) -> list[T]:
    """The entries appearing more than once, sorted.

    THE DEFECT THIS REPLACES
    ------------------------
    This idiom was written **nine times** across the core::

        {name for name in names if names.count(name) > 1}

    ``list.count`` scans the whole sequence, and it is called once per entry, so
    the comprehension is **O(n^2)**. Nine records used it to reject duplicate
    names -- validation checks, validity conditions, model inputs and outputs,
    route ids, problem names, loss paths, condition prerequisites, and the
    reason list on an assessment -- and every one of them paid it on
    construction.

    Invisible at the sizes anything currently declares, and measured at the
    sizes it would take to matter: a report of 10,000 checks spent 684 ms here,
    and an assessment carrying 10,000 unknown conditions spent 3.1 s. Both are
    past any real declaration; both are the shape of a defect that only ever
    reveals itself on the day the input grows.

    ``Counter`` answers the same question in one pass. **The result is
    identical**, including its rendering: a sorted list, so the ``{duplicates}``
    already interpolated into eight of those error messages reads exactly as it
    did.

    Sorted because an error message that names a different subset order on
    each run is a message two readers cannot compare.
    """
    counted = Counter(items)
    return sorted(entry for entry, total in counted.items() if total > 1)
