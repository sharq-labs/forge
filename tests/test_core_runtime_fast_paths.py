"""The exact-type fast paths added this round must agree with the slow paths.

WHY THIS FILE EXISTS, and it is not a good reason
--------------------------------------------------
The Sprint 9 mutation run planted PERF-RT-3 -- the ``dict`` fast path in
``encode`` dropping canonical key ordering -- and **nothing caught it**. The
optimization was written in this round, the gap was created in this round, and
only the mutant found it.

A fast path is a second implementation of a rule. Adding one without a test
that the two implementations agree is how a record starts serializing
differently depending on the order its keys happened to be inserted, which is
exactly the kind of drift a canonical form exists to prevent.

So: every fast path added this round is checked against the general path it
short-circuits, on inputs that take each branch.
"""

from __future__ import annotations

import json

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.serialization import encode, unwritable


class MappingSubclass(dict):
    """A Mapping that is NOT exactly ``dict``, so it takes the ABC branch."""


class CustomMapping:
    """A Mapping by registration only: neither ``dict`` nor a subclass of it."""

    def __init__(self, data):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


from collections.abc import Mapping as _ABCMapping  # noqa: E402

_ABCMapping.register(CustomMapping)


# =====================================================================
# encode -- canonical key ordering, on every branch
# =====================================================================

UNSORTED = {"zebra": 1, "alpha": 2, "middle": 3, "9": 4, "Beta": 5}


def test_encode_sorts_keys_whatever_order_they_were_inserted():
    """THE GAP PERF-RT-3 FOUND. Canonical means canonical on the fast path too."""
    forward = encode(dict(UNSORTED))
    backward = encode({k: UNSORTED[k] for k in reversed(list(UNSORTED))})

    assert list(forward) == sorted(UNSORTED, key=str)
    assert forward == backward
    assert json.dumps(forward) == json.dumps(backward)


def test_the_dict_fast_path_and_the_mapping_path_agree():
    """Three shapes, one answer: exactly-dict, dict subclass, registered Mapping."""
    plain = encode(dict(UNSORTED))
    subclass = encode(MappingSubclass(UNSORTED))
    registered = encode(CustomMapping(UNSORTED))
    assert plain == subclass == registered
    assert list(plain) == list(subclass) == list(registered)


def test_nested_mappings_are_sorted_at_every_depth():
    payload = {"b": {"z": 1, "a": 2}, "a": {"y": 3, "x": 4}}
    got = encode(payload)
    assert list(got) == ["a", "b"]
    assert list(got["a"]) == ["x", "y"]
    assert list(got["b"]) == ["a", "z"]


def test_encode_still_refuses_what_it_always_refused():
    with pytest.raises(ScientificCoreError, match="cannot serialize"):
        encode(object())


@pytest.mark.parametrize("value", [True, False, 0, 1, -3, 2.5, "text", None])
def test_the_leaf_fast_path_returns_leaves_unchanged(value):
    assert encode(value) is value or encode(value) == value


def test_bool_is_not_silently_widened_to_int():
    """`True` must come back as a bool, not as 1: they read back differently."""
    assert encode({"flag": True}) == {"flag": True}
    assert isinstance(encode({"flag": True})["flag"], bool)


# =====================================================================
# unwritable -- the float and dict fast paths
# =====================================================================

def test_the_float_fast_path_still_refuses_non_finite_values():
    """THE GAP PERF-RT-4 targets. A fast path that skips a refusal is a hole."""
    assert unwritable({"x": float("nan")}, path="m") == ("m['x']", "float('nan')")
    assert unwritable({"x": float("inf")}, path="m") == ("m['x']", "float('inf')")
    assert unwritable({"x": float("-inf")}, path="m") == ("m['x']", "float('inf')")
    assert unwritable({"x": 1.5}, path="m") is None


def test_the_dict_fast_path_still_refuses_a_non_string_key():
    assert unwritable({1: "a"}, path="m") == ("m[1]", "int key")
    assert unwritable(MappingSubclass({1: "a"}), path="m") == ("m[1]", "int key")
    assert unwritable(CustomMapping({1: "a"}), path="m") == ("m[1]", "int key")


def test_the_fast_and_general_paths_report_the_same_path_expression():
    """A refusal that points at the wrong leaf is a refusal nobody can act on."""
    payload = {"outer": {"inner": [1, 2, float("nan")]}}
    assert unwritable(payload, path="meta") == ("meta['outer']['inner'][2]", "float('nan')")
    assert unwritable(MappingSubclass(payload), path="meta") == (
        "meta['outer']['inner'][2]", "float('nan')"
    )


def test_a_writable_structure_is_still_accepted_on_every_branch():
    payload = {"a": 1, "b": [1, "x", True, None], "c": {"d": 2.5}}
    assert unwritable(payload) is None
    assert unwritable(MappingSubclass(payload)) is None
    assert unwritable(CustomMapping(payload)) is None


def test_a_tuple_is_still_admitted_and_an_object_still_is_not():
    assert unwritable({"t": (1, 2)}) is None
    found = unwritable({"o": object()}, path="m")
    assert found is not None and found[1] == "object"
