"""v0.4 preregistration candidate: built from the code it binds, never written where a formal run would accept it, and
frozen only by the owner with every blocking item resolved."""

from __future__ import annotations

import pytest

from benchmarks.genesis_lite import pilot_v4, preregistration_v4 as p4


def test_the_candidate_binds_the_current_identity_and_roster():
    doc = p4.build()
    assert doc["status"] == "CANDIDATE_NOT_FROZEN"
    assert doc["development_identity_v4"] == pilot_v4.development_identity_v4()[0]
    assert set(doc["roster"]) == set(pilot_v4.ROSTER)
    assert doc["grid"]["world_sets_per_arm"] == 2400
    assert doc["custody"]["label"] == "SELF_ADMINISTERED"
    assert doc["statistics"]["noninferiority"]["against"].startswith("every")


def test_the_candidate_is_never_written_where_the_formal_tier_reads():
    assert p4.CANDIDATE.parent != pilot_v4.PREREG.parent
    assert "CANDIDATE" in p4.CANDIDATE.name


def test_freeze_refuses_without_the_owners_approval():
    with pytest.raises(ValueError, match="approval"):
        p4.freeze("  ", {})


def test_the_crash_classification_and_the_proposer_environment_block_the_freeze():
    blocking = {k for k, v in p4.OPEN_ITEMS.items() if v["blocking"]}
    assert {"D15-crash-classification", "A1b-proposer-env", "A1-pysr-units-dev-pilot", "A6-cost"} <= blocking
    assert not p4.OPEN_ITEMS["M-d-candidate-registration"]["blocking"]
    others = {k: "resolved" for k in blocking - {"D15-crash-classification"}}
    with pytest.raises(ValueError, match="D15-crash-classification"):
        p4.freeze("owner: freeze", others)
    assert not pilot_v4.PREREG.exists()


def test_freeze_refuses_while_blocking_items_are_open():
    with pytest.raises(ValueError, match="blocking open items"):
        p4.freeze("owner: freeze", {"A6-cost": "measured"})
    assert not pilot_v4.PREREG.exists()
