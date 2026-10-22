"""GEN2-BR1.1 review round 2: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md)."""

from __future__ import annotations

import dataclasses

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (
    BudgetReader, BudgetSource, FeasibilityStatus as F, FeasibleActionSpace, WorldRefused, admit,
)

SIM = ax.br1.base("battery")["simulate_pulse"]


def _with_cost(o, ledger_unit: str, total: float, declared_unit: str, amount: float):
    """The battery's simulate_pulse priced at ``amount`` (in the declared cost unit) against a cost ledger."""
    ref = "battery.cost"
    o.ledgers[ref] = ax.ledger(total, 0.0, ledger_unit, ref)
    actions = tuple(dataclasses.replace(a, estimated_cost={**dict(a.estimated_cost), "cost": ax.q(amount, "dimensionless")},
                                        cost_basis="synthetic price") if a.action_id == "simulate_pulse" else a
                    for a in o.declaration.actions)
    o.declaration = dataclasses.replace(o.declaration, actions=actions, budget=tuple(
        b for b in o.declaration.budget if b.dimension != "cost") + (BudgetSource.ledger("cost", ref, declared_unit),))
    return admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())


# ---- R2-A1 (A-F4 residual): a cost amount is converted from the declared cost unit, never read in the ledger's -------------
@pytest.mark.parametrize("declared,amount,expected", [("hour", 3.0, F.INFEASIBLE_BUDGET), ("hour", 1.5, F.FEASIBLE),
                                                      ("minute", 150.0, F.INFEASIBLE_BUDGET),
                                                      ("minute", 90.0, F.FEASIBLE)])
def test_an_equal_budget_spelled_in_another_unit_decides_the_same(declared, amount, expected):
    in_hours = _with_cost(ax.owned("battery"), "hour", 2.0, declared, amount)
    in_minutes = _with_cost(ax.owned("battery"), "minute", 120.0, declared, amount)
    assert in_hours.status is in_minutes.status is expected, (in_hours.codes(), in_minutes.codes())


def test_a_cost_ledger_states_its_declared_unit_and_it_must_convert_into_the_ledgers():
    with pytest.raises(WorldRefused, match="unit"):
        BudgetSource.ledger("cost", "battery.cost")                    # no declared cost unit
    with pytest.raises(WorldRefused, match="only a cost ledger"):
        BudgetSource.ledger("solver_calls", "battery.solver", "hour")
    with pytest.raises(WorldRefused, match="does not convert"):
        _with_cost(ax.owned("battery"), "meter", 2.0, "hour", 1.0)


# ---- R2-B-01 / R2-A2: one owner account object is one account, whatever the reader calls it -----------------------------
def test_one_ledger_object_registered_under_two_ids_is_refused():
    led = ax.ledger(100.0, 0.0, "second", "acct")
    with pytest.raises(WorldRefused, match="one id"):
        BudgetReader({"acct_a": led, "acct_b": led})


# ---- R2-B-02: the admitted world is the owners' projection, carrying none of the caller's text -----------------------------
def test_caller_written_non_material_text_never_reaches_the_executor():
    from engcore.mind.world import ExecutionDesk, MindWorldPort, ScientificWorld
    o = ax.owned("battery")
    copy_ = ScientificWorld.from_dict({**o.world.to_dict(), "description": "the Mind's own words"})
    assert copy_.revision_id == o.world.revision_id                    # non-material: the same world
    queue = []
    gateway = ExecutionDesk(o.authorities(), queue.append, accept_synthetic=True).gateway()
    admitted = MindWorldPort(FeasibleActionSpace.build(copy_)).request_admission(
        o.propose("simulate_pulse", *SIM), gateway).admitted
    assert admitted.world.description == o.declaration.description != "the Mind's own words"


