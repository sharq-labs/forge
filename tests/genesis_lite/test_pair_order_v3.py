"""Owner-approved symmetric distance; historical v2 remains unchanged."""
import pytest

from benchmarks.genesis_lite.evaluator.score_v3 import score_universe


def law(inside, outside):
    return {"piecewise": {"if_below": [{"var": "x"}, {"const": 2}],
                          "then": {"const": inside}, "else": {"const": outside}}}


@pytest.mark.parametrize("inside,outside,truth", [
    ((.99, 1.01), (1, 100), 1),
    ((-.99, -1.01), (-1, -100), -1),
    ((0, 0), (0, 1), 0),
    ((.98, 1.02), (1, 100), 1),
])
def test_pair_order_does_not_change_outcome_or_credit(inside, outside, truth):
    laws = [law(inside[i], outside[i]) for i in range(2)]
    entry = {"universe_id": "synthetic", "kind": "indistinguishable", "variables": ["x"],
             "tolerance": .02, "noise_sigma": .02, "box": {"x": [0, 1]},
             "inbox": [({"x": .5}, truth)], "evaluation": [({"x": 3}, truth)]}
    a = score_universe({"answer": "indistinguishable", "laws": laws}, entry)
    b = score_universe({"answer": "indistinguishable", "laws": laws[::-1]}, entry)
    assert (a["outcome"], a["credit"]) == (b["outcome"], b["credit"])


def test_inbox_threshold_passes_but_close_outside_pair_does_not_diverge():
    entry = {"universe_id": "synthetic", "kind": "indistinguishable", "variables": ["x"],
             "tolerance": .02, "noise_sigma": .02, "box": {"x": [0, 1]},
             "inbox": [({"x": .5}, 1)], "evaluation": [({"x": 3}, 1)]}
    for laws in ([law(1, .99), law(1, 1.01)], [law(1, 1.01), law(1, .99)]):
        assert score_universe({"answer": "indistinguishable", "laws": laws}, entry)["outcome"] == "indistinguishable_miss"


@pytest.mark.parametrize("a,b,expected", [(0., 0., 0.), (0., 1., 1.), (-1., 1., 2.), (1e308, -1e308, 2.)])
def test_distance_zero_sign_and_overflow(a, b, expected):
    from benchmarks.genesis_lite.evaluator.score_v3 import _pair_distance
    assert _pair_distance(a, b) == _pair_distance(b, a) == expected
