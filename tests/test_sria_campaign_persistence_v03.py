"""Core V0.3 incremental campaign persistence acceptance tests.

These tests pin representation invariants, not wall-clock timings.  Historical
facts must be stored once, compact checkpoints must commit to exact prefixes,
and materialized legacy state must remain equivalent for resume.
"""

from __future__ import annotations

import copy
import json

import pytest

from src.engcore.sria.campaign.budget import BudgetLedger
from src.engcore.sria.campaign.checkpoint import (
    CampaignCheckpoint,
    CheckpointStore,
    EffectLedger,
)
from src.engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from src.engcore.sria.campaign.persistence import (
    IncrementalCheckpointStore,
    PersistenceIntegrityError,
)
from src.engcore.sria.campaign.state import (
    CampaignRun,
    ExecutionState,
    IterationRecord,
)
from src.engcore.sria.decision.actions import ActionFamily


def _run(
    *,
    iteration: int,
    max_iterations: int,
    iterations: tuple[IterationRecord, ...],
    event_head: str,
) -> CampaignRun:
    return CampaignRun(
        run_id="v03-run",
        campaign_id="v03-campaign",
        charter_version="1",
        state=ExecutionState.READY,
        iteration=iteration,
        max_iterations=max_iterations,
        iterations=iterations,
        event_log_digest=event_head,
    )


def _legacy_snapshot(
    *,
    run: CampaignRun,
    log: CampaignEventLog,
    budget: BudgetLedger,
    effects: EffectLedger,
) -> CampaignCheckpoint:
    return CampaignCheckpoint(
        run=run,
        events=CampaignEventLog(run.run_id, log.events),
        budget=BudgetLedger(
            total_budget=budget.total_budget,
            reserved_validation_budget=budget.reserved_validation_budget,
            charges=budget.charges,
            cost_unit=budget.cost_unit,
            enforced_cap=budget.enforced_cap,
            enforced_cap_source=budget.enforced_cap_source,
        ),
        effects=EffectLedger(applied=dict(effects.applied)),
        obligation_state={"adequacy": bool(run.iteration % 2)},
    )


def _build_state(n: int = 8):
    log = CampaignEventLog("v03-run")
    budget = BudgetLedger(total_budget=10000.0, reserved_validation_budget=100.0)
    effects = EffectLedger()
    records: list[IterationRecord] = []
    states: list[CampaignCheckpoint] = []

    for index in range(n):
        iteration = index + 1
        for slot in range(4):
            log.append(
                CampaignEventType.ITERATION_COMPLETED,
                iteration=iteration,
                payload={"iteration": iteration, "slot": slot},
                at=f"t-{iteration}-{slot}",
            )
        budget.settle(
            charge_id=f"charge-{iteration}",
            action_id=f"action-{iteration}",
            iteration=iteration,
            family=ActionFamily.EXPLORE,
            realized=1.0,
            predicted=1.0,
        )
        effects.mark(f"v03-run:{iteration}:effect:subject", f"ref-{iteration}")
        records.append(
            IterationRecord(
                iteration=iteration,
                recommendation_id=f"rec-{iteration}",
                selected_action_id=f"action-{iteration}",
                execution_id=f"exec-{iteration}",
                realized_cost=1.0,
                predicted_cost=1.0,
            )
        )
        run = _run(
            iteration=iteration,
            max_iterations=max(n, 1),
            iterations=tuple(records),
            event_head=log.head_digest,
        )
        states.append(
            _legacy_snapshot(run=run, log=log, budget=budget, effects=effects)
        )
    return states


def test_historical_records_are_stored_once_not_as_repeated_prefixes() -> None:
    states = _build_state(40)
    store = IncrementalCheckpointStore()
    for checkpoint in states:
        store.save(checkpoint)

    assert len(store) == 40
    assert store.event_record_count == 4 * 40
    assert store.budget_record_count == 40
    assert store.effect_record_count == 40
    assert store.iteration_record_count == 40

    payload = store.to_dict()
    assert len(payload["events"]) == 160
    assert len(payload["budget_journal"]) == 40
    assert len(payload["effect_journal"]) == 40
    assert len(payload["iteration_journal"]) == 40
    assert len(payload["checkpoints"]) == 40

    # Compact checkpoints commit by cursor/digest. They do not embed any of the
    # cumulative journals, and compact run state does not embed iterations.
    for checkpoint in payload["checkpoints"]:
        assert "events" not in checkpoint
        assert "budget" not in checkpoint
        assert "effects" not in checkpoint
        assert "iterations" not in checkpoint["run_state"]
        assert "event_count" in checkpoint
        assert "budget_charge_count" in checkpoint
        assert "effect_count" in checkpoint
        assert "iteration_record_count" in checkpoint


