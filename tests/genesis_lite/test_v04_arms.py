"""Genesis-lite v0.4 development arms: random_grammar (D14) and pysr_units (EXC-5). Fast checks; a campaign run with
PySR installed is part of the A1 development pilot, not this file."""

from __future__ import annotations

import ast
import importlib.util
import math
import pathlib

import numpy as np
import pytest

from benchmarks.genesis_lite import arms, arms_v4
from engcore.mind.grammar import enumerate_structures

from .test_v03_grammar_arm import CARD, World

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_the_registry_holds_two_new_competence_arms_and_no_edited_old_one():
    assert set(arms_v4.ARMS_V4) == {"random_grammar", "pysr_units"}
    for fn, family, stochastic, role in arms_v4.ARMS_V4.values():
        assert callable(fn) and family and stochastic and role == "competence"
    from benchmarks.genesis_lite.arms_v3 import ARMS_V3, PYSR_SETTINGS
    assert "pysr_units" not in ARMS_V3
    assert PYSR_SETTINGS["maxsize"] == 15                       # the registered pysr_symbolic arm is unchanged


def test_the_arms_read_no_hidden_or_harness_state():
    tree = ast.parse((ROOT / "benchmarks/genesis_lite/arms_v4.py").read_text(encoding="utf-8"))
    mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    banned = ("answer_key", "universe", "evaluator", "harness", "escrow", "presentation", "pilot")
    assert not [m for m in mods if any(b in m for b in banned)], mods


def test_random_grammar_draws_few_structures_from_the_same_grammar(monkeypatch):
    seen = {}
    real = arms_v4.select

    def spy(structures, L, z, **kw):
        seen["structures"], seen["z"], seen["generated"] = list(structures), np.array(z), kw["generated"]
        return real(structures, L, z, **kw)

    monkeypatch.setattr(arms_v4, "select", spy)
    out = arms_v4.random_grammar(CARD, World(), seed=3)
    assert out["answer"] in {"law", "insufficient_evidence", "no_law", "confounded"}
    every = {s.key for s in enumerate_structures(2)[0]}             # the capped set grammar_enumeration fits
    assert len(seen["structures"]) == arms_v4.RANDOM_DRAWS == seen["generated"]
    assert {s.key for s in seen["structures"]} <= every


def test_random_grammar_selects_on_the_training_split_only(monkeypatch):
    seen, collected = {}, {}
    real, real_gather = arms_v4.select, arms._gather

    def spy(structures, L, z, **kw):
        seen["n"] = len(z)
        return real(structures, L, z, **kw)

    def gather(card, client, rng, design, tag):
        rows, rep = real_gather(card, client, rng, design, tag)
        collected["rows"], collected["rep"] = rows, rep
        return rows, rep

    monkeypatch.setattr(arms_v4, "select", spy)
    monkeypatch.setattr(arms, "_gather", gather)
    arms_v4.random_grammar(CARD, World(), seed=0)
    train, hold, _, _ = arms._split(collected["rows"], collected["rep"])
    assert seen["n"] == len(train) and len(hold) > 0


def test_rerunning_the_same_universe_and_seed_cannot_restart_the_multiplicity_count():
    from engcore.claims.multiplicity import MultiplicityRefused
    arms_v4.random_grammar(CARD, World(), seed=11)
    with pytest.raises(MultiplicityRefused):
        arms_v4.random_grammar(CARD, World(), seed=11)


def test_si_unit_is_a_pure_renaming_and_refuses_undeclared_bases():
    assert arms_v4.si_unit("L^1*T^-1", ["L", "T"]) == "m^1*kg^-1"
    assert arms_v4.si_unit("1", ["L", "T"]) == "1"
    from engcore.mind.grammar import DimensionRefused
    with pytest.raises(DimensionRefused):
        arms_v4.si_unit("Q^1", ["L", "T"])


def test_dimension_check_accepts_logs_of_groups_and_rejects_logs_of_dimensional_inputs():
    sympy = pytest.importorskip("sympy")
    x0, x1 = sympy.symbols("x0 x1")
    dims = {"x0": (1, 0), "x1": (1, 0)}
    assert arms_v4._dimension(0.3 + 1.2 * sympy.log(x0 / x1), dims, 2) == (0.0, 0.0)
    assert arms_v4._dimension(0.3 + 1.2 * sympy.log(x0), dims, 2) is None


def test_a_translation_failure_raises_so_the_universe_scores_inadmissible():
    sympy = pytest.importorskip("sympy")
    x0 = sympy.symbols("x0")
    with pytest.raises(arms_v4.ArmFailure):
        arms_v4._log_space_law(sympy.sin(x0), {"x0": "a"})


def test_the_log_space_law_is_exp_of_the_equation():
    sympy = pytest.importorskip("sympy")
    from engcore.blindfold.expression import evaluate
    x0 = sympy.symbols("x0")
    law = arms_v4._log_space_law(0.5 + 2.0 * sympy.log(x0), {"x0": "a"})
    assert math.isclose(evaluate(law, {"a": 1.7}), math.exp(0.5) * 1.7 ** 2.0, rel_tol=1e-12)


