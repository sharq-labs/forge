"""Bounded generated authority traces; executable contract checks, not formal proof."""
from itertools import product

import pytest

from engcore.mind.world import OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r15 import _simple, _seal, _settle
from tests.mind.test_authority_review_r14 import _desk, _solver, _refused, _SelfFillingNote, ax

K = OwnerKind.BUDGET_LEDGER
# Exhaustive fixed grammar: 2 x 4 x 3 = 24 short traces, without RNG or sleeps.
TRACES = [
    (handing, effect, ending)
    for handing, effect, ending in product(
        ("same_objects", "detached"),
        ("unchanged", "spend", "top_up", "unread_spend"),
        ("continue", "restore", "seal"),
    )
]


@pytest.mark.parametrize("handing,effect,ending", TRACES)
def test_generated_owner_transition_trace(handing, effect, ending):
    account, held, mode, reader = _simple()
    checkpoint = account.to_dict()
    if handing == "detached":
        original = reader._follow
        def copies():
            ledgers, experiments = original()
            if mode["sealed"]:
                return ledgers, experiments
            return {k: BudgetLedger.from_dict(v.to_dict()) for k,v in ledgers.items()}, {}
        reader._follow = copies
    if effect == "spend":
        _settle(account, "spent")
    elif effect == "unread_spend":
        _settle(account, "spent", _SelfFillingNote())
    elif effect == "top_up":
        account.total_budget += 10.0
    try:
        observed = reader.read(K, "a")
    except OwnerUnavailable:
        observed = None
    if effect == "unread_spend":
        assert observed is None
    else:
        assert observed is not None
    if ending == "restore":
        held["a"] = BudgetLedger.from_dict(checkpoint)
    elif ending == "seal":
        _seal(reader, mode)
    must_refuse = ending == "seal" or effect == "unread_spend" or (effect == "spend" and ending == "restore")
    if must_refuse:
        with pytest.raises(OwnerUnavailable):
            reader.read(K, "a")
    else:
        assert reader.read(K, "a") is not None


# Execution traces check the observable duplicate effect, independently of pins.
@pytest.mark.parametrize("visibility,ending", list(product(
    ("read_spend", "unread_spend", "sealed_spend"),
    ("restore", "rollback_then_top_up"),
)))
def test_generated_executed_action_cannot_regain_authority(visibility, ending):
    o = ax.owned("battery")
    lid = _solver(o)
    mode = {"sealed": False}
    import types
    def accounts():
        return (types.MappingProxyType(o.ledgers) if mode["sealed"] else dict(o.ledgers)), dict(o.experiments)
    calls = []
    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], "run.1", _SelfFillingNote() if visibility == "unread_spend" else "spend")
    reader, authorities, gateway, result = _desk(o, accounts, executor)
    checkpoint = o.ledgers[lid].to_dict()
    gateway.dispatch(result.admitted)
    if visibility == "sealed_spend":
        _seal(reader, mode)
    else:
        try:
            reader.read(K, lid)
        except OwnerUnavailable:
            assert visibility == "unread_spend"
    o.ledgers[lid] = BudgetLedger.from_dict(checkpoint)
    if ending == "rollback_then_top_up":
        o.ledgers[lid].total_budget += 10.0
    assert _refused(gateway, result.admitted)
    assert calls == [1]



# Generated interleavings include start, wait, interruption and comparison.
@pytest.mark.parametrize("phase,event,restore", list(product(
    ("start", "handing", "read"), ("seal", "spend", "top_up", "interrupt"), (False, True),
)))
def test_generated_inflight_lifecycle(monkeypatch, phase, event, restore):
    import threading
    from engcore.mind.world import BudgetReader
    from tests.mind.test_authority_review_r15 import _thread, _join
    account, held, mode, reader = _simple()
    checkpoint = account.to_dict()
    reached, resume = threading.Event(), threading.Event()
    reader.WAIT_S = 0.0  # deterministic timeout of the observer while the first pin is paused
    original_accounts, original_read = reader._follow, BudgetReader._read_back
    original_handed = BudgetReader._handed.__func__
    def checkpoint_pause():
        reached.set()
        assert resume.wait(10)
        if event == "interrupt":
            raise KeyboardInterrupt()
    def accounts():
        if phase == "start" and threading.current_thread().name == "verification":
            checkpoint_pause()
        return original_accounts()
    def read_back(self):
        result = original_read(self)
        if phase == "read" and threading.current_thread().name == "verification":
            checkpoint_pause()
        return result
    def handed(cls, *args):
        if phase == "handing" and threading.current_thread().name == "verification":
            checkpoint_pause()
        return original_handed(cls, *args)
    monkeypatch.setattr(BudgetReader, "_handed", classmethod(handed))
    reader._follow = accounts
    monkeypatch.setattr(BudgetReader, "_read_back", read_back)
    thread, box = _thread(lambda: reader.read(K, "a"))
    try:
        assert reached.wait(10)
        if event == "seal":
            _seal(reader, mode)
        elif event in ("spend", "top_up"):
            if event == "spend":
                _settle(account, "spent")
            else:
                account.total_budget += 10.0
            with pytest.raises(OwnerUnavailable):
                reader.read(K, "a")  # observes effect, refuses while the first pin is in flight
        if restore:
            held["a"] = BudgetLedger.from_dict(checkpoint)
    finally:
        resume.set()
        _join(thread)
    assert len(box) == 1
    if event == "seal" or (event == "spend" and (phase == "read" or (restore and phase == "start"))):
        assert isinstance(box[0], OwnerUnavailable)
    elif event == "interrupt":
        assert isinstance(box[0], KeyboardInterrupt)
        assert reader._sealed is None and not reader._diverged
        assert reader.read(K, "a") is not None
    else:
        assert not isinstance(box[0], BaseException)
    if event == "spend" and restore:
        with pytest.raises(OwnerUnavailable):
            reader.read(K, "a")  # the retained pin may serve the spend, never the restored older state
    assert not reader._in_flight
