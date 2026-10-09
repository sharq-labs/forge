"""Big Rocks K/L/M/N: grammar, three-valued constraints, multi-fidelity standing/promotion, history, hierarchy, search loop."""

from __future__ import annotations

import pytest

from engcore.design import DesignCandidate, DesignCandidateReference, DesignSpace
from engcore.design.grammar import CompatibilityRule, ConstraintStatus, DesignGrammar, RuleKind, evaluate_constraints
from engcore.design.hierarchy import ComponentDesignSpace, HierarchicalCandidate, HierarchicalDesignSpace, verify_component_lineage
from engcore.design.history import AttemptOutcome, DesignAttempt, DesignHistory
from engcore.design.multifidelity import (
    FidelityLedger, FidelityObservation, FidelityOutcome, PromotionPolicy, Standing, standard_ladder,
)
from engcore.design.search import run_discovery
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from engcore.scientific.ir.values import CategoricalValue
from engcore.scientific.ir.variables import ScientificVariable, VariableKind
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity

CTX = "c" * 64
MASS = ObjectiveDefinition("min-mass", "mass", ObjectiveDirection.MINIMIZE, "kg")


def space(space_id="enclosure"):
    return DesignSpace(space_id, "1", (
        ScientificVariable("wall", "mm", lower=Quantity(1, "mm"), upper=Quantity(5, "mm")),
        ScientificVariable("cooling", "dimensionless", kind=VariableKind.CATEGORICAL, categories=("air", "liquid", "none")),
        ScientificVariable("housing", "dimensionless", kind=VariableKind.CATEGORICAL, categories=("sealed", "vented")),
    ))


def grammar():
    return DesignGrammar("enclosure-grammar", space(), (
        CompatibilityRule("sealed-no-air", RuleKind.EXCLUDES, "housing", ("sealed",), "cooling", ("air",),
                          "a sealed housing has no air path"),))


def obs(key, rung, outcome, mass=None, **kw):
    rank = standard_ladder().rung(rung).rank
    metrics = {} if mass is None else {"mass": Quantity(mass, "kg")}
    reason = kw.pop("reason", "declared criteria; uncertainty UNKNOWN")
    return FidelityObservation(key, rung, rank, outcome, kw.pop("provider", "test-model"), reason, metrics, **kw)


# --------------------------------------------------------------------------
# K: grammar and constraints
# --------------------------------------------------------------------------


def test_grammar_rejects_incompatible_combinations_and_refuses_bad_rules():
    g = grammar()
    bad = {"wall": Quantity(2, "mm"), "cooling": CategoricalValue("air"), "housing": CategoricalValue("sealed")}
    good = dict(bad, cooling=CategoricalValue("liquid"))
    assert g.violations(bad) == ("sealed-no-air: a sealed housing has no air path",) and g.violations(good) == ()
    with pytest.raises(InvalidScientificProblem, match="continuous"):
        DesignGrammar("g", space(), (CompatibilityRule("r", RuleKind.REQUIRES, "wall", (1,), "cooling", ("air",), "x"),))
    with pytest.raises(InvalidScientificProblem, match="does not declare"):
        DesignGrammar("g", space(), (CompatibilityRule("r", RuleKind.REQUIRES, "cooling", ("plasma",), "housing", ("vented",), "x"),))


def test_constraints_are_three_valued_and_missing_metrics_are_unknown():
    limit = ConstraintDefinition("max-temp", "temperature", ConstraintOperator.LESS_EQUAL, Quantity(350, "K"))
    mass = ConstraintDefinition("max-mass", "mass", ConstraintOperator.LESS_EQUAL, Quantity(2, "kg"))
    e = evaluate_constraints((limit, mass), {"mass": Quantity(1.5, "kg")})
    assert e.feasible is None and e.unknown == ("max-temp",)
    e2 = evaluate_constraints((limit, mass), {"mass": Quantity(2.5, "kg"), "temperature": Quantity(300, "K")})
    assert e2.feasible is False and e2.violated == ("max-mass",)
    e3 = evaluate_constraints((limit,), {"temperature": Quantity(20, "degC")})
    assert e3.feasible is True and e3.outcomes[0].status is ConstraintStatus.SATISFIED


# --------------------------------------------------------------------------
# L: multi-fidelity
# --------------------------------------------------------------------------


def test_cheap_support_never_overwrites_a_higher_fidelity_contradiction():
    led = FidelityLedger("k").add(obs("k", "analytic", FidelityOutcome.SUPPORTS, 1.0))
    assert led.standing()[0] is Standing.SUPPORTED
    led = led.add(obs("k", "numerical", FidelityOutcome.CONTRADICTS))
    led = led.add(obs("k", "analytic", FidelityOutcome.SUPPORTS, 0.9))
    standing, rank, why = led.standing()
    assert standing is Standing.CONTRADICTED and rank == 2 and "overrides" in why
    split = FidelityLedger("k").add(obs("k", "numerical", FidelityOutcome.SUPPORTS, 1.0)).add(obs("k", "numerical", FidelityOutcome.CONTRADICTS))
    assert split.standing()[0] is Standing.CONFLICTED
    assert FidelityLedger("k").add(obs("k", "analytic", FidelityOutcome.PROVIDER_FAILED, provider="p")).standing()[0] is Standing.UNDECIDED
    with pytest.raises(InvalidScientificProblem, match="UNKNOWN uncertainty"):
        obs("k", "numerical", FidelityOutcome.SUPPORTS, 1.0, reason="looks fine")
    with pytest.raises(InvalidScientificProblem, match="exposes no metrics"):
        obs("k", "analytic", FidelityOutcome.REFUSED, 1.0)


