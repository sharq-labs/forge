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
    client = QueryCap(inner, 3)
    rem = [client.observe("u-1", {"x0": 1.0}, query_id=f"q{i}")["budget_remaining"] for i in range(3)]
    assert rem == [2, 1, 0]                                    # the world's true remaining budget never reaches the arm
    with pytest.raises(EscrowRefused) as exc:
        client.observe("u-1", {"x0": 1.0}, query_id="q3")
    assert is_budget_refusal(exc.value) and "u-1" in str(exc.value)
    assert inner.seen == ["q0", "q1", "q2"] and client.used == 3          # the refused query never reached the escrow


def test_a_refused_query_is_not_counted_against_the_cap():
    from benchmarks.genesis_lite.harness_v3 import QueryCap
    client = QueryCap(_Inner(refuse_at={"bad"}), 2)
    with pytest.raises(EscrowRefused) as exc:
        client.observe("u-1", {"x0": 9.0}, query_id="bad")
    assert not is_budget_refusal(exc.value) and client.used == 0
    client.observe("u-1", {"x0": 1.0}, query_id="a")
    client.observe("u-1", {"x0": 1.0}, query_id="b")
    assert client.used == 2


def test_the_capped_client_exposes_only_observe():
    from benchmarks.genesis_lite.harness_v3 import QueryCap
    client = QueryCap(_Inner(), 2)
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
