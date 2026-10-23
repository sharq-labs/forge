"""GEN2-BR1.1 review round 13: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md section 9).

Round 13 reviewed ``3b407ddb`` (the round-12 fix) and found that a handed state that was not read back kept only its
length, so a restore plus one more charge re-admitted the executed action (F13-02 = R13-C-F1 = R13-A-F2 = R13-B-F2,
MAJOR); that account content raising a ``BaseException`` left every verification with no trace, so a restore
re-dispatched (R13-C-F2 = R13-A-F1 = F13-03 = R13-B-F3); and that the snapshot built ``dict(mapping)`` before reading
entries, so key objects' own ``__hash__``/``__eq__`` merged or wiped accounts (R13-B-F1, MAJOR).  These pin the fixes: a
state not read back is observed as its entry objects (a later state must begin with exactly them), content raising any
non-interrupt ``BaseException`` is a classified failure and an interrupt is re-raised only after the comparison, the
mapping's entries are listed without hashing its keys, and the fresh-thread retry's MINORs (the completion race, one
thread per account, one deadline per verification, the private cache, a verification in flight until it compared)."""

from __future__ import annotations

import asyncio
import threading
import time
import types
from collections.abc import Mapping

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.base import WorldRefused
from engcore.mind.world.projection import project_world
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _desk(o, accounts, executor):
    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    return reader, authorities, ExecutionDesk(authorities, executor, accept_synthetic=True).gateway(), r


def _refused(gateway, admitted):
    try:
        gateway.dispatch(admitted)
        return False
    except DispatchRefused:
        return True


class _SelfFillingNote:                                                    # the interpreter's mutation error, every time
    def __str__(self):
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


# ---- F13-02 / R13-C-F1 (MAJOR): a state not read back is observed as its entry objects ---------------------------------------
@pytest.mark.parametrize("after_restore", ["one_other_charge", "nothing"])
def test_a_spend_not_read_back_is_never_readmitted_after_a_restore_and_another_charge(after_restore):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=1.0, detail=_SelfFillingNote())

    reader, authorities, gateway, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    with pytest.raises(OwnerUnavailable):                                  # handed the spend, not read back
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = before                                                # restore (object replaced)
    if after_restore == "one_other_charge":                                # then another action's charge: the length
        o.ledgers[lid].settle(charge_id="other.1", action_id="other", iteration=2, family=ActionFamily.EXPLORE,
                              realized=0.5)                                # is back where the spend left it
    assert _readmitted(o, authorities, gateway) is False and len(calls) == 1   # a fresh world from the owners now
    assert _refused(gateway, r.admitted) and len(calls) == 1


def _readmitted(o, authorities, gateway):
    """Whether a world projected from the owners now admits and dispatches the action again (as a Mind would)."""
    try:
        world = project_world(o.declaration, authorities)
    except OwnerUnavailable:
        return False
    result = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    return result.admitted is not None and not _refused(gateway, result.admitted)


def test_an_honest_account_not_read_back_is_read_once_it_moves_on_in_place():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    real = live.to_dict
    state = {"moving": True}

    def mutating():
        if state["moving"]:
            raise RuntimeError("dictionary changed size during iteration")
        return real()

    object.__setattr__(live, "to_dict", mutating)
    with pytest.raises(OwnerUnavailable, match="moved while it was serialized"):
        reader.read(OwnerKind.EXPERIMENT, eid)
    live.record(ScientificEvaluation("camp.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    state["moving"] = False
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None and reader._diverged == {}
    o.experiments[eid] = ScientificExperiment.from_dict(real())             # then a checkpoint restore of the same
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None and reader._diverged == {}   # content: its history decides


# ---- R13-C-F2 / R13-A-F1 / F13-03: content raising a BaseException is a classified failure; an interrupt is re-raised ------------
class _Halt(BaseException):
    pass


class _RaisesOnStr:
    def __init__(self, exc_type):
        self.exc_type = exc_type

    def __str__(self):
        raise self.exc_type("from the account's content")


class _ExceptionRaisingOnStr(Exception):                                   # an Exception whose own rendering raises one
    def __str__(self):
        raise _Halt("rendering")


class _ExceptionInContent:
    def __str__(self):
        raise _ExceptionRaisingOnStr()


@pytest.mark.parametrize("detail", [_RaisesOnStr(_Halt), _RaisesOnStr(asyncio.CancelledError), _ExceptionInContent()],
                         ids=["base_exception", "cancelled", "rendering_raises_base_exception"])
def test_content_raising_a_base_exception_is_refused_and_never_redispatched(detail):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=1.0, detail=detail)

    reader, authorities, gateway, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    with pytest.raises(OwnerUnavailable):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = before
    assert _refused(gateway, r.admitted) and len(calls) == 1


def test_an_account_raising_a_base_exception_no_world_reads_refuses_no_admission():
    o = ax.owned("battery")
    side = BudgetLedger(total_budget=10.0)
    side.settle(charge_id="c", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0,
                detail=_RaisesOnStr(_Halt))
    reader = BudgetReader.following(lambda: ({**o.ledgers, "side.ledger": side}, dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    assert admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities).feasible


class _Interrupt(KeyboardInterrupt):
    pass


def test_an_interrupted_read_back_is_re_raised_after_the_spend_was_observed():
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    detail = _RaisesOnStr(_Interrupt)

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=1.0, detail=detail)

    reader, authorities, gateway, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    with pytest.raises(_Interrupt):                                        # the interrupt still reaches the caller
        reader.pinned()
    assert reader._in_flight == set()
    o.ledgers[lid] = before
    assert _refused(gateway, r.admitted) and len(calls) == 1               # ...after the spend was recorded


# ---- R13-B-F1 / R13-CRIT-1 (MAJOR): a handed mapping is read as a dict, from the dict's own storage ---------------------------------
def _lying(kind, hidden):
    """A dict subclass whose own methods misstate its entries (it says it is empty, or skips ``hidden``)."""

    class Lying(dict):
        def __len__(self):
            return 0 if kind == "says_empty" else dict.__len__(self)

        def __bool__(self):
            return kind != "says_empty"

        def __iter__(self):
            return iter([k for k in dict.keys(self) if k != hidden])

        def keys(self):
            return [k for k in dict.keys(self) if k != hidden]

        def items(self):
            return [(k, v) for k, v in dict.items(self) if k != hidden]

    return Lying


@pytest.mark.parametrize("kind", ["says_empty", "skips_the_solver"])
def test_a_dict_subclass_never_hides_a_handed_account(kind):
    o = ax.owned("battery")
    lid = _solver(o)
    state = {"spent": False}
    stale = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    lying = _lying(kind, lid)

    def accounts():
        return (lying(o.ledgers) if state["spent"] else dict(o.ledgers)), dict(o.experiments)

    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=1.0)
        state["spent"] = True

    reader, authorities, gateway, r = _desk(o, accounts, executor)
    gateway.dispatch(r.admitted)
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(o.ledgers[lid].revision)   # the spent one
    o.ledgers[lid] = stale
    state["spent"] = False
    assert _refused(gateway, r.admitted) and len(calls) == 1