# ---- R2-B-05: a read the owner refused is recorded and refused again on replay ------------------------------------------------
def test_an_admission_refused_by_an_owner_read_replays_reproduced():
    import json
    from engcore.mind.world import AdmissionRecord, replay_admission
    from engcore.scientific.models.definition import ScientificModelDefinition
    from engcore.sria.decision.replay import ReplayOutcome

    class Sly(ScientificModelDefinition):
        pass
    o = ax.owned("battery")
    m = o.models.list()[0]
    sly = Sly(**{f: getattr(m, f) for f in m.__dataclass_fields__})
    authorities = o.authorities(models=ax.ModelRegistry((sly,)))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    assert r.admitted is None and "AUTHORITY_MISMATCH" in r.codes()
    record = json.loads(json.dumps(AdmissionRecord.of(r, authorities).to_dict()))
    assert record["snapshot"]["refused"] and replay_admission(record).outcome is ReplayOutcome.REPRODUCED


# ---- R2-B-06 / R2-B-07: re-derivation applies the owner's own rule to the payload, under the identity it is filed ---------
def test_a_ledger_charged_with_integer_amounts_replays_and_records_are_checked_against_their_filing():
    import copy
    import json
    from engcore.mind.world import AdmissionRecord, replay_admission
    from engcore.mind.world.owners import frozen_readers
    from engcore.sria.decision.replay import ReplayOutcome
    o = ax.owned("battery")
    led = o.ledgers["synthetic.battery.pulse-cell.solver"]
    led.settle(charge_id="int", action_id="x", iteration=3, family=ax.ActionFamily.EXPLORE, realized=1)   # an int
    o._world = None
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    record = json.loads(json.dumps(AdmissionRecord.of(r, o.authorities()).to_dict()))
    assert replay_admission(record).outcome is ReplayOutcome.REPRODUCED
    other = ax.run_state("battery.someone-else", {"cell": ("component", {
        "SOC": (ax.q(0.8, "dimensionless"), ax.covered(ax.q(0.75, "dimensionless"), ax.q(0.85, "dimensionless"))),
        "R0": (ax.q(0.012, "ohm"), ax.Uncertainty.unknown("not quantified"))})})
    forged = copy.deepcopy(record["snapshot"])
    item = next(i for i in forged["records"] if i["owner_kind"] == "system_state")
    item["record"]["payload"]["state"] = other.checkpoint.state.to_dict()  # another run's state, self-consistent
    item["record"]["record_digest"] = other.checkpoint.state.digest
    with pytest.raises(WorldRefused, match="another run"):
        frozen_readers(forged)
    forged = copy.deepcopy(record["snapshot"])
    item = next(i for i in forged["records"] if i["owner_kind"] == "model_record")
    item["record"]["record_id"] = '["some.other.model","9"]'
    with pytest.raises(WorldRefused, match="filed under"):
        frozen_readers(forged)


# ---- R2-B-10: a probe that fails is an owner that cannot answer, not a missing record -------------------------------------
def test_a_failing_provider_probe_is_owner_unavailable():
    from engcore.mind.world import BindingStatus, verify_world
    o = ax.owned("battery")
    pid = o.world.providers[0].provider_id

    def broken():
        raise RuntimeError("the probe crashed")
    entry = o.providers._entries[pid]
    o.providers._entries[pid] = (entry[0], broken)
    failures = verify_world(o.world, o.authorities(refresh=True)).failures()
    assert {c.status for c in failures} == {BindingStatus.OWNER_UNAVAILABLE}


# ---- R2-A3 / R2-A4 / R2-A6 / R2-A7 ---------------------------------------------------------------------------------------------
def test_a_continuous_range_is_never_called_admissible():
    o = ax.owned("battery")
    space = FeasibleActionSpace.build(o.world)
    alt = space.alternatives(o.propose("simulate_pulse", *SIM), "t_pulse")
    assert alt["kind"] == "declared_range" and "NOT checked" in alt["label"]


