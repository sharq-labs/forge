"""GEN2-BR1 contract tests: the fail-closed, authority and replay properties the design and authority reviews required.

Each block pins one property of ``engcore.mind.world`` that the failing-first file does not:

* removing information about the system (a value, an uncertainty, a provider, a budget statement, a cost, a fixed
  condition, a control's value) never turns a non-FEASIBLE decision FEASIBLE;
* model applicability gates model execution only, through the core assessment, with its status verbatim; the world's
  own interval rule is sound, never applied to a screen or a condition with prerequisites, and carries its own code;
* an undeclared budget dimension or cost is MISSING_INFORMATION, never unlimited or zero; budgets are decided by the
  owners' rules on raw amounts, and a budget statement changes only with its owner record;
* a FEASIBLE decision yields a closed admitted-action record built from the canonical proposal, carrying every value
  the decision read; nothing in the package dispatches;
* bound values verify against exactly-typed owner records (supersession, measured quantity), and change only with
  their record, in derive and in lineage verification;
* the Mind port holds a detached copy and reaches no executor; an external proposal is re-derived from its certified
  suggestion by the check itself (revision, family, provenance);
* units are the owner's conversions (a temperature difference is not a temperature); identity is the raw owner payload;
* reason codes and annotation keys are closed; replay verifies its inputs before recomputing.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import pathlib
import types

import pytest

import engcore.mind.world as world_pkg
from benchmarks.mind_gen2_world_v1 import fixtures as fx
from engcore.execution.orchestration.resources import ResourceBudget, ResourceUsage
from engcore.mind.repsem import canonical_bytes
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, CheckFamily, ClearedAction, FeasibilityDecision, FeasibilityStatus as F, FeasibleActionSpace,
    FORBIDDEN_PROPOSAL_KEYS, IntakeCode, IntakeRefusal, Lineage, MindWorldPort, ObservationChannel, ProposalRefused,
    ProposedAction, RecordKind, RecordRef, ScientificWorld, StaleProposal, TemporalSemantics as TS, ValueOrigin,
    WorldBudget, WorldRefused, binders, proposed_action_from_suggestion, replay_decision, verify_lineage,
)
from engcore.mind.world.domains import DiscreteLevels, domain_problem, membership
from engcore.mind.world.feasibility import STATUS_BY_SOURCE, FeasibilityReason
from engcore.mind.world.world import ApplicabilityBinding, ProviderSnapshot
from engcore.providers.health import ProviderHealth, ProviderHealthReport, assess_health
from engcore.scientific import (
    ConstraintDefinition, ConstraintOperator as Op, RangeCondition, ScientificModelDefinition, ScientificVariable,
    Uncertainty, ValidityDomain, VariableKind, VariableRole as IR,
)
from engcore.scientific.ir.values import CategoricalValue, IntegerValue
from engcore.scientific.models.definition import InputSourceKind, ModelInputSpec
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


def restated_budget(b: WorldBudget, token: str, **changes) -> WorldBudget:
    """A budget as the owner's newer statement gives it (a new ledger record)."""
    return dataclasses.replace(b, authority=fx.synthetic(f"ledger/{token}"), **changes)


