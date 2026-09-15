"""Audit stream sria — SER-01: stored assurance state is re-derived from the log.

The V0.3 store commits to its journals with plain SHA-256 digests. Anyone who
edits the bytes can recompute them, so the digests detect accidental
corruption, not deliberate edits. The reviewer showed three consequences:

* T1 — ``obligation_state`` edited and the head digest recomputed: accepted.
* T2 — an iteration record rewritten (verdict ``valid``, a forged admitted id)
  and two digests recomputed: accepted, with no matching events in the log.
* T3 — a legacy-format file with the same edits loaded through
  ``load_from_path``, which silently migrated it.

The repair derives both facts from the hash-chained event log on materialize
and refuses disagreement, and legacy migration happens only on request.
"""

from __future__ import annotations

import copy
import json

import pytest

from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.campaign.checkpoint import CheckpointStore, EffectLedger
from engcore.sria.campaign.events import CampaignEventLog, CampaignEventType
from engcore.sria.campaign.persistence import (
    CampaignCheckpointV3,
    IncrementalCheckpointStore,
    IterationJournalEntry,
    PersistenceIntegrityError,
    _copy_iteration_continuation,
)
from engcore.sria.campaign.state import CampaignRun, ExecutionState, IterationRecord
from engcore.sria.decision.actions import ActionFamily

RUN_ID = "audit-sria-ser01"
REFUSED = (PersistenceIntegrityError, ValueError)


def _store(n: int = 3) -> IncrementalCheckpointStore:
    store = IncrementalCheckpointStore()
    events = CampaignEventLog(RUN_ID)
    budget = BudgetLedger(total_budget=100.0, reserved_validation_budget=10.0)
    effects = EffectLedger()
    iterations: list[IterationRecord] = []
    previous: CampaignRun | None = None
    for index in range(n):
        iteration = index + 1
        verdict = "valid" if iteration >= 2 else "inconclusive"
        admitted = (f"ev-{iteration}",) if verdict == "valid" else ()
        events.append(
            CampaignEventType.ARBITER_DECIDED,
            iteration=iteration,
            payload={
                "decision_id": f"d-{iteration}",
                "verdict": verdict,
                "unmet_obligations": [] if admitted else ["critic:numerical"],
                "obligation_results": {"critic:numerical": bool(admitted)},
            },
            at=f"t-{iteration}a",
        )
        if admitted:
            events.append(
                CampaignEventType.EVIDENCE_ADMITTED,
                iteration=iteration,
                payload={"evidence_id": admitted[0]},
                at=f"t-{iteration}b",
            )
        events.append(
            CampaignEventType.ITERATION_COMPLETED,
            iteration=iteration,
            payload={"iteration": iteration},
            at=f"t-{iteration}c",
        )
        budget.settle(
            charge_id=f"charge-{iteration}", action_id=f"action-{iteration}",
            iteration=iteration, family=ActionFamily.EXPLORE, realized=1.0,
            predicted=1.0,
        )
        effects.mark(f"effect-{iteration}", f"ref-{iteration}")
        iterations.append(
            IterationRecord(
                iteration=iteration,
                selected_action_id=f"action-{iteration}",
                execution_id=f"exec-{iteration}",
                evidence_ids=(f"ev-{iteration}",),
                arbiter_decision_id=f"d-{iteration}",
                arbiter_verdict=verdict,
                admitted_evidence_ids=admitted,
                predicted_cost=1.0,
                realized_cost=1.0,
            )
        )
        run = CampaignRun(
            run_id=RUN_ID, campaign_id="campaign-ser01",
            state=ExecutionState.READY, iteration=iteration, max_iterations=n,
            iterations=tuple(iterations), event_log_digest=events.head_digest,
        )
        if previous is not None:
            _copy_iteration_continuation(previous, run)
        store.save_state(
            run=run, events=events, budget=budget, effects=effects,
            obligation_state={"critic:numerical": iteration >= 2},
        )
        previous = run
    return store


def _loads(payload):
    """Load and resume; either step may refuse."""
    store = IncrementalCheckpointStore.from_dict(payload)
    return store.latest()


