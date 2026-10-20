"""Development adapter guards; actual test fixtures use a different namespace."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import time

import pytest

spec=importlib.util.spec_from_file_location("mind_readiness",Path(__file__).resolve().parents[2]/"tools/forge_mind_readiness.py")
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


def test_fixed_plan_has_all_registered_baselines():
    doc=driver.plan()
    assert len(doc["arms"])==21 and len(doc["roles"])==20
    assert doc["expected_cards"]==5040 and doc["world_sets"]==40
    assert doc["roles"]["historical_answer"]=="adversarial"
    assert "NON-FORMAL" in doc["labels"]


def test_real_candidate_pairing_and_semantic_repeat_separate_test_namespace(monkeypatch):
    from benchmarks.genesis_lite.v0_3 import arms,formal,registry
    def forbidden(*a,**k): raise AssertionError("formal access")
    monkeypatch.setattr(formal,"run_formal",forbidden)
    monkeypatch.setattr(registry.AttemptRegistry,"__init__",forbidden)
    monkeypatch.setattr(driver,"CAMPAIGNS",("adapter-unit-development-only",))
    monkeypatch.setattr(driver,"PUBLIC_SEED","mind-adapter-unit-only-v1")
    doc=driver.plan()
    def run(arm,seed=0):
        saved=dict(arms.ARMS)
        try:return driver.worker(doc,arm,"anonymous",driver.CAMPAIGNS[0],seed)
        finally:arms.ARMS.clear();arms.ARMS.update(saved)
    first=run("mind_full");again=run("mind_full");base=run("careful")
    assert first["status"]==again["status"]==base["status"]=="VALID"
    assert first["key_digest"]==base["key_digest"]
    assert first["key_digest"]!=run("careful",1)["key_digest"]
    assert driver.semantic(first)==driver.semantic(again)
    assert first["tier_bound"]=="development" and first["pair_bound"]==doc["pair_bound"]
    assert first["arm_spec"]=="benchmarks.genesis_lite_mind.arm:mind_full"
    assert all(u["independent_agrees"] for u in first["universes"])


@pytest.mark.parametrize("field",["prereg_sha256","sources","pair_bound","dependency_sha256"])
def test_changed_plan_refuses(field):
    doc=driver.plan();doc[field]="tampered"
    with pytest.raises(ValueError,match="mismatch"):driver.verify_plan(doc)


def test_wrong_candidate_callable_refused(monkeypatch):
    from benchmarks.genesis_lite_mind import arm
    from benchmarks.genesis_lite.v0_3 import arms
    doc=driver.plan()
    monkeypatch.setattr(arm,"mind_full",lambda *a,**k: {})
    saved=dict(arms.ARMS)
    try:
        with pytest.raises(ValueError,match="callable identity"):
            driver.worker(doc,"mind_full","anonymous",driver.CAMPAIGNS[0],0)
    finally:arms.ARMS.clear();arms.ARMS.update(saved)


def test_missing_coverage_cannot_be_promising():
    result=driver.summarize([],[],driver.plan())
    assert result["recommendation"]=="BLOCKED_EXECUTION"
    assert result["formal_lift_claimed"] is False
    assert all(a["mean_six_kind_credit"] is None for a in result["arms"].values())


def test_exhausted_budget_keeps_unstarted_job(tmp_path):
    record=driver.execute(tmp_path/"unused.json",("mind_full","anonymous",driver.CAMPAIGNS[0],0),time.monotonic()-1)
    assert record["status"]=="DEVELOPMENT_EXECUTION_FAILED" and "NOT RUN" in record["reasons"][0]


def test_timeout_kills_own_process_group_and_retains_record(monkeypatch,tmp_path):
    killed=[]
    class Process:
        pid=12345
        calls=0
        def __init__(self,*a,**kw):
            assert kw["start_new_session"] is True
            assert kw["cwd"]==kw["env"]["TMPDIR"]
        def communicate(self,timeout=None):
            self.calls+=1
            if self.calls==1:raise subprocess.TimeoutExpired("test",timeout)
            assert timeout==5
            return "partial", "error"
    monkeypatch.setattr(driver.subprocess,"Popen",Process)
    monkeypatch.setattr(driver.os,"killpg",lambda pid,sig:killed.append(pid))
    result=driver.execute(tmp_path/"unused.json",("mind_full","anonymous",driver.CAMPAIGNS[0],0),time.monotonic()+10)
    assert killed==[12345] and result["stdout"]=="partial"
    assert result["status"]=="DEVELOPMENT_EXECUTION_FAILED"


def synthetic_complete(monkeypatch):
    from benchmarks.genesis_lite.v0_3 import analysis as a
    from engcore.blindfold.roles import DEFAULT_CREDIT
    doc=driver.plan()
    rows=[dict(arm=arm,presentation=p,campaign_id=c,seed=s,status="VALID",reasons=[],
        key_digest=f"synthetic-{p}-{c}-{s}",universes=[dict(kind=k,outcome="insufficient_evidence",
            credit=DEFAULT_CREDIT[k].get("insufficient_evidence",0),independent_agrees=True,
            truth_in_searched_family=True,proposal={"rationale":"synthetic-only"}) for k in a.KINDS])
        for arm in doc["arms"] for p in driver.PRESENTATIONS for c in driver.CAMPAIGNS for s in driver.SEEDS]
    replay=copy.deepcopy([r for r in rows if r["arm"]=="mind_full" and
                         r["campaign_id"]==driver.CAMPAIGNS[0] and r["seed"]==0])
    def analysis_only(*args,**kwargs):
        return dict(lift_claimed=False,screened_world_sets=1,primary={"pooled":{"lower95":1}},
                    holm_significant={"pooled":True},presentation_noninferiority={"all":True},
                    kind_noninferiority={"all":{"ok":True}})
    monkeypatch.setattr(a,"lift_decision",analysis_only)
    return doc,rows,replay


def test_one_symmetric_screen_retained_without_survivor_bias(monkeypatch):
    doc,rows,replay=synthetic_complete(monkeypatch)
    # Not one of the four replay slots.
    for row in rows:
        if row["seed"]==1 and row["presentation"]=="anonymous" and row["campaign_id"]==driver.CAMPAIGNS[0]:
            row.update(status="INVALID_BENCHMARK",reasons=["trap synthetic: invalid world"],universes=[])
    result=driver.summarize(rows,replay,doc)
    assert result["complete"] and len(result["screened_world_sets"])==1
    assert all(v["recorded_cards"]==39*6 for v in result["arms"].values())
    assert result["invalid_runs"]  # original failed record remains present


def test_excessive_screening_is_execution_blocker(monkeypatch):
    doc,rows,replay=synthetic_complete(monkeypatch)
    for row in rows:
        if row["seed"]==1 and row["presentation"]=="anonymous" and row["campaign_id"] in driver.CAMPAIGNS[:3]:
            row.update(status="INVALID_BENCHMARK",reasons=["trap synthetic: invalid world"],universes=[])
    result=driver.summarize(rows,replay,doc)
    assert result["screen_cap_exceeded"] and not result["complete"]
    assert result["recommendation"]=="BLOCKED_EXECUTION"


def test_one_arm_invalid_is_not_a_symmetric_screen(monkeypatch):
    doc,rows,replay=synthetic_complete(monkeypatch)
    row=next(r for r in rows if r["arm"]=="careful" and r["seed"]==1)
    row.update(status="INVALID_BENCHMARK",reasons=["trap synthetic: invalid world"],universes=[])
    result=driver.summarize(rows,replay,doc)
    assert not result["screened_world_sets"] and not result["complete"]


@pytest.mark.parametrize("failure",["missing","timeout","mismatch"])
def test_replay_failure_blocks_execution_not_mind_performance(monkeypatch,failure):
    doc,rows,replay=synthetic_complete(monkeypatch)
    if failure=="missing":replay.pop()
    elif failure=="timeout":replay[0].update(status="DEVELOPMENT_EXECUTION_FAILED",universes=[])
    else:replay[0]["key_digest"]="tampered"
    result=driver.summarize(rows,replay,doc)
    assert not result["complete"] and not result["replay_ok"]
    assert result["recommendation"]=="BLOCKED_EXECUTION"
