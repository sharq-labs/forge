"""GEN2-BR1.1 review round 3: one control per confirmed finding (benchmarks/mind_gen2_authority_v1/README.md).

The round's BLOCKER class (R3-A1 = R3-B-01 = R3-C-01 = R3-D1 = E3-F1, R3-A2, K3-F1) was one question asked of every
value kind: is the value a decision was made on the value an executor receives?  Round 2 decided a level control on
the proposer's spelling and executed the declared level; an integer was decided through a float and executed exact.
Now every family decides on the configuration AS IT WILL BE EXECUTED and admission mints exactly that."""

from __future__ import annotations

import dataclasses
import json
import math

import pytest

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, AdmissionResult, ApplicabilityBinding, BudgetReader, BudgetSource, DeclaredConstraint,
    DispatchRefused, ExecutionDesk, ExecutionKind, FeasibilityStatus as F, FeasibleActionSpace, MindWorldPort,
    TemporalSemantics as TS, WorldRefused, admit, authorize_dispatch, project_world, proposed_action_from_suggestion,
)
from engcore.mind.world.actions import ControlSpec
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific import (
    ConstraintDefinition, ConstraintOperator as Op, Quantity, RangeCondition, ScientificModelDefinition, ValidityDomain,
)
from engcore.scientific.ir.values import IntegerValue
from engcore.scientific.models.definition import InputSourceKind, ModelInputSpec
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.external import ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposerKind


def _desk(o, **policy):
    calls = []
    desk = ExecutionDesk(o.authorities(), calls.append, accept_synthetic=True, **policy)
    return desk.gateway(), calls


def _port(o, **flags):
    return MindWorldPort(FeasibleActionSpace.build(project_world(o.declaration, o.authorities())), **flags)


def _lm(world, action_id, assignments, observe=()):
    point = {"assignments": [{"variable": k, "value": v.to_dict()} for k, v in assignments.items()],
             "observe": list(observe)}
    s = ExternalSuggestion(ProposerKind.LANGUAGE_MODEL, "llm", "1", world.action(action_id).family, action_id, point,
                           "a language-model suggestion", extra={"world_revision": world.revision_id})
    return proposed_action_from_suggestion(s, world=world)


def _executed(port, gateway, calls, proposal):
    """Admit through the Mind-facing API; if admitted, execute and return (result, what the executor received)."""
    r = port.request_admission(proposal, gateway)
    if r.admitted is None:
        return r, None
    n = len(calls)
    port.execute(r.admitted, gateway)
    return r, calls[n]


