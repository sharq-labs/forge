"""SRIA V0.1 M4.1 — decision semantics tests.

Runs under pytest, and standalone via
``python -m tests.test_sria_m41_semantics``.

Each test guards a distinction that the arithmetic cannot see: the difference
between "not worth buying" and "could not evaluate", between a solver crashing
and the physics saying no, between a conditional value and an expected one,
and between seconds and utility.
"""

from __future__ import annotations

import json
import sys

from src.engcore.sria import Disposition
from src.engcore.sria.calibration import (
    ComputationalLearningRecord,
    CostModel,
    structure_for,
)
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.calibration.ingest import CAMPAIGN_ENVIRONMENT
from src.engcore.sria.decision import (
    ActionFamily,
    ApplicabilitySupport,
    CalibrationCostSupplier,
    CalibrationState,
    CandidateEvaluator,
    ComponentStatus,
    CostTradeoff,
    DecisionRecommendation,
    MisusedFailureChannel,
    RecommendationOutcome,
    ScoreComponent,
    ScoreStatus,
    UtilityEngine,
    UtilityPolicy,
    misdeclared_scientific_outcomes,
)
from src.engcore.sria.decision.belief_snapshot import BeliefSnapshot

from tests.sria_m4_benchmark import (
    ToyCostSupplier,
    ToyFailureSupplier,
    ToyOutcomeModel,
    ToyTerminalUtility,
    ground_truth_net_value,
    toy_action,
    toy_charter,
    toy_cost_tradeoff,
    toy_snapshot,
)
from tests.test_sria_m4_decision import SCENARIOS, engine, evaluate, objective


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


GOOD = toy_action("good", family=ActionFamily.EXPLORE, reliability=0.9, cost=0.5)
POOR = toy_action("poor", family=ActionFamily.EXPLORE, reliability=0.51, cost=5.0)


class BrokenOutcomeModel(ToyOutcomeModel):
    """Cannot value one specific action — mirrors a missing expectation."""

    def __init__(self, broken_id: str) -> None:
        self._broken = broken_id

    def conditional_success_utility_gain(self, candidate, snapshot, objective):
        if candidate.action_id == self._broken:
            return ScoreComponent(
                name="conditional_success_utility_gain",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source="toy.outcome_model",
                detail="no outcome expectation exists for this action",
            )
        return super().conditional_success_utility_gain(candidate, snapshot, objective)


def engine_with_broken(broken_id: str) -> UtilityEngine:
    return UtilityEngine(
        policy=UtilityPolicy(policy_id="toy.policy", cost_tradeoff=toy_cost_tradeoff()),
        outcome_model=BrokenOutcomeModel(broken_id),
        cost_supplier=ToyCostSupplier(),
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )


# =====================================================================
# 1. STOP requires complete score coverage
# =====================================================================

def test_A_all_candidates_unscorable_is_not_a_stop():
    unknown = engine(p_fail=None, failure_verdict=CalibrationVerdict.INSUFFICIENT_DATA)
    recommendation = evaluate((GOOD, POOR), eng=unknown, rid="rec-A")

    assert recommendation.outcome is RecommendationOutcome.DECISION_INCOMPLETE
    assert recommendation.outcome is not RecommendationOutcome.STOP_PROPOSAL
    assert set(recommendation.unresolved_action_ids) == {"good", "poor"}
    assert recommendation.is_complete is False
    assert "unevaluated" in recommendation.reason


def test_B_one_negative_plus_one_unscorable_is_not_a_stop():
    """The decisive case: a negative score does not license "nothing is worth
    buying" while another candidate remains unevaluated."""
    recommendation = evaluate(
        (POOR, GOOD), eng=engine_with_broken("good"), rid="rec-B"
    )
    scores = {s.action_id: s for s in recommendation.scores}
    assert scores["poor"].is_rankable and scores["poor"].total < 0
    assert scores["good"].status is ScoreStatus.NOT_SCORABLE

    assert recommendation.outcome is RecommendationOutcome.DECISION_INCOMPLETE
    assert recommendation.outcome is not RecommendationOutcome.STOP_PROPOSAL
    assert recommendation.unresolved_action_ids == ("good",)
    assert "complete score coverage" in recommendation.reason


