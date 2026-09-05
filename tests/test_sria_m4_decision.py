"""SRIA V0.1 M4 — decision intelligence tests.

Runs under pytest, and standalone via ``python -m tests.test_sria_m4_decision``.

Scenarios are **predeclared** in :data:`SCENARIOS` with their expected winners
computed from the closed form in ``sria_m4_benchmark``. Nothing is tuned after
seeing a result.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from src.engcore.scientific import Quantity
from src.engcore.sria import CampaignCharter, CampaignType, ExecutorType, ResearchAction
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.decision import (
    ActionFamily,
    ActionProposal,
    AtomicAction,
    BudgetPlan,
    CandidateEvaluator,
    CompositeAction,
    ComponentStatus,
    CostAggregation,
    DecisionRecommendation,
    DiscriminateGenerator,
    ExecutionOrder,
    ExploreGenerator,
    FactorAvailability,
    GenerationContext,
    Hypothesis,
    HypothesisSet,
    OutcomeDependence,
    PredictionDisagreement,
    RecommendationOutcome,
    ScoreStatus,
    TerminalObjectiveStatus,
    UtilityEngine,
    UtilityPolicy,
    ValidateGenerator,
    generate_candidates,
    information_only_ranking,
    pin_decision_basis,
    resolve_terminal_objective,
)

from tests.sria_m4_benchmark import (
    COST_WEIGHT,
    toy_cost_tradeoff,
    PAYOFF,
    ToyCostSupplier,
    ToyFailureSupplier,
    ToyOutcomeModel,
    ToyTerminalUtility,
    gate_forbidding,
    ground_truth_net_value,
    toy_action,
    toy_charter,
    toy_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DECISION_DIR = REPO_ROOT / "src" / "engcore" / "sria" / "decision"


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


# =====================================================================
# Fixtures
# =====================================================================

def objective(charter=None, utility=None):
    return resolve_terminal_objective(
        charter or toy_charter(), utility if utility is not None else ToyTerminalUtility()
    )


def engine(
    *,
    p_fail: float | None = 0.0,
    failure_verdict: CalibrationVerdict | None = CalibrationVerdict.TRUSTED,
    cost_verdict: CalibrationVerdict | None = CalibrationVerdict.TRUSTED,
    gate=None,
    policy: UtilityPolicy | None = None,
) -> UtilityEngine:
    return UtilityEngine(
        policy=policy
        or UtilityPolicy(policy_id="toy.policy", cost_tradeoff=toy_cost_tradeoff()),
        outcome_model=ToyOutcomeModel(),
        cost_supplier=ToyCostSupplier(cost_verdict),
        failure_supplier=ToyFailureSupplier(p_fail, failure_verdict),
        feasibility_gate=gate,
    )


def evaluate(candidates, *, eng=None, snapshot=None, obj=None, budget=None, rid="rec-1"):
    """Score a candidate set against a properly pinned decision basis.

    M4.4 requires formal scoring to run on a verified basis, so a snapshot that
    does not already carry one is pinned here to the stack that will score it —
    exactly what a real caller does at snapshot-mint time. A snapshot that
    *does* carry a basis is passed through untouched, so tests that
    deliberately present a stale or contradictory basis still see it refused.
    """
    evaluator = CandidateEvaluator(eng or engine())
    snapshot = snapshot if snapshot is not None else toy_snapshot()
    objective_ = obj if obj is not None else objective()
    if not snapshot.pins_decision_basis:
        snapshot = pin_decision_basis(
            snapshot,
            evaluator.build_manifest(
                candidates=candidates, snapshot=snapshot, objective=objective_
            ),
        )
    return evaluator.evaluate(
        recommendation_id=rid,
        candidates=candidates,
        snapshot=snapshot,
        objective=objective_,
        budget=budget,
    )


# =====================================================================
# PREDECLARED BENCHMARK SCENARIOS
# =====================================================================
#
# Each entry: (name, candidates, expected SRIA winner, expected info-only
# winner, whether the two must differ). Winners are derived from the closed
# form in the benchmark module, not from running the engine.

CHEAP_WEAK = toy_action("cheap_weak", family=ActionFamily.EXPLORE, reliability=0.55, cost=0.5)
EXPENSIVE_STRONG = toy_action(
    "expensive_strong", family=ActionFamily.CHARACTERIZE, reliability=0.95, cost=3.0
)
CHEAP_STRONG = toy_action("cheap_strong", family=ActionFamily.EXPLORE, reliability=0.90, cost=0.5)
COSTLY_MARGINAL = toy_action(
    "costly_marginal", family=ActionFamily.CHARACTERIZE, reliability=0.95, cost=4.0
)

SCENARIOS = {
    # A: cheap low-information loses to expensive high-information.
    #    net(cheap_weak)      = (5.5 - 5) - 0.5 =  0.0
    #    net(expensive_strong)= (9.5 - 5) - 3.0 = +1.5   <- both agree
    "A_cheap_loses_to_informative": {
        "candidates": (CHEAP_WEAK, EXPENSIVE_STRONG),
        "sria_winner": "expensive_strong",
        "info_winner": "expensive_strong",
        "must_differ": False,
    },
    # B: expensive action rejected when the extra information is too small.
    #    net(cheap_strong)     = (9.0 - 5) - 0.5 = +3.5  <- SRIA
    #    net(costly_marginal)  = (9.5 - 5) - 4.0 = +0.5  <- info-only
    "B_expensive_rejected_for_marginal_gain": {
        "candidates": (CHEAP_STRONG, COSTLY_MARGINAL),
        "sria_winner": "cheap_strong",
        "info_winner": "costly_marginal",
        "must_differ": True,
    },
    # NULL: both methods agree; the machinery must not differ for its own sake.
    "NULL_both_agree": {
        "candidates": (
            toy_action("weak_pricey", family=ActionFamily.EXPLORE, reliability=0.55, cost=2.0),
            toy_action("strong_cheap", family=ActionFamily.OPTIMIZE, reliability=0.95, cost=0.5),
        ),
        "sria_winner": "strong_cheap",
        "info_winner": "strong_cheap",
        "must_differ": False,
    },
}


def test_benchmark_scenarios_match_closed_form():
    """The engine reproduces the analytic net value on every scenario."""
    for name, spec in SCENARIOS.items():
        recommendation = evaluate(spec["candidates"], rid=f"rec-{name}")
        assert recommendation.outcome is RecommendationOutcome.RECOMMEND_ACTION, name
        for score in recommendation.scores:
            candidate = next(
                c for c in spec["candidates"] if c.action_id == score.action_id
            )
            expected = ground_truth_net_value(candidate)
            assert abs(score.total - expected) < 1e-9, (
                f"{name}/{score.action_id}: {score.total} != {expected}"
            )


def test_M4_success_criterion_sria_beats_cost_unaware_ranking():
    """SRIA and a cost-unaware ranker must differ where the objective says so."""
    differed = []
    agreed = []

    for name, spec in SCENARIOS.items():
        recommendation = evaluate(spec["candidates"], rid=f"rec-{name}")
        sria_choice = recommendation.chosen_action_id
        info_choice = information_only_ranking(recommendation.scores)[0].action_id

        assert sria_choice == spec["sria_winner"], f"{name}: SRIA chose {sria_choice}"
        assert info_choice == spec["info_winner"], f"{name}: info chose {info_choice}"

        if spec["must_differ"]:
            assert sria_choice != info_choice, f"{name} was predeclared to differ"
            # And SRIA's pick must be better by the campaign's own objective.
            by_id = {c.action_id: c for c in spec["candidates"]}
            sria_value = ground_truth_net_value(by_id[sria_choice])
            info_value = ground_truth_net_value(by_id[info_choice])
            assert sria_value > info_value, (
                f"{name}: SRIA {sria_value} not better than info-only {info_value}"
            )
            differed.append(name)
        else:
            assert sria_choice == info_choice, f"{name} was predeclared to agree"
            agreed.append(name)

    # The criterion: at least one principled difference, and at least one null.
    assert differed, "no scenario demonstrated a changed decision"
    assert agreed, "no null scenario — the machinery must not always differ"


# =====================================================================
# 1. No research-mode state machine
# =====================================================================

def test_no_research_mode_state_machine_exists():
    forbidden_names = {
        "current_mode",
        "research_mode",
        "set_mode",
        "transition_mode",
        "ModeController",
        "MetaBrain",
        "ScientificBrain",
        "UniversalStrategist",
    }
    for path in sorted(DECISION_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                assert node.name not in forbidden_names, f"{path.name}: {node.name}"
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                raise AssertionError(f"{path.name} references {node.id}")
            if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                raise AssertionError(f"{path.name} references .{node.attr}")

    # Families are a flat vocabulary, not an ordered machine.
    assert len(list(ActionFamily)) == 6
    for family in ActionFamily:
        assert not hasattr(family, "next_family")


# =====================================================================
# 2-3. All six families generate, and feed one engine
# =====================================================================

def build_full_context(**kw):
    targets = {
        family: (
            {
                "action_id": f"{family.value}-a",
                "target_ref": f"target-{family.value}",
                "observable": "theta",
            },
        )
        for family in ActionFamily
        if family is not ActionFamily.DISCRIMINATE
    }
    hypotheses = HypothesisSet(
        hypotheses=(
            Hypothesis(hypothesis_id="h1", model_ref="m1"),
            Hypothesis(hypothesis_id="h2", model_ref="m2"),
        ),
        disagreements=(
            PredictionDisagreement(
                observable="theta", hypothesis_a="h1", hypothesis_b="h2",
                separation=2.0,
            ),
        ),
    )
    return GenerationContext(
        snapshot=kw.get("snapshot", toy_snapshot()),
        targets=targets,
        hypotheses=hypotheses,
        validation_targets={"ob-1": "residual_evidence"},
    )


def test_all_six_families_generate_candidates():
    candidates = generate_candidates(build_full_context())
    families = {c.family for c in candidates}
    assert families == set(ActionFamily), f"missing: {set(ActionFamily) - families}"

    for candidate in candidates:
        proposal = candidate.proposal
        assert proposal.target_ref and proposal.rationale
        assert isinstance(proposal.assumptions, tuple)


def test_all_families_feed_one_common_engine():
    candidates = generate_candidates(build_full_context())
    # Give every candidate the metadata the toy suppliers read.
    enriched = tuple(
        toy_action(
            c.action_id,
            family=c.family,
            reliability=0.8,
            cost=0.2,
            target_ref=c.proposal.target_ref,
        )
        for c in candidates
    )
    recommendation = evaluate(enriched, rid="rec-common")
    scored_families = {s.family for s in recommendation.scores}
    assert scored_families == set(ActionFamily)
    # One engine version scored them all.
    assert recommendation.engine_version
    assert len({s.status for s in recommendation.scores}) >= 1


# =====================================================================
# 4. Infeasible candidates cannot be ranked
# =====================================================================

def test_infeasible_candidate_cannot_be_ranked():
    """C: high raw VoI must not rescue an inadmissible action."""
    forbidden = toy_action(
        "forbidden_but_brilliant",
        family=ActionFamily.OPTIMIZE,
        reliability=1.0,          # perfect information
        cost=0.01,                # nearly free
        target_ref="forbidden-zone",
    )
    modest = toy_action("modest", family=ActionFamily.EXPLORE, reliability=0.8, cost=0.5)

    recommendation = evaluate(
        (forbidden, modest),
        eng=engine(gate=gate_forbidding("forbidden-zone")),
        rid="rec-infeasible",
    )
    scores = {s.action_id: s for s in recommendation.scores}
    assert scores["forbidden_but_brilliant"].status is ScoreStatus.INFEASIBLE
    assert scores["forbidden_but_brilliant"].total is None
    assert recommendation.chosen_action_id == "modest"
    # It would have won on information alone.
    assert ground_truth_net_value(forbidden) > ground_truth_net_value(modest)


# =====================================================================
# 5. Missing terminal utility blocks formal VoI
# =====================================================================

def test_missing_terminal_objective_blocks_formal_voi():
    """I: no decision or no utility -> no formal VoI, explicitly."""
    no_utility = resolve_terminal_objective(toy_charter(), None)
    assert no_utility.status is TerminalObjectiveStatus.TERMINAL_OBJECTIVE_UNAVAILABLE
    assert "utility" in no_utility.reason

    recommendation = evaluate(
        (CHEAP_STRONG,), obj=no_utility, rid="rec-no-objective"
    )
    assert recommendation.outcome is (
        RecommendationOutcome.TERMINAL_OBJECTIVE_UNAVAILABLE
    )
    assert recommendation.chosen_action_id == ""

    # OPEN_RESEARCH stays reserved: no faked VoI for open-ended discovery.
    open_charter = CampaignCharter(
        campaign_id="open", campaign_type=CampaignType.OPEN_RESEARCH
    )
    open_objective = resolve_terminal_objective(open_charter, ToyTerminalUtility())
    assert open_objective.status is (
        TerminalObjectiveStatus.TERMINAL_OBJECTIVE_UNAVAILABLE
    )
    _raises(ValueError, lambda: open_objective.utility)


# =====================================================================
# 6. UNKNOWN probability is never silently replaced
# =====================================================================

def test_unknown_p_fail_is_never_silently_replaced():
    """M2 reports INSUFFICIENT_DATA; that must not become a confident number."""
    unknown = engine(p_fail=None, failure_verdict=CalibrationVerdict.INSUFFICIENT_DATA)
    recommendation = evaluate((CHEAP_STRONG,), eng=unknown, rid="rec-unknown")

    # M4.1: an unevaluated eligible candidate yields DECISION_INCOMPLETE, not
    # a stop proposal and not a bare "no scorable candidate".
    assert recommendation.outcome is RecommendationOutcome.DECISION_INCOMPLETE
    assert recommendation.unresolved_action_ids == ("cheap_strong",)
    score = recommendation.scores[0]
    assert score.status is ScoreStatus.NOT_SCORABLE
    assert score.total is None
    p_fail = score.component("p_computational_failure")
    assert p_fail.status is ComponentStatus.UNAVAILABLE
    assert p_fail.value is None

    # A component cannot claim UNAVAILABLE while carrying a value.
    from src.engcore.sria.decision.utility import ScoreComponent

    _raises(
        ValueError,
        ScoreComponent,
        name="p_computational_failure",
        value=0.1,
        status=ComponentStatus.UNAVAILABLE,
    )


def test_declared_policy_fallback_is_allowed_but_marked_degraded():
    """A conservative default is permitted only when declared, and stays visible."""
    policy = UtilityPolicy(
        policy_id="toy.conservative",
        cost_tradeoff=toy_cost_tradeoff(),
        default_failure_probability=0.5,
        default_failure_rationale="charter declares a conservative 0.5 prior",
    )
    eng = engine(
        p_fail=None,
        failure_verdict=CalibrationVerdict.INSUFFICIENT_DATA,
        policy=policy,
    )
    recommendation = evaluate((CHEAP_STRONG,), eng=eng, rid="rec-defaulted")
    score = recommendation.scores[0]
    assert score.status is ScoreStatus.DEGRADED
    p_fail = score.component("p_computational_failure")
    assert p_fail.status is ComponentStatus.DEFAULTED
    assert p_fail.value == 0.5
    assert "conservative" in p_fail.detail
    assert any("p_computational_failure=defaulted" in a for a in recommendation.degraded_assumptions)

    # An undeclared fallback is rejected outright.
    _raises(
        ValueError,
        UtilityPolicy,
        policy_id="sloppy",
        default_failure_probability=0.5,
    )


# =====================================================================
# 7-8. Failure information value
# =====================================================================

def test_failure_voi_only_when_scientifically_informative():
    """D: an informative failure adds value."""
    informative = toy_action(
        "probe_boundary",
        family=ActionFamily.EXPLORE,
        reliability=0.6,
        cost=0.5,
        conditional_failure_gain=2.0,
        informative_failure_causes=("numerical",),
    )
    silent = toy_action(
        "probe_silent",
        family=ActionFamily.EXPLORE,
        reliability=0.6,
        cost=0.5,
        conditional_failure_gain=2.0,          # declared, but no informative cause
    )
    # p_cf = 0.5, so expected failure VoI = 2.0 x 0.5 = 1.0 for the informative
    # probe and 0 for the one that declared no informative cause.
    eng = engine(p_fail=0.5)
    recommendation = evaluate((informative, silent), eng=eng, rid="rec-failvoi")
    scores = {s.action_id: s for s in recommendation.scores}

    assert scores["probe_boundary"].component("expected_failure_voi").value == 1.0
    assert scores["probe_silent"].component("expected_failure_voi").value == 0.0
    assert recommendation.chosen_action_id == "probe_boundary"

    # And it matches the independent closed form.
    assert abs(
        scores["probe_boundary"].total - ground_truth_net_value(informative, p_fail=0.5)
    ) < 1e-9


def test_infrastructure_failure_creates_no_scientific_voi():
    """E: a lost node teaches nothing about the physics."""
    infra = toy_action(
        "flaky_node",
        family=ActionFamily.EXPLORE,
        reliability=0.6,
        cost=0.5,
        conditional_failure_gain=5.0,
        informative_failure_causes=("infrastructure",),
    )
    recommendation = evaluate((infra,), eng=engine(p_fail=0.5), rid="rec-infra")
    component = recommendation.scores[0].component("expected_failure_voi")
    assert component.value == 0.0
    assert "infrastructure" in component.detail

    from src.engcore.sria.decision import (
        excluded_failure_causes,
        informative_failure_causes,
    )

    assert informative_failure_causes(infra) == ()
    assert excluded_failure_causes(infra) == ("infrastructure",)


# =====================================================================
# 9-10. Calibration integration
# =====================================================================

def test_cost_is_sourced_from_m2_calibration():
    """Cost comes from the M2 model, not from a number invented here."""
    from src.engcore.sria.calibration import (
        CostModel,
        ComputationalLearningRecord,
        structure_for,
    )
    from src.engcore.sria.calibration.ingest import CAMPAIGN_ENVIRONMENT
    from src.engcore.sria.decision.suppliers import CalibrationCostSupplier
    from src.engcore.sria import Disposition

    training = [
        ComputationalLearningRecord(
            record_id=f"r{i}",
            structure=structure_for(5, 100),
            environment=CAMPAIGN_ENVIRONMENT,
            solver_identity=("solverX", "v1"),
            disposition=Disposition.SUCCESS,
            realized_cost=4.0,
            group_key=f"g{i}",
        )
        for i in range(6)
    ]
    model = CostModel().fit(training, dataset_id="m4-test")

    def build_record(member, snapshot):
        return ComputationalLearningRecord(
            record_id=member.action_id,
            structure=structure_for(5, 100),
            environment=CAMPAIGN_ENVIRONMENT,
            solver_identity=("solverX", "v1"),
            disposition=Disposition.SUCCESS,
            group_key="query",
        )

    supplier = CalibrationCostSupplier(
        model,
        record_builder=build_record,
        verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
    )
    component = supplier.expected_cost(CHEAP_STRONG, toy_snapshot())
    assert component.status is ComponentStatus.AVAILABLE
    assert component.source.startswith("m2:")
    assert abs(component.value - 4.0) < 1e-6      # the fitted median
    assert component.calibration_verdict is CalibrationVerdict.TRUSTED


def test_untrusted_calibration_is_visible_in_the_decision_record():
    """J: degraded calibration propagates into the recommendation."""
    eng = engine(cost_verdict=CalibrationVerdict.UNTRUSTED)
    recommendation = evaluate((CHEAP_STRONG,), eng=eng, rid="rec-untrusted")

    score = recommendation.scores[0]
    assert score.status is ScoreStatus.DEGRADED
    cost = score.component("expected_cost")
    assert cost.status is ComponentStatus.DEGRADED
    assert cost.calibration_verdict is CalibrationVerdict.UNTRUSTED
    assert any("expected_cost=degraded" in a for a in recommendation.degraded_assumptions)

    reloaded = DecisionRecommendation.from_dict(
        json.loads(json.dumps(recommendation.to_dict()))
    )
    assert reloaded.degraded_assumptions == recommendation.degraded_assumptions


def test_insufficient_failure_calibration_reports_unavailable():
    """INSUFFICIENT_DATA is distinct from a low probability."""
    from src.engcore.sria.decision.suppliers import CalibrationFailureSupplier

    supplier = CalibrationFailureSupplier(
        None,
        verdict=CalibrationVerdict.INSUFFICIENT_DATA,
        insufficient_reason="corpus contains zero failures",
    )
    component = supplier.computational_failure_probability(
        CHEAP_STRONG, toy_snapshot()
    )
    assert component.status is ComponentStatus.UNAVAILABLE
    assert component.value is None
    assert "zero failures" in component.detail


# =====================================================================
# 11. Strategy identity is not fidelity
# =====================================================================

def test_strategy_identity_cannot_masquerade_as_fidelity():
    """M2.1's boundary still holds when a proposal asks for a fidelity rung."""
    from src.engcore.sria.calibration import (
        FidelityRung,
        FidelitySemanticError,
        assert_not_a_strategy_identity,
    )

    _raises(FidelitySemanticError, assert_not_a_strategy_identity, "cmaes")
    _raises(
        FidelitySemanticError,
        FidelityRung,
        rung_id="stacked_v0301",
        rank=0,
        model_ref="toy.model",
    )
    # A proposal may name a rung, but naming a strategy does not create one.
    proposal = ActionProposal(
        family=ActionFamily.CHARACTERIZE,
        target_ref="theta",
        rationale="low-fidelity screen",
        required_fidelity="cmaes",
    )
    assert proposal.required_fidelity == "cmaes"
    _raises(
        FidelitySemanticError,
        assert_not_a_strategy_identity,
        proposal.required_fidelity,
    )


