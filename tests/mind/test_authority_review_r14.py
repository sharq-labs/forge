"""GEN2-BR1.1 review round 14: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md section 9).

Round 14 reviewed ``1c9fdd84`` (the round-13 fix) and found that a handed state not read back and SHORTER than the
history observed was never recorded, so a later return to the observed checkpoint was accepted and the executed action
dispatched again (R14-A-F1 = R14-C-F1 = D14-F1 = F14-F1 = E14-F1, MAJOR, both skeptics each), and that an honest
non-dict mapping handed at a verification left its state unobserved, so the same authorization was dispatched again
after a restore (CRIT14-1, MAJOR).  These pin the fixes and assert OUTCOMES (CRIT14-2): every state not read back is
recorded as its entry objects whatever its length, a read state is checked against them both just before and just after
its read-back, a handing that is not a pair of dicts makes the reader refuse every account from then on, only a
``KeyboardInterrupt`` is an interrupt, and an unread state whose entry objects are those of a state read back (its
content observed) records nothing, so an honest unchanged checkpoint restore after it is read."""

from __future__ import annotations
from tests.mind.publication_support import following

import threading
import types

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _desk(o, accounts, executor):
    reader = following(accounts)
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


def _readmitted(o, authorities, gateway):
    """Whether a world projected from the owners now admits and dispatches the action again (as a Mind would)."""
    try:
        world = project_world(o.declaration, authorities)
    except OwnerUnavailable:
        return False
    result = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    return result.admitted is not None and not _refused(gateway, result.admitted)


class _SelfFillingNote:                                                    # the interpreter's mutation error, every time
    def __str__(self):
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


def _settle(ledger, charge_id, detail="observed"):
    ledger.settle(charge_id=charge_id, action_id="simulate_pulse" if charge_id.startswith("run") else "other",
                  iteration=1, family=ActionFamily.EXPLORE, realized=0.5, detail=detail)


# ---- R14-A-F1 = R14-C-F1 = D14-F1 = F14-F1 = E14-F1 (MAJOR): a shorter state not read back is recorded ---------------------------
def test_a_shorter_spend_not_read_back_never_lets_the_observed_checkpoint_redispatch():
    o = ax.owned("battery")
    lid = _solver(o)
    early = BudgetLedger.from_dict(o.ledgers[lid].to_dict())               # an earlier checkpoint
    calls = []

    def executor(authorization):                                           # the run lands on a restored earlier
        calls.append(1)                                                    # checkpoint (not read back)
        o.ledgers[lid] = BudgetLedger.from_dict(early.to_dict())
        _settle(o.ledgers[lid], f"run.{len(calls)}", _SelfFillingNote())

    reader, authorities, gateway, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    for i in (1, 2):                                                       # two other charges, observed
        _settle(o.ledgers[lid], f"other.{i}")
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None
    observed = BudgetLedger.from_dict(o.ledgers[lid].to_dict())            # the observed checkpoint
    world = project_world(o.declaration, authorities)
    admitted = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world)).admitted
    gateway.dispatch(admitted)                                             # shorter than observed, never read back
    with pytest.raises(OwnerUnavailable):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = observed                                              # restore the observed checkpoint
    assert _readmitted(o, authorities, gateway) is False and len(calls) == 1
    assert _refused(gateway, admitted) and len(calls) == 1


def test_a_shorter_state_not_read_back_that_compares_last_still_refuses_a_waiting_longer_one():
    o = ax.owned("battery")
    lid = _solver(o)
    v1_handed, v1_go = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "V1":
            v1_handed.set()
            v1_go.wait(10)
        return mapping

    calls = []

    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}", _SelfFillingNote())   # not read back

    reader, authorities, gateway, r = _desk(o, accounts, executor)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    v1 = threading.Thread(target=lambda: _swallow(reader.pinned), name="V1", daemon=True)
    v1.start()
    assert v1_handed.wait(10)                                              # V1 holds the spend (shorter, unread)
    o.ledgers[lid] = before                                                # restore, then two other charges: longer
    for i in (1, 2):
        _settle(o.ledgers[lid], f"other.{i}")
    threading.Timer(0.2, v1_go.set).start()                                # V1 compares while V2 waits for it
    assert _readmitted(o, authorities, gateway) is False and len(calls) == 1
    v1.join(10)
    assert _readmitted(o, authorities, gateway) is False and len(calls) == 1


# ---- R14-C-F2 / F14-F2: a read state is checked against unread entries just before AND just after its read-back ------------------
def test_an_in_place_rollback_during_its_own_read_back_is_not_accepted_against_an_unread_state():
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []

    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}", _SelfFillingNote())

    reader, authorities, gateway, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)), executor)
    live = o.ledgers[lid]
    earlier = live.charges
    gateway.dispatch(r.admitted)
    with pytest.raises(OwnerUnavailable):                                  # the spend, not read back
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    real = type(live).to_dict

    def rolled_back(self):                                                 # rolls the ledger back in place while
        object.__setattr__(self, "charges", earlier)                       # its own read-back runs
        return real(self)

    object.__setattr__(live, "to_dict", types.MethodType(rolled_back, live))
    assert _refused(gateway, r.admitted) and len(calls) == 1


