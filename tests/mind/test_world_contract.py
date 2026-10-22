"""GEN2-BR1 contract tests: the fail-closed, authority and replay properties the design and authority reviews required.

Each block pins one property of ``engcore.mind.world`` that the failing-first file does not:

* removing information (a value, an uncertainty, a provider, a budget declaration, a cost, a fixed condition, a
  control's value) never turns a non-FEASIBLE decision FEASIBLE;
* model applicability gates model execution only, through the core assessment, with its status verbatim, and holds
  at both edges of an interval;
* an undeclared budget dimension or cost is MISSING_INFORMATION, never unlimited or zero;
* the execution gate holds its own world, dispatches only what it re-derives, shares one ledger per world revision,
  reads provider builds live, refuses synthetic worlds unless allowed and verifies bound values against their owner
  records and models against the registry;
* the Mind port holds a detached copy and reaches no executor; external proposals enter only as ExternalSuggestion
  records bound to the port's revision;
* replay verifies its inputs before recomputing; revisions verify as a chain; identity is unit-canonical.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import pathlib

import pytest

import engcore.mind.world as world_pkg
from benchmarks.mind_gen2_world_v1 import fixtures as fx
from engcore.mind.repsem import canonical_bytes
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, CheckFamily, ClearedAction, ExecutionGate, FeasibilityDecision, FeasibilityStatus as F,
    FeasibleActionSpace, FORBIDDEN_PROPOSAL_KEYS, GateRefused, IntakeCode, IntakeRefusal, MindWorldPort,
    ObservationChannel, ProposedAction, RecordKind, RecordRef, ScientificWorld, TemporalSemantics as TS, ValueOrigin,
    WorldBudget, WorldRefused, binders, replay_decision, verify_lineage,
)
from engcore.mind.world.domains import domain_problem, membership
from engcore.mind.world.feasibility import STATUS_BY_SOURCE, FeasibilityReason
from engcore.mind.world.world import ProviderSnapshot
from engcore.providers.health import ProviderHealth, ProviderHealthReport, assess_health
from engcore.scientific import ScientificVariable, Uncertainty, VariableKind, VariableRole as IR
from engcore.scientific.ir.values import CategoricalValue, IntegerValue
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.external import AUTHORITY_KEYS, ExternalSuggestion
from engcore.sria.decision.hypotheses import ProposalProvenance, ProposerKind
from engcore.sria.decision.recommendation import BudgetPlan
from engcore.sria.decision.replay import ReplayOutcome
from engcore.system_runtime.state import InitialStateSpec, OwnerState, SystemState

q, cat = fx.q, fx.cat
D = fx.DIMLESS


def space(w: ScientificWorld) -> FeasibleActionSpace:
    return FeasibleActionSpace.build(w)


def check(w: ScientificWorld, action_id: str, assignments, observe=()):
    return space(w).check(fx.propose(w, action_id, assignments, observe))


def codes(d) -> set[str]:
    return {r.code for r in d.reasons}


def with_variable(w: ScientificWorld, name: str, reason: str, **changes) -> ScientificWorld:
    return w.derive(reason=reason, variables=tuple(dataclasses.replace(v, **changes) if v.name == name else v
                                                   for v in w.variables))


def rebound(w: ScientificWorld, name: str, reason: str, **changes) -> ScientificWorld:
    """A bound value restated: the world never edits it, so the restatement cites a newer (synthetic) record."""
    return with_variable(w, name, reason, source=fx.synthetic(f"rebound/{name}/{reason}"), **changes)


def with_action(w: ScientificWorld, action_id: str, reason: str, **changes) -> ScientificWorld:
    return w.derive(reason=reason, actions=tuple(dataclasses.replace(a, **changes) if a.action_id == action_id else a
                                                 for a in w.actions))


def _hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@pytest.fixture(scope="module")
def battery():
    return fx.battery_world()


# ---- removal never improves an answer ---------------------------------------------------------------------------------------
def _proposals(name: str, w: ScientificWorld):
    out = []
    for aid, (assignments, observe) in fx.base(name).items():
        out.append((aid, assignments, observe))
        spec = w.action(aid)
        for control in spec.controls:                      # one non-FEASIBLE variant per control: never supplied
            out.append((aid, {k: v for k, v in assignments.items() if k != control.variable}, observe))
    return out


def _reductions(w: ScientificWorld):
    """World-side information removals: every one must leave a non-FEASIBLE decision non-FEASIBLE."""
    for v in w.variables:
        if v.value is not None:
            yield f"withdraw value {v.name}", lambda w=w, n=v.name: with_variable(
                w, n, "value withdrawn", value=None, origin=None, source=None, value_basis="",
                uncertainty=Uncertainty.unknown("withdrawn"))
            if v.uncertainty.is_quantified:
                yield f"forget uncertainty {v.name}", lambda w=w, n=v.name: rebound(
                    w, n, "uncertainty forgotten", uncertainty=Uncertainty.unknown("forgotten"))
    for p in w.providers:
        yield f"drop provider {p.provider_id}", lambda w=w, pid=p.provider_id: w.derive(
            reason="provider snapshot dropped", providers=tuple(x for x in w.providers if x.provider_id != pid))
    for dim, _ in w.budget.unbounded:
        yield f"undeclare {dim}", lambda w=w, d=dim: w.derive(reason="declaration dropped", budget=dataclasses.replace(
            w.budget, unbounded=tuple(x for x in w.budget.unbounded if x[0] != d)))
    for a in w.actions:
        for dim, _ in a.estimated_cost:
            yield f"drop cost {a.action_id}.{dim}", lambda w=w, a=a, d=dim: with_action(
                w, a.action_id, "cost dropped", estimated_cost=tuple(x for x in a.estimated_cost if x[0] != d))
        for f in a.fixed_conditions:
            yield f"drop fixed {a.action_id}.{f.name}", lambda w=w, a=a, n=f.name: with_action(
                w, a.action_id, "fixed condition dropped",
                fixed_conditions=tuple(x for x in a.fixed_conditions if x.name != n))


@pytest.mark.parametrize("name", sorted(fx.WORLDS))
def test_removing_information_never_turns_a_refusal_into_feasible(name):
    w = fx.WORLDS[name]()
    proposals = _proposals(name, w)
    before = {(aid, repr(sorted(a)), o): check(w, aid, a, o).status for aid, a, o in proposals}
    assert F.FEASIBLE in before.values() and any(s is not F.FEASIBLE for s in before.values())
    stated = 0
    for label, reduce in _reductions(w):
        try:
            reduced = reduce()
        except WorldRefused:
            continue                                        # a world that cannot be stated is not a FEASIBLE answer
        stated += 1
        for aid, a, o in proposals:
            after = check(reduced, aid, {k: v for k, v in a.items()}, o).status
            if before[(aid, repr(sorted(a)), o)] is not F.FEASIBLE:
                assert after is not F.FEASIBLE, f"{name}: '{label}' turned {aid} FEASIBLE"
    assert stated, f"{name}: no reduction could be stated, so nothing was exercised"


# ---- applicability gates model execution only ---------------------------------------------------------------------------------
def test_s9_outside_the_route_models_domain_is_infeasible_applicability_with_the_core_status(battery):
    d = check(battery, "simulate_pulse", {"I": q(2, "A"), "T_amb": q(80, "degC"), "t_pulse": q(60, "s")})
    assert d.status is F.INFEASIBLE_APPLICABILITY
    r = next(r for r in d.reasons if r.code == "OUTSIDE_VALIDATED_DOMAIN")
    assert r.detail["validity_status"] == "outside_validated_domain" and list(r.detail["violated"]) == ["T_amb"]
    payload = d.to_dict()
    assert payload["classification"] == "action_feasibility_not_scientific_support"
    assert not {"hypothesis", "claim", "verdict", "supported", "refused"} & set(payload)


def test_conditional_provider_availability_is_the_route_models_applicability():
    motor = fx.motor_world()
    d = check(motor, "simulate_thermal", {"I_cmd": q(28, "A"), "solver_iterations": IntegerValue(200)})
    assert d.status is F.INFEASIBLE_APPLICABILITY            # 28 A is inside the control's 0-30 A, outside the route
    assert check(motor, "simulate_thermal", {"I_cmd": q(25, "A"), "solver_iterations": IntegerValue(200)}).feasible


def test_applicability_is_an_annotation_for_a_system_query(battery):
    spec = battery.action("signed_pulse")
    w = battery.derive(reason="annotate", actions=tuple(
        dataclasses.replace(a, applicability=(battery.applicability[0].binding_id,)) if a is spec else a
        for a in battery.actions))
    d = check(w, "signed_pulse", {"mode": cat("discharge"), "I": q(-2, "A"), "t_pulse": q(30, "s")})
    assert d.feasible and d.annotations[0]["gating"] is False
    with pytest.raises(WorldRefused, match="MODEL_EXECUTION"):
        dataclasses.replace(battery.action("simulate_pulse"), applicability=())


def test_unknown_and_undecided_applicability_are_missing_information():
    drone = fx.drone_world()
    blind = with_variable(drone, "wind", "anemometer reading withdrawn", value=None, origin=None, source=None,
                          uncertainty=Uncertainty.unknown("withdrawn"))
    d = check(blind, "simulate_flight", {"thrust_cmd": q(12, "N")})
    assert d.status is F.MISSING_INFORMATION and "APPLICABILITY_NOT_SUPPLIED" in codes(d)
    straddle = rebound(drone, "wind", "gusty", value=q(11.8, "m/s"), uncertainty=fx.interval(11.8, 0.5, "m/s"))
    assert "APPLICABILITY_UNDECIDED" in codes(check(straddle, "simulate_flight", {"thrust_cmd": q(12, "N")}))
    windy = rebound(drone, "wind", "storm", value=q(15, "m/s"), uncertainty=fx.interval(15, 0.5, "m/s"))
    assert check(windy, "simulate_flight", {"thrust_cmd": q(12, "N")}).status is F.INFEASIBLE_APPLICABILITY


def test_applicability_holds_at_both_edges_of_an_interval():
    """An interval wider than the route on BOTH sides is undecided, not outside: each side is decided on its own."""
    narrow = fx.drone_world().derive(reason="a narrower route", applicability=(
        fx.route_model("synthetic.6dof", "0.9", "wind", "m/s", 4, 6),))
    wide = rebound(narrow, "wind", "gusty", value=q(5, "m/s"), uncertainty=fx.interval(5, 1.5, "m/s"))
    d = check(wide, "simulate_flight", {"thrust_cmd": q(12, "N")})
    assert d.status is F.MISSING_INFORMATION and "APPLICABILITY_UNDECIDED" in codes(d)
    calm = rebound(narrow, "wind", "steady", value=q(5, "m/s"), uncertainty=fx.interval(5, 0.5, "m/s"))
    assert check(calm, "simulate_flight", {"thrust_cmd": q(12, "N")}).feasible


# ---- budget: undeclared is never unlimited, missing cost is never zero ----------------------------------------------------------
def test_undeclared_budget_dimension_and_cost_are_missing_information(battery):
    b = battery.budget
    w = battery.derive(reason="cost declaration dropped",
                       budget=dataclasses.replace(b, unbounded=tuple(x for x in b.unbounded if x[0] != "cost")))
    d = check(w, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    assert d.status is F.MISSING_INFORMATION and "BUDGET_DIMENSION_UNDECLARED" in codes(d)
    nocost = with_action(battery, "pulse", "cost dropped", estimated_cost=())
    assert "COST_NOT_DECLARED" in codes(check(nocost, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))


def test_wall_time_budget_is_checked_against_the_declared_duration():
    hvac = fx.hvac_world("chamber")
    long = with_action(hvac, "mode_change", "a longer run", estimated_duration=q(7, "hour"))
    d = check(long, "mode_change", {"hvac_mode": cat("heat"), "speed": q(3500, "rpm")})
    reason = next(r for r in d.reasons if r.code == "OVER_BUDGET")
    assert reason.subject == "wall_time" and reason.detail["remaining"] == 6 * 3600.0


def test_negative_untyped_or_unitful_costs_are_refused():
    for bad in ({"experiments": IntegerValue(-1)}, {"cost": q(-5, D)}, {"cost": q(5, "percent")},
                {"solver_calls": q(2, "s")}):
        with pytest.raises(WorldRefused):
            fx.action("x", ActionFamily.EXPLORE, ActionMode.OBSERVE, expected_observables=("V",), estimated_cost=bad)


def test_budget_counts_are_ints_and_a_cost_plan_restates_its_spend():
    ref = fx.synthetic("ledger/x")
    for bad in (5.0, 2.7, True):
        with pytest.raises(WorldRefused, match="int"):
            WorldBudget(experiments=bad, observations_spent=0, authority=ref)  # type: ignore[arg-type]
    plan = BudgetPlan(100.0, spent_general=0.0)
    with pytest.raises(WorldRefused, match="restates its spent"):
        WorldBudget(cost=plan, cost_unit="credit", authority=ref)          # an unstated spend would read as zero
    with pytest.raises(WorldRefused, match="restates its spent"):
        WorldBudget(cost=BudgetPlan(100.0, spent_general=30.0), cost_spent=(0.0, 0.0), cost_unit="credit",
                    authority=ref)
    stated = WorldBudget(cost=plan, cost_spent=(0.0, 0.0), cost_unit="credit", authority=ref)
    assert stated.status("cost") == "limited" and WorldBudget.from_dict(stated.to_dict()) == stated
    payload = stated.to_dict()
    del payload["cost"]["spent_general"]
    with pytest.raises(WorldRefused, match="never zero"):
        WorldBudget.from_dict(payload)


# ---- the gate ------------------------------------------------------------------------------------------------------------------------
def gate(w: ScientificWorld, executor, **kw) -> ExecutionGate:
    """A gate over a synthetic fixture world (explicitly allowed) reading live provider builds and the model registry."""
    kw.setdefault("provider_status", lambda pid: fx.live_status(pid, w.provider(pid).version))
    kw.setdefault("model_registry", fx.model_registry(w) if w.applicability else None)
    return ExecutionGate(space(w), executor, allow_synthetic=True, **kw)


def _cleared(w: ScientificWorld, aid: str, assignments, observe=()):
    decision, cleared = space(w).clear(fx.propose(w, aid, assignments, observe))
    assert decision.feasible and cleared is not None
    return cleared


def test_the_gate_dispatches_once_with_the_configuration_it_derives(battery):
    w = fx.fresh(battery, "dispatch-once")
    calls = []
    g = gate(w, calls.append)
    cleared = _cleared(w, "pulse", {"I": q(1000, "mA"), "t_pulse": q(60, "s"), "T_amb": q(77, "degF")}, ("V",))
    g.dispatch(cleared)
    assert len(calls) == 1 and type(calls[0]) is ClearedAction and calls[0] is not cleared
    config = dict(calls[0].configuration)
    assert config["T_amb"] == q(25, "degC") and config["I"] == q(1.0, "A")    # the declared value and declared level
    with pytest.raises(GateRefused, match="DUPLICATE_DISPATCH"):
        g.dispatch(cleared)
    with pytest.raises(GateRefused, match="DUPLICATE_DISPATCH"):
        gate(w, calls.append).dispatch(cleared)                              # one ledger per world revision
    assert len(calls) == 1


def test_the_executor_never_receives_the_callers_objects(battery):
    w = fx.fresh(battery, "callers-objects")
    calls = []
    g = gate(w, calls.append)
    cleared = _cleared(w, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}, ("V",))

    class Shifty(tuple):
        """Serializes as the cleared configuration once, then yields another current."""
        reads = 0

        def __iter__(self):
            Shifty.reads += 1
            return super().__iter__() if Shifty.reads == 1 else iter((("I", q(5, "A")),))

    g.dispatch(dataclasses.replace(cleared, configuration=Shifty(cleared.configuration)))
    assert type(calls[0].configuration) is tuple and dict(calls[0].configuration)["I"] == q(1.0, "A")

    class Lenient(ClearedAction):
        pass

    sub = Lenient(*(getattr(cleared, f.name) for f in dataclasses.fields(ClearedAction)))
    with pytest.raises(GateRefused, match="NOT_CLEARED"):
        g.dispatch(sub)

    class Loud(ProposedAction):
        pass

    loud = object.__new__(Loud)
    for f in dataclasses.fields(ProposedAction):
        object.__setattr__(loud, f.name, getattr(cleared.proposal, f.name))
    with pytest.raises(GateRefused, match="NOT_CLEARED"):
        g.dispatch(dataclasses.replace(cleared, proposal=loud))    # refused before the ledger is read
    assert len(calls) == 1


def test_the_gate_reserves_budget_across_gates_on_one_revision():
    w = fx.fresh(fx.gen1_pool_world().derive(reason="23 of 24 experiments spent",
                                             budget=fx.budget(24, 23, ledger="gen1-pool")), "reserve")
    a = _cleared(w, "pool_query", {"I_A": q(1.0, "A"), "t_on_s": q(30, "s")})
    b = _cleared(w, "pool_query", {"I_A": q(2.0, "A"), "t_on_s": q(30, "s")})
    assert gate(w, lambda c: "ran").dispatch(a) == "ran"
    with pytest.raises(GateRefused, match="OVER_BUDGET_RESERVED"):
        gate(w, lambda c: "ran").dispatch(b)                                 # a second gate sees the reservation
    assert gate(w, lambda c: "ran").reserved() == {"experiments": 1.0}


def test_the_gate_reads_the_live_provider_build(battery):
    w = fx.fresh(battery, "provider")
    cleared = _cleared(w, "simulate_pulse", *fx.base("battery")["simulate_pulse"])
    with pytest.raises(GateRefused, match="PROVIDER_STATUS_UNAVAILABLE"):
        gate(w, lambda c: None, provider_status=None).dispatch(cleared)
    for live in (fx.live_status("sim.ecm", "1.1"), fx.live_status("sim.ecm", "1.0", available=False),
                 dataclasses.replace(fx.live_status("sim.ecm", "1.0"), digest="0" * 64)):
        with pytest.raises(GateRefused, match="PROVIDER_BUILD_MISMATCH"):
            gate(w, lambda c: None, provider_status=lambda pid, live=live: live).dispatch(cleared)
    assert gate(w, lambda c: "ran").dispatch(cleared) == "ran"              # refusals reserved nothing


def test_a_forged_clearance_is_refused(battery):
    w = fx.fresh(battery, "forged")
    bad = fx.propose(w, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")})
    good = _cleared(w, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    g = gate(w, lambda c: None)
    with pytest.raises(GateRefused, match="NOT_REPRODUCED"):
        g.dispatch(dataclasses.replace(good, proposal=bad))
    tampered = dataclasses.replace(good, configuration=good.configuration + (("SOC", q(0.5, D)),))
    with pytest.raises(GateRefused, match="CONFIGURATION_TAMPERED"):
        g.dispatch(tampered)
    with pytest.raises(GateRefused, match="NOT_CLEARED"):
        g.dispatch(good.proposal)  # type: ignore[arg-type]
    other = w.derive(reason="spent", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery"))
    with pytest.raises(GateRefused, match="OTHER_SPACE"):
        gate(other, lambda c: None).dispatch(good)


def test_the_gate_holds_its_own_world_and_detects_tampering(battery):
    w = fx.fresh(battery, "detached")
    cleared = _cleared(w, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    g = gate(w, lambda c: "ran")
    port = MindWorldPort(space(w))
    object.__setattr__(w, "basis", "edited by the caller after the gate was built")
    object.__setattr__(port.world, "basis", "edited through the Mind's port")
    assert g.dispatch(cleared) == "ran"                                      # neither edit reaches the gate's copy
    w2 = fx.fresh(battery, "tampered")
    cleared2 = _cleared(w2, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    g2 = gate(w2, lambda c: "ran")
    object.__setattr__(g2._world, "basis", "edited inside the gate")
    with pytest.raises(GateRefused, match="WORLD_TAMPERED"):
        g2.dispatch(cleared2)


def test_the_gate_refuses_synthetic_worlds_and_unverified_models(battery):
    w = fx.fresh(battery, "refusals")
    with pytest.raises(GateRefused, match="SYNTHETIC_WORLD"):
        ExecutionGate(space(w), lambda c: None, model_registry=fx.model_registry(w))
    with pytest.raises(GateRefused, match="MODELS_UNVERIFIED"):
        gate(w, lambda c: None, model_registry=None)
    with pytest.raises(WorldRefused, match="registered"):
        gate(w, lambda c: None, model_registry=fx.model_registry(fx.hvac_world()))
    with pytest.raises(WorldRefused, match="synthetic fixture"):
        w.verify_bindings({})


# ---- owner records: a recorded (non-synthetic) world ------------------------------------------------------------------------------
def _state(soc: float) -> SystemState:
    spec = InitialStateSpec(q(0, "s"), (OwnerState("cell", "component", (
        InitialStateValue("SOC", q(soc, D), fx.interval(soc, 0.02, D)),)),))
    return SystemState.initial(spec, request_digest=_hex("request"), system_digest=_hex("system"),
                               environment_digest="")


def _measurement(volts: float):
    from engcore.scientific.measurements.calibration import CalibrationCertificate
    from engcore.scientific.measurements.context import ExperimentContext
    from engcore.scientific.measurements.instrument import InstrumentIdentity
    from engcore.scientific.measurements.observation import CalibratedMeasurementObservation
    from engcore.scientific.measurements.traceability import (
        MeasurementTraceabilityChain, TraceabilityKind, TraceabilityReference,
    )
    from engcore.scientific.results.uncertainty import UncertaintySource

    def u(v: float, h: float) -> Uncertainty:
        return Uncertainty(kind="interval", lower=q(v - h, "V"), upper=q(v + h, "V"), method="calibrated meter",
                           source_kind=UncertaintySource.MEASUREMENT)

    meter = InstrumentIdentity("dmm-1", "synthetic", "meter", "sn-1")
    chain = MeasurementTraceabilityChain("chain-1", (
        TraceabilityReference("cert-1", TraceabilityKind.CERTIFICATE, "synthetic lab", _hex("certificate")),
        TraceabilityReference("std-1", TraceabilityKind.REFERENCE_STANDARD, "synthetic lab", _hex("standard"))),
        (("cert-1", "std-1"),))
    calibration = CalibrationCertificate("cal-1", meter, "synthetic lab", _hex("calibration"), "V", q(1, "V"),
                                         u(1, 0.001), "2026-01-01T00:00:00+00:00", "2027-01-01T00:00:00+00:00", chain)
    context = ExperimentContext("ctx-1", _hex("protocol"), _hex("specimen"), {})
    return CalibratedMeasurementObservation("obs-1", "V", q(volts, "V"), u(volts, 0.01), meter, calibration, context,
                                            _hex("raw"), "2026-06-01T00:00:00+00:00", "group-1")


def _recorded_world(soc_fields, v_fields, token: str = "recorded") -> ScientificWorld:
    variables = (
        fx.var("I", R.CONTROLLED_INPUT, "A", TS.PER_SEGMENT, domain=fx.crange("I", "A", -5, 5)),
        fx.var("SOC", R.STATE_VARIABLE, D, TS.STATE_EVOLVING, driven_by=("I",),
               domain=fx.crange("SOC", D, 0, 1, IR.STATE), **soc_fields),
        fx.var("V", R.MEASUREMENT, "V", TS.TIME_SERIES, **v_fields),
    )
    return fx.world(
        f"recorded.cell.{token}", variables,
        actions=(fx.action("pulse", ActionFamily.CHARACTERIZE, ActionMode.INTERVENE,
                           controls=(fx.ctrl("I", fx.levels("A", 1.0, 2.0)),),
                           preconditions=(fx.at_least("soc_floor", "SOC", q(0.1, D)),),
                           expected_observables=("V",), estimated_cost={"experiments": IntegerValue(1)}),),
        channels=(ObservationChannel("V", RecordRef(RecordKind.INSTRUMENT, _hex("voltmeter"))),),
        budget=WorldBudget(experiments=5, observations_spent=0,
                           unbounded={"cost": "no monetary budget", "solver_calls": "no solver is used",
                                      "wall_time": "no wall-time limit"},
                           authority=RecordRef(RecordKind.BUDGET_LEDGER, _hex("ledger"))),
        references=(RecordRef(RecordKind.PROBLEM_SPECIFICATION, _hex("specification")),))


def test_a_recorded_world_executes_only_when_its_bound_values_match_their_owner_records():
    state, obs = _state(0.8), _measurement(3.7)
    soc_fields = binders.from_system_state(state, "SOC", origin=ValueOrigin.ESTIMATED)
    w = _recorded_world(soc_fields, binders.from_measurement(obs))
    records = {state.digest: state, obs.digest: obs}
    assert not w.synthetic and set(w.verify_bindings(records)) == {"SOC", "V"}
    with pytest.raises(WorldRefused, match="not supplied"):
        ExecutionGate(space(w), lambda c: None, records={state.digest: state})
    with pytest.raises(WorldRefused, match="own digest"):
        ExecutionGate(space(w), lambda c: None, records={state.digest: _state(0.7), obs.digest: obs})
    edited = _recorded_world({**soc_fields, "uncertainty": fx.interval(0.8, 0.05, D)}, binders.from_measurement(obs),
                             "edited")
    with pytest.raises(WorldRefused, match="differs from what its owner record states"):
        ExecutionGate(space(edited), lambda c: None, records=records)
    calls = []
    ExecutionGate(space(w), calls.append, records=records).dispatch(_cleared(w, "pulse", {"I": q(1.0, "A")}, ("V",)))
    assert len(calls) == 1


def test_a_bound_value_changes_only_with_its_owner_record():
    state, obs = _state(0.8), _measurement(3.7)
    w = _recorded_world(binders.from_system_state(state, "SOC", origin=ValueOrigin.ESTIMATED),
                        binders.from_measurement(obs))
    with pytest.raises(WorldRefused, match="owner record"):
        with_variable(w, "SOC", "hand edit", value=q(0.81, D))
    later = _state(0.7)
    moved = with_variable(w, "SOC", "the next committed state",
                          **binders.from_system_state(later, "SOC", origin=ValueOrigin.ESTIMATED))
    assert moved.variable("SOC").value == q(0.7, D)
    assert set(moved.verify_bindings({later.digest: later, obs.digest: obs})) == {"SOC", "V"}
    with pytest.raises(WorldRefused, match="cannot be"):
        fx.var("SOC", R.STATE_VARIABLE, D, TS.STATE_EVOLVING, driven_by=("I",),
               **fx.declared(q(0.5, D)))                    # a state's value is never declared
    with pytest.raises(WorldRefused, match="binder is not implemented"):
        binders.read_bound(RecordKind.BELIEF_SNAPSHOT, state, "SOC")


# ---- the Mind port -------------------------------------------------------------------------------------------------------------------
def test_the_port_reaches_no_executor():
    tree = ast.parse(pathlib.Path(world_pkg.__file__).with_name("port.py").read_bytes().decode("utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and ("gate" in m or "provider" in m or "execution" in m) for m in imported)
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not {i for i in identifiers if "gate" in i.lower() or "execut" in i.lower() or "dispatch" in i.lower()}


def test_reading_and_proposing_through_the_port_never_executes(battery):
    w = fx.fresh(battery, "port")
    calls = []
    sp = space(w)
    gate(w, calls.append)                                   # an executor exists, held by its owner only
    port = MindWorldPort(sp)
    assert port.world is not w and port.world.revision_id == w.revision_id
    assert port.action_space is not sp and port.action_space.space_id == sp.space_id
    d = port.propose(fx.propose(w, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")}))
    assert d.status is F.INFEASIBLE_PROTOCOL and calls == [] and len(port.journal) == 1
    assert set(MindWorldPort.__slots__) == {"_space", "_journal"}


# ---- external intake --------------------------------------------------------------------------------------------------------------
def _suggestion(w, point, *, target="pulse", family=None, kind=ProposerKind.LANGUAGE_MODEL, extra=None):
    family = family or w.action(target).family
    extra = {"world_revision": w.revision_id} if extra is None else extra
    return ExternalSuggestion(kind, "llm", "1", family, target, point, "because", extra=extra)


def _assign(**values):
    return [{"variable": k, "value": v.to_dict() if hasattr(v, "to_dict") else v} for k, v in values.items()]


def test_a_language_model_proposal_enters_only_as_a_suggestion_and_meets_the_same_check(battery):
    port = MindWorldPort(space(battery))
    d = port.propose_suggestion(_suggestion(battery, {"assignments": _assign(I=q(1.15, "A"), t_pulse=q(60, "s"))}))
    assert isinstance(d, FeasibilityDecision) and d.status is F.INFEASIBLE_PROTOCOL
    with pytest.raises(WorldRefused, match="ExternalSuggestion"):
        ProposedAction("pulse", battery.revision_id, {"I": q(1.0, "A")}, (),
                       ProposalProvenance(ProposerKind.LANGUAGE_MODEL, "llm"))
    claimed = ProposedAction("pulse", battery.revision_id, {"I": q(1.0, "A"), "t_pulse": q(60, "s")}, (),
                             ProposalProvenance(ProposerKind.LANGUAGE_MODEL, "llm", proposal_digest=_hex("claimed")))
    with pytest.raises(WorldRefused, match="propose_suggestion"):
        port.propose(claimed)                               # the port binds an LLM's provenance itself


def test_a_categorical_suggestion_is_accepted_and_checked(battery):
    point = {"assignments": _assign(mode=cat("discharge"), I=q(-2, "A"), t_pulse=q(30, "s"))}
    d = MindWorldPort(space(battery)).propose_suggestion(_suggestion(battery, point, target="signed_pulse"))
    assert isinstance(d, FeasibilityDecision) and d.feasible


@pytest.mark.parametrize("point, extra, code", [
    ({"assignments": _assign(I=q(1.0, "A")), "feasible": True}, None, IntakeCode.AUTHORITY_KEY),
    ({"assignments": _assign(I=q(1.0, "A")), "confidence": 0.9}, None, IntakeCode.AUTHORITY_KEY),
    ({"assignments": [{"variable": "I", "value": 1.0}]}, None, IntakeCode.NOT_A_TYPED_VALUE),
    ({"assignments": _assign(I=q(1.0, "A")), "note": "x"}, None, IntakeCode.UNKNOWN_KEY),
    ({"assignments": [{"variable": "mode", "value": CategoricalValue("charge", ("charge", "x")).to_dict()}]}, None,
     IntakeCode.MALFORMED),                                 # a proposer cannot attach a vocabulary (a domain claim)
    ({"assignments": _assign(I=q(1.0, "A"))}, {}, IntakeCode.MALFORMED),
    ({"assignments": _assign(I=q(1.0, "A"))}, {"world_revision": "0" * 64}, IntakeCode.STALE_REVISION),
])
def test_intake_refusals_are_structured(battery, point, extra, code):
    port = MindWorldPort(space(battery))
    result = port.propose_suggestion(_suggestion(battery, point, extra=extra))
    assert isinstance(result, IntakeRefusal) and result.code is code
    assert IntakeRefusal.from_dict(result.to_dict()) == result
    assert port.journal[-1] == ("suggestion", result.suggestion_digest, code.value)


def test_a_suggestion_labelled_with_another_family_is_refused(battery):
    point = {"assignments": _assign(I=q(1.0, "A"), t_pulse=q(60, "s"))}
    result = MindWorldPort(space(battery)).propose_suggestion(_suggestion(battery, point,
                                                                          family=ActionFamily.EXPLORE))
    assert isinstance(result, IntakeRefusal) and result.code is IntakeCode.FAMILY_MISMATCH


def test_a_suggestion_is_bound_to_the_ports_own_revision_and_a_stale_proposal_is_refused(battery):
    child = battery.derive(reason="spent", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery"))
    port = MindWorldPort(space(child))
    point = {"assignments": _assign(I=q(1.0, "A"), t_pulse=q(60, "s"))}
    result = port.propose_suggestion(_suggestion(child, point))
    assert isinstance(result, FeasibilityDecision) and result.world_revision == child.revision_id
    stale = port.propose_suggestion(_suggestion(battery, point))
    assert isinstance(stale, IntakeRefusal) and stale.code is IntakeCode.STALE_REVISION
    from engcore.mind.world import StaleProposal
    with pytest.raises(StaleProposal):
        port.propose(fx.propose(battery, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))


def test_forbidden_keys_cover_the_certified_and_gen1_lists():
    from engcore.mind.minimal.structures import _FORBIDDEN_PROPOSAL_KEYS as gen1
    assert set(AUTHORITY_KEYS) <= FORBIDDEN_PROPOSAL_KEYS and set(gen1) <= FORBIDDEN_PROPOSAL_KEYS
    assert {"feasible", "budget", "domain", "levels"} <= FORBIDDEN_PROPOSAL_KEYS
    # a categorical value's own payload carries a (normally empty) vocabulary field; a non-empty one is refused as
    # a value that asserts a domain, not by key
    assert "vocabulary" in cat("x").to_dict() and "vocabulary" not in FORBIDDEN_PROPOSAL_KEYS


def test_a_variable_named_like_a_forbidden_key_still_works_through_intake():
    n = {"I": "status", "t_pulse": "budget"}.get
    w = fx.battery_world(lambda s: n(s) or s)
    d = MindWorldPort(space(w)).propose_suggestion(_suggestion(
        w, {"assignments": [{"variable": "status", "value": q(1.0, "A").to_dict()},
                            {"variable": "budget", "value": q(60, "s").to_dict()}]}))
    assert isinstance(d, FeasibilityDecision) and d.feasible


# ---- replay and identity --------------------------------------------------------------------------------------------------------------
def test_replay_verifies_its_inputs_before_recomputing(battery):
    p = fx.propose(battery, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")})
    d = space(battery).check(p).to_dict()
    assert replay_decision(d, battery.to_dict(), p.to_dict()).outcome is ReplayOutcome.REPRODUCED
    other = fx.propose(battery, "pulse", {"I": q(2.0, "A"), "t_pulse": q(60, "s")})
    r = replay_decision(d, battery.to_dict(), other.to_dict())
    assert r.outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE and "proposal_digest" in r.mismatches
    tampered_world = battery.to_dict()
    tampered_world["basis"] = "edited after the fact"
    assert replay_decision(d, tampered_world, p.to_dict()).outcome is ReplayOutcome.REPLAY_DEPENDENCY_UNAVAILABLE
    forged = dict(d, status="FEASIBLE", reasons=[])
    assert replay_decision(forged, battery.to_dict(), p.to_dict()).outcome is ReplayOutcome.NONDETERMINISM_DETECTED


@pytest.mark.parametrize("name", sorted(fx.WORLDS))
def test_every_fixture_world_round_trips_byte_identically(name):
    w = fx.WORLDS[name]()
    payload = w.to_dict()
    again = ScientificWorld.from_dict(payload)
    assert canonical_bytes(again.to_dict()) == canonical_bytes(payload) and again.revision_id == w.revision_id
    for aid, (a, o) in fx.base(name).items():
        d = check(w, aid, a, o)
        assert FeasibilityDecision.from_dict(d.to_dict()).to_dict() == d.to_dict()


def test_labels_are_not_identity_and_unit_spellings_are_one_value(battery):
    v = battery.variable("I")
    relabelled = dataclasses.replace(battery, variables=tuple(dataclasses.replace(x, label="renamed for humans")
                                                              if x is v else x for x in battery.variables),
                                     description="new words")
    assert relabelled.content_digest == battery.content_digest
    with pytest.raises(WorldRefused, match="no material change"):
        battery.derive(reason="only a label", variables=relabelled.variables)
    pulse = battery.action("pulse")
    in_mA = dataclasses.replace(pulse, controls=tuple(
        dataclasses.replace(c, domain=fx.levels("mA", 1000, 2000)) if c.variable == "I" else c for c in pulse.controls))
    assert in_mA.digest == pulse.digest                       # 1000 mA and 1 A are one level
    with pytest.raises(WorldRefused, match="no material change"):
        battery.derive(reason="levels respelled", actions=tuple(in_mA if a is pulse else a for a in battery.actions))
    widened = dataclasses.replace(pulse, controls=tuple(
        dataclasses.replace(c, domain=fx.levels("A", 1.0, 2.0, 4.0)) if c.variable == "I" else c for c in pulse.controls))
    moved = battery.derive(reason="a third level", actions=tuple(widened if a is pulse else a for a in battery.actions))
    assert moved.revision_id != battery.revision_id and moved.lineage.changed_fields == ("actions",)


def test_lineage_verifies_as_a_chain_and_refuses_forgery(battery):
    a = battery.derive(reason="spent one", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery"))
    b = a.derive(reason="provider down", providers=(fx.provider("sim.ecm", "1.0", available=False),))
    store = {w.revision_id: w for w in (battery, a, b)}
    assert verify_lineage(b, store) == (battery.revision_id, a.revision_id, b.revision_id)
    forged = dataclasses.replace(b, lineage=dataclasses.replace(b.lineage, changed_fields=("budget",)))
    with pytest.raises(WorldRefused, match="changed fields"):
        verify_lineage(forged, store)
    with pytest.raises(WorldRefused, match="parent"):
        verify_lineage(b, {b.revision_id: b})


def test_provider_snapshots_are_the_owner_records_and_bind_together():
    snap = fx.provider("sim.ecm", "1.0")
    other = fx.provider("sim.ecm", "2.0")
    with pytest.raises(WorldRefused, match="status digest"):
        ProviderSnapshot(snap.status, other.report)
    with pytest.raises(TypeError):
        snap.status["version"] = "9"                             # frozen
    for available in (True, False):
        status = fx.live_status("p", "1", available=available)
        for health in ProviderHealth:                            # the owner's rule decides, never a copied table
            report = ProviderHealthReport("p", health, "r", assess_health(status).status_digest)
            assert ProviderSnapshot.from_status(status, report).executable is (available and report.executable)


def test_the_status_by_source_table_is_exhaustive_over_declarable_sources():
    assert set(STATUS_BY_SOURCE) == set(RoleSource) - {RoleSource.LEGACY_ADAPTER_DEFAULT}
    with pytest.raises(WorldRefused, match="legacy"):
        fx.ctrl("I", fx.levels("A", 1.0), RoleSource.LEGACY_ADAPTER_DEFAULT)


def test_a_decision_cannot_be_feasible_without_every_family_or_disagree_with_its_reasons(battery):
    d = check(battery, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    assert d.feasible and {c.family for c in d.checked} == set(CheckFamily)
    with pytest.raises(WorldRefused, match="every check family"):
        dataclasses.replace(d, checked=d.checked[:-1])
    reason = FeasibilityReason(F.MISSING_INFORMATION, "X", CheckFamily.STATE, "s", "m")
    with pytest.raises(WorldRefused, match="disagrees"):
        dataclasses.replace(d, reasons=(reason,))
    bad = check(battery, "pulse", {"I": q(1.15, "A")})
    exported = bad.feasibility_verdicts()
    assert exported and all(not v.feasible for v in exported)
    assert not any("MISSING_INFORMATION" in v.reason for v in exported)


def test_a_feasible_decision_names_the_bound_values_it_relied_on(battery):
    d = check(battery, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    relied = [a for a in d.annotations if "relied_on_bound_values" in a]
    assert relied and "SOC" in {entry["variable"] for entry in relied[0]["relied_on_bound_values"]}


def test_a_system_query_names_no_provider():
    with pytest.raises(WorldRefused):
        fx.action("x", ActionFamily.EXPLORE, ActionMode.OBSERVE, expected_observables=("V",),
                  provider_requirements=(fx.binding("sim.ecm", "1.0"),), estimated_cost=fx.cost(1, 0))


# ---- domains: kinds, units, edges, guards, scope, uncertainty --------------------------------------------------------------------------
def test_offset_units_compare_in_their_ratio_base(battery):
    drone = fx.drone_world()
    assert check(drone, "hover_test", {"thrust_cmd": q(12, "N"), "payload": q(500, "g")}).feasible
    w = fx.gen1_pool_world()
    assert check(w, "pool_query", {"I_A": q(1000, "mA"), "t_on_s": q(0.5, "min")}).feasible
    hvac = fx.hvac_world("chamber")
    assert check(hvac, "step_speed", {"speed": q(3000, "rpm"), "fan_stage": IntegerValue(3),
                                      "T_out": q(95, "degF")}).feasible        # 95 degF is the fixed 35 degC
    # identity precision is 12 significant digits: a value equal to a level at that precision IS that level
    assert check(w, "pool_query", {"I_A": q(1.0000000000004, "A"), "t_on_s": q(30, "s")}).feasible
    assert not check(w, "pool_query", {"I_A": q(1.000000001, "A"), "t_on_s": q(30, "s")}).feasible


def test_continuous_bounds_are_the_owners_exact_check(battery):
    """Level identity rounds to 12 digits; a range bound does not: the owner's require_within_bounds decides."""
    assert check(battery, "signed_pulse", {"mode": cat("charge"), "I": q(5, "A"), "t_pulse": q(30, "s")}).feasible
    d = check(battery, "signed_pulse", {"mode": cat("charge"), "I": q(5.0000000000004, "A"), "t_pulse": q(30, "s")})
    assert "OUTSIDE_RANGE" in codes(d) and not d.feasible


