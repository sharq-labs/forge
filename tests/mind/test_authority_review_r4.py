"""GEN2-BR1.1 review round 4: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md).

Round 4's MAJORs: a fixed condition's own domain was checked on its declared spelling while the executor received the
converted value (R4-A1 = R4-C-F1), and the round-3 mint guard re-derived with the very function that built what it
checked (K4-F1).  Now every value a check reads, a fixed condition's included, is decided as executed, and admission
mints from the sources by a separate path and requires every value any family decided on to equal it."""

from __future__ import annotations

import dataclasses
import json
import sys

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, BudgetReader, BudgetSource, DeclaredConstraint, DispatchRefused, ExecutionDesk, FeasibilityStatus as F,
    FeasibleActionSpace, MindWorldPort, TemporalSemantics as TS, WorldRefused, admit, authorize_dispatch, project_world,
    proposed_action_from_suggestion,
)
from engcore.mind.world import actions as actions_mod
from engcore.mind.world import feasibility as fz
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific import (
    ConstraintDefinition, ConstraintOperator as Op, Quantity, ScientificVariable, VariableKind,
)
from engcore.scientific.ir.values import IntegerValue
from engcore.scientific.ir.variables import VariableRole as IR
from engcore.sria.campaign.budget import BudgetCharge, BudgetLedger
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind

SIM = ax.base("battery")["simulate_pulse"]


