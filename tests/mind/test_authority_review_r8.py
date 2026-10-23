"""GEN2-BR1.1 review round 8: one control per finding (benchmarks/mind_gen2_authority_v1/README.md).

Round 8 found no BLOCKER or MAJOR from lenses A and B; these pin the MINOR fixes: the follower's read-back and its
comparison are one locked step again (a spend a verification read is observed before a rollback can be read; the
execution side's accounts() is still called with no lock held), the experiment read-back cache is one entry per
account, a torn experiment serialization is refused, an eager pin's refusal of any kind waits for a read of that owner,
the declaration modes that read no account or provider, and the level predicate (a fixed condition's branch, the
refusal's stated reason, subnormal and signed-zero spellings)."""

from __future__ import annotations

import threading

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, Authorities, BudgetReader, DeclarationReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace,
    OwnerKind, TemporalSemantics as TS, WorldRefused, admit,
)
from engcore.mind.world import admission as admission_mod
from engcore.mind.world import feasibility as fz
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.domains import DiscreteLevels
from engcore.scientific import Quantity
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
POOL = ("pool_query", {"I_A": Quantity(1, "A"), "t_on_s": Quantity(60, "s")})
P = RoleSource.PROTOCOL_METADATA


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


def _followed(o):
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    return reader, authorities


# ---- B8-m1: what a verification read is compared before a later read ------------------------------------------------------------
def test_a_spend_one_verification_read_is_observed_before_a_rollback_can_be_read(monkeypatch):
    """Verification T2 reads the spent ledger back and is paused before it compares; the execution side rolls the
    ledger back; a dispatch of the executed action then reads the rollback.  The dispatch waits for T2's comparison
    (one locked step), sees the rollback as behind, and is refused: the executor runs once."""
    o = ax.owned("battery")
    lid = _solver(o)
    reader, authorities = _followed(o)
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                          realized=2.0)                                     # the executor spends
    read, resume = threading.Event(), threading.Event()
    real = BudgetReader._read_back

    def paused(self):
        out = real(self)
        if threading.current_thread().name == "T2":
            read.set()
            resume.wait(10)                                                # T2 read the spend; not compared yet
        return out

    monkeypatch.setattr(BudgetReader, "_read_back", paused)
    outcome = {}
    t2 = threading.Thread(target=lambda: reader.pinned(), name="T2", daemon=True)
    t2.start()
    assert read.wait(10)
    o.ledgers[lid] = before                                                # the execution side rolls back

    def redispatch():
        try:
            gateway.dispatch(r.admitted)
            outcome["T1"] = "DISPATCHED"
        except DispatchRefused as exc:
            outcome["T1"] = str(exc)

    t1 = threading.Thread(target=redispatch, name="T1", daemon=True)
    t1.start()
    t1.join(0.5)
    resume.set()
    t2.join(10)
    t1.join(10)
    assert not t1.is_alive() and "OWNER_UNAVAILABLE" in outcome["T1"] and len(calls) == 1


def test_the_execution_side_is_never_called_under_the_followers_lock():
    o = ax.owned("battery")
    held = []
    reader = None

    def accounts():
        if reader is not None:
            held.append(reader._lock.locked())
        return o.ledgers, o.experiments

    reader = BudgetReader.following(accounts)
    reader.pinned()
    assert held == [False]