def test_an_integer_domain_in_a_dimensionless_unit_is_searchable():
    percent = ScientificVariable("duty", "percent", VariableKind.INTEGER, IR.CONTROL, q(0, "percent"),
                                 q(100, "percent"))
    assert domain_problem(percent, "duty", "percent") is None
    assert membership(percent, IntegerValue(50)) is None and membership(percent, IntegerValue(101)) is not None


def test_integer_and_categorical_kinds_are_checked_by_kind():
    hvac = fx.hvac_world("chamber")
    assert "OUTSIDE_RANGE" in codes(check(hvac, "step_speed", {"speed": q(3000, "rpm"), "fan_stage": IntegerValue(6)}))
    assert "VALUE_KIND_MISMATCH" in codes(check(hvac, "step_speed", {"speed": q(3000, "rpm"),
                                                                     "fan_stage": q(2.5, D)}))
    d = check(hvac, "mode_change", {"hvac_mode": cat("defrost"), "speed": q(3000, "rpm")})
    assert d.status is F.INFEASIBLE_PROTOCOL and "CATEGORY_NOT_DECLARED" in codes(d)
    assert "VALUE_KIND_MISMATCH" in codes(check(hvac, "mode_change", {"hvac_mode": q(1, D),
                                                                      "speed": q(3000, "rpm")}))