def _hex(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@pytest.fixture(scope="module")
def battery():
    return fx.battery_world()


PULSE_OK = {"I": q(1.0, "A"), "t_pulse": q(60, "s")}


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
    """Removals of information about the system: every one must leave a non-FEASIBLE decision non-FEASIBLE."""
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
        yield f"undeclare {dim}", lambda w=w, d=dim: w.derive(reason="declaration dropped", budget=restated_budget(
            w.budget, f"undeclared-{d}", unbounded=tuple(x for x in w.budget.unbounded if x[0] != d)))
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


def _hvac_with_guarded_room_constraint():
    """T_room declared [10, 40] degC and read only by a constraint in force when hvac_mode is heat."""
    hvac = fx.hvac_world("chamber")
    hvac = with_variable(hvac, "T_room", "a declared range", domain=fx.crange("T_room", "degC", 10, 40, IR.OBSERVABLE))
    room = fx.DeclaredConstraint("heat_room_cap", fx.at_most("heat_room_cap", "T_room", q(30, "degC")),
                                 fx.when("hvac_mode", "heat"), ("mode_change",), fx.P, "synthetic: heating stops at 30")
    return hvac.derive(reason="a guarded room limit", constraints=hvac.constraints + (room,))


def test_a_value_read_only_by_a_constraint_not_in_force_is_not_used():
    hvac = _hvac_with_guarded_room_constraint()
    cool = {"hvac_mode": cat("cool"), "speed": q(3000, "rpm")}
    heat = {"hvac_mode": cat("heat"), "speed": q(3500, "rpm")}
    blurred = rebound(hvac, "T_room", "uncertainty lost", uncertainty=Uncertainty.unknown("lost"))
    withdrawn = with_variable(hvac, "T_room", "withdrawn", value=None, origin=None, source=None,
                              uncertainty=Uncertainty.unknown("withdrawn"))
    for w in (hvac, blurred, withdrawn):
        assert check(w, "mode_change", cool).feasible                   # the constraint is not in force
    assert check(hvac, "mode_change", heat).feasible
    assert check(blurred, "mode_change", heat).status is F.MISSING_INFORMATION
    assert "CONSTRAINT_UNRESOLVED" in codes(check(withdrawn, "mode_change", heat))
    hot = rebound(hvac, "T_room", "too hot", value=q(45, "degC"), uncertainty=fx.interval(45, 0.2, "degC"))
    d = check(hot, "mode_change", heat)                     # outside its range, and above the 30 degC limit
    assert d.status is F.INFEASIBLE_PROTOCOL and {"STATE_OUTSIDE_DECLARED_DOMAIN", "CONSTRAINT_VIOLATED"} <= codes(d)
    gone = with_variable(hot, "T_room", "withdrawn", value=None, origin=None, source=None,
                         uncertainty=Uncertainty.unknown("withdrawn"))
    assert check(gone, "mode_change", heat).status is F.MISSING_INFORMATION   # withdrawing never helps


# ---- applicability gates model execution only ---------------------------------------------------------------------------------
def test_s9_outside_the_route_models_domain_is_infeasible_applicability_with_the_core_status(battery):
    d = check(battery, "simulate_pulse", {"I": q(2, "A"), "T_amb": q(80, "degC"), "t_pulse": q(60, "s")})
    assert d.status is F.INFEASIBLE_APPLICABILITY
    r = next(r for r in d.reasons if r.code == "OUTSIDE_VALIDATED_DOMAIN")
    assert r.detail["validity_status"] == "outside_validated_domain" and list(r.detail["violated"]) == ["T_amb"]
    assert d.annotations[0]["core_status"] == "outside_validated_domain" and d.annotations[0]["interval_rule"] is None
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
    d = check(windy, "simulate_flight", {"thrust_cmd": q(12, "N")})
    assert d.status is F.INFEASIBLE_APPLICABILITY and codes(d) == {"INTERVAL_OUTSIDE_VALIDATED_DOMAIN"}
    assert d.annotations[0]["interval_rule"] == "outside_whole_interval" and d.annotations[0]["core_status"] is None


def test_applicability_holds_at_both_edges_of_an_interval():
    """An interval wider than the route on BOTH sides is undecided, not outside: each side is decided on its own."""
    narrow = fx.drone_world().derive(reason="a narrower route", applicability=(
        fx.route_model("synthetic.6dof", "0.9", "wind", "m/s", 4, 6),))
    wide = rebound(narrow, "wind", "gusty", value=q(5, "m/s"), uncertainty=fx.interval(5, 1.5, "m/s"))
    d = check(wide, "simulate_flight", {"thrust_cmd": q(12, "N")})
    assert d.status is F.MISSING_INFORMATION and "APPLICABILITY_UNDECIDED" in codes(d)
    calm = rebound(narrow, "wind", "steady", value=q(5, "m/s"), uncertainty=fx.interval(5, 0.5, "m/s"))
    assert check(calm, "simulate_flight", {"thrust_cmd": q(12, "N")}).feasible


def _route(*conditions, inputs=("wind",), units=("m/s",)) -> ApplicabilityBinding:
    return ApplicabilityBinding(ScientificModelDefinition(
        "synthetic.6dof", "0.9",
        inputs=tuple(ModelInputSpec(n, InputSourceKind.VARIABLE, unit_exemplar=u) for n, u in zip(inputs, units)),
        exclusions=(), excludes_nothing_because="a synthetic contract fixture model excludes nothing it declares",
        validity=ValidityDomain(tuple(conditions))))


def test_a_screen_or_a_prerequisite_is_never_turned_into_a_definite_outside():
    """Outside a conservative screen is an evidence gap (the core says UNKNOWN), and a condition with prerequisites is
    the core's to combine: the world's interval rule never applies to either."""
    drone = fx.drone_world()
    windy = lambda w: rebound(w, "wind", "storm", value=q(15, "m/s"), uncertainty=fx.interval(15, 0.5, "m/s"))
    screened = windy(drone.derive(reason="a screen", applicability=(
        _route(RangeCondition("wind", minimum=q(0, "m/s"), maximum=q(12, "m/s"), conservative_screen=True)),)))
    d = check(screened, "simulate_flight", {"thrust_cmd": q(12, "N")})
    assert d.status is F.MISSING_INFORMATION and "APPLICABILITY_UNKNOWN" in codes(d)
    dependent = windy(drone.derive(reason="a prerequisite", applicability=(_route(
        RangeCondition("wind", minimum=q(0, "m/s"), maximum=q(12, "m/s"), requires=("altitude",)),
        RangeCondition("altitude", minimum=q(0, "m"), maximum=q(100, "m")),
        inputs=("wind", "altitude"), units=("m/s", "m")),)))
    d = check(dependent, "simulate_flight", {"thrust_cmd": q(12, "N")})
    assert d.status is F.MISSING_INFORMATION and "INTERVAL_OUTSIDE_VALIDATED_DOMAIN" not in codes(d)


# ---- budget: undeclared is never unlimited, missing cost is never zero, raw amounts, owner statements -------------------------
def test_undeclared_budget_dimension_and_cost_are_missing_information(battery):
    b = battery.budget
    w = battery.derive(reason="cost declaration dropped", budget=restated_budget(
        b, "battery/no-cost", unbounded=tuple(x for x in b.unbounded if x[0] != "cost")))
    d = check(w, "pulse", PULSE_OK)
    assert d.status is F.MISSING_INFORMATION and "BUDGET_DIMENSION_UNDECLARED" in codes(d)
    nocost = with_action(battery, "pulse", "cost dropped", estimated_cost=())
    assert "COST_NOT_DECLARED" in codes(check(nocost, "pulse", PULSE_OK))


def test_wall_time_budget_is_checked_against_the_declared_duration():
    hvac = fx.hvac_world("chamber")
    long = with_action(hvac, "mode_change", "a longer run", estimated_duration=q(7, "hour"))
    d = check(long, "mode_change", {"hvac_mode": cat("heat"), "speed": q(3500, "rpm")})
    reason = next(r for r in d.reasons if r.code == "OVER_BUDGET")
    assert reason.subject == "wall_time" and reason.detail["remaining"] == 6 * 3600.0


def test_budgets_are_decided_by_the_owners_rules_on_raw_amounts(battery):
    hvac = fx.hvac_world("chamber")                          # 6 h of wall time remain
    exact = with_action(hvac, "mode_change", "exactly what remains", estimated_duration=q(21600, "s"))
    over = with_action(hvac, "mode_change", "a hair more", estimated_duration=q(21600.0000000004, "s"))
    heat = {"hvac_mode": cat("heat"), "speed": q(3500, "rpm")}
    assert check(exact, "mode_change", heat).feasible
    assert "OVER_BUDGET" in codes(check(over, "mode_change", heat))
    priced = battery.derive(reason="a cost budget", budget=restated_budget(
        battery.budget, "battery/priced", cost=BudgetPlan(100.0), cost_spent=(0.0, 0.0), cost_unit="credit",
        unbounded=tuple(x for x in battery.budget.unbounded if x[0] != "cost")))
    for amount, ok in ((100.0, True), (100.0000000004, False)):
        w = with_action(priced, "pulse", "priced", estimated_cost={**fx.cost(1, 0), "cost": q(amount, D)})
        assert check(w, "pulse", PULSE_OK).feasible is ok


def test_negative_untyped_or_unitful_costs_are_refused():
    for bad in ({"experiments": IntegerValue(-1)}, {"cost": q(-5, D)}, {"cost": q(5, "percent")},
                {"solver_calls": q(2, "s")}):
        with pytest.raises(WorldRefused):
            fx.action("x", ActionFamily.EXPLORE, ActionMode.OBSERVE, expected_observables=("V",), estimated_cost=bad)


def test_budget_statements_are_explicit_typed_and_cited():
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
    solver = ResourceBudget(max_function_evaluations=10)
    with pytest.raises(WorldRefused, match="restates its usage"):
        WorldBudget(compute=solver, compute_used=ResourceUsage(function_evaluations=4), authority=ref)
    assert WorldBudget(compute=solver, compute_used=ResourceUsage(function_evaluations=4), compute_spent=(0.0, 4),
                       authority=ref).remaining("solver_calls") == 6
    with pytest.raises(WorldRefused, match="cites the owner record"):
        WorldBudget(unbounded={"cost": "no monetary budget"})                 # a declaration is the owner's too


def test_a_budget_statement_changes_only_with_its_owner_record(battery):
    with pytest.raises(WorldRefused, match="owner's statement"):
        battery.derive(reason="spent", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery"))
    child = battery.derive(reason="spent", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery/2"))
    assert child.budget.remaining("experiments") == 16
    forged = dataclasses.replace(child, budget=fx.budget(20, 0, solver=(10, 4), ledger="battery/2"))
    with pytest.raises(WorldRefused, match="owner's statement"):
        verify_lineage(dataclasses.replace(forged, lineage=Lineage(2, child.revision_id, "edited", ("budget",))),
                       {w.revision_id: w for w in (battery, child)})


# ---- the admitted-action record -------------------------------------------------------------------------------------------------
def _cleared(w: ScientificWorld, aid: str, assignments, observe=()):
    decision, cleared = space(w).clear(fx.propose(w, aid, assignments, observe))
    assert decision.feasible and type(cleared) is ClearedAction
    return cleared


def test_clearing_yields_a_closed_record_of_the_canonical_proposal(battery):
    cleared = _cleared(battery, "pulse", {"I": q(1000, "mA"), "t_pulse": q(60, "s"), "T_amb": q(77, "degF")}, ("V",))
    config = dict(cleared.configuration)
    assert config["I"] == q(1.0, "A") and config["T_amb"] == q(25, "degC")     # declared level, declared value
    assert cleared.decision.proposal_digest == cleared.proposal.digest and cleared.world_revision == battery.revision_id
    context = {c["variable"]: c for c in cleared.context}
    assert context["SOC"]["source"]["ref"] == "synthetic:coulomb-count/run-0" and "mode" in config
    assert cleared.to_dict()["classification"] == "action_feasibility_not_scientific_support"
    d, none = space(battery).clear(fx.propose(battery, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")}))
    assert none is None and not d.feasible
    with pytest.raises(WorldRefused, match="clears"):
        ClearedAction.of(space(battery), cleared.proposal, d)


def test_a_record_is_never_built_from_a_view_the_check_did_not_see(battery):
    class Loud(ProposedAction):
        pass

    honest = fx.propose(battery, "pulse", PULSE_OK)
    loud = object.__new__(Loud)
    for f in dataclasses.fields(ProposedAction):
        object.__setattr__(loud, f.name, getattr(honest, f.name))
    with pytest.raises(WorldRefused, match="exact ProposedAction"):
        space(battery).clear(loud)

    class Shifty(tuple):
        """Reads as the honest assignments once, then as an off-protocol current."""
        reads = 0

        def __iter__(self):
            Shifty.reads += 1
            return super().__iter__() if Shifty.reads == 1 else iter((("I", q(5, "A")), ("t_pulse", q(9999, "s"))))

    shifty = fx.propose(battery, "pulse", PULSE_OK)
    object.__setattr__(shifty, "assignments", Shifty(shifty.assignments))
    decision, cleared = space(battery).clear(shifty)
    assert decision.feasible and dict(cleared.configuration)["t_pulse"] == q(60, "s")
    assert cleared.proposal.digest == decision.proposal_digest


def test_two_worlds_that_differ_in_a_model_input_give_different_records():
    """The drone's model reads the measured wind, which no control sets: the record carries it, bound to its record."""
    calm = fx.drone_world()
    breezy = rebound(calm, "wind", "breezier", value=q(6, "m/s"), uncertainty=fx.interval(6, 0.5, "m/s"))
    a = _cleared(calm, "simulate_flight", {"thrust_cmd": q(12, "N")}, ("altitude",))
    b = _cleared(breezy, "simulate_flight", {"thrust_cmd": q(12, "N")}, ("altitude",))
    assert a.configuration == b.configuration and a.digest != b.digest
    wind = {c["variable"]: c for c in b.context}["wind"]
    assert wind["value"]["magnitude"] == 6.0 and wind["source"]["ref"].startswith("synthetic:rebound/wind")


def test_nothing_in_the_world_package_dispatches_or_holds_an_executor():
    assert not (pathlib.Path(world_pkg.__file__).parent / "gate.py").exists()
    for path in pathlib.Path(world_pkg.__file__).parent.glob("*.py"):
        tree = ast.parse(path.read_bytes().decode("utf-8"))
        identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
            n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))} | {
            a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args + n.kwonlyargs}
        assert not {i for i in identifiers if "dispatch" in i.lower() or "executor" in i.lower()}, path.name


# ---- owner records: a recorded (non-synthetic) world ------------------------------------------------------------------------------
def _state(soc: float) -> SystemState:
    spec = InitialStateSpec(q(0, "s"), (OwnerState("cell", "component", (
        InitialStateValue("SOC", q(soc, D), fx.interval(soc, 0.02, D)),)),))
    return SystemState.initial(spec, request_digest=_hex("request"), system_digest=_hex("system"),
                               environment_digest="")


def _next_state(state: SystemState, soc: float) -> SystemState:
    return state.advance(time=q(60, "s"), produced_by="step", updates=(OwnerState("cell", "component", (
        InitialStateValue("SOC", q(soc, D), fx.interval(soc, 0.02, D)),)),))


def _measurement(volts: float, quantity: str = "V"):
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
    calibration = CalibrationCertificate("cal-1", meter, "synthetic lab", _hex("calibration"), quantity, q(1, "V"),
                                         u(1, 0.001), "2026-01-01T00:00:00+00:00", "2027-01-01T00:00:00+00:00", chain)
    context = ExperimentContext("ctx-1", _hex("protocol"), _hex("specimen"), {})
    return CalibratedMeasurementObservation("obs-1", quantity, q(volts, "V"), u(volts, 0.01), meter, calibration,
                                            context, _hex("raw"), "2026-06-01T00:00:00+00:00", "group-1")


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


def test_bound_values_verify_against_exactly_typed_owner_records():
    state, obs = _state(0.8), _measurement(3.7)
    soc_fields = binders.from_system_state(state, "SOC", origin=ValueOrigin.ESTIMATED)
    w = _recorded_world(soc_fields, binders.from_measurement(obs, "V"))
    records = {state.digest: state, obs.digest: obs}
    assert not w.synthetic and set(w.verify_bindings(records)) == {"SOC", "V"}
    with pytest.raises(WorldRefused, match="not supplied"):
        w.verify_bindings({state.digest: state})
    with pytest.raises(WorldRefused, match="own digest"):
        w.verify_bindings({state.digest: _state(0.7), obs.digest: obs})
    lookalike = types.SimpleNamespace(digest=state.digest, owners=state.owners, previous_digest="")
    with pytest.raises(WorldRefused, match="reads exactly a SystemState"):
        w.verify_bindings({state.digest: lookalike, obs.digest: obs})
    edited = _recorded_world({**soc_fields, "uncertainty": fx.interval(0.8, 0.05, D)},
                             binders.from_measurement(obs, "V"), "edited")
    with pytest.raises(WorldRefused, match="differs from what its owner record states"):
        edited.verify_bindings(records)
    with pytest.raises(WorldRefused, match="synthetic fixture"):
        fx.battery_world().verify_bindings({})


def test_a_superseded_state_or_another_quantity_never_verifies():
    state, obs = _state(0.8), _measurement(3.7)
    w = _recorded_world(binders.from_system_state(state, "SOC", origin=ValueOrigin.ESTIMATED),
                        binders.from_measurement(obs, "V"))
    later = _next_state(state, 0.05)
    with pytest.raises(WorldRefused, match="superseded"):
        w.verify_bindings({state.digest: state, later.digest: later, obs.digest: obs})
    humidity = _measurement(3.7, quantity="relative_humidity")
    with pytest.raises(WorldRefused, match="measured 'relative_humidity'"):
        binders.from_measurement(humidity, "V")
    forged = _recorded_world(binders.from_system_state(state, "SOC", origin=ValueOrigin.ESTIMATED),
                             {**binders.from_measurement(obs, "V"),
                              "source": RecordRef(RecordKind.MEASUREMENT_OBSERVATION, humidity.digest)}, "forged")
    with pytest.raises(WorldRefused, match="measured 'relative_humidity'"):
        forged.verify_bindings({state.digest: state, humidity.digest: humidity})


def test_a_bound_value_changes_only_with_its_owner_record_in_derive_and_in_lineage():
    state, obs = _state(0.8), _measurement(3.7)
    w = _recorded_world(binders.from_system_state(state, "SOC", origin=ValueOrigin.ESTIMATED),
                        binders.from_measurement(obs, "V"))
    with pytest.raises(WorldRefused, match="owner record"):
        with_variable(w, "SOC", "hand edit", value=q(0.81, D))
    later = _next_state(state, 0.7)
    moved = with_variable(w, "SOC", "the next committed state",
                          **binders.from_system_state(later, "SOC", origin=ValueOrigin.ESTIMATED))
    assert moved.variable("SOC").value == q(0.7, D)
    assert set(moved.verify_bindings({later.digest: later, obs.digest: obs})) == {"SOC", "V"}
    declared_range = with_variable(w, "SOC", "a narrower declared range", domain=fx.crange("SOC", D, 0.05, 0.95, IR.STATE))
    assert declared_range.lineage.changed_fields == ("variables",)               # a declaration may change
    hand = dataclasses.replace(w, variables=tuple(dataclasses.replace(v, value=q(0.81, D)) if v.name == "SOC" else v
                                                 for v in w.variables),
                               lineage=Lineage(1, w.revision_id, "hand-built", ("variables",)))
    with pytest.raises(WorldRefused, match="owner record"):
        verify_lineage(hand, {w.revision_id: w})
    with pytest.raises(WorldRefused, match="cannot be"):
        fx.var("SOC", R.STATE_VARIABLE, D, TS.STATE_EVOLVING, driven_by=("I",),
               **fx.declared(q(0.5, D)))                    # a state's value is never declared
    with pytest.raises(WorldRefused, match="binder is not implemented"):
        binders.read_bound(RecordKind.BELIEF_SNAPSHOT, state, "SOC")


def test_a_declared_value_is_exact_only_for_a_set_point(battery):
    """A DECLARED latent value (not a set point) decides nothing a bound value with unknown uncertainty could not."""
    chem = fx.var("chem", R.LATENT_PARAMETER, D, TS.TIME_INVARIANT, domain=fx.cats("chem", "lfp", "nmc"),
                  **fx.declared(cat("lfp")))
    w = battery.derive(reason="a declared chemistry", variables=battery.variables + (chem,))
    pulse = w.action("pulse")
    guarded = dataclasses.replace(pulse, controls=tuple(
        dataclasses.replace(c, active_when=fx.Guard("chem", (cat("lfp"),))) if c.variable == "t_pulse" else c
        for c in pulse.controls))
    w = w.derive(reason="t_pulse only for one chemistry", actions=tuple(guarded if a is pulse else a for a in w.actions))
    d = check(w, "pulse", PULSE_OK)
    assert d.status is F.MISSING_INFORMATION and "GUARD_UNRESOLVED" in codes(d)


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


def test_the_port_holds_a_detached_copy(battery):
    sp = space(battery)
    port = MindWorldPort(sp)
    assert port.world is not battery and port.world.revision_id == battery.revision_id
    assert port.action_space is not sp and port.action_space.space_id == sp.space_id
    d = port.propose(fx.propose(battery, "pulse", {"I": q(1.15, "A"), "t_pulse": q(60, "s")}))
    assert d.status is F.INFEASIBLE_PROTOCOL and len(port.journal) == 1
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
                       ProposalProvenance(ProposerKind.LANGUAGE_MODEL, "llm", proposal_digest=_hex("claimed")))


def test_the_check_rederives_a_sourced_proposal_from_its_suggestion(battery):
    """Provenance, revision and family are verified by the check itself, so no route around the port helps."""
    sug = _suggestion(battery, {"assignments": _assign(I=q(1.15, "A"), t_pulse=q(60, "s"))})
    honest = proposed_action_from_suggestion(sug, world=battery)
    assert isinstance(honest, ProposedAction) and honest.source == sug
    assert ProposedAction.from_dict(honest.to_dict()) == honest
    swapped = dataclasses.replace(honest, assignments=(("I", q(1.0, "A")), ("t_pulse", q(60, "s"))))
    with pytest.raises(ProposalRefused, match="not what its source suggestion yields"):
        space(battery).check(swapped)
    with pytest.raises(ProposalRefused):
        space(battery).clear(swapped)
    with pytest.raises(WorldRefused, match="propose_suggestion"):
        MindWorldPort(space(battery)).propose(swapped)
    explore = _suggestion(battery, {"assignments": _assign(I=q(1.0, "A"), t_pulse=q(60, "s"))},
                          family=ActionFamily.EXPLORE)
    mislabelled = ProposedAction("pulse", battery.revision_id, {"I": q(1.0, "A"), "t_pulse": q(60, "s")}, (),
                                 ProposalProvenance(ProposerKind.LANGUAGE_MODEL, "llm@1", proposal_digest=explore.digest),
                                 "because", explore)
    with pytest.raises(ProposalRefused, match="FAMILY_MISMATCH"):
        space(battery).check(mislabelled)
    with pytest.raises(WorldRefused, match="provenance"):
        dataclasses.replace(honest, proposer=ProposalProvenance(ProposerKind.HUMAN, "llm@1",
                                                                proposal_digest=sug.digest))
    p = honest
    d = space(battery).check(p).to_dict()
    assert replay_decision(d, battery.to_dict(), p.to_dict()).outcome is ReplayOutcome.REPRODUCED


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
    ({"assignments": _assign(I=q(1.0, "A"))}, {"world_revision": "WORLD", "approved": True}, IntakeCode.UNKNOWN_KEY),
])
def test_intake_refusals_are_structured(battery, point, extra, code):
    if extra is not None and extra.get("world_revision") == "WORLD":
        extra = {**extra, "world_revision": battery.revision_id}
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
    child = battery.derive(reason="spent", budget=fx.budget(20, 4, solver=(10, 4), ledger="battery/2"))
    port = MindWorldPort(space(child))
    point = {"assignments": _assign(I=q(1.0, "A"), t_pulse=q(60, "s"))}
    result = port.propose_suggestion(_suggestion(child, point))
    assert isinstance(result, FeasibilityDecision) and result.world_revision == child.revision_id
    stale = port.propose_suggestion(_suggestion(battery, point))
    assert isinstance(stale, IntakeRefusal) and stale.code is IntakeCode.STALE_REVISION
    with pytest.raises(StaleProposal):
        port.propose(fx.propose(battery, "pulse", PULSE_OK))


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


