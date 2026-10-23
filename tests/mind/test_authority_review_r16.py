"""Bounded R16 interruption/owner-history regression controls; no scientific validation."""
from tests.mind.publication_support import following
import inspect
import sys
from unittest.mock import patch

import pytest

from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world import owners
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax


def _interrupt_handing(reader):
    original = BudgetReader._handed.__func__
    armed = [True]
    def interrupted(cls, *args):
        if armed:
            armed.pop()
            raise KeyboardInterrupt()
        return original(cls, *args)
    with patch.object(BudgetReader, "_handed", classmethod(interrupted)):
        with pytest.raises(KeyboardInterrupt):
            reader.pinned()


@pytest.mark.parametrize("iteration", [1, 1.0, "1"])
def test_retained_history_uses_owner_normalization(iteration):
    account = BudgetLedger(total_budget=100.)
    _settle(account, "initial")
    held = {"a": account}
    reader = following(lambda: (held, {}))
    account.settle(charge_id="new", action_id="new", iteration=iteration,
                   family="explore", realized=1.)
    _interrupt_handing(reader)
    held["a"] = BudgetLedger.from_dict(account.to_dict())
    assert reader.read(OwnerKind.BUDGET_LEDGER, "a") is not None
    assert not reader._diverged


@pytest.mark.parametrize("count", [1, 2, 3])
def test_repeated_detached_interruptions_reconcile(count):
    account = BudgetLedger(total_budget=100.)
    _settle(account, "initial")
    reader = following(lambda: ({"a": BudgetLedger.from_dict(account.to_dict())}, {}))
    _settle(account, "new")
    for _ in range(count):
        _interrupt_handing(reader)
    assert reader.read(OwnerKind.BUDGET_LEDGER, "a") is not None
    assert not reader._diverged


@pytest.mark.parametrize("checkpoint", ["handed = True", "self._uncompared[ticket] = mapping"])
def test_post_return_single_interrupt_retains_spend(checkpoint):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def execute(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, _, gateway, admitted = _desk(o, lambda: (o.ledgers, o.experiments), execute)
    saved = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(admitted.admitted)
    lines, start = inspect.getsourcelines(BudgetReader.pinned)
    line = next(start + i for i, text in enumerate(lines) if text.strip() == checkpoint)
    hits = []
    def trace(frame, event, arg):
        if event == "line" and frame.f_code is BudgetReader.pinned.__code__ and frame.f_lineno == line:
            hits.append(line)
            raise KeyboardInterrupt()
        return trace
    sys.settrace(trace)
    try:
        with pytest.raises(KeyboardInterrupt):
            reader.pinned()
    finally:
        sys.settrace(None)
    assert hits == [line]
    o.ledgers[lid] = saved
    assert _refused(gateway, admitted.admitted)
    assert calls == [1]


@pytest.mark.parametrize("kind", ["rollback", "different"])
def test_detached_pending_spend_never_disappears(kind):
    account = BudgetLedger(total_budget=100.)
    _settle(account, "initial")
    held = [account]
    reader = following(lambda: ({"a": BudgetLedger.from_dict(held[0].to_dict())}, {}))
    saved = BudgetLedger.from_dict(account.to_dict())
    _settle(account, "new")
    _interrupt_handing(reader)
    if kind == "different":
        _settle(saved, "different")
    held[0] = saved
    _interrupt_handing(reader)
    with pytest.raises(OwnerUnavailable):
        reader.read(OwnerKind.BUDGET_LEDGER, "a")


def test_unread_malformed_detached_history_stays_unresolved_then_recovers():
    account = BudgetLedger(total_budget=100.)
    _settle(account, "initial")
    reader = following(lambda: ({"a": BudgetLedger.from_dict(account.to_dict())}, {}))
    _settle(account, "new")
    _interrupt_handing(reader)
    _interrupt_handing(reader)
    real = BudgetReader._history
    # Only retained reconciliation fails: normal readback already completed.
    original_read = BudgetReader._read_back
    def read_then_break(snapshot):
        result = original_read(snapshot)
        def bad(items):
            raise ValueError("malformed retained payload")
        monkey = patch.object(BudgetReader, "_history", staticmethod(bad))
        monkey.start()
        cleanup.append(monkey)
        return result
    cleanup = []
    try:
        with patch.object(BudgetReader, "_read_back", read_then_break):
            with pytest.raises(OwnerUnavailable):
                reader.read(OwnerKind.BUDGET_LEDGER, "a")
    finally:
        for monkey in cleanup:
            monkey.stop()
    assert BudgetReader._history is real
    assert not reader._diverged
    assert reader.read(OwnerKind.BUDGET_LEDGER, "a") is not None


def test_concurrent_new_barrier_invalidates_old_reconciliation():
    import threading
    account = BudgetLedger(total_budget=100.)
    _settle(account, "initial")
    reader = following(lambda: ({"a": BudgetLedger.from_dict(account.to_dict())}, {}))
    _settle(account, "first")
    _interrupt_handing(reader)
    _interrupt_handing(reader)
    entered, resume = threading.Event(), threading.Event()
    real_history = BudgetReader._history
    real_read = BudgetReader._read_back
    local = threading.local()
    errors = []
    def read(snapshot):
        result = real_read(snapshot)
        if threading.current_thread() is worker:
            local.reconcile = True
        return result
    def history(items):
        if getattr(local, "reconcile", False):
            local.reconcile = False
            entered.set()
            assert resume.wait(5)
        return real_history(items)
    def run():
        try:
            reader.read(OwnerKind.BUDGET_LEDGER, "a")
        except BaseException as exc:
            errors.append(exc)
    worker = threading.Thread(target=run)
    with patch.object(BudgetReader, "_read_back", read), patch.object(BudgetReader, "_history", staticmethod(history)):
        worker.start()
        try:
            assert entered.wait(5)
            _settle(account, "second")
            _interrupt_handing(reader)
        finally:
            resume.set()
            worker.join(5)
    assert not worker.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], OwnerUnavailable)
    assert not reader._diverged
    assert reader.read(OwnerKind.BUDGET_LEDGER, "a") is not None




