"""Round 15: deterministic authority lifecycle and read-back regressions.

All ordering uses events or explicit call checkpoints. Timeouts are deadlock
bounds, never scheduling inputs. Synthetic contract evidence, not validation.
"""
from __future__ import annotations

import sys
import threading
import types

import pytest

from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world import owners as ow
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import (
    _desk, _solver, _settle, _refused, _SelfFillingNote, ax,
)

K = OwnerKind.BUDGET_LEDGER


def _simple():
    account = BudgetLedger(total_budget=100.0)
    _settle(account, "initial")
    held = {"a": account}
    mode = {"sealed": False}
    def accounts():
        return (types.MappingProxyType(held) if mode["sealed"] else held), {}
    return account, held, mode, BudgetReader.following(accounts)


def _seal(reader, mode):
    mode["sealed"] = True
    with pytest.raises(OwnerUnavailable):
        reader.pinned()
    mode["sealed"] = False


def _thread(fn, name="verification"):
    box = []
    def run():
        try:
            box.append(fn())
        except BaseException as exc:
            box.append(exc)
    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread, box


def _join(thread):
    thread.join(10)
    assert not thread.is_alive(), "deterministic checkpoint did not complete"


@pytest.mark.parametrize("phase", ["accounts", "read_back"])
def test_seal_before_authoritative_comparison_refuses_inflight_pin(monkeypatch, phase):
    account, held, mode, reader = _simple()
    reached, resume = threading.Event(), threading.Event()
    if phase == "accounts":
        original = reader._follow
        def paused():
            if threading.current_thread().name == "verification":
                reached.set()
                assert resume.wait(10)
            return original()
        reader._follow = paused
    else:
        original = BudgetReader._read_back
        def paused(self):
            result = original(self)
            if threading.current_thread().name == "verification":
                reached.set()
                assert resume.wait(10)
            return result
        monkeypatch.setattr(BudgetReader, "_read_back", paused)
    thread, box = _thread(lambda: reader.read(K, "a"))
    try:
        assert reached.wait(10)
        _seal(reader, mode)
    finally:
        resume.set()
        _join(thread)
    assert len(box) == 1 and isinstance(box[0], OwnerUnavailable)
    assert not reader._in_flight


def test_seal_while_comparison_waits_refuses_after_wait(monkeypatch):
    account, held, mode, reader = _simple()
    handing, release, waiting = threading.Event(), threading.Event(), threading.Event()
    original = reader._follow
    def accounts():
        if threading.current_thread().name == "sealer":
            handing.set()
            assert release.wait(10)
            return types.MappingProxyType(held), {}
        return original()
    reader._follow = accounts
    wait_for = reader._changed.wait_for
    def checkpoint(predicate, timeout=None):
        waiting.set()
        return wait_for(predicate, timeout)
    monkeypatch.setattr(reader._changed, "wait_for", checkpoint)
    other, other_box = _thread(reader.pinned, "sealer")
    assert handing.wait(10)
    verifier, box = _thread(lambda: reader.read(K, "a"))
    try:
        assert waiting.wait(10)
    finally:
        release.set()
        _join(other)
        _join(verifier)
    assert isinstance(other_box[0], OwnerUnavailable)
    assert isinstance(box[0], OwnerUnavailable)
    assert not reader._in_flight


def test_comparison_is_atomic_with_seal(monkeypatch):
    account, held, mode, reader = _simple()
    original = BudgetReader._read_back
    checked = []
    class Checked(dict):
        def items(self):
            assert reader._lock.locked(), "comparison escaped the lifecycle critical region"
            checked.append(True)
            return super().items()
    def checked_read(self):
        read, interrupted = original(self)
        return Checked(read), interrupted
    monkeypatch.setattr(BudgetReader, "_read_back", checked_read)
    assert reader.read(K, "a") is not None
    assert checked


