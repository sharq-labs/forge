import math
import random
from itertools import product

import pytest

from benchmarks.genesis_lite import analysis_v4 as a4
from benchmarks.genesis_lite.analysis import KINDS, AnalysisRefused
from benchmarks.genesis_lite.evaluator import score_v3

ROLES = {"careful": "competence", "grammar_enumeration": "competence", "space_filling": "competence",
         "always_refuse": "floor", "historical_answer": "adversarial"}
PRESENTATIONS = a4.PRESENTATIONS
GRID = frozenset((p, f"c{i}", s) for p in PRESENTATIONS for i in range(150) for s in (0, 1))   # 1200 world sets


def outcome_for(kind, credit):
    if credit == 0.0:                                        # an evaluator outcome the kind's table does not list
        return next(o for o in sorted(a4.OUTCOMES) if o != "indistinguishable_unresolved"
                    and o not in score_v3.v2.CREDIT[kind])
    for outcome, value in score_v3.v2.CREDIT[kind].items():
        if value == credit:
            return outcome
    raise AssertionError((kind, credit))


def record(arm, ws, credits, uid_prefix="u"):
    p, c, s = ws
    return {"arm": arm, "status": "VALID", "presentation": p, "campaign_id": c, "seed": s,
            "universes": [{"kind": k, "credit": float(credits[k]), "outcome": outcome_for(k, float(credits[k])),
                           "independent_agrees": True, "universe_id": f"{uid_prefix}-{p}-{c}-{s}-{k}",
                           "region_tell": "box"} for k in KINDS]}


BASE = {"confounded": 0.0, "discoverable": 0.0, "indistinguishable": 0.5, "insufficient_evidence": 1.0,
        "no_solution": 1.0, "spurious_correlate": 0.0}
FLOOR = {k: 0.0 for k in KINDS}


def field(baseline=BASE, grid=GRID, skip=()):
    rows = []
    for arm, role in ROLES.items():
        credits = FLOOR if role != "competence" else baseline
        rows += [record(arm, ws, credits) for ws in sorted(grid) if (arm, ws) not in skip]
    return rows


def everything_represented(grid=GRID):
    return {f"u-{p}-{c}-{s}-{k}": True for (p, c, s) in grid for k in a4.LAW_KINDS}


def candidate(credits, grid=GRID, name="mind"):
    return [record(name, ws, credits) for ws in sorted(grid)]


BETTER = {**BASE, "discoverable": 1.0, "spurious_correlate": 1.0}


# ----------------------------------------------------------------------------- the bound itself


def test_constant_differences_give_the_closed_form_bound():
    n, delta = 50, 0.05
    expected = 1.0 - 7 * 24 * math.log(2 / delta) / (3 * (n - 1))
    assert math.isclose(a4.bernstein_lower_bound([1.0] * n, delta, 24.0), expected)


@pytest.mark.parametrize("values", [[], [1.0], [float("nan"), 1.0], [float("inf"), 0.0], [-12.0, 12.1]])
def test_invalid_differences_refuse(values):
    with pytest.raises(AnalysisRefused):
        a4.bernstein_lower_bound(values, 0.05, 24.0)


@pytest.mark.parametrize("delta", [0.0, 1.0, -0.1, float("nan"), float("inf")])
def test_invalid_delta_refuses(delta):
    with pytest.raises(AnalysisRefused):
        a4.bernstein_lower_bound([0.0, 1.0], delta, 24.0)


def test_a_zero_mean_sample_is_never_significant_and_more_units_shrink_the_p_value():
    assert a4.bernstein_p_value([1.0, -1.0] * 500, 24.0) == 1.0
    small = a4.bernstein_p_value([1.0] * 100, 24.0)
    large = a4.bernstein_p_value([1.0] * 400, 24.0)
    assert large < small < 1.0


def test_the_p_value_matches_the_bound_at_its_own_level():
    xs = [1.5, 0.5, 1.0, 2.0] * 200
    p = a4.bernstein_p_value(xs, 24.0)
    assert 0 < p < 0.05
    assert a4.bernstein_lower_bound(xs, min(0.999, p * 1.001), 24.0) > 0
    assert a4.bernstein_lower_bound(xs, p * 0.999, 24.0) <= 0


def test_exact_two_point_null_enumeration_is_conservative():
    pvalues = [a4.bernstein_p_value(sample, 24.0) for sample in product((-12.0, 12.0), repeat=10)]
    for alpha in (0.01, 0.05, 0.10):
        assert sum(p <= alpha for p in pvalues) / len(pvalues) <= alpha


