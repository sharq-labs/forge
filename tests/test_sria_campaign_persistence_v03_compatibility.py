"""Compatibility and resume-equivalence gates for Core V0.3 persistence."""

from __future__ import annotations

from src.engcore.sria.actions import ExecutorType, ResearchAction
from src.engcore.sria.campaign.budget import BudgetLedger
from src.engcore.sria.campaign.checkpoint import (
    CampaignCheckpoint,
    CheckpointStore,
    EffectLedger,
    IterationPlan,
)
from src.engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from src.engcore.sria.campaign.persistence import IncrementalCheckpointStore
from src.engcore.sria.campaign.persistence_runner import IncrementalCampaignRunner
from src.engcore.sria.campaign.state import CampaignRun, ExecutionState, PauseReason
from src.engcore.sria.decision.actions import ActionFamily, ActionProposal, AtomicAction
from src.engcore.sria.decision.belief_snapshot import BeliefSnapshot
from src.engcore.sria.decision.recommendation import (
    DecisionRecommendation,
    RecommendationOutcome,
)
from src.engcore.sria.decision.replay import ExecutionDependencyManifest

RUN_ID = "v03-compat"


def _plan() -> IterationPlan:
    snapshot = BeliefSnapshot(
        snapshot_id="snap-1",
        campaign_id="campaign-compat",
        charter_version="1",
    )
    manifest = ExecutionDependencyManifest(
        snapshot_digest=snapshot.digest,
        charter_version="1",
        candidate_set_digest="candidate-set",
    )
    action = AtomicAction(
        action=ResearchAction(
            action_id="action-1",
            executor_type=ExecutorType.SIMULATION,
            target_ref="target-1",
        ),
        proposal=ActionProposal(
            family=ActionFamily.EXPLORE,
            target_ref="target-1",
            rationale="compatibility fixture",
        ),
    )
    recommendation = DecisionRecommendation(
        recommendation_id="rec-1",
        outcome=RecommendationOutcome.RECOMMEND_ACTION,
        snapshot_digest=snapshot.digest,
        campaign_id="campaign-compat",
        charter_version="1",
        chosen_action_id=action.action_id,
        chosen_family=action.family,
        dependency_manifest=manifest,
        reason="compatibility fixture",
    )
    return IterationPlan(
        iteration=1,
        snapshot=snapshot,
        manifest=manifest,
        recommendation=recommendation,
        action=action,
        charter_version="1",
        campaign_id="campaign-compat",
        predicted_cost=2.0,
        liveness_reason="",
    )


def _legacy_checkpoint_with_plan() -> CampaignCheckpoint:
    events = CampaignEventLog(RUN_ID)
    events.append(
        CampaignEventType.CAMPAIGN_CREATED,
        iteration=0,
        payload={"campaign_id": "campaign-compat"},
    )
    events.append(
        CampaignEventType.ACTION_SELECTED,
        iteration=1,
        payload={"action_id": "action-1"},
    )

    # Total realized spend is 10 against a declared budget of 8.  Migration
    # therefore has to preserve both the reservation split and a real overrun.
    budget = BudgetLedger(total_budget=8.0, reserved_validation_budget=5.0)
    budget.settle(
        charge_id="validation-charge",
        action_id="validation-action",
        iteration=0,
        family=ActionFamily.VALIDATE,
        realized=7.0,
        predicted=6.0,
    )
    budget.settle(
        charge_id="ordinary-charge",
        action_id="ordinary-action",
        iteration=0,
        family=ActionFamily.EXPLORE,
        realized=3.0,
        predicted=3.0,
    )

    effects = EffectLedger()
    effects.mark("effect:execute", "exec-1")
    effects.mark("effect:admit", "evidence-1")

    run = CampaignRun(
        run_id=RUN_ID,
        campaign_id="campaign-compat",
        charter_version="1",
        state=ExecutionState.ACTION_SELECTED,
        iteration=1,
        max_iterations=3,
        event_log_digest=events.head_digest,
    )
    return CampaignCheckpoint(
        run=run,
        events=events,
        budget=budget,
        effects=effects,
        plan=_plan(),
        obligation_state={"adequacy": True, "independence": False},
    )


def test_legacy_migration_preserves_plan_obligations_budget_and_effects_exactly() -> None:
    source = _legacy_checkpoint_with_plan()
    legacy = CheckpointStore()
    legacy.save(source)

    migrated = IncrementalCheckpointStore.from_legacy_store(legacy)
    restored = migrated.latest()
    assert restored is not None

    assert restored.run.to_dict() == source.run.to_dict()
    assert restored.events.to_dict() == source.events.to_dict()
    assert restored.plan is not None and source.plan is not None
    assert restored.plan.digest == source.plan.digest
    assert restored.obligation_state == source.obligation_state
    assert restored.budget.to_dict() == source.budget.to_dict()
    assert restored.effects.to_dict() == source.effects.to_dict()

    assert restored.budget.spent_validation == source.budget.spent_validation
    assert restored.budget.spent_general == source.budget.spent_general
    assert restored.budget.overrun == source.budget.overrun == 2.0


def test_repeated_charge_id_remains_idempotent_after_migration() -> None:
    source = _legacy_checkpoint_with_plan()
    legacy = CheckpointStore()
    legacy.save(source)
    restored = IncrementalCheckpointStore.from_legacy_store(legacy).latest()
    assert restored is not None

    before = restored.budget.to_dict()
    existing = restored.budget.settle(
        charge_id="ordinary-charge",
        action_id="different-action-must-not-replace-history",
        iteration=99,
        family=ActionFamily.EXPLORE,
        realized=99.0,
        predicted=99.0,
    )
    assert existing.charge_id == "ordinary-charge"
    assert restored.budget.to_dict() == before


def test_selected_action_without_plan_still_fails_closed_after_v03_restore() -> None:
    events = CampaignEventLog("v03-missing-plan")
    events.append(
        CampaignEventType.CAMPAIGN_CREATED,
        iteration=0,
        payload={"campaign_id": "missing-plan-campaign"},
    )
    events.append(
        CampaignEventType.ACTION_SELECTED,
        iteration=1,
        payload={"action_id": "recorded-action"},
    )
    run = CampaignRun(
        run_id="v03-missing-plan",
        campaign_id="missing-plan-campaign",
        state=ExecutionState.ACTION_SELECTED,
        iteration=1,
        max_iterations=3,
        event_log_digest=events.head_digest,
    )
    store = IncrementalCheckpointStore()
    store.save_state(
        run=run,
        events=events,
        budget=BudgetLedger(total_budget=10.0),
        effects=EffectLedger(),
        plan=None,
    )

    runner = object.__new__(IncrementalCampaignRunner)
    runner._checkpoints = store
    runner._recommendations = {}
    runner._snapshots = {}
    runner._clock = lambda: "resume-test"
    runner.restore_latest()

    resumed = runner.step()
    assert resumed.state is ExecutionState.PAUSED
    assert resumed.pause_reason is PauseReason.OPERATOR_REQUESTED
    assert runner.plan is None
    assert runner.events.last(CampaignEventType.CAMPAIGN_PAUSED, iteration=1) is not None
