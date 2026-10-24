"""Round 19: a concurrent unread barrier is not proof of rewritten history."""
import inspect
import sys
import threading

import pytest

from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.owners import AccountPublication
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import ax, _settle, _solver


@pytest.mark.parametrize("detached", [False, True])
def test_changed_unread_barrier_keeps_monotonic_replacement_recoverable(detached):
    """A reads, B clears its barrier, C retains a forward replacement, then A compares.

    Checkpoints pause existing operations without replacing account reads or comparisons.
    The in-place control distinguishes an identity prefix from detached equal content.
    """
    owner = ax.owned("battery")
    ledger_id = _solver(owner)
    owner.ledgers[ledger_id] = BudgetLedger.from_dict({**owner.ledgers[ledger_id].to_dict(), "charges": []})
    source = AccountPublication()
    reader = BudgetReader.following(lambda: source.publish(owner.ledgers, owner.experiments))
    ready = {name: threading.Event() for name in ("A", "B", "C")}
    release = {name: threading.Event() for name in ready}
    outcomes, errors, threads = {}, [], []
    lines, first_line = inspect.getsourcelines(BudgetReader._observe_all)
    markers = {"A": "with self._changed:",
               "B": "if interrupted is None and pending and accepted:",
               "C": "read, interrupted = snapshot._read_back()"}
    checkpoints = {name: first_line + next(i for i, line in enumerate(lines) if line.strip() == marker)
                   for name, marker in markers.items()}

    def verify(name):
        reached = False

        def checkpoint(frame, event, arg):
            nonlocal reached
            if (not reached and event == "line" and frame.f_code is BudgetReader._observe_all.__code__
                    and frame.f_lineno == checkpoints[name]):
                reached = True
                ready[name].set()
                assert release[name].wait(10), f"checkpoint {name} was not released"
            return checkpoint

        sys.settrace(checkpoint)
        try:
            outcomes[name] = reader.pinned().read(OwnerKind.BUDGET_LEDGER, ledger_id).revision
        except OwnerUnavailable as exc:
            outcomes[name] = str(exc)
        except BaseException as exc:
            errors.append(exc)
        finally:
            sys.settrace(None)

    try:
        for name in ready:
            if name == "A" or (name == "C" and detached):
                owner.ledgers[ledger_id] = BudgetLedger.from_dict(owner.ledgers[ledger_id].to_dict())
            if name == "A":
                _settle(owner.ledgers[ledger_id], "initial")
            if name == "C":
                _settle(owner.ledgers[ledger_id], "forward")
            thread = threading.Thread(target=verify, args=(name,), name=name)
            threads.append(thread)
            thread.start()
            assert ready[name].wait(10), f"checkpoint {name} was not reached"
            if name == "B":
                # B clears the old barrier, releases the lock and times out waiting for A.
                release[name].set()
                thread.join(5)
                assert not thread.is_alive()
        assert type(reader._unread_entries[("ledger", ledger_id)]) is tuple
        release["A"].set()
        threads[0].join(10)
        assert not threads[0].is_alive()
    finally:
        for event in release.values():
            event.set()
        for thread in threads:
            thread.join(10)
    assert not any(thread.is_alive() for thread in threads)
    assert not errors, errors
    assert "in flight" in outcomes["B"]
    assert "rewrote" not in outcomes["A"]
    assert ("ledger", ledger_id) not in reader._diverged
    assert reader.read(OwnerKind.BUDGET_LEDGER, ledger_id).revision == "2"
    assert reader.pinned().read(OwnerKind.BUDGET_LEDGER, ledger_id).revision == "2"
