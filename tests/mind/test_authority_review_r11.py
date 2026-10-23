"""GEN2-BR1.1 review round 11: one control per fixed finding (benchmarks/mind_gen2_authority_v1/README.md).

Round 11 found that a handed account could still escape the follower's comparison: a read-back step outside the
classification raised on deeply nested owner content (R11-C-F1 / F11-1), and a handed mapping the constructor refused
hid the spend of every other account in it (F11-2).  It also found read-back failures classified by exception type
instead of by what happens (A11-F1 / A11-F2 / B11-1 / R11-D-F1 / R11-D-F2 / R11-C-F3).  These pin the fixes: what a
verification is handed is read entry by entry; every read-back is total and tried up to three times (three alike =
the state, refused for good; any success = observed; differing failures = moving, refused once), with a recursion
failure retried on a fresh thread; served experiment records are parsed from the owner's text; a verification waited
for that leaves without comparing makes its waiters decide on nothing; and the controls rounds 10-11 lacked."""

from __future__ import annotations

import enum
import threading
import time

import numpy as np
import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (
    Authorities, BudgetReader, DeclarationReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind,
    ScientificWorld, admit,
)
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import _lower_revision
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
_WAIT_S = getattr(BudgetReader, "WAIT_S", 1.0)                             # (a default on trees before round 10)


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _desk(o, accounts, executor):
    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    return reader, ExecutionDesk(authorities, executor, accept_synthetic=True).gateway(), r


def _refused(gateway, admitted):
    try:
        gateway.dispatch(admitted)
        return False
    except DispatchRefused:
        return True


def _nested(depth):
    value: dict = {"leaf": [1, 2]}
    for i in range(depth):
        value = {f"k{i}": value}
    return value


def _spend_then_restore(o, eid, change, accounts=None, restore=lambda: None):
    """Dispatch once (the executor records an observation and applies ``change``), let one verification be handed the
    spent state, restore the pre-run experiment by replacing it (and call ``restore``), and re-dispatch: (refused?,
    executor calls, the reader)."""
    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed"))
        change(o.experiments[eid])

    reader, gateway, r = _desk(o, accounts or (lambda: (dict(o.ledgers), dict(o.experiments))), executor)
    before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    gateway.dispatch(r.admitted)
    try:
        reader.pinned()                                                    # a verification is handed the spend
    except OwnerUnavailable:
        pass
    o.experiments[eid] = before
    restore()
    return _refused(gateway, r.admitted), len(calls), reader


# ---- R11-C-F1 / F11-1 (MAJOR): deeply nested owner content is read back by the owner's rules, not the reader's stack -------------
@pytest.mark.parametrize("depth", [3, 600, 2000])
def test_a_deeply_nested_spend_is_observed_and_its_rollback_never_redispatches(depth):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    refused, calls, reader = _spend_then_restore(o, eid, lambda e: e.metadata.__setitem__("trace", _nested(depth)))
    assert refused and calls == 1 and reader._diverged == {}               # observed, not refused for good


def test_a_deeply_nested_account_no_world_reads_refuses_no_admission():
    o = ax.owned("battery")
    side = ax.experiment("other.campaign", 400, 3)
    side.metadata["trace"] = _nested(600)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), {**o.experiments, "other.campaign": side}))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    assert admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities).feasible


# ---- F11-2 (MAJOR): one entry that is no account never hides the others ---------------------------------------------------------
class _SubLedger(BudgetLedger):
    pass