def test_sealed_spend_then_restore_never_redispatches(monkeypatch):
    o = ax.owned("battery")
    lid = _solver(o)
    reached, resume = threading.Event(), threading.Event()
    mode = {"proxy": False}
    calls = []
    def accounts():
        if threading.current_thread().name == "verification":
            reached.set()
            assert resume.wait(10)
        return (types.MappingProxyType(o.ledgers) if mode["proxy"] else dict(o.ledgers)), dict(o.experiments)
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, result = _desk(o, accounts, executor)
    checkpoint = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    thread, box = _thread(lambda: _refused(gateway, result.admitted))
    try:
        assert reached.wait(10)
        mode["proxy"] = True
        with pytest.raises(OwnerUnavailable):
            reader.pinned()
        o.ledgers[lid] = checkpoint
        mode["proxy"] = False
    finally:
        resume.set()
        _join(thread)
    assert box == [True] and calls == [1]


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RecursionError, MemoryError])
def test_async_or_resource_interruption_of_handing_never_retires_honest_reader(monkeypatch, failure):
    account, held, mode, reader = _simple()
    original = BudgetReader._handed.__func__
    armed = [True]
    def interrupted(cls, *args):
        if armed.pop() if armed else False:
            raise failure("injected at an explicit phase")
        return original(cls, *args)
    monkeypatch.setattr(BudgetReader, "_handed", classmethod(interrupted))
    with pytest.raises((failure, OwnerUnavailable)):
        reader.pinned()
    assert reader._sealed is None
    assert not reader._in_flight
    assert reader.read(K, "a") is not None


def test_interrupt_at_entry_listing_preserves_previously_read_spend(monkeypatch):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, result = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    checkpoint = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    original = BudgetReader._entries
    armed = [True]
    def interrupted(self, key):
        if key[0] == "experiment" and armed:
            armed.pop()
            raise KeyboardInterrupt()
        return original(self, key)
    with monkeypatch.context() as patch:
        patch.setattr(BudgetReader, "_entries", interrupted)
        with pytest.raises(KeyboardInterrupt):
            reader.pinned()
    o.ledgers[lid] = checkpoint
    assert _refused(gateway, result.admitted) and calls == [1]


@pytest.mark.parametrize("variant", ["rollback", "aba", "lying", "unread_rollback"])
def test_readback_must_reconcile_listed_entries_before_authorizing(monkeypatch, variant):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, result = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    live = o.ledgers[lid]
    earlier, payload = live.charges, live.to_dict()
    gateway.dispatch(result.admitted)
    spent = live.charges
    real = BudgetLedger.to_dict
    def false_read():
        if variant == "lying":
            return payload
        object.__setattr__(live, "charges", earlier)
        value = real(live)
        if variant == "aba":
            object.__setattr__(live, "charges", spent)
        if variant == "unread_rollback":
            raise RuntimeError("dictionary changed size during iteration")
        return value
    object.__setattr__(live, "to_dict", false_read)
    assert _refused(gateway, result.admitted) and calls == [1]
    object.__delattr__(live, "to_dict")
    o.ledgers[lid] = BudgetLedger.from_dict(payload)
    assert _refused(gateway, result.admitted) and calls == [1]


def test_honest_growth_across_unread_checkpoint_never_means_rewritten(monkeypatch):
    account, held, mode, reader = _simple()
    original = BudgetReader._account
    key = ("ledger", "a")
    def growing(self, account_key):
        if account_key == key:
            _settle(account, "middle")
            # A second verification observed this prefix while this read ran.
            with reader._changed:
                reader._note_unread(key, account.charges)
            _settle(account, "after")
        return original(self, account_key)
    with monkeypatch.context() as patch:
        patch.setattr(BudgetReader, "_account", growing)
        try:
            reader.read(K, "a")
        except OwnerUnavailable:
            pass  # safe transient refusal is allowed
    assert key not in reader._diverged
    assert reader.read(K, "a") is not None


def test_unchanged_detached_accounts_recover_after_interrupt(monkeypatch):
    account, held, mode, reader = _simple()
    reader._follow = lambda: ({k: BudgetLedger.from_dict(v.to_dict()) for k,v in held.items()}, {})
    original = BudgetReader._account
    armed = [True]
    def interrupted(self, key):
        if armed:
            armed.pop()
            raise KeyboardInterrupt()
        return original(self, key)
    with monkeypatch.context() as patch:
        patch.setattr(BudgetReader, "_account", interrupted)
        with pytest.raises(KeyboardInterrupt):
            reader.pinned()
    assert reader.read(K, "a") is not None
    assert reader._sealed is None and not reader._diverged


