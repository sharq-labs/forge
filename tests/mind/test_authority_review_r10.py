"""GEN2-BR1.1 review round 10: one control per fixed finding (benchmarks/mind_gen2_authority_v1/README.md).

Round 10 found that round 9's plain-data rule hid ordinary spends the owner reads back (R10-C-F1 / R10-D-F1 / K10-F2),
and that the ticket rule protected a handed spend only when its verification STARTED first (R10-C-F2 / F10-1 / A10-F1 /
E10-F1).  These pin the fixes: each account is read back by its owner from the text its owner writes it down as (no
other rule), a handed state its owner cannot write down refuses its account for good, a verification decides only once
every verification in flight when it compared has compared (it waits, bounded, holding no lock), each snapshot reads
back into a private cache (B10-1), account ids are exactly str (B10-4), a stated revision never makes admission raise
(B10-5), ledger records are detached (F10-5), and the read-back runs unlocked and under the same-thread flag (B10-7)."""

from __future__ import annotations

import enum
import threading
import time

import numpy as np
import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (
    Authorities, BudgetReader, DeclarationReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind,
    ScientificWorld, WorldRefused, admit,
)
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _desk(o, accounts):
    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is not None
    return reader, authorities, r


def _redispatch(gateway, admitted):
    try:
        gateway.dispatch(admitted)
        return "DISPATCHED"
    except DispatchRefused as exc:
        return f"refused: {exc}"


# ---- R10-C-F1 / K10-F2: a spend recorded with ordinary nested metadata is observed, so its rollback never re-dispatches -----------
@pytest.mark.parametrize("meta", [{}, {"seeds": [1, 2]}, {"run": {"host": "a"}}, {"x": np.float64(0.5)}])
def test_an_observation_with_nested_metadata_is_observed_and_its_rollback_never_redispatches(meta):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader, authorities, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)))
    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation(f"run.{len(calls)}", {}, status=EvaluationStatus.NOT_CONVERGED,
                                                       detail="observed", metadata=meta))

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    gateway.dispatch(r.admitted)
    assert reader.read(OwnerKind.EXPERIMENT, eid).revision == str(len(before.evaluations) + 1)   # the spend: observed
    o.experiments[eid] = before                                            # the execution side restores (replaces)
    assert _redispatch(gateway, r.admitted).startswith("refused") and len(calls) == 1


# ---- R10-D-F1 / c1007: a ledger spend in values its owner reads back (numpy, IntEnum, str-Enum) is observed -------------------------
class _It(enum.IntEnum):
    ONE = 1


class _Note(str, enum.Enum):
    RAN = "ran"


@pytest.mark.parametrize("kw", [{"iteration": np.int64(1)}, {"iteration": _It.ONE}, {"predicted": np.float64(1.5)},
                                {"detail": _Note.RAN}])
def test_a_ledger_spend_in_values_its_owner_reads_back_is_observed_and_its_rollback_never_redispatches(kw):
    o = ax.owned("battery")
    lid = _solver(o)
    reader, authorities, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)))
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    o.ledgers[lid].settle(**{"charge_id": "run-1", "action_id": "simulate_pulse", "iteration": 1,
                             "family": ActionFamily.EXPLORE, "realized": 2.0, **kw})
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(before.revision + 1)
    o.ledgers[lid] = before
    assert _redispatch(gateway, r.admitted).startswith("refused") and len(calls) == 1