def test_a_handed_mapping_that_is_not_a_dict_refuses_the_verification():
    o = ax.owned("battery")

    class Pairs(Mapping):
        def __init__(self, d):
            self.d = d

        def __getitem__(self, key):
            return self.d[key]

        def __iter__(self):
            return iter(self.d)

        def __len__(self):
            return len(self.d)

    state = {"pairs": False}
    reader = BudgetReader.following(lambda: ((Pairs(o.ledgers) if state["pairs"] else dict(o.ledgers)),
                                             dict(o.experiments)))
    state["pairs"] = True
    with pytest.raises(OwnerUnavailable, match="no pair of account mappings"):
        reader.read(OwnerKind.BUDGET_LEDGER, _solver(o))


def test_the_strict_constructor_reads_a_dict_from_its_own_storage():
    lying = _lying("skips", "B")
    reader = BudgetReader(lying({"A": BudgetLedger(total_budget=10.0), "B": BudgetLedger(total_budget=99.0)}), {})
    assert sorted(reader._ledgers) == ["A", "B"]
    with pytest.raises(WorldRefused, match="is a dict"):
        BudgetReader(types.MappingProxyType({"A": BudgetLedger(total_budget=10.0)}), {})


# ---- R13-CRIT-2: a later, shorter state not read back never replaces a longer one ----------------------------------------------
def test_a_shorter_state_not_read_back_never_replaces_a_longer_one():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    real = live.to_dict
    state = {"moving": True}

    def mutating():
        if state["moving"]:
            raise RuntimeError("dictionary changed size during iteration")
        return real()

    object.__setattr__(live, "to_dict", mutating)
    for i in (1, 2):
        live.record(ScientificEvaluation(f"camp.{i}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    with pytest.raises(OwnerUnavailable):                                  # not read back with two new entries
        reader.read(OwnerKind.EXPERIMENT, eid)
    live._evaluations.pop()                                                # in place, back one entry
    with pytest.raises(OwnerUnavailable):                                  # not read back with one
        reader.read(OwnerKind.EXPERIMENT, eid)
    state["moving"] = False
    with pytest.raises(OwnerUnavailable, match="behind"):                  # readable now, between the two: behind
        reader.read(OwnerKind.EXPERIMENT, eid)


# ---- E13-F1 / F13-01 / D13-1: a fresh thread that completes just after the wait is read, not refused for good ----------------------
def test_a_fresh_thread_completing_after_the_wait_is_read_not_refused_for_good(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    release = threading.Event()

    def to_dict():
        if threading.current_thread().name == "V":
            raise RecursionError("maximum recursion depth exceeded")
        if threading.current_thread().name == "budget-read-back":
            release.wait(10)                                               # completes only when released
        return real()

    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    object.__setattr__(live, "to_dict", to_dict)
    monkeypatch.setattr(BudgetReader, "WAIT_S", 0.2)
    real_alive = threading.Thread.is_alive

    def is_alive(thread):                                                  # the thread finishes exactly at the check
        if thread.name == "budget-read-back" and not release.is_set():
            release.set()
            thread.join(10)
        return real_alive(thread)

    monkeypatch.setattr(threading.Thread, "is_alive", is_alive)
    out = {}

    def verifier():
        try:
            out["v"] = reader.read(OwnerKind.EXPERIMENT, eid)
        except OwnerUnavailable as exc:
            out["v"] = str(exc)

    t = threading.Thread(target=verifier, name="V")
    t.start()
    t.join(10)
    assert not isinstance(out["v"], str), out["v"]                         # read back and served, not refused
    assert reader._diverged == {}


# ---- E13-F5 / R13-C-F4 / R13-A-F4 / R13-B-F4: one fresh read-back thread per account at a time -------------------------------------
def test_a_blocked_fresh_thread_is_not_joined_by_another_for_the_same_account(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    release = threading.Event()

    def to_dict():
        if threading.current_thread().name.startswith("V"):
            raise RecursionError("maximum recursion depth exceeded")
        if threading.current_thread().name == "budget-read-back":
            release.wait(10)
        return real()

    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    object.__setattr__(live, "to_dict", to_dict)
    monkeypatch.setattr(BudgetReader, "WAIT_S", 0.2)
    try:
        for i in range(3):
            t = threading.Thread(target=lambda: _swallow(lambda: reader.read(OwnerKind.EXPERIMENT, eid)), name=f"V{i}")
            t.start()
            t.join(10)
        assert sum(1 for x in threading.enumerate() if x.name == "budget-read-back") == 1
    finally:
        release.set()


def test_fresh_thread_waits_share_one_deadline_per_verification(monkeypatch):
    o = ax.owned("battery")
    e1 = next(iter(o.experiments))
    e2 = ax.experiment("other.campaign", 400, 3)
    release = threading.Event()
    reader = BudgetReader.following(lambda: (dict(o.ledgers), {**o.experiments, "other.campaign": e2}))
    for exp in (o.experiments[e1], e2):
        real = exp.to_dict

        def to_dict(real=real):
            if threading.current_thread().name == "V":
                raise RecursionError("maximum recursion depth exceeded")
            if threading.current_thread().name == "budget-read-back":
                release.wait(10)
            return real()

        object.__setattr__(exp, "to_dict", to_dict)
    monkeypatch.setattr(BudgetReader, "WAIT_S", 0.5)
    out = {}

    def verifier():
        t0 = time.perf_counter()
        _swallow(reader.pinned)
        out["s"] = time.perf_counter() - t0

    try:
        t = threading.Thread(target=verifier, name="V")
        t.start()
        t.join(10)
        assert out["s"] < 0.9                                              # one WAIT_S in all, not one per account
    finally:
        release.set()


# ---- E13-F2: an abandoned fresh thread writes nothing the verification holds -------------------------------------------------------
def test_an_abandoned_fresh_thread_writes_into_nothing_the_verification_holds(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    release = threading.Event()
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live.record(ScientificEvaluation("camp.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))   # new content

    def to_dict():
        if threading.current_thread().name == "V":
            raise RecursionError("maximum recursion depth exceeded")
        if threading.current_thread().name == "budget-read-back":
            release.wait(10)
        return real()

    object.__setattr__(live, "to_dict", to_dict)
    monkeypatch.setattr(BudgetReader, "WAIT_S", 0.2)
    out = {}
    t = threading.Thread(target=lambda: out.__setitem__("snapshot", reader.pinned()), name="V")
    t.start()
    t.join(10)
    snapshot = out["snapshot"]
    held = dict(snapshot._readback)
    release.set()
    for x in threading.enumerate():
        if x.name == "budget-read-back":
            x.join(10)
    assert snapshot._readback == held


# ---- E13-F7: a verification interrupted inside its comparison is still in flight to the ones waiting for it ------------------------
class _RaisingContainer:
    def __contains__(self, item):
        raise _Interrupt("inside the comparison")


def test_a_verification_interrupted_inside_its_comparison_makes_its_waiters_decide_on_nothing(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    w_handed, w_go = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "W":
            w_handed.set()
            w_go.wait(10)
        return mapping

    reader = BudgetReader.following(accounts)
    real_handed = BudgetReader._handed.__func__

    def handed(cls, *a):
        snapshot = real_handed(cls, *a)
        if threading.current_thread().name == "W":
            snapshot._aliased = _RaisingContainer()
        return snapshot

    monkeypatch.setattr(BudgetReader, "_handed", classmethod(handed))
    w = threading.Thread(target=lambda: _absorb(reader.pinned), name="W", daemon=True)
    w.start()
    assert w_handed.wait(10)
    threading.Timer(0.2, w_go.set).start()                                 # W compares while D waits for it
    with pytest.raises(OwnerUnavailable, match="left without comparing"):
        reader.pinned().read(OwnerKind.EXPERIMENT, eid)
    w.join(10)


def _swallow(fn):
    try:
        fn()
    except OwnerUnavailable:
        pass


def _absorb(fn):
    try:
        fn()
    except (_Interrupt, OwnerUnavailable):
        pass