def test_promotion_is_budgeted_explained_and_never_promotes_contradiction_or_unknown():
    policy = PromotionPolicy(standard_ladder(), MASS, {"analytic": 2})
    ledgers = [FidelityLedger("a").add(obs("a", "analytic", FidelityOutcome.SUPPORTS, 3.0)),
               FidelityLedger("b").add(obs("b", "analytic", FidelityOutcome.SUPPORTS, 1.0)),
               FidelityLedger("c").add(obs("c", "analytic", FidelityOutcome.SUPPORTS, 2.0)),
               FidelityLedger("d").add(obs("d", "analytic", FidelityOutcome.CONTRADICTS)),
               FidelityLedger("e").add(obs("e", "analytic", FidelityOutcome.SUPPORTS)),
               FidelityLedger("f")]
    decisions = {d.candidate_key: d for d in policy.decide(ledgers, "analytic")}
    assert {k for k, d in decisions.items() if d.promoted} == {"b", "c"}
    assert "budget" in decisions["a"].reason and "contradicted" in decisions["d"].reason
    assert "UNKNOWN" in decisions["e"].reason and "never observed" in decisions["f"].reason
    assert all(d.to_rung == "reduced_order" for d in decisions.values())
    with pytest.raises(InvalidScientificProblem, match="top rung"):
        policy.decide(ledgers, "experimental")


# --------------------------------------------------------------------------
# M: history
# --------------------------------------------------------------------------


def test_history_is_append_only_tamper_evident_and_skips_deterministic_negatives():
    h = DesignHistory()
    h.record(DesignAttempt("k1", "analytic", CTX, AttemptOutcome.CONSTRAINT_VIOLATED, "too hot", violated_constraints=("max-temp",)))
    h.record(DesignAttempt("k2", "analytic", CTX, AttemptOutcome.PROVIDER_FAILED, "solver crashed", provider="ccx-2.23"))
    assert h.should_skip("k1", "analytic", CTX)[0]
    assert not h.should_skip("k1", "analytic", "d" * 64)[0]  # another evaluation context is another question
    assert h.should_skip("k2", "analytic", CTX, provider="ccx-2.23")[0]
    assert not h.should_skip("k2", "analytic", CTX, provider="code_aster-17")[0]
    payload = h.to_dict()
    assert DesignHistory.from_dict(payload).head == h.head
    payload["entries"][0]["attempt"]["reason"] = "fine actually"
    with pytest.raises(InvalidScientificProblem, match="digest"):
        DesignHistory.from_dict(payload)
    with pytest.raises(InvalidScientificProblem, match="names the violated"):
        DesignAttempt("k", "analytic", CTX, AttemptOutcome.CONSTRAINT_VIOLATED, "x")
    with pytest.raises(InvalidScientificProblem, match="validation-derived"):
        DesignAttempt("k", "analytic", CTX, AttemptOutcome.FAILED, "x", verdict="validated")


# --------------------------------------------------------------------------
# N: hierarchy
# --------------------------------------------------------------------------


def _cand(space_, twin, cid, assignments, parents=()):
    return DesignCandidate(cid, space_.reference, TwinReference(twin, "1"), assignments, generation=1 if parents else 0,
                           parents=tuple(DesignCandidateReference(p) for p in parents))


