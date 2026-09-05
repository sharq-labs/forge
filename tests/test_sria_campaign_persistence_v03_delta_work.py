"""Deterministic delta-work regressions for Core V0.3 persistence.

These tests pin operation counts/state transitions rather than wall-clock time.
The persistence save path may process newly appended history, but it must not
rescan committed effect history or recompute budget aggregates from all prior
charges on every checkpoint.
"""

from __future__ import annotations

from src.engcore.sria.campaign.budget import BudgetLedger
from src.engcore.sria.campaign.checkpoint import EffectLedger
from src.engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from src.engcore.sria.campaign.persistence import IncrementalCheckpointStore
from src.engcore.sria.campaign.state import CampaignRun, ExecutionState
from src.engcore.sria.decision.actions import ActionFamily


def _run(run_id: str, iteration: int, max_iterations: int, events: CampaignEventLog):
    return CampaignRun(
        run_id=run_id,
        campaign_id=f"{run_id}-campaign",
        state=ExecutionState.READY,
        iteration=iteration,
        max_iterations=max_iterations,
        event_log_digest=events.head_digest,
    )


def test_effect_persistence_consumes_only_new_append_order_entries(monkeypatch) -> None:
    run_id = "v03-effect-delta"
    store = IncrementalCheckpointStore()
    events = CampaignEventLog(run_id)
    budget = BudgetLedger(total_budget=1000.0)
    effects = EffectLedger()

    original = EffectLedger.entries_from
    delta_sizes: list[int] = []

    def counted_entries_from(self: EffectLedger, index: int):
        delta = original(self, index)
        delta_sizes.append(len(delta))
        return delta

    monkeypatch.setattr(EffectLedger, "entries_from", counted_entries_from)

    checkpoints = 80
    for index in range(checkpoints):
        iteration = index + 1
        effects.mark(f"effect-{iteration:04d}", f"ref-{iteration:04d}")
        events.append(
            CampaignEventType.ITERATION_COMPLETED,
            iteration=iteration,
            payload={"iteration": iteration},
        )
        store.save_state(
            run=_run(run_id, iteration, checkpoints, events),
            events=events,
            budget=budget,
            effects=effects,
        )

    assert store.effect_record_count == checkpoints
    assert len(delta_sizes) == checkpoints
    assert sum(delta_sizes) == checkpoints
    assert max(delta_sizes) == 1


def test_effect_ledger_v02_wire_shape_is_unchanged_by_private_append_journal() -> None:
    ledger = EffectLedger()
    ledger.mark("z-key", "z-ref")
    ledger.mark("a-key", "a-ref")

    payload = ledger.to_dict()
    assert set(payload) == {"schema", "applied"}
    assert payload["applied"] == {"a-key": "a-ref", "z-key": "z-ref"}
    assert "_journal" not in payload
    assert "journal" not in payload

    restored = EffectLedger.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.applied == ledger.applied


def test_budget_checkpoint_aggregates_follow_only_new_charges_and_survive_reload() -> None:
    run_id = "v03-budget-delta"
    store = IncrementalCheckpointStore()
    events = CampaignEventLog(run_id)
    budget = BudgetLedger(total_budget=50.0, reserved_validation_budget=10.0)
    effects = EffectLedger()

    checkpoints = 25
    for index in range(checkpoints):
        iteration = index + 1
        family = ActionFamily.VALIDATE if iteration == 1 else ActionFamily.EXPLORE
        realized = 3.0 if iteration == 1 else 2.0
        budget.settle(
            charge_id=f"charge-{iteration}",
            action_id=f"action-{iteration}",
            iteration=iteration,
            family=family,
            realized=realized,
            predicted=realized,
        )
        events.append(
            CampaignEventType.BUDGET_UPDATED,
            iteration=iteration,
            payload={"realized": realized},
        )
        record = store.save_state(
            run=_run(run_id, iteration, checkpoints, events),
            events=events,
            budget=budget,
            effects=effects,
        )
        assert record.budget_charge_count == iteration
        assert record.spent_total == budget.spent_total
        assert record.spent_general == budget.spent_general
        assert record.spent_validation == budget.spent_validation
        assert record.budget_overrun == budget.overrun

    restored = IncrementalCheckpointStore.from_dict(store.to_dict())
    latest = restored.latest_record
    assert latest is not None
    assert latest.spent_total == budget.spent_total
    assert latest.spent_general == budget.spent_general
    assert latest.spent_validation == budget.spent_validation
    assert latest.budget_overrun == budget.overrun

    # Append one more charge after reload. Reconstructed running aggregates must
    # continue from the committed journal rather than restart from zero.
    budget.settle(
        charge_id="charge-after-reload",
        action_id="action-after-reload",
        iteration=checkpoints,
        family=ActionFamily.EXPLORE,
        realized=1.5,
        predicted=1.5,
    )
    events.append(
        CampaignEventType.BUDGET_UPDATED,
        iteration=checkpoints,
        payload={"realized": 1.5, "after_reload": True},
    )
    final = restored.save_state(
        run=_run(run_id, checkpoints, checkpoints, events),
        events=events,
        budget=budget,
        effects=effects,
    )
    assert final.spent_total == budget.spent_total
    assert final.spent_general == budget.spent_general
    assert final.spent_validation == budget.spent_validation
    assert final.budget_overrun == budget.overrun