def test_C_all_scorable_and_non_positive_is_a_stop():
    recommendation = evaluate((POOR,), rid="rec-C")
    assert recommendation.outcome is RecommendationOutcome.STOP_PROPOSAL
    assert recommendation.unresolved_action_ids == ()
    assert recommendation.is_complete is True
    assert "every eligible candidate was scored" in recommendation.reason
    assert "does not assert" in recommendation.reason


def test_D_positive_winner_with_unresolved_candidate_is_visibly_partial():
    other = toy_action("other", family=ActionFamily.OPTIMIZE, reliability=0.95, cost=0.5)
    recommendation = evaluate(
        (GOOD, other), eng=engine_with_broken("other"), rid="rec-D"
    )
    assert recommendation.outcome is RecommendationOutcome.PARTIAL_RECOMMENDATION
    assert recommendation.chosen_action_id == "good"
    assert recommendation.unresolved_action_ids == ("other",)
    assert recommendation.is_complete is False
    assert "partial" in recommendation.reason
    assert "could not be evaluated" in recommendation.coverage_caveat

    reloaded = DecisionRecommendation.from_dict(
        json.loads(json.dumps(recommendation.to_dict()))
    )
    assert reloaded.unresolved_action_ids == ("other",)
    assert reloaded.outcome is RecommendationOutcome.PARTIAL_RECOMMENDATION


def test_infeasible_is_excluded_not_unresolved():
    """An infeasible candidate is properly ruled out, so it does not block a stop."""
    from tests.sria_m4_benchmark import gate_forbidding

    blocked = toy_action(
        "blocked", family=ActionFamily.EXPLORE, reliability=0.99, cost=0.1,
        target_ref="forbidden-zone",
    )
    recommendation = evaluate(
        (POOR, blocked),
        eng=engine(gate=gate_forbidding("forbidden-zone")),
        rid="rec-infeasible-stop",
    )
    assert recommendation.outcome is RecommendationOutcome.STOP_PROPOSAL
    assert recommendation.unresolved_action_ids == ()


# =====================================================================
# 2. Computational failure is not a scientific outcome
# =====================================================================

def test_scientific_outcomes_cannot_be_declared_as_execution_failures():
    for cause in ("infeasible", "hypothesis_contradiction", "scientific", "scope"):
        bad = toy_action(
            f"bad_{cause}",
            family=ActionFamily.EXPLORE,
            reliability=0.8,
            cost=0.5,
            conditional_failure_gain=3.0,
            informative_failure_causes=(cause,),
        )
        assert misdeclared_scientific_outcomes(bad) == (cause,)
        _raises(MisusedFailureChannel, evaluate, (bad,), rid=f"rec-{cause}")


def test_only_execution_failures_carry_failure_information():
    from src.engcore.sria.decision import (
        INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES,
        SCIENTIFIC_OUTCOME_CAUSES,
    )

    assert INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES == {
        "numerical",
        "solver",
        "coupling",
    }
    # The two vocabularies are disjoint — nothing can be both.
    assert not (
        INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES & SCIENTIFIC_OUTCOME_CAUSES
    )
    assert "infrastructure" not in INFORMATIVE_COMPUTATIONAL_FAILURE_CAUSES


# =====================================================================
# 3. Failure VoI probability semantics
# =====================================================================

