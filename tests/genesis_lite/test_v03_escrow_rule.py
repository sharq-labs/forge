"""Owner decision 2026-10-29 (option B): the v0.3 escrow applies the five v0.3 pair/fraction rules in a NEW file
(``engcore.blindfold.escrow_v3``); the pinned v0.2 ``escrow.py`` is untouched. The escrow's facts and the independent v0.3
evaluator (``score_v3``) must agree by construction:

1. in-box agreement and 2. outside divergence use |a-b|/max(|a|,|b|) (symmetric, zero for two zeros);
3. bracketing uses lo-tol|lo| .. hi+tol|hi|; 4. outside divergence counts points whatever their truth;
5. an exact zero prediction of a zero truth is within tolerance.
"""

from __future__ import annotations

import math
import random
import types

import pytest

from benchmarks.genesis_lite import harness as h2
from benchmarks.genesis_lite.evaluator import score_v3
from engcore.blindfold import escrow as escrow_v2
from engcore.blindfold.expression import c, mul, pw, v


def _world(tol=0.05, sigma=0.05, box=(1.0, 2.0)):
    return types.SimpleNamespace(tolerance=tol, noise_sigma=sigma,
                                 inputs=(types.SimpleNamespace(name="x", low=box[0], high=box[1]),))


def _entry(w, inbox, truths):
    x = w.inputs[0]
    return {"tolerance": w.tolerance, "noise_sigma": w.noise_sigma, "inbox": inbox, "evaluation": truths,
            "box": {"x": [x.low, x.high]}}


def _outcome(pair):
    if pair["hit"] and pair["contains_truth"]:
        return "indistinguishable_hit"
    return "indistinguishable_unresolved" if pair["hit"] else "indistinguishable_miss"


def test_the_pinned_v0_2_escrow_is_untouched():
    assert h2.code_identity()[1] == []


def test_pair_facts_do_not_depend_on_the_order_of_the_two_laws():
    from engcore.blindfold.escrow_v3 import assess_pair_v3
    w = _world(sigma=0.095)
    a, b = c(1.10), c(1.00)
    inbox = [({"x": 1.5}, 1.05)]
    truths = [({"x": 1.2}, 1.05), ({"x": 4.0}, 1.05)]
    assert assess_pair_v3([a, b], truths, inbox, w) == assess_pair_v3([b, a], truths, inbox, w)
    # the v0.2 rule is order-dependent on the same case (kept as it was; documented, not used by v0.3)
    assert escrow_v2._assess_pair([a, b], truths, inbox, w)["mutual_in_box"] != \
        escrow_v2._assess_pair([b, a], truths, inbox, w)["mutual_in_box"]


def test_negative_values_are_bracketed_with_sign_correct_bounds():
    from engcore.blindfold.escrow_v3 import assess_pair_v3
    w = _world()
    a, b = c(-1.0), c(-2.0)
    truths = [({"x": 1.5}, -0.97), ({"x": 4.0}, -0.97)]
    assert assess_pair_v3([a, b], truths, [({"x": 1.5}, -0.97)], w)["brackets_truth"] is True
    assert escrow_v2._assess_pair([a, b], truths, [({"x": 1.5}, -0.97)], w)["brackets_truth"] is False


def test_an_exact_zero_prediction_of_a_zero_truth_is_within_tolerance():
    from engcore.blindfold.escrow_v3 import fraction_v3
    truths = [({"x": 1.5}, 0.0), ({"x": 1.7}, 0.0)]
    assert fraction_v3(c(0.0), truths, 0.05) == score_v3.fraction_within(c(0.0), truths, 0.05) == 1.0
    assert fraction_v3(c(1e-9), truths, 0.05) == 0.0


def test_outside_divergence_counts_points_whatever_their_truth():
    from engcore.blindfold.escrow_v3 import assess_pair_v3
    w = _world()
    a, b = pw(v("x"), 1.0), pw(v("x"), 2.0)
    truths = [({"x": 4.0}, float("nan")), ({"x": 5.0}, float("nan"))]
    assert assess_pair_v3([a, b], truths, [({"x": 1.0}, 1.0)], w)["differ_fraction_outside"] == 1.0


def test_a_law_undefined_somewhere_is_non_finite_not_a_crash():
    from engcore.blindfold.escrow_v3 import assess_pair_v3, fraction_v3
    log_law = {"log": v("x")}
    truths = [({"x": -1.0}, 1.0), ({"x": 1.5}, 0.4)]
    assert fraction_v3(log_law, truths, 0.05) == score_v3.fraction_within(log_law, truths, 0.05)
    assert assess_pair_v3([log_law, c(1.0)], truths, [({"x": 1.5}, 0.4)], _world())["finite"] is False


def _random_case(rng):
    w = _world(tol=rng.choice([0.02, 0.05, 0.1]), sigma=rng.choice([0.01, 0.05, 0.1]))
    e1 = rng.uniform(0.3, 2.0)
    d = rng.choice([0.0, 0.01, 0.05, 0.3]) * rng.choice([-1, 1])
    k = rng.choice([1.0, -1.0, 0.0, rng.uniform(0.2, 3.0)])
    a = mul(c(k), pw(v("x"), e1))
    b = mul(c(k * (1 + rng.choice([0.0, 0.01, 0.2]))), pw(v("x"), e1 + d))
    t = rng.choice([0.0, 0.5, 1.0, -0.5, 1.5, rng.uniform(-1, 2)])
    truth = mul(c(k), pw(v("x"), e1 + t * d))

    def at(x):
        val = score_v3.v2.value(truth, {"x": x})
        return rng.choice([val, val, val, val, float("nan"), 0.0]) if rng.random() < 0.15 else val

    inbox = [({"x": x}, at(x)) for x in (rng.uniform(1.0, 2.0) for _ in range(rng.randint(1, 5)))]
    truths = [({"x": x}, at(x)) for x in [rng.uniform(1.0, 2.0) for _ in range(3)] + [rng.uniform(2.5, 8.0) for _ in range(4)]]
    return [a, b], inbox, truths, w


def test_the_v3_escrow_and_the_independent_v3_evaluator_agree_on_random_and_edge_cases():
    from engcore.blindfold.escrow_v3 import assess_pair_v3, fraction_v3
    rng = random.Random(20261029)
    seen = set()
    for _ in range(1500):
        laws, inbox, truths, w = _random_case(rng)
        pair = assess_pair_v3(laws, truths, inbox, w)
        mine = score_v3._pair_outcome(laws, _entry(w, inbox, truths))
        assert _outcome(pair) == mine, (laws, inbox, truths, pair)
        for law in laws:
            assert fraction_v3(law, truths, w.tolerance) == score_v3.fraction_within(law, truths, w.tolerance)
        seen.add(mine)
    assert seen == {"indistinguishable_hit", "indistinguishable_unresolved", "indistinguishable_miss"}


def test_the_v3_development_path_scores_on_the_v3_escrow():
    from benchmarks.genesis_lite import arms
    from benchmarks.genesis_lite.harness_v3 import SUBSTRATE_V3_FILES, run_one_v3
    assert "src/engcore/blindfold/escrow_v3.py" in SUBSTRATE_V3_FILES
    rec = run_one_v3("extrapolation_pair", arms.ARMS["extrapolation_pair"][0], master_seed=(3).to_bytes(4, "big") * 8,
                     campaign_id="gl-v03-rule", presentation="anonymous")
    assert rec.status == "VALID" and rec.evaluator_status == "VALID", rec.reasons
    assert rec.escrow_rule == "v0_3"
    assert h2.code_identity()[1] == []
