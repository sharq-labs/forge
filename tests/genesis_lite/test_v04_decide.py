"""decide_v4: the formal entry takes roles, grid and provenance from the sealed run, never from the caller (review
findings 3, 4 and 10)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from benchmarks.genesis_lite import decide_v4, pilot_v4
from benchmarks.genesis_lite.analysis import KINDS, AnalysisRefused
from benchmarks.genesis_lite.isolated_host import ISOLATION_LABEL

from .test_analysis_v4 import BASE, FLOOR, outcome_for

IDENTITY = "i" * 64
ROOT_C = "r" * 64
GOOD_CHECK = {"inspected": True, "uid": [65534] * 4, "gid": [65534] * 4, "groups": [], "caps": {"CapEff": 0},
              "no_new_privs": True, "private_namespaces": {"mnt": True}, "hidden": {"/home": True}, "private_tmp": True,
              "whitelist_covered": True, "exposed_read_only": {"/opt/x": True},
              "private_writable": {"/tmp": True, "/dev/shm": True}, "shared_state_covered": {"/run": True}}


def _record(arm, task, credits, *, tier="formal", isolation=ISOLATION_LABEL, identity=IDENTITY):
    cid = pilot_v4.campaign_id(tier, task)
    return {"arm": arm, "status": "VALID", "presentation": task.presentation, "campaign_id": cid, "seed": task.seed,
            "task": asdict(task), "isolation": isolation, "isolation_checks": [GOOD_CHECK] * 6,
            "development_identity_v4": identity,
            "universes": [{"kind": k, "credit": float(credits[k]), "outcome": outcome_for(k, float(credits[k])),
                           "independent_agrees": True, "universe_id": f"u-{cid}-{k}", "region_tell": "box"}
                          for k in KINDS]}


def _run_dir(tmp_path, *, drop_arm=None, tamper=None):
    arms = sorted(pilot_v4.roles()) + ["mind"]
    tasks = [pilot_v4.Task(a, c, p, 0) for c in range(2) for p in pilot_v4.PRESENTATIONS for a in arms]
    if drop_arm:
        tasks = [t for t in tasks if t.arm != drop_arm]
    roles = pilot_v4.roles()
    recs = [_record(t.arm, t, FLOOR if roles.get(t.arm) in ("floor", "sanity", "adversarial") else BASE) for t in tasks]
    if tamper:
        tamper(recs)
    runs = "".join(json.dumps(r, sort_keys=True) + "\n" for r in recs).encode()
    commitment = {"root_commitment_sha256": ROOT_C, "development_identity_v4": IDENTITY, "tier": "formal",
                  "tasks": [asdict(t) for t in tasks]}
    (tmp_path / "commitment.json").write_text(json.dumps(commitment))
    (tmp_path / "summary.json").write_text(json.dumps({**commitment, "runs_sha256": hashlib.sha256(runs).hexdigest()}))
    (tmp_path / "runs.jsonl").write_bytes(runs)
    law = {u["universe_id"]: True for r in recs for u in r["universes"] if u["kind"] in ("confounded", "discoverable",
                                                                                         "spurious_correlate")}
    reveal = {"runs_sha256": hashlib.sha256(runs).hexdigest(), "root_commitment_sha256": ROOT_C, "represented": law}
    (tmp_path / "reveal.json").write_text(json.dumps(reveal))
    return tmp_path


def test_a_complete_sealed_run_is_analysed_under_the_frozen_roster(tmp_path):
    out = decide_v4.decide(_run_dir(tmp_path), tmp_path / "reveal.json", "mind")
    assert out["coverage_problems"] == [] and out["lift_claimed"] is False
    assert out["commitment"]["tier"] == "formal"


def test_dropping_a_baseline_from_the_task_list_refuses(tmp_path):
    with pytest.raises(AnalysisRefused, match="frozen roster"):
        decide_v4.decide(_run_dir(tmp_path, drop_arm="grammar_enumeration"), tmp_path / "reveal.json", "mind")


@pytest.mark.parametrize("field,value", [("isolation", "in_process"), ("development_identity_v4", "x" * 64),
                                         ("campaign_id", "gl-v04-development-0-0-anonymous"),
                                         ("isolation_checks", [GOOD_CHECK] * 5)])
def test_a_record_of_other_provenance_refuses(tmp_path, field, value):
    def tamper(recs):
        recs[0][field] = value
    with pytest.raises(AnalysisRefused, match="provenance"):
        decide_v4.decide(_run_dir(tmp_path, tamper=tamper), tmp_path / "reveal.json", "mind")


def test_edited_runs_refuse(tmp_path):
    d = _run_dir(tmp_path)
    (d / "runs.jsonl").write_bytes((d / "runs.jsonl").read_bytes()[:-10] + b"0000000000")
    with pytest.raises(AnalysisRefused, match="digest"):
        decide_v4.decide(d, d / "reveal.json", "mind")


def test_a_reveal_from_another_root_refuses(tmp_path):
    d = _run_dir(tmp_path)
    reveal = json.loads((d / "reveal.json").read_text())
    (d / "reveal.json").write_text(json.dumps({**reveal, "root_commitment_sha256": "z" * 64}))
    with pytest.raises(AnalysisRefused, match="root"):
        decide_v4.decide(d, d / "reveal.json", "mind")