# ---- closed vocabulary, replay and identity -------------------------------------------------------------------------------------
def test_reason_codes_and_annotation_keys_are_closed(battery):
    with pytest.raises(WorldRefused, match="closed"):
        FeasibilityReason(F.INFEASIBLE_DOMAIN, "REFUTED", CheckFamily.DOMAIN, "I", "hypothesis refuted")
    d = check(battery, "pulse", PULSE_OK).to_dict()
    with pytest.raises(WorldRefused, match="closed set"):
        FeasibilityDecision.from_dict({**d, "annotations": d["annotations"] + [{"verdict": "SUPPORTED"}]})
    words = {"verdict", "supported", "refused", "admission", "admitted", "truth", "hypothesis", "outcome"}
    for name in fx.WORLDS:
        w = fx.WORLDS[name]()
        for aid, (a, o) in fx.base(name).items():
            for item in check(w, aid, a, o).to_dict()["annotations"]:
                assert not words & set(item), (name, aid, item)


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


def test_identity_is_the_raw_owner_payload(battery):
    """Labels are not identity.  Anything a check or an execution can see is: a 13th-digit bound, a respelled level."""
    v = battery.variable("I")
    relabelled = dataclasses.replace(battery, variables=tuple(dataclasses.replace(x, label="renamed for humans")
                                                              if x is v else x for x in battery.variables),
                                     description="new words")
    assert relabelled.content_digest == battery.content_digest
    with pytest.raises(WorldRefused, match="no material change"):
        battery.derive(reason="only a label", variables=relabelled.variables)
    signed = battery.action("signed_pulse")
    nudged = dataclasses.replace(signed, controls=tuple(
        dataclasses.replace(c, domain=fx.crange("I", "A", -5, 4.9999999999996)) if c.variable == "I" else c
        for c in signed.controls))
    near = battery.derive(reason="a 13th-digit bound", actions=tuple(nudged if a is signed else a for a in battery.actions))
    assert near.revision_id != battery.revision_id
    probe = {"mode": cat("charge"), "I": q(4.9999999999998, "A"), "t_pulse": q(30, "s")}
    assert check(battery, "signed_pulse", probe).feasible and not check(near, "signed_pulse", probe).feasible
    pulse = battery.action("pulse")
    in_mA = dataclasses.replace(pulse, controls=tuple(
        dataclasses.replace(c, domain=fx.levels("mA", 1000, 2000)) if c.variable == "I" else c for c in pulse.controls))
    respelled = battery.derive(reason="levels respelled", actions=tuple(in_mA if a is pulse else a for a in battery.actions))
    assert respelled.revision_id != battery.revision_id and respelled.lineage.changed_fields == ("actions",)
    assert dict(_cleared(respelled, "pulse", PULSE_OK).configuration)["I"] == q(1000, "mA")   # the declared level


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


