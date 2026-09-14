"""The frozen API records union semantics, not CPython's private union class."""

from __future__ import annotations

import typing

from engcore import api_snapshot


def _shape(value):
    entry = api_snapshot.describe("example.public", "Alias", value)
    return {
        "kind": entry["kind"],
        "defined_in": entry.get("defined_in"),
        "union_members": entry.get("union_members"),
    }


def test_pep604_and_typing_union_have_one_canonical_snapshot_shape():
    modern = _shape(int | str)
    legacy = _shape(typing.Union[int, str])

    assert modern == legacy
    assert modern == {
        "kind": "Union",
        "defined_in": "typing",
        "union_members": ["builtins.int", "builtins.str"],
    }


def test_union_member_order_does_not_change_the_contract():
    assert _shape(int | str)["union_members"] == _shape(str | int)["union_members"]


def test_non_union_objects_keep_their_real_defining_module():
    entry = api_snapshot.describe("example.public", "dict", dict)
    assert entry["kind"] == "class"
    assert entry["defined_in"] == "builtins"
