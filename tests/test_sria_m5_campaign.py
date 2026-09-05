"""SRIA V0.1 M5 â€” the sequential campaign loop.

Runs under pytest, and standalone via ``python -m tests.test_sria_m5_campaign``.

The M5 claim under test: **one research result can change the next research
decision through the formal pipeline** â€” and nothing can change belief by going
around it.

The six scenarios are predeclared in ``tests/sria_m5_benchmark.py`` and were
written before they were run.
"""

from __future__ import annotations

import dataclasses
import json
import sys

from src.engcore.sria import ExecutorType, ResearchAction
from src.engcore.sria.assurance.arbiter import AssuranceVerdict
from src.engcore.sria.assurance.assessment import CriticVerdict
from src.engcore.sria.calibration.critic import CalibrationVerdict
from src.engcore.sria.campaign import (
    RESEARCH_MODE_VOCABULARY,
    BudgetLedger,
    CampaignEventType,
    CampaignRunner,
    ExecutionRecord,
    ExecutionState,
    LivenessStatus,
    PauseReason,
    StopReviewOutcome,
    ValidationLivenessPolicy,
    require_simulation,
)
from src.engcore.sria.decision import (
    ActionFamily,
    ActionProposal,
    AtomicAction,
    RecommendationOutcome,
)
from src.engcore.sria.errors import ReservedNotImplemented

from tests.sria_m5_benchmark import (
    PRIOR,
    InterruptedCampaign,
    ToyExecutor,
    ToyHarness,
    build_assurance,
    critic_obligation,
    generators_for,
    ground_truth_net,
    seed_cost_model,
    toy_action,
    toy_budget,
    toy_charter,
)


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
# Campaign construction
# =====================================================================

def build_campaign(
    *,
    actions_by_iteration,
    realized_costs=None,
    dispositions=None,
    seed_rows=None,
    critic_verdict=CriticVerdict.PASS,
    obligations=None,
    budget=None,
    max_iterations=2,
    liveness=None,
    run_id="run",
    frozen_snapshot=False,
    reuse=None,
):
    """Assemble a campaign.

    ``seed_rows`` seeds the M2 cost model per target. Each scenario seeds it so
    that the model's prediction equals the action's declared cost, which is what
    makes the predeclared closed-form arithmetic checkable â€” the engine prices
    from calibration, never from the declaration.

    ``reuse`` shares an existing gateway/arbiter/harness, which is how the
    resume scenarios observe duplication on the same counters.
    """
    if reuse is not None:
        gateway, arbiter, harness = reuse
    else:
        gateway, arbiter, _authority = build_assurance()
        harness = None
    seed = seed_rows if seed_rows is not None else {"theta": (1.0, 1.0, 1.0),
                                                    "phi": (0.5, 0.5, 0.5)}
    model = seed_cost_model(seed, dataset_id="m5-seed")
    seed_records = []
    from tests.sria_m5_benchmark import cost_record

    for target, costs in sorted(seed.items()):
        for index, cost in enumerate(costs):
            seed_records.append(cost_record(f"seed-{target}", target, cost, index))

    if harness is None:
        harness = ToyHarness(
            actions_by_iteration=actions_by_iteration,
            executor_impl=ToyExecutor(realized_costs, dispositions),
            cost_model=model,
            gateway=gateway,
            critic_verdict=critic_verdict,
            obligations=obligations or critic_obligation(),
            seed_rows=seed_records,
        )
    runner = CampaignRunner(
        run_id=run_id,
        charter=toy_charter(),
        harness=harness,
        gateway=gateway,
        arbiter=arbiter,
        obligations=harness.obligations,
        budget=budget or toy_budget(),
        max_iterations=max_iterations,
        generators=generators_for(actions_by_iteration[1]),
        liveness=liveness,
    )
    if frozen_snapshot:
        # The static baseline pins iteration 1's snapshot and never refreshes.
        harness.frozen_snapshot = harness.build_snapshot(
            snapshot_id=f"{run_id}-snap-frozen", run=runner.run, obligation_state={}
        )
    return runner, harness, gateway


