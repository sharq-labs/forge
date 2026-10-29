"""EXC-3 (owner-approved 2026-10-29): experiment selection under a scarce budget.

The v0.3 harness may cap the observations every arm makes on a universe below the world's budget: the presented card
states the cap, and the arm's client refuses past it with the escrow's own budget-refusal text. The worlds, the escrow,
the scoring and the credit table are unchanged; at fraction 1.0 nothing changes at all.
"""

from __future__ import annotations

import json
import math

import pytest

from engcore.blindfold.escrow import EscrowRefused, is_budget_refusal

SEED = (21).to_bytes(4, "big") * 8


def _card(budget=40, inputs=2):
    return {"universe_id": "u-1", "query_budget": budget, "query_cost": 1.0,
            "inputs": [{"name": f"x{i}", "settable": True, "range": [1.0, 2.0]} for i in range(inputs)]}


@pytest.mark.parametrize("budget,inputs,fraction,cap", [(40, 2, 1.0, 40), (40, 2, 0.5, 20), (40, 2, 0.25, 10),
                                                        (12, 4, 0.25, 6), (12, 3, 0.5, 6), (5, 4, 0.25, 5),
                                                        (13, 2, 0.5, 6)])
def test_the_cap_is_a_fraction_of_the_budget_with_a_d_plus_2_floor_never_above_the_budget(budget, inputs, fraction, cap):
    from benchmarks.genesis_lite.harness_v3 import query_cap
    assert query_cap(_card(budget, inputs), fraction) == cap


@pytest.mark.parametrize("fraction", [0, -0.5, 1.5, math.nan, math.inf, True, "0.5", None])
def test_a_fraction_outside_zero_to_one_is_refused(fraction):
    from benchmarks.genesis_lite.harness_v3 import query_cap
    with pytest.raises(ValueError):
        query_cap(_card(), fraction)


def test_a_card_whose_query_cost_is_not_one_is_refused_below_the_full_budget():
    from benchmarks.genesis_lite.harness_v3 import query_cap
    card = {**_card(), "query_cost": 2.0}
    assert query_cap(card, 1.0) == 40
    with pytest.raises(ValueError):
        query_cap(card, 0.5)


class _Inner:
    def __init__(self, refuse_at=()):
        self.seen, self.refuse_at = [], set(refuse_at)

    def observe(self, uid, settings, query_id=""):
        self.seen.append(query_id)
        if query_id in self.refuse_at:
            raise EscrowRefused("x0=9 lies outside the box")
        return {"budget_remaining": 999, "observation": {"x0": settings["x0"], "y": 1.0}}


def test_the_capped_client_refuses_past_the_cap_with_the_escrows_budget_text():
    from benchmarks.genesis_lite.harness_v3 import QueryCap
    inner = _Inner()
    client = QueryCap(inner, 3, "u-1", {"x0"})
    rem = [client.observe("u-1", {"x0": 1.0}, query_id=f"q{i}")["budget_remaining"] for i in range(3)]
    assert rem == [2, 1, 0]                                    # the world's true remaining budget never reaches the arm
    with pytest.raises(EscrowRefused) as exc:
        client.observe("u-1", {"x0": 1.0}, query_id="q3")
    assert is_budget_refusal(exc.value) and "u-1" in str(exc.value)
    assert inner.seen == ["q0", "q1", "q2"] and client.used == 3          # the refused query never reached the escrow


def test_a_refused_query_is_not_counted_against_the_cap():
    from benchmarks.genesis_lite.harness_v3 import QueryCap
    client = QueryCap(_Inner(refuse_at={"bad"}), 2, "u-1", {"x0"})
    with pytest.raises(EscrowRefused) as exc:
        client.observe("u-1", {"x0": 9.0}, query_id="bad")
    assert not is_budget_refusal(exc.value) and client.used == 0
    client.observe("u-1", {"x0": 1.0}, query_id="a")
    client.observe("u-1", {"x0": 1.0}, query_id="b")
    assert client.used == 2


def test_the_capped_client_exposes_only_observe():
    from benchmarks.genesis_lite.harness_v3 import QueryCap
    client = QueryCap(_Inner(), 2, "u-1", {"x0"})
    assert not hasattr(client, "seen") and not hasattr(client, "refuse_at")