def test_a_value_the_proposer_may_not_set_is_never_read():
    """R2-A4: the model reads the ambient temperature, which this action does not offer as a control.  A proposer that
    assigns it anyway is refused by the role family, and its value never reaches the core's applicability assessment
    (the input stays the world's current value, which is not exact)."""
    import dataclasses as dc
    w = ax.br1.battery_world()
    spec = w.action("simulate_pulse")
    fixed_ambient = dc.replace(spec, controls=tuple(c for c in spec.controls if c.variable != "T_amb"))
    w = w.derive(reason="the ambient is not offered", actions=tuple(fixed_ambient if a is spec else a for a in w.actions))
    proposal = {"I": ax.q(2.0, "A"), "t_pulse": ax.q(60, "s"), "T_amb": ax.q(25, "degC")}
    d = FeasibleActionSpace.build(w).check(ax.br1.propose(w, "simulate_pulse", proposal))
    assert "CONTROL_NOT_OFFERED_BY_ACTION" in {r.code for r in d.reasons}
    a = next(x for x in d.annotations if "assessments" in x)
    assert a["not_exact_inputs"] == ["T_amb"] and a["core_status"] is None and a["assessments"] == []


def test_the_state_family_has_no_definite_verdict_left_and_a_record_carrying_one_is_refused():
    from engcore.mind.world.feasibility import REASON_CODES, CheckFamily, FeasibilityDecision
    gone = {"PRECONDITION_VIOLATED", "STATE_OUTSIDE_DECLARED_DOMAIN", "STATE_DOMAIN_UNDECIDED", "PRECONDITION_UNDECIDED"}
    assert not gone & REASON_CODES[CheckFamily.STATE]
    w = ax.br1.battery_world()
    d = FeasibleActionSpace.build(w).check(ax.br1.propose(w, "pulse", {"I": ax.q(1.0, "A"), "t_pulse": ax.q(60, "s")}))
    payload = d.to_dict()
    reason = next(r for r in payload["reasons"] if r["family"] == "state")
    reason["code"], reason["status"] = "PRECONDITION_VIOLATED", "INFEASIBLE_STATE"
    payload["status"] = "INFEASIBLE_STATE"
    with pytest.raises(WorldRefused):
        FeasibilityDecision.from_dict(payload)


def test_a_level_proposed_in_another_unit_reaches_the_executor_as_the_declared_level():
    from engcore.mind.world import authorize_dispatch
    o = ax.gen1_pool()
    r = admit(FeasibleActionSpace.build(o.world), o.propose("pool_query", {"I_A": ax.q(1000.0000000000004, "mA"),
                                                                           "t_on_s": ax.q(60, "s")}), o.authorities())
    assert r.admitted is not None
    assert dict(r.admitted.configuration)["I_A"] == ax.q(1000.0000000000004, "mA")      # as proposed
    assert r.admitted.settings_in_declared_units()["I_A"] == 1.0                        # the declared level, exactly
    auth = authorize_dispatch(r.admitted, o.authorities(), accept_synthetic=True)
    assert dict(auth.settings)["I_A"] == 1.0


# ---- lens C: C2-M2 (declaration revisions move forward), C2-M5 (ledger totals), C2-M6 (suggestions-only port) ---------------
def test_a_followed_declaration_never_goes_back_a_revision():
    from engcore.mind.world import Authorities, BindingStatus, DeclarationReader, verify_world
    o = ax.owned("battery")
    held = [dataclasses.replace(o.declaration, revision=3)]
    reader = DeclarationReader.following(lambda: held)
    authorities = Authorities.of(*(reader if type(r) is DeclarationReader else r for r in o.authorities().readers))
    reader.pinned()
    held[0] = o.declaration                                            # revision 1 again, after 3 was in force
    assert {c.status for c in verify_world(o.world, authorities).failures()} == {BindingStatus.OWNER_UNAVAILABLE}