# =====================================================================
# 12-13. Composite actions
# =====================================================================

def composite(dependence=OutcomeDependence.UNDECLARED, aggregation=CostAggregation.SUM, **kw):
    members = (
        toy_action("pair_lo", family=ActionFamily.DISCRIMINATE, reliability=0.7, cost=0.5),
        toy_action("pair_hi", family=ActionFamily.DISCRIMINATE, reliability=0.9, cost=1.5),
    )
    return CompositeAction(
        composite_id="pair",
        proposal=ActionProposal(
            family=ActionFamily.DISCRIMINATE,
            target_ref="theta",
            rationale="paired low/high evaluation",
        ),
        members=members,
        order=kw.get("order", ExecutionOrder.SEQUENTIAL),
        cost_aggregation=aggregation,
        declared_total_cost=kw.get("declared_total_cost"),
        outcome_dependence=dependence,
        dependence_rationale=kw.get("rationale", "declared by the campaign")
        if dependence is not OutcomeDependence.UNDECLARED
        else "",
    )


def test_composite_cost_semantics_are_explicit():
    member_costs = {"pair_lo": 0.5, "pair_hi": 1.5}

    sequential = composite(
        OutcomeDependence.INDEPENDENT_DECLARED, CostAggregation.SUM
    )
    assert sequential.aggregate_cost(member_costs) == 2.0

    parallel = composite(
        OutcomeDependence.INDEPENDENT_DECLARED,
        CostAggregation.MAX,
        order=ExecutionOrder.PARALLEL,
    )
    assert parallel.aggregate_cost(member_costs) == 1.5

    declared = composite(
        OutcomeDependence.INDEPENDENT_DECLARED,
        CostAggregation.DECLARED,
        declared_total_cost=1.8,
    )
    assert declared.aggregate_cost(member_costs) == 1.8

    # DECLARED without a total, and MAX with sequential order, are refused.
    _raises(
        ValueError,
        composite,
        OutcomeDependence.INDEPENDENT_DECLARED,
        CostAggregation.DECLARED,
    )
    _raises(
        ValueError,
        composite,
        OutcomeDependence.INDEPENDENT_DECLARED,
        CostAggregation.MAX,
        order=ExecutionOrder.SEQUENTIAL,
    )