def test_models_verify_against_the_registry(battery):
    assert battery.verify_models(fx.model_registry(battery)) == (battery.applicability[0].binding_id,)
    with pytest.raises(WorldRefused, match="registered"):
        battery.verify_models(fx.model_registry(fx.hvac_world()))


def test_the_status_by_source_table_is_exhaustive_over_declarable_sources():
    assert set(STATUS_BY_SOURCE) == set(RoleSource) - {RoleSource.LEGACY_ADAPTER_DEFAULT}
    with pytest.raises(WorldRefused, match="legacy"):
        fx.ctrl("I", fx.levels("A", 1.0), RoleSource.LEGACY_ADAPTER_DEFAULT)


def test_a_decision_cannot_be_feasible_without_every_family_or_disagree_with_its_reasons(battery):
    d = check(battery, "pulse", PULSE_OK)
    assert d.feasible and {c.family for c in d.checked} == set(CheckFamily)
    with pytest.raises(WorldRefused, match="every check family"):
        dataclasses.replace(d, checked=d.checked[:-1])
    reason = FeasibilityReason(F.MISSING_INFORMATION, "PRECONDITION_UNRESOLVED", CheckFamily.STATE, "s", "m")
    with pytest.raises(WorldRefused, match="disagrees"):
        dataclasses.replace(d, reasons=(reason,))
    bad = check(battery, "pulse", {"I": q(1.15, "A")})
    exported = bad.feasibility_verdicts()
    assert exported and all(not v.feasible for v in exported)
    assert not any("MISSING_INFORMATION" in v.reason for v in exported)