def test_latest_materializes_the_same_logical_checkpoint() -> None:
    states = _build_state(6)
    store = IncrementalCheckpointStore()
    for checkpoint in states:
        store.save(checkpoint)

    restored = store.latest()
    assert restored is not None
    assert restored.to_dict() == states[-1].to_dict()


def test_every_legacy_checkpoint_round_trips_through_migration() -> None:
    legacy = CheckpointStore()
    states = _build_state(7)
    for checkpoint in states:
        legacy.save(checkpoint)

    migrated = IncrementalCheckpointStore.from_legacy_store(legacy)
    assert len(migrated.records) == len(states)
    assert [item.to_dict() for item in migrated.history] == [
        item.to_dict() for item in states
    ]


def test_json_round_trip_is_deterministic_and_preserves_latest_state() -> None:
    store = IncrementalCheckpointStore()
    for checkpoint in _build_state(5):
        store.save(checkpoint)

    encoded = json.dumps(store.to_dict(), sort_keys=True, separators=(",", ":"))
    reloaded = IncrementalCheckpointStore.from_dict(json.loads(encoded))
    encoded_again = json.dumps(
        reloaded.to_dict(), sort_keys=True, separators=(",", ":")
    )
    assert encoded_again == encoded
    assert reloaded.latest().to_dict() == store.latest().to_dict()


def test_tampering_with_a_committed_event_is_detected() -> None:
    store = IncrementalCheckpointStore()
    for checkpoint in _build_state(3):
        store.save(checkpoint)
    payload = copy.deepcopy(store.to_dict())
    payload["events"][1]["payload"]["slot"] = 999

    with pytest.raises(PersistenceIntegrityError):
        IncrementalCheckpointStore.from_dict(payload)


def test_tampering_with_checkpoint_history_is_detected() -> None:
    store = IncrementalCheckpointStore()
    for checkpoint in _build_state(3):
        store.save(checkpoint)
    payload = copy.deepcopy(store.to_dict())
    payload["checkpoints"][1]["previous_checkpoint_digest"] = "wrong"

    with pytest.raises(PersistenceIntegrityError):
        IncrementalCheckpointStore.from_dict(payload)


def test_a_valid_uncommitted_event_suffix_does_not_change_latest_resume() -> None:
    states = _build_state(2)
    store = IncrementalCheckpointStore()
    for checkpoint in states:
        store.save(checkpoint)

    before = store.latest().to_dict()
    payload = copy.deepcopy(store.to_dict())

    # Produce a genuinely valid next chained event, but do not add a checkpoint
    # that commits it. The loader may retain it for audit; resume stays pinned to
    # the latest committed cursor.
    log = CampaignEventLog("v03-run", states[-1].events.events)
    extra = log.append(
        CampaignEventType.CAMPAIGN_PAUSED,
        iteration=2,
        payload={"reason": "synthetic crash suffix"},
        at="after-checkpoint",
    )
    payload["events"].append(extra.to_dict())

    reloaded = IncrementalCheckpointStore.from_dict(payload)
    assert reloaded.latest().to_dict() == before
    assert reloaded.verify_all()

    # Continuing through an ambiguous uncommitted suffix is fail-closed.
    with pytest.raises(PersistenceIntegrityError, match="uncommitted"):
        reloaded.save(states[-1])


def test_budget_and_effect_state_survive_materialization_exactly() -> None:
    states = _build_state(5)
    store = IncrementalCheckpointStore()
    for checkpoint in states:
        store.save(checkpoint)

    restored = store.latest()
    expected = states[-1]
    assert restored.budget.to_dict() == expected.budget.to_dict()
    assert restored.effects.to_dict() == expected.effects.to_dict()
    assert restored.obligation_state == expected.obligation_state

    # Existing effect remains at-most-once after reload/materialization.
    key = "v03-run:5:effect:subject"
    value, performed = restored.effects.once(key, lambda: "must-not-run")
    assert value is None
    assert performed is False
    assert restored.effects.reference(key) == "ref-5"


def test_checkpoint_cursors_are_monotone() -> None:
    store = IncrementalCheckpointStore()
    for checkpoint in _build_state(10):
        store.save(checkpoint)

    previous = (0, 0, 0, 0)
    for record in store.records:
        current = (
            record.event_count,
            record.budget_charge_count,
            record.effect_count,
            record.iteration_record_count,
        )
        assert all(now >= old for now, old in zip(current, previous))
        previous = current


def test_event_log_suffix_api_returns_only_new_records() -> None:
    log = CampaignEventLog("v03-run")
    for index in range(12):
        log.append(
            CampaignEventType.ITERATION_COMPLETED,
            iteration=index,
            payload={"index": index},
        )

    assert log.event_at(7).sequence == 7
    assert [event.sequence for event in log.events_from(9)] == [9, 10, 11]
    assert log.events_from(len(log)) == ()
