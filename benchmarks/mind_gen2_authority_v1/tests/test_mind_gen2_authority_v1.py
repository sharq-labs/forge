"""GEN2-BR1.1 benchmark integrity: the committed authority matrix and the BR1 re-score reproduce, and say what they say."""

from __future__ import annotations

import json
import pathlib

from benchmarks.mind_gen2_authority_v1 import rescore
from benchmarks.mind_gen2_authority_v1 import run_benchmark as rb

HERE = pathlib.Path(rb.__file__).resolve().parent


def test_the_authority_matrix_reproduces():
    assert rb._dump(rb.matrix()) == rb.AUTHORITY_PATH.read_bytes()


def test_the_br1_rescore_reproduces():
    assert rescore.dump(rescore.build()) == rescore.PATH.read_bytes()


def test_nothing_unverified_is_ever_admitted_and_every_admission_replays():
    s = json.loads(rb.AUTHORITY_PATH.read_bytes())["summary"]
    assert s["mutations_admitted"] == 0 and s["mutations_total"] >= 100
    assert s["owner_changes_admitted"] == 0 and s["owner_changes_total"] >= 25
    assert s["replay_reproduced"] == s["replay_total"] == s["base_total"]
    assert s["base_not_admitted"] == [
        "drone/simulate_flight: MISSING_INFORMATION ['APPLICABILITY_INPUT_NOT_EXACT']",
        "hvac_field/simulate_building: MISSING_INFORMATION ['APPLICABILITY_INPUT_NOT_EXACT']",
    ]


def test_the_gen1_failure_class_stays_refused_with_declared_alternatives():
    g = json.loads(rb.AUTHORITY_PATH.read_bytes())["gen1_failure_class"]
    assert g["status"] == "INFEASIBLE_PROTOCOL" and "LEVEL_NOT_DECLARED" in g["codes"] and not g["admitted"]
    assert [a["magnitude"] for a in g["alternatives_I_A"]] == [1.0, 2.0]
    assert g["label"] == "admissible options under the declared world, not recommendations"


def test_every_world_is_verified_and_bound():
    worlds = json.loads(rb.AUTHORITY_PATH.read_bytes())["worlds"]
    assert set(worlds) == set(rb.NAMES)
    assert all(w["verified"] and w["bindings"] >= 2 for w in worlds.values())
