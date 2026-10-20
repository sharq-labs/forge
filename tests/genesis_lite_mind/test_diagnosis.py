"""Diagnostic integrity tests; the live adapter test uses a separate unit namespace."""
import copy
import json
import os
import sys
from types import SimpleNamespace
import pytest
from tools import forge_mind_diagnosis as d


def test_plan_is_new_bounded_development():
    from tools.forge_mind_readiness import PUBLIC_SEED
    p = d.plan()
    assert p["namespace"] != PUBLIC_SEED
    assert p["primary_runs"] == len(p["jobs"]) == 12
    assert p["primary_cards"] == 72
    assert "no formal" in p["root"]


@pytest.mark.parametrize("field", ["namespace", "prereg_sha256", "sources", "pair_bound", "jobs"])
def test_mutated_plan_refuses(field):
    p = d.plan()
    p[field] = "modified"
    with pytest.raises(ValueError, match="mismatch"):
        d.verify(p)


def test_missing_duplicate_and_changed_trace_refuse():
    from benchmarks.genesis_lite_mind.arm import card_digest
    payloads = [{"card": {"universe_id": str(i)}} for i in range(6)]
    for p in payloads:
        p["card_digest"] = card_digest(p["card"])
    row = {"presented_card_digests": {"sealed-"+str(i): p["card_digest"] for i,p in enumerate(payloads)}}
    assert len(d.join_traces(row, payloads)) == 6
    for broken in (payloads[:5], payloads + payloads[:1]):
        with pytest.raises(ValueError):
            d.join_traces(row, broken)
    changed = copy.deepcopy(payloads)
    changed[0]["card"]["query_budget"] = 999
    with pytest.raises(ValueError):
        d.join_traces(row, changed)


def test_empty_posterior_is_unknown_not_zero():
    comp = SimpleNamespace(weights=lambda: {}, rows=[], rivals={},
                           problem=SimpleNamespace(inputs=[], covariates=["u"]),
                           noise=SimpleNamespace(to_dict=lambda: {"sd_ln": None}))
    view = d.snapshot(comp)
    assert view["support"] == "UNAVAILABLE"
    assert view["null_mass"] is None and view["inclusion"]["u"] is None


def test_real_export_replay_control_and_no_formal_access(monkeypatch, tmp_path):
    from benchmarks.genesis_lite.v0_3 import arms, formal, registry
    from tools.forge_blindfold_demo import semantic
    def forbidden(*a, **k):
        raise AssertionError("formal entry point called")
    monkeypatch.setattr(formal, "run_formal", forbidden)
    monkeypatch.setattr(registry.AttemptRegistry, "__init__", forbidden)
    monkeypatch.setattr(d, "NAMESPACE", "mind-trace-unit-only-not-diagnostic-grid-v1")
    monkeypatch.setattr(d, "JOBS", [("unit-trace-only", "anonymous", 31)])
    doc = d.plan()
    saved, env = dict(arms.ARMS), dict(os.environ)
    profiler = sys.getprofile()
    try:
        d.worker(doc, 0, tmp_path / "traced")
        arms.ARMS.clear()
        arms.ARMS.update(saved)
        d.worker(doc, 0, tmp_path / "control", no_trace=True)
    finally:
        arms.ARMS.clear()
        arms.ARMS.update(saved)
        os.environ.clear()
        os.environ.update(env)
    a = json.loads((tmp_path / "traced/run.json").read_bytes())
    b = json.loads((tmp_path / "control/run.json").read_bytes())
    assert semantic(a) == semantic(b)
    diags = json.loads((tmp_path / "traced/diagnostics.json").read_bytes())
    assert len(diags) == 6
    assert all(x["replay"]["status"] == "VERIFIED" for x in diags)
    assert all(len(x["trajectory"]) == x["observations"] + 1 for x in diags)
    assert sys.getprofile() is profiler
    trace_path = next((tmp_path / "traced/traces").glob("*.json"))
    corrupted = json.loads(trace_path.read_bytes())
    corrupted["trace"]["steps"][0]["record_digest"] = "0" * 64
    with pytest.raises(ValueError, match="diverged"):
        d.analyze(corrupted)
    corrupted = json.loads(trace_path.read_bytes())
    corrupted["trace"]["final_stop"]["reason"] = "fabricated stopping reason"
    with pytest.raises(ValueError, match="final stop/state"):
        d.analyze(corrupted)
