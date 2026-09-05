"""SRIA V0.1 M5 — campaign state/event/checkpoint foundation.

Runs under pytest, and standalone via
``python -m tests.test_sria_m5_foundation``.

This is the gate the M5 brief puts before the loop: resume and idempotency are
proven here, against a toy no-op executor, so that nothing is built on an unsafe
runner. If these fail, the campaign loop must not be wired.

The effects exercised are the four the brief names — execution, evidence
admission, calibration rows, budget — plus authorization single-use, driven
through the same :class:`EffectLedger` the real runner uses.
"""

from __future__ import annotations

import json
import sys

from src.engcore.sria.campaign import (
    RESEARCH_MODE_VOCABULARY,
    BudgetExhausted,
    BudgetLedger,
    CampaignCheckpoint,
    CampaignEventLog,
    CampaignEventType,
    CampaignRun,
    ChainBroken,
    CheckpointStore,
    EffectLedger,
    ExecutionState,
    IterationRecord,
    PauseReason,
    ResumeViolation,
)
from src.engcore.sria.campaign.events import CampaignEvent
from src.engcore.sria.decision import ActionFamily


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


RUN = "run-1"


# =====================================================================
# A toy executor whose only job is to be observably called
# =====================================================================

class ToyExecutor:
    """Counts invocations. Nothing here is scientific; that is the point."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, action_id: str) -> str:
        self.calls.append(action_id)
        return f"exec-{action_id}-{len(self.calls)}"


class ToyBelief:
    """Stands in for the Gateway. Counts admissions per evidence id."""

    def __init__(self) -> None:
        self.admitted: list[str] = []

    def admit(self, evidence_id: str) -> str:
        self.admitted.append(evidence_id)
        return evidence_id


class ToyMemory:
    """Stands in for calibration memory. Counts recorded rows."""

    def __init__(self) -> None:
        self.rows: list[str] = []

    def record(self, record_id: str) -> str:
        self.rows.append(record_id)
        return record_id


class ToyAuthorization:
    """Single-use authorization, as M3 froze it."""

    def __init__(self) -> None:
        self.consumed: set[str] = set()

    def consume(self, code: str) -> bool:
        if code in self.consumed:
            return False
        self.consumed.add(code)
        return True


# =====================================================================
# Event log: append-only and tamper-evident
# =====================================================================

def test_event_log_is_append_only_and_ordered():
    log = CampaignEventLog(RUN)
    log.append(CampaignEventType.CAMPAIGN_CREATED, iteration=0)
    log.append(CampaignEventType.SNAPSHOT_CREATED, iteration=1, payload={"d": "abc"})
    log.append(CampaignEventType.ACTION_SELECTED, iteration=1, payload={"a": "A"})

    assert [e.sequence for e in log] == [0, 1, 2]
    assert log.verify_chain() is True
    # No update, no delete, no insert: the public surface has none.
    for forbidden in ("remove", "pop", "insert", "update", "delete", "__setitem__"):
        assert not hasattr(log, forbidden), forbidden


def test_event_chain_detects_truncation_and_edits():
    log = CampaignEventLog(RUN)
    for i in range(4):
        log.append(CampaignEventType.ITERATION_COMPLETED, iteration=i)
    events = list(log.events)

    # Drop a middle event.
    truncated = events[:1] + events[2:]
    _raises(ChainBroken, CampaignEventLog, RUN, tuple(truncated))

    # Edit a payload in place (rebuilding the event, since events are frozen).
    edited = list(events)
    edited[2] = CampaignEvent(
        sequence=2,
        event_type=CampaignEventType.ITERATION_COMPLETED,
        run_id=RUN,
        iteration=99,                       # <- changed
        prev_digest=edited[2].prev_digest,
    )
    _raises(ChainBroken, CampaignEventLog, RUN, tuple(edited))


def test_event_log_round_trips_and_verifies_head():
    log = CampaignEventLog(RUN)
    log.append(CampaignEventType.CAMPAIGN_CREATED, iteration=0)
    log.append(CampaignEventType.EXECUTION_COMPLETED, iteration=1, payload={"c": 2.0})
    reloaded = CampaignEventLog.from_dict(json.loads(json.dumps(log.to_dict())))
    assert reloaded.head_digest == log.head_digest
    assert len(reloaded) == 2

    tampered = json.loads(json.dumps(log.to_dict()))
    tampered["head_digest"] = "0" * 64
    _raises(ChainBroken, CampaignEventLog.from_dict, tampered)


def test_event_queries_support_resume_decisions():
    log = CampaignEventLog(RUN)
    log.append(CampaignEventType.EXECUTION_COMPLETED, iteration=1)
    log.append(CampaignEventType.EVIDENCE_ADMITTED, iteration=1, payload={"e": "ev1"})
    log.append(CampaignEventType.EXECUTION_COMPLETED, iteration=2)

    assert log.has(CampaignEventType.EXECUTION_COMPLETED, iteration=1)
    assert not log.has(CampaignEventType.EVIDENCE_ADMITTED, iteration=2)
    assert log.last(CampaignEventType.EVIDENCE_ADMITTED).payload["e"] == "ev1"
    assert len(log.in_iteration(1)) == 2


# =====================================================================
# Lifecycle is operational, not a research mode
# =====================================================================

def test_execution_state_is_not_a_research_mode_vocabulary():
    """No lifecycle state may name an action family."""
    states = {s.value.lower() for s in ExecutionState}
    assert states & RESEARCH_MODE_VOCABULARY == set()
    for family in ActionFamily:
        assert family.value.lower() not in states


def test_a_paused_or_failed_run_must_explain_itself():
    _raises(
        ValueError,
        CampaignRun,
        run_id=RUN,
        campaign_id="c",
        state=ExecutionState.PAUSED,
    )
    _raises(
        ValueError,
        CampaignRun,
        run_id=RUN,
        campaign_id="c",
        state=ExecutionState.FAILED,
    )
    ok = CampaignRun(
        run_id=RUN,
        campaign_id="c",
        state=ExecutionState.PAUSED,
        pause_reason=PauseReason.NO_ACTION_WORTH_BUYING,
    )
    assert ok.pause_reason is PauseReason.NO_ACTION_WORTH_BUYING


def test_campaign_run_is_bounded_and_never_certifies():
    _raises(ValueError, CampaignRun, run_id=RUN, campaign_id="c", max_iterations=0)
    run = CampaignRun(run_id=RUN, campaign_id="c", max_iterations=3)
    assert run.is_certification is False
    assert run.is_terminal is False


def test_campaign_run_round_trips():
    run = CampaignRun(
        run_id=RUN,
        campaign_id="c",
        max_iterations=2,
        iteration=1,
        iterations=(
            IterationRecord(
                iteration=1,
                snapshot_digest="s1",
                selected_action_id="A",
                predicted_cost=1.0,
                realized_cost=3.0,
                admitted_evidence_ids=("ev-1",),
            ),
        ),
    )
    reloaded = CampaignRun.from_dict(json.loads(json.dumps(run.to_dict())))
    assert reloaded.to_dict() == run.to_dict()
    assert reloaded.record(1).cost_overrun == 2.0
    assert reloaded.admitted_evidence_ids == ("ev-1",)


# =====================================================================
# Budget: predicted and realized are different things
# =====================================================================

def test_predicted_and_realized_cost_stay_distinct():
    ledger = BudgetLedger(total_budget=10.0)
    charge = ledger.settle(
        charge_id="c1",
        action_id="A",
        iteration=1,
        family=ActionFamily.EXPLORE,
        realized=3.0,
        predicted=1.0,
    )
    assert charge.predicted == 1.0
    assert charge.realized == 3.0
    assert charge.overrun == 2.0
    # Only the realized amount moves the budget.
    assert ledger.spent_total == 3.0
    assert ledger.remaining == 7.0
    assert ledger.total_overrun == 2.0


def test_budget_cannot_be_double_charged():
    ledger = BudgetLedger(total_budget=10.0)
    first = ledger.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=4.0,
    )
    second = ledger.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=4.0,
    )
    assert second is first
    assert len(ledger.charges) == 1
    assert ledger.spent_total == 4.0


def test_hard_budget_is_enforced_at_selection_not_at_settlement():
    """M5.1: enforcement is a *selection* rule; settlement only observes.

    M5 raised from ``settle``, which refused to record compute that had already
    been spent. A ledger that will not write down a real cost reports a budget
    reality has already broken.
    """
    ledger = BudgetLedger(total_budget=5.0)
    ledger.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=4.0,
    )
    # Enforcement: the next action is not affordable, so it is never selected.
    assert ledger.affordable(2.0, family=ActionFamily.EXPLORE) is False
    assert ledger.general_pool == 1.0
    assert ledger.is_overrun is False


def test_a_realized_overrun_is_recorded_in_full():
    """remaining 2, predicted 1, realized 5 -> recorded, overrun 3."""
    ledger = BudgetLedger(total_budget=5.0)
    ledger.settle(
        charge_id="c0", action_id="prior", iteration=1,
        family=ActionFamily.EXPLORE, realized=3.0,
    )
    assert ledger.remaining == 2.0
    assert ledger.affordable(1.0, family=ActionFamily.EXPLORE) is True

    charge = ledger.settle(
        charge_id="c1", action_id="A", iteration=2,
        family=ActionFamily.EXPLORE, realized=5.0, predicted=1.0,
    )
    assert charge.realized == 5.0                  # nothing was truncated
    assert charge.predicted == 1.0                 # the decision is untouched
    assert charge.overrun == 4.0                   # prediction error
    assert ledger.spent_total == 8.0
    assert ledger.overrun == 3.0                   # past the declared budget
    assert ledger.is_overrun is True
    assert ledger.remaining == 0.0
    # And no further ordinary action can be selected.
    assert ledger.affordable(0.01, family=ActionFamily.EXPLORE) is False


def test_declared_budget_is_not_an_enforced_cap():
    """The ledger will not claim a guarantee the executor cannot provide."""
    declared = BudgetLedger(total_budget=5.0)
    assert declared.enforced_cap is None
    assert "no executor-enforced resource cap" in declared.guarantee_statement
    assert "cannot be prevented mid-run" in declared.guarantee_statement

    capped = BudgetLedger(
        total_budget=5.0, enforced_cap=5.0,
        enforced_cap_source="toy executor wall-clock kill",
    )
    assert capped.enforced_cap == 5.0
    assert "executor-enforced cap" in capped.guarantee_statement
    # A cap without an enforcer is a declaration wearing a stronger word.
    _raises(ValueError, BudgetLedger, total_budget=5.0, enforced_cap=5.0)


def test_validation_reservation_is_protected_from_ordinary_actions():
    ledger = BudgetLedger(total_budget=10.0, reserved_validation_budget=4.0)
    assert ledger.general_pool == 6.0
    assert ledger.validation_pool == 4.0

    assert ledger.affordable(6.0, family=ActionFamily.EXPLORE) is True
    assert ledger.affordable(6.5, family=ActionFamily.EXPLORE) is False
    assert ledger.affordable(9.0, family=ActionFamily.VALIDATE) is True

    ledger.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=6.0,
    )
    # The reservation survives an ordinary action consuming the whole general
    # pool — that is the M4 guarantee this ledger inherits.
    assert ledger.validation_pool == 4.0
    assert ledger.affordable(1.0, family=ActionFamily.EXPLORE) is False

    # Even if an ordinary action somehow overran, it draws nothing from the
    # reservation: certification money is not available to it at any point.
    probe = BudgetLedger(total_budget=10.0, reserved_validation_budget=4.0)
    probe.settle(
        charge_id="x", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=12.0,
    )
    assert probe.charges[0].from_validation_reservation == 0.0
    assert probe.charges[0].from_general_pool == 12.0
    assert probe.validation_pool == 4.0        # still not its money
    assert probe.is_overrun is True
    assert probe.overrun == 2.0

    validation = ledger.settle(
        charge_id="c3", action_id="V", iteration=2,
        family=ActionFamily.VALIDATE, realized=4.0,
    )
    assert validation.from_validation_reservation == 4.0
    assert validation.from_general_pool == 0.0


def test_budget_ledger_projects_onto_the_frozen_m4_plan():
    ledger = BudgetLedger(total_budget=10.0, reserved_validation_budget=3.0)
    ledger.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=2.0,
    )
    plan = ledger.to_plan()
    assert plan.total_budget == 10.0
    assert plan.reserved_validation_budget == 3.0
    assert plan.spent_general == 2.0
    assert plan.general_pool == 5.0


def test_budget_ledger_round_trips():
    ledger = BudgetLedger(total_budget=8.0, reserved_validation_budget=2.0)
    ledger.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.VALIDATE, realized=3.0, predicted=1.0,
    )
    reloaded = BudgetLedger.from_dict(json.loads(json.dumps(ledger.to_dict())))
    assert reloaded.spent_validation == ledger.spent_validation
    assert reloaded.spent_general == ledger.spent_general
    assert reloaded.charges[0].overrun == 2.0


# =====================================================================
# Effect ledger: the at-most-once machinery
# =====================================================================

def test_effect_runs_once_and_records_its_reference():
    ledger = EffectLedger()
    executor = ToyExecutor()
    key = ledger.key(RUN, 1, "execute", "A")

    value, performed = ledger.once(
        key, lambda: executor.execute("A"), reference=lambda v: v
    )
    assert performed is True
    assert value == "exec-A-1"
    assert ledger.reference(key) == "exec-A-1"

    value2, performed2 = ledger.once(
        key, lambda: executor.execute("A"), reference=lambda v: v
    )
    assert performed2 is False
    assert value2 is None
    assert executor.calls == ["A"]          # the effect did not happen twice


def test_marking_an_applied_effect_twice_is_refused():
    ledger = EffectLedger()
    ledger.mark("k", "ref")
    _raises(ResumeViolation, ledger.mark, "k", "ref")


def test_effect_ledger_round_trips():
    ledger = EffectLedger()
    ledger.mark(ledger.key(RUN, 1, "admit", "ev-1"), "ev-1")
    reloaded = EffectLedger.from_dict(json.loads(json.dumps(ledger.to_dict())))
    assert reloaded.is_applied(ledger.key(RUN, 1, "admit", "ev-1"))


# =====================================================================
# THE GATE — resume across a simulated interruption
# =====================================================================

def _iteration_steps(
    *,
    run_id,
    iteration,
    effects,
    budget,
    log,
    executor,
    belief,
    memory,
    authorization,
    stop_after=None,
):
    """One iteration's side effects, each guarded by the effect ledger.

    ``stop_after`` simulates a crash immediately after the named step, which is
    how the interruption in the resume tests is produced: the process simply
    stops between two guarded effects.
    """
    action_id = f"A{iteration}"
    evidence_id = f"ev-{iteration}"
    record_id = f"rec-{iteration}"

    # 1. execute
    key = effects.key(run_id, iteration, "execute", action_id)
    value, performed = effects.once(
        key, lambda: executor.execute(action_id), reference=lambda v: v
    )
    if performed:
        log.append(
            CampaignEventType.EXECUTION_COMPLETED,
            iteration=iteration,
            payload={"action_id": action_id, "execution_id": value},
        )
    if stop_after == "execute":
        return

    # 2. charge realized cost
    key = effects.key(run_id, iteration, "charge", action_id)
    _, performed = effects.once(
        key,
        lambda: budget.settle(
            charge_id=key,
            action_id=action_id,
            iteration=iteration,
            family=ActionFamily.EXPLORE,
            realized=2.0,
            predicted=1.0,
        ),
        reference=lambda c: c.charge_id,
    )
    if performed:
        log.append(
            CampaignEventType.BUDGET_UPDATED,
            iteration=iteration,
            payload={"realized": 2.0},
        )
    if stop_after == "charge":
        return

    # 3. admit evidence (consuming single-use authorization)
    key = effects.key(run_id, iteration, "admit", evidence_id)

    def _admit():
        assert authorization.consume(f"auth-{iteration}") is True
        return belief.admit(evidence_id)

    _, performed = effects.once(key, _admit, reference=lambda v: v)
    if performed:
        log.append(
            CampaignEventType.EVIDENCE_ADMITTED,
            iteration=iteration,
            payload={"evidence_id": evidence_id},
        )
    if stop_after == "admit":
        return

    # 4. calibration memory
    key = effects.key(run_id, iteration, "calibrate", record_id)
    _, performed = effects.once(
        key, lambda: memory.record(record_id), reference=lambda v: v
    )
    if performed:
        log.append(
            CampaignEventType.CALIBRATION_UPDATED,
            iteration=iteration,
            payload={"record_id": record_id},
        )

    log.append(CampaignEventType.ITERATION_COMPLETED, iteration=iteration)


def _fresh_world():
    return ToyExecutor(), ToyBelief(), ToyMemory(), ToyAuthorization()


def _checkpoint(run_id, log, budget, effects, *, iteration, state):
    return CampaignCheckpoint(
        run=CampaignRun(
            run_id=run_id,
            campaign_id="c",
            max_iterations=3,
            iteration=iteration,
            state=state,
        ),
        events=log,
        budget=budget,
        effects=effects,
    )


def test_resume_after_interruption_does_not_duplicate_anything():
    """The gate: interrupt mid-iteration, resume, verify every effect is once."""
    executor, belief, memory, authorization = _fresh_world()
    log = CampaignEventLog(RUN)
    budget = BudgetLedger(total_budget=20.0)
    effects = EffectLedger()
    store = CheckpointStore()

    # --- run iteration 1, crashing right after execution ------------------
    _iteration_steps(
        run_id=RUN, iteration=1, effects=effects, budget=budget, log=log,
        executor=executor, belief=belief, memory=memory,
        authorization=authorization, stop_after="execute",
    )
    store.save(
        _checkpoint(RUN, log, budget, effects, iteration=1,
                    state=ExecutionState.EXECUTING)
    )
    assert executor.calls == ["A1"]
    assert belief.admitted == []
    assert budget.spent_total == 0.0

    # --- resume from the checkpoint, this time to completion --------------
    resumed = CampaignCheckpoint.from_dict(
        json.loads(json.dumps(store.latest().to_dict()))
    )
    log2, budget2, effects2 = resumed.events, resumed.budget, resumed.effects

    _iteration_steps(
        run_id=RUN, iteration=1, effects=effects2, budget=budget2, log=log2,
        executor=executor, belief=belief, memory=memory,
        authorization=authorization,
    )

    # Every at-most-once effect happened exactly once.
    assert executor.calls == ["A1"]                    # not re-executed
    assert belief.admitted == ["ev-1"]                 # admitted once
    assert memory.rows == ["rec-1"]                    # one calibration row
    assert budget2.spent_total == 2.0                  # charged once
    assert len(budget2.charges) == 1
    assert authorization.consumed == {"auth-1"}        # single-use respected
    assert log2.verify_chain() is True


def test_resume_on_an_already_completed_iteration_is_a_no_op():
    executor, belief, memory, authorization = _fresh_world()
    log = CampaignEventLog(RUN)
    budget = BudgetLedger(total_budget=20.0)
    effects = EffectLedger()

    for _ in range(3):                      # replay the whole iteration 3x
        _iteration_steps(
            run_id=RUN, iteration=1, effects=effects, budget=budget, log=log,
            executor=executor, belief=belief, memory=memory,
            authorization=authorization,
        )

    assert executor.calls == ["A1"]
    assert belief.admitted == ["ev-1"]
    assert memory.rows == ["rec-1"]
    assert budget.spent_total == 2.0
    assert authorization.consumed == {"auth-1"}
    # Only the first pass wrote effect events; the later passes added only the
    # iteration marker, so nothing scientific was recorded twice.
    assert len(log.of_type(CampaignEventType.EXECUTION_COMPLETED)) == 1
    assert len(log.of_type(CampaignEventType.EVIDENCE_ADMITTED)) == 1
    assert len(log.of_type(CampaignEventType.CALIBRATION_UPDATED)) == 1
    assert len(log.of_type(CampaignEventType.BUDGET_UPDATED)) == 1


def test_resume_at_each_interruption_point_is_safe():
    """Crash after every step in turn; the end state is identical each time."""
    for stop_after in ("execute", "charge", "admit", None):
        executor, belief, memory, authorization = _fresh_world()
        log = CampaignEventLog(RUN)
        budget = BudgetLedger(total_budget=20.0)
        effects = EffectLedger()

        _iteration_steps(
            run_id=RUN, iteration=1, effects=effects, budget=budget, log=log,
            executor=executor, belief=belief, memory=memory,
            authorization=authorization, stop_after=stop_after,
        )
        checkpoint = CampaignCheckpoint.from_dict(
            json.loads(
                json.dumps(
                    _checkpoint(
                        RUN, log, budget, effects, iteration=1,
                        state=ExecutionState.EXECUTING,
                    ).to_dict()
                )
            )
        )
        _iteration_steps(
            run_id=RUN, iteration=1, effects=checkpoint.effects,
            budget=checkpoint.budget, log=checkpoint.events,
            executor=executor, belief=belief, memory=memory,
            authorization=authorization,
        )

        assert executor.calls == ["A1"], stop_after
        assert belief.admitted == ["ev-1"], stop_after
        assert memory.rows == ["rec-1"], stop_after
        assert checkpoint.budget.spent_total == 2.0, stop_after
        assert authorization.consumed == {"auth-1"}, stop_after


def test_replaying_a_processed_result_adds_no_second_contribution():
    """One experiment cannot become two pieces of belief support."""
    executor, belief, memory, authorization = _fresh_world()
    effects = EffectLedger()
    key = effects.key(RUN, 1, "admit", "ev-1")

    for _ in range(5):
        effects.once(key, lambda: belief.admit("ev-1"), reference=lambda v: v)

    assert belief.admitted == ["ev-1"]
    assert len(belief.admitted) == 1


# =====================================================================
# Checkpoint store
# =====================================================================

def test_checkpoint_store_is_append_only_and_verifies_history():
    log = CampaignEventLog(RUN)
    log.append(CampaignEventType.CAMPAIGN_CREATED, iteration=0)
    budget = BudgetLedger(total_budget=5.0)
    effects = EffectLedger()
    store = CheckpointStore()

    first = store.save(
        _checkpoint(RUN, log, budget, effects, iteration=0,
                    state=ExecutionState.READY)
    )
    log2 = CampaignEventLog(RUN, log.events)
    log2.append(CampaignEventType.ITERATION_COMPLETED, iteration=1)
    store.save(
        _checkpoint(RUN, log2, budget, effects, iteration=1,
                    state=ExecutionState.READY)
    )
    assert len(store) == 2
    assert store.latest().run.iteration == 1
    assert store.history[0].digest == first.digest

    # A checkpoint whose log shrank is a rewritten history, not a resume.
    shrunk = CampaignEventLog(RUN)
    _raises(
        ResumeViolation,
        store.save,
        _checkpoint(RUN, shrunk, budget, effects, iteration=1,
                    state=ExecutionState.READY),
    )


def test_checkpoint_rejects_a_mismatched_event_log():
    log = CampaignEventLog("some-other-run")
    _raises(
        ResumeViolation,
        _checkpoint,
        RUN, log, BudgetLedger(total_budget=1.0), EffectLedger(),
        iteration=0, state=ExecutionState.READY,
    )


def test_checkpoint_round_trips_through_json():
    log = CampaignEventLog(RUN)
    log.append(CampaignEventType.CAMPAIGN_CREATED, iteration=0)
    log.append(CampaignEventType.EXECUTION_COMPLETED, iteration=1)
    budget = BudgetLedger(total_budget=9.0, reserved_validation_budget=2.0)
    budget.settle(
        charge_id="c1", action_id="A", iteration=1,
        family=ActionFamily.EXPLORE, realized=1.5, predicted=1.0,
    )
    effects = EffectLedger()
    effects.mark("k1", "ref1")

    checkpoint = _checkpoint(
        RUN, log, budget, effects, iteration=1, state=ExecutionState.ASSESSING
    )
    reloaded = CampaignCheckpoint.from_dict(
        json.loads(json.dumps(checkpoint.to_dict()))
    )
    assert reloaded.digest == checkpoint.digest
    assert reloaded.events.verify_chain() is True
    assert reloaded.budget.spent_total == 1.5
    assert reloaded.effects.is_applied("k1")


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA V0.1 M5 — campaign foundation (resume/idempotency gate)")
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
        print(f"M5 foundation: FAIL ({failures}/{len(tests)}) — DO NOT BUILD THE LOOP")
        return 1
    print(f"M5 foundation: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