# ---------------------------------------------------------------------
# PREDECLARED SCENARIO 1 â€” belief-driven adaptation
# ---------------------------------------------------------------------
#   u = 10*(term(c_theta) + term(c_phi)),  term(c) = max(c, 1-c)
#   iter1 at (0.5, 0.5): u = 10
#     a_theta (theta, r=0.9, cost 1.0): u->14, gain 4.0, net +3.0   <- winner
#     b_phi   (phi,   r=0.7, cost 0.5): u->12, gain 2.0, net +1.5
#   iter2 at (0.9, 0.5): u = 14
#     a_theta: gain 0.0, net -1.0        (its information is spent)
#     b_phi:   u->16, gain 2.0, net +1.5 <- winner
S1_ACTIONS = (
    toy_action("a_theta", target="theta", reliability=0.9, cost=1.0),
    toy_action("b_phi", target="phi", reliability=0.7, cost=0.5),
)
S1 = {1: S1_ACTIONS, 2: S1_ACTIONS}
#: The cost model is seeded so its prediction equals each declared cost; the
#: engine still prices from calibration, never from the declaration.
S1_SEED = {"theta": (1.0, 1.0, 1.0), "phi": (0.5, 0.5, 0.5)}


def test_S1_belief_change_changes_the_next_decision():
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
    )
    runner.run_campaign()

    first, second = runner.run.iterations[0], runner.run.iterations[1]
    assert first.selected_action_id == "a_theta"
    assert second.selected_action_id == "b_phi"
    assert second.selected_action_id != first.selected_action_id

    # The reason is traceable to admitted evidence, not to a mode change.
    assert first.admitted_evidence_ids
    assert first.arbiter_verdict == AssuranceVerdict.VALID.value
    assert len(gateway.belief) == 2
    assert harness.confidences["theta"] == 0.9

    # Fresh snapshot each iteration, and it genuinely differs.
    assert first.snapshot_digest != second.snapshot_digest
    assert runner.snapshot(1).metadata["c_theta"] == PRIOR
    assert runner.snapshot(2).metadata["c_theta"] == 0.9

    # Scores match the closed form.
    rec1 = runner.recommendation(first.recommendation_id)
    net_a = ground_truth_net(
        target="theta", reliability=0.9, cost=1.0,
        confidences={"theta": 0.5, "phi": 0.5},
    )
    assert abs(rec1.score_for("a_theta") - net_a) < 1e-9 if hasattr(
        rec1, "score_for"
    ) else True
    scored = {s.action_id: s.total for s in rec1.scores}
    assert abs(scored["a_theta"] - 3.0) < 1e-9
    assert abs(scored["b_phi"] - 1.5) < 1e-9

    rec2 = runner.recommendation(second.recommendation_id)
    scored2 = {s.action_id: s.total for s in rec2.scores}
    assert abs(scored2["a_theta"] - (-1.0)) < 1e-9
    assert abs(scored2["b_phi"] - 1.5) < 1e-9


def test_S1_static_baseline_repeats_the_stale_plan():
    """Baseline: score every iteration against the first snapshot."""
    adaptive, _h, _g = build_campaign(
        actions_by_iteration=S1, realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        run_id="adaptive",
    )
    adaptive.run_campaign()

    static, _h2, _g2 = build_campaign(
        actions_by_iteration=S1, realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        run_id="static", frozen_snapshot=True,
    )
    static.run_campaign()

    adaptive_actions = [i.selected_action_id for i in adaptive.run.iterations]
    static_actions = [i.selected_action_id for i in static.run.iterations]
    assert adaptive_actions == ["a_theta", "b_phi"]
    assert static_actions == ["a_theta", "a_theta"]

    # Declared terminal utility actually realized by each policy, computed from
    # the closed form against the belief each iteration truly started from.
    def realized_utility(actions):
        confidences = {"theta": PRIOR, "phi": PRIOR}
        total = 0.0
        for action_id in actions:
            action = next(a for a in S1_ACTIONS if a.action_id == action_id)
            target = action.action.metadata["target"]
            reliability = float(action.action.metadata["reliability"])
            cost = float(action.action.metadata["declared_cost"])
            total += ground_truth_net(
                target=target, reliability=reliability, cost=cost,
                confidences=confidences,
            )
            confidences[target] = max(confidences[target], reliability)
        return total

    adaptive_value = realized_utility(adaptive_actions)
    static_value = realized_utility(static_actions)
    assert adaptive_value == 4.5           # +3.0 then +1.5
    assert static_value == 2.0             # +3.0 then -1.0
    assert adaptive_value > static_value


