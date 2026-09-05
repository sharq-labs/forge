"""Deterministic save-work acceptance for Core V0.3 persistence.

S5 in the frozen preregistration forbids checkpoint N from re-verifying all
prior checkpoint prefixes.  This test counts semantic verification operations,
not wall-clock time, so it is stable across runners.
"""

from __future__ import annotations

from src.engcore.sria.campaign.budget import BudgetLedger
from src.engcore.sria.campaign.checkpoint import EffectLedger
from src.engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from src.engcore.sria.campaign.persistence import IncrementalCheckpointStore
from src.engcore.sria.campaign.state import CampaignRun, ExecutionState


def test_checkpoint_save_work_is_incremental_not_quadratic() -> None:
    store = IncrementalCheckpointStore()
    events = CampaignEventLog("save-work-run")
    budget = BudgetLedger(total_budget=1000.0)
    effects = EffectLedger()

    commitment_checks = {"count": 0}
    original = store._verify_checkpoint_commitment

    def counted(checkpoint, *, verify_budget=True):
        commitment_checks["count"] += 1
        return original(checkpoint, verify_budget=verify_budget)

    store._verify_checkpoint_commitment = counted  # type: ignore[method-assign]

    checkpoints = 40
    for index in range(checkpoints):
        for slot in range(4):
            events.append(
                CampaignEventType.ITERATION_COMPLETED,
                iteration=index + 1,
                payload={"iteration": index + 1, "slot": slot},
            )
        run = CampaignRun(
            run_id="save-work-run",
            campaign_id="save-work-campaign",
            state=ExecutionState.READY,
            iteration=index + 1,
            max_iterations=checkpoints,
            event_log_digest=events.head_digest,
        )
        store.save_state(run=run, events=events, budget=budget, effects=effects)

    assert store.event_record_count == 4 * checkpoints
    assert len(store.records) == checkpoints

    # A constant number of commitment checks per save is acceptable.  Replaying
    # checkpoint 0..N on every save is not.  The generous 3N ceiling allows a
    # previous-head check plus the new-record check without pinning an internal
    # implementation detail.
    assert commitment_checks["count"] <= 3 * checkpoints, (
        "saving a checkpoint re-verified historical checkpoints; S5 requires "
        "incremental save work"
    )