def test_a_feasible_decision_names_the_bound_values_it_relied_on(battery):
    d = check(battery, "pulse", PULSE_OK)
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
    # level matching is at 12 significant digits: a value equal to a level at that precision IS that level
    assert check(w, "pool_query", {"I_A": q(1.0000000000004, "A"), "t_on_s": q(30, "s")}).feasible
    assert not check(w, "pool_query", {"I_A": q(1.000000001, "A"), "t_on_s": q(30, "s")}).feasible


def test_a_temperature_difference_is_never_a_temperature(battery):
    restated = check(battery, "pulse", {**PULSE_OK, "T_amb": q(298.15, "delta_degC")})
    assert restated.status is F.INFEASIBLE_PROTOCOL and "FIXED_CONDITION_CHANGED" in codes(restated)
    d = check(battery, "simulate_pulse", {"I": q(2, "A"), "T_amb": q(298.15, "delta_degC"), "t_pulse": q(60, "s")})
    assert d.status is F.INFEASIBLE_DOMAIN and "UNIT_INCOMPATIBLE" in codes(d)
    with pytest.raises(WorldRefused, match="convert"):
        DiscreteLevels("degC", (q(298.15, "delta_degC"),))
    pulse = battery.action("pulse")
    delta_fixed = dataclasses.replace(pulse, fixed_conditions=tuple(
        fx.fixed("T_amb", q(298.15, "delta_degC")) if f.name == "T_amb" else f for f in pulse.fixed_conditions))
    with pytest.raises(WorldRefused, match="convert"):
        battery.derive(reason="a delta set point", actions=tuple(delta_fixed if a is pulse else a for a in battery.actions))


