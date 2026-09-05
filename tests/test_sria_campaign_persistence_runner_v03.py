"""The V0.3 runner changes only the persistence seam.

The overridden checkpoint seam is exercised directly, and the real constructor
is also pinned so an explicitly supplied empty incremental store cannot be lost
to the frozen M5 constructor's truthiness-based defaulting.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.engcore.sria.campaign.budget import BudgetLedger
from src.engcore.sria.campaign.checkpoint import EffectLedger
from src.engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from src.engcore.sria.campaign.persistence import IncrementalCheckpointStore
from src.engcore.sria.campaign.persistence_runner import IncrementalCampaignRunner
from src.engcore.sria.campaign.state import CampaignRun, ExecutionState


def _bare_runner() -> IncrementalCampaignRunner:
    runner = object.__new__(IncrementalCampaignRunner)
    runner._checkpoints = IncrementalCheckpointStore()
    runner._run = CampaignRun(
        run_id="runner-v03",
        campaign_id="campaign-v03",
        state=ExecutionState.READY,
        max_iterations=3,
    )
    runner._events = CampaignEventLog("runner-v03")
    runner._budget = BudgetLedger(
        total_budget=100.0,
        enforced_cap=90.0,
        enforced_cap_source="test executor",
    )
    runner._effects = EffectLedger()
    runner._plan = None
    runner._obligation_state = {}
    runner._recommendations = {}
    runner._snapshots = {}
    return runner


def test_real_constructor_retains_an_explicit_empty_incremental_store() -> None:
    external = IncrementalCheckpointStore()
    charter = MagicMock()
    charter.campaign_id = "constructor-campaign"

    runner = IncrementalCampaignRunner(
        run_id="constructor-run",
        charter=charter,
        harness=MagicMock(),
        gateway=MagicMock(),
        arbiter=MagicMock(),
        obligations=MagicMock(),
        budget=BudgetLedger(total_budget=10.0),
        max_iterations=2,
        checkpoints=external,
        liveness=MagicMock(),
        stopping=MagicMock(),
        clock=lambda: "constructor-clock",
    )

    assert runner.checkpoints is external
    assert isinstance(runner.checkpoints, IncrementalCheckpointStore)


def test_incremental_runner_checkpoint_writes_only_new_event_history() -> None:
    runner = _bare_runner()

    runner._events.append(
        CampaignEventType.CAMPAIGN_CREATED,
        iteration=0,
        payload={"campaign_id": "campaign-v03"},
    )
    first = runner._checkpoint()
    assert first.event_count == 1
    assert runner._checkpoints.event_record_count == 1

    runner._events.append(
        CampaignEventType.CAMPAIGN_PAUSED,
        iteration=0,
        payload={"reason": "test"},
    )
    second = runner._checkpoint()
    assert second.event_count == 2
    assert runner._checkpoints.event_record_count == 2
    assert len(runner._checkpoints.records) == 2


def test_restore_latest_materializes_existing_runner_state_without_replay() -> None:
    runner = _bare_runner()
    runner._events.append(
        CampaignEventType.CAMPAIGN_CREATED,
        iteration=0,
        payload={"campaign_id": "campaign-v03"},
    )
    runner._obligation_state = {"adequacy": True}
    runner._checkpoint()

    restored = object.__new__(IncrementalCampaignRunner)
    restored._checkpoints = runner._checkpoints
    restored._recommendations = {}
    restored._snapshots = {}

    run = restored.restore_latest()
    assert run.to_dict() == runner._run.to_dict()
    assert restored._events.to_dict() == runner._events.to_dict()
    assert restored._budget.to_dict() == runner._budget.to_dict()
    assert restored._budget.enforced_cap == 90.0
    assert restored._budget.enforced_cap_source == "test executor"
    assert restored._effects.to_dict() == runner._effects.to_dict()
    assert restored._obligation_state == {"adequacy": True}


def test_restore_latest_refreezes_adopted_event_history_before_next_checkpoint() -> None:
    runner = _bare_runner()
    runner._events.append(
        CampaignEventType.CAMPAIGN_CREATED,
        iteration=0,
        payload={"nested": {"attempts": [1]}},
    )
    runner._events.append(
        CampaignEventType.CAMPAIGN_PAUSED,
        iteration=0,
        payload={"reason": "first-save"},
    )
    runner._checkpoint()

    restored = object.__new__(IncrementalCampaignRunner)
    restored._checkpoints = runner._checkpoints
    restored._recommendations = {}
    restored._snapshots = {}
    restored.restore_latest()
    before = restored._checkpoints.to_dict()["events"]

    with pytest.raises(TypeError, match="campaign event payloads are immutable"):
        restored.events.events[0].payload["nested"]["attempts"].append(2)

    restored._events.append(
        CampaignEventType.CAMPAIGN_PAUSED,
        iteration=0,
        payload={"reason": "second-save"},
    )
    restored._run = CampaignRun(
        run_id="runner-v03",
        campaign_id="campaign-v03",
        state=ExecutionState.READY,
        iteration=1,
        max_iterations=3,
        event_log_digest=restored._events.head_digest,
    )
    restored._checkpoint()

    latest = IncrementalCheckpointStore.from_dict(
        restored._checkpoints.to_dict()
    ).latest()
    assert latest is not None
    assert before[0]["payload"]["nested"]["attempts"] == [1]
    assert latest.events.events[0].payload["nested"]["attempts"] == [1]