# ---- the pre-existing class (scope skeptic v1): a handed state its owner cannot write down refuses its account for good -----------
@pytest.mark.parametrize("value", [{1, 2}, float("nan"), object()])
def test_a_handed_state_its_owner_cannot_write_down_refuses_the_account_for_good(value):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    reader, authorities, r = _desk(o, lambda: (dict(o.ledgers), dict(o.experiments)))
    calls = []

    def executor(authorization):
        calls.append(1)
        o.experiments[eid].record(ScientificEvaluation("run.1", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        o.experiments[eid].metadata["note"] = value                        # the spent state cannot be written down

    gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
    before = ScientificExperiment.from_dict(o.experiments[eid].to_dict())
    gateway.dispatch(r.admitted)
    with pytest.raises(OwnerUnavailable, match="refused by this reader from then on"):
        reader.read(OwnerKind.EXPERIMENT, eid)
    o.experiments[eid] = before                                            # a readable restore re-authorizes nothing
    assert _redispatch(gateway, r.admitted).startswith("refused") and len(calls) == 1


def test_a_self_containing_value_is_refused_at_once():
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    loop: list = []
    loop.append(loop)
    o.experiments[eid].metadata["loop"] = loop
    t0 = time.perf_counter()
    with pytest.raises(OwnerUnavailable, match="owner writes down"):
        BudgetReader.following(lambda: (o.ledgers, o.experiments)).read(OwnerKind.EXPERIMENT, eid)
    assert time.perf_counter() - t0 < 5.0


# ---- R10-C-F2 / F10-1 / A10-F1 / E10-F1: the verification handed the spend started SECOND ----------------------------------------
def test_a_rollback_read_by_an_earlier_started_verification_never_redispatches(monkeypatch):
    monkeypatch.setattr(BudgetReader, "WAIT_S", 0.2)
    o = ax.owned("battery")
    lid = _solver(o)
    d_entered, restored, t2_handed, t2_resume = (threading.Event() for _ in range(4))

    def accounts():
        name = threading.current_thread().name
        if name == "D":
            d_entered.set()
            restored.wait(10)                                              # D started first; answered after the restore
        mapping = (dict(o.ledgers), dict(o.experiments))
        if name == "T2":
            t2_handed.set()
            t2_resume.wait(10)                                             # T2 was handed the spend; returns later
        return mapping

    reader, authorities, r = _desk(o, accounts)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                          realized=2.0)
    out = {}
    d = threading.Thread(target=lambda: out.setdefault("D", _redispatch(gateway, r.admitted)), name="D", daemon=True)
    d.start()
    assert d_entered.wait(10)
    t2 = threading.Thread(target=lambda: reader.pinned(), name="T2", daemon=True)
    t2.start()
    assert t2_handed.wait(10)
    o.ledgers[lid] = before                                                # the execution side restores
    restored.set()
    d.join(10)
    t2_resume.set()
    t2.join(10)
    assert out["D"].startswith("refused") and len(calls) == 1
    assert _redispatch(gateway, r.admitted).startswith("refused") and len(calls) == 1


# ---- the wait: a compared verification decides on what the verifications in flight when it compared recorded --------------------
@pytest.mark.parametrize("spend", [False, True, "W fails"])
def test_a_compared_verification_decides_on_what_the_ones_in_flight_record(spend):
    o = ax.owned("battery")
    lid = _solver(o)
    handed, resume = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == "W":
            handed.set()
            resume.wait(10)
            if spend == "W fails":                                         # W leaves without comparing
                raise RuntimeError("the execution side's store went away")
        return mapping

    reader = BudgetReader.following(accounts)
    before = o.ledgers[lid]
    if spend is True:
        spent = BudgetLedger.from_dict(before.to_dict())
        spent.settle(charge_id="m1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=0.5)
        o.ledgers[lid] = spent
    def w_verify():
        try:
            reader.pinned()
        except OwnerUnavailable:
            pass

    w = threading.Thread(target=w_verify, name="W", daemon=True)
    w.start()
    assert handed.wait(10)                                                 # W holds the (spent or unchanged) ledger
    o.ledgers[lid] = before                                                # (a restore when W was handed a spend)
    threading.Timer(0.1, resume.set).start()                               # W compares while V waits for it
    t0 = time.perf_counter()
    if spend is True:
        with pytest.raises(OwnerUnavailable, match="behind"):              # V's state: behind what W recorded
            reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid)
    else:
        assert reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid) is not None   # nothing moved: V decides
    assert time.perf_counter() - t0 < BudgetReader.WAIT_S                  # decided once W left, not on the timeout
    w.join(10)


def test_concurrent_admissions_through_one_desk_are_decided_not_refused():
    """Round 10's first candidate (refuse while any other verification is in flight) refused 157 of 160 admissions in
    the reviewers' p10c load; the bounded wait decides them.  A refusal is allowed only as the wait's timeout."""
    o = ax.owned("battery")
    other = BudgetLedger(total_budget=100.0)                               # an account no world reads, moving on
    reader, authorities, r = _desk(o, lambda: ({**o.ledgers, "other.ledger": other}, dict(o.experiments)))
    outcomes, stop = [], threading.Event()

    def spender():
        i = 0
        while not stop.is_set():
            other.settle(charge_id=f"s{i}", action_id="x", iteration=i, family=ActionFamily.EXPLORE,
                                  realized=0.0)
            i += 1
            time.sleep(0.001)

    def verifier():
        for _ in range(15):
            a = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
            outcomes.append(a.status.value if a.feasible else a.codes())

    s = threading.Thread(target=spender, daemon=True)
    s.start()
    vs = [threading.Thread(target=verifier) for _ in range(6)]
    [v.start() for v in vs]
    [v.join(60) for v in vs]
    stop.set()
    feasible = sum(x == "FEASIBLE" for x in outcomes)
    assert len(outcomes) == 90 and feasible >= 60, outcomes