def test_a_skewed_mean_zero_null_keeps_the_nominal_level():
    # the null law the sign-flip test failed on (BLINDFOLD_V04_POWER_AND_INFERENCE_DRAFT.md §4)
    vals, w = [-6.0, 0.5, 1.0], [0.1, 0.4, 0.5]
    mu = sum(v * q for v, q in zip(vals, w))
    vals = [v - mu for v in vals]
    rng = random.Random(1)
    rejections = sum(a4.bernstein_p_value(rng.choices(vals, w, k=120), 24.0) <= 0.05 for _ in range(300))
    assert rejections <= 0.05 * 300


def test_clopper_pearson_known_values_and_refusals():
    assert math.isclose(a4.clopper_pearson_lower(10, 10), 0.05 ** (1 / 10), rel_tol=1e-9)
    assert a4.clopper_pearson_lower(0, 10) == 0.0
    assert a4.clopper_pearson_lower(5, 10) < 0.5
    for bad in ((11, 10), (-1, 10), (0, 0)):
        with pytest.raises(AnalysisRefused):
            a4.clopper_pearson_lower(*bad)


# ----------------------------------------------------------------------------- the decision contract


@pytest.mark.parametrize("multiplicity", a4.MULTIPLICITY)
def test_a_large_lift_on_represented_worlds_is_claimed(multiplicity):
    result = a4.decision(field() + candidate(BETTER), "mind", ROLES, everything_represented(), GRID,
                         multiplicity=multiplicity)
    assert result["coverage_problems"] == []
    assert result["lift_claimed"] is True


def test_equal_performance_is_never_a_lift():
    result = a4.decision(field() + candidate(BASE), "mind", ROLES, everything_represented(), GRID)
    assert result["lift_claimed"] is False


@pytest.mark.parametrize("kind", a4.LAW_KINDS)
def test_out_of_family_gain_in_any_law_kind_is_capped(kind):
    # FDA-06: a gain only where no baseline family represents the truth earns nothing (v0.2 capped discoverable only)
    gain = {**BASE, kind: 1.0}
    represented = everything_represented()
    for (p, c, s) in GRID:
        represented[f"u-{p}-{c}-{s}-{kind}"] = False
    capped = a4.decision(field() + candidate(gain), "mind", ROLES, represented, GRID, multiplicity="iut_all")
    assert capped["lift_claimed"] is False
    competence = [a for a, r in ROLES.items() if r == "competence"]
    assert all(capped["superiority"][a]["mean_difference"] <= 0 for a in competence)
    represented_ok = a4.decision(field() + candidate(gain), "mind", ROLES, everything_represented(), GRID,
                                 multiplicity="iut_all")
    assert all(t["mean_difference"] > 0 for t in represented_ok["superiority"].values())


def test_a_missing_representation_verdict_refuses():
    represented = everything_represented()
    represented.pop(next(iter(represented)))
    with pytest.raises(AnalysisRefused):
        a4.decision(field() + candidate(BETTER), "mind", ROLES, represented, GRID)


def test_removing_a_baseline_record_blocks_the_claim():
    ws = sorted(GRID)[0]
    result = a4.decision(field(skip={("careful", ws)}) + candidate(BETTER), "mind", ROLES, everything_represented(),
                         GRID)
    assert result["coverage_problems"]
    assert result["lift_claimed"] is False


def test_a_loss_on_a_control_kind_blocks_a_large_discovery_gain():
    # +3 on the law kinds, -1 on insufficient_evidence: superiority alone would hold
    trade = {**BETTER, "confounded": 1.0, "insufficient_evidence": 0.0}
    result = a4.decision(field() + candidate(trade), "mind", ROLES, everything_represented(), GRID,
                         multiplicity="iut_all")
    assert all(t["reject"] for t in result["superiority"].values())
    assert result["kind_noninferiority"]["insufficient_evidence"]["ok"] is False
    assert result["lift_claimed"] is False


def test_a_loss_in_one_presentation_blocks_the_claim():
    rows = field()
    # the trap presentation loses 2 per unit on the law kinds; pooled superiority and every kind still hold
    rows += [record("mind", ws, BETTER if ws[0] != "trap" else {**BASE, "discoverable": -1.0,
                                                                  "spurious_correlate": -1.0})
             for ws in sorted(GRID)]
    result = a4.decision(rows, "mind", ROLES, everything_represented(), GRID, multiplicity="iut_all")
    assert all(t["reject"] for t in result["superiority"].values())
    assert all(v["ok"] for v in result["kind_noninferiority"].values())
    assert result["presentation_noninferiority"]["trap"]["ok"] is False
    assert result["lift_claimed"] is False


def test_iut_compares_every_non_adversarial_arm():
    rows = field() + candidate(BETTER)
    result = a4.decision(rows, "mind", ROLES, everything_represented(), GRID, multiplicity="iut_all")
    assert set(result["superiority"]) == {a for a, r in ROLES.items() if r != "adversarial"}
    holm = a4.decision(rows, "mind", ROLES, everything_represented(), GRID, multiplicity="holm_family")
    assert set(holm["superiority"]) == set(a4.PRIMARY_FAMILY)