@pytest.mark.parametrize("arm", ["careful", "mind_full"])
def test_every_arm_sees_and_keeps_to_the_cap(arm):
    from benchmarks.genesis_lite import pilot_v3
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    rec = run_one_v3(arm, pilot_v3._arm(arm), master_seed=SEED, campaign_id="gl-v03-cap", presentation="anonymous",
                     budget_fraction=0.25)
    assert rec.status == "VALID" and rec.evaluator_status == "VALID", rec.reasons
    assert rec.budget_fraction == 0.25
    observing = [u for u in rec.universes if u["observe_calls"]]
    assert observing and all(u["observe_calls"] <= u["query_cap"] < u["query_budget"] for u in observing)


def test_at_fraction_one_the_cap_is_the_world_budget_and_the_card_is_unchanged():
    from benchmarks.genesis_lite import pilot_v3
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    run = lambda **kw: run_one_v3("careful", pilot_v3._arm("careful"), master_seed=SEED, campaign_id="gl-v03-cap",  # noqa: E731
                                  presentation="anonymous", **kw)
    default, full = run(), run(budget_fraction=1.0)
    assert full.status == "VALID" and full.presented_card_digests == default.presented_card_digests
    assert all(u["query_cap"] == u["query_budget"] for u in full.universes)


def test_the_same_worlds_are_scored_at_every_fraction():
    from benchmarks.genesis_lite import pilot_v3
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    kinds = [[(u["universe_id"], u["kind"]) for u in run_one_v3("careful", pilot_v3._arm("careful"), master_seed=SEED,
                                                                 campaign_id="gl-v03-cap", presentation="anonymous",
                                                                 budget_fraction=f).universes]
             for f in (1.0, 0.5, 0.25)]
    assert kinds[0] == kinds[1] == kinds[2]


@pytest.mark.parametrize("fraction", [0.0, 2.0, math.nan])
def test_an_invalid_fraction_invalidates_the_run(fraction):
    from benchmarks.genesis_lite import pilot_v3
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    rec = run_one_v3("careful", pilot_v3._arm("careful"), master_seed=SEED, campaign_id="gl-v03-cap",
                     presentation="anonymous", budget_fraction=fraction)
    assert rec.status == "INVALID_BENCHMARK" and any("budget fraction" in r for r in rec.reasons)


# ---- pilot -------------------------------------------------------------------------------------------------------------
def test_the_plan_runs_every_fraction_on_each_world_set_before_the_next():
    from benchmarks.genesis_lite.pilot_v3 import Task, plan
    tasks = plan(["a", "b"], campaigns=2, presentations=("anonymous",), seeds=(0,), fractions=(1.0, 0.25))
    assert tasks[:4] == [Task("a", 0, "anonymous", 0, 1.0), Task("b", 0, "anonymous", 0, 1.0),
                         Task("a", 0, "anonymous", 0, 0.25), Task("b", 0, "anonymous", 0, 0.25)]
    assert len(tasks) == 8 and Task("a", 0, "anonymous", 0).budget_fraction == 1.0


def _rec(arm, campaign, fraction, credit, calls=3):
    return {"arm": arm, "status": "VALID", "reasons": [], "wall_seconds": 1.0, "observe_calls": calls,
            "worker_maxrss_kib": 100, "v3_total_credit": credit,
            "universes": [{"kind": "discoverable", "answer": "law", "outcome": "law_pass", "credit": credit,
                           "rationale": "r", "observe_calls": calls}],
            "task": {"arm": arm, "campaign": campaign, "presentation": "anonymous", "seed": 0, "budget_fraction": fraction}}