def test_expected_failure_voi_is_conditional_times_probability():
    """Analytic: conditional gain 4.0 at p_cf 0.25 must contribute exactly 1.0."""
    probe = toy_action(
        "probe",
        family=ActionFamily.EXPLORE,
        reliability=0.8,
        cost=0.5,
        conditional_failure_gain=4.0,
        informative_failure_causes=("numerical",),
    )
    recommendation = evaluate((probe,), eng=engine(p_fail=0.25), rid="rec-cond")
    score = recommendation.scores[0]

    failure = score.component("expected_failure_voi")
    assert abs(failure.value - 1.0) < 1e-12       # 4.0 x 0.25
    assert any("weighted by" in a for a in failure.assumptions)

    # No double counting: success term uses (1 - p), failure term uses p.
    gain = score.component("conditional_success_utility_gain").value
    p = score.component("p_computational_failure").value
    assert abs(score.total - (gain * (1 - p) + 4.0 * p - 0.5)) < 1e-12
    assert abs(score.total - ground_truth_net_value(probe, p_fail=0.25)) < 1e-12


def test_failure_voi_scales_with_probability():
    probe = toy_action(
        "probe", family=ActionFamily.EXPLORE, reliability=0.8, cost=0.5,
        conditional_failure_gain=4.0, informative_failure_causes=("numerical",),
    )
    values = {}
    for p in (0.0, 0.5, 1.0):
        score = evaluate((probe,), eng=engine(p_fail=p), rid=f"r{p}").scores[0]
        values[p] = score.component("expected_failure_voi").value
    assert values[0.0] == 0.0
    assert abs(values[0.5] - 2.0) < 1e-12
    assert abs(values[1.0] - 4.0) < 1e-12


def test_failure_voi_unavailable_when_probability_unavailable():
    probe = toy_action(
        "probe", family=ActionFamily.EXPLORE, reliability=0.8, cost=0.5,
        conditional_failure_gain=4.0, informative_failure_causes=("numerical",),
    )
    unknown = engine(p_fail=None, failure_verdict=CalibrationVerdict.INSUFFICIENT_DATA)
    score = evaluate((probe,), eng=unknown, rid="rec-nofail").scores[0]
    assert score.status is ScoreStatus.NOT_SCORABLE
    assert score.component("expected_failure_voi").status is ComponentStatus.UNAVAILABLE


# =====================================================================
# 4. Cost must be converted into terminal-utility units
# =====================================================================

def test_undeclared_cost_tradeoff_makes_formal_voi_unavailable():
    naked = UtilityPolicy(policy_id="toy.naked")     # no tradeoff, no waiver
    assert naked.cost_awareness_declared is False
    eng = UtilityEngine(
        policy=naked,
        outcome_model=ToyOutcomeModel(),
        cost_supplier=ToyCostSupplier(),
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )
    recommendation = evaluate((GOOD,), eng=eng, rid="rec-nolambda")
    assert recommendation.outcome is RecommendationOutcome.DECISION_INCOMPLETE
    assert "cost-to-utility tradeoff" in recommendation.scores[0].blocking_reason


def test_explicit_zero_cost_penalty_is_allowed():
    waived = UtilityPolicy(policy_id="toy.free", zero_cost_penalty=True)
    eng = UtilityEngine(
        policy=waived,
        outcome_model=ToyOutcomeModel(),
        cost_supplier=ToyCostSupplier(),
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )
    score = evaluate((GOOD,), eng=eng, rid="rec-free").scores[0]
    assert score.is_rankable
    penalty = score.component("cost_penalty")
    assert penalty.value == 0.0
    assert "declared zero cost penalty" in penalty.assumptions[0]
    # Cost is ignored entirely, so the score is the raw gain.
    assert abs(score.total - 4.0) < 1e-12

    _raises(
        ValueError,
        UtilityPolicy,
        policy_id="x",
        cost_tradeoff=toy_cost_tradeoff(),
        zero_cost_penalty=True,
    )