def test_readback_straddling_honest_growth_recovers_after_transient_failure(monkeypatch):
    account, held, mode, reader = _simple()
    original = BudgetReader._account
    armed = [True]
    def growing(self, key):
        if armed:
            armed.pop()
            _settle(account, "growth")
        return original(self, key)
    with monkeypatch.context() as patch:
        patch.setattr(BudgetReader, "_account", growing)
        try:
            reader.read(K, "a")
        except OwnerUnavailable:
            pass
    def moving():
        raise RuntimeError("dictionary changed size during iteration")
    object.__setattr__(account, "to_dict", moving)
    with pytest.raises(OwnerUnavailable):
        reader.read(K, "a")
    object.__delattr__(account, "to_dict")
    held["a"] = BudgetLedger.from_dict(account.to_dict())
    assert reader.read(K, "a") is not None
    assert not reader._diverged


def test_repeated_content_interrupt_is_explicit_never_success_or_poison():
    account, held, mode, reader = _simple()
    class Interrupted:
        def __str__(self):
            raise KeyboardInterrupt("account content")
    _settle(account, "interrupt", Interrupted())
    for _ in range(2):
        with pytest.raises(KeyboardInterrupt):
            reader.read(K, "a")
    assert reader._sealed is None and not reader._diverged



def test_seal_after_waited_verification_completes_still_refuses(monkeypatch):
    account, held, mode, reader = _simple()
    handing, release, waiting = threading.Event(), threading.Event(), threading.Event()
    original = reader._follow
    def accounts():
        if threading.current_thread().name == "other":
            handing.set()
            assert release.wait(10)
        return original()
    reader._follow = accounts
    wait_for = reader._changed.wait_for
    def checkpoint(predicate, timeout=None):
        waiting.set()
        result = wait_for(predicate, timeout)
        # Exact boundary: the waited ticket has compared; a different ticket
        # seals before this waiter finishes its authoritative recheck.
        reader._changed.release()
        try:
            sealer, errors = _thread(lambda: _seal(reader, mode), "sealer")
            _join(sealer)
            assert errors == [None]
        finally:
            reader._changed.acquire()
        return result
    monkeypatch.setattr(reader._changed, "wait_for", checkpoint)
    other, other_box = _thread(reader.pinned, "other")
    assert handing.wait(10)
    verifier, box = _thread(lambda: reader.read(K, "a"))
    try:
        assert waiting.wait(10)
    finally:
        release.set()
        _join(other)
        _join(verifier)
    assert isinstance(box[0], OwnerUnavailable)
    assert not reader._in_flight



def test_retired_account_never_reruns_retained_content():
    account, held, mode, reader = _simple()
    class Moving:
        calls = 0
        def __str__(self):
            self.calls += 1
            raise RuntimeError("dictionary changed size during iteration")
    note = Moving()
    _settle(account, "unread", note)
    with pytest.raises(OwnerUnavailable):
        reader.read(K, "a")
    different = BudgetLedger(total_budget=100.)
    _settle(different, "different-history")
    held["a"] = different
    with pytest.raises(OwnerUnavailable):
        reader.read(K, "a")
    assert ("ledger", "a") in reader._diverged
    calls = note.calls
    with pytest.raises(OwnerUnavailable):
        reader.read(K, "a")
    assert note.calls == calls


@pytest.mark.parametrize("base", [tuple, list])
def test_native_pair_subclasses_preserve_the_dict_handing_contract(base):
    account, held, mode, reader = _simple()
    class Pair(base):
        pass  # an honest native-container subclass, e.g. a named tuple
    reader._follow = lambda: Pair((held, {}))
    assert reader.read(K, "a") is not None
    assert reader._sealed is None

@pytest.mark.parametrize("failure", [KeyboardInterrupt, RecursionError, MemoryError])
@pytest.mark.parametrize("retry_later", [False, True])
@pytest.mark.parametrize("direct_mapping", [False, True])
def test_interrupted_handing_preserves_spend_before_detached_restore(monkeypatch, failure, retry_later, direct_mapping):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, authorities, gateway, result = _desk(o, lambda: (o.ledgers if direct_mapping else dict(o.ledgers), dict(o.experiments)), executor)
    checkpoint = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(result.admitted)
    original = BudgetReader._handed.__func__
    armed = [True, True] if retry_later else [True]
    def interrupted(cls, *args):
        if armed:
            armed.pop()
            raise failure("interrupt after execution-side handing")
        return original(cls, *args)
    with monkeypatch.context() as patch:
        patch.setattr(BudgetReader, "_handed", classmethod(interrupted))
        with pytest.raises((failure, OwnerUnavailable)):
            reader.pinned()
    assert reader._sealed is None
    assert bool(reader._uncompared) is retry_later
    o.ledgers[lid] = checkpoint
    assert _refused(gateway, result.admitted) and calls == [1]