def test_guard_precedence_is_proposal_then_fixed_condition_then_declared_value(battery):
    declared_discharge = with_variable(battery, "mode", "protocol states discharge", value=cat("discharge"),
                                       origin=ValueOrigin.DECLARED, value_basis="protocol states it")
    ok = check(declared_discharge, "signed_pulse", {"mode": cat("charge"), "I": q(2, "A"), "t_pulse": q(30, "s")})
    assert ok.feasible                                         # the proposal's mode wins over the declared one


def test_constraint_scope_is_declared_and_names_resolve_exactly(battery):
    c = battery.constraints[0]
    widened = battery.derive(reason="charge rule for every action",
                             constraints=(dataclasses.replace(c, applies_to=("*",)),) + battery.constraints[1:])
    d = check(widened, "observe_rest", {}, ("V",))
    assert d.status is F.MISSING_INFORMATION and "GUARD_UNRESOLVED" in codes(d)   # observe_rest never states a mode
    with pytest.raises(WorldRefused, match="undeclared"):
        battery.derive(reason="typo", constraints=(dataclasses.replace(
            c, consequence=dataclasses.replace(c.consequence, metric="I_typo")),))
    with pytest.raises(WorldRefused, match="undeclared actions"):
        battery.derive(reason="typo", constraints=(dataclasses.replace(c, applies_to=("pulse_typo",)),))