@pytest.mark.parametrize("extra", ["numpy_str_id", "str_enum_id", "subclass_account", "alias", "int_key"])
def test_a_malformed_entry_never_hides_a_spend_on_another_account(extra):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    lid = _solver(o)
    state = {"spent": False}

    class Id(str, enum.Enum):
        SIDE = "side.ledger"

    def accounts():
        ledgers = dict(o.ledgers)
        if state["spent"]:
            ledgers.update({"numpy_str_id": {np.str_("side.ledger"): BudgetLedger(total_budget=1.0)},
                            "str_enum_id": {Id.SIDE: BudgetLedger(total_budget=1.0)},
                            "subclass_account": {"side.ledger": _SubLedger(total_budget=1.0)},
                            "alias": {"side.ledger": ledgers[lid]},
                            "int_key": {7: BudgetLedger(total_budget=1.0)}}[extra])
        return ledgers, dict(o.experiments)

    refused, calls, reader = _spend_then_restore(o, eid, lambda e: state.__setitem__("spent", True), accounts,
                                                 restore=lambda: state.__setitem__("spent", False))   # entry gone
    assert refused and calls == 1                                          # the study's spend was observed
    if extra == "subclass_account":
        assert ("ledger", "side.ledger") in reader._diverged               # (private) that entry refused for good
    if extra == "alias":
        with pytest.raises(OwnerUnavailable, match="two ids"):
            state["spent"] = True
            reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid)


# ---- A11-F1 / R11-D-F2 / R11-C-F3: a failure that repeats alike is the state (for good), whatever its exception type --------------
class _Unprintable:
    def __init__(self, exc):
        self.exc = exc

    def __str__(self):
        raise self.exc


class _BadItems(dict):
    def __init__(self, exc):
        super().__init__(a=1)
        self.exc = exc

    def items(self):
        raise self.exc