def test_composite_outcome_dependence_never_defaults_to_independent():
    undeclared = composite(OutcomeDependence.UNDECLARED)
    assert undeclared.outcome_dependence is OutcomeDependence.UNDECLARED
    assert undeclared.assumes_independence is False

    recommendation = evaluate((undeclared,), rid="rec-undeclared")
    score = recommendation.scores[0]
    assert score.status is ScoreStatus.NOT_SCORABLE
    assert "independence" in score.blocking_reason

    # Declaring it makes the composite scorable — and requires a rationale.
    declared = composite(OutcomeDependence.INDEPENDENT_DECLARED)
    assert declared.assumes_independence is True
    ok = evaluate((declared,), rid="rec-declared")
    assert ok.scores[0].is_rankable
    _raises(
        ValueError,
        CompositeAction,
        composite_id="x",
        proposal=declared.proposal,
        members=declared.members,
        outcome_dependence=OutcomeDependence.INDEPENDENT_DECLARED,
        dependence_rationale="",
    )


# =====================================================================
# 14. Mandatory validation cannot be starved
# =====================================================================

def test_validation_budget_is_protected():
    """F: exploration cannot consume the money certification depends on."""
    budget = BudgetPlan(total_budget=5.0, reserved_validation_budget=3.0)
    assert budget.general_pool == 2.0
    assert budget.validation_pool == 3.0

    # An attractive but expensive explore action cannot reach the reservation.
    assert budget.affordable(2.0, family=ActionFamily.EXPLORE) is True
    assert budget.affordable(2.5, family=ActionFamily.EXPLORE) is False
    # Validation may draw on its reservation plus the general pool.
    assert budget.affordable(4.5, family=ActionFamily.VALIDATE) is True

    # greedy: gain 4.9 - cost 2.2 = +2.7, but 2.2 > the 2.0 general pool.
    # validation: gain 3.5 - cost 2.5 = +1.0, affordable from its reservation.
    greedy = toy_action("greedy_explore", family=ActionFamily.EXPLORE, reliability=0.99, cost=2.2)
    validation = toy_action("validate_ob1", family=ActionFamily.VALIDATE, reliability=0.85, cost=2.5)

    # The greedy action genuinely scores higher — it is excluded by the fence,
    # not by being a worse action.
    assert ground_truth_net_value(greedy) > ground_truth_net_value(validation) > 0

    recommendation = evaluate(
        (greedy, validation), budget=budget, rid="rec-budget"
    )
    assert recommendation.chosen_action_id == "validate_ob1"

    # Without the reservation, the greedy action would have won.
    unfenced = BudgetPlan(total_budget=5.0, reserved_validation_budget=0.0)
    assert evaluate(
        (greedy, validation), budget=unfenced, rid="rec-unfenced"
    ).chosen_action_id == "greedy_explore"