# ---- B10-1: each snapshot reads back into a private cache (no unlocked writer shares the dict the comparison prunes) -------------
def test_no_verification_crashes_on_another_ones_read_back():
    pool = [ax.experiment(f"camp{j}", 400, 3) for j in range(40)]
    n = {"i": 0}
    lock = threading.Lock()

    def accounts():
        with lock:
            n["i"] += 1
            i = n["i"]
        return {}, {f"c{(i + j) % 53}": pool[(i + j) % 40] for j in range(20)}   # a changing set of accounts

    reader = BudgetReader.following(accounts)
    errors = []

    def worker():
        for _ in range(60):
            try:
                reader.pinned()
            except OwnerUnavailable:
                pass
            except Exception as exc:  # noqa: BLE001 - what round 9's shared cache raised
                errors.append(repr(exc))

    ts = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    assert errors == [] and reader._in_flight == set()                     # (private: no ticket left behind)


def test_a_snapshot_reads_back_into_its_own_cache_until_it_compares(monkeypatch):
    o = ax.owned("battery")
    first = next(iter(o.experiments))
    last = ax.experiment("camp.last", 400, 3)
    reader = BudgetReader.following(lambda: (o.ledgers, {**o.experiments, "camp.last": last}))
    old = reader._readback[("experiment", first)][0]                       # (private: the cached content digest)
    o.experiments[first].record(ScientificEvaluation("moved", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    entered, resume = threading.Event(), threading.Event()
    real = last.to_dict

    def paused():
        entered.set()
        resume.wait(10)
        return real()

    monkeypatch.setattr(last, "to_dict", paused)                           # A pauses in its read-back, after `first`
    a = threading.Thread(target=lambda: reader.pinned(), daemon=True)
    a.start()
    assert entered.wait(10)
    assert reader._readback[("experiment", first)][0] == old               # A's new entry is not the follower's yet
    resume.set()
    a.join(10)
    assert reader._readback[("experiment", first)][0] != old               # adopted when A compared


# ---- B10-4: account ids are exactly str (no id's code runs under the follower's lock) --------------------------------------------
def test_an_account_id_that_is_not_exactly_a_str_is_refused():
    o = ax.owned("battery")
    held = []
    state = {"reader": None}

    class Key(str):
        def __hash__(self):
            if state["reader"] is not None:
                held.append(state["reader"]._lock.locked())
            return str.__hash__(self)

    with pytest.raises(WorldRefused, match="exactly a str"):
        BudgetReader({Key("x"): o.ledgers[_solver(o)]})
    mode = {"key": False}

    def accounts():
        ledgers = dict(o.ledgers)
        if mode["key"]:
            ledgers[Key("x")] = ledgers.pop(_solver(o))
        return ledgers, dict(o.experiments)

    reader = BudgetReader.following(accounts)
    state["reader"] = reader
    mode["key"] = True
    with pytest.raises(OwnerUnavailable, match="exactly a str"):
        reader.pinned()
    assert True not in held


# ---- B10-5 / R10-C-m3 / F10-2 / E10-F3 / R10-D-F3: a stated revision never makes admission raise --------------------------------
@pytest.mark.parametrize("revision", ["²", "1²", "٠", "1" * 5000])
def test_a_world_stating_any_declaration_revision_is_refused_not_raised(revision):
    o = ax.owned("battery")
    held = [o.declaration]
    decl = DeclarationReader.following(lambda: held)
    a = Authorities.of(*(decl if type(r) is DeclarationReader else r for r in o.authorities().readers))
    payload = o.world.to_dict()
    payload["declaration"]["revision"] = revision
    payload["declaration"]["record_digest"] = "1" * 64
    forged = ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})
    r = admit(FeasibleActionSpace.build(forged), o.propose("simulate_pulse", *SIM, world=forged), a)
    assert r.admitted is None and r.codes()


# ---- F10-5 / E10-F5: a pinned ledger record is detached from the account ---------------------------------------------------------
def test_a_pinned_ledger_record_does_not_move_with_the_account():
    o = ax.owned("battery")
    lid = _solver(o)
    o.ledgers[lid].settle(charge_id="d1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=0.1,
                          detail={"runs": ["r1"]})
    snapshot = BudgetReader.following(lambda: (o.ledgers, o.experiments)).pinned()
    first = snapshot.read(OwnerKind.BUDGET_LEDGER, lid)
    o.ledgers[lid].charges[-1].detail["runs"].append("edited after the pin")     # the live account moves in place
    again = snapshot.read(OwnerKind.BUDGET_LEDGER, lid)
    assert again.payload["ledger"]["charges"][-1]["detail"] == {"runs": ["r1"]}
    assert BudgetLedger.from_dict(again.payload["ledger"]).digest == first.record_digest


