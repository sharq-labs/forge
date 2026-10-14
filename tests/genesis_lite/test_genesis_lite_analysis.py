"""Genesis-lite lift contract (analysis.py): P-1 closed in the decision rule, and the reviews' channels closed too.

Synthetic records in the shape the harness writes, under REGISTERED arm names (roles come from the frozen registry), with
every registered non-adversarial arm present (tests/genesis_lite/lift_records.py). A proposer that trades control
failures for discovery credit, that invalidates world sets, that wins on some presentations while losing on others, or
whose comparison set can be weakened must not obtain a lift claim; a proposer that is better on discovery and no worse
anywhere, on the full preregistered grid, must. The G0/A1 final-review channels are in test_genesis_lite_final_review.py.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from benchmarks.genesis_lite import analysis, arms
from tests.genesis_lite.lift_records import BETTER, CAREFUL, GRID, KINDS, field, records

RECKLESS = {"discoverable": 0.9, **{k: 0.0 for k in KINDS if k != "discoverable"}}


@pytest.fixture(autouse=True)
def _small_formal_grid(monkeypatch):
    monkeypatch.setattr(analysis, "FORMAL_GRID", GRID)
    monkeypatch.setattr(analysis, "BOOTSTRAP", 400)


def _decide(rows, candidate="mind"):
    return analysis.lift_decision(rows, candidate, grid=GRID)


def test_p1_a_reckless_proposer_gets_no_lift_however_much_discovery_it_wins():
    d = _decide(field() + records("mind", RECKLESS))
    assert d["lift_claimed"] is False and d["primary"]["pooled"]["mean_difference"] < 0


def test_p1_a_discovery_gain_bought_with_one_control_is_refused_by_noninferiority():
    d = _decide(field() + records("mind", dict(CAREFUL, discoverable=1.0, no_solution=0.5)))
    assert d["primary"]["pooled"]["lower95"] > 0
    assert d["kind_noninferiority"]["no_solution"]["ok"] is False and d["lift_claimed"] is False


def test_positive_control_a_better_and_no_worse_proposer_on_the_full_grid_is_claimed():
    d = _decide(field() + records("mind", BETTER))
    assert d["coverage_problems"] == [] and d["lift_claimed"] is True


def test_review_a_proposer_that_invalidates_world_sets_it_loses_gets_no_claim():
    mind = records("mind", BETTER)
    for r in mind[::3]:
        r["status"] = "INVALID_BENCHMARK"
    d = _decide(field() + mind)
    assert d["lift_claimed"] is False and any("not VALID" in p for p in d["coverage_problems"])


def test_review_missing_world_sets_and_non_isolated_runs_block_a_claim():
    part = analysis.formal_grid([f"c{i}" for i in range(30)], ("anonymous", "renamed"), (0, 1))
    d = _decide(field() + records("mind", BETTER, grid=part))
    assert d["lift_claimed"] is False and any("preregistered world sets" in p for p in d["coverage_problems"])
    d = _decide(field() + records("mind", BETTER, isolation="in_process"))
    assert d["lift_claimed"] is False and any("isolated" in p for p in d["coverage_problems"])


def test_review_an_incomplete_baseline_blocks_a_claim_instead_of_shrinking_the_comparison():
    careful = records("careful", CAREFUL)
    for r in careful[::5]:
        r["status"] = "INVALID_BENCHMARK"
    d = _decide(field(careful=careful) + records("mind", BETTER))
    assert d["lift_claimed"] is False and any(p.startswith("careful:") for p in d["coverage_problems"])


def test_review_paired_world_sets_must_hold_the_same_universes():
    mind = records("mind", BETTER)
    for r in mind[:10]:
        for u in r["universes"]:
            u["universe_id"] = "other-root-" + u["universe_id"]
    d = _decide(field() + mind)
    assert d["lift_claimed"] is False and any("different universes" in p for p in d["coverage_problems"])


def test_review_winning_three_presentations_while_losing_the_trap_is_refused():
    def lose_trap(p, c, s, k):
        if k == "discoverable":
            return -1.0 if p == "trap" else 1.0
        from tests.genesis_lite.lift_records import credit
        return credit(CAREFUL[k], int(c[1:]), s, k)
    d = _decide(field() + records("mind", CAREFUL, credit_fn=lose_trap))
    assert d["presentation_noninferiority"]["trap"] is False and d["lift_claimed"] is False


def test_review_noninferiority_uses_the_best_arm_on_each_kind():
    d = _decide(field(single_setting=dict(CAREFUL, confounded=1.0, discoverable=0.0)) + records("mind", BETTER))
    assert d["strongest_baseline"] == "careful"
    assert d["kind_noninferiority"]["confounded"]["reference_arm"] == "single_setting"
    assert d["kind_noninferiority"]["confounded"]["ok"] is False and d["lift_claimed"] is False


def test_review_roles_come_from_the_registry_and_strangers_are_refused():
    assert analysis.registered_roles()["always_law"] == "floor" and analysis.registered_roles()["careful"] == "competence"
    with pytest.raises(analysis.AnalysisRefused, match="unregistered"):
        _decide(field() + records("my_weak_baseline", CAREFUL) + records("mind", BETTER))


def test_review_a_duplicate_world_set_record_is_refused_not_overwritten():
    careful = records("careful", CAREFUL)
    with pytest.raises(analysis.AnalysisRefused, match="two VALID records"):
        _decide(field(careful=careful + careful[:1]) + records("mind", BETTER))


def test_review_missing_kinds_non_finite_and_off_table_credits_are_refused():
    def one():
        return records("careful", CAREFUL, grid=analysis.formal_grid(["c0"], ("anonymous",), (0,)))
    rec = one()
    rec[0]["universes"] = rec[0]["universes"][1:]
    with pytest.raises(analysis.AnalysisRefused, match="every kind"):
        analysis.world_credits(rec)
    rec = one()
    rec[0]["universes"][0]["credit"] = float("nan")
    with pytest.raises(analysis.AnalysisRefused, match="non-finite"):
        analysis.world_credits(rec)
    rec = one()
    rec[0]["universes"][0]["credit"] = 0.8
    with pytest.raises(analysis.AnalysisRefused, match="DEFAULT_CREDIT"):
        analysis.world_credits(rec)


def test_the_strongest_baseline_is_chosen_over_every_non_adversarial_arm_floors_included():
    credits = analysis.world_credits(records("careful", CAREFUL) + records("always_law", {k: 0.9 for k in KINDS})
                                     + records("historical_answer", {k: 1.0 for k in KINDS}))
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