@pytest.mark.parametrize("exc", [NotImplementedError("no"), RuntimeError("no"), TypeError("no")])
def test_a_ledger_spend_whose_serialization_always_fails_refuses_the_account_for_good(exc):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    reader, gateway, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), calls.append)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                          realized=2.0, detail=_Unprintable(exc))
    with pytest.raises(OwnerUnavailable, match="from then on"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = before
    assert _refused(gateway, r.admitted) and len(calls) == 1


@pytest.mark.parametrize("exc", [NotImplementedError("no"), RuntimeError("no")])
def test_an_experiment_spend_whose_serialization_always_fails_refuses_the_account_for_good(exc):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    refused, calls, reader = _spend_then_restore(o, eid, lambda e: e.metadata.__setitem__("note", _BadItems(exc)))
    assert refused and calls == 1 and ("experiment", eid) in reader._diverged


@pytest.mark.parametrize("break_it", ["no_accounting", "budget_not_its_own"])
def test_an_experiment_whose_accounting_never_matches_its_read_back_is_refused_for_good(monkeypatch, break_it):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    real = live.to_dict

    def broken():
        out = real()
        if break_it == "no_accounting":
            out.pop("accounting")
        else:
            out["accounting"] = {**out["accounting"], "remaining_observations": -1}
        return out

    monkeypatch.setattr(live, "to_dict", broken)
    with pytest.raises(OwnerUnavailable, match="from then on"):
        reader.read(OwnerKind.EXPERIMENT, eid)


def test_a_ledger_spend_its_owner_cannot_read_back_refuses_the_account_for_good():
    o = ax.owned("battery")
    lid = _solver(o)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    o.ledgers[lid].settle(charge_id=("a", "tuple"), action_id="x", iteration=1, family=ActionFamily.EXPLORE,
                          realized=1.0)                                     # its JSON list is no charge id it reads
    with pytest.raises(OwnerUnavailable, match="from then on"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)


def test_a_spend_too_deep_for_the_owners_encoder_refuses_the_account_for_good():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    deep: list = []
    cur = deep
    for _ in range(100000):
        nxt: list = []
        cur.append(nxt)
        cur = nxt
    refused, calls, reader = _spend_then_restore(o, eid, lambda e: e.metadata.__setitem__("trace", deep))
    assert refused and calls == 1 and "recursion" in reader._diverged[("experiment", eid)]


# ---- A11-F2 / R11-D-F1 / B11-1: a read torn by an honest move is refused once, never for good ----------------------------------
@pytest.mark.parametrize("kind", ["ledger", "experiment"])
def test_a_read_torn_by_an_honest_move_is_retried_not_refused_for_good(monkeypatch, kind):
    o = ax.owned("battery")
    lid, eid = _solver(o), next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.ledgers[lid] if kind == "ledger" else o.experiments[eid]
    real = live.to_dict
    torn = {"n": 0}

    def once_torn():
        out = real()
        torn["n"] += 1
        if torn["n"] == 1:                                                 # read across a two-step top-up
            if kind == "ledger":
                out["reserved_validation_budget"] = out["total_budget"] + 1.0
            else:
                out["budget"] = {**out["budget"], "max_observations": 1}
        return out

    monkeypatch.setattr(live, "to_dict", once_torn)
    record = reader.read(OwnerKind.BUDGET_LEDGER if kind == "ledger" else OwnerKind.EXPERIMENT, lid if kind == "ledger"
                         else eid)
    assert record is not None and torn["n"] == 2 and reader._diverged == {}


def test_an_account_that_keeps_moving_is_refused_once_and_read_when_it_rests(monkeypatch):
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

    monkeypatch.setattr(live, "to_dict", mutating)
    with pytest.raises(OwnerUnavailable, match="moved while it was serialized"):
        reader.read(OwnerKind.EXPERIMENT, eid)
    state["moving"] = False
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None and reader._diverged == {}


def test_a_verification_on_a_deep_call_stack_never_refuses_an_honest_account_for_good(monkeypatch):
    import sys
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict

    def depth():
        n, frame = 0, sys._getframe()
        while frame is not None:
            n, frame = n + 1, frame.f_back
        return n

    shallow = depth() + 40

    def depth_dependent():                                                 # deep enough for the caller's stack only
        if depth() > shallow:
            raise RecursionError("maximum recursion depth exceeded")
        return real()

    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    monkeypatch.setattr(live, "to_dict", depth_dependent)

    def deep(k):
        return deep(k - 1) if k else reader.read(OwnerKind.EXPERIMENT, eid)

    assert deep(60) is not None                                            # read back on a fresh, shallow thread
    assert reader._diverged == {}


def test_an_account_refused_for_good_is_not_read_back_again(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    calls = []

    def unwritable():
        calls.append(1)
        out = real()
        out["metadata"] = {"note": {1, 2}}
        return out

    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    monkeypatch.setattr(live, "to_dict", unwritable)
    with pytest.raises(OwnerUnavailable, match="from then on"):
        reader.read(OwnerKind.EXPERIMENT, eid)
    before = len(calls)
    with pytest.raises(OwnerUnavailable, match="from then on"):
        reader.read(OwnerKind.EXPERIMENT, eid)
    assert before == 3 and len(calls) == before                            # three read-backs once, none after


# ---- B11-2 / R11-C-F2 / F11-3: an account refused for good while a verification waited is refused to it ------------------------
def test_a_spend_refused_for_good_while_a_rollback_waits_refuses_the_rollback():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    p_handed, p_go = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "P":
            p_handed.set()
            p_go.wait(10)
        return mapping

    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation("run.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        o.experiments[eid].metadata["note"] = {1, 2}                       # the spent state cannot be written down

    before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    reader, gateway, r = _desk(o, accounts, executor)
    gateway.dispatch(r.admitted)
    p = threading.Thread(target=lambda: _swallow(reader.pinned), name="P", daemon=True)
    p.start()
    assert p_handed.wait(10)                                               # P holds the unwritable spend
    o.experiments[eid] = before                                            # the execution side restores
    threading.Timer(0.2, p_go.set).start()                                 # P compares while D waits for it
    assert _refused(gateway, r.admitted) and len(calls) == 1
    p.join(10)


def _swallow(fn):
    try:
        fn()
    except OwnerUnavailable:
        pass


# ---- abandonment: a verification waited for that was handed accounts and left without comparing them ---------------------------
class _Interrupted(BaseException):
    pass


def test_a_verification_waited_for_that_leaves_uncompared_makes_the_waiter_decide_on_nothing(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    entered, go = threading.Event(), threading.Event()
    real_handed = BudgetReader._handed.__func__

    def interrupted_after_handed(cls, *args):
        if threading.current_thread().name == "W":
            entered.set()
            go.wait(10)
            raise _Interrupted()                                           # W is interrupted after it was handed
        return real_handed(cls, *args)                                     # accounts, before it compares them

    # (Round 13: an exception raised inside the read-back is now a classified failure and an interrupt there is
    # re-raised only after the comparison, so W is interrupted at the snapshot step instead, where it still leaves
    # uncompared.)
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    monkeypatch.setattr(BudgetReader, "_handed", classmethod(interrupted_after_handed))
    w = threading.Thread(target=lambda: _absorb(reader.pinned), name="W", daemon=True)
    w.start()
    assert entered.wait(10)
    threading.Timer(0.2, go.set).start()
    t0 = time.perf_counter()
    with pytest.raises(OwnerUnavailable, match="left without comparing"):
        reader.pinned().read(OwnerKind.EXPERIMENT, eid)
    assert time.perf_counter() - t0 < _WAIT_S                              # decided when W left, not on the timeout
    w.join(10)
    assert reader._in_flight == set()


def _absorb(fn):
    try:
        fn()
    except (_Interrupted, OwnerUnavailable):             # (round 14: an interrupted handing seals the reader)
        pass


# ---- B11-3: an interrupted leave never leaves the ticket in flight or the flag set ---------------------------------------------
def test_an_interrupted_leave_leaves_nothing_in_flight(monkeypatch):
    o = ax.owned("battery")
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))

    def interrupted(ticket, handed):
        raise _Interrupted()

    monkeypatch.setattr(reader, "_leave", interrupted)
    with pytest.raises(_Interrupted):
        reader.pinned()
    monkeypatch.undo()
    assert reader._in_flight == set() and not getattr(reader._in_follow, "active", False)
    t0 = time.perf_counter()
    assert reader.pinned().read(OwnerKind.EXPERIMENT, next(iter(o.experiments))) is not None
    assert time.perf_counter() - t0 < _WAIT_S


# ---- K11-F2: a served experiment record is never the cached one ----------------------------------------------------------------
def test_editing_a_served_experiment_record_changes_nothing_later_verifications_serve():
    import json

    from engcore.mind.world.owners import rederive
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    first = reader.read(OwnerKind.EXPERIMENT, eid)
    first.payload["experiment"]["metadata"]["edited"] = True               # a consumer edits what it was served
    first.payload["accounting"]["observations"] = -1
    again = reader.read(OwnerKind.EXPERIMENT, eid)                         # unchanged content: the cached text
    assert "edited" not in again.payload["experiment"]["metadata"] and again.payload["accounting"]["observations"] >= 0
    assert rederive(OwnerKind.EXPERIMENT, again.owner_id, eid, json.loads(json.dumps(again.payload))) == \
        (again.revision, again.record_digest)


# ---- R11-D-F4: revisions are compared as numerals ------------------------------------------------------------------------------
@pytest.mark.parametrize("stated,in_force,lower", [("9", "10", True), ("10", "9", False), ("009", "10", True),
                                                   ("010", "9", False), ("10", "10", False), ("0", "00", False),
                                                   ("99", "100", True), ("1²", "2", False), ("", "1", False)])
def test_a_stated_revision_is_compared_as_a_numeral(stated, in_force, lower):
    assert _lower_revision(stated, in_force) is lower


def test_a_multi_digit_older_revision_is_stale():
    import dataclasses

    from benchmarks.mind_gen2_world_v1 import fixtures as b
    base = b.battery_world()
    w2 = b.world(base.world_id, base.variables, entities=base.entities, constraints=base.constraints,
                 channels=base.channels, applicability=base.applicability,
                 providers=base.providers + (b.provider("sim.secret", "1.0"),), budget=base.budget,
                 references=base.references, actions=base.actions)
    o2 = ax.owned("battery", w2)
    payload = o2.world.to_dict()
    payload["declaration"]["revision"] = "9"                               # the world states revision 9
    world = ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})
    in_force = dataclasses.replace(o2.declaration, revision=10,
                                   providers=tuple(p for p in o2.declaration.providers if p != "sim.secret"))
    decl = DeclarationReader.following(lambda: [in_force])
    readers = tuple(decl if type(r) is DeclarationReader else r for r in o2.authorities(refresh=True).readers)
    r = admit(FeasibleActionSpace.build(world), o2.propose("simulate_pulse", *SIM, world=world), Authorities.of(*readers))
    assert {c.status.value for c in r.verification.checks if c.record_id == "sim.secret"} == {"stale"}