# ---- B10-7 / R10-D-F4 / F10-3: the read-back runs with no lock held, under the same-thread flag ----------------------------------
def test_the_read_back_runs_with_no_lock_held(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    state = {"reader": None}
    held = []

    def recorded():
        if state["reader"] is not None:
            held.append(state["reader"]._lock.locked())
        return real()

    monkeypatch.setattr(live, "to_dict", recorded)
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    state["reader"] = reader
    reader.pinned()
    assert held and True not in held


def test_a_read_through_from_the_read_back_is_refused_at_once(monkeypatch):
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict
    state = {"reader": None}
    ran = []

    def reads_through():
        ran.append(1)
        if state["reader"] is not None and len(ran) < 50:
            state["reader"].pinned()                                       # the execution side reads through
        return real()

    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    monkeypatch.setattr(live, "to_dict", reads_through)
    state["reader"] = reader
    with pytest.raises(OwnerUnavailable):
        reader.read(OwnerKind.EXPERIMENT, eid)
    assert len(ran) == 1                                                   # refused at once, never recursed


# ---- F10-3 / R10-D-F4 (B9-m1's case): the record served is the account handed over, not an object discarded since ------------------
def test_an_equal_content_replacement_serves_the_account_handed_over():
    import copy
    import json

    from engcore.mind.world import AdmissionRecord, replay_admission
    from engcore.mind.world.owners import rederive
    from engcore.sria.decision.replay import ReplayOutcome
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    o.experiments[eid].metadata["runs"] = {"list": ["a"]}
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    reader.read(OwnerKind.EXPERIMENT, eid)
    old = o.experiments[eid]
    o.experiments[eid] = ScientificExperiment.from_dict(copy.deepcopy(old.to_dict()))   # equal content, new object
    old.metadata["runs"]["list"].append("moved on the discarded object")
    served = reader.read(OwnerKind.EXPERIMENT, eid)
    assert served.payload["experiment"]["metadata"] == json.loads(json.dumps(o.experiments[eid].to_dict()))["metadata"]
    assert rederive(OwnerKind.EXPERIMENT, served.owner_id, eid, json.loads(json.dumps(served.payload))) == \
        (served.revision, served.record_digest)
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    record = json.loads(json.dumps(AdmissionRecord.of(r, authorities).to_dict()))
    assert replay_admission(record).outcome is ReplayOutcome.REPRODUCED


# ---- B10-7 (m2): an accounts() that raises leaves nothing in flight --------------------------------------------------------------
def test_a_failed_accounts_call_refuses_only_its_own_verification():
    o = ax.owned("battery")
    lid = _solver(o)
    state = {"down": False}

    def accounts():
        if state["down"]:
            raise ConnectionError("the ledger store is offline")
        return o.ledgers, o.experiments

    reader = BudgetReader.following(accounts)
    state["down"] = True
    with pytest.raises(OwnerUnavailable, match="could not state"):
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    state["down"] = False
    t0 = time.perf_counter()
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid) is not None
    assert time.perf_counter() - t0 < BudgetReader.WAIT_S                  # no ticket left behind to wait for


# ---- A10-F6: bind executes a fixed condition by the check's own rule -------------------------------------------------------------
def test_bind_executes_a_fixed_condition_as_the_check_does():
    from benchmarks.mind_gen2_world_v1 import fixtures as b
    from engcore.mind.repsem.roles import RoleSource, VariableRole as R
    from engcore.mind.world import ActionMode, TemporalSemantics as TS
    from engcore.mind.world import actions as act
    from engcore.mind.world import feasibility as fz
    from engcore.mind.world.base import value_payload
    from engcore.mind.world.domains import DiscreteLevels
    from engcore.scientific import Quantity
    lv = DiscreteLevels("K", (Quantity(308.15, "K"), Quantity(308.16, "K"), Quantity(310.15, "K")))
    w = b.world("synthetic.bind_vs_check", (
        b.var("T", R.FIXED_PROTOCOL_CONDITION, "degC", TS.CONSTANT_PER_RUN, domain=lv),
        b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("mode", b.cats("mode", "a", "b"), RoleSource.PROTOCOL_METADATA),),
                          fixed_conditions=(b.fixed("T", Quantity(35.0, "degC")),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="bvc"), references=(b.synthetic("bvc/1"),))
    spec, var = w.action("a"), w.variable("T")
    spellings = [Quantity(m, u) for base_, u in ((308.15, "K"), (35.0, "degC"), (95.0, "degF"), (310.15, "K"),
                                                 (37.0, "degC"), (98.6, "degF"), (35.01, "degC"), (308.155, "K"))
                 for m in (np.nextafter(base_, -np.inf), base_, np.nextafter(base_, np.inf), base_ * (1 + 1e-12))]
    for v in spellings:
        assert value_payload(act._fixed_as_executed(var.domain, v, var.unit)) == \
            value_payload(fz.as_executed(w, spec, "T", v)), v