def test_a_recorded_ledger_whose_derived_totals_lie_does_not_replay():
    import copy
    from engcore.mind.world import AdmissionRecord
    from engcore.mind.world.owners import frozen_readers
    o = ax.owned("battery")
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    snap = copy.deepcopy(AdmissionRecord.of(r, o.authorities()).to_dict()["snapshot"])
    item = next(i for i in snap["records"] if i["owner_kind"] == "budget_ledger")
    item["record"]["payload"]["ledger"]["remaining"] = 1e9
    from engcore.sria.decision.replay import canonical_digest
    item["record"]["record_digest"] = canonical_digest(item["record"]["payload"]["ledger"])
    with pytest.raises(WorldRefused, match="derived totals"):
        frozen_readers(snap)


def test_a_suggestions_only_port_refuses_a_bare_proposal():
    from engcore.mind.world import ExecutionDesk, MindWorldPort
    o = ax.owned("battery")
    gateway = ExecutionDesk(o.authorities(), lambda auth: auth, accept_synthetic=True).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(o.world), suggestions_only=True)
    with pytest.raises(WorldRefused, match="certified ExternalSuggestion"):
        port.request_admission(o.propose("simulate_pulse", *SIM), gateway)


# ---- lens D: D2-F1 (provider report), D2-F2 (head regression), D2-F3 (replaced accounts), D2-F5 (unit registry), D2-F6 --------
def _record(o):
    import json
    from engcore.mind.world import AdmissionRecord
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    return json.loads(json.dumps(AdmissionRecord.of(r, o.authorities()).to_dict()))


def test_a_recorded_provider_report_must_be_the_owners_assessment_of_its_status():
    import copy
    from engcore.mind.world import replay_admission
    from engcore.sria.decision.replay import ReplayOutcome
    record = _record(ax.owned("battery"))
    assert replay_admission(record).outcome is ReplayOutcome.REPRODUCED
    forged = copy.deepcopy(record)
    item = next(i for i in forged["snapshot"]["records"] if i["owner_kind"] == "provider_status")
    item["record"]["payload"]["report"]["health"] = "broken"           # the status (and its digest) untouched
    out = replay_admission(forged)
    assert out.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE and "assessment" in out.detail


def test_a_followed_run_head_never_goes_back():
    from engcore.mind.world import BindingStatus, verify_world
    o = ax.owned("battery")
    authorities = o.authorities()
    o.advance()
    verify_world(o.world, authorities)                                 # the reader has now seen the later head
    o.head = o.run.checkpoint                                          # the execution side states the earlier one
    assert {c.status for c in verify_world(o.world, authorities).failures()} == {BindingStatus.OWNER_UNAVAILABLE}


def test_a_following_budget_reader_sees_a_replaced_account_object():
    from engcore.mind.world import BindingStatus, verify_world
    o = ax.owned("battery")
    authorities = o.authorities()
    assert verify_world(o.world, authorities).ok
    ref = "synthetic.battery.pulse-cell.solver"
    restored = ax.BudgetLedger.from_dict(o.ledgers[ref].to_dict())    # the execution side restores its account...
    restored.settle(charge_id="after-restore", action_id="x", iteration=1, family=ax.ActionFamily.EXPLORE, realized=1.0)
    o.ledgers[ref] = restored                                          # ...and replaces the object
    failures = verify_world(o.world, authorities).failures()
    assert failures and {c.status for c in failures} == {BindingStatus.STALE}


def test_a_replay_recorded_under_another_unit_registry_is_not_reproduced_here():
    import copy
    from engcore.mind.world import replay_admission
    from engcore.sria.decision.replay import ReplayOutcome
    record = _record(ax.owned("battery"))
    forged = copy.deepcopy(record)
    item = next(i for i in forged["snapshot"]["records"] if i["owner_kind"] == "unit_registry")
    other = "f" * 64
    item["record"]["record_digest"], item["record"]["revision"] = other, other[:16]
    item["record"]["payload"]["fingerprint"] = other
    out = replay_admission(forged)
    assert out.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE


