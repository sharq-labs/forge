"""Genesis-lite v0.1 contract (analysis.py): P-1 closed in the decision rule, and the reviews' channels closed too.

Synthetic records in the shape the harness writes, under REGISTERED arm names (roles come from the frozen registry).
A proposer that trades control failures for discovery credit, that invalidates world sets, that wins on some
presentations while losing on others, or whose comparison set can be weakened must not obtain a lift claim; a proposer
that is better on discovery and no worse anywhere, on the full preregistered grid, must.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from benchmarks.genesis_lite import analysis, arms

KINDS = analysis.KINDS
PRESENTATIONS = analysis.PRIMARY_FAMILY[1:]
CAMPAIGNS = [f"c{i}" for i in range(30)]
SEEDS = (0, 1)
GRID = analysis.formal_grid(CAMPAIGNS, PRESENTATIONS, SEEDS)
BASELINE = {"discoverable": 0.1, "no_solution": 0.7, "insufficient_evidence": 1.0, "indistinguishable": 0.5,
            "spurious_correlate": 0.5, "confounded": 0.2}


def _records(arm, per_kind, *, presentations=PRESENTATIONS, seeds=SEEDS, isolation="proposer_process", override=None):
    out = []
    for p in presentations:
        for s in seeds:
            for c in CAMPAIGNS:
                i = int(c[1:])
                kinds = dict(per_kind if override is None else override(p, s, i, per_kind))
                out.append({"arm": arm, "status": "VALID", "presentation": p, "campaign_id": c, "seed": s,
                            "isolation": isolation,
                            "universes": [{"kind": k, "universe_id": f"{p}-{s}-{c}-{k}",
                                           "credit": kinds[k] * (1.0 if (i + s + len(k)) % 3 else 0.8)} for k in KINDS]})
    return out


def _decide(*records, candidate="mind"):
    return analysis.lift_decision([r for rec in records for r in rec], candidate, grid=GRID)


def test_p1_a_reckless_proposer_gets_no_lift_however_much_discovery_it_wins():
    reckless = {"discoverable": 0.7, "no_solution": -1.0, "insufficient_evidence": -1.0, "indistinguishable": -0.8,
                "spurious_correlate": -0.8, "confounded": -1.0}
    d = _decide(_records("careful", BASELINE), _records("mind", reckless))
    assert d["lift_claimed"] is False and d["primary"]["pooled"]["mean_difference"] < 0


def test_p1_a_discovery_gain_bought_with_one_control_is_refused_by_noninferiority():
    d = _decide(_records("careful", BASELINE), _records("mind", dict(BASELINE, discoverable=1.0, no_solution=0.4)))
    assert d["primary"]["pooled"]["lower95"] > 0
    assert d["control_noninferiority"]["no_solution"]["ok"] is False and d["lift_claimed"] is False


def test_positive_control_a_better_and_no_worse_proposer_on_the_full_grid_is_claimed():
    d = _decide(_records("careful", BASELINE), _records("mind", dict(BASELINE, discoverable=0.6)))
    assert d["coverage_problems"] == [] and d["lift_claimed"] is True


def test_review_a_proposer_that_invalidates_world_sets_it_loses_gets_no_claim():
    mind = _records("mind", dict(BASELINE, discoverable=0.6))
    for r in mind[::3]:
        r["status"] = "INVALID_BENCHMARK"
    d = _decide(_records("careful", BASELINE), mind)
    assert d["lift_claimed"] is False and any("not VALID" in p for p in d["coverage_problems"])


def test_review_missing_world_sets_and_non_isolated_runs_block_a_claim():
    d = _decide(_records("careful", BASELINE), _records("mind", dict(BASELINE, discoverable=0.6),
                                                        presentations=("anonymous", "renamed")))
    assert d["lift_claimed"] is False and any("preregistered world sets" in p for p in d["coverage_problems"])
    d = _decide(_records("careful", BASELINE), _records("mind", dict(BASELINE, discoverable=0.6), isolation="in_process"))
    assert d["lift_claimed"] is False and any("isolated" in p for p in d["coverage_problems"])


def test_review_an_incomplete_baseline_blocks_a_claim_instead_of_shrinking_the_comparison():
    careful = _records("careful", BASELINE)
    for r in careful[::5]:
        r["status"] = "INVALID_BENCHMARK"
    d = _decide(careful, _records("mind", dict(BASELINE, discoverable=0.6)))
    assert d["lift_claimed"] is False and any(p.startswith("careful:") for p in d["coverage_problems"])


def test_review_paired_world_sets_must_hold_the_same_universes():
    mind = _records("mind", dict(BASELINE, discoverable=0.6))
    for r in mind[:10]:
        for u in r["universes"]:
            u["universe_id"] = "other-root-" + u["universe_id"]
    d = _decide(_records("careful", BASELINE), mind)
    assert d["lift_claimed"] is False and any("different universes" in p for p in d["coverage_problems"])


def test_review_winning_three_presentations_while_losing_the_trap_is_refused():
    def lose_trap(p, s, i, k):
        return dict(k, discoverable=-1.0) if p == "trap" else dict(k, discoverable=1.0)
    d = _decide(_records("careful", BASELINE), _records("mind", BASELINE, override=lose_trap))
    assert d["presentation_noninferiority"]["trap"] is False and d["lift_claimed"] is False


def test_review_noninferiority_uses_the_best_arm_on_each_control_kind():
    d = _decide(_records("careful", BASELINE), _records("single_setting", dict(BASELINE, confounded=1.0, discoverable=-1.0)),
                _records("mind", dict(BASELINE, discoverable=0.6)))
    assert d["strongest_baseline"] == "careful"
    assert d["control_noninferiority"]["confounded"]["reference_arm"] == "single_setting"
    assert d["control_noninferiority"]["confounded"]["ok"] is False and d["lift_claimed"] is False


def test_review_roles_come_from_the_registry_and_strangers_are_refused():
    assert analysis.registered_roles()["always_law"] == "floor" and analysis.registered_roles()["careful"] == "competence"
    with pytest.raises(analysis.AnalysisRefused, match="unregistered"):
        _decide(_records("careful", BASELINE), _records("my_weak_baseline", BASELINE), _records("mind", BASELINE))


def test_review_a_duplicate_world_set_record_is_refused_not_overwritten():
    careful = _records("careful", BASELINE)
    with pytest.raises(analysis.AnalysisRefused, match="two VALID records"):
        _decide(careful + careful[:1], _records("mind", dict(BASELINE, discoverable=0.6)))


def test_review_missing_kinds_and_non_finite_credits_are_refused():
    rec = _records("careful", BASELINE, presentations=("anonymous",), seeds=(0,))[:1]
    rec[0]["universes"] = rec[0]["universes"][1:]
    with pytest.raises(analysis.AnalysisRefused, match="every kind"):
        analysis.world_credits(rec)
    rec = _records("careful", BASELINE, presentations=("anonymous",), seeds=(0,))[:1]
    rec[0]["universes"][0]["credit"] = float("nan")
    with pytest.raises(analysis.AnalysisRefused, match="non-finite"):
        analysis.world_credits(rec)


def test_the_strongest_baseline_is_chosen_over_every_non_adversarial_arm_floors_included():
    credits = analysis.world_credits(_records("careful", BASELINE) + _records("always_law", {k: 2.0 for k in KINDS})
                                     + _records("historical_answer", {k: 5.0 for k in KINDS}))
    best, scores = analysis.strongest_baseline(credits, analysis.registered_roles())
    assert best == "always_law" and "historical_answer" not in scores


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
