"""GEN2-BR1.1 review round 9: one control per fixed finding (benchmarks/mind_gen2_authority_v1/README.md).

Round 9 found 0 BLOCKER / 0 MAJOR and Q1-Q7 NO from every lens and the critic.  These pin its MINOR fixes: the
follower's read-back runs with no lock held and a verification decides on nothing while an earlier-started one is in
flight (no execution-side code under the lock, nothing waits, and a spend an earlier verification was handed is never
overtaken by a rollback); an experiment is read back only from plain JSON data; the read-back cache keeps the accounts
handed over now; an eager pin's error lasts the whole verification; the exact-level guard compares with the matched
level; and bind tests a fixed condition as every check executes it."""

from __future__ import annotations

import threading

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, Authorities, BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind,
    TemporalSemantics as TS, WorldRefused, admit,
)
from engcore.mind.world import feasibility as fz
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.domains import DiscreteLevels
from engcore.scientific import Quantity
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
P = RoleSource.PROTOCOL_METADATA


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _paused_accounts(o, name):
    """An accounts() that, on thread ``name``, hands over the mapping as it is now and then waits (inside accounts(),
    with no lock held) until it is told to return."""
    handed, resume = threading.Event(), threading.Event()

    def accounts():
        mapping = (dict(o.ledgers), dict(o.experiments))
        if threading.current_thread().name == name and not resume.is_set():
            handed.set()
            resume.wait(10)
        return mapping

    return accounts, handed, resume


# ---- R9-C-F4 / F9-4 / B8-m1: a spend an earlier verification was handed is never overtaken by a rollback ---------------------------
def test_a_rollback_read_while_an_earlier_verification_holds_the_spend_never_redispatches():
    o = ax.owned("battery")
    lid = _solver(o)
    accounts, handed, resume = _paused_accounts(o, "T2")
    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE, realized=2.0)
    o.ledgers[lid] = spent                                                 # the executor spends (object replaced)
    t2 = threading.Thread(target=lambda: reader.pinned(), name="T2", daemon=True)
    t2.start()
    assert handed.wait(10)                                                 # T2 was handed the spent ledger
    o.ledgers[lid] = before                                                # the execution side restores (replaces)
    with pytest.raises(DispatchRefused, match="OWNER_UNAVAILABLE"):        # T2 is in flight: nothing is decided
        gateway.dispatch(r.admitted)
    resume.set()
    t2.join(10)                                                            # T2 compares the spend
    with pytest.raises(DispatchRefused, match="OWNER_UNAVAILABLE"):        # the restore is now behind
        gateway.dispatch(r.admitted)
    assert len(calls) == 1


# ---- R9-D-F4: a concurrent older mapping is refused for that verification only -----------------------------------------------------
def test_an_older_mapping_compared_after_a_newer_one_is_refused_only_for_its_verification():
    o = ax.owned("battery")
    lid = _solver(o)
    accounts, handed, resume = _paused_accounts(o, "A")
    reader = BudgetReader.following(accounts)
    r0 = o.ledgers[lid].revision
    out = {}

    def verify_a():
        try:
            out["A"] = reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid).revision
        except OwnerUnavailable as exc:
            out["A"] = str(exc)

    a = threading.Thread(target=verify_a, name="A", daemon=True)
    a.start()
    assert handed.wait(10)                                                 # A holds the older mapping
    moved = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    moved.settle(charge_id="m1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=0.5)
    o.ledgers[lid] = moved
    with pytest.raises(OwnerUnavailable, match="still in flight"):         # B starts later: it decides on nothing,
        reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid)                 # but its observation is recorded
    resume.set()
    a.join(10)
    assert "behind" in out["A"]                                            # A's older mapping: refused for A only
    assert reader.read(OwnerKind.BUDGET_LEDGER, lid).revision == str(r0 + 1)   # nothing refused for good


# ---- B9-m1 / B9-m2 / R9-D-F1: an experiment is read back only from plain JSON data -------------------------------------------------
class _Hooked:
    """A metadata value whose code must never run while the follower reads accounts back."""

    def __deepcopy__(self, memo):
        raise AssertionError("an execution-side hook ran during the read-back")

    def __reduce__(self):
        raise AssertionError("an execution-side hook ran during the read-back")