def test_a_level_is_matched_by_one_rule_in_every_spelling():
    from engcore.mind.world.domains import DiscreteLevels, LEVEL_ULP, matched_level
    amps = DiscreteLevels("ampere", (ax.q(1.0, "A"), ax.q(2.0, "A")))
    assert matched_level(amps, ax.q(1000, "mA")) == ax.q(1.0, "A")
    assert matched_level(amps, ax.q(1.0000000000004, "A")) is None        # ~1800 ulp: not a level, in any spelling
    assert matched_level(amps, ax.q(1000.0000000004, "mA")) is None
    temps = DiscreteLevels("degree_Celsius", (ax.q(25, "degC"),))
    assert matched_level(temps, ax.q(298.15, "K")) == ax.q(25, "degC")    # conversion noise, within LEVEL_ULP
    assert LEVEL_ULP <= 64


# ---- R2-F4: the standing never closes an action on a value its proposals set ---------------------------------------------
@pytest.mark.parametrize("name", sorted(ax.WORLDS))
def test_every_action_a_base_proposal_admits_is_open_in_the_standing(name):
    o = ax.WORLDS[name]()
    space = FeasibleActionSpace.build(o.world)
    admitted = [aid for aid, (assignments, observe) in ax.base(name).items()
                if admit(space, o.propose(aid, assignments, observe), o.authorities()).feasible]
    assert admitted                                                    # the control is not vacuous
    assert set(admitted) <= set(space.open_actions()), (admitted, space.open_actions())
    for entry in space.entries:                                        # no standing reason on a control or fixed value
        spec = o.world.action(entry.action_id)
        assert not [r for r in entry.standing if r.family.value == "state"
                    and (spec.control(r.subject) is not None or spec.fixed(r.subject) is not None)]


# ---- R2-F6 / R2-F10: an admitted action says what its configuration and its waived budget rest on -----------------------------
def test_admitted_actions_and_authorizations_state_the_requested_configuration_and_declared_unbounded_budget():
    from engcore.mind.world import admission as adm
    from engcore.mind.world import authorize_dispatch
    o = ax.owned("battery")
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), o.authorities())
    auth = authorize_dispatch(r.admitted, o.authorities(), accept_synthetic=True)
    waived = sorted([list(p) for p in o.world.budget.unbounded])
    assert waived                                                      # battery waives cost by declaration
    for payload in (r.admitted.to_dict(), auth.to_dict()):
        assert payload["configuration_basis"] == adm.CONFIGURATION_BASIS
        assert "realization_uncertainty_not_assessed" in payload["configuration_basis"]
        assert sorted(payload["budget_unbounded_by_declaration"]) == waived


# ---- R2-F9: SRIA verdicts leave only a decision made under live owner readers ------------------------------------------------
def test_sria_verdicts_are_exported_only_from_an_admission_under_live_readers():
    from engcore.mind.world import Authorities
    o = ax.gen1_pool()
    off = {"I_A": ax.q(1.15, "A"), "t_on_s": ax.q(60, "s")}
    space = FeasibleActionSpace.build(o.world)
    live = admit(space, o.propose("pool_query", off), o.authorities())
    assert live.live and live.verification.ok and live.feasibility_verdicts()
    snapshot = o.authorities().snapshot(o.world.authority_bindings())
    frozen = admit(space, o.propose("pool_query", off), Authorities.from_snapshot(snapshot))
    assert not frozen.live and frozen.verification.ok and frozen.status is live.status
    assert frozen.feasibility_verdicts() == ()                         # a snapshot decides, but never exports
    assert frozen.digest == live.digest                                # liveness is not part of the identity