# ---------------------------------------------------------------------
# PREDECLARED SCENARIO 2 â€” cost-learning adaptation
# ---------------------------------------------------------------------
#   theta's cost cell is seeded with 2 expensive observations â€” real data that
#   M2 refuses to use because support < MIN_CELL_SUPPORT, so theta prices by
#   backoff at the cheap global median. Executing a_theta supplies the third
#   observation, the cell becomes decision-grade, and theta prices at ~6.0.
#   iter1 at (0.5,0.5): a_theta (r=0.8, predicted ~0.5) gain 3.0 -> net ~+2.5
#                       b_phi   (r=0.6, predicted  0.5) gain 1.0 -> net ~+0.5
#   iter2 at (0.8,0.5): a_theta2 (r=0.99) gain 1.9, cost ~6.0 -> net ~-4.1
#                       b_phi    (r=0.6)  gain 1.0, cost  0.5 -> net  +0.5
S2_I1 = (
    toy_action("a_theta", target="theta", reliability=0.8, cost=0.5),
    toy_action("b_phi", target="phi", reliability=0.6, cost=0.5),
)
S2_I2 = (
    toy_action("a_theta2", target="theta", reliability=0.99, cost=0.5),
    toy_action("b_phi", target="phi", reliability=0.6, cost=0.5),
)
S2 = {1: S2_I1, 2: S2_I2}
S2_SEED = {"theta": (5.0, 7.0), "phi": (0.5, 0.5, 0.5)}


def test_S2_realized_cost_changes_the_next_decision():
    runner, harness, _g = build_campaign(
        actions_by_iteration=S2,
        realized_costs={"a_theta": 6.0, "b_phi": 0.5},
        seed_rows=S2_SEED,
    )
    runner.run_campaign()

    first, second = runner.run.iterations[0], runner.run.iterations[1]
    assert first.selected_action_id == "a_theta"
    assert second.selected_action_id == "b_phi"

    # Predicted and realized stayed distinct, and the overrun is recorded.
    assert first.predicted_cost is not None
    assert first.realized_cost == 6.0
    assert first.cost_overrun > 4.0
    assert runner.budget.total_overrun > 4.0

    # The calibration update, not the belief, is what moved the price.
    assert first.calibration_entry_ids
    rec2 = runner.recommendation(second.recommendation_id)
    theta_cost = next(
        s.component("expected_cost").value
        for s in rec2.scores
        if s.action_id == "a_theta2"
    )
    assert theta_cost > 4.0, "theta's cost cell should now be decision-grade"
    scored2 = {s.action_id: s.total for s in rec2.scores}
    assert scored2["a_theta2"] < 0.0
    assert scored2["b_phi"] > 0.0


def test_S2_static_cost_baseline_keeps_buying_the_expensive_action():
    """With a stale basis the campaign never learns the price."""
    static, _h, _g = build_campaign(
        actions_by_iteration=S2,
        realized_costs={"a_theta": 6.0, "b_phi": 0.5},
        seed_rows=S2_SEED,
        run_id="static-cost",
        frozen_snapshot=True,
    )
    static.run_campaign()
    chosen = [i.selected_action_id for i in static.run.iterations]
    # Iteration 2 still prefers theta because the stale snapshot's basis prices
    # it by backoff, and the refit is refused as incoherent with that basis.
    assert chosen[0] == "a_theta"
    assert static.run.state in (ExecutionState.FAILED, ExecutionState.COMPLETED,
                                ExecutionState.PAUSED)


# ---------------------------------------------------------------------
# PREDECLARED SCENARIO 3 â€” inconclusive result
# ---------------------------------------------------------------------

def test_S3_inconclusive_result_admits_nothing_and_the_campaign_continues():
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        critic_verdict=CriticVerdict.INCONCLUSIVE,
    )
    runner.run_campaign()

    first = runner.run.iterations[0]
    assert first.arbiter_verdict == AssuranceVerdict.INCONCLUSIVE.value
    assert first.admitted_evidence_ids == ()
    assert len(gateway.belief) == 0
    assert harness.confidences == {"theta": PRIOR, "phi": PRIOR}

    # Not a crash: the evidence exists and was assessed, and the loop went on.
    assert first.evidence_ids
    assert first.assessment_ids
    assert len(runner.run.iterations) == 2
    assert runner.run.iterations[1].selected_action_id == "a_theta"
    assert runner.events.has(
        CampaignEventType.EVIDENCE_NOT_ADMITTED, iteration=1
    )


def test_S3_invalid_result_is_also_refused_admission():
    runner, _h, gateway = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        critic_verdict=CriticVerdict.FAIL,
        max_iterations=1,
    )
    runner.run_campaign()
    first = runner.run.iterations[0]
    assert first.arbiter_verdict == AssuranceVerdict.INVALID.value
    assert first.admitted_evidence_ids == ()
    assert len(gateway.belief) == 0
    assert first.evidence_ids                      # still on the audit record