def test_preconditions_hold_at_the_edges_of_the_current_value(battery):
    point = rebound(battery, "SOC", "a point estimate", uncertainty=Uncertainty(
        kind="standard", standard_uncertainty=q(0.02, D), method="declared"))
    assert "PRECONDITION_UNCERTAINTY_UNKNOWN" in codes(check(point, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))
    straddle = rebound(battery, "SOC", "near the floor", value=q(0.11, D), uncertainty=fx.interval(0.11, 0.02, D))
    assert "PRECONDITION_UNDECIDED" in codes(check(straddle, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}))
    low = rebound(battery, "SOC", "empty", value=q(0.05, D), uncertainty=fx.interval(0.05, 0.01, D))
    assert check(low, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")}).status is F.INFEASIBLE_STATE


def test_a_state_straddling_its_declared_domain_is_undecided(battery):
    """SOC 0.999 +- 0.01 may already be outside its declared [0, 1]: undecided, never assumed inside."""
    edge = rebound(battery, "SOC", "near full", value=q(0.999, D), uncertainty=fx.interval(0.999, 0.01, D))
    d = check(edge, "pulse", {"I": q(1.0, "A"), "t_pulse": q(60, "s")})
    assert d.status is F.MISSING_INFORMATION and "STATE_DOMAIN_UNDECIDED" in codes(d)


def test_alternatives_are_declared_options_never_projections():
    w = fx.gen1_pool_world()
    p = fx.propose(w, "pool_query", {"I_A": q(1.15, "A"), "t_on_s": q(55.62, "s")})
    alt = space(w).alternatives(p, "I_A")
    assert [o.magnitude for o in alt["options"]] == [1.0, 2.0] and "not recommendations" in alt["label"]
    rng = space(w).alternatives(p, "t_on_s")
    assert rng["kind"] == "declared_range" and "options" not in rng