def test_unconverted_raw_cost_cannot_enter_a_score():
    """Seconds are not utility: a unit mismatch blocks the score."""
    mismatched = UtilityEngine(
        policy=UtilityPolicy(policy_id="toy.policy", cost_tradeoff=toy_cost_tradeoff()),
        outcome_model=ToyOutcomeModel(),
        cost_supplier=ToyCostSupplier(unit="second"),   # tradeoff converts hours
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )
    recommendation = evaluate((GOOD,), eng=mismatched, rid="rec-units")
    score = recommendation.scores[0]
    assert score.status is ScoreStatus.NOT_SCORABLE
    penalty = score.component("cost_penalty")
    assert penalty.status is ComponentStatus.UNAVAILABLE
    assert "unconverted" in penalty.detail

    _raises(
        ValueError, toy_cost_tradeoff().penalty, 1.0, cost_unit="second"
    )


def test_cost_tradeoff_carries_its_provenance():
    tradeoff = toy_cost_tradeoff()
    assert tradeoff.cost_unit == "hour"
    assert tradeoff.utility_reference
    assert tradeoff.source
    assert tradeoff.assumptions

    for missing in ("cost_unit", "utility_reference", "source"):
        kwargs = dict(
            rate=1.0, cost_unit="hour", utility_reference="u", source="s"
        )
        kwargs[missing] = "  "
        _raises(ValueError, CostTradeoff, **kwargs)

    score = evaluate((GOOD,), rid="rec-tradeoff").scores[0]
    penalty = score.component("cost_penalty")
    assert penalty.unit == tradeoff.utility_reference
    assert any("utility per hour" in a for a in penalty.assumptions)


# =====================================================================
# 5. Calibration applicability / support
# =====================================================================

def cost_model_and_builder():
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
    model = CostModel().fit(training, dataset_id="m41")

    def builder(structure=None, environment=None, solver="solverX"):
        def build(member, snapshot):
            return ComputationalLearningRecord(
                record_id=member.action_id,
                structure=structure or structure_for(5, 100),
                environment=environment or CAMPAIGN_ENVIRONMENT,
                solver_identity=(solver, "v1"),
                disposition=Disposition.SUCCESS,
                group_key="query",
            )

        return build

    return model, builder


def support_envelope():
    return ApplicabilitySupport(
        structure_digests=frozenset({structure_for(5, 100).digest}),
        environment_digests=frozenset({CAMPAIGN_ENVIRONMENT.digest}),
        solver_ids=frozenset({"solverX"}),
        description="BBOB corpus, one machine, known strategies",
    )


def test_supported_query_is_decision_grade():
    model, builder = cost_model_and_builder()
    supplier = CalibrationCostSupplier(
        model,
        record_builder=builder(),
        verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
        support=support_envelope(),
    )
    component = supplier.expected_cost(GOOD, toy_snapshot())
    assert component.status is ComponentStatus.AVAILABLE
    assert abs(component.value - 4.0) < 1e-6


def test_unseen_environment_cannot_appear_trusted():
    """No cross-hardware evidence exists, so a new machine is not supported."""
    from src.engcore.sria.signatures import EnvironmentSignature

    other_machine = EnvironmentSignature(
        hardware_class="cluster.epyc", precision="float64"
    )
    model, builder = cost_model_and_builder()
    supplier = CalibrationCostSupplier(
        model,
        record_builder=builder(environment=other_machine),
        verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
        support=support_envelope(),
    )
    component = supplier.expected_cost(GOOD, toy_snapshot())
    assert component.status is ComponentStatus.DEGRADED
    assert component.status is not ComponentStatus.AVAILABLE
    assert any("outside support" in a for a in component.assumptions)
    assert "cross-hardware" in " ".join(component.assumptions)


def test_unsupported_solver_is_visibly_degraded():
    model, builder = cost_model_and_builder()
    supplier = CalibrationCostSupplier(
        model,
        record_builder=builder(solver="brand_new_solver"),
        verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
        support=support_envelope(),
    )
    component = supplier.expected_cost(GOOD, toy_snapshot())
    assert component.status is ComponentStatus.DEGRADED
    assert "not in the training corpus" in " ".join(component.assumptions)


