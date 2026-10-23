"""GEN2-BR1.1 round-12 leads: one control per confirmed lead (benchmarks/mind_gen2_authority_v1/README.md section 9).

Review round 12 was interrupted with no result; its two started lenses left probes
(``docs/work/evidence/br11_cloud_2026_10_23/round12_interrupted/``) that were reproduced locally at ``d40aff44``.  These
pin the fixes: a read-back failure is classified without running any of the failure's own code that could raise out of
the classification (R12-1); two handed entries spelling one id refuse that id for good, and the strict constructor
refuses them (R12-2); a handed state that is not read back still observes how far its account had moved (its owner's
history length), so a return behind it is refused while behind, whatever its failures looked like (R12-3); the
fresh-thread retry is waited for at most ``WAIT_S`` (R12-4), runs the same classified attempts as the calling thread,
and recognizes a recursion failure an owner wrapped (R12-5); and the controls the surviving mutants lacked (R12-6)."""

from __future__ import annotations
from tests.mind.publication_support import following

import itertools
import sys
import threading
import time

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.base import WorldRefused
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
_WAIT_S = getattr(BudgetReader, "WAIT_S", 1.0)


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _desk(o, accounts):
    reader = following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    return reader, authorities, r


def _refused(gateway, admitted):
    try:
        gateway.dispatch(admitted)
        return False
    except DispatchRefused:
        return True


def _ledger_spend_then_restore(detail, verifications=2):
    """Dispatch once (the executor settles a charge carrying ``detail`` on the bound solver ledger), let
    ``verifications`` verifications be handed the spent state, restore the pre-run ledger by replacing it, and
    re-dispatch: (refused?, executor calls, the reader)."""
    o = ax.owned("battery")
    lid = _solver(o)
    reader, authorities, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)))
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                              family=ActionFamily.EXPLORE, realized=1.0, detail=detail)

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    for _ in range(verifications):
        with pytest.raises(OwnerUnavailable):
            reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = before
    return _refused(gateway, r.admitted), len(calls), reader


def _depth():
    n, frame = 0, sys._getframe()
    while frame is not None:
        n, frame = n + 1, frame.f_back
    return n


# ---- R12-1: a failure whose message cannot be rendered is classified, never raised out of a verification ------------------------
class _Unprintable(Exception):
    def __str__(self):
        raise ValueError("message not available")


class _UnprintableDetail:                                                  # str(detail) raises an unrenderable exception
    def __str__(self):
        raise _Unprintable()


class _Arg:
    def __str__(self):
        raise ValueError("argument not printable")


class _UnprintableRuntimeError:                                            # an exact RuntimeError whose argument cannot render
    def __str__(self):
        raise RuntimeError(_Arg())


@pytest.mark.parametrize("detail", [_UnprintableDetail(), _UnprintableRuntimeError()], ids=["exception", "argument"])
def test_a_spend_whose_failure_cannot_be_rendered_is_refused_and_never_redispatched(detail):
    refused, calls, reader = _ledger_spend_then_restore(detail)
    assert refused and calls == 1


