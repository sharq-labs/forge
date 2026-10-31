"""FDA-05 development fixtures only; no generator, hidden roots or final data."""

import pytest

from benchmarks.genesis_lite.evaluator import score as legacy
from benchmarks.genesis_lite.evaluator.score_v3 import score_universe


def law(outside):
    return {"piecewise": {"if_below": [{"var": "x"}, {"const": 2}],
                          "then": {"const": 1}, "else": {"const": outside}}}


def entry(truth=10, *, passing_points=None):
    truths = [truth] * 10 if passing_points is None else [1] * passing_points + [10] * (10 - passing_points)
    return {"universe_id": "synthetic-fda05", "kind": "indistinguishable", "variables": ["x"],
            "tolerance": .01, "noise_sigma": .01, "box": {"x": [0, 1]},
            "inbox": [({"x": .25}, 1), ({"x": .75}, 1)],
            "evaluation": [({"x": 3 + i}, t) for i, t in enumerate(truths)]}


def proposal(a=1, b=1000):
    return {"answer": "indistinguishable", "laws": [law(a), law(b)]}


@pytest.mark.parametrize("truth", [10, 100])
def test_bracketing_two_incompatible_truths_is_not_recovery(truth):
    result = score_universe(proposal(), entry(truth))
    assert result["outcome"] == "indistinguishable_unresolved"
    assert result["credit"] == 0
    assert result["fractions"] == [0, 0]


@pytest.mark.parametrize("passing_points,hit", [(9, True), (8, False), (10, True)])
def test_existing_pass_fraction_is_not_widened(passing_points, hit):
    result = score_universe(proposal(), entry(passing_points=passing_points))
    assert (result["outcome"] == "indistinguishable_hit") is hit


@pytest.mark.parametrize("defect", ["no_outside", "inbox_misfit", "nonfinite"])
def test_one_accurate_law_does_not_bypass_pair_eligibility(defect):
    task, answer = entry(1), proposal()
    if defect == "no_outside":
        task["box"] = {"x": [0, 20]}
    elif defect == "inbox_misfit":
        answer["laws"][1] = {"const": 1000}
    else:
        answer["laws"][1] = {"log": {"const": -1}}
    assert score_universe(answer, task)["outcome"] == "indistinguishable_miss"


@pytest.mark.parametrize("answer", [{"answer": "law", "law": law(10)},
                                    {"answer": "law", "law": law(3)},
                                    {"answer": "insufficient_evidence"}])
def test_single_laws_and_refusals_keep_existing_scores(answer):
    result = score_universe(answer, entry())
    old = legacy.score_universe(answer, entry())
    for field in ("outcome", "credit", "fractions"):
        assert result[field] == old[field]


def test_historical_rule_remains_explicitly_different():
    assert legacy.score_universe(proposal(), entry())["outcome"] == "indistinguishable_hit"


@pytest.mark.parametrize("kind", list(legacy.CREDIT))
def test_unresolved_pair_never_erases_existing_control_penalties(kind):
    task = {**entry(), "kind": kind}
    old = legacy.score_universe(proposal(), task)
    result = score_universe(proposal(), task)
    assert result["outcome"] == "indistinguishable_unresolved"
    assert result["credit"] == min(0, old["credit"])


@pytest.mark.parametrize("kind", list(legacy.CREDIT))
@pytest.mark.parametrize("truth", [1, 1000])
def test_either_accurate_pair_member_keeps_existing_credit_in_every_kind(kind, truth):
    task = {**entry(truth), "kind": kind}
    old = legacy.score_universe(proposal(), task)
    result = score_universe(proposal(), task)
    assert result["outcome"] == old["outcome"] == "indistinguishable_hit"
    assert result["credit"] == old["credit"]


def test_invalid_expression_is_still_refused():
    with pytest.raises(legacy.EvaluatorRefused):
        score_universe({"answer": "indistinguishable", "laws": [{"var": "secret"}, law(1)]}, entry())


def test_new_score_cannot_masquerade_as_frozen_v2():
    result = score_universe(proposal(), entry())
    assert result["benchmark_id"] == "genesis_lite.blindfold_l5.v0_3"
    assert result["schema"] != legacy.EVALUATOR_SCHEMA
    assert result["readiness"] == "DEVELOPMENT_ONLY"