def test_the_summary_reports_each_level_apart_with_the_predeclared_contrasts():
    from benchmarks.genesis_lite.pilot_v3 import CONTRASTS, _summarize
    assert CONTRASTS == (("mind_full", "mind_no_adaptive_selection"), ("bo_botorch_variance", "space_filling"))
    arms = ["mind_full", "mind_no_adaptive_selection"]
    recs = [_rec("mind_full", 0, 1.0, 1.0), _rec("mind_no_adaptive_selection", 0, 1.0, 1.0),
            _rec("mind_full", 1, 1.0, 1.0), _rec("mind_no_adaptive_selection", 1, 1.0, 0.0),
            _rec("mind_full", 0, 0.25, 1.0), _rec("mind_no_adaptive_selection", 0, 0.25, -1.0),
            _rec("mind_full", 1, 0.25, 0.0), _rec("mind_no_adaptive_selection", 1, 0.25, 1.0)]
    s = _summarize(arms, {a: True for a in arms}, recs, [], [], ("anonymous",), (0,), 2, 1.0, 1, 10.0, planned=8,
                   fractions=(1.0, 0.25))
    assert s["design"]["budget_fractions"] == [1.0, 0.25]
    assert set(s["budget_levels"]) == {"1.0", "0.25"}
    assert s["budget_levels"]["0.25"]["arms"]["mind_full"]["descriptive_credit"]["paired_mean_total"] == 0.5
    c = {(x["a"], x["b"]): x for x in s["budget_levels"]["0.25"]["contrasts"]}
    full = c[("mind_full", "mind_no_adaptive_selection")]
    assert (full["paired_world_sets"], full["mean_difference"], full["a_better"], full["b_better"], full["ties"]) == (
        2, 0.5, 1, 1, 0)
    assert full["label"].startswith("DEVELOPMENT_DESCRIPTIVE")
    absent = c[("bo_botorch_variance", "space_filling")]
    assert absent["paired_world_sets"] == 0 and absent["mean_difference"] is None
    one = {(x["a"], x["b"]): x for x in s["budget_levels"]["1.0"]["contrasts"]}[("mind_full", "mind_no_adaptive_selection")]
    assert (one["mean_difference"], one["a_better"], one["ties"]) == (0.5, 1, 1)