@pytest.mark.parametrize("detail", [_UnprintableDetail(), _UnprintableRuntimeError()], ids=["exception", "argument"])
def test_an_unrenderable_account_no_world_reads_refuses_no_admission(detail):
    o = ax.owned("battery")
    side = BudgetLedger(total_budget=10.0)
    side.settle(charge_id="c", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0, detail=detail)
    reader = following(lambda: ({**o.ledgers, "side.ledger": side}, dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    assert admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities).feasible


# ---- R12-2: two handed entries spelling one id refuse that id; the strict constructor refuses them -------------------------------
class _Tag(str):                                                           # equal only to itself: two keys, one spelling
    __hash__ = object.__hash__

    def __eq__(self, other):
        return self is other


@pytest.mark.parametrize("stale_last", [True, False])
def test_two_entries_spelling_one_id_never_hide_a_spend(stale_last):
    o = ax.owned("battery")
    lid = _solver(o)
    state = {"spent": False}
    stale = BudgetLedger.from_dict(o.ledgers[lid].to_dict())

    def accounts():
        ledgers = {_Tag(k): v for k, v in o.ledgers.items()}
        if state["spent"]:                                                 # a stale cache entry under a second key
            items = list(ledgers.items()) + [(_Tag(lid), stale)]
            ledgers = dict(items if stale_last else items[::-1])
        return ledgers, dict(o.experiments)

    reader, authorities, r = _desk(o, accounts)
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=1.0)
        state["spent"] = True

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    with pytest.raises(OwnerUnavailable, match="spell one id"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = stale                                                 # restore, handed under one key again
    state["spent"] = False
    assert _refused(gateway, r.admitted) and len(calls) == 1


def test_the_strict_constructor_refuses_two_ids_spelling_one():
    with pytest.raises(WorldRefused, match="spell one id"):
        BudgetReader({_Tag("L"): BudgetLedger(total_budget=10.0), _Tag("L"): BudgetLedger(total_budget=99.0)}, {})
    with pytest.raises(WorldRefused, match="spell one id"):
        BudgetReader({}, {_Tag("E"): ax.experiment("E", 10, 1), _Tag("E"): ax.experiment("E", 20, 1)})


def test_a_str_subclass_id_is_read_under_its_spelling_and_runs_no_code():
    o = ax.owned("battery")
    lid = _solver(o)
    ran = []

    class Named(str):                                                      # its own rendering names another account
        def __str__(self):
            ran.append("__str__")
            return "another.ledger"

    reader = following(lambda: ({Named(k): v for k, v in o.ledgers.items()}, dict(o.experiments)))
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None
    assert reader.read(OwnerKind.BUDGET_LEDGER, "another.ledger") is None and ran == []
    strict = BudgetReader({Named(lid): o.ledgers[lid]}, {})
    assert strict.read(OwnerKind.BUDGET_LEDGER, lid) is not None and ran == []


# ---- R12-3: a handed state not read back observes its account's length: a return behind it is refused ---------------------------
class _SelfFillingNote:                                                    # the interpreter's own mutation error, every time
    def __str__(self):
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


class _VaryingNote:                                                        # one failure, a fresh message at every attempt
    counter = itertools.count()

    def __str__(self):
        raise ConnectionError(f"note store unreachable (request {next(self.counter)})")


@pytest.mark.parametrize("detail", [_SelfFillingNote(), _VaryingNote()], ids=["mutation_text", "varying_message"])
def test_a_spend_whose_read_back_always_looks_moving_is_never_redispatched(detail):
    refused, calls, reader = _ledger_spend_then_restore(detail, verifications=3)
    assert refused and calls == 1


def _swallow(fn):
    try:
        fn()
    except OwnerUnavailable:
        pass


def test_a_state_not_read_back_while_a_rollback_waits_refuses_the_rollback():
    o = ax.owned("battery")
    lid = _solver(o)
    p_handed, p_go = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "P":
            p_handed.set()
            p_go.wait(10)
        return mapping

    reader, authorities, r = _desk(o, accounts)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=1.0, detail=_SelfFillingNote())

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    p = threading.Thread(target=lambda: _swallow(reader.pinned), name="P", daemon=True)
    p.start()
    assert p_handed.wait(10)                                               # P holds a spend no read-back writes down
    o.ledgers[lid] = before                                                # the execution side restores
    threading.Timer(0.2, p_go.set).start()                                 # P compares while D waits for it
    assert _refused(gateway, r.admitted) and len(calls) == 1
    p.join(10)


def test_a_state_not_read_back_whose_length_cannot_be_read_refuses_its_account_for_good(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]

    class Evaluations(list):
        pass

    object.__setattr__(live, "_evaluations", Evaluations(live._evaluations))
    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))

    def moving():
        raise RuntimeError("dictionary changed size during iteration")

    monkeypatch.setattr(live, "to_dict", moving)
    with pytest.raises(OwnerUnavailable, match="from then on"):
        reader.read(OwnerKind.EXPERIMENT, eid)