def test_validate_generator_skips_satisfied_obligations():
    context = GenerationContext(
        snapshot=toy_snapshot(obligation_state={"ob-1": True, "ob-2": False}),
        validation_targets={"ob-1": "residual_evidence", "ob-2": "scope_validity"},
    )
    candidates = ValidateGenerator().generate(context)
    assert [c.proposal.target_ref for c in candidates] == ["ob-2"]


# =====================================================================
# 15. Stop proposal is not a stop
# =====================================================================

def test_stop_proposal_is_never_a_final_scientific_stop():
    """H: everything scores <= 0 -> STOP_PROPOSAL, and nothing stronger."""
    worthless = toy_action("worthless", family=ActionFamily.EXPLORE, reliability=0.51, cost=5.0)
    recommendation = evaluate((worthless,), rid="rec-stop")

    assert recommendation.outcome is RecommendationOutcome.STOP_PROPOSAL
    assert recommendation.chosen_action_id == ""
    assert recommendation.is_certification is False
    assert "does not assert" in recommendation.reason

    # The vocabulary contains no certification member at all.
    values = {o.value for o in RecommendationOutcome}
    for forbidden in ("validated", "safe_to_stop", "scientifically_complete"):
        assert forbidden not in values
    names = {o.name for o in RecommendationOutcome}
    assert not names & {"VALIDATED", "SAFE_TO_STOP", "SCIENTIFICALLY_COMPLETE"}


