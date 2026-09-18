"""Core Freeze V2 as a historical record: what it froze, and that V3 supersedes it without rewriting it.

Until the main adversarial audit (2026-09-15) this module verified the V2 contract against the live
tree. That contract can no longer hold on a correct tree: its identity references are literal records
that contradict their own numbers (a DOWNGRADED route with missing thresholds and a uniqueness its
starts do not imply), and the audit's HUQ-09/HUQ-12 fixes make every such record refuse. Core Freeze
V3 (tests/test_core_freeze_v3_manifest.py) is the binding contract for descendants. What stays true,
and is asserted here, is the record V2 made of its own freeze.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.certification import core_freeze_v2, core_freeze_v3  # noqa: E402

MANIFEST = REPO / core_freeze_v2.MANIFEST_PATH


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_bytes())


def test_v2_was_additive_over_v1(manifest):
    api = manifest["api"]
    assert api["v1"]["frozen_digest"] == core_freeze_v2.V1_FROZEN_DIGEST
    assert api["v1"]["frozen_count"] == core_freeze_v2.V1_FROZEN_COUNT
    assert api["v1_entries_byte_identical_in_v2"] is True
    assert api["v2"]["frozen_count"] == api["v1"]["frozen_count"] + len(api["v2"]["added_frozen_symbols"])
    assert all(name.startswith("engcore.hybrid_uq.") for name in api["v2"]["added_frozen_symbols"])


def test_no_approximation_class_was_recorded_as_exact(manifest):
    assert not any(entry["exact_posterior"] for entry in manifest["vocabulary"]["approximation_classes"].values())


def test_every_v2_record_round_tripped_when_frozen(manifest):
    for name, entry in manifest["serialization_inventory"].items():
        assert entry["round_trip_byte_identical"] and entry["unknown_schema_refused"], name


def test_the_v2_frozen_api_surface_is_superseded_additively(manifest):
    """AMENDED at Core Freeze V4 (I-29, R-65/R-69). Was: the V2 surface is still the live surface.

    V3 superseded the V2 serialization contract and not its shapes, and this test asserted exactly
    that -- `core_freeze_v2.api_facts() == manifest["api"]`, live against recorded. The 2026-09-16
    scientific core re-audit moved the shapes, additively: the V2 frozen digest moved with the V1
    one, `RouteReason` grew from 24 members to 43, and no symbol, field, default or member was
    removed, renamed, revalued or reordered.

    So the claim here is the V4 one, and it is stronger than the equality it replaces: the live V2
    surface is compared with the V2 snapshot AS COMMITTED AT THE V2 FREEZE COMMIT -- read out of git
    and refused unless its bytes hash to what the V2 manifest pinned -- and every difference must be
    one of the additive kinds. The old form could only be satisfied by changing nothing, which is
    finding 95's complaint about `v1_entries_byte_identical_in_v2` one module along.
    """
    from engcore import api_snapshot
    from tools.certification import core_freeze_v4

    stored = core_freeze_v4.stored_v2_frozen_snapshot(REPO)
    assert stored["file_sha256"] == manifest["pinned_v2_snapshot_files"][stored["file"]]
    live = api_snapshot.frozen_only(api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES))
    assert core_freeze_v4.additive_only_problems(stored["snapshot"], live) == []
    assert live["symbol_count"] == manifest["api"]["v2"]["frozen_count"] == 221
    insertions = core_freeze_v4.enum_insertions(stored["snapshot"], live)
    assert "engcore.hybrid_uq.RouteReason" in insertions, (
        "the inserted members are not recorded anywhere, which is finding 95 itself")


def test_v3_supersedes_v2_and_records_its_bytes_and_reasons():
    v3_manifest = REPO / core_freeze_v3.MANIFEST_PATH
    if not v3_manifest.exists():
        pytest.skip("candidate: the V3 manifest is built from the candidate commit")
    recorded = json.loads(v3_manifest.read_bytes())
    assert recorded["v2_manifest_sha256"] == core_freeze_v2.sha256_bytes(MANIFEST.read_bytes())
    assert recorded["supersedes_v2_because"]


def test_the_v2_identity_references_are_refused_by_the_hardened_readers():
    """The reason V2 cannot bind any more, measured: its fixture records no longer construct."""
    assert core_freeze_v3.v2_fixtures_refused()