def test_component_owned_variables_replacement_and_recomposition_lineage():
    drone = DesignSpace("drone", "1", (ScientificVariable("arm_length", "m", lower=Quantity(0.1, "m"), upper=Quantity(0.5, "m")),))
    motor = DesignSpace("motor", "1", (ScientificVariable("turns", "dimensionless", lower=Quantity(5, "dimensionless"), upper=Quantity(40, "dimensionless")),
                                       ScientificVariable("arm_length", "m", lower=Quantity(0.01, "m"), upper=Quantity(0.02, "m"))))
    hs = HierarchicalDesignSpace("drone", (ComponentDesignSpace(("drone",), drone), ComponentDesignSpace(("drone", "prop1", "motor"), motor)))
    assert hs.owner_of("arm_length") == (("drone",), ("drone", "prop1", "motor"))  # names are local, never flattened
    d0 = _cand(drone, "drone-twin", "d0", {"arm_length": Quantity(0.3, "m")})
    m0 = _cand(motor, "motor-twin-0", "m0", {"turns": Quantity(10, "dimensionless"), "arm_length": Quantity(0.015, "m")})
    root = HierarchicalCandidate(hs, {("drone",): d0, ("drone", "prop1", "motor"): m0})
    m1 = _cand(motor, "motor-twin-1", "m1", {"turns": Quantity(14, "dimensionless"), "arm_length": Quantity(0.015, "m")}, parents=("m0",))
    child = root.replace_component(("drone", "prop1", "motor"), m1, note="more turns for torque", assembly_digest="a" * 64)
    assert child.candidate_id != root.candidate_id and child.parent_candidate == root.candidate_id
    assert root.component(("drone", "prop1", "motor")).candidate_id == "m0"
    assert verify_component_lineage(child, {root.candidate_id: root}) == (root.candidate_id, child.candidate_id)
    stray = _cand(motor, "motor-twin-2", "m2", {"turns": Quantity(20, "dimensionless"), "arm_length": Quantity(0.015, "m")})
    with pytest.raises(InvalidScientificProblem, match="declare the replaced one as a parent"):
        root.replace_component(("drone", "prop1", "motor"), stray, note="x")
    with pytest.raises(InvalidScientificProblem, match="exactly one sub-candidate per owner"):
        HierarchicalCandidate(hs, {("drone",): d0})
    with pytest.raises(InvalidScientificProblem):
        HierarchicalCandidate(hs, {("drone",): d0, ("drone", "prop1", "motor"): _cand(motor, "m-x", "mx", {"turns": Quantity(99, "dimensionless"),
                                                                                                               "arm_length": Quantity(0.015, "m")})})


# --------------------------------------------------------------------------
# K+L+M: the loop
# --------------------------------------------------------------------------


class Analytic:
    rung_id, provider = "analytic", "closed-form-mass"

    def evaluate(self, key, a):
        wall = a["wall"].magnitude_in("m")
        mass = 7800 * 0.2 * 0.2 * wall + (1.0 if a["cooling"].value == "liquid" else 0.2)
        if a["cooling"].value == "none" and wall < 0.002:
            return FidelityObservation(key, "analytic", 0, FidelityOutcome.CONTRADICTS, self.provider, "thin uncooled wall overheats")
        return FidelityObservation(key, "analytic", 0, FidelityOutcome.SUPPORTS, self.provider, "meets screening criteria",
                                   {"mass": Quantity(mass, "kg")}, uncertainty="not_applicable")


class Lumped:
    rung_id, provider = "reduced_order", "lumped-thermal-v1"

    def __init__(self):
        self.calls = []

    def evaluate(self, key, a):
        self.calls.append(key)
        if a["housing"].value == "sealed":
            return FidelityObservation(key, "reduced_order", 1, FidelityOutcome.CONTRADICTS, self.provider, "sealed housing overheats (lumped)")
        if len(self.calls) == 1:
            raise RuntimeError("license server unreachable")
        return FidelityObservation(key, "reduced_order", 1, FidelityOutcome.SUPPORTS, self.provider, "meets lumped criteria",
                                   {"mass": Quantity(1.0, "kg")})


def test_discovery_loop_is_deterministic_records_everything_and_claims_no_validation():
    policy = PromotionPolicy(standard_ladder(), MASS, {"analytic": 3})
    lumped = Lumped()
    run = run_discovery(space(), count=24, evaluators={"analytic": Analytic(), "reduced_order": lumped}, policy=policy,
                        context_digest=CTX, grammar=grammar())
    again = run_discovery(space(), count=24, evaluators={"analytic": Analytic(), "reduced_order": Lumped()}, policy=policy,
                          context_digest=CTX, grammar=grammar())
    assert run.digest == again.digest and run.to_dict()["classification"] == "search_record_not_validation"
    assert run.rejected and all("sealed-no-air" in r[0] for r in run.rejected.values())
    promoted = [p.candidate_key for p in run.promotions if p.promoted]
    assert len(promoted) == 3 and sorted(lumped.calls) == sorted(promoted)  # only promoted candidates reach rung 1
    standings = run.standings()
    failed = [k for k, (s, _, why) in standings.items() if k in promoted and s == "supported" and why.startswith("supported at rank 0")]
    assert failed, "the candidate whose rung-1 evaluator raised keeps only its rung-0 standing"
    assert any(o.outcome is FidelityOutcome.PROVIDER_FAILED for led in run.ledgers.values() for o in led.observations)
    for key in run.supported_at_highest_rank():
        assert standings[key][0] == "supported"


def test_rerun_with_shared_history_skips_known_outcomes():
    policy = PromotionPolicy(standard_ladder(), MASS, {"analytic": 2})
    history = DesignHistory()
    first = run_discovery(space(), count=10, evaluators={"analytic": Analytic()}, policy=policy, context_digest=CTX, history=history)
    second = run_discovery(space(), count=10, evaluators={"analytic": Analytic()}, policy=policy, context_digest=CTX, history=history)
    assert len(second.skipped) == len(first.assignments)
    assert all(not led.observations for led in second.ledgers.values())
    assert history.outcome_counts().get("succeeded", 0) + history.outcome_counts().get("contradicted", 0) == len(first.assignments)