# =====================================================================
# 16-17. Provenance and determinism
# =====================================================================

def test_decision_provenance_round_trips():
    recommendation = evaluate(
        SCENARIOS["B_expensive_rejected_for_marginal_gain"]["candidates"],
        rid="rec-prov",
    )
    reloaded = DecisionRecommendation.from_dict(
        json.loads(json.dumps(recommendation.to_dict()))
    )
    assert reloaded.outcome is recommendation.outcome
    assert reloaded.chosen_action_id == recommendation.chosen_action_id
    assert reloaded.snapshot_digest == recommendation.snapshot_digest
    assert len(reloaded.scores) == len(recommendation.scores)
    assert reloaded.scores[0].components

    provenance = recommendation.to_decision_provenance()
    assert provenance.decision_id == "rec-prov"
    assert provenance.belief_snapshot_ref == recommendation.snapshot_digest
    assert provenance.chosen_action == recommendation.chosen_action_id
    assert set(provenance.candidate_actions) == {
        s.action_id for s in recommendation.scores
    }
    assert provenance.policy_id == "toy.policy"
    assert provenance.human_override is False

    from src.engcore.sria.provenance import DecisionProvenance

    assert (
        DecisionProvenance.from_dict(json.loads(json.dumps(provenance.to_dict())))
        == provenance
    )