def test_owner_malformed_retained_history_never_becomes_current():
    account = BudgetLedger(total_budget=100.)
    _settle(account, "initial")
    held = {"a": account}
    reader = following(lambda: (held, {}))
    checkpoint = BudgetLedger.from_dict(account.to_dict())
    # The owner accepts this charge, but its own from_dict cannot normalize it.
    account.settle(charge_id="unread", action_id="other", iteration="not-an-integer",
                   family="explore", realized=1.)
    _interrupt_handing(reader)
    held["a"] = checkpoint
    for _ in range(2):
        with pytest.raises(OwnerUnavailable):
            reader.read(OwnerKind.BUDGET_LEDGER, "a")
    assert reader._unread_entries
    assert not reader._diverged


@pytest.mark.parametrize("rollback", [False, True])
def test_experiment_detached_histories_reconcile_without_losing_attempts(rollback):
    from engcore.scientific.experiments.experiment import ScientificExperiment
    from engcore.scientific.experiments.evaluation import ScientificEvaluation, EvaluationStatus
    o = ax.owned("battery")
    eid, account = next(iter(o.experiments.items()))
    held = [account]
    reader = following(lambda: ({}, {eid: ScientificExperiment.from_dict(held[0].to_dict())}))
    checkpoint = ScientificExperiment.from_dict(account.to_dict())
    account.record(ScientificEvaluation("new", {}, status=EvaluationStatus.NOT_CONVERGED))
    _interrupt_handing(reader)
    _interrupt_handing(reader)
    if rollback:
        held[0] = checkpoint
        with pytest.raises(OwnerUnavailable):
            reader.read(OwnerKind.EXPERIMENT, eid)
    else:
        assert reader.read(OwnerKind.EXPERIMENT, eid) is not None
    assert not reader._diverged


def test_retained_conflict_cannot_be_erased_by_returning_to_first_branch():
    account = BudgetLedger(total_budget=100.)
    _settle(account, "initial")
    held = [account]
    reader = following(lambda: ({"a": BudgetLedger.from_dict(held[0].to_dict())}, {}))
    other = BudgetLedger.from_dict(account.to_dict())
    _settle(account, "first-branch")
    _settle(other, "other-branch")
    _interrupt_handing(reader)
    held[0] = other
    _interrupt_handing(reader)
    held[0] = account
    with pytest.raises(OwnerUnavailable):
        reader.read(OwnerKind.BUDGET_LEDGER, "a")