# ---- CRIT14-1 (MAJOR): a handing that is not a pair of dicts makes the reader refuse every account from then on -----------------
def test_a_spend_handed_in_a_mapping_that_is_not_a_dict_is_never_redispatched():
    o = ax.owned("battery")
    lid = _solver(o)
    state = {"proxy": False}

    def accounts():
        ledgers = dict(o.ledgers)
        return (types.MappingProxyType(ledgers) if state["proxy"] else ledgers), dict(o.experiments)

    calls = []

    def executor(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
        state["proxy"] = True

    reader, authorities, gateway, r = _desk(o, accounts, executor)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    with pytest.raises(OwnerUnavailable, match="refuses every account from then on"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid] = before                                                # restore; handed as a dict again
    state["proxy"] = False
    assert _refused(gateway, r.admitted) and len(calls) == 1
    assert _readmitted(o, authorities, gateway) is False and len(calls) == 1


# ---- R14-C-F3 / E14-F2: only a KeyboardInterrupt is an interrupt -------------------------------------------------------------------
class _RaisesOnStr:
    def __init__(self, exc_type):
        self.exc_type = exc_type

    def __str__(self):
        raise self.exc_type("from the account's content")


@pytest.mark.parametrize("exc_type", [SystemExit, GeneratorExit])
def test_content_raising_system_exit_or_generator_exit_is_a_failure_not_an_interrupt(exc_type):
    o = ax.owned("battery")
    side = BudgetLedger(total_budget=10.0)
    side.settle(charge_id="c", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0,
                detail=_RaisesOnStr(exc_type))
    reader = following(lambda: ({**o.ledgers, "side.ledger": side}, dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    assert admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities).feasible
    with pytest.raises(OwnerUnavailable, match="from then on"):
        reader.read(OwnerKind.BUDGET_LEDGER, "side.ledger")


# ---- R14-A-F2 / D14-F2 / F14-F3 / R14-C-F4: an unread state with no unseen entry records nothing ----------------------------------
def test_an_unread_state_holding_only_observed_entries_lets_an_unchanged_checkpoint_restore_be_read():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    live.record(ScientificEvaluation("camp.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None              # read back: its entries observed
    real = live.to_dict

    def moving():
        raise RuntimeError("dictionary changed size during iteration")

    object.__setattr__(live, "to_dict", moving)
    with pytest.raises(OwnerUnavailable, match="moved while it was serialized"):
        reader.read(OwnerKind.EXPERIMENT, eid)                             # the same entries, not read back
    o.experiments[eid] = ScientificExperiment.from_dict(real())            # the campaign's checkpoint resume
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None and reader._diverged == {}


def test_an_unread_state_with_a_new_entry_still_refuses_an_object_replacing_restore():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    before = ScientificExperiment.from_dict(live.to_dict())
    real = live.to_dict

    def moving():
        raise RuntimeError("dictionary changed size during iteration")

    object.__setattr__(live, "to_dict", moving)
    live.record(ScientificEvaluation("camp.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    with pytest.raises(OwnerUnavailable):                                  # a new entry, never read back
        reader.read(OwnerKind.EXPERIMENT, eid)
    o.experiments[eid] = before
    # R15 can now read the retained entry history through its owner's rule.
    # The restored account is therefore known to be behind, and still refused.
    with pytest.raises(OwnerUnavailable, match="behind"):
        reader.read(OwnerKind.EXPERIMENT, eid)
    assert reader._seen[("experiment", eid)]
    assert real is not None


def test_an_unread_state_that_moved_on_in_place_is_cleared_and_an_unchanged_restore_is_read():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader = following(lambda: (dict(o.ledgers), dict(o.experiments)))
    live = o.experiments[eid]
    real = live.to_dict
    state = {"moving": True}

    def mutating():
        if state["moving"]:
            raise RuntimeError("dictionary changed size during iteration")
        return real()

    object.__setattr__(live, "to_dict", mutating)
    live.record(ScientificEvaluation("camp.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    with pytest.raises(OwnerUnavailable):                                  # a new entry, not read back: recorded
        reader.read(OwnerKind.EXPERIMENT, eid)
    live.record(ScientificEvaluation("camp.2", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    state["moving"] = False
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None              # moved on in place: read, record cleared
    o.experiments[eid] = ScientificExperiment.from_dict(real())             # then a checkpoint restore of that content
    assert reader.read(OwnerKind.EXPERIMENT, eid) is not None and reader._diverged == {}


def _swallow(fn):
    try:
        fn()
    except OwnerUnavailable:
        pass
