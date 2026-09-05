"""Crash-boundary and migration tests for the initial V0.3 JSON file backend.

The backend intentionally claims only atomic whole-image replacement, not a
remote database transaction or delta-written filesystem journal.  A failed
replacement must leave the previous committed image readable, and explicit
legacy migration must never rewrite its source artifact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.engcore.sria.campaign.budget import BudgetLedger
from src.engcore.sria.campaign.checkpoint import (
    CampaignCheckpoint,
    CheckpointStore,
    EffectLedger,
)
from src.engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from src.engcore.sria.campaign.persistence import IncrementalCheckpointStore
from src.engcore.sria.campaign.state import CampaignRun, ExecutionState

RUN_ID = "v03-file-backend"


def _save_one(store: IncrementalCheckpointStore, events: CampaignEventLog, iteration: int):
    events.append(
        CampaignEventType.ITERATION_COMPLETED,
        iteration=iteration,
        payload={"iteration": iteration},
    )
    run = CampaignRun(
        run_id=RUN_ID,
        campaign_id="v03-file-campaign",
        state=ExecutionState.READY,
        iteration=iteration,
        max_iterations=3,
        event_log_digest=events.head_digest,
    )
    store.save_state(
        run=run,
        events=events,
        budget=BudgetLedger(total_budget=10.0),
        effects=EffectLedger(),
    )
    return run


def test_failed_atomic_replace_leaves_previous_committed_image_readable(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "campaign.json"
    store = IncrementalCheckpointStore()
    events = CampaignEventLog(RUN_ID)

    _save_one(store, events, 1)
    store.save_to_path(target)
    previous_bytes = target.read_bytes()
    previous = IncrementalCheckpointStore.load_from_path(target).latest()
    assert previous is not None

    _save_one(store, events, 2)

    def fail_replace(_source, _target):
        raise OSError("synthetic crash before atomic rename")

    monkeypatch.setattr(
        "src.engcore.sria.campaign.persistence.os.replace", fail_replace
    )
    with pytest.raises(OSError, match="synthetic crash"):
        store.save_to_path(target)

    assert target.read_bytes() == previous_bytes
    reloaded = IncrementalCheckpointStore.load_from_path(target).latest()
    assert reloaded is not None
    assert reloaded.to_dict() == previous.to_dict()


def test_rewriting_identical_logical_state_produces_identical_file_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "campaign.json"
    store = IncrementalCheckpointStore()
    events = CampaignEventLog(RUN_ID)
    _save_one(store, events, 1)

    store.save_to_path(target)
    first = target.read_bytes()
    store.save_to_path(target)
    second = target.read_bytes()
    assert second == first


def test_explicit_legacy_migration_does_not_rewrite_source(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.json"
    migrated_path = tmp_path / "v03.json"

    events = CampaignEventLog(RUN_ID)
    events.append(
        CampaignEventType.CAMPAIGN_CREATED,
        iteration=0,
        payload={"campaign_id": "v03-file-campaign"},
    )
    run = CampaignRun(
        run_id=RUN_ID,
        campaign_id="v03-file-campaign",
        state=ExecutionState.READY,
        max_iterations=1,
        event_log_digest=events.head_digest,
    )
    checkpoint = CampaignCheckpoint(
        run=run,
        events=events,
        budget=BudgetLedger(total_budget=10.0),
        effects=EffectLedger(),
    )
    legacy = CheckpointStore()
    legacy.save(checkpoint)
    legacy.save_to_path(legacy_path)
    source_before = legacy_path.read_bytes()

    migrated = IncrementalCheckpointStore.migrate_legacy_file(
        legacy_path, migrated_path
    )

    assert legacy_path.read_bytes() == source_before
    assert migrated_path.exists()
    assert migrated.latest() is not None
    assert migrated.latest().to_dict() == checkpoint.to_dict()
