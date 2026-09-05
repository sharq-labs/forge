"""Deterministic scaling acceptance for Core V0.3 campaign persistence.

The frozen preregistration defines success primarily by record counts and
serialized-growth shape, not wall-clock speed.  This test grows one live event
log and persists four fixed-shape events per checkpoint, exactly matching the
PERF-0 synthetic pattern used to expose the legacy repeated-prefix defect.
"""

from __future__ import annotations

import json

from src.engcore.sria.campaign.budget import BudgetLedger
from src.engcore.sria.campaign.checkpoint import EffectLedger
from src.engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from src.engcore.sria.campaign.persistence import IncrementalCheckpointStore
from src.engcore.sria.campaign.state import CampaignRun, ExecutionState

RUN_ID = "v03-scaling"
EVENTS_PER_CHECKPOINT = 4


def _serialized_size(n: int) -> tuple[int, IncrementalCheckpointStore]:
    store = IncrementalCheckpointStore()
    events = CampaignEventLog(RUN_ID)
    budget = BudgetLedger(total_budget=10000.0)
    effects = EffectLedger()

    for index in range(n):
        iteration = index + 1
        for slot in range(EVENTS_PER_CHECKPOINT):
            events.append(
                CampaignEventType.ITERATION_COMPLETED,
                iteration=iteration,
                payload={"iteration": iteration, "slot": slot},
                at="",
            )
        run = CampaignRun(
            run_id=RUN_ID,
            campaign_id="v03-scaling-campaign",
            state=ExecutionState.READY,
            iteration=iteration,
            max_iterations=n,
            event_log_digest=events.head_digest,
        )
        store.save_state(run=run, events=events, budget=budget, effects=effects)

    blob = json.dumps(store.to_dict(), sort_keys=True, separators=(",", ":"))
    return len(blob.encode("utf-8")), store


def test_event_records_are_exactly_linear_at_one_thousand_checkpoints() -> None:
    _size, store = _serialized_size(1000)

    assert len(store.records) == 1000
    assert store.event_record_count == EVENTS_PER_CHECKPOINT * 1000 == 4000

    # The legacy PERF-0 representation retained 2,002,000 event records for the
    # same head history.  The successor stores each fact once.
    assert store.event_record_count != 2_002_000

    for record in store.to_dict()["checkpoints"]:
        assert "events" not in record
        assert "budget_journal" not in record
        assert "effect_journal" not in record
        assert "iteration_journal" not in record


def test_serialized_growth_is_linear_shaped_not_repeated_prefix_quadratic() -> None:
    size_100, _ = _serialized_size(100)
    size_300, _ = _serialized_size(300)
    size_1000, _ = _serialized_size(1000)

    assert size_100 < size_300 < size_1000

    # With fixed-shape records a tenfold checkpoint increase should remain near
    # tenfold bytes.  The bounds deliberately allow JSON digit-width overhead;
    # they are loose enough to avoid platform/timing noise but far below the
    # ~100x growth expected from repeated-prefix quadratic storage.
    assert size_300 / size_100 < 4.5
    assert size_1000 / size_100 < 15.0
