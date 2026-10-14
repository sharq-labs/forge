"""G0/A1 final review of Genesis-lite v0.1 (2026-10-14): reproducers for the confirmed lift-rule and pairing defects.

Every test builds a comparison in which a lift claim would be FALSE SUPPORT and asserts that none is made:

* D1 -- removing or invalidating a registered baseline's evidence must not weaken the comparison;
* D2 -- the world-set grid and the record set are preregistered, not chosen by the caller;
* D3 -- discovery must not be traded away for control credit (non-inferiority covers every kind);
* D4 -- a discoverable world whose truth lies outside every arm's searched family has no strong baseline: no lift there;
* D5 -- every compared arm is paired with the candidate by universe content, never skipped for a missing id;
* D6 -- a REPRESENTATION_LIMITED cell (preregistered rule) credits no lift as reasoning;
* D7 -- every arm sees the same stimulus for one world set; only the run-private pseudonym differs;
* credits are bound to the frozen DEFAULT_CREDIT table and to the independent evaluator's agreement;
* a candidate cannot run under a registered baseline's name.

The positive control shows that a genuinely better, no-worse candidate is still claimed under the same setup.
"""

from __future__ import annotations

import json

import pytest

from benchmarks.genesis_lite import analysis, arms, harness
from tests.genesis_lite.lift_records import (BASELINES, BETTER, CAMPAIGNS, CAREFUL, GRID, KINDS, PRESENTATIONS, SEEDS,
                                             WEAK, credit as _credit, field as _field, records as _records)


@pytest.fixture(autouse=True)
def _small_formal_grid(monkeypatch):
    """The preregistered grid is 30 x 4 x 20; these tests use 30 x 4 x 2 as the formal grid to stay fast."""
    monkeypatch.setattr(analysis, "FORMAL_GRID", GRID, raising=False)
    monkeypatch.setattr(analysis, "BOOTSTRAP", 400)


def _decide(rows, candidate="mind", grid=GRID):
    return analysis.lift_decision(rows, candidate, grid=grid)


def test_positive_control_a_better_no_worse_candidate_is_still_claimed():
    d = _decide(_field() + _records("mind", BETTER))
    assert d["coverage_problems"] == [] and d["strongest_baseline"] == "careful" and d["lift_claimed"] is True


def test_d1_an_invalidated_strongest_baseline_does_not_hand_the_candidate_a_weaker_comparator():
    rows = _field(space_filling=_records("space_filling", {k: 0.95 for k in KINDS}, status="INVALID_BENCHMARK"))
    assert _decide(rows + _records("mind", BETTER))["lift_claimed"] is False


def test_d1_an_omitted_registered_baseline_blocks_the_claim():
    assert _decide(_field(greedy_forward=None) + _records("mind", BETTER))["lift_claimed"] is False


def test_d2_a_caller_chosen_subgrid_is_not_the_preregistered_grid():
    sub = analysis.formal_grid(CAMPAIGNS, PRESENTATIONS, (0,))
    rows = [r for r in _field() + _records("mind", BETTER) if (r["presentation"], r["campaign_id"], r["seed"]) in sub]
    assert _decide(rows, grid=sub)["lift_claimed"] is False


def test_d2_records_outside_the_grid_block_the_claim_instead_of_steering_the_baseline():
    extra = _records("space_filling", WEAK, grid=analysis.formal_grid(["x1"], PRESENTATIONS, SEEDS))
    assert _decide(_field() + extra + _records("mind", BETTER))["lift_claimed"] is False


def test_d3_discovery_cannot_be_traded_for_control_credit():
    strong_discoverer = dict(CAREFUL, discoverable=0.9, confounded=0.2)
    trader = dict(CAREFUL, discoverable=0.3, confounded=1.0)
    rows = _field(space_filling=strong_discoverer)
    assert _decide(rows + _records("mind", trader))["lift_claimed"] is False


def test_d4_gains_only_on_worlds_outside_the_searched_family_are_not_lift():
    off = lambda ws: int(ws[1][1:]) % 2 == 0  # noqa: E731
    rows = [r for name in BASELINES
            for r in _records(name, CAREFUL if name == "careful" else WEAK, out_of_family=off)]

    def mind_credit(p, c, s, k):
        i = int(c[1:])
        if k == "discoverable" and off((p, c, s)):
            return 1.0                                          # the candidate "wins" only where no strong arm exists
        return _credit(CAREFUL[k], i, s, k)
    rows += _records("mind", CAREFUL, out_of_family=off, credit_fn=mind_credit)
    assert _decide(rows)["lift_claimed"] is False


def test_d5_a_candidate_without_universe_ids_is_not_paired_by_assumption():
    assert _decide(_field() + _records("mind", BETTER, ids=False))["lift_claimed"] is False


def test_d5_a_per_kind_reference_on_different_universes_blocks_the_claim():
    rows = _field(single_setting=_records("single_setting", WEAK, id_prefix="other-"))
    assert _decide(rows + _records("mind", BETTER))["lift_claimed"] is False


