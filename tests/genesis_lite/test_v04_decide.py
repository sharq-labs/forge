"""decide_v4: the formal entry takes roles, grid, provenance and representation verdicts from the sealed run and the
revealed root, never from the caller (review findings 3, 4 and 10; re-review H1, H2, M1, L1, L3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from benchmarks.genesis_lite import decide_v4, pilot_v4
from benchmarks.genesis_lite.analysis import KINDS, AnalysisRefused
from benchmarks.genesis_lite.isolated_host import CAP_SETS, ISOLATION_LABEL, NAMESPACES

from .test_analysis_v4 import BASE, FLOOR, outcome_for

IDENTITY = "i" * 64
ROOT = bytes(range(32))
ROOT_C = hashlib.sha256(ROOT).hexdigest()
LAW_KINDS = ("confounded", "discoverable", "spurious_correlate")
HIDDEN = ["/home", "/root"]
RUNTIME = {"public_test_fixture": True}
RUNTIME_DIGEST = hashlib.sha256(json.dumps(RUNTIME, sort_keys=True).encode()).hexdigest()
MANIFEST = json.dumps({"proposer_runtime_identity": {"sha256": RUNTIME_DIGEST, "content": RUNTIME}}, sort_keys=True).encode()
GOOD_CHECK = {"inspected": True, "uid": [65534] * 4, "gid": [65534] * 4, "groups": [], "caps": dict.fromkeys(CAP_SETS, 0),
              "no_new_privs": True, "private_namespaces": dict.fromkeys(NAMESPACES, True),
              "hidden": dict.fromkeys(HIDDEN, True), "private_tmp": True,
              "whitelist_covered": True, "exposed_read_only": {"/opt/x": True},
              "private_writable": {"/tmp": True, "/dev/shm": True}, "shared_state_covered": {"/run": True}}


def _record(arm, task, credits, *, tier="formal", isolation=ISOLATION_LABEL, identity=IDENTITY):
    cid = pilot_v4.campaign_id(tier, task)
    return {"arm": arm, "status": "VALID", "presentation": task.presentation, "campaign_id": cid, "seed": task.seed,
            "task": asdict(task), "isolation": isolation, "isolation_checks": [GOOD_CHECK] * 6,
            "development_identity_v4": identity, "proposer_runtime_identity_sha256": RUNTIME_DIGEST,
            "completed_within_deadline": True,
            "universes": [{"kind": k, "credit": float(credits[k]), "outcome": outcome_for(k, float(credits[k])),
                           "independent_agrees": True, "universe_id": f"u-{cid}-{k}", "region_tell": "box"}
                          for k in KINDS]}


def _all_represented(records, root):
    """Stand-in for reveal_v4.represented on synthetic records (the real one re-derives worlds from the root)."""
    assert root == ROOT
    return {"represented": {u["universe_id"]: True for r in records for u in r["universes"] if u["kind"] in LAW_KINDS}}


@pytest.fixture(autouse=True)
def _tree(monkeypatch):
    monkeypatch.setattr(decide_v4, "development_identity_v4", lambda: (IDENTITY, []))
    monkeypatch.setattr(decide_v4, "formal_identity_check", lambda identity: "")
    monkeypatch.setattr(decide_v4, "formal_runtime_check", lambda manifest: "")
    monkeypatch.setattr(decide_v4, "read_root", lambda path: ROOT)
    monkeypatch.setattr(decide_v4, "represented", _all_represented)


def _run_dir(tmp_path, *, drop_arm=None, tamper=None, tier="formal", summary=None, commit=None, uids=None):
    arms = sorted(pilot_v4.roles()) + ["mind"]
    tasks = [pilot_v4.Task(a, c, p, 0) for c in range(2) for p in pilot_v4.PRESENTATIONS for a in arms]
    if drop_arm:
        tasks = [t for t in tasks if t.arm != drop_arm]
    roles = pilot_v4.roles()
    recs = [_record(t.arm, t, FLOOR if roles.get(t.arm) in ("floor", "sanity", "adversarial") else BASE, tier=tier)
            for t in tasks]
    if uids:
        for r, t in zip(recs, tasks):
            uids(r, t)
    if tamper:
        tamper(recs)
    runs = "".join(json.dumps(r, sort_keys=True) + "\n" for r in recs).encode()
    commitment = {"root_commitment_sha256": ROOT_C, "development_identity_v4": IDENTITY, "tier": tier,
                  "tasks": [asdict(t) for t in tasks], "planned_campaigns": len(tasks), "tree_dirty": False,
                  "v0_2_pin_changed": [], "proposer_env": {}, "exposed": ["/opt/x"], "hidden": HIDDEN,
                  "proposer_runtime_identity_sha256": RUNTIME_DIGEST,
                  "environment_manifest_sha256": hashlib.sha256(MANIFEST).hexdigest(),
                  **(commit or {})}
    (tmp_path / "commitment.json").write_text(json.dumps(commitment))
    done = {**commitment, "runs_sha256": hashlib.sha256(runs).hexdigest(), "completed": len(tasks),
            "not_run_at_deadline": 0, **(summary or {})}
    (tmp_path / "summary.json").write_text(json.dumps(done))
    (tmp_path / "runs.jsonl").write_bytes(runs)
    (tmp_path / "environment.json").write_bytes(MANIFEST)
    return tmp_path


def _decide(d, **kw):
    return decide_v4.decide(d, d / "root.bin", "mind", **kw)


def test_a_complete_sealed_run_is_analysed_under_the_frozen_roster(tmp_path):
    out = _decide(_run_dir(tmp_path))
    assert out["coverage_problems"] == [] and out["lift_claimed"] is False
    assert out["commitment"]["tier"] == "formal" and out["tier_status"] == "FORMAL"


def test_dropping_a_baseline_from_the_task_list_refuses(tmp_path):
    with pytest.raises(AnalysisRefused, match="frozen roster"):
        _decide(_run_dir(tmp_path, drop_arm="grammar_enumeration"))


@pytest.mark.parametrize("field,value", [("isolation", "in_process"), ("development_identity_v4", "x" * 64),
                                         ("isolation_checks", [GOOD_CHECK] * 5)])
def test_a_record_of_other_provenance_refuses(tmp_path, field, value):
    def tamper(recs):
        recs[0][field] = value
    with pytest.raises(AnalysisRefused, match="provenance"):
        _decide(_run_dir(tmp_path, tamper=tamper))


def test_edited_runs_refuse(tmp_path):
    d = _run_dir(tmp_path)
    (d / "runs.jsonl").write_bytes((d / "runs.jsonl").read_bytes()[:-10] + b"0000000000")
    with pytest.raises(AnalysisRefused, match="digest"):
        _decide(d)


# ------------------------------------------------------------------- H1: the reveal is recomputed, never trusted


def test_another_root_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(decide_v4, "read_root", lambda path: b"\x01" * 32)
    with pytest.raises(AnalysisRefused, match="root does not match"):
        _decide(_run_dir(tmp_path))


def test_the_cap_inputs_come_from_the_recomputed_reveal_not_from_a_supplied_file(tmp_path, monkeypatch):
    # nothing is represented: every law-kind cell is capped. A hand-written reveal claiming the opposite must not lift it
    seen = {}

    def nothing_represented(records, root):
        out = {u["universe_id"]: False for r in records for u in r["universes"] if u["kind"] in LAW_KINDS}
        seen["verdicts"] = out
        return {"represented": out}
    monkeypatch.setattr(decide_v4, "represented", nothing_represented)
    d = _run_dir(tmp_path)
    runs_sha = hashlib.sha256((d / "runs.jsonl").read_bytes()).hexdigest()
    forged = {"runs_sha256": runs_sha, "root_commitment_sha256": ROOT_C,
              "represented": {u: True for u in _all_represented(
                  [json.loads(x) for x in (d / "runs.jsonl").read_text().splitlines()], ROOT)["represented"]}}
    (d / "reveal.json").write_text(json.dumps(forged))
    with pytest.raises(AnalysisRefused, match="differs from the one recomputed"):
        _decide(d, reveal_path=d / "reveal.json")
    calls = []
    real = decide_v4.a4.decision
    monkeypatch.setattr(decide_v4.a4, "decision", lambda *a, **k: calls.append(a[3]) or real(*a, **k))
    _decide(d)
    assert calls == [seen["verdicts"]]


def test_a_root_that_does_not_reproduce_the_worlds_refuses(tmp_path, monkeypatch):
    def wrong(records, root):
        raise ValueError("law-kind universes were not re-derived from this root")
    monkeypatch.setattr(decide_v4, "represented", wrong)
    with pytest.raises(AnalysisRefused, match="cannot be recomputed"):
        _decide(_run_dir(tmp_path))


def _real_worlds(record, task):
    """Give a synthetic record the universe ids and monomial flags of the worlds the root really derives."""
    from benchmarks.genesis_lite.evaluator import score_v3
    from benchmarks.genesis_lite.expressibility_v3 import worlds
    by_kind = {w.kind.value: w for w in worlds(pilot_v4.master_seed(ROOT, task.campaign, task.presentation, task.seed),
                                               pilot_v4.campaign_id("formal", task))}
    for u in record["universes"]:
        w = by_kind[u["kind"]]
        u["universe_id"] = w.universe_id
        u["truth_in_searched_family"] = w.law is not None and score_v3.v2.in_monomial_family(w.law)


def test_the_real_reveal_runs_through_decide_on_worlds_the_root_derives(tmp_path, monkeypatch):
    # review 2026-10-31 M-d: the real reveal_v4.represented, not the stand-in, decides the cap inputs
    from benchmarks.genesis_lite import reveal_v4
    monkeypatch.setattr(decide_v4, "represented", reveal_v4.represented)
    d = _run_dir(tmp_path, uids=_real_worlds)
    out = _decide(d)
    assert out["coverage_problems"] == [] and out["tier_status"] == "FORMAL"
    monkeypatch.setattr(decide_v4, "read_root", lambda path: b"\x07" * 32)
    with pytest.raises(AnalysisRefused, match="root does not match"):
        _decide(d)


def test_the_multiplicity_is_holm_and_the_caller_cannot_choose_another(tmp_path):
    # review 2026-10-31 H-a: D9 fixes Holm over the pre-declared family
    import inspect
    assert "multiplicity" not in inspect.signature(decide_v4.decide).parameters
    assert _decide(_run_dir(tmp_path))["multiplicity"] == "holm_family"


@pytest.mark.parametrize("commit,match", [({"tree_dirty": True}, "dirty tree"),
                                          ({"v0_2_pin_changed": ["scoring.py"]}, "v0.2 pin")])
def test_a_formal_run_from_a_dirty_tree_or_a_moved_pin_refuses(tmp_path, commit, match):
    with pytest.raises(AnalysisRefused, match=match):
        _decide(_run_dir(tmp_path, commit=commit))


def test_a_verification_of_other_hides_than_the_committed_ones_refuses(tmp_path):
    def tamper(recs):
        recs[0]["isolation_checks"] = [{**GOOD_CHECK, "hidden": {"/home": True}}] * 6
    with pytest.raises(AnalysisRefused, match="provenance"):
        _decide(_run_dir(tmp_path, tamper=tamper))


def test_a_malformed_task_refuses_instead_of_crashing(tmp_path):
    def tamper(recs):
        recs[0]["task"] = {"arm": "careful"}
    with pytest.raises(AnalysisRefused, match="malformed task"):
        _decide(_run_dir(tmp_path, tamper=tamper))


# ------------------------------------------------------------------- H2: the deciding code is the code that ran


def test_code_changed_after_the_run_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(decide_v4, "development_identity_v4", lambda: ("j" * 64, []))
    with pytest.raises(AnalysisRefused, match="not the code that ran"):
        _decide(_run_dir(tmp_path))


def test_a_changed_v02_pin_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(decide_v4, "development_identity_v4", lambda: (IDENTITY, ["scoring.py"]))
    with pytest.raises(AnalysisRefused, match="not the code that ran"):
        _decide(_run_dir(tmp_path))


def test_a_formal_decision_needs_the_frozen_preregistration(tmp_path, monkeypatch):
    monkeypatch.setattr(decide_v4, "formal_identity_check", lambda identity: "no frozen v0.4 preregistration")
    with pytest.raises(AnalysisRefused, match="formal decision refused"):
        _decide(_run_dir(tmp_path))


def test_the_real_formal_check_refuses_without_a_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(decide_v4, "formal_identity_check", pilot_v4.formal_identity_check)
    if not pilot_v4.PREREG.exists():
        with pytest.raises(AnalysisRefused, match="formal decision refused"):
            _decide(_run_dir(tmp_path))


def test_a_development_run_is_development_only_and_never_claims_lift(tmp_path, monkeypatch):
    real = decide_v4.a4.decision
    monkeypatch.setattr(decide_v4.a4, "decision", lambda *a, **k: {**real(*a, **k), "lift_claimed": True})
    monkeypatch.setattr(decide_v4, "formal_identity_check", lambda identity: "must not be consulted")
    out = _decide(_run_dir(tmp_path, tier="development"))
    assert out["lift_claimed"] is False and out["tier_status"] == "DEVELOPMENT_ONLY"


# ------------------------------------------------------------------- M1, L1, L3: complete runs and bound records


@pytest.mark.parametrize("summary,match", [({"not_run_at_deadline": 3}, "deadline"),
                                           ({"completed": 1}, "completed"),
                                           ({"not_run_at_deadline": None}, "deadline")])
def test_an_incomplete_run_refuses(tmp_path, summary, match):
    with pytest.raises(AnalysisRefused, match=match):
        _decide(_run_dir(tmp_path, summary=summary))


@pytest.mark.parametrize("status", ["INVALID_BENCHMARK", "WORKER_FAILED", "DEADLINE_COMPLETED", "DEADLINE_TERMINATED"])
def test_any_non_valid_record_blocks_even_for_an_adversarial_arm(tmp_path, status):
    def tamper(recs):
        next(r for r in recs if r["arm"] == "historical_answer")["status"] = status
    with pytest.raises(AnalysisRefused, match="non-VALID"):
        _decide(_run_dir(tmp_path, tamper=tamper))


def test_a_missing_record_refuses(tmp_path):
    with pytest.raises(AnalysisRefused, match="record"):
        _decide(_run_dir(tmp_path, tamper=lambda recs: recs.pop()))


@pytest.mark.parametrize("field,value", [("campaign_id", "gl-v04-formal-9-anonymous"), ("seed", 7),
                                         ("presentation", "trap")])
def test_a_record_that_names_another_campaign_than_its_task_refuses(tmp_path, field, value):
    def tamper(recs):
        r = next(r for r in recs if r["presentation"] != "trap")
        r[field] = value
    with pytest.raises(AnalysisRefused, match="another campaign"):
        _decide(_run_dir(tmp_path, tamper=tamper))


def test_a_duplicated_record_refuses(tmp_path):
    def tamper(recs):
        recs[-1] = dict(recs[0])
    with pytest.raises(AnalysisRefused, match="not one committed task"):
        _decide(_run_dir(tmp_path, tamper=tamper))


@pytest.mark.parametrize("key", ["tier", "planned_campaigns", "root_commitment_sha256", "hidden", "proposer_env",
                                "proposer_runtime_identity_sha256", "environment_manifest_sha256"])
def test_a_summary_missing_a_bound_key_refuses(tmp_path, key):
    d = _run_dir(tmp_path)
    s = json.loads((d / "summary.json").read_text())
    s.pop(key)
    (d / "summary.json").write_text(json.dumps(s))
    with pytest.raises(AnalysisRefused, match="lacks"):
        _decide(d)


@pytest.mark.parametrize("mutation", ["missing", "modified"])
def test_saved_runtime_manifest_must_survive_replay(tmp_path, mutation):
    d = _run_dir(tmp_path)
    if mutation == "missing":
        (d / "environment.json").unlink()
    else:
        (d / "environment.json").write_text(MANIFEST.decode().replace("true", "false"))
    with pytest.raises(AnalysisRefused, match="manifest refused"):
        _decide(d)


def test_same_source_run_cannot_be_replayed_under_another_registered_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(decide_v4, "formal_runtime_check", pilot_v4.formal_runtime_check)
    path = tmp_path / "registration.json"
    path.write_text(json.dumps({"proposer_runtime_identity_sha256": "another-runtime"}))
    monkeypatch.setattr(pilot_v4, "PREREG", path)
    with pytest.raises(AnalysisRefused, match="runtime/environment"):
        _decide(_run_dir(tmp_path))


def test_each_worker_record_is_bound_to_the_committed_runtime(tmp_path):
    def tamper(records):
        records[0]["proposer_runtime_identity_sha256"] = "another-runtime"
    with pytest.raises(AnalysisRefused, match="provenance"):
        _decide(_run_dir(tmp_path, tamper=tamper))


def test_missing_operator_deadline_evidence_never_means_on_time(tmp_path):
    with pytest.raises(AnalysisRefused, match="operator deadline"):
        _decide(_run_dir(tmp_path, tamper=lambda rows: rows[0].pop("completed_within_deadline")))