# ---- round-2 critic K-F1 (BLOCKER at bc6980c): a restated fixed condition never moves the value decided on ---------------------
def _hvac_strict_endpoint():
    """hvac_chamber whose model is valid only for T_out < 35 degC (a strict endpoint at the protocol's fixed level)."""
    from engcore.scientific import Quantity
    o = ax.owned("hvac_chamber")
    m = next(x for x in o.models.list() if x.validity.context_keys >= {"T_out"})
    cond = next(c for c in m.validity.conditions if c.name == "T_out")
    strict = dataclasses.replace(m, validity=dataclasses.replace(m.validity, conditions=tuple(
        dataclasses.replace(c, maximum=Quantity(35.0, "degC"), maximum_inclusive=False) if c is cond else c
        for c in m.validity.conditions)))
    o.models = ax.ModelRegistry(tuple(strict if x is m else x for x in o.models.list()))
    return o


def _hvac_constraint(source):
    """hvac_chamber with a declared constraint T_out < 35 degC (protocol metadata or problem specification)."""
    from engcore.mind.repsem.roles import RoleSource
    from engcore.mind.world.domains import DeclaredConstraint
    from engcore.scientific import ConstraintDefinition, ConstraintOperator as Op, Quantity
    o = ax.owned("hvac_chamber")
    scope = ("simulate_building",) if source == "protocol" else ("*",)
    c = DeclaredConstraint("t_out_below_35", ConstraintDefinition("t_out_below_35", "T_out", Op.LESS_THAN,
                                                                  Quantity(35.0, "degC")), None, scope,
                           RoleSource.PROTOCOL_METADATA if source == "protocol" else RoleSource.PROBLEM_SPECIFICATION,
                           "synthetic: the chamber stays below 35 degC")
    o.declaration = dataclasses.replace(o.declaration, constraints=o.declaration.constraints + (c,))
    return o


def _lm(world, assignments, observe):
    from engcore.mind.world import proposed_action_from_suggestion
    from engcore.sria.decision.external import ExternalSuggestion
    from engcore.sria.decision.hypotheses import ProposerKind
    point = {"assignments": [{"variable": k, "value": v.to_dict()} for k, v in assignments.items()],
             "observe": list(observe)}
    s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", world.action("simulate_building").family,
                           "simulate_building", point, "restating the protocol temperature in kelvin",
                           extra={"world_revision": world.revision_id})
    return proposed_action_from_suggestion(s, world=world)


@pytest.mark.parametrize("variant,expected", [("strict_endpoint", F.INFEASIBLE_APPLICABILITY),
                                              ("protocol", F.INFEASIBLE_PROTOCOL),
                                              ("specification", F.INFEASIBLE_DOMAIN)])
@pytest.mark.parametrize("proposer", ["port", "language_model"])
def test_a_restated_fixed_condition_is_decided_and_dispatched_at_the_fixed_value(variant, expected, proposer):
    from engcore.mind.world import ExecutionDesk, IntakeRefusal, MindWorldPort, project_world
    from engcore.scientific import Quantity
    o = _hvac_strict_endpoint() if variant == "strict_endpoint" else _hvac_constraint(variant)
    assignments, observe = ax.base("hvac_chamber")["simulate_building"]
    calls = []
    gateway = ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(project_world(o.declaration, o.authorities())))
    fixed = port.world.action("simulate_building").fixed("T_out").value
    restated = Quantity(fixed.to("kelvin").magnitude - 1e-10, "kelvin")    # the same value at 12 digits
    make = (lambda a: o.propose("simulate_building", a, observe, world=port.world)) if proposer == "port" else (
        lambda a: _lm(port.world, a, observe))
    honest, forged = make(assignments), make({**assignments, "T_out": restated})
    assert not isinstance(forged, IntakeRefusal), forged
    h, r = port.request_admission(honest, gateway), port.request_admission(forged, gateway)
    assert h.status is expected and r.status is expected, (h.codes(), r.codes())
    assert r.admitted is None and not calls