def test_incompatible_signature_version_is_degraded():
    model, builder = cost_model_and_builder()
    supplier = CalibrationCostSupplier(
        model,
        record_builder=builder(),
        verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
        support=support_envelope(),
    )
    stale = BeliefSnapshot(
        snapshot_id="stale",
        campaign_id="toy-campaign",
        calibration=CalibrationState(
            cost_verdict=CalibrationVerdict.TRUSTED,
            structure_signature_version=999,
        ),
    )
    component = supplier.expected_cost(GOOD, stale)
    assert component.status is ComponentStatus.DEGRADED
    assert "signature version" in " ".join(component.assumptions)


def test_degraded_support_propagates_into_the_recommendation():
    model, builder = cost_model_and_builder()
    from src.engcore.sria.signatures import EnvironmentSignature

    supplier = CalibrationCostSupplier(
        model,
        record_builder=builder(
            environment=EnvironmentSignature(
                hardware_class="cluster.epyc", precision="float64"
            )
        ),
        verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
        support=support_envelope(),
    )
    eng = UtilityEngine(
        policy=UtilityPolicy(policy_id="toy.policy", cost_tradeoff=toy_cost_tradeoff()),
        outcome_model=ToyOutcomeModel(),
        cost_supplier=supplier,
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )
    recommendation = evaluate((GOOD,), eng=eng, rid="rec-support")
    assert recommendation.scores[0].status is ScoreStatus.DEGRADED
    assert any(
        "expected_cost=degraded" in a for a in recommendation.degraded_assumptions
    )


# =====================================================================
# 6. Snapshot / replay semantics
# =====================================================================

def test_snapshot_pins_the_calibration_identity():
    pinned = CalibrationState(
        cost_model_id="cost.hierarchical",
        cost_model_version="cost/hierarchical-log-median/1",
        cost_dataset_id="corpus-v1",
        cost_verdict=CalibrationVerdict.TRUSTED,
    )
    snapshot = BeliefSnapshot(
        snapshot_id="s", campaign_id="c", calibration=pinned
    )
    assert pinned.pin[0] == "cost/hierarchical-log-median/1"
    assert pinned.pin[1] == "corpus-v1"

    # The pin is inside the digest, so a different model identity is a
    # different snapshot — an executable replay cannot silently drift.
    moved = BeliefSnapshot(
        snapshot_id="s",
        campaign_id="c",
        calibration=CalibrationState(
            cost_model_id="cost.hierarchical",
            cost_model_version="cost/hierarchical-log-median/2",
            cost_dataset_id="corpus-v2",
            cost_verdict=CalibrationVerdict.TRUSTED,
        ),
    )
    assert snapshot.digest != moved.digest
    assert (
        BeliefSnapshot.from_dict(json.loads(json.dumps(snapshot.to_dict()))).digest
        == snapshot.digest
    )


