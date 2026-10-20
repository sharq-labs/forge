"""Evaluator-versus-escrow agreement on fixed synthetic worlds (the R-05 construction; no pilot or formal world).

For every (pair, truth, bound) case, the escrow's bounded pair assessment (``engcore.blindfold.pair_bound``) and the
v0.3 evaluator's :func:`~benchmarks.genesis_lite.v0_3.evaluator.pair_hit` must return the same hit. The unbounded
assessments (v0.2 rule) must agree as well. Used by the readiness gate and by the escrow-half tests.
"""

from __future__ import annotations

from typing import Any

from ..evaluator.expr import value
from ..evaluator.score import _pair_hit
from . import evaluator as v03e

TOL, SIGMA = 0.05, 0.01
EVAL_PTS = [{"x": 1.0 + 3.0 * (i + 0.5) / 60} for i in range(60)]
INBOX_PTS = [{"x": 1.0 + (i + 0.5) / 20} for i in range(20)]


def _c(k: float) -> dict:
    return {"const": k}


def _mul(*a: Any) -> dict:
    return {"mul": list(a)}


def _add(*a: Any) -> dict:
    return {"add": list(a)}


def _pw(b: Any, e: float) -> dict:
    return {"pow": [b, _c(e)]}


X = {"var": "x"}
HALF_X = _mul(X, _c(0.5))
BASE = _mul(_c(3.0), _pw(X, 1.5))
GROW8 = _add(_c(1.0), _mul(_c(0.005), _pw(HALF_X, 8)))
T_UP, T_DOWN = _mul(BASE, GROW8), _mul(BASE, _pw(GROW8, -1))
FIT = _mul(_c(3.02), _pw(X, 1.5))


def _spread(base: dict, k: float, m: float) -> list[dict]:
    grow = _add(_c(1.0), _mul(_c(k), _pw(HALF_X, m)))
    return [_mul(base, grow), _mul(base, _pw(grow, -1))]


def _narrow(spread: float) -> list[dict]:
    s = _pw(HALF_X, 400)
    grow = _add(_c(1.0), _mul(_c(spread), s, _pw(_add(_c(1.0), s), -1)))
    return [_mul(T_UP, grow), _mul(T_UP, _pw(grow, -1))]


PAIRS = {"vacuous": _spread(FIT, 1e-3, 60), "honest": [T_UP, T_DOWN], "narrow_0.1": _narrow(0.1),
         "inbox_disagree": _spread(FIT, 5e-2, 1)}
BOUNDS = [("tol_multiple", 0.5), ("tol_multiple", 3.0), ("tol_multiple", 5.0), ("absolute", 0.15), ("absolute", 0.25),
          ("absolute", 1e6)]                       # tol_multiple 3.0 is the owner's w (D1, 2026-10-20)


def _world(truth: dict, alternative: dict) -> Any:
    from engcore.blindfold.universe import HiddenWorld, UniverseKind, Variable  # noqa: PLC0415

    return HiddenWorld(universe_id="selfcheck", kind=UniverseKind.INDISTINGUISHABLE, base_dimensions=("L",),
                       inputs=(Variable("x", (1,), 1.0, 2.0),), output="y", output_dimension=(1,), law=truth,
                       alternative_law=alternative, noise_sigma=SIGMA, assessment_region={"x": (1.0, 4.0)},
                       evaluation_points=tuple(EVAL_PTS), inbox_points=tuple(INBOX_PTS), tolerance=TOL)


def compare(pair_bound: Any) -> list[dict[str, Any]]:
    """Every case with both verdicts; ``agree`` is True only when bounded AND unbounded hits match."""
    out = []
    for truth_name, truth, alternative in (("T_up", T_UP, T_DOWN), ("T_down", T_DOWN, T_UP)):
        truths = [(p, value(truth, p)) for p in EVAL_PTS]
        inbox = [(p, value(truth, p)) for p in INBOX_PTS]
        entry = {"tolerance": TOL, "noise_sigma": SIGMA, "box": {"x": [1.0, 2.0]}, "evaluation": truths, "inbox": inbox}
        world = _world(truth, alternative)
        for pair_name, laws in PAIRS.items():
            for form, w in BOUNDS:
                escrow = pair_bound.assess_pair_bounded(laws, truths, inbox, world, pair_bound.PairBound(form, w))
                mine = v03e.pair_hit(laws, entry, v03e.PairBound(form, w))
                unbounded = _pair_hit(laws, entry)
                out.append({"truth": truth_name, "pair": pair_name, "bound": [form, w], "escrow_hit": escrow["hit"],
                            "evaluator_hit": mine, "escrow_unbounded_hit": escrow["unbounded_hit"],
                            "evaluator_unbounded_hit": unbounded,
                            "agree": escrow["hit"] == mine and escrow["unbounded_hit"] == unbounded})
    return out