def test_same_inputs_give_a_deterministic_recommendation():
    candidates = SCENARIOS["A_cheap_loses_to_informative"]["candidates"]
    snapshot = toy_snapshot()
    first = evaluate(candidates, snapshot=snapshot, rid="rec-det")
    second = evaluate(tuple(reversed(candidates)), snapshot=snapshot, rid="rec-det")

    assert first.chosen_action_id == second.chosen_action_id
    assert first.snapshot_digest == second.snapshot_digest
    assert first.to_dict()["chosen_action_id"] == second.to_dict()["chosen_action_id"]

    # Ties break on action id, not on input order.
    tie_a = toy_action("aaa", family=ActionFamily.EXPLORE, reliability=0.8, cost=0.5)
    tie_b = toy_action("bbb", family=ActionFamily.OPTIMIZE, reliability=0.8, cost=0.5)
    assert evaluate((tie_a, tie_b), rid="t1").chosen_action_id == "aaa"
    assert evaluate((tie_b, tie_a), rid="t2").chosen_action_id == "aaa"


def test_belief_snapshot_is_immutable_and_honest_about_gaps():
    snapshot = toy_snapshot()
    assert snapshot.hypothesis_availability is FactorAvailability.UNAVAILABLE
    assert snapshot.parameter_availability is FactorAvailability.UNAVAILABLE
    _raises(Exception, setattr, snapshot, "snapshot_id", "other")

    from src.engcore.sria.decision import BeliefSnapshot

    # Weights without declared availability are refused.
    _raises(
        ValueError,
        BeliefSnapshot,
        snapshot_id="s",
        campaign_id="c",
        hypothesis_weights={"h1": 0.6},
    )
    assert (
        BeliefSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict()))).digest
        == snapshot.digest
    )