def test_ser01_an_untampered_store_still_resumes():
    restored = _loads(copy.deepcopy(_store().to_dict()))
    assert dict(restored.obligation_state) == {"critic:numerical": True}
    assert restored.run.iterations[-1].admitted_evidence_ids == ("ev-3",)


def test_ser01_t1_edited_obligation_state_with_recomputed_digest_is_refused():
    payload = copy.deepcopy(_store().to_dict())
    payload["checkpoints"][-1]["obligation_state"] = {
        "critic:numerical": True, "certification": True,
    }
    payload["checkpoint_head_digest"] = CampaignCheckpointV3.from_dict(
        payload["checkpoints"][-1]
    ).digest
    with pytest.raises(REFUSED):
        _loads(payload)


def test_ser01_t1b_flipping_an_unmet_obligation_is_refused():
    """The first checkpoint says critic:numerical is unmet; flip it."""
    store = _store(1)
    payload = copy.deepcopy(store.to_dict())
    payload["checkpoints"][-1]["obligation_state"] = {"critic:numerical": True}
    payload["checkpoint_head_digest"] = CampaignCheckpointV3.from_dict(
        payload["checkpoints"][-1]
    ).digest
    with pytest.raises(REFUSED):
        _loads(payload)


def test_ser01_t2_rewritten_iteration_record_is_refused():
    payload = copy.deepcopy(_store().to_dict())
    entry = payload["iteration_journal"][0]
    record = entry["record"]
    record["arbiter_verdict"] = "valid"
    forged = ["forged-evidence"]
    if isinstance(record.get("admitted_evidence_ids"), dict):
        record["admitted_evidence_ids"] = {**record["admitted_evidence_ids"], "items": forged}
    else:
        record["admitted_evidence_ids"] = forged
    # Re-chain every later entry and the checkpoints that commit to them.
    entries = payload["iteration_journal"]
    for index, item in enumerate(entries):
        if index:
            item["prev_digest"] = IterationJournalEntry.from_dict(entries[index - 1]).digest
    head = IterationJournalEntry.from_dict(entries[-1]).digest
    previous_digest = ""
    for checkpoint in payload["checkpoints"]:
        count = checkpoint["iteration_record_count"]
        checkpoint["iteration_head_digest"] = IterationJournalEntry.from_dict(
            entries[count - 1]
        ).digest
        checkpoint["previous_checkpoint_digest"] = previous_digest
        previous_digest = CampaignCheckpointV3.from_dict(checkpoint).digest
    payload["checkpoint_head_digest"] = previous_digest
    assert head == payload["checkpoints"][-1]["iteration_head_digest"]
    with pytest.raises(REFUSED):
        _loads(payload)


def _legacy_file(tmp_path, *, tamper: bool):
    legacy = CheckpointStore()
    for checkpoint in _store().history:
        legacy.save(checkpoint)
    payload = legacy.to_dict()
    if tamper:
        payload["checkpoints"][-1]["obligation_state"] = {
            "critic:numerical": True, "certification": True,
        }
    path = tmp_path / "legacy.json"
    path.write_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return path


def test_ser01_t3_legacy_file_is_not_migrated_implicitly(tmp_path):
    path = _legacy_file(tmp_path, tamper=False)
    with pytest.raises(PersistenceIntegrityError):
        IncrementalCheckpointStore.load_from_path(path)
    migrated = IncrementalCheckpointStore.load_from_path(path, allow_legacy_migration=True)
    assert dict(migrated.latest().obligation_state) == {"critic:numerical": True}


def test_ser01_t3_tampered_legacy_file_is_refused_even_when_migration_is_requested(tmp_path):
    path = _legacy_file(tmp_path, tamper=True)
    with pytest.raises(REFUSED):
        IncrementalCheckpointStore.load_from_path(
            path, allow_legacy_migration=True
        ).latest()


def test_ser01_event_log_docstring_no_longer_claims_tamper_evidence():
    from engcore.sria.campaign import events

    doc = events.__doc__ or ""
    assert "This is tamper-evidence" not in doc
    assert "accidental" in doc
