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


# ---- review round 1 (2026-10-28) ----------------------------------------------------------------------------------------
def test_a_bo_candidate_on_the_box_edge_maps_to_a_setting_inside_the_range():
    from benchmarks.genesis_lite.arms_v3 import to_setting
    x = {"name": "q", "range": [0.1, 10.0]}
    assert to_setting(1.0, x) == 10.0 and to_setting(0.0, x) == 0.1
    assert 0.1 <= to_setting(0.37, x) <= 10.0


def test_a_library_failure_is_inadmissible_never_a_credited_refusal(monkeypatch):
    import sys
    from benchmarks.genesis_lite.arms_v3 import ARMS_V3
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    monkeypatch.setitem(sys.modules, "pysindy", None)               # importing it now fails, installed or not
    monkeypatch.setitem(sys.modules, "pysindy.optimizers", None)
    rec = run_one_v3("pysindy_stlsq", ARMS_V3["pysindy_stlsq"][0], master_seed=(11).to_bytes(4, "big") * 8,
                     campaign_id="gl-v03-libfail", presentation="anonymous")
    assert rec.status == "VALID", rec.reasons
    fitted = [u for u in rec.universes if u["answer"] != "insufficient_evidence" or "PySINDy" in u["rationale"]]
    assert fitted and all(u["answer"] == "inadmissible" for u in fitted if "too few" not in u["rationale"]
                          and "outside the query box" not in u["rationale"])
    assert not any("failed" in u["rationale"] and u["answer"] == "insufficient_evidence" for u in rec.universes)


def test_the_run_identity_binds_the_arms_and_library_versions():
    from benchmarks.genesis_lite import arms
    from benchmarks.genesis_lite.harness_v3 import V3_FILES, run_one_v3
    assert "arms_v3.py" in V3_FILES
    rec = run_one_v3("always_refuse", arms.ARMS["always_refuse"][0], master_seed=bytes(range(32)),
                     campaign_id="gl-v03-ident", presentation="anonymous")
    assert {"numpy", "pysr", "pysindy", "botorch", "torch"} <= set(rec.library_versions)
    assert all("rationale" in u for u in rec.universes)
    assert rec.v3_total_credit == sum(u["credit"] for u in rec.universes)


def test_run_one_v3_refuses_when_the_pinned_v0_2_code_drifted(monkeypatch):
    from benchmarks.genesis_lite import arms, harness as h2
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    monkeypatch.setattr(h2, "code_identity", lambda: ("x" * 64, ["src/engcore/blindfold/escrow.py"]))
    rec = run_one_v3("always_refuse", arms.ARMS["always_refuse"][0], master_seed=bytes(range(32)),
                     campaign_id="gl-v03-drift", presentation="anonymous")
    assert rec.status == "INVALID_BENCHMARK" and rec.development_identity == ""