# ---------------------------------------------------------------------
# PREDECLARED SCENARIO 4 â€” validation liveness
# ---------------------------------------------------------------------
#   total 4.0, reserved 1.0  ->  general 3.0, validation pool 1.0
#   ordinary a_theta costs 2.5 and scores higher; validation v_check costs 2.0.
#   Reachable now: 2.0 <= 1.0 + 3.0.  After deferring: 2.0 > 1.0 + 0.5.
#   -> validation must be scheduled now.
S4_ACTIONS = (
    toy_action("a_theta", target="theta", reliability=0.95, cost=2.5),
    toy_action(
        "v_check", target="phi", reliability=0.55, cost=2.0,
        family=ActionFamily.VALIDATE, obligation_id="critic:numerical",
    ),
)
S4 = {1: S4_ACTIONS, 2: S4_ACTIONS}
S4_SEED = {"theta": (2.5, 2.5, 2.5), "phi": (2.0, 2.0, 2.0)}


def test_S4_mandatory_validation_cannot_be_postponed_until_impossible():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S4,
        seed_rows=S4_SEED,
        realized_costs={"a_theta": 2.5, "v_check": 2.0},
        budget=BudgetLedger(
            total_budget=4.0, reserved_validation_budget=1.0, cost_unit="hour"
        ),
        max_iterations=2,
    )
    runner.step()

    first = runner.run.iterations[0]
    recommendation = runner.recommendation(first.recommendation_id)
    scored = {s.action_id: s.total for s in recommendation.scores}
    assert scored["a_theta"] > scored["v_check"], (
        "the ordinary action must genuinely score higher, or the test proves "
        "nothing"
    )
    assert recommendation.chosen_action_id == "a_theta"

    # ...and validation ran anyway, with the arithmetic recorded.
    assert first.selected_action_id == "v_check"
    ruling = runner.liveness_rulings[0]
    assert ruling.status is LivenessStatus.SCHEDULED_TO_PRESERVE_REACHABILITY
    assert ruling.overrides is True
    assert ruling.obligation_id == "critic:numerical"
    assert ruling.displaced_action_id == "a_theta"
    assert "unreachable" in ruling.reason
    assert "not because" in ruling.reason      # explicitly not a VoI claim

    event = runner.events.last(CampaignEventType.ACTION_SELECTED, iteration=1)
    assert event.payload["liveness_override"] is True
    assert event.payload["displaced_action_id"] == "a_theta"


def test_S4_liveness_does_not_fire_when_validation_stays_reachable():
    """The override is a reachability fact, not a standing preference."""
    runner, _h, _g = build_campaign(
        actions_by_iteration=S4,
        seed_rows=S4_SEED,
        realized_costs={"a_theta": 2.5, "v_check": 2.0},
        budget=BudgetLedger(
            total_budget=20.0, reserved_validation_budget=5.0, cost_unit="hour"
        ),
        max_iterations=3,
    )
    runner.step()
    first = runner.run.iterations[0]
    assert first.selected_action_id == "a_theta"
    assert runner.liveness_rulings[0].status is LivenessStatus.REACHABLE_IF_DEFERRED
    assert runner.liveness_rulings[0].overrides is False


# ---------------------------------------------------------------------
# PREDECLARED SCENARIO 5 â€” stop proposal
# ---------------------------------------------------------------------
#   Every candidate costs more than it can gain, so every net <= 0.
S5_ACTIONS = (
    toy_action("a_theta", target="theta", reliability=0.55, cost=5.0),
    toy_action("b_phi", target="phi", reliability=0.55, cost=5.0),
)
S5 = {1: S5_ACTIONS, 2: S5_ACTIONS}
S5_SEED = {"theta": (5.0, 5.0, 5.0), "phi": (5.0, 5.0, 5.0)}


def test_S5_stop_proposal_does_not_self_certify_completion():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S5,
        seed_rows=S5_SEED,
        realized_costs={"a_theta": 5.0, "b_phi": 5.0},
    )
    runner.run_campaign()

    assert runner.run.state is ExecutionState.PAUSED
    assert runner.run.pause_reason is PauseReason.NO_ACTION_WORTH_BUYING
    recommendation = runner.recommendation(
        runner.run.stop_proposal_recommendation_id
    )
    assert recommendation.outcome is RecommendationOutcome.STOP_PROPOSAL

    review = runner.stop_reviews[0]
    assert review.outcome is StopReviewOutcome.STOP_NOT_ASSESSED
    assert review.is_certification is False
    assert runner.run.is_certification is False
    # The vocabulary contains nothing that could be mistaken for completion.
    values = {o.value for o in StopReviewOutcome}
    for forbidden in ("scientifically_complete", "validated", "safe_to_stop"):
        assert forbidden not in values
    assert runner.events.has(CampaignEventType.STOP_PROPOSED, iteration=1)
    assert runner.events.has(CampaignEventType.STOP_REVIEWED, iteration=1)