# ---- R12-6 (mutants differ_not_moving, why_only): failures that differ only in their text are a move, refused once ---------------
def test_three_read_backs_torn_by_honest_records_refuse_once_then_read():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    real = live.to_dict
    calls = {"n": 0}

    def torn():                                                            # a record lands mid-serialization, three times
        out = real()
        calls["n"] += 1
        if calls["n"] <= 3:
            live.record(ScientificEvaluation(f"camp.{calls['n']}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                             detail="x"))
            out["accounting"] = real()["accounting"]                       # one message, a different text each time
        return out

    object.__setattr__(live, "to_dict", torn)
    with pytest.raises(OwnerUnavailable, match="moved while it was serialized"):
        reader.read(OwnerKind.EXPERIMENT, eid)
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None and reader._diverged == {}


# ---- R12-4: the fresh-thread retry is waited for at most WAIT_S ---------------------------------------------------------------------
def test_a_fresh_thread_read_back_blocked_by_the_verifiers_own_lock_is_refused_within_the_wait():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    lock = threading.RLock()                                               # the execution side's store lock (re-entrant)

    def to_dict():
        with lock:
            if threading.current_thread().name == "V":
                raise RecursionError("maximum recursion depth exceeded")  # the verifying caller's deep stack
            return real()

    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    object.__setattr__(live, "to_dict", to_dict)
    out = {}

    def verifier():
        with lock:                                                         # verifies while holding the store lock
            t0 = time.perf_counter()
            try:
                reader.read(OwnerKind.EXPERIMENT, eid)
                out["v"] = "served"
            except OwnerUnavailable as exc:
                out["v"] = str(exc)
            out["s"] = time.perf_counter() - t0

    t = threading.Thread(target=verifier, name="V", daemon=True)
    t.start()
    t.join(10 * _WAIT_S)
    assert not t.is_alive(), "the verification never returned"
    assert out["s"] < 3 * _WAIT_S and "from then on" not in out["v"] and out["v"] != "served"
    assert reader._in_flight == set()
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None and reader._diverged == {}   # later, at normal depth


# ---- R12-5: the fresh-thread retry is classified like the calling thread's, and sees a wrapped recursion failure ------------------
def test_a_torn_fresh_thread_read_back_is_retried_not_refused_for_good():
    o = ax.owned("battery")
    lid = _solver(o)
    live = o.ledgers[lid]
    real = live.to_dict
    shallow = _depth() + 40
    torn = {"n": 0}

    def to_dict():
        if threading.current_thread().name != "budget-read-back" and _depth() > shallow:
            raise RecursionError("maximum recursion depth exceeded")
        out = real()
        if threading.current_thread().name == "budget-read-back" and torn["n"] == 0:
            torn["n"] += 1                                                 # the fresh thread reads across a top-up once
            out["reserved_validation_budget"] = out["total_budget"] + 1.0
        return out

    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    object.__setattr__(live, "to_dict", to_dict)

    def deep(k):
        return deep(k - 1) if k else reader.read(OwnerKind.BUDGET_LEDGER, lid)

    assert deep(60) is not None and torn["n"] == 1 and reader._diverged == {}


def test_a_recursion_failure_an_owner_wraps_is_retried_on_a_fresh_thread():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    shallow = _depth() + 40

    def to_dict():
        if _depth() > shallow:
            try:
                raise RecursionError("maximum recursion depth exceeded")
            except RecursionError as exc:                                  # as the unit owner wraps it
                raise ValueError(f"unparsable unit 'megafarad': {exc}") from exc
        return real()

    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    object.__setattr__(live, "to_dict", to_dict)

    def deep(k):
        return deep(k - 1) if k else reader.read(OwnerKind.EXPERIMENT, eid)

    assert deep(60) is not None and reader._diverged == {}


# ---- R12-6 (mutant fresh_thread_no_flag): a read-through from the fresh thread is refused at once ---------------------------------
def test_a_read_through_from_the_fresh_thread_read_back_is_refused_at_once():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    shallow = _depth() + 40
    nested: list[str] = []
    entered: list[int] = []

    def to_dict():
        if threading.current_thread().name != "budget-read-back" and _depth() > shallow:
            raise RecursionError("maximum recursion depth exceeded")
        if threading.current_thread().name == "budget-read-back" and not entered:
            entered.append(1)
            try:
                reader.read(OwnerKind.BUDGET_LEDGER, _solver(o))           # the account's code reads through the reader
                nested.append("served")
            except OwnerUnavailable as exc:
                nested.append(str(exc))
        return real()

    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    object.__setattr__(live, "to_dict", to_dict)

    def deep(k):
        return deep(k - 1) if k else reader.read(OwnerKind.EXPERIMENT, eid)

    t0 = time.perf_counter()
    assert deep(60) is not None
    assert len(nested) == 1 and "read through" in nested[0] and time.perf_counter() - t0 < _WAIT_S


# ---- R12-6 (mutant alias_not_recorded2): an aliased spend is recorded, so its rollback is refused --------------------------------
def test_a_spend_handed_under_two_ids_is_recorded_and_its_rollback_never_redispatches():
    o = ax.owned("battery")
    lid = _solver(o)
    state = {"alias": False}

    def accounts():
        ledgers = dict(o.ledgers)
        if state["alias"]:
            ledgers["mirror.of.solver"] = ledgers[lid]
        return ledgers, dict(o.experiments)

    reader, authorities, r = _desk(o, accounts)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    calls = []

    def executor(authorization):
        calls.append(1)
        o.ledgers[lid].settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                              realized=1.0)
        state["alias"] = True

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    with pytest.raises(OwnerUnavailable, match="two ids"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = before
    state["alias"] = False
    assert _refused(gateway, r.admitted) and len(calls) == 1