def test_calibration_mutation_after_snapshot_does_not_change_the_record():
    """Regression: refitting the model later must not rewrite an old decision."""
    model, builder = cost_model_and_builder()
    supplier = CalibrationCostSupplier(
        model, record_builder=builder(), verdict=CalibrationVerdict.TRUSTED,
        cost_unit="hour",
    )
    eng = UtilityEngine(
        policy=UtilityPolicy(policy_id="toy.policy", cost_tradeoff=toy_cost_tradeoff()),
        outcome_model=ToyOutcomeModel(),
        cost_supplier=supplier,
        failure_supplier=ToyFailureSupplier(0.0, CalibrationVerdict.TRUSTED),
    )
    from src.engcore.sria.decision import pin_decision_basis

    evaluator = CandidateEvaluator(eng)
    pinned = pin_decision_basis(
        toy_snapshot(),
        evaluator.build_manifest(
            candidates=(GOOD,), snapshot=toy_snapshot(), objective=objective()
        ),
    )
    before = evaluator.evaluate(
        recommendation_id="rec-pin",
        candidates=(GOOD,),
        snapshot=pinned,
        objective=objective(),
    )
    recorded_cost = before.scores[0].component("expected_cost").value
    recorded_digest = before.snapshot_digest

    # Now mutate calibration memory: refit on much more expensive runs.
    refit = [
        ComputationalLearningRecord(
            record_id=f"n{i}",
            structure=structure_for(5, 100),
            environment=CAMPAIGN_ENVIRONMENT,
            solver_identity=("solverX", "v1"),
            disposition=Disposition.SUCCESS,
            realized_cost=400.0,
            group_key=f"g{i}",
        )
        for i in range(6)
    ]
    model.fit(refit, dataset_id="m41-refit")

    # The stored record is unchanged — this is what audit replay guarantees.
    assert before.scores[0].component("expected_cost").value == recorded_cost
    assert before.snapshot_digest == recorded_digest
    reloaded = DecisionRecommendation.from_dict(
        json.loads(json.dumps(before.to_dict()))
    )
    assert reloaded.scores[0].component("expected_cost").value == recorded_cost

    # M4.1 recorded here that a fresh evaluation against the same snapshot
    # silently produced a different number, and that the pins only made the
    # divergence *detectable*. M4.3/M4.4 closed that: reusing the basis the
    # first decision was scored against is now refused outright.
    from src.engcore.sria.decision import CoherenceStatus

    stale = evaluator.evaluate(
        recommendation_id="rec-pin",
        candidates=(GOOD,),
        snapshot=pinned,
        objective=objective(),
    )
    assert stale.outcome is RecommendationOutcome.STATE_INCOHERENT
    # The refit also moved the dataset id, so the identity changed too.
    assert stale.coherence.status is CoherenceStatus.DEPENDENCY_MISMATCH
    assert "cost_model:cost.hierarchical" in {
        c.field for c in stale.coherence.conflicts
    }
    assert stale.scores == ()

    # Deciding on the refit model remains available — with a new basis.
    after = evaluate((GOOD,), eng=eng, snapshot=toy_snapshot(), rid="rec-new")
    assert after.scores[0].component("expected_cost").value != recorded_cost
    assert after.snapshot_digest != recorded_digest


# =====================================================================
# 7. Validation-budget claim (scope statement, tests unchanged)
# =====================================================================

def test_validation_budget_claim_is_scoped_to_reservation_only():
    """M4 protects the reserved budget; it makes no scheduling guarantee."""
    from src.engcore.sria.decision import BudgetPlan

    budget = BudgetPlan(total_budget=5.0, reserved_validation_budget=3.0)
    assert budget.general_pool == 2.0
    assert budget.validation_pool == 3.0
    # There is no scheduler, no queue, no liveness machinery in M4.
    for forbidden in ("schedule", "next_step", "enqueue", "deadline"):
        assert not hasattr(budget, forbidden)
    assert not hasattr(CandidateEvaluator, "schedule")


# =====================================================================
# 8. The predeclared benchmark is unchanged
# =====================================================================

def test_original_benchmark_still_holds_after_the_corrections():
    from src.engcore.sria.decision import information_only_ranking

    differed, agreed = [], []
    for name, spec in SCENARIOS.items():
        recommendation = evaluate(spec["candidates"], rid=f"rec41-{name}")
        assert recommendation.outcome is RecommendationOutcome.RECOMMEND_ACTION, name
        assert recommendation.is_complete is True

        sria = recommendation.chosen_action_id
        info = information_only_ranking(recommendation.scores)[0].action_id
        assert sria == spec["sria_winner"], name
        assert info == spec["info_winner"], name

        for score in recommendation.scores:
            candidate = next(
                c for c in spec["candidates"] if c.action_id == score.action_id
            )
            assert abs(score.total - ground_truth_net_value(candidate)) < 1e-9

        (differed if sria != info else agreed).append(name)

    assert differed == ["B_expensive_rejected_for_marginal_gain"]
    assert len(agreed) == 2


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M4.1 — decision semantics tests")
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
        print(f"M4.1 tests: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M4.1 tests: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
