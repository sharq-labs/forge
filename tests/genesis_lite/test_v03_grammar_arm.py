"""EXC-4: the grammar_enumeration development baseline -- registration, identity, data roles, refusals, one campaign."""

from __future__ import annotations

import ast
import math
import pathlib

import numpy as np
import pytest

from benchmarks.genesis_lite import arms, arms_grammar_v3, pilot_v3

ROOT = pathlib.Path(__file__).resolve().parents[2]
CARD = {"universe_id": "u-g", "level": "L5", "base_dimensions": ["L", "T"],
        "inputs": [{"name": "a", "unit": "L^1", "settable": True, "range": [0.5, 2.0]},
                   {"name": "b", "unit": "L^1", "settable": True, "range": [1.0, 3.0]},
                   {"name": "c", "unit": "T^-1", "settable": True, "range": [0.2, 4.0]}],
        "observed_covariates": ["w"], "covariate_units": {"w": "1"}, "output": {"name": "y", "unit": "L^1*T^-1"},
        "assessment_region": {"a": [0.5, 2.0], "b": [1.0, 3.0], "c": [0.2, 4.0]}, "query_budget": 40, "query_cost": 1.0,
        "answers": ["law", "no_law", "insufficient_evidence", "indistinguishable", "confounded"]}


class World:
    """y = 1.7 a c (a/b)^0.6, multiplicative noise; a passive covariate w."""

    def __init__(self, law=None, noise=0.005):
        self.rng = np.random.default_rng(0)
        self.law = law or (lambda s: 1.7 * s["a"] * s["c"] * (s["a"] / s["b"]) ** 0.6)
        self.noise = noise
        self.calls = 0

    def observe(self, uid, settings, query_id=""):
        self.calls += 1
        y = self.law(settings) * math.exp(self.rng.normal() * self.noise)
        return {"observation": {**settings, "w": float(math.exp(self.rng.normal() * 0.3)), "y": y}}


def test_the_arm_is_registered_available_and_a_baseline():
    assert "grammar_enumeration" in pilot_v3.all_arms() and pilot_v3.arm_available("grammar_enumeration")
    assert pilot_v3.proposer_kind("grammar_enumeration") == "baseline"
    assert pilot_v3._arm("grammar_enumeration") is arms_grammar_v3.grammar_enumeration


def test_the_arm_and_the_grammar_code_are_bound_into_the_development_identity():
    from benchmarks.genesis_lite.harness_v3 import SUBSTRATE_V3_FILES, V3_FILES
    assert "arms_grammar_v3.py" in V3_FILES
    assert {f"src/engcore/mind/grammar/{m}.py" for m in ("__init__", "dimensions", "grammar", "fit", "evidence")} \
        <= set(SUBSTRATE_V3_FILES)
    assert "src/engcore/mind/minimal/runner.py" in SUBSTRATE_V3_FILES          # EXC-2's binding is kept


def test_the_arm_reads_no_hidden_or_harness_state():
    tree = ast.parse((ROOT / "benchmarks/genesis_lite/arms_grammar_v3.py").read_text(encoding="utf-8"))
    mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    banned = ("answer_key", "universe", "evaluator", "harness", "escrow", "presentation", "pilot")
    assert not [m for m in mods if any(b in m for b in banned)], mods


def test_selection_sees_the_training_split_only(monkeypatch):
    """The structure is chosen on training rows; the hold-out reaches only the gate (lessons: selection leak)."""
    seen = {}
    real = arms_grammar_v3.select

    def spy(structures, L, z, **kw):
        seen["z"] = np.array(z)
        return real(structures, L, z, **kw)

    collected = {}
    real_gather = arms._gather

    def gather(card, client, rng, design, tag):
        rows, rep = real_gather(card, client, rng, design, tag)
        collected["rows"], collected["rep"] = rows, rep
        return rows, rep

    monkeypatch.setattr(arms_grammar_v3, "select", spy)
    monkeypatch.setattr(arms, "_gather", gather)
    out = arms_grammar_v3.grammar_enumeration(CARD, World(), seed=0)
    train, hold, _, _ = arms._split(collected["rows"], collected["rep"])
    basis = arms_grammar_v3.analyse([arms_grammar_v3.InputDimension(x["name"], x["unit"], *x["range"])
                                     for x in CARD["inputs"]], CARD["output"]["unit"], CARD["base_dimensions"])
    _, z_train = arms_grammar_v3.design_matrix(basis, train, "y")
    assert len(hold) >= 3 and len(seen["z"]) == len(train)
    assert np.array_equal(seen["z"], z_train)
    assert out["answer"] == "law", out["rationale"]


