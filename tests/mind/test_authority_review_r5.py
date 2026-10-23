"""GEN2-BR1.1 review round 5: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md).

Round 5's MAJOR (B5-F1 = R5-C-F1 = R5-D1): the round-4 budget follower took a history it had just refused as its new
baseline, so a rolled-back account was refused once and accepted at the next verification.  A followed account that
went back or rewrote its history is now refused for good by that reader, and an account the world does not bind
refuses nothing (round 6: every handed account is still observed at every verification)."""

from __future__ import annotations

import dataclasses

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, BudgetReader, DeclarationReader, DeclaredConstraint, ExecutionDesk, FeasibilityStatus as F,
    FeasibleActionSpace, OwnerKind, TemporalSemantics as TS, WorldRefused, admit, authorize_dispatch,
)
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific import ConstraintDefinition, ConstraintOperator as Op, Quantity
from engcore.scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def _solver(o):
    return next(k for k in o.ledgers if k.endswith(".solver"))


# ---- B5-F1 = R5-C-F1 = R5-D1 (MAJOR): a rollback is refused for good, through the desk ----------------------------------------
def test_a_rolled_back_account_is_refused_at_every_later_dispatch_not_only_the_first():
    o = ax.owned("battery")
    lid = _solver(o)
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())          # the account as admitted
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.feasible
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                          realized=2.0)                                  # the executor spends
    from engcore.mind.world import DispatchRefused
    with pytest.raises(DispatchRefused, match="AUTHORITY_STALE"):        # the reader observes the spent account
        gateway.dispatch(r.admitted)
    o.ledgers[lid] = before                                              # the execution side rolls the account back
    for attempt in range(3):                                             # refused now, and at every later dispatch
        with pytest.raises(DispatchRefused, match="OWNER_UNAVAILABLE"):
            gateway.dispatch(r.admitted)
    assert len(calls) == 1


def test_an_account_the_world_does_not_bind_never_refuses_its_admission():
    o = ax.owned("battery")
    accounts = {"ledgers": {**o.ledgers, "unrelated": ax.ledger(1.0, 0.0, "hour", "unrelated")}}
    reader = BudgetReader.following(lambda: (accounts["ledgers"], o.experiments))
    assert reader.read(OwnerKind.BUDGET_LEDGER, _solver(o)) is not None
    broken = ax.ledger(1.0, 0.0, "hour", "unrelated")
    broken.reserved_validation_budget = 5.0                              # unreadable by its owner (in-place edit)
    accounts["ledgers"] = {**o.ledgers, "unrelated": broken}
    assert reader.read(OwnerKind.BUDGET_LEDGER, _solver(o)) is not None  # the bound account is unaffected


# ---- K5-F2: controls for two round-4 reader fixes ---------------------------------------------------------------------------------
def test_a_ledger_its_owner_cannot_read_back_is_owner_unavailable_not_an_error():
    o = ax.owned("battery")
    lid = _solver(o)
    world = o.world                                                      # projected while the ledger was readable
    o.ledgers[lid].reserved_validation_budget = o.ledgers[lid].total_budget + 1.0   # the class allows it in place
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), o.authorities())
    assert r.status is F.MISSING_INFORMATION and "AUTHORITY_OWNER_UNAVAILABLE" in r.codes()


def test_a_refused_declaration_read_advances_nothing():
    o = ax.owned("battery")
    first = o.declaration
    second = dataclasses.replace(first, declaration_id="zz." + first.declaration_id)
    held = {"set": [first, second]}
    reader = DeclarationReader.following(lambda: held["set"])
    reader.pinned()
    advanced = dataclasses.replace(first, revision=first.revision + 1)
    restated = dataclasses.replace(second, basis=second.basis + " (restated)")     # same revision, other content
    held["set"] = [advanced, restated]
    with pytest.raises(OwnerUnavailable, match="restated"):
        reader.pinned()
    held["set"] = [first, second]                                        # nothing advanced: the original set stands
    reader.pinned()


