import pytest

from benchmarks.genesis_lite.evaluator import score as legacy
from benchmarks.genesis_lite.evaluator.score_v3 import score_universe, fraction_within


def entry(truth):
    return {"universe_id": "synthetic-zero", "kind": "discoverable", "variables": ["x"],
            "tolerance": .01, "evaluation": [({"x": 0}, truth)]}


@pytest.mark.parametrize("truth,prediction,passed", [(0., 0., True), (0., 1e-300, False),
    (1e-300, 0., False), (-2., -2., True), (-2., 2., False)])
def test_zero_and_signed_truths_have_explicit_accuracy(truth, prediction, passed):
    result = score_universe({"answer": "law", "law": {"const": prediction}}, entry(truth))
    assert (result["outcome"] == "law_pass") is passed


def test_historical_zero_result_stays_unchanged():
    assert legacy.score_universe({"answer": "law", "law": {"const": 0}}, entry(0))["outcome"] == "law_fail"


def test_mixed_zero_truths_count_in_denominator():
    truths = [({"x": 0}, 0)] * 9 + [({"x": 1}, 1)]
    assert fraction_within({"const": 0}, truths, .01) == .9


@pytest.mark.parametrize("truth", [None, float("nan"), float("inf")])
def test_unknown_truths_are_never_matches(truth):
    assert fraction_within({"const": 0}, [({"x": 0}, truth)], .01) == 0


def test_zero_inbox_does_not_veto_an_eligible_pair():
    a = {"piecewise": {"if_below": [{"var": "x"}, {"const": 1}],
                       "then": {"const": 0}, "else": {"const": 1}}}
    b = {"piecewise": {"if_below": [{"var": "x"}, {"const": 1}],
                       "then": {"const": 0}, "else": {"const": 2}}}
    task = {**entry(1), "kind": "indistinguishable", "noise_sigma": .01,
            "box": {"x": [0, .5]}, "inbox": [({"x": 0}, 0)], "evaluation": [({"x": 2}, 1)]}
    assert score_universe({"answer": "indistinguishable", "laws": [a, b]}, task)["outcome"] == "indistinguishable_hit"