def test_continuous_bounds_are_the_owners_exact_check(battery):
    """Level matching rounds to 12 digits; a range bound does not: the owner's require_within_bounds decides."""
    assert check(battery, "signed_pulse", {"mode": cat("charge"), "I": q(5, "A"), "t_pulse": q(30, "s")}).feasible
    d = check(battery, "signed_pulse", {"mode": cat("charge"), "I": q(5.0000000000004, "A"), "t_pulse": q(30, "s")})
    assert "OUTSIDE_RANGE" in codes(d) and not d.feasible


def test_an_integer_domain_is_stated_in_its_variables_own_unit():
    percent = ScientificVariable("duty", "percent", VariableKind.INTEGER, IR.CONTROL, q(0, "percent"),
                                 q(100, "percent"))
    assert domain_problem(percent, "duty", "percent") is None
    assert "own unit" in domain_problem(percent, "duty", "dimensionless")
    assert membership(percent, IntegerValue(50)) is None and membership(percent, IntegerValue(101)) is not None
    found = membership(percent, IntegerValue(10 ** 400))
    assert found is not None and found[0] == "OUTSIDE_RANGE"                      # a structured refusal, no crash


def test_integer_and_categorical_kinds_are_checked_by_kind():
    hvac = fx.hvac_world("chamber")
    assert "OUTSIDE_RANGE" in codes(check(hvac, "step_speed", {"speed": q(3000, "rpm"), "fan_stage": IntegerValue(6)}))
    assert "OUTSIDE_RANGE" in codes(check(hvac, "step_speed", {"speed": q(3000, "rpm"),
                                                               "fan_stage": IntegerValue(10 ** 400)}))
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
    assert "PRECONDITION_UNCERTAINTY_UNKNOWN" in codes(check(point, "pulse", PULSE_OK))
    straddle = rebound(battery, "SOC", "near the floor", value=q(0.11, D), uncertainty=fx.interval(0.11, 0.02, D))
    assert "PRECONDITION_UNDECIDED" in codes(check(straddle, "pulse", PULSE_OK))
    low = rebound(battery, "SOC", "empty", value=q(0.05, D), uncertainty=fx.interval(0.05, 0.01, D))
    assert check(low, "pulse", PULSE_OK).status is F.INFEASIBLE_STATE


