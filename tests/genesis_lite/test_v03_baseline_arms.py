"""Genesis-lite v0.3 development baselines: PySR, PySINDy and BoTorch arms (owner-approved 2026-10-28).

Fast checks only: the registry, the honest availability report and PySR's translation into the escrow's expression
grammar. Running each arm through a campaign is in test_v03_baseline_arms_e2e.py (expensive tier).
"""

from __future__ import annotations

import importlib.util
import math

import pytest

from engcore.blindfold.expression import evaluate, validate


def test_the_registry_names_the_three_strongest_traditional_methods():
    from benchmarks.genesis_lite.arms_v3 import ARMS_V3
    assert set(ARMS_V3) == {"pysr_symbolic", "pysindy_stlsq", "bo_botorch_variance"}
    for fn, family, stochastic, role in ARMS_V3.values():
        assert callable(fn) and family and role == "competence"


def test_availability_reports_what_is_installed_and_never_substitutes():
    from benchmarks.genesis_lite.arms_v3 import availability_v3
    report = availability_v3()
    for name, module in (("pysr_symbolic", "pysr"), ("pysindy_stlsq", "pysindy"), ("bo_botorch_variance", "botorch")):
        installed = importlib.util.find_spec(module) is not None
        assert report[name]["status"] == ("AVAILABLE_DEVELOPMENT" if installed else "NOT_AVAILABLE")


def test_pysr_output_translates_into_the_escrow_grammar():
    sympy = pytest.importorskip("sympy")
    from benchmarks.genesis_lite.arms_v3 import to_grammar
    x0, x1 = sympy.symbols("x0 x1")
    expr = 2.5 * x0 ** 1.5 / x1 - sympy.exp(-x1) + sympy.log(x0)
    law = to_grammar(expr, {"x0": "speed", "x1": "mass"})
    assert validate(law) == {"speed", "mass"}
    point = {"speed": 1.7, "mass": 0.8}
    expected = 2.5 * 1.7 ** 1.5 / 0.8 - math.exp(-0.8) + math.log(1.7)
    assert math.isclose(evaluate(law, point), expected, rel_tol=1e-12)


@pytest.mark.parametrize("make", [lambda s, x: s.sin(x), lambda s, x: x ** x, lambda s, x: s.Abs(x)])
def test_operations_outside_the_grammar_are_refused_not_approximated(make):
    sympy = pytest.importorskip("sympy")
    from benchmarks.genesis_lite.arms_v3 import GrammarRefused, to_grammar
    x0 = sympy.symbols("x0")
    with pytest.raises(GrammarRefused):
        to_grammar(make(sympy, x0), {"x0": "speed"})