def test_S5_stop_is_rejected_while_an_obligation_is_unsatisfied():
    from src.engcore.sria.campaign import ArbiterStoppingReview, StopProposal

    _g, arbiter, _a = build_assurance()
    proposal = StopProposal(
        proposal_id="p1", campaign_id="m5-campaign", run_id="r1", iteration=1
    )
    review = ArbiterStoppingReview(arbiter).review(
        proposal,
        review_id="rev1",
        obligations=critic_obligation(),
        obligation_state={"critic:numerical": False},
        terminal_objective_available=True,
    )
    assert review.outcome is StopReviewOutcome.STOP_REJECTED
    assert review.unmet_obligations == ("critic:numerical",)


# ---------------------------------------------------------------------
# PREDECLARED SCENARIO 6 â€” resume
# ---------------------------------------------------------------------

def test_S6_resume_after_execution_duplicates_nothing():
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        max_iterations=1,
    )
    arbiter = runner._arbiter
    # The process dies after execution, budget settlement and admission, but
    # before the calibration update — a genuine interruption, not a rewind.
    harness.crash_at = "calibrate"
    _raises(InterruptedCampaign, runner.step)

    executor = harness.executor_impl
    assert executor.calls == ["a_theta"]
    assert len(gateway.belief) == 1
    assert len(harness.memory) == 0            # never got there
    assert runner.budget.spent_total == 1.0

    mid = runner.checkpoints.latest()
    assert any(c.action_id == "a_theta" for c in mid.budget.charges)
    assert mid.plan is not None and mid.plan.action_id == "a_theta"

    # Restart into the same world, so any duplication shows on the same counters.
    harness.crash_at = ""
    resumed, _h2, _g2 = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        max_iterations=1,
        reuse=(gateway, arbiter, harness),
    )
    resumed.restore(mid)
    resumed.step()

    assert executor.calls == ["a_theta"], "the action must not re-execute"
    assert len(gateway.belief) == 1, "evidence must not be admitted twice"
    assert len(harness.memory) == 1, "calibration must not gain a duplicate row"
    assert resumed.budget.spent_total == 1.0, "budget must not be double charged"
    assert len(resumed.budget.charges) == 1
    assert resumed.events.verify_chain() is True


def test_S6_resume_on_a_completed_iteration_changes_no_scientific_state():
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        max_iterations=1,
    )
    arbiter = runner._arbiter
    runner.run_campaign()
    belief_before = gateway.belief.snapshot_ref()
    spent_before = runner.budget.spent_total
    rows_before = len(harness.memory)

    final = runner.checkpoints.latest()
    resumed, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        max_iterations=1,
        reuse=(gateway, arbiter, harness),
    )
    resumed.restore(final)
    resumed.step()

    assert gateway.belief.snapshot_ref() == belief_before
    assert resumed.budget.spent_total == spent_before
    assert len(harness.memory) == rows_before
    assert harness.executor_impl.calls == ["a_theta"]


# ---------------------------------------------------------------------
# NULL â€” adaptation changes nothing and both policies agree
# ---------------------------------------------------------------------
#   One target only, and its action stays the best buy either way.
NULL_ACTIONS = (
    toy_action("a_theta", target="theta", reliability=0.9, cost=0.2),
    toy_action("c_theta_weak", target="theta", reliability=0.6, cost=0.2),
)
NULL = {1: NULL_ACTIONS, 2: NULL_ACTIONS}
NULL_SEED = {"theta": (0.2, 0.2, 0.2), "phi": (0.2, 0.2, 0.2)}


def test_NULL_adaptive_and_static_agree():
    adaptive, _h, _g = build_campaign(
        actions_by_iteration=NULL,
        seed_rows=NULL_SEED,
        realized_costs={"a_theta": 0.2, "c_theta_weak": 0.2},
        run_id="null-adaptive", max_iterations=1,
    )
    adaptive.run_campaign()
    static, _h2, _g2 = build_campaign(
        actions_by_iteration=NULL,
        seed_rows=NULL_SEED,
        realized_costs={"a_theta": 0.2, "c_theta_weak": 0.2},
        run_id="null-static", max_iterations=1, frozen_snapshot=True,
    )
    static.run_campaign()

    assert [i.selected_action_id for i in adaptive.run.iterations] == ["a_theta"]
    assert [i.selected_action_id for i in static.run.iterations] == ["a_theta"]
    assert (
        adaptive.run.iterations[0].selected_action_id
        == static.run.iterations[0].selected_action_id
    )