# ---- E5-F3: a fixed condition at a level of its variable's own domain is decided and executed as that level -------------------
def test_a_fixed_condition_at_its_variables_own_level_is_refused_where_the_level_is():
    lt = DeclaredConstraint("I_below_2A", ConstraintDefinition("I_below_2A", "I", Op.LESS_THAN, Quantity(2.0, "A")),
                            None, ("*",), RoleSource.PROBLEM_SPECIFICATION, "synthetic: strictly below 2 A")

    def world(fixed_value):
        return b.world("synthetic.own_level", (
            b.var("I", R.CONTROLLED_INPUT, "A", TS.CONSTANT_PER_RUN, domain=b.levels("A", 1, 2)),
            b.var("t_on", R.CONTROLLED_INPUT, "s", TS.CONSTANT_PER_RUN, domain=b.crange("t_on", "s", 0, 100)),
            b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
            actions=(b.action("hold", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                              controls=(b.ctrl("t_on", b.crange("t_on", "s", 0, 100)),),
                              fixed_conditions=(b.fixed("I", fixed_value),), expected_observables=("y",),
                              estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
            channels=(b.channel("y"),), constraints=(lt,), budget=b.budget(5, 0, ledger="ol"),
            references=(b.synthetic("ol/1"),))

    for spelled in (Quantity(2.0, "A"), Quantity(1.9999999999999991, "A"), Quantity(1999.9999999999998, "mA")):
        w = world(spelled)
        d = FeasibleActionSpace.build(w).check(b.propose(w, "hold", {"t_on": b.q(5, "s")}, ("y",)))
        assert d.status is F.INFEASIBLE_DOMAIN and "CONSTRAINT_VIOLATED" in d.codes(), spelled
    w = world(Quantity(1000, "mA"))
    d = FeasibleActionSpace.build(w).check(b.propose(w, "hold", {"t_on": b.q(5, "s")}, ("y",)))
    assert d.feasible and dict(d.decided)["I"] == Quantity(1.0, "A")


# ---- A5-F2: an OVER_BUDGET record states the remainder the owner compared with ----------------------------------------------------
def test_a_validate_refusal_records_both_pools_the_owner_compared_with():
    from engcore.mind.world import BudgetStatement
    led = BudgetLedger(total_budget=10.0, reserved_validation_budget=6.0, cost_unit="dimensionless")
    from engcore.mind.world.authority import OwnerRecord
    record = OwnerRecord(OwnerKind.BUDGET_LEDGER, "budget", "acct", "0", led.digest, {"ledger": led.to_dict()})
    statement = BudgetStatement("solver_calls", "ledger", {"ledger": led.to_dict()},
                                record.binding(("ledger",), {"ledger": led.to_dict()}, ""))
    ok, remaining, accounted, basis = statement.decide(IntegerValue(12).value, ActionFamily.VALIDATE)
    assert not ok and remaining.magnitude == 10.0 and basis == "validation_pool+general_pool"
    ok, remaining, _, basis = statement.decide(8, ActionFamily.VALIDATE)
    assert ok
    ok, remaining, _, basis = statement.decide(8, ActionFamily.EXPLORE)
    assert not ok and remaining.magnitude == 4.0 and basis == "general_pool"


# ---- A5-F4: a fixed condition's kind fits its variable ----------------------------------------------------------------------------
@pytest.mark.parametrize("value", [IntegerValue(7), CategoricalValue("high"), BooleanValue(True)])
@pytest.mark.parametrize("unit", ["bar", "degree", "percent"])         # round 6 (A6-F2): scaled dimensionless units too
def test_a_non_quantity_fixed_condition_for_a_unit_bearing_variable_is_refused(value, unit):
    with pytest.raises(WorldRefused, match="unit-bearing variable"):
        b.world("synthetic.fixed_kind", (
            b.var("p", R.CONTROLLED_INPUT, unit, TS.CONSTANT_PER_RUN),
            b.var("t_on", R.CONTROLLED_INPUT, "s", TS.CONSTANT_PER_RUN, domain=b.crange("t_on", "s", 0, 100)),
            b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
            actions=(b.action("hold", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                              controls=(b.ctrl("t_on", b.crange("t_on", "s", 0, 100)),),
                              fixed_conditions=(b.fixed("p", value),), expected_observables=("y",),
                              estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
            channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="fk"), references=(b.synthetic("fk/1"),))


# ---- A5-F6: an authorization says which applicability bindings gated it --------------------------------------------------------
def test_the_authorization_says_whether_each_applicability_binding_gated_the_action():
    o = ax.owned("battery")
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    models = authorize_dispatch(r.admitted, o.authorities(), accept_synthetic=True).to_dict()["models"]
    assert models and all(m["gating"] is True for m in models)                # a MODEL_EXECUTION action
    o2 = ax.owned("hvac_chamber")
    for aid, (assignments, observe) in ax.base("hvac_chamber").items():
        spec = o2.world.action(aid)
        if spec.applicability and spec.execution.value != "model_execution":
            res = admit(FeasibleActionSpace.build(o2.world), o2.propose(aid, assignments, observe), o2.authorities())
            if res.admitted is not None:
                assert all(m["gating"] is False for m in res.admitted.to_dict()["models"])


# ---- A5-F7: a fixed-condition refusal says what was declared and what is executed, never 'proposed' -------------------------------
def test_a_fixed_condition_refusal_never_calls_the_declared_value_proposed(monkeypatch):
    from engcore.mind.world import actions as actions_mod
    from tests.mind.test_authority_review_r4 import _pressure_world
    monkeypatch.setattr(actions_mod, "membership", lambda domain, value: None)
    w = _pressure_world(Quantity(101.52641641114641, "psi"))
    monkeypatch.undo()
    d = FeasibleActionSpace.build(w).check(b.propose(w, "hold", {"t_on": b.q(5, "s")}, ("y",)))
    reason = next(r for r in d.reasons if r.subject == "p")
    assert "proposed" not in reason.detail and {"fixed_condition", "as_executed"} <= set(reason.detail)