def test_interval_rules_are_sound_for_two_sided_sets(battery):
    """An interval straddling both ends of a range, or both sides of an EQUAL band, is undecided, never outside."""
    wide = rebound(battery, "SOC", "very uncertain", value=q(0.5, D), uncertainty=fx.interval(0.5, 0.6, D))
    d = check(wide, "pulse", PULSE_OK)
    assert d.status is F.MISSING_INFORMATION and "STATE_DOMAIN_UNDECIDED" in codes(d)
    edge = rebound(battery, "SOC", "near full", value=q(0.999, D), uncertainty=fx.interval(0.999, 0.01, D))
    assert "STATE_DOMAIN_UNDECIDED" in codes(check(edge, "pulse", PULSE_OK))
    over = rebound(battery, "SOC", "over full", value=q(1.05, D), uncertainty=fx.interval(1.05, 0.01, D))
    assert "STATE_OUTSIDE_DECLARED_DOMAIN" in codes(check(over, "pulse", PULSE_OK))
    band = ConstraintDefinition("soc_mid", "SOC", Op.EQUAL, q(0.5, D), tolerance=q(0.05, D))
    banded = with_action(battery, "pulse", "a band precondition", preconditions=(band,))
    for half, expected in ((0.01, F.FEASIBLE), (0.2, F.MISSING_INFORMATION)):
        w = rebound(banded, "SOC", f"mid {half}", value=q(0.5, D), uncertainty=fx.interval(0.5, half, D))
        assert check(w, "pulse", PULSE_OK).status is expected
    above = rebound(banded, "SOC", "above the band", value=q(0.9, D), uncertainty=fx.interval(0.9, 0.01, D))
    assert "PRECONDITION_VIOLATED" in codes(check(above, "pulse", PULSE_OK))


def test_alternatives_are_declared_options_never_projections():
    w = fx.gen1_pool_world()
    p = fx.propose(w, "pool_query", {"I_A": q(1.15, "A"), "t_on_s": q(55.62, "s")})
    alt = space(w).alternatives(p, "I_A")
    assert [o.magnitude for o in alt["options"]] == [1.0, 2.0] and "not recommendations" in alt["label"]
    rng = space(w).alternatives(p, "t_on_s")
    assert rng["kind"] == "declared_range" and "options" not in rng