def test_d6_a_representation_limited_cell_credits_no_lift_as_reasoning():
    enumerator = dict(WEAK, no_solution=1.0)                  # the monomial representation alone solves no_solution
    careful = dict(CAREFUL, no_solution=0.3)
    rows = _field(monomial_enumeration=enumerator, careful=careful)
    assert _decide(rows + _records("mind", dict(careful, no_solution=1.0)))["lift_claimed"] is False


def test_credits_must_come_from_the_frozen_table():
    rows = _field() + _records("mind", BETTER, credit_fn=lambda p, c, s, k: 0.8)
    with pytest.raises(analysis.AnalysisRefused, match="DEFAULT_CREDIT"):
        _decide(rows)


def test_credits_the_independent_evaluator_did_not_agree_with_block_the_claim():
    mind = _records("mind", BETTER)
    mind[0]["universes"][0]["independent_agrees"] = False
    assert _decide(_field() + mind)["lift_claimed"] is False


def test_a_candidate_cannot_take_a_registered_baselines_name():
    rows = _field(space_filling=None) + _records("space_filling", BETTER)
    with pytest.raises(analysis.AnalysisRefused, match="registered"):
        _decide(rows, candidate="space_filling")


# ---- D7: stimulus pairing in the harness -----------------------------------------------------------------------------
MASTER = bytes(range(32))


@pytest.mark.parametrize("presentation", ["renamed", "paraphrased", "trap"])
def test_d7_two_arms_on_one_world_set_see_the_same_stimulus(monkeypatch, presentation):
    cards: dict[str, list] = {}

    def remember(tag):
        def arm(card, client, *, seed=0):
            cards.setdefault(tag, []).append(card)
            return {"universe_id": card["universe_id"], "answer": "no_law"}
        return arm

    for tag in ("arm_a", "arm_b"):
        monkeypatch.setitem(arms.ARMS, tag, (remember(tag), "t", False, "floor"))
        rec = harness.run_one(tag, arms.ARMS[tag][0], master_seed=MASTER, campaign_id="gl-test-7", presentation=presentation)
        assert rec.status == "VALID", rec.reasons
    strip = lambda cs: [json.dumps({k: v for k, v in c.items() if k != "universe_id"}, sort_keys=True) for c in cs]  # noqa: E731
    assert strip(cards["arm_a"]) == strip(cards["arm_b"])
    assert {c["universe_id"] for c in cards["arm_a"]}.isdisjoint(c["universe_id"] for c in cards["arm_b"])


# ---- v0.2 pilot finding (2026-10-14): an arm-independent screen invalidates a world set for every arm -----------------
from tests.genesis_lite.lift_records import SCREEN_REASON  # noqa: E402


def _screened(rows, ws, reason=SCREEN_REASON, arms_hit=None):
    for r in rows:
        if (r["presentation"], r["campaign_id"], r["seed"]) == ws and (arms_hit is None or r["arm"] in arms_hit):
            r["status"], r["reasons"] = "INVALID_BENCHMARK", [reason]
    return rows


def test_pilot_a_world_set_every_arm_lost_to_the_literal_screen_is_excluded_for_all_alike():
    rows = _screened(_field() + _records("mind", BETTER), ("paraphrased", "c3", 1))
    d = _decide(rows)
    assert d["screened_world_sets"] == 1 and d["coverage_problems"] == [] and d["lift_claimed"] is True


def test_pilot_a_screen_reason_on_the_candidate_alone_is_not_an_exclusion():
    rows = _screened(_field() + _records("mind", BETTER), ("paraphrased", "c3", 1), arms_hit={"mind"})
    assert _decide(rows)["lift_claimed"] is False


def test_pilot_different_screen_reasons_across_arms_are_not_an_exclusion():
    rows = _screened(_field() + _records("mind", BETTER), ("paraphrased", "c3", 1))
    next(r for r in rows if r["arm"] == "careful" and r["campaign_id"] == "c3" and r["seed"] == 1
         and r["presentation"] == "paraphrased")["reasons"] = ["leakage audit: something else"]
    assert _decide(rows)["lift_claimed"] is False


def test_pilot_an_arm_specific_failure_never_counts_as_a_screen():
    rows = _screened(_field() + _records("mind", BETTER), ("paraphrased", "c3", 1), reason="run aborted: TimeoutError")
    assert _decide(rows)["lift_claimed"] is False


def test_pilot_too_many_screened_world_sets_is_a_benchmark_defect_not_a_result():
    rows = _field() + _records("mind", BETTER)
    for i in range(15):                                        # 15 of 240 world sets = 6.25% > the 5% cap
        rows = _screened(rows, ("trap", f"c{i}", 0))
    d = _decide(rows)
    assert d["lift_claimed"] is False and any("screen" in p for p in d["coverage_problems"])


def test_review_records_from_another_benchmark_identity_are_not_analysed_as_this_one():
    mind = _records("mind", BETTER)
    for r in mind:
        r["prereg_sha256"] = "0" * 64
    assert _decide(_field() + mind)["lift_claimed"] is False


def test_review_a_credit_must_be_the_table_value_of_its_own_outcome():
    mind = _records("mind", BETTER)
    u = next(u for u in mind[0]["universes"] if u["credit"] == -1.0)
    u["credit"] = 1.0                                        # outcome still law_fail
    with pytest.raises(analysis.AnalysisRefused, match="outcome"):
        _decide(_field() + mind)