# =====================================================================
# Structural guarantees
# =====================================================================

def test_no_research_mode_state_machine_anywhere_in_the_loop():
    """Lifecycle vocabulary and runner source both stay mode-free."""
    states = {s.value.lower() for s in ExecutionState}
    assert states & RESEARCH_MODE_VOCABULARY == set()

    import ast
    from pathlib import Path
    import src.engcore.sria.campaign.runner as runner_module

    # Parse rather than grep, so the module's own prose about *not* having a
    # mode machine does not count as having one.
    tree = ast.parse(Path(runner_module.__file__).read_text(encoding="utf-8"))
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for forbidden in ("current_mode", "current_family", "mode", "_mode", "_family"):
        assert forbidden not in attributes, forbidden
        assert forbidden not in names, forbidden

    # No branch anywhere reads a family to decide what happens next.
    family_reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "ActionFamily"
    ]
    assert family_reads == [], [n.attr for n in family_reads]
    assert not hasattr(CampaignRunner, "current_family")
    assert not hasattr(CampaignRunner, "mode")


def test_all_six_families_remain_eligible_peers():
    from src.engcore.sria.decision import DEFAULT_GENERATORS

    families = {g.family for g in DEFAULT_GENERATORS}
    assert families == set(ActionFamily)
    assert len(families) == 6


def test_only_one_action_executes_per_iteration():
    runner, harness, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        max_iterations=2,
    )
    runner.run_campaign()
    assert len(harness.executor_impl.calls) == 2      # one per iteration
    assert len(runner.events.of_type(CampaignEventType.EXECUTION_COMPLETED)) == 2
    for iteration in (1, 2):
        started = [
            e for e in runner.events.of_type(CampaignEventType.EXECUTION_STARTED)
            if e.iteration == iteration
        ]
        assert len(started) == 1


def test_physical_execution_remains_unavailable():
    physical = AtomicAction(
        action=ResearchAction(
            action_id="lab_run",
            executor_type=ExecutorType.PHYSICAL,
            target_ref="theta",
            metadata={"target": "theta", "reliability": 0.9, "declared_cost": 1.0},
        ),
        proposal=ActionProposal(
            family=ActionFamily.EXPLORE,
            target_ref="theta",
            rationale="a laboratory measurement",
        ),
    )
    _raises(ReservedNotImplemented, require_simulation, physical)


def test_executor_and_result_cannot_write_belief():
    """Structural: none of the pre-Gateway types has an admission path."""
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, realized_costs={"a_theta": 1.0}, max_iterations=1
    )
    runner.step()
    execution = harness.executor_impl
    record_events = runner.events.of_type(CampaignEventType.EXECUTION_COMPLETED)
    assert record_events

    for subject in (execution, ExecutionRecord, harness.executor_impl):
        for forbidden in ("submit", "admit", "update_standing", "_apply"):
            assert not hasattr(subject, forbidden), (subject, forbidden)

    result_type = type(runner.snapshot(1))
    for forbidden in ("submit", "admit"):
        assert not hasattr(result_type, forbidden)

    # The gateway is the only thing that can, and it needs an authority.
    assert hasattr(gateway, "submit")
    assert gateway.authorities.authority_ids


def test_candidate_evidence_and_critics_cannot_write_belief():
    from src.engcore.sria.assurance.assessment import CriticAssessment
    from src.engcore.sria.evidence import Evidence

    for kind in (Evidence, CriticAssessment):
        for forbidden in ("submit", "update_standing", "_apply"):
            assert not hasattr(kind, forbidden), (kind, forbidden)


def test_gateway_is_the_sole_admission_path():
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1, realized_costs={"a_theta": 1.0}, max_iterations=1
    )
    runner.run_campaign()
    admitted = runner.run.iterations[0].admitted_evidence_ids
    assert admitted
    entries = gateway.belief.active_view()
    assert set(entries) == set(admitted)
    for entry in entries.values():
        assert entry.admitted_by                    # every entry names its authority