@pytest.mark.skipif(importlib.util.find_spec("pysr") is not None, reason="PySR installed: the failure path needs it absent")
def test_a_missing_library_raises_instead_of_earning_a_refusal():
    with pytest.raises(arms_v4.ArmFailure):
        arms_v4.pysr_units(CARD, World(), seed=0)



class _Frame:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        return enumerate(self.rows)


def _fake_pysr(monkeypatch, front):
    """A stand-in ``pysr`` module: records what the arm passes to fit and returns ``front`` as the Pareto front."""
    import sys
    import types
    seen = {}

    class PySRRegressor:
        def __init__(self, **kw):
            seen["init"] = kw

        def fit(self, X, y, **kw):
            seen["fit"] = kw
            self.equations_ = _Frame([{"complexity": c, "sympy_format": s} for c, s in front])
            return self
    monkeypatch.setitem(sys.modules, "pysr", types.SimpleNamespace(PySRRegressor=PySRRegressor))
    return seen


@pytest.mark.parametrize("equation,consistent", [("0.5 + log(x0/x1)", True), ("1.0 + x0", False)])
def test_pysr_units_passes_dimensionless_ln_y_and_records_a_structured_consistency_flag(monkeypatch, equation,
                                                                                        consistent):
    # re-review L4, fix 7: y_units="1" (ln y is dimensionless) and a boolean flag that is never a scoring input
    pytest.importorskip("sympy")
    seen = _fake_pysr(monkeypatch, [(3, equation)])
    out = arms_v4.pysr_units(CARD, World(), seed=0)
    assert seen["fit"]["y_units"] == "1"
    assert seen["fit"]["X_units"] == [arms_v4.si_unit(x["unit"], CARD["base_dimensions"]) for x in CARD["inputs"]]
    assert out["dimensionally_consistent"] is consistent


def test_pysr_units_skips_non_finite_front_equations_and_fails_when_none_is_finite(monkeypatch):
    # re-review L4, fix 9: a non-finite equation is dropped, never raised; an all-non-finite front is a method failure
    pytest.importorskip("sympy")
    for bad in ("log(x0 - 100)", "1/(x0 - x0)"):          # nan on the rows; zoo, which numpy cannot even print
        _fake_pysr(monkeypatch, [(1, bad), (3, "0.5 + log(x0/x1)")])
        assert arms_v4.pysr_units(CARD, World(), seed=0)["dimensionally_consistent"] is True
    _fake_pysr(monkeypatch, [(1, "log(x0 - 100)"), (2, "1/(x0 - x0)")])
    with pytest.raises(arms_v4.ArmFailure, match="finite"):
        arms_v4.pysr_units(CARD, World(), seed=0)


def test_the_v04_identity_covers_every_file_that_decides_the_cap_and_the_verification():
    from benchmarks.genesis_lite.harness_v4 import SUBSTRATE_V4_FILES, V4_FILES
    assert {"reveal_v4.py", "expressibility_v3.py", "decide_v4.py", "analysis_v4.py", "isolated_host.py"} <= set(V4_FILES)
    assert "src/engcore/blindfold/isolation.py" in SUBSTRATE_V4_FILES


def _records_from_worlds(root, flip=False):
    from benchmarks.genesis_lite.evaluator import score_v3
    from benchmarks.genesis_lite.expressibility_v3 import worlds
    from benchmarks.genesis_lite.pilot_v4 import Task, campaign_id, master_seed
    task = Task("careful", 0, "anonymous", 0)
    cid = campaign_id("development", task)
    universes = [{"universe_id": w.universe_id, "kind": w.kind.value,
                  "truth_in_searched_family": (w.law is not None and score_v3.v2.in_monomial_family(w.law)) != flip}
                 for w in worlds(master_seed(root, task.campaign, task.presentation, task.seed), cid)]
    return [{"status": "VALID", "arm": task.arm, "campaign_id": cid,
             "task": {"campaign": 0, "presentation": "anonymous", "seed": 0}, "universes": universes}]


def test_the_reveal_recomputes_the_monomial_flag_from_the_world_not_the_record():
    # re-review L4, fix 8: records that agree with each other but not with the re-derived world refuse
    from benchmarks.genesis_lite.reveal_v4 import represented
    root = bytes(range(32))
    assert set(represented(_records_from_worlds(root), root)["represented"])
    with pytest.raises(ValueError, match="flag is not the world's"):
        represented(_records_from_worlds(root, flip=True), root)


def test_the_reveal_refuses_records_that_disagree_on_the_monomial_family():
    from benchmarks.genesis_lite.reveal_v4 import represented
    rec = {"status": "VALID", "arm": "a", "campaign_id": "gl-v04-development-0-0-anonymous",
           "task": {"campaign": 0, "presentation": "anonymous", "seed": 0},
           "universes": [{"universe_id": "u1", "kind": "discoverable", "truth_in_searched_family": True}]}
    other = {**rec, "arm": "b", "universes": [{**rec["universes"][0], "truth_in_searched_family": False}]}
    with pytest.raises(ValueError, match="disagree"):
        represented([rec, other], b"\x00" * 32)