# ---- B8-m3: one cache entry per account ---------------------------------------------------------------------------------------------
def test_the_experiment_read_back_cache_keeps_one_entry_per_account():
    from engcore.scientific.experiments import EvaluationStatus, ScientificEvaluation
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    for i in range(20):
        o.experiments[eid].record(ScientificEvaluation(f"c{i}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        assert reader.read(OwnerKind.EXPERIMENT, eid) is not None
    assert len(reader._readback) <= len(o.experiments)                     # (private: the cache's size)


# ---- B8-m4: an experiment serialized while it moved is refused ----------------------------------------------------------------------
def test_an_experiment_whose_serialized_accounting_is_not_its_evaluations_is_refused(monkeypatch):
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    live = o.experiments[eid]
    real = live.to_dict

    def torn():                                    # the live object's serialization only (its read-back is honest)
        out = real()
        out["accounting"] = {**out["accounting"], "observations": out["accounting"]["observations"] + 1}
        return out

    monkeypatch.setattr(live, "to_dict", torn)
    with pytest.raises(OwnerUnavailable, match="serialized while it moved"):
        BudgetReader(o.ledgers, o.experiments).read(OwnerKind.EXPERIMENT, eid)


# ---- B8-m5: an eager pin's refusal of any kind waits for a read of that owner ------------------------------------------------------
def test_a_pin_refused_by_an_owner_the_world_does_not_read_refuses_nothing():
    class Grumpy:
        kinds = frozenset({OwnerKind.SYSTEM_STATE})
        owner_id = "x"

        def pinned(self):
            raise WorldRefused("this reader refuses to pin")

        def read(self, kind, record_id):
            return None

        def superseded(self, kind, record_id):
            return None

    p = ax.gen1_pool()
    world = p.world
    r = admit(FeasibleActionSpace.build(world), p.propose(*POOL, world=world),
              Authorities.of(Grumpy(), *p.authorities().readers))
    assert r.feasible
    memo = Authorities.of(Grumpy(), *p.authorities().readers).memoized()
    assert memo.served()["unavailable"] == []
    with pytest.raises(WorldRefused, match="refuses to pin"):              # raised, unchanged, to a read
        memo.read(OwnerKind.SYSTEM_STATE, "anything")


# ---- B8-m6: every declaration mode that names no account or provider reads none ----------------------------------------------------
@pytest.mark.parametrize("mode", ["in_force", "not_in_force", "none", "unavailable"])
def test_no_account_or_provider_outside_the_declaration_in_force_is_read(monkeypatch, mode):
    from engcore.mind.world import ScientificWorld
    from engcore.providers.catalog import ProviderRegistry
    base = b.battery_world()
    w2 = b.world(base.world_id, base.variables, entities=base.entities, constraints=base.constraints,
                 channels=base.channels, applicability=base.applicability,
                 providers=base.providers + (b.provider("sim.secret", "1.0"),), budget=base.budget,
                 references=base.references, actions=base.actions)
    o2 = ax.owned("battery", w2)
    world = o2.world
    in_force = ax.owned("battery").declaration
    if mode == "not_in_force":
        payload = world.to_dict()
        payload["declaration"]["record_id"] = "unknown.declaration"
        world = ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})
    elif mode == "none":
        payload = world.to_dict()
        payload["declaration"] = None
        world = ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})
    held = {"set": [in_force]}
    decl = DeclarationReader.following(lambda: held["set"])
    readers = tuple(decl if type(r) is DeclarationReader else r for r in o2.authorities(refresh=True).readers)
    if mode == "unavailable":
        held["set"] = None
    probed = []
    real = ProviderRegistry.status
    monkeypatch.setattr(ProviderRegistry, "status",
                        lambda self, pid, **kw: (probed.append(pid), real(self, pid, **kw))[1])
    r = admit(FeasibleActionSpace.build(world), o2.propose("simulate_pulse", *SIM, world=world), Authorities.of(*readers))
    assert r.admitted is None and "sim.secret" not in probed
    secret = [c for c in r.verification.checks if c.record_id == "sim.secret"]
    assert secret and all("not read" in c.detail["why"] for c in secret)
    assert {c.status.value for c in secret} == ({"owner_unavailable"} if mode == "unavailable" else {"mismatch"})


# ---- A8-F2 / A8-F5: the fixed-condition branch of the level predicate, and the reason it states -----------------------------------
def _a803():
    lvs = DiscreteLevels("bar", (Quantity(835.78852837, "bar"),))
    w = b.world("synthetic.a803", (
        b.var("T", R.FIXED_PROTOCOL_CONDITION, "psi", TS.CONSTANT_PER_RUN, domain=lvs),
        b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("mode", b.cats("mode", "a", "b"), P),),
                          fixed_conditions=(b.fixed("T", Quantity(83578852.83694999, "Pa")),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="a803"), references=(b.synthetic("a803/1"),))
    return ax.owned("a803", w)


def test_a_fixed_condition_the_identity_rule_does_not_match_is_never_executed_as_a_level(monkeypatch):
    o = _a803()
    proposal = o.propose("a", {"mode": b.cat("a")}, ("y",))
    d = FeasibleActionSpace.build(o.world).check(proposal)
    reason = next(x for x in d.reasons if x.code == "LEVEL_NOT_DECLARED")
    assert "nearer another declared level" not in reason.message and "identity rule" in reason.message
    r = admit(FeasibleActionSpace.build(o.world), proposal, o.authorities())
    assert r.admitted is None and "LEVEL_NOT_DECLARED" in r.codes()
    monkeypatch.setattr(fz, "level_problem", lambda *a: None)              # the family's guard regressed
    with pytest.raises(WorldRefused, match="executed only as a declared level"):
        admit(FeasibleActionSpace.build(o.world), proposal, o.authorities())


# ---- A8-F6: a subnormal spelling the owner does not call zero, and a negative zero -------------------------------------------------
def test_a_value_the_owner_does_not_call_zero_is_never_executed_as_the_zero_level():
    lv = DiscreteLevels("bar", (Quantity(0.0, "bar"), Quantity(8.753759, "bar")))
    w = b.world("synthetic.zero", (
        b.var("p", R.CONTROLLED_INPUT, "kPa", TS.CONSTANT_PER_RUN, domain=lv),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE, controls=(b.ctrl("p", lv, P),),
                          expected_observables=("y",), estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="z"), references=(b.synthetic("z/1"),))
    o = ax.owned("zero", w)
    space = FeasibleActionSpace.build(o.world)
    for value in (Quantity(5e-324, "Pa"), Quantity(-5e-324, "Pa"), Quantity(1e-300, "Pa")):
        d = space.check(o.propose("a", {"p": value}, ("y",)))
        assert not d.feasible and "LEVEL_NOT_DECLARED" in d.codes(), value
    for value in (Quantity(0.0, "Pa"), Quantity(-0.0, "Pa"), Quantity(0.0, "bar")):
        d = space.check(o.propose("a", {"p": value}, ("y",)))
        assert d.feasible and repr(dict(d.decided)["p"].magnitude) == "0.0", value   # the level, never -0.0
    assert not fz.is_declared_level(o.world, o.world.action("a"), "p", Quantity(-0.0, "kPa"))
