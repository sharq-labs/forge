"""EXC-2 (owner-approved 2026-10-29): the existing Minimal Mind as a measurement arm of the v0.3 development pilot.

The adapter only translates: a presented card becomes an ``ExperimentalProblem``, observations go through the escrow's
client, and the Mind's conclusion becomes a Blindfold answer by a mapping frozen before any run. Mind code is untouched.
"""

from __future__ import annotations

import json
import math
import random

import pytest

from engcore.blindfold.expression import evaluate, validate

CARD = {"universe_id": "u-1", "level": "L5", "base_dimensions": ["L"],
        "inputs": [{"name": "q", "unit": "L^1", "settable": True, "range": [0.5, 4.0]},
                   {"name": "r", "unit": "1", "settable": True, "range": [1.0, 10.0]}],
        "observed_covariates": ["w"], "covariate_units": {"w": "1"}, "output": {"name": "y", "unit": "L^2"},
        "assessment_region": {"q": [0.5, 8.0], "r": [1.0, 10.0]}, "query_budget": 40, "query_cost": 1.0,
        "answers": ["law", "no_law", "insufficient_evidence", "indistinguishable", "confounded"]}


def test_a_card_becomes_the_mind_problem_it_states():
    from benchmarks.genesis_lite.mind_arm_v3 import problem_from_card
    p = problem_from_card(CARD)
    assert [(x.name, x.low, x.high, x.unit) for x in p.inputs] == [("q", 0.5, 4.0, "L^1"), ("r", 1.0, 10.0, "1")]
    assert p.covariates == ("w",) and p.observable == "y" and p.observable_unit == "L^2"
    assert p.budget == 40 and p.query_cost == 1.0
    assert p.region == {"q": (0.5, 8.0), "r": (1.0, 10.0)} and p.extrapolates


def test_the_fitted_law_translates_exactly_into_the_escrow_grammar():
    from benchmarks.genesis_lite.mind_arm_v3 import law_expression
    from engcore.mind.minimal.runner import FittedLaw
    law = FittedLaw("h", 0.37, {"q": 1.5, "w": -0.4}, {"q": 0.12})
    expr = law_expression(law)
    assert validate(expr) == {"q", "w"}
    rng = random.Random(7)
    for _ in range(50):
        pt = {"q": rng.uniform(0.5, 8.0), "w": rng.uniform(0.1, 5.0)}
        lq, lw = math.log(pt["q"]), math.log(pt["w"])
        expected = math.exp(0.37 + 1.5 * lq - 0.4 * lw + 0.12 * lq * lq)
        assert math.isclose(evaluate(expr, pt), expected, rel_tol=1e-12)
    assert evaluate(law_expression(FittedLaw("c", 1.2, {}, {})), {}) == pytest.approx(math.exp(1.2), rel=1e-15)


def test_the_conclusion_mapping_is_frozen_and_complete():
    from benchmarks.genesis_lite.mind_arm_v3 import TRANSLATION
    from engcore.mind.minimal.runner import ConclusionKind
    assert TRANSLATION == {"law": "law", "no_dependence": "no_law", "insufficient_evidence": "insufficient_evidence",
                           "unidentifiable_passive_association": "confounded", "indistinguishable": "indistinguishable",
                           "refused": "insufficient_evidence"}
    assert set(TRANSLATION) == {k.value for k in ConclusionKind}


def test_an_indistinguishable_conclusion_carries_its_two_laws():
    from benchmarks.genesis_lite.mind_arm_v3 import proposal_from
    from engcore.mind.minimal.runner import ConclusionKind, FittedLaw, MindConclusion
    two = MindConclusion(ConclusionKind.INDISTINGUISHABLE, "r", laws=(FittedLaw("a", 0.1, {"q": 1.0}, {}),
                                                                      FittedLaw("b", 0.1, {"q": 2.0}, {})))
    p = proposal_from(CARD, two)
    assert p["answer"] == "indistinguishable" and len(p["laws"]) == 2


def test_a_law_conclusion_proposes_the_leading_law_and_refusals_carry_none():
    from benchmarks.genesis_lite.mind_arm_v3 import proposal_from
    from engcore.mind.minimal.runner import ConclusionKind, FittedLaw, MindConclusion
    p = proposal_from(CARD, MindConclusion(ConclusionKind.LAW, "r", laws=(FittedLaw("a", 0.1, {"q": 1.0}, {}),)))
    assert p["answer"] == "law" and validate(p["law"]) == {"q"}
    for kind, answer in ((ConclusionKind.NO_DEPENDENCE, "no_law"), (ConclusionKind.REFUSED, "insufficient_evidence"),
                         (ConclusionKind.UNIDENTIFIABLE_PASSIVE_ASSOCIATION, "confounded")):
        q = proposal_from(CARD, MindConclusion(kind, "why"))
        assert q["answer"] == answer and "law" not in q and "laws" not in q and q["rationale"].startswith("Mind")


