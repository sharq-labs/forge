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

KINDS = analysis.KINDS
PRESENTATIONS = ("anonymous", "renamed", "paraphrased", "trap")
CAMPAIGNS = [f"c{i}" for i in range(30)]
SEEDS = (0, 1)
GRID = analysis.formal_grid(CAMPAIGNS, PRESENTATIONS, SEEDS)
BASELINES = sorted(n for n, entry in arms.ARMS.items() if entry[3] in ("competence", "floor", "sanity"))
WEAK = {k: 0.3 for k in KINDS}
CAREFUL = dict(discoverable=0.3, **{k: 0.8 for k in KINDS if k != "discoverable"})
BETTER = dict(CAREFUL, discoverable=0.8)


def _credit(rate: float, i: int, s: int, kind: str) -> float:
    return 1.0 if (i * 7 + s * 3 + len(kind)) % 10 < round(rate * 10) else -1.0


def _records(arm, rates, *, grid=GRID, status="VALID", ids=True, id_prefix="", out_of_family=lambda ws: False,
             credit=None):
    out = []
    for p, c, s in sorted(grid):
        i = int(c[1:]) if c[1:].isdigit() else 0
        universes = []
        for k in KINDS:
            u = {"kind": k, "credit": credit(p, c, s, k) if credit else _credit(rates[k], i, s, k),
                 "independent_agrees": True, "truth_in_searched_family": not (k == "discoverable" and out_of_family((p, c, s)))}
            if ids:
                u["universe_id"] = f"{id_prefix}{p}-{s}-{c}-{k}"
            universes.append(u)
        out.append({"arm": arm, "status": status, "presentation": p, "campaign_id": c, "seed": s,
                    "isolation": "proposer_process", "universes": universes})
    return out


def _field(**override):
    """Every registered non-adversarial arm (weak), careful as the strongest, plus overrides (None drops an arm)."""
    rows = []
    for name in BASELINES:
        spec = override.get(name, CAREFUL if name == "careful" else WEAK)
        if spec is None:
            continue
        rows += spec if isinstance(spec, list) else _records(name, spec)
    return rows


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
    rows += _records("mind", CAREFUL, out_of_family=off, credit=mind_credit)
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
    rows = _field() + _records("mind", BETTER, credit=lambda p, c, s, k: 0.8)
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