# ---- R3-A1 (BLOCKER at 1a87f7c): a level control is decided AS the declared level it is, and executed as it -------------
def _soak(kind: str):
    """A model execution whose control T_set offers the levels 35 / 45 degC; the model (``applicability``) or a
    specification constraint (``constraint``) admits only T_set strictly above 35 degC."""
    model = ScientificModelDefinition(
        "synthetic.soak", "1", inputs=(ModelInputSpec("T_set", InputSourceKind.VARIABLE, unit_exemplar="degC"),),
        exclusions=(), excludes_nothing_because="synthetic",
        validity=ValidityDomain((RangeCondition("T_set", minimum=b.q(35, "degC"), maximum=b.q(80, "degC"),
                                                minimum_inclusive=(kind != "applicability")),)))
    route = ApplicabilityBinding(model)
    constraints = () if kind != "constraint" else (DeclaredConstraint(
        "hot_soak", ConstraintDefinition("hot_soak", "T_set", Op.GREATER_THAN, b.q(35, "degC")), None, ("*",), b.S,
        "synthetic: the specification soaks strictly above 35 degC"),)
    w = b.world("synthetic.soak", (
        b.var("T_set", R.CONTROLLED_INPUT, "degC", TS.CONSTANT_PER_RUN, domain=b.crange("T_set", "degC", -40, 85)),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("soak_sim", ActionFamily.EXPLORE, ActionMode.INTERVENE, execution=ExecutionKind.MODEL_EXECUTION,
                          controls=(b.ctrl("T_set", b.levels("degC", 35, 45), b.P),), expected_observables=("y",),
                          provider_requirements=(b.binding("sim.soak", "1.0"),), applicability=(route.binding_id,),
                          estimated_cost=b.cost(0, 1), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), applicability=(route,), providers=(b.provider("sim.soak", "1.0"),),
        constraints=constraints, budget=b.budget(5, 0, solver=(10, 0), ledger="soak"),
        references=(b.synthetic("soak/1"),))
    return ax.owned("soak", w)


@pytest.mark.parametrize("kind,refused", [("applicability", F.INFEASIBLE_APPLICABILITY), ("constraint", F.INFEASIBLE_DOMAIN)])
@pytest.mark.parametrize("proposer", ["port", "language_model"])
def test_every_spelling_of_a_refuted_level_is_refuted_and_an_admitted_level_is_executed_as_decided(kind, refused,
                                                                                                  proposer):
    o = _soak(kind)
    gateway, calls = _desk(o, suggestions_only=proposer == "language_model")
    port = _port(o, suggestions_only=proposer == "language_model")
    make = (lambda v: o.propose("soak_sim", {"T_set": v}, ("y",), world=port.world)) if proposer == "port" else (
        lambda v: _lm(port.world, "soak_sim", {"T_set": v}, ("y",)))
    for spelled in (b.q(35, "degC"), b.q(95, "degF"), b.q(308.15, "K"), b.q(35 - 4 * math.ulp(35.0), "degC")):
        r, sent = _executed(port, gateway, calls, make(spelled))
        assert r.status is refused and sent is None, (spelled, r.codes())
    for spelled in (b.q(45, "degC"), b.q(113, "degF"), b.q(318.15, "K")):
        r, sent = _executed(port, gateway, calls, make(spelled))
        assert r.status is F.FEASIBLE and dict(sent.settings) == {"T_set": 45.0}, (spelled, r.codes())
        assert dict(sent.configuration)["T_set"] == b.q(45, "degC") and r.admitted.proposal.value("T_set") == spelled


def test_a_strict_specification_bound_at_a_level_refuses_every_spelling_of_that_level():
    o = ax.gen1_pool()
    below = DeclaredConstraint("I_below_2A", ConstraintDefinition("I_below_2A", "I_A", Op.LESS_THAN, Quantity(2.0, "A")),
                               None, ("*",), RoleSource.PROBLEM_SPECIFICATION, "synthetic: strictly below 2 A")
    o.declaration = dataclasses.replace(o.declaration, constraints=o.declaration.constraints + (below,))
    gateway, calls = _desk(o)
    port = _port(o)
    for spelled in (Quantity(2.0, "A"), Quantity(2.0 - 2 * math.ulp(2.0), "A"), Quantity(2000.0 - 1e-12, "mA")):
        r, sent = _executed(port, gateway, calls, o.propose("pool_query", {"I_A": spelled, "t_on_s": b.q(60, "s")},
                                                            world=port.world))
        assert r.status is F.INFEASIBLE_DOMAIN and "CONSTRAINT_VIOLATED" in r.codes() and sent is None, spelled
    r, sent = _executed(port, gateway, calls, o.propose("pool_query", {"I_A": Quantity(1000, "mA"),
                                                                       "t_on_s": b.q(1, "min")}, world=port.world))
    assert r.feasible and dict(sent.settings) == {"I_A": 1.0, "t_on_s": 60.0}


# ---- R3-A2 (BLOCKER at 1a87f7c): one comparison rule, relative at every scale; a zero level is matched only by zero -------
def test_a_small_level_is_never_executed_as_a_zero_level_and_a_value_between_levels_is_refused():
    w = b.world("synthetic.cap", (
        b.var("C_load", R.CONTROLLED_INPUT, "F", TS.CONSTANT_PER_RUN, domain=b.crange("C_load", "F", 0, 1e-12)),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("load_test", ActionFamily.CHARACTERIZE, ActionMode.INTERVENE,
                          controls=(b.ctrl("C_load", b.levels("F", 0.0, 1e-14), b.P),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="cap"), references=(b.synthetic("cap/1"),))
    o = ax.owned("cap", w)
    gateway, calls = _desk(o)
    port = _port(o)
    for spelled, executed in ((b.q(1e-14, "F"), 1e-14), (b.q(10, "fF"), 1e-14), (b.q(0, "F"), 0.0)):
        r, sent = _executed(port, gateway, calls, o.propose("load_test", {"C_load": spelled}, ("y",), world=port.world))
        assert r.feasible and dict(sent.settings) == {"C_load": executed}, spelled
    r, sent = _executed(port, gateway, calls, o.propose("load_test", {"C_load": b.q(5e-15, "F")}, ("y",),
                                                        world=port.world))
    assert r.status is F.INFEASIBLE_PROTOCOL and r.codes() == ("LEVEL_NOT_DECLARED",) and sent is None


# ---- K3-F1 (BLOCKER at 1a87f7c): an integer is decided as the exact integer an executor receives ---------------------------
def _motor_iterations(upper: int):
    o = ax.owned("motor")
    domain = b.irange("solver_iterations", 1, upper)
    o.declaration = dataclasses.replace(
        o.declaration,
        variables=tuple(dataclasses.replace(v, domain=domain) if v.name == "solver_iterations" else v
                        for v in o.declaration.variables),
        actions=tuple(dataclasses.replace(a, controls=tuple(
            ControlSpec(c.variable, domain, c.declared_by, c.basis) if c.variable == "solver_iterations" else c
            for c in a.controls)) for a in o.declaration.actions))
    return o


def test_an_integer_control_is_decided_exactly_at_the_largest_exact_bound():
    upper = 2 ** 53
    o = _motor_iterations(upper)
    gateway, calls = _desk(o)
    port = _port(o)
    assignments, observe = ax.base("motor")["simulate_thermal"]
    for n, admitted in ((upper, True), (upper + 1, False), (upper + 2, False)):
        r, sent = _executed(port, gateway, calls, o.propose(
            "simulate_thermal", {**assignments, "solver_iterations": IntegerValue(n)}, observe, world=port.world))
        assert (sent is not None) is admitted, (n, r.codes())
        if admitted:
            assert dict(sent.settings)["solver_iterations"]["value"] == n            # the exact integer decided
        else:
            assert r.status is F.INFEASIBLE_DOMAIN and "OUTSIDE_RANGE" in r.codes()


@pytest.mark.parametrize("upper", [2 ** 53 + 2, 2 ** 63 - 1, 10 ** 16])
def test_an_integer_domain_whose_bound_a_float_cannot_hold_is_refused_at_declaration(upper):
    with pytest.raises(WorldRefused, match="2\\*\\*53"):
        _motor_iterations(upper)


# ---- K3-F2: what an executor receives is what was decided, for every admitted proposal in every spelling -----------------
RESPELL = {"ampere": "milliampere", "second": "minute", "degree_Celsius": "degree_Fahrenheit", "kelvin": "degree_Celsius",
           "newton": "kilonewton", "gram": "kilogram", "kilogram": "gram", "volt": "millivolt", "watt": "kilowatt",
           "revolutions_per_minute": "radian / second", "meter": "millimeter", "hertz": "kilohertz"}


def _respelled(assignments):
    out = {}
    for k, v in assignments.items():
        target = RESPELL.get(v.units) if isinstance(v, Quantity) else None
        out[k] = v if target is None else Quantity(v.magnitude_in(target), target)
    return out


@pytest.mark.parametrize("name", sorted(ax.WORLDS) + ["gen1_pool"])
def test_the_settings_an_executor_receives_are_the_decided_configuration_and_a_fixed_point(name):
    o = ax.gen1_pool() if name == "gen1_pool" else ax.WORLDS[name]()
    gateway, calls = _desk(o)
    port = _port(o)
    proposals = ax.base(name) if name != "gen1_pool" else {"pool_query": ({"I_A": b.q(1, "A"), "t_on_s": b.q(60, "s")}, ())}
    reached = 0
    for aid, (assignments, observe) in proposals.items():
        for spelling in (assignments, _respelled(assignments)):
            r, sent = _executed(port, gateway, calls, o.propose(aid, spelling, observe, world=port.world))
            if sent is None:
                continue
            reached += 1
            config = dict(sent.configuration)
            for var, value in config.items():                    # the configuration is in the declared unit, and the
                if isinstance(value, Quantity):                  # executor's setting is exactly its magnitude
                    assert value.units == port.world.variable(var).unit and dict(sent.settings)[var] == value.magnitude
            again, resent = _executed(port, gateway, calls, o.propose(aid, {
                k: (Quantity(dict(sent.settings)[k], port.world.variable(k).unit) if isinstance(v, Quantity) else v)
                for k, v in config.items() if port.world.action(aid).control(k) is not None}, observe, world=port.world))
            assert again.feasible and dict(resent.settings) == dict(sent.settings), (aid, again.codes())
    assert reached, name


# ---- MINORs ---------------------------------------------------------------------------------------------------------------
def test_budget_units_are_ratio_scale_and_a_count_is_exactly_dimensionless():
    with pytest.raises(WorldRefused, match="offset scale"):
        BudgetSource.ledger("cost", "acct", "degC")
    o = ax.owned("battery")
    ref = next(b_.ref for b_ in o.declaration.budget if b_.dimension == "solver_calls" and b_.kind == "ledger")
    o.ledgers[ref] = ax.ledger(300.0, 0.0, "percent", ref)
    with pytest.raises(WorldRefused, match="exactly in 'dimensionless'"):
        project_world(o.declaration, o.authorities())


def test_a_followed_budget_account_never_goes_back_a_revision():
    from engcore.mind.world import Authorities
    o = ax.owned("battery")
    ref = next(b_.ref for b_ in o.declaration.budget if b_.kind == "ledger")
    before = ax.ledger(10.0, 0.0, o.ledgers[ref].cost_unit, ref)
    after = ax.ledger(10.0, 1.0, before.cost_unit, ref)                # one settled charge later
    assert after.revision == before.revision + 1
    from engcore.mind.world import OwnerKind
    accounts = {"ledgers": {**o.ledgers, ref: before}}
    reader = BudgetReader.following(lambda: (accounts["ledgers"], o.experiments))
    authorities = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    assert authorities.live
    assert reader.read(OwnerKind.BUDGET_LEDGER, ref) is not None       # the account as first read
    accounts["ledgers"] = {**o.ledgers, ref: after}
    assert reader.read(OwnerKind.BUDGET_LEDGER, ref) is not None       # forward: fine
    accounts["ledgers"] = {**o.ledgers, ref: before}                   # restored to an earlier revision
    with pytest.raises(OwnerUnavailable, match="went back a revision"):
        reader.read(OwnerKind.BUDGET_LEDGER, ref)
    with pytest.raises(OwnerUnavailable, match="from then on"):        # and it stays refused (round 5)
        reader.read(OwnerKind.BUDGET_LEDGER, ref)


def test_the_desk_policy_admits_and_dispatches_only_certified_suggestions_whatever_the_port():
    o = ax.owned("battery")
    sim = ax.base("battery")["simulate_pulse"]
    gateway, calls = _desk(o, suggestions_only=True)
    open_gateway, _ = _desk(o)
    port = _port(o)                                                    # a port WITHOUT the flag
    bare = o.propose("simulate_pulse", *sim, world=port.world)
    with pytest.raises(WorldRefused, match="suggestions_only"):
        port.request_admission(bare, gateway)
    admitted = port.request_admission(bare, open_gateway).admitted     # admitted elsewhere ...
    assert admitted is not None
    with pytest.raises(DispatchRefused, match="suggestions_only"):
        port.execute(admitted, gateway)                                # ... is never dispatched by this desk
    certified = _lm(port.world, "simulate_pulse", *sim)
    r, sent = _executed(port, gateway, calls, certified)
    assert r.feasible and sent is not None
    flagged = _port(o, suggestions_only=True)
    with pytest.raises(DispatchRefused, match="certified"):
        flagged.execute(admitted, open_gateway)                        # the port's own flag holds at execute too


def test_only_admission_states_that_a_result_was_decided_under_live_readers():
    o = ax.owned("battery")
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *ax.base("battery")["simulate_pulse"]),
              o.authorities())
    assert r.live
    with pytest.raises(WorldRefused, match="only admission"):
        dataclasses.replace(r, live=True)
    with pytest.raises(WorldRefused, match="only admission"):
        AdmissionResult(r.status, r.reasons, r.verification, r.decision, None, r.proposal, r.world, r.space_id, True)


def test_a_replay_under_another_unit_registry_is_refused_however_its_snapshot_is_labelled():
    import copy
    from engcore.mind.world import AdmissionRecord, Authorities, replay_admission
    from engcore.mind.world import admission as adm
    from engcore.sria.decision.replay import ReplayOutcome
    o = ax.owned("battery")
    sim = ax.base("battery")["simulate_pulse"]
    live = o.authorities()
    rec = json.loads(json.dumps(AdmissionRecord.of(admit(FeasibleActionSpace.build(o.world),
                                                         o.propose("simulate_pulse", *sim), live), live).to_dict()))
    for label in ("unit_registry", None, "declaration"):
        snap = copy.deepcopy(rec["snapshot"])
        for item in snap["records"]:
            if item["record"]["owner_kind"] == "unit_registry":
                item["record"]["record_digest"], item["record"]["revision"] = "f" * 64, "f" * 16
                item["record"]["payload"]["fingerprint"] = "f" * 64
                item.pop("owner_kind", None) if label is None else item.__setitem__("owner_kind", label)
        forged = Authorities.from_snapshot(snap)
        world = project_world(o.declaration, forged)
        proposal = o.propose("simulate_pulse", *sim, world=world)
        result = admit(FeasibleActionSpace.build(world), proposal, forged)
        out = replay_admission({"schema": adm.RECORD_SCHEMA, "world": world.to_dict(), "proposal": proposal.to_dict(),
                                "snapshot": snap, "result": json.loads(json.dumps(result.to_dict()))})
        assert out.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE and "unit registry" in out.detail, label