def test_escrow_refusals_reach_the_mind_as_observation_refusals():
    from benchmarks.genesis_lite.mind_arm_v3 import observer
    from engcore.blindfold.escrow import EscrowRefused
    from engcore.mind.minimal.runner import ObservationRefused

    class Client:
        def __init__(self, message):
            self.message = message

        def observe(self, uid, settings, query_id):
            raise EscrowRefused(self.message)

    with pytest.raises(ObservationRefused) as budget:
        observer(CARD, Client("query budget 40 exhausted for u-1"))({"q": 1.0, "r": 2.0}, "q0")
    assert budget.value.budget is True
    with pytest.raises(EscrowRefused):        # re-raised as the baselines' _collect does: scored inadmissible
        observer(CARD, Client("q=9 lies outside the box"))({"q": 9.0, "r": 2.0}, "q1")


def test_four_mind_arms_one_per_variant_all_available_in_the_pilot():
    from benchmarks.genesis_lite import pilot_v3
    from benchmarks.genesis_lite.mind_arm_v3 import MIND_ARMS
    assert set(MIND_ARMS) == {"mind_full", "mind_no_adaptive_selection", "mind_no_belief_update", "mind_no_falsifier"}
    assert set(MIND_ARMS) <= set(pilot_v3.all_arms()) and all(pilot_v3.arm_available(a) for a in MIND_ARMS)


def test_the_mind_code_is_bound_into_the_development_identity():
    from benchmarks.genesis_lite.harness_v3 import SUBSTRATE_V3_FILES
    assert {"src/engcore/mind/minimal/runner.py", "src/engcore/mind/minimal/experiments.py",
            "src/engcore/mind/minimal/outcome_model.py"} <= set(SUBSTRATE_V3_FILES)


def test_the_mind_arm_runs_a_valid_v0_3_campaign():
    from benchmarks.genesis_lite.harness import code_identity
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    from benchmarks.genesis_lite.mind_arm_v3 import MIND_ARMS
    rec = run_one_v3("mind_full", MIND_ARMS["mind_full"][0], master_seed=(11).to_bytes(4, "big") * 8,
                     campaign_id="gl-v03-mind", presentation="anonymous")
    assert rec.status == "VALID" and rec.evaluator_status == "VALID", rec.reasons
    assert len(rec.universes) == 6 and all(u["rationale"].startswith("Mind") for u in rec.universes
                                           if u["answer"] != "inadmissible")
    assert code_identity()[1] == []


# ---- review of 896efd72 (2026-10-29) ------------------------------------------------------------------------------------
def test_a_non_budget_refusal_makes_the_mind_arm_fail_not_refuse():
    from benchmarks.genesis_lite.mind_arm_v3 import MIND_ARMS
    from engcore.blindfold.escrow import EscrowRefused

    class Client:
        def observe(self, uid, settings, query_id):
            raise EscrowRefused("q=9.0 is outside the allowed query range")

    with pytest.raises(EscrowRefused):
        MIND_ARMS["mind_full"][0](CARD, Client(), seed=0)


@pytest.mark.parametrize("laws", [0, 1, 3])
def test_a_mind_answer_missing_its_laws_is_a_failure_not_a_refusal(laws):
    from benchmarks.genesis_lite.mind_arm_v3 import MindAdapterError, proposal_from
    from engcore.mind.minimal.runner import ConclusionKind, FittedLaw, MindConclusion
    kind = ConclusionKind.LAW if laws == 0 else ConclusionKind.INDISTINGUISHABLE
    conclusion = MindConclusion(kind, "r", laws=tuple(FittedLaw(f"h{i}", 0.1, {"q": 1.0}, {}) for i in range(laws)))
    with pytest.raises(MindAdapterError):
        proposal_from(CARD, conclusion)


def test_a_refused_mind_answer_is_marked_as_a_model_refusal():
    from benchmarks.genesis_lite.mind_arm_v3 import proposal_from
    from engcore.mind.minimal.runner import ConclusionKind, MindConclusion
    p = proposal_from(CARD, MindConclusion(ConclusionKind.REFUSED, "non-positive observable"))
    assert p["answer"] == "insufficient_evidence" and p["rationale"].startswith("Mind refused")