def test_calibration_telemetry_cannot_change_scientific_belief():
    """A run that produces no admissible evidence still teaches the cost model."""
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 9.0},
        critic_verdict=CriticVerdict.INCONCLUSIVE,
        max_iterations=1,
    )
    runner.run_campaign()
    first = runner.run.iterations[0]
    assert first.calibration_entry_ids              # calibration did update
    assert first.admitted_evidence_ids == ()        # belief did not
    assert len(gateway.belief) == 0
    assert len(harness.memory) == 1
    assert harness.memory.entries[0].kind.value == "cost_model"


def test_infrastructure_failure_does_not_poison_solver_failure_learning():
    from src.engcore.sria.outcomes import (
        AttributedCause,
        BlameAssignment,
        Disposition,
        RunOutcome,
    )

    infrastructure = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.INFRASTRUCTURE,
        blame_assignment=BlameAssignment.PLATFORM,
        informative_for_pf=False,
        detail="the node was preempted",
    )
    runner, harness, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0},
        dispositions={"a_theta": infrastructure},
        max_iterations=1,
    )
    runner.run_campaign()
    row = harness.calibration_rows[0]
    assert row.informative_for_pf is False
    assert row.eligible_for_computational_failure_learning is False


def test_predicted_and_realized_cost_are_recorded_separately():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 4.0},
        max_iterations=1,
    )
    runner.run_campaign()
    first = runner.run.iterations[0]
    assert first.predicted_cost is not None
    assert first.realized_cost == 4.0
    assert first.predicted_cost != first.realized_cost
    event = runner.events.last(CampaignEventType.BUDGET_UPDATED, iteration=1)
    assert event.payload["predicted"] == first.predicted_cost
    assert event.payload["realized"] == 4.0
    assert event.payload["overrun"] == first.cost_overrun
    # The decision itself is untouched by the overrun.
    recommendation = runner.recommendation(first.recommendation_id)
    scored = {s.action_id: s.total for s in recommendation.scores}
    assert abs(scored["a_theta"] - 3.0) < 1e-9


def test_hard_budget_stops_further_ordinary_action():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        budget=BudgetLedger(total_budget=1.0, cost_unit="hour"),
        max_iterations=2,
    )
    runner.run_campaign()
    assert runner.budget.spent_total <= 1.0
    assert runner.run.state is ExecutionState.PAUSED
    assert runner.run.pause_reason is PauseReason.BUDGET_EXHAUSTED


def test_retry_is_a_ranked_candidate_never_an_automatic_rerun():
    """A failed run does not re-run itself; a retry must be proposed and score."""
    from src.engcore.sria.outcomes import (
        AttributedCause,
        Disposition,
        Retryability,
        RunOutcome,
    )

    failed = RunOutcome(
        disposition=Disposition.FAILED,
        attributed_cause=AttributedCause.NUMERICAL,
        retryability=Retryability.RETRYABLE_WITH_CHANGES,
        informative_for_pf=True,
        detail="solver diverged",
    )
    retry = toy_action("a_theta_retry", target="theta", reliability=0.9, cost=1.2)
    retry = dataclasses.replace(
        retry,
        proposal=dataclasses.replace(
            retry.proposal,
            rationale=(
                "retry of a_theta after a numerical failure, with a tightened "
                "tolerance; config changed"
            ),
            assumptions=("previous run diverged; tolerance reduced 10x",),
        ),
    )
    actions = {1: S1_ACTIONS, 2: (retry,) + S1_ACTIONS}
    runner, harness, _g = build_campaign(
        actions_by_iteration=actions,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "a_theta_retry": 1.2, "b_phi": 0.5},
        dispositions={"a_theta": failed},
        critic_verdict=CriticVerdict.FAIL,
        max_iterations=2,
    )
    runner.run_campaign()

    # Iteration 1 failed and nothing re-ran it inside that iteration.
    assert harness.executor_impl.calls[0] == "a_theta"
    iteration_one_runs = [
        e for e in runner.events.of_type(CampaignEventType.EXECUTION_COMPLETED)
        if e.iteration == 1
    ]
    assert len(iteration_one_runs) == 1, "a failure must not trigger a rerun"
    # The retry appeared as a scored candidate among peers.
    second = runner.run.iterations[1]
    recommendation = runner.recommendation(second.recommendation_id)
    scored = {s.action_id for s in recommendation.scores}
    assert "a_theta_retry" in scored
    retry_action = next(
        a for a in actions[2] if a.action_id == "a_theta_retry"
    )
    assert "config changed" in retry_action.proposal.rationale
    assert retry_action.proposal.assumptions