# =====================================================================
# 18-19. Trust path and import boundary
# =====================================================================

def test_decision_layer_cannot_touch_the_trust_path():
    """G/18: the ranking layer writes no belief and admits nothing."""
    for path in sorted(DECISION_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {
                    "submit",
                    "update_standing",
                    "authorize_admission",
                    "register_authorization",
                    "_apply",
                }, f"{path.name} calls .{node.attr}"
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "gateway" not in node.module, f"{path.name}: {node.module}"
                assert "admission" not in node.module, f"{path.name}: {node.module}"

    from src.engcore.sria.decision import CandidateEvaluator, UtilityEngine

    for cls in (CandidateEvaluator, UtilityEngine):
        for forbidden in ("submit", "belief", "gateway", "admit", "authorize"):
            assert not hasattr(cls, forbidden)


def test_no_llm_dependency_in_the_decision_layer():
    from src.engcore.sria.trust import assert_no_llm_dependencies, find_forbidden_imports

    assert DECISION_DIR.is_dir()
    assert find_forbidden_imports([DECISION_DIR]) == ()
    assert_no_llm_dependencies([DECISION_DIR])


# =====================================================================
# Family provenance
# =====================================================================

def test_generated_actions_carry_typed_provenance():
    context = build_full_context()
    candidates = generate_candidates(context)
    by_family = {c.family: c for c in candidates}

    discriminate = by_family[ActionFamily.DISCRIMINATE]
    assert "differ by 2" in discriminate.proposal.rationale
    assert any("weights" in a for a in discriminate.proposal.assumptions)
    assert discriminate.proposal.informative_failure_causes == ("numerical",)

    validate = by_family[ActionFamily.VALIDATE]
    assert "not yet satisfied" in validate.proposal.rationale
    assert any("Arbiter" in a for a in validate.proposal.assumptions)

    explore = by_family[ActionFamily.EXPLORE]
    assert explore.proposal.informative_failure_causes == ("numerical",)


def test_duplicate_candidate_ids_are_refused():
    class Twin(ExploreGenerator):
        family = ActionFamily.EXPLORE

    context = GenerationContext(
        snapshot=toy_snapshot(),
        targets={ActionFamily.EXPLORE: ({"action_id": "same"},)},
    )
    _raises(
        ValueError, generate_candidates, context, (ExploreGenerator(), Twin())
    )


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M4 — decision intelligence tests")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"M4 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M4 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
