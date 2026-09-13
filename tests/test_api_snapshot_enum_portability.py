"""Enum API snapshots must describe Forge semantics, not EnumType internals."""

from __future__ import annotations

import enum

from engcore import api_snapshot


class ExampleStatus(str, enum.Enum):
    READY = "ready"
    FAILED = "failed"


def test_enum_signature_is_canonical_and_runtime_independent():
    expected = {
        "parameters": [
            {
                "name": "values",
                "kind": "var_positional",
                "has_default": False,
                "default": {"kind": "none"},
            }
        ],
        "required": [],
    }

    assert api_snapshot._signature_of(ExampleStatus) == expected


def test_enum_description_preserves_members_while_hiding_metaclass_signature():
    description = api_snapshot.describe("tests", "ExampleStatus", ExampleStatus)

    assert description["kind"] == "enum"
    assert description["signature"] == {
        "parameters": [
            {
                "name": "values",
                "kind": "var_positional",
                "has_default": False,
                "default": {"kind": "none"},
            }
        ],
        "required": [],
    }
    assert description["enum_members"] == [
        {"name": "READY", "value": "ready"},
        {"name": "FAILED", "value": "failed"},
    ]