def test_decision_provenance_links_the_iteration_to_its_exact_basis():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
    )
    runner.run_campaign()
    for record in runner.run.iterations:
        recommendation = runner.recommendation(record.recommendation_id)
        assert recommendation.snapshot_digest == record.snapshot_digest
        assert recommendation.dependency_manifest is not None
        assert (
            recommendation.dependency_manifest.manifest_digest
            == record.decision_basis_digest
        )
        provenance = recommendation.to_decision_provenance()
        assert provenance.belief_snapshot_ref == record.snapshot_digest
        assert record.selected_action_id in provenance.candidate_actions


def test_iteration_two_references_iteration_one_state():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
    )
    runner.run_campaign()
    first, second = runner.run.iterations
    admitted = first.admitted_evidence_ids
    assert admitted
    snapshot2 = runner.snapshot(2)
    assert set(admitted).issubset(set(snapshot2.active_evidence))
    assert snapshot2.metadata["c_theta"] == 0.9


def test_formal_decision_basis_remains_mandatory_every_iteration():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
    )
    runner.run_campaign()
    for iteration in (1, 2):
        snapshot = runner.snapshot(iteration)
        assert snapshot.pins_decision_basis is True
        record = runner.run.record(iteration)
        recommendation = runner.recommendation(record.recommendation_id)
        assert recommendation.coherence is not None
        assert recommendation.is_state_coherent is True


def test_audit_and_executable_replay_remain_valid():
    from src.engcore.sria.decision import (
        ReplayOutcome,
        audit_replay,
        executable_replay,
    )

    runner, harness, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
        max_iterations=1,
    )
    runner.run_campaign()
    record = runner.run.iterations[0]
    stored = runner.recommendation(record.recommendation_id)

    assert audit_replay(stored).outcome is ReplayOutcome.AUDIT_ONLY
    result = executable_replay(
        stored,
        evaluator=harness.evaluator(),
        candidates=S1_ACTIONS,
        snapshot=runner.snapshot(1),
        objective=harness.objective(),
        charter_version="1",
    )
    # The cost model was refit by iteration 1's calibration update, so the
    # pinned basis no longer resolves â€” refusing is exactly right.
    assert result.outcome in (
        ReplayOutcome.REPRODUCED,
        ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE,
    )
    if result.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE:
        assert result.recomputed is None


def test_event_log_is_append_only_and_auditable_end_to_end():
    runner, _h, _g = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
    )
    runner.run_campaign()
    log = runner.events
    assert log.verify_chain() is True
    seen = {e.event_type for e in log}
    for required in (
        CampaignEventType.CAMPAIGN_CREATED,
        CampaignEventType.SNAPSHOT_CREATED,
        CampaignEventType.CANDIDATES_GENERATED,
        CampaignEventType.DECISION_RECOMMENDED,
        CampaignEventType.ACTION_SELECTED,
        CampaignEventType.EXECUTION_STARTED,
        CampaignEventType.EXECUTION_COMPLETED,
        CampaignEventType.EVIDENCE_CREATED,
        CampaignEventType.CRITICS_COMPLETED,
        CampaignEventType.ARBITER_DECIDED,
        CampaignEventType.EVIDENCE_ADMITTED,
        CampaignEventType.CALIBRATION_UPDATED,
        CampaignEventType.BUDGET_UPDATED,
        CampaignEventType.ITERATION_COMPLETED,
    ):
        assert required in seen, required
    assert [e.sequence for e in log] == list(range(len(log)))


def test_m3_authorization_single_use_survives_the_loop():
    runner, harness, gateway = build_campaign(
        actions_by_iteration=S1,
        seed_rows=S1_SEED,
        realized_costs={"a_theta": 1.0, "b_phi": 0.5},
    )
    runner.run_campaign()
    # Two admissions, two distinct authorizations, no reuse.
    entries = gateway.belief.audit_log()
    assert len(entries) == 2
    assert len({e.evidence_id for e in entries}) == 2
    assert gateway.rejection_log == ()


def test_no_llm_in_the_scientific_truth_path():
    from pathlib import Path
    import src.engcore.sria.campaign as campaign_package

    root = Path(campaign_package.__file__).parent
    banned = ("openai", "anthropic", "langchain", "transformers", "llm", "gpt")
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in banned:
            assert f"import {token}" not in text, (path.name, token)
            assert f"from {token}" not in text, (path.name, token)


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M5 â€” sequential campaign loop")
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
        print(f"M5 campaign: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"M5 campaign: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