def _pressure_world(fixed_value: Quantity):
    """p is a controlled input declared in bar whose own domain is [0, 700] kPa; the action holds p fixed."""
    domain = ScientificVariable("p", "kPa", VariableKind.CONTINUOUS, IR.CONTROL, Quantity(0.0, "kPa"),
                                Quantity(700.0, "kPa"))
    return b.world("synthetic.fixed_domain", (
        b.var("p", R.CONTROLLED_INPUT, "bar", TS.CONSTANT_PER_RUN, domain=domain),
        b.var("t_on", R.CONTROLLED_INPUT, "s", TS.CONSTANT_PER_RUN, domain=b.crange("t_on", "s", 0, 100)),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("hold", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("t_on", b.crange("t_on", "s", 0, 100)),),
                          fixed_conditions=(b.fixed("p", fixed_value),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="fd"), references=(b.synthetic("fd/1"),))


# ---- R4-A1 = R4-C-F1 (MAJOR): a fixed condition's own domain is decided on the value as executed ---------------------------
def test_a_fixed_condition_inside_its_domain_only_in_its_declared_spelling_is_refused_at_declaration():
    edge = Quantity(101.52641641114641, "psi")     # inside 700 kPa as spelled; 7.000000000000001 bar as executed
    with pytest.raises(WorldRefused, match="as executed"):
        _pressure_world(edge)
    assert _pressure_world(Quantity(100.0, "psi")).action("hold") is not None


def test_the_domain_family_checks_a_fixed_condition_as_executed_even_when_declaration_checks_err(monkeypatch):
    monkeypatch.setattr(actions_mod, "membership", lambda domain, value: None)        # a bind check that errs
    w = _pressure_world(Quantity(101.52641641114641, "psi"))
    monkeypatch.undo()
    d = FeasibleActionSpace.build(w).check(b.propose(w, "hold", {"t_on": b.q(5, "s")}, ("y",)))
    reasons = [r for r in d.reasons if r.subject == "p"]
    assert d.status is not F.FEASIBLE and reasons and reasons[0].code == "OUTSIDE_RANGE"
    assert "fixed_condition" in reasons[0].detail


def test_an_action_level_that_executes_outside_the_variables_own_domain_is_refused_at_declaration():
    domain = ScientificVariable("I", "mA", VariableKind.CONTINUOUS, IR.CONTROL, Quantity(0.0, "mA"),
                                Quantity(700.0, "mA"))
    with pytest.raises(WorldRefused, match="as they are executed"):
        b.world("synthetic.edge_level", (
            b.var("I", R.CONTROLLED_INPUT, "A", TS.CONSTANT_PER_RUN, domain=domain),
            b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
            actions=(b.action("step", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                              controls=(b.ctrl("I", b.levels("mA", 350, 700), b.P),), expected_observables=("y",),
                              estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
            channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="el"), references=(b.synthetic("el/1"),))


def test_a_fixed_condition_that_is_a_level_of_its_variable_is_decided_and_executed_as_that_level():
    o = ax.gen1_pool()
    below = DeclaredConstraint("I_below_2A", ConstraintDefinition("I_below_2A", "I_A", Op.LESS_THAN, Quantity(2.0, "A")),
                               None, ("*",), RoleSource.PROBLEM_SPECIFICATION, "synthetic: strictly below 2 A")
    o.declaration = dataclasses.replace(o.declaration, constraints=o.declaration.constraints + (below,))
    w = o.world
    spec = w.action("pool_query")
    assert fz.as_executed(w, spec, "I_A", Quantity(1.9999999999999991, "A")) == Quantity(2.0, "A")
    assert fz.as_executed(w, spec, "I_A", Quantity(1999.9999999999998, "mA")) == Quantity(2.0, "A")


# ---- K4-F1 (MAJOR): the mint guard is independent of the resolution the families use --------------------------------------
def _hvac_strict_endpoint():
    import tests.mind.test_authority_review_r2 as r2
    return r2._hvac_strict_endpoint()


def _restated_fixed(o):
    from engcore.mind.world import ScientificWorld  # noqa: F401
    assignments, observe = ax.base("hvac_chamber")["simulate_building"]
    world = project_world(o.declaration, o.authorities())
    fixed = world.action("simulate_building").fixed("T_out").value
    restated = Quantity(fixed.to("kelvin").magnitude - 1e-10, "kelvin")
    return world, o.propose("simulate_building", {**assignments, "T_out": restated}, observe, world=world)


def test_a_resolution_that_reads_a_restated_fixed_condition_never_mints(monkeypatch):
    """The bc6980c read (a proposal's value for any variable) re-introduced into the shared resolution: the families
    decide FEASIBLE on the restated value, and admission refuses to mint it."""
    original = fz._resolve

    def bc6980c_read(world, spec, proposal, name, *, include_proposal=True):
        if include_proposal and proposal is not None and proposal.value(name) is not None:
            v = proposal.value(name)
            return fz._Resolved(v, "proposal", (v,))
        return original(world, spec, proposal, name, include_proposal=include_proposal)

    o = _hvac_strict_endpoint()
    world, forged = _restated_fixed(o)
    monkeypatch.setattr(fz, "_resolve", bc6980c_read)
    assert FeasibleActionSpace.build(world).check(forged).feasible            # the regressed check is fooled ...
    with pytest.raises(WorldRefused, match="not the value to be executed"):
        admit(FeasibleActionSpace.build(world), forged, o.authorities())       # ... admission is not


def test_one_family_that_decides_on_another_value_never_mints(monkeypatch):
    """Only the protocol family reads the proposer's raw spelling of a level (the round-3 defect in one family)."""
    o = ax.gen1_pool()
    below = DeclaredConstraint("I_below_2A", ConstraintDefinition("I_below_2A", "I_A", Op.LESS_THAN, Quantity(2.0, "A")),
                               None, ("pool_query",), RoleSource.PROTOCOL_METADATA, "synthetic: strictly below 2 A")
    o.declaration = dataclasses.replace(o.declaration, constraints=o.declaration.constraints + (below,))
    world = project_world(o.declaration, o.authorities())
    p = o.propose("pool_query", {"I_A": Quantity(1999.9999999999995, "mA"), "t_on_s": b.q(60, "s")}, world=world)
    assert admit(FeasibleActionSpace.build(world), p, o.authorities()).status is F.INFEASIBLE_PROTOCOL
    original = fz._resolve

    def protocol_reads_raw(world_, spec, proposal, name, **kw):
        if sys._getframe(2).f_code.co_name == "_check_protocol" and proposal is not None and spec.control(name):
            v = proposal.value(name)
            if v is not None:
                return fz._Resolved(v, "proposal", (v,))
        return original(world_, spec, proposal, name, **kw)

    monkeypatch.setattr(fz, "_resolve", protocol_reads_raw)
    assert FeasibleActionSpace.build(world).check(p).feasible
    with pytest.raises(WorldRefused, match="not the value to be executed"):
        admit(FeasibleActionSpace.build(world), p, o.authorities())


# ---- records state what was decided, in the unit decided ---------------------------------------------------------------------
def test_an_over_budget_refusal_records_the_amount_and_the_remainder_in_the_ledgers_unit():
    base = b.battery_world()
    sim = base.action("simulate_pulse")
    priced = dataclasses.replace(sim, estimated_cost={"experiments": IntegerValue(0), "solver_calls": IntegerValue(2),
                                                      "cost": Quantity(3.0, "dimensionless")},
                                 estimated_duration=Quantity(2.0, "hour"))
    o = ax.owned("battery", base.derive(reason="priced", actions=tuple(
        priced if a.action_id == "simulate_pulse" else a for a in base.actions)))
    o.declaration = dataclasses.replace(o.declaration, budget=tuple(
        x for x in o.declaration.budget if x.dimension not in ("cost", "wall_time")) + (
        BudgetSource.ledger("cost", "acct.cost", "hour"), BudgetSource.ledger("wall_time", "acct.wall")))
    o.ledgers["acct.cost"] = ax.ledger(120.0, 0, "minute", "c")
    o.ledgers["acct.wall"] = ax.ledger(60.0, 0, "minute", "w")
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    over = {x.subject: x.detail for x in r.reasons if x.code == "OVER_BUDGET"}
    assert over["cost"]["requested"]["units"] == over["cost"]["remaining"]["units"] == "minute"
    assert (over["cost"]["requested"]["magnitude"], over["cost"]["remaining"]["magnitude"]) == (180.0, 120.0)
    assert (over["wall_time"]["requested"]["magnitude"], over["wall_time"]["remaining"]["magnitude"]) == (120.0, 60.0)


def test_a_domain_refusal_keeps_the_proposers_spelling_and_states_the_value_decided_on():
    o = ax.gen1_pool()
    d = FeasibleActionSpace.build(o.world).check(o.propose("pool_query", {"I_A": Quantity(1150, "mA"),
                                                                          "t_on_s": b.q(60, "s")}))
    reason = next(r for r in d.reasons if r.code == "LEVEL_NOT_DECLARED")
    assert reason.detail["proposed"]["magnitude"] == 1150.0 and reason.detail["proposed"]["units"] == "milliampere"
    assert reason.detail["as_executed"]["units"] == "ampere"


def test_levels_closer_than_the_identity_rule_can_tell_apart_are_refused():
    from engcore.mind.world.domains import DiscreteLevels
    with pytest.raises(WorldRefused, match="closer than"):
        DiscreteLevels("A", (Quantity(1.0, "A"), Quantity(1.0000000000051, "A")))
    assert DiscreteLevels("A", (Quantity(1.0, "A"), Quantity(1.001, "A"))).levels


def test_the_authorization_names_the_models_whose_applicability_gated_it():
    o = ax.owned("battery")
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    auth = authorize_dispatch(r.admitted, o.authorities(), accept_synthetic=True)
    payload = auth.to_dict()
    assert payload["models"] and payload["models"] == [dict(m) for m in r.admitted.to_dict()["models"]]


def test_a_time_series_input_is_never_held_fixed_as_a_scalar():
    with pytest.raises(WorldRefused, match="TIME_SERIES"):
        b.world("synthetic.profile", (
            b.var("I_profile", R.CONTROLLED_INPUT, "A", TS.TIME_SERIES),
            b.var("t_on", R.CONTROLLED_INPUT, "s", TS.CONSTANT_PER_RUN, domain=b.crange("t_on", "s", 0, 100)),
            b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
            actions=(b.action("hold", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                              controls=(b.ctrl("t_on", b.crange("t_on", "s", 0, 100)),),
                              fixed_conditions=(b.fixed("I_profile", Quantity(2.0, "A")),), expected_observables=("y",),
                              estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
            channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="tp"), references=(b.synthetic("tp/1"),))


# ---- proposers -----------------------------------------------------------------------------------------------------------------
def test_alternatives_are_enumerated_for_a_language_model_proposal():
    o = ax.gen1_pool()
    world = o.world
    point = {"assignments": [{"variable": "I_A", "value": Quantity(1.15, "A").to_dict()},
                             {"variable": "t_on_s", "value": Quantity(60, "s").to_dict()}], "observe": []}
    s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", world.action("pool_query").family, "pool_query",
                           point, "an off-level current", extra={"world_revision": world.revision_id})
    proposal = proposed_action_from_suggestion(s, world=world)
    out = FeasibleActionSpace.build(world).alternatives(proposal, "I_A")
    assert [x.magnitude for x in out["options"]] == [1.0, 2.0]


def test_the_executor_guard_itself_applies_the_proposer_policy():
    o = ax.owned("battery")
    calls = []
    desk = ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True, suggestions_only=True)
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    auth = authorize_dispatch(r.admitted, o.authorities(), accept_synthetic=True)      # minted without the policy
    with pytest.raises(DispatchRefused, match="suggestions_only"):
        desk._executor(auth)                     # the guard the execution owner's executor sits behind (private)
    with pytest.raises(DispatchRefused, match="suggestions_only"):
        desk.dispatch(r.admitted)
    assert not calls


# ---- followed budget accounts ----------------------------------------------------------------------------------------------------
def test_a_followed_account_whose_history_was_rewritten_at_the_same_length_is_refused_then_and_after():
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    o.ledgers[lid].settle(charge_id="run-a", action_id="other", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    d2 = o.ledgers[lid].to_dict()
    accounts = {"ledgers": dict(o.ledgers)}
    reader = BudgetReader.following(lambda: (accounts["ledgers"], o.experiments))
    restored = BudgetLedger.from_dict(d2)
    rewritten = BudgetLedger(total_budget=restored.total_budget, cost_unit=restored.cost_unit,
                             charges=restored.charges[:1])
    rewritten.settle(charge_id="run-b", action_id="other", iteration=1, family=ActionFamily.EXPLORE, realized=3.0)
    assert rewritten.revision == restored.revision                     # the same length, another history
    accounts["ledgers"] = {**o.ledgers, lid: rewritten}
    with pytest.raises(OwnerUnavailable, match="rewrote their history"):
        reader.pinned()
    accounts["ledgers"] = {**o.ledgers, lid: BudgetLedger.from_dict(d2)}   # and back to what was seen before it
    with pytest.raises(OwnerUnavailable):
        reader.pinned()


def test_a_followed_account_restored_unchanged_or_topped_up_is_the_same_account():
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    old = o.ledgers[lid]
    charge = BudgetCharge("fixture.spent", "fixture", 0, ActionFamily.EXPLORE, realized=2, from_general_pool=2)
    o.ledgers[lid] = BudgetLedger(total_budget=old.total_budget, cost_unit=old.cost_unit, charges=(charge,))
    gateway_calls = []
    authorities = o.authorities()
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    gateway = ExecutionDesk(authorities, gateway_calls.append, accept_synthetic=True).gateway()
    gateway.dispatch(r.admitted)
    o.ledgers[lid] = BudgetLedger.from_dict(o.ledgers[lid].to_dict())   # a checkpoint restore, integer amounts
    gateway.dispatch(r.admitted)
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    o.ledgers[lid].total_budget = o.ledgers[lid].total_budget + 5.0     # a declaration top-up, history unchanged
    reader.pinned()
    assert len(gateway_calls) == 2


# ---- replay ------------------------------------------------------------------------------------------------------------------------
def test_a_decision_under_another_unit_registry_does_not_replay_here():
    from engcore.mind.world import ScientificWorld
    from engcore.sria.decision.replay import ReplayOutcome
    o = ax.owned("battery")
    payload = json.loads(json.dumps(o.world.to_dict()))
    payload["unit_registry"]["record_digest"] = "f" * 64
    payload = {k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")}
    forged = ScientificWorld.from_dict(payload)
    proposal = o.propose("simulate_pulse", *SIM, world=forged)
    record = FeasibleActionSpace.build(forged).check(proposal).to_dict()
    out = fz.replay_decision(record, forged.to_dict(), proposal.to_dict())
    assert out.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE and "unit registry" in out.detail


def test_an_admission_decided_on_a_matched_level_replays_byte_for_byte():
    from engcore.mind.world import AdmissionRecord, replay_admission
    from engcore.sria.decision.replay import ReplayOutcome
    o = ax.gen1_pool()
    live = o.authorities()
    r = admit(FeasibleActionSpace.build(o.world), o.propose("pool_query", {"I_A": Quantity(1000, "mA"),
                                                                           "t_on_s": b.q(1, "min")}), live)
    assert r.feasible and dict(r.admitted.configuration)["I_A"] == Quantity(1.0, "A")
    rec = json.loads(json.dumps(AdmissionRecord.of(r, live).to_dict()))
    assert replay_admission(rec).outcome is ReplayOutcome.REPRODUCED