@pytest.mark.parametrize("change", [{"assessment_region": None}, {"assessment_region": {"q": [0.5, 8.0]}},
                                    {"assessment_region": {"q": [0.5, 8.0], "r": [1.0, 10.0], "zz": [1, 2]}},
                                    {"query_cost": 2.0}, {"settable": False}])
def test_a_card_the_mind_cannot_state_exactly_is_refused(change):
    import copy
    from benchmarks.genesis_lite.mind_arm_v3 import MindAdapterError, problem_from_card
    card = copy.deepcopy(CARD)
    if "settable" in change:
        card["inputs"][1]["settable"] = False
    elif change.get("assessment_region", 1) is None:
        card.pop("assessment_region")
    else:
        card.update(change)
    with pytest.raises(MindAdapterError):
        problem_from_card(card)


def test_full_and_fixed_design_mind_arms_share_the_initial_design_seed_and_budget():
    from benchmarks.genesis_lite.mind_arm_v3 import MIND_ARMS, problem_from_card
    from engcore.mind.minimal.runner import initial_design

    def record(arm):
        seen = []

        class Client:
            def observe(self, uid, settings, query_id):
                seen.append(dict(settings))
                x = settings
                return {"observation": {"q": x["q"], "r": x["r"], "w": 1.3, "y": 2.0 * x["q"] ** 1.5 / x["r"]}}

        MIND_ARMS[arm][0](CARD, Client(), seed=4)
        return seen

    full, fixed = record("mind_full"), record("mind_no_adaptive_selection")
    n = len(initial_design(problem_from_card(CARD), 4))
    assert full[:n] == fixed[:n] and len(fixed) <= CARD["query_budget"] and len(full) <= CARD["query_budget"]


def test_ablation_labels_say_everything_they_remove():
    from benchmarks.genesis_lite.mind_arm_v3 import MIND_ARMS
    fixed = MIND_ARMS["mind_no_adaptive_selection"][1]
    assert "falsifier-targeted" in fixed and "early stop" in fixed
    assert "selection only" in MIND_ARMS["mind_no_belief_update"][1]


def test_the_identity_binds_the_minds_import_closure():
    from benchmarks.genesis_lite.harness_v3 import SUBSTRATE_V3_FILES
    assert {"src/engcore/claims/falsification.py", "src/engcore/mind/__init__.py",
            "src/engcore/mind/minimal/runner.py"} <= set(SUBSTRATE_V3_FILES)
    assert any(f.startswith("src/engcore/sria/decision/") for f in SUBSTRATE_V3_FILES)


def test_the_mind_arm_is_submitted_as_a_candidate_not_a_baseline():
    from benchmarks.genesis_lite.harness_v3 import run_one_v3
    from benchmarks.genesis_lite.mind_arm_v3 import MIND_ARMS
    rec = run_one_v3("mind_full", MIND_ARMS["mind_full"][0], master_seed=(11).to_bytes(4, "big") * 8,
                     campaign_id="gl-v03-mind", presentation="anonymous", proposer_kind="candidate")
    assert rec.status == "VALID" and rec.proposer_kind == "candidate"


def test_the_bound_closure_covers_every_engcore_module_a_mind_run_loads():
    import subprocess
    import sys
    from benchmarks.genesis_lite.harness_v3 import ROOT, SUBSTRATE_V3_FILES
    # import the Mind alone, run it once (lazy imports included), then list the engcore modules that were loaded
    code = "\n".join([
        "import sys, json",
        "from engcore.mind.minimal.problem import ExperimentalProblem, InputSpec",
        "from engcore.mind.minimal.runner import run_mind",
        "p = ExperimentalProblem('u', (InputSpec('q', 0.5, 4.0, 'L^1'),), ('w',), 'y', 'L^1', 20, 1.0, {'q': (0.5, 8.0)})",
        "run_mind(p, lambda s, ref: {'q': s['q'], 'w': 1.0, 'y': 2.0 * s['q']}, seed=1)",
        "print(json.dumps(sorted(getattr(m, '__file__', '') or '' for n, m in sys.modules.items()"
        " if n.split('.')[0] == 'engcore')))"])
    out = json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                                    cwd=ROOT).stdout)
    assert any(f.endswith("runner.py") for f in out)
    loaded = {__import__("pathlib").Path(f).resolve().relative_to(ROOT).as_posix() for f in out if f}
    assert loaded and loaded <= set(SUBSTRATE_V3_FILES), sorted(loaded - set(SUBSTRATE_V3_FILES))