def test_a_power_law_world_gives_a_law_that_predicts_held_out_points():
    world = World()
    out = arms_grammar_v3.grammar_enumeration(CARD, world, seed=1)
    assert out["answer"] == "law", out["rationale"]
    from engcore.blindfold.expression import evaluate
    for pt in ({"a": 0.7, "b": 2.5, "c": 3.1}, {"a": 1.9, "b": 1.1, "c": 0.3}):
        assert math.isclose(evaluate(out["law"], pt), world.law(pt), rel_tol=0.03)


def test_a_non_positive_output_refuses_and_never_drops_rows():
    out = arms_grammar_v3.grammar_enumeration(CARD, World(law=lambda s: s["a"] - 1.0), seed=0)
    assert out["answer"] == "insufficient_evidence" and "non-positive" in out["rationale"] and "law" not in out


@pytest.mark.parametrize("unit", ["L", "M^1", "L^0.5"])
def test_units_that_cannot_be_analysed_refuse(unit):
    card = {**CARD, "inputs": [{**CARD["inputs"][0], "unit": unit}, *CARD["inputs"][1:]]}
    out = arms_grammar_v3.grammar_enumeration(card, World(), seed=0)
    assert out["answer"] == "insufficient_evidence" and "dimensional analysis refused" in out["rationale"]


def test_an_output_dimension_the_inputs_cannot_carry_refuses():
    card = {**CARD, "output": {"name": "y", "unit": "T^1*L^5"}, "inputs": CARD["inputs"][:2]}
    out = arms_grammar_v3.grammar_enumeration(card, World(law=lambda s: s["a"]), seed=0)
    assert out["answer"] == "insufficient_evidence" and "dimensional analysis refused" in out["rationale"]


# ---- review 2026-10-30 (forge-scientific-review: CHANGES REQUIRED) ------------------------------------------------------
def test_h1_a_noisy_world_fails_the_precision_bar_as_careful_does():
    """The free-form gate alone would accept a law whose hold-out RMS is near a large noise; the arm keeps
    ``arms._gate``'s precision bar, so it refuses where ``careful`` refuses."""
    from engcore.blindfold import baselines as bf
    card = {**CARD, "universe_id": "u-noisy"}
    out = arms_grammar_v3.grammar_enumeration(card, World(noise=0.4), seed=3)
    assert out["answer"] == "insufficient_evidence" and "bar not met: precision" in out["rationale"], out
    assert bf.careful(card, World(noise=0.4))["answer"] == "insufficient_evidence"


def test_h1_the_precision_bar_is_reachable_and_guards(monkeypatch):
    """Mutation: with the bar disabled the same noisy world is no longer refused for precision."""
    monkeypatch.setattr(arms, "PRECISION", math.inf)
    out = arms_grammar_v3.grammar_enumeration({**CARD, "universe_id": "u-noisy-mut"}, World(noise=0.4), seed=3)
    assert "precision (se" not in out["rationale"]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_h1_rereview_beat_a_constant_comes_before_the_precision_bar(seed):
    """Re-review 2026-10-30: a constant law under large noise (a no_solution-like world) is ``no_law`` for the arm, as for
    ``careful`` -- the precision bar must not pre-empt the held-out beat-a-constant check."""
    from engcore.blindfold import baselines as bf
    card = {**CARD, "universe_id": f"u-const-{seed}", "query_budget": 60}
    world = lambda: World(law=lambda s: 2.0, noise=0.7)           # noqa: E731
    world_a = world()
    world_a.rng = np.random.default_rng(seed)
    out = arms_grammar_v3.grammar_enumeration(card, world_a, seed=seed)
    world_b = world()
    world_b.rng = np.random.default_rng(seed)
    ref = bf.careful(card, world_b)
    assert ref["answer"] == "no_law"
    assert out["answer"] == "no_law", out["rationale"]


