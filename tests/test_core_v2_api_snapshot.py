"""Core V2 API snapshot: the pinned V2 surface is the live one, and it is V1 plus exactly the hybrid_uq additions."""

from __future__ import annotations

import json
import pathlib

from engcore import api_snapshot

REPO = pathlib.Path(__file__).resolve().parents[1]
V2_FROZEN = REPO / "tests" / "api" / "v2_frozen_api_snapshot.json"
V2_FULL = REPO / "tests" / "api" / "v2_full_api_snapshot.json"
V2_FROZEN_COUNT = 221
V2_ADDED_COUNT = 27


def _v2():
    return api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES)


def test_the_live_v2_frozen_surface_matches_the_pinned_snapshot():
    pinned = json.loads(V2_FROZEN.read_text(encoding="utf-8"))
    assert api_snapshot.canonical_bytes(api_snapshot.frozen_only(_v2())) == api_snapshot.canonical_bytes(pinned)


def test_the_live_v2_full_surface_matches_the_pinned_snapshot():
    pinned = json.loads(V2_FULL.read_text(encoding="utf-8"))
    assert api_snapshot.canonical_bytes(_v2()) == api_snapshot.canonical_bytes(pinned)


def test_the_v2_counts_are_v1_plus_the_additions():
    frozen = api_snapshot.frozen_only(_v2())
    assert frozen["symbol_count"] == V2_FROZEN_COUNT
    added = [e for e in frozen["symbols"] if e["module"] in api_snapshot.V2_ADDED_MODULES]
    assert len(added) == V2_ADDED_COUNT
    assert V2_FROZEN_COUNT - V2_ADDED_COUNT == api_snapshot.frozen_only()["symbol_count"] == 194


def test_no_v2_addition_is_experimental_or_deprecated():
    for entry in _v2()["symbols"]:
        if entry["module"] in api_snapshot.V2_ADDED_MODULES:
            assert entry["classification"] == "FREEZE", entry["name"]


def test_the_v2_pinned_file_is_written_with_lf_bytes():
    assert b"\r\n" not in V2_FROZEN.read_bytes() and b"\r\n" not in V2_FULL.read_bytes()
