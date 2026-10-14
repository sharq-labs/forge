"""Genesis-lite v0.1 contract (analysis.py): the P-1 defect is closed in the decision rule, not by tuning.

Synthetic records, built to the shape the harness writes. A proposer that trades control failures for discovery credit
must not obtain a lift claim; a proposer that is better on discovery and no worse on controls must.
"""

from __future__ import annotations

import json
import pathlib

from benchmarks.genesis_lite import analysis, arms

KINDS = ("confounded", "discoverable", "indistinguishable", "insufficient_evidence", "no_solution", "spurious_correlate")


def _records(arm: str, per_kind: dict[str, float], campaigns: int = 30, presentations=analysis.PRIMARY_FAMILY[1:]):
    out = []
    for p in presentations:
        for i in range(campaigns):
            out.append({"arm": arm, "status": "VALID", "presentation": p, "campaign_id": f"c{i}", "seed": 0,
                        "universes": [{"kind": k, "credit": per_kind[k] if (i + len(k)) % 3 else per_kind[k] * 0.8}
                                      for k in KINDS]})
    return out


BASELINE = {"discoverable": 0.1, "no_solution": 0.7, "insufficient_evidence": 1.0, "indistinguishable": 0.5,
            "spurious_correlate": 0.5, "confounded": 0.2}


def test_p1_a_reckless_proposer_gets_no_lift_however_much_discovery_it_wins():
    reckless = {"discoverable": 0.7, "no_solution": -1.0, "insufficient_evidence": -1.0, "indistinguishable": -0.8,
                "spurious_correlate": -0.8, "confounded": -1.0}
    credits = analysis.world_credits(_records("careful", BASELINE) + _records("reckless", reckless))
    decision = analysis.lift_decision(credits, "reckless", "careful")
    assert decision["lift_claimed"] is False
    assert decision["primary"]["pooled"]["mean_difference"] < 0


def test_p1_a_discovery_gain_bought_with_one_control_is_refused_by_noninferiority():
    trader = dict(BASELINE, discoverable=1.0, no_solution=0.4)       # +0.9 discovery, -0.3 on one control: net positive
    credits = analysis.world_credits(_records("careful", BASELINE) + _records("trader", trader))
    decision = analysis.lift_decision(credits, "trader", "careful")
    assert decision["primary"]["pooled"]["lower95"] > 0
    assert decision["control_noninferiority"]["no_solution"]["ok"] is False
    assert decision["lift_claimed"] is False


def test_positive_control_a_better_and_no_worse_proposer_is_claimed():
    better = dict(BASELINE, discoverable=0.6)
    credits = analysis.world_credits(_records("careful", BASELINE) + _records("better", better))
    assert analysis.lift_decision(credits, "better", "careful")["lift_claimed"] is True


def test_no_shared_campaigns_means_no_claim():
    credits = analysis.world_credits(_records("careful", BASELINE) + _records("other", dict(BASELINE, discoverable=1.0),
                                                                                 presentations=("trap",)))
    credits["other"] = {("x", f"z{i}"): v for i, v in enumerate(credits["other"].values())}
    assert analysis.lift_decision(credits, "other", "careful")["lift_claimed"] is False


def test_the_strongest_baseline_is_chosen_over_every_non_adversarial_arm_floors_included():
    roles = {"careful": "competence", "always_law": "floor", "historical_answer": "adversarial"}
    credits = analysis.world_credits(_records("careful", BASELINE)
                                     + _records("always_law", {k: 2.0 for k in KINDS})
                                     + _records("historical_answer", {k: 5.0 for k in KINDS}))
    best, scores = analysis.strongest_baseline(credits, roles)
    assert best == "always_law" and "historical_answer" not in scores


def test_failed_and_invalid_runs_never_enter_the_endpoint():
    rec = _records("careful", BASELINE, campaigns=2, presentations=("anonymous",))
    rec[0]["status"] = "INVALID_BENCHMARK"
    credits = analysis.world_credits(rec)
    assert list(credits["careful"]) == [("anonymous", "c1")]


def test_on_the_v0_pilot_data_the_reckless_floor_ranks_last_under_the_v01_endpoint():
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