def test_a_record_whose_credit_disagrees_with_its_outcome_refuses():
    rows = field() + candidate(BETTER)
    rows[-1]["universes"][0]["outcome"] = "law_fail"
    with pytest.raises(AnalysisRefused):
        a4.decision(rows, "mind", ROLES, everything_represented(), GRID)


@pytest.mark.parametrize("outcome", ["no_credit", "", "LAW_PASS", "unknown"])
def test_an_outcome_outside_the_evaluator_vocabulary_refuses_instead_of_scoring_zero(outcome):
    # re-review M2: an unknown outcome at credit 0 would beat inadmissible (-1), so UNKNOWN would improve an arm
    with pytest.raises(AnalysisRefused, match="vocabulary"):
        a4.expected_credit("discoverable", outcome)
    rows = field() + candidate(BETTER)
    rows[0]["universes"][0].update(outcome=outcome, credit=0.0)
    with pytest.raises(AnalysisRefused, match="vocabulary"):
        a4.decision(rows, "mind", ROLES, everything_represented(), GRID)


def test_an_evaluator_refusal_the_kind_does_not_list_keeps_the_frozen_zero():
    assert a4.expected_credit("discoverable", "no_law") == 0.0          # EvaluatorConfig: unlisted outcomes score 0
    assert a4.OUTCOMES >= {o for table in score_v3.v2.CREDIT.values() for o in table}


def test_an_unresolved_pair_keeps_its_penalty_and_earns_no_recovery():
    assert a4.expected_credit("indistinguishable", "indistinguishable_unresolved") == 0.0
    assert a4.expected_credit("discoverable", "indistinguishable_unresolved") == -0.5


@pytest.mark.parametrize("defect", ["registered_name", "stranger", "independent_disagrees", "bad_multiplicity"])
def test_identity_and_authority_defects_refuse(defect):
    rows = field() + candidate(BETTER)
    name, mult = "mind", "holm_family"
    if defect == "registered_name":
        name = "careful"
    elif defect == "stranger":
        rows += [record("stranger", ws, BASE) for ws in sorted(GRID)[:1]]
    elif defect == "independent_disagrees":
        rows[-1]["universes"][0]["independent_agrees"] = False
    else:
        mult = "bonferroni"
    with pytest.raises(AnalysisRefused):
        a4.decision(rows, name, ROLES, everything_represented(), GRID, multiplicity=mult)


def test_strata_are_descriptive_and_separate_out_of_family_credit():
    represented = everything_represented()
    key = next(k for k in represented if k.endswith("-discoverable"))
    represented[key] = False
    out = a4.strata(field() + candidate(BETTER), represented)
    assert out["descriptive_only"] is True
    cells = out["arms"]["mind"]
    assert cells["representation:out_of_family|kind:discoverable"]["n"] == 1
    assert "region:box|kind:discoverable" in cells


# ----------------------------------------------------------------------------- review 2026-10-30


def test_noninferiority_is_tested_against_every_arm_not_a_data_chosen_one():
    # finding 2: careful and grammar tie on no_solution (mean 0); the candidate copies space_filling exactly, which a
    # single max-mean reference (ties broken by name) would pick; against careful its differences are +-2 per unit
    rows = []
    for i, ws in enumerate(sorted(GRID)):
        flip = 1.0 if i % 2 else -1.0
        for arm, role in ROLES.items():
            credits = dict(FLOOR) if role != "competence" else dict(BASE)
            if role == "competence":
                credits["no_solution"] = -flip if arm == "careful" else flip
            rows.append(record(arm, ws, credits))
        rows.append(record("mind", ws, {**BETTER, "no_solution": flip}))
    result = a4.decision(rows, "mind", ROLES, everything_represented(), GRID, multiplicity="iut_all")
    assert result["kind_noninferiority"]["no_solution"]["ok"] is False
    assert result["kind_noninferiority"]["no_solution"]["worst_arm"] == "careful"
    assert result["lift_claimed"] is False


@pytest.mark.parametrize("grid", [frozenset(w for w in GRID if w[0] != "trap"),
                                  GRID | {("upside_down", "c0", 0)}])
def test_a_grid_with_a_missing_or_unknown_presentation_refuses(grid):
    with pytest.raises(AnalysisRefused, match="presentations"):
        a4.decision(field(grid=grid) + candidate(BETTER, grid=grid), "mind", ROLES, everything_represented(grid), grid)


def test_the_representation_limited_cap_applies_inside_the_decision():
    # grammar earns full credit on every no_solution world: that cell measures the representation, so a candidate's
    # gain there (vs the floor arms) is capped at each comparator's credit and cannot help it
    assert ("no_solution", "anonymous") in a4.representation_limited({w: BASE for w in GRID if w[0] == "anonymous"})