def test_a_run_over_fractions_writes_every_level_and_resummarizes_without_missing_records(tmp_path):
    from benchmarks.genesis_lite.pilot_v3 import resummarize, run_pilot
    s = run_pilot(["always_refuse", "careful"], out=tmp_path, campaigns=1, presentations=("anonymous",), seeds=(0,),
                  workers=1, deadline_seconds=300.0, root=bytes(32), fractions=(1.0, 0.25))
    assert s["tasks"]["planned"] == 4 and s["tasks"]["completed"] == 4
    assert set(s["budget_levels"]) == {"1.0", "0.25"}
    rows = [json.loads(x) for x in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert sorted(r["task"]["budget_fraction"] for r in rows) == [0.25, 0.25, 1.0, 1.0]
    assert resummarize(tmp_path)["tasks"]["missing_records"] == 0


def test_the_cli_takes_the_budget_fractions(tmp_path, monkeypatch):
    from benchmarks.genesis_lite import pilot_v3
    seen = {}
    monkeypatch.setattr(pilot_v3, "run_pilot", lambda names, **kw: seen.update(kw) or {
        "tasks": {}, "elapsed_seconds": 0, "paired_world_sets_complete": 0})
    pilot_v3.main(["--out", str(tmp_path), "--arms", "careful", "--budget-fractions", "1.0,0.5,0.25"])
    assert seen["fractions"] == (1.0, 0.5, 0.25)


# ---- review of a9734570 (CHANGES REQUIRED, 2026-10-29): fixed before the pilot --------------------------------------------
def _run(arm, fraction=0.25, campaign="gl-v03-cap", fn=None):
    from benchmarks.genesis_lite import pilot_v3
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    return run_one_v3(arm, fn or pilot_v3._arm(arm), master_seed=SEED, campaign_id=campaign, presentation="anonymous",
                      budget_fraction=fraction, proposer_kind="baseline" if fn else None)


def test_every_universe_records_its_inputs_cap_and_the_selection_queries_each_design_leaves():
    from benchmarks.genesis_lite.harness_v3 import selection_queries
    from benchmarks.genesis_lite.mind_arm_v3 import problem_from_card
    from engcore.mind.minimal.runner import initial_design
    rec = _run("careful")
    for u in rec.universes:
        assert {"inputs", "query_cap", "query_budget", "mind_selection_queries", "bo_selection_queries"} <= set(u)
    card = {**_card(12, 4), "inputs": [{"name": f"x{i}", "settable": True, "range": [1.0, 2.0], "unit": "1"}
                                       for i in range(4)], "observed_covariates": [], "output": {"name": "y", "unit": "1"},
            "assessment_region": {f"x{i}": [1.0, 2.0] for i in range(4)}}
    for cap in (5, 6, 7, 12, 15, 30):
        shown = {**card, "query_budget": cap}
        got = selection_queries(shown)
        assert got["mind"] == max(0, cap - len(initial_design(problem_from_card(shown), 0)))


@pytest.mark.parametrize("cap,inputs", [(5, 3), (6, 4), (7, 3), (15, 4), (30, 3), (60, 4)])
def test_the_bo_selection_count_matches_the_arms_own_initial_design(cap, inputs, monkeypatch):
    from benchmarks.genesis_lite import arms, arms_v3
    from benchmarks.genesis_lite.harness_v3 import selection_queries
    card = {**_card(cap, inputs), "output": {"name": "y", "unit": "1"}}
    seen = []

    class Stop(Exception):
        pass

    def first_collect(card_, client, points, tag):
        seen.append(len(points))
        raise Stop

    monkeypatch.setattr(arms, "_collect", first_collect)
    with pytest.raises(Stop):
        arms_v3.bo_botorch_variance(card, client=None, seed=0)
    replicate = min(4, cap // 4)
    assert selection_queries(card)["bo"] == max(0, cap - replicate - seen[0])


def test_cap_and_used_are_read_only():
    from benchmarks.genesis_lite.harness_v3 import QueryCap
    client = QueryCap(_Inner(), 2, "u-1", {"x0"})
    for name in ("cap", "used"):
        with pytest.raises(AttributeError):
            setattr(client, name, 10 ** 6)


def test_an_arm_that_breaks_the_cap_invalidates_the_run():
    def greedy(card, client, *, seed=0):
        setattr(client, "_QueryCap__cap", 10 ** 6)          # reaching past the read-only view
        x = card["inputs"]
        for k in range(int(card["query_budget"]) + 3):
            try:
                client.observe(card["universe_id"], {i["name"]: i["range"][0] for i in x}, query_id=f"g{k}")
            except EscrowRefused:
                break
        return {"universe_id": card["universe_id"], "answer": "insufficient_evidence", "rationale": "greedy"}
    rec = _run("greedy", fn=greedy)
    assert rec.status == "INVALID_BENCHMARK" and any("cap" in r for r in rec.reasons), rec.reasons


def test_an_arm_that_ignores_the_card_budget_stops_at_the_cap_and_is_not_inadmissible():
    def eager(card, client, *, seed=0):
        x = card["inputs"]
        n = 0
        while True:
            try:
                client.observe(card["universe_id"], {i["name"]: i["range"][0] for i in x}, query_id=f"e{n}")
                n += 1
            except EscrowRefused:
                break
        return {"universe_id": card["universe_id"], "answer": "insufficient_evidence", "rationale": f"eager {n}"}
    rec = _run("eager", fn=eager)
    assert rec.status == "VALID", rec.reasons
    assert all(u["answer"] != "inadmissible" and u["observe_calls"] == u["query_cap"] for u in rec.universes)


@pytest.mark.parametrize("settings,uid", [({"zz": 1.0}, None), ({}, "other")])
def test_past_the_cap_a_malformed_query_is_still_the_arms_failure(settings, uid):
    from benchmarks.genesis_lite.harness_v3 import QueryCap
    client = QueryCap(_Inner(), 0, "u-1", {"x0"})
    with pytest.raises(EscrowRefused) as exc:
        client.observe(uid or "u-1", settings, query_id="q")
    assert not is_budget_refusal(exc.value)


def test_a_capped_card_differs_from_the_full_card_only_in_its_budget():
    cards = {}

    def spy(card, client, *, seed=0):
        cards.setdefault(card["universe_id"], []).append(dict(card))
        return {"universe_id": card["universe_id"], "answer": "insufficient_evidence", "rationale": "spy"}
    for f in (1.0, 0.25):
        assert _run("spy", fraction=f, fn=spy).status == "VALID"
    for full, capped in cards.values():
        assert {k for k in full if full[k] != capped[k]} <= {"query_budget"}
        assert capped["query_budget"] <= full["query_budget"]


@pytest.mark.parametrize("arm", ["mind_no_adaptive_selection", "space_filling", "bo_botorch_variance"])
def test_the_contrasted_arms_keep_to_the_cap(arm):
    if arm == "bo_botorch_variance":
        pytest.importorskip("botorch")
    rec = _run(arm)
    assert rec.status == "VALID", rec.reasons
    assert all(u["observe_calls"] <= u["query_cap"] for u in rec.universes)


def _urec(arm, campaign, fraction, credits, budgets=(12, 60), mind_sel=(0, 3), bo_sel=(0, 2), status="VALID"):
    return {"arm": arm, "status": status, "reasons": [], "wall_seconds": 1.0, "observe_calls": 3,
            "worker_maxrss_kib": 100, "v3_total_credit": sum(credits),
            "universes": [{"universe_id": f"u{i}", "kind": "discoverable", "answer": "law", "outcome": "law_pass",
                           "credit": c, "rationale": "r", "observe_calls": 3, "query_budget": b,
                           "query_cap": max(1, int(b * fraction)), "mind_selection_queries": m, "bo_selection_queries": s}
                          for i, (c, b, m, s) in enumerate(zip(credits, budgets, mind_sel, bo_sel))],
            "task": {"arm": arm, "campaign": campaign, "presentation": "anonymous", "seed": 0, "budget_fraction": fraction}}


def test_contrasts_are_paired_per_universe_stratified_and_on_worlds_common_to_every_level():
    from benchmarks.genesis_lite.pilot_v3 import _summarize
    arms_ = ["mind_full", "mind_no_adaptive_selection"]
    recs = [_urec("mind_full", 0, 0.25, (1.0, 1.0)), _urec("mind_no_adaptive_selection", 0, 0.25, (1.0, -1.0)),
            _urec("mind_full", 1, 0.25, (0.0, 1.0)), _urec("mind_no_adaptive_selection", 1, 0.25, (0.0, 1.0)),
            _urec("mind_full", 0, 1.0, (1.0, 1.0)), _urec("mind_no_adaptive_selection", 0, 1.0, (1.0, 1.0)),
            _urec("mind_full", 1, 1.0, (1.0, 1.0), status="INVALID_BENCHMARK"),
            _urec("mind_no_adaptive_selection", 1, 1.0, (1.0, 1.0))]
    s = _summarize(arms_, {a: True for a in arms_}, recs, [], [], ("anonymous",), (0,), 2, 1.0, 1, 10.0, planned=8,
                   fractions=(1.0, 0.25))
    lv = s["budget_levels"]["0.25"]
    assert 0 < lv["realised_fraction_mean"] <= 1
    c = {(x["a"], x["b"]): x for x in lv["contrasts"]}[("mind_full", "mind_no_adaptive_selection")]
    pu = c["per_universe"]
    assert pu["opportunity_field"] == "mind_selection_queries"
    assert (pu["all"]["n"], pu["all"]["mean_difference"], pu["all"]["a_better"], pu["all"]["ties"]) == (4, 0.5, 1, 3)
    assert pu["without_selection_opportunity"]["n"] == 2 and pu["without_selection_opportunity"]["a_better"] == 0
    assert pu["with_selection_opportunity"]["n"] == 2 and pu["with_selection_opportunity"]["mean_difference"] == 1.0
    assert set(pu["by_query_budget"]) == {"12", "60"}
    assert (c["common_world_sets"], c["common_mean_difference"]) == (1, 2.0)    # campaign 1 is not VALID at 1.0
    notes = {(x["a"], x["b"]): x["note"] for x in lv["contrasts"]}
    assert "design and analysis confounded" in notes[("bo_botorch_variance", "space_filling")]
    assert "design only" in notes[("mind_full", "mind_no_adaptive_selection")]


# ---- re-review of 1648ce7b (APPROVE WITH NOTES): notes 3 and 4 --------------------------------------------------------
def test_an_inadmissible_universe_keeps_its_cap_and_budget():
    def boom(card, client, *, seed=0):
        raise RuntimeError("arm failure")
    rec = _run("boom", fn=boom)
    assert rec.status == "VALID" and all(u["answer"] == "inadmissible" for u in rec.universes)
    assert all(u["query_cap"] <= u["query_budget"] and "observe_calls" in u for u in rec.universes)


def test_a_failure_recording_the_cap_data_invalidates_the_run_not_the_arm(monkeypatch):
    from benchmarks.genesis_lite import harness_v3

    def broken(card):
        raise ZeroDivisionError("bookkeeping")
    monkeypatch.setattr(harness_v3, "selection_queries", broken)
    rec = _run("careful")
    assert rec.status == "INVALID_BENCHMARK" and any("bookkeeping" in r for r in rec.reasons), rec.reasons