@pytest.mark.parametrize("value", [_Hooked(), {1: "int key"}, {"nested": [_Hooked()]}])
def test_an_experiment_whose_data_is_not_plain_json_is_refused_without_running_its_code(value):
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    o.experiments[eid].metadata["note"] = value
    with pytest.raises(OwnerUnavailable, match="plain JSON"):
        BudgetReader(o.ledgers, o.experiments).read(OwnerKind.EXPERIMENT, eid)
    with pytest.raises(OwnerUnavailable, match="plain JSON"):
        BudgetReader.following(lambda: (o.ledgers, o.experiments)).read(OwnerKind.EXPERIMENT, eid)


def test_a_served_experiment_never_shares_objects_with_the_account_handed_over():
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    o.experiments[eid].metadata["runs"] = ["a"]
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    first = reader.read(OwnerKind.EXPERIMENT, eid)
    o.experiments[eid].metadata["runs"].append("b")                        # the live account moves in place
    assert first.payload["experiment"]["metadata"] == {"runs": ["a"]}
    later = reader.read(OwnerKind.EXPERIMENT, eid)
    assert later.payload["experiment"]["metadata"] == {"runs": ["a", "b"]} and later.record_digest != first.record_digest


# ---- B9-m3: the cache keeps the accounts handed over now --------------------------------------------------------------------------
def test_the_read_back_cache_keeps_only_the_accounts_handed_over_now():
    from engcore.scientific.experiments.experiment import ExperimentBudget, ScientificExperiment
    from engcore.scientific.ir.problem import ScientificProblem
    o = ax.owned("battery")
    state = {"i": 0}

    def accounts():
        eid = f"rotating.{state['i']}"
        return o.ledgers, {**o.experiments, eid: ScientificExperiment(eid, ScientificProblem("p"), ExperimentBudget(5))}

    reader = BudgetReader.following(accounts)
    for i in range(10):
        state["i"] = i
        reader.pinned()
    assert len(reader._readback) <= len(o.experiments) + 1                 # (private: the cache's size)


# ---- A9-F5: an eager pin's error lasts the whole verification ---------------------------------------------------------------------
def test_an_owner_whose_pin_fails_is_pinned_once_per_verification():
    calls = []

    class Flaky:
        kinds = frozenset({OwnerKind.SYSTEM_STATE})
        owner_id = "x"

        def pinned(self):
            calls.append(1)
            if len(calls) == 1:
                raise WorldRefused("first pin refused")
            return self

        def read(self, kind, record_id):
            return None

        def superseded(self, kind, record_id):
            return None

    memo = Authorities.of(Flaky()).memoized()
    for record_id in ("a", "b"):                                           # two records: no cached refusal of one
        with pytest.raises(WorldRefused, match="first pin refused"):
            memo.read(OwnerKind.SYSTEM_STATE, record_id)
    assert len(calls) == 1


# ---- F9-5: the exact-level guard compares with the MATCHED level -----------------------------------------------------------------
def test_a_value_executed_at_another_declared_level_than_its_own_is_refused(monkeypatch):
    lv = DiscreteLevels("A", (Quantity(1.0, "A"), Quantity(2.0, "A")))
    w = b.world("synthetic.two_levels", (
        b.var("I", R.CONTROLLED_INPUT, "A", TS.CONSTANT_PER_RUN, domain=lv), b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE, controls=(b.ctrl("I", lv, P),),
                          expected_observables=("y",), estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="t"), references=(b.synthetic("t/1"),))
    spec = w.action("a")
    assert fz.level_problem(w, spec, "I", Quantity(1.0, "A"), Quantity(1.0, "A")) is None
    found = fz.level_problem(w, spec, "I", Quantity(1.0, "A"), Quantity(2.0, "A"))   # a declared level, not its own
    assert found is not None and found[0] == "LEVEL_NOT_DECLARED"


# ---- A9-F1: bind tests a fixed condition as every check executes it ---------------------------------------------------------------
def test_a_fixed_condition_every_check_would_refuse_is_refused_at_bind():
    lv = DiscreteLevels("m", (Quantity(5862.446126855, "m"),))
    with pytest.raises(WorldRefused, match="outside its declared domain"):
        b.world("synthetic.a902", (
            b.var("T", R.FIXED_PROTOCOL_CONDITION, "ft", TS.CONSTANT_PER_RUN, domain=lv),
            b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
            b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
            actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                              controls=(b.ctrl("mode", b.cats("mode", "a", "b"), P),),
                              fixed_conditions=(b.fixed("T", Quantity(19233.747135351055, "ft")),),
                              expected_observables=("y",), estimated_cost=b.cost(1, 0),
                              estimated_duration=b.q(10, "s")),),
            channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="a902"), references=(b.synthetic("a902/1"),))
