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


def test_the_v2_frozen_api_surface_is_still_the_live_surface(manifest):
    """V3 superseded the V2 serialization contract, not its shapes."""
    assert core_freeze_v2.api_facts() == manifest["api"]


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