def test_h1_rereview_the_gate_keeps_arms_gate_order_on_a_failed_bar():
    """The precision bar and the lack-of-fit bar fail together into the covariate check, then a refusal."""
    rows = [{"a": 1.0 + i / 10, "b": 1.5, "c": 1.0, "w": 1.0 + (i % 3) / 10, "y": 1.0 + (i % 2) * 0.5 + i / 10}
            for i in range(40)]
    law = {"mul": [{"const": 1.0}, {"pow": [{"var": "a"}, {"const": 1.0}]}]}
    out = arms_grammar_v3.gate({**CARD, "observed_covariates": []}, rows, 4, law, 30, "t")
    assert out["answer"] in ("insufficient_evidence", "no_law")
    if out["answer"] == "insufficient_evidence":
        assert "precision (se" in out["rationale"]


def test_the_report_rederives_the_answer_key_worlds_and_refuses_a_wrong_root():
    from benchmarks.genesis_lite import expressibility_v3 as ev
    from benchmarks.genesis_lite.answer_key import export_answer_key
    from benchmarks.genesis_lite.harness import MIX
    from benchmarks.genesis_lite.pilot_v3 import master_seed
    root, cid = bytes(range(32)), "gl-v03-dev-0-0-anonymous"
    master = master_seed(root, 0, "anonymous", 0)
    ids = [w.universe_id for w in ev.worlds(master, cid)]
    key = export_answer_key(master, cid, MIX, ids)
    assert key["status"] == "DERIVED"
    assert [u["kind"] for u in key["universes"]] == [w.kind.value for w in ev.worlds(master, cid)]
    records = [{"status": "VALID", "arm": "careful", "task": {"seed": 0, "campaign": 0, "presentation": "anonymous"},
                "universes": [{"universe_id": u["universe_id"], "kind": u["kind"], "credit": 0.0,
                               "answer": "insufficient_evidence", "truth_in_searched_family": False}
                              for u in key["universes"]]}]
    with pytest.raises(ValueError):
        ev.report(records, bytes(32))                                 # another root re-derives other worlds


def test_m3_scipy_is_recorded_in_the_library_versions():
    from benchmarks.genesis_lite.harness_v3 import LIBRARIES, library_versions
    assert "scipy" in LIBRARIES and library_versions()["scipy"] != "NOT_INSTALLED"


def test_l1_the_ledger_id_is_bound_to_universe_seed_and_data():
    seen = []
    real = arms_grammar_v3.select

    def spy(structures, L, z, **kw):
        seen.append(kw["ledger_id"])
        return real(structures, L, z, **kw)

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(arms_grammar_v3, "select", spy)
        arms_grammar_v3.grammar_enumeration({**CARD, "universe_id": "u-id-a"}, World(), seed=4)
        arms_grammar_v3.grammar_enumeration({**CARD, "universe_id": "u-id-b"}, World(), seed=4)
    assert len(seen) == 2 and seen[0] != seen[1] and all("token" not in s for s in seen)


def test_expressibility_agrees_with_the_monomial_family_and_never_claims_a_missing_law():
    """Consistency of the report helper: a hidden law inside the monomial family is a dimensionally consistent power law,
    so it must be EXPRESSIBLE_BY_FIT; a world without a law is NO_LAW, never expressible."""
    from benchmarks.genesis_lite import expressibility_v3 as ev
    from benchmarks.genesis_lite.evaluator import in_monomial_family
    from engcore.blindfold.universe import generate_universe
    checked = 0
    for i in range(30):
        w = generate_universe(f"exc4-expr-{i}", "discoverable")
        if in_monomial_family(w.law):
            assert ev.expressibility(w) == "EXPRESSIBLE_BY_FIT", w.universe_id
            checked += 1
    assert checked >= 5
    assert ev.expressibility(generate_universe("exc4-expr-none", "no_solution")) == "NO_LAW"


def test_the_arm_runs_a_valid_v0_3_campaign():
    from benchmarks.genesis_lite.harness import code_identity
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    rec = run_one_v3("grammar_enumeration", arms_grammar_v3.grammar_enumeration, master_seed=(21).to_bytes(4, "big") * 8,
                     campaign_id="gl-v03-grammar", presentation="paraphrased")
    assert rec.status == "VALID" and rec.evaluator_status == "VALID", rec.reasons
    assert len(rec.universes) == 6 and all(u["answer"] != "inadmissible" for u in rec.universes)
    assert code_identity()[1] == []
