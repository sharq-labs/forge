"""Genesis-lite v0.1 contract (analysis.py): P-1 closed in the decision rule, and the review's channels closed too.

Synthetic records in the shape the harness writes. A proposer that trades control failures for discovery credit, that
invalidates world sets it is losing, or that wins on some presentations while losing on others must not obtain a lift
claim; a proposer that is better on discovery and no worse anywhere must.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from benchmarks.genesis_lite import analysis, arms

KINDS = analysis.KINDS
PRESENTATIONS = analysis.PRIMARY_FAMILY[1:]
ROLES = {"careful": "competence", "always_law": "floor", "reckless": "candidate", "trader": "candidate",
         "better": "candidate", "historical_answer": "adversarial", "single_setting": "sanity"}
BASELINE = {"discoverable": 0.1, "no_solution": 0.7, "insufficient_evidence": 1.0, "indistinguishable": 0.5,
            "spurious_correlate": 0.5, "confounded": 0.2}


def _records(arm, per_kind, *, campaigns=30, presentations=PRESENTATIONS, seeds=(0, 1), isolation="proposer_process",
             override=None):
    out = []
    for p in presentations:
        for s in seeds:
            for i in range(campaigns):
                kinds = dict(per_kind if override is None else override(p, s, i, per_kind))
                out.append({"arm": arm, "status": "VALID", "presentation": p, "campaign_id": f"c{i}", "seed": s,
                            "isolation": isolation,
                            "universes": [{"kind": k, "credit": kinds[k] * (1.0 if (i + s + len(k)) % 3 else 0.8)}
                                          for k in KINDS]})
    return out


def test_p1_a_reckless_proposer_gets_no_lift_however_much_discovery_it_wins():
    reckless = {"discoverable": 0.7, "no_solution": -1.0, "insufficient_evidence": -1.0, "indistinguishable": -0.8,
                "spurious_correlate": -0.8, "confounded": -1.0}
    d = analysis.lift_decision(_records("careful", BASELINE) + _records("reckless", reckless), "reckless", ROLES)
    assert d["lift_claimed"] is False and d["primary"]["pooled"]["mean_difference"] < 0


def test_p1_a_discovery_gain_bought_with_one_control_is_refused_by_noninferiority():
    trader = dict(BASELINE, discoverable=1.0, no_solution=0.4)       # +0.9 discovery, -0.3 on one control: net positive
    d = analysis.lift_decision(_records("careful", BASELINE) + _records("trader", trader), "trader", ROLES)
    assert d["primary"]["pooled"]["lower95"] > 0
    assert d["control_noninferiority"]["no_solution"]["ok"] is False and d["lift_claimed"] is False


def test_positive_control_a_better_and_no_worse_proposer_is_claimed():
    d = analysis.lift_decision(_records("careful", BASELINE) + _records("better", dict(BASELINE, discoverable=0.6)),
                               "better", ROLES)
    assert d["coverage_problems"] == [] and d["lift_claimed"] is True


def test_review_a_proposer_that_invalidates_the_world_sets_it_loses_gets_no_claim():
    better = _records("better", dict(BASELINE, discoverable=0.6))
    for r in better[::3]:
        r["status"] = "INVALID_BENCHMARK"                              # e.g. a crafted integrity failure
    d = analysis.lift_decision(_records("careful", BASELINE) + better, "better", ROLES)
    assert d["lift_claimed"] is False and any("not VALID" in p for p in d["coverage_problems"])


def test_review_missing_world_sets_and_non_isolated_runs_block_a_claim():
    only_some = _records("better", dict(BASELINE, discoverable=0.6), presentations=("anonymous", "renamed"))
    d = analysis.lift_decision(_records("careful", BASELINE) + only_some, "better", ROLES)
    assert d["lift_claimed"] is False and any("no VALID run" in p for p in d["coverage_problems"])
    in_process = _records("better", dict(BASELINE, discoverable=0.6), isolation="in_process")
    d = analysis.lift_decision(_records("careful", BASELINE) + in_process, "better", ROLES)
    assert d["lift_claimed"] is False and any("isolated" in p for p in d["coverage_problems"])


def test_review_winning_three_presentations_while_losing_the_trap_is_refused():
    def lose_trap(p, s, i, k):
        return dict(k, discoverable=-1.0) if p == "trap" else dict(k, discoverable=1.0)
    d = analysis.lift_decision(_records("careful", BASELINE) + _records("better", BASELINE, override=lose_trap),
                               "better", ROLES)
    assert d["presentation_noninferiority"]["trap"] is False and d["lift_claimed"] is False


def test_review_noninferiority_uses_the_best_arm_on_each_control_kind():
    strong_confounded = dict(BASELINE, confounded=1.0, discoverable=-1.0)   # weaker overall, best on confounded
    candidate = dict(BASELINE, discoverable=0.6)
    d = analysis.lift_decision(_records("careful", BASELINE) + _records("single_setting", strong_confounded)
                               + _records("better", candidate), "better", ROLES)
    assert d["strongest_baseline"] == "careful"
    assert d["control_noninferiority"]["confounded"]["reference_arm"] == "single_setting"
    assert d["control_noninferiority"]["confounded"]["ok"] is False and d["lift_claimed"] is False


def test_the_strongest_baseline_is_chosen_over_every_non_adversarial_arm_floors_included():
    credits = analysis.world_credits(_records("careful", BASELINE) + _records("always_law", {k: 2.0 for k in KINDS})
                                     + _records("historical_answer", {k: 5.0 for k in KINDS}))
    best, scores = analysis.strongest_baseline(credits, ROLES)
    assert best == "always_law" and "historical_answer" not in scores


def test_a_campaign_missing_a_kind_is_refused_not_scored_as_zero():
    rec = _records("careful", BASELINE, campaigns=1, presentations=("anonymous",), seeds=(0,))
    rec[0]["universes"] = rec[0]["universes"][1:]
    with pytest.raises(ValueError, match="every kind"):
        analysis.world_credits(rec)


def test_on_the_v0_pilot_data_the_reckless_floor_ranks_last_under_the_joint_endpoint():
    """The P-1 regression on real (v0 pilot) data, recomputed from the committed per-cell summary."""
    summary = json.loads((pathlib.Path(__file__).resolve().parents[2] / "benchmarks/genesis_lite/pilot_results/"
                          "v0-2026-10-14/summary.json").read_bytes())
    totals: dict[str, float] = {}
    for cell, row in summary["cells"].items():
        arm, _kind, _p = cell.split("|")
        totals[arm] = totals.get(arm, 0.0) + row["mean_credit"] / 4      # mean over the four presentations
    assert min(totals, key=totals.get) == "always_law"
    assert totals["always_law"] < 0 < totals["careful"]
    assert "fit_all_gated" in arms.ARMS and arms.ARMS["fit_all_gated"][3] == "competence"
