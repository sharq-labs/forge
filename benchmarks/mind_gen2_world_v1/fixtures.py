"""Synthetic ScientificWorld contract fixtures for four structurally different systems (development evidence only).

These are contract fixtures, not scientific claims: every number is invented to exercise the world/action-space
contract, and nothing here is fitted, measured or read from a dataset.  Every bound value cites a
``RecordKind.SYNTHETIC_FIXTURE`` reference, which is never evidence.  No battery v1/v2/v3 data, answer or truth is used.
All domain vocabulary (battery, HVAC, drone, motor) lives here, never in ``engcore.mind.world``.

Every world declares each variable's role from its (synthetic) problem specification or protocol metadata, never from
its name; the HVAC world is built twice to show that the SAME name ``T_out`` is a fixed protocol condition in a
climate-chamber task and a passive nuisance in a field task, and behaves accordingly.

Every identifier (variable, action, constraint, entity, provider, model) passes through ``n``, so a test can rename
them all bijectively (opaque tokens, an adversarial permutation, forbidden words) and require identical decisions:
nothing may depend on what a name says.

``base(world, n)`` gives, per action, one proposal FEASIBLE by construction; the benchmark derives its cases from it.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Mapping

from engcore.execution.orchestration.resources import ResourceBudget, ResourceUsage
from engcore.mind.repsem.roles import RoleDeclaration, RoleSource, VariableRole as R
from engcore.mind.world import (
    ActionMode, ActionSpec, ApplicabilityBinding, ControlSpec, DeclaredConstraint, DiscreteLevels, Entity,
    ExecutionKind, Guard, ObservationChannel, ProposedAction, ProviderSnapshot, RecordKind, RecordRef,
    ScientificWorld, TemporalSemantics as TS, ValueOrigin, WorldBudget, WorldVariable,
)
from engcore.providers.catalog import Availability, ProviderCapability, ProviderMode, ProviderStatus
from engcore.providers.health import assess_health
from engcore.scientific import (
    ConstraintDefinition, ConstraintOperator as Op, Quantity, RangeCondition, ScientificModelDefinition,
    ScientificParameter, ScientificVariable, Uncertainty, ValidityDomain, VariableKind, VariableRole as IR,
)
from engcore.scientific.ir.values import CategoricalValue, IntegerValue
from engcore.scientific.models.definition import InputSourceKind, ModelInputSpec
from engcore.scientific.models.registry import ModelRegistry
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.hypotheses import ProposalProvenance, ProposerKind
from engcore.system_runtime.request import ProviderBinding

P = RoleSource.PROTOCOL_METADATA
S = RoleSource.PROBLEM_SPECIFICATION
DIMLESS = "dimensionless"
Rename = Callable[[str], str]


def same(name: str) -> str:
    return name


# ---- small constructors (fixture vocabulary only) ---------------------------------------------------------------------
def q(magnitude: float, unit: str) -> Quantity:
    return Quantity(magnitude, unit)


def cat(value: str) -> CategoricalValue:
    return CategoricalValue(value)


def synthetic(token: str) -> RecordRef:
    return RecordRef(RecordKind.SYNTHETIC_FIXTURE, f"synthetic:{token}")


def interval(value: float, half: float, unit: str) -> Uncertainty:
    return Uncertainty(kind="interval", lower=q(value - half, unit), upper=q(value + half, unit),
                       method="synthetic declared interval")


def var(name: str, role: R, unit: str, temporal: TS, *, role_source: RoleSource = S, driven_by: tuple[str, ...] = (),
        derived_from: tuple[str, ...] = (), **kw: Any) -> WorldVariable:
    decl = RoleDeclaration(name, role, unit, role_source, "synthetic specification declares this role",
                           tuple(driven_by), tuple(derived_from))
    return WorldVariable(decl, temporal, **kw)


def declared(value: Any) -> dict[str, Any]:
    return {"value": value, "origin": ValueOrigin.DECLARED, "value_basis": "synthetic protocol states this value"}


def bound(value: Any, origin: ValueOrigin, token: str, uncertainty: Uncertainty | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"value": value, "origin": origin, "source": synthetic(token)}
    if uncertainty is not None:
        out["uncertainty"] = uncertainty
    return out


def crange(name: str, unit: str, lo: float, hi: float, role: IR = IR.CONTROL) -> ScientificVariable:
    return ScientificVariable(name, unit, VariableKind.CONTINUOUS, role, q(lo, unit), q(hi, unit))


def irange(name: str, lo: int, hi: int, role: IR = IR.CONTROL) -> ScientificVariable:
    return ScientificVariable(name, DIMLESS, VariableKind.INTEGER, role, q(lo, DIMLESS), q(hi, DIMLESS))


def cats(name: str, *values: str, role: IR = IR.CONTROL) -> ScientificVariable:
    return ScientificVariable(name, DIMLESS, VariableKind.CATEGORICAL, role, categories=tuple(values))


def levels(unit: str, *values: float) -> DiscreteLevels:
    return DiscreteLevels(unit, tuple(q(v, unit) for v in values))


def ctrl(variable: str, domain: Any, source: RoleSource = S, **kw: Any) -> ControlSpec:
    return ControlSpec(variable, domain, source, f"synthetic {source.value} declares these allowed values", **kw)


def fixed(name: str, value: Any) -> ScientificParameter:
    return ScientificParameter(name, value)


def at_most(name: str, metric: str, bound_: Quantity) -> ConstraintDefinition:
    return ConstraintDefinition(name, metric, Op.LESS_EQUAL, bound_)


def at_least(name: str, metric: str, bound_: Quantity) -> ConstraintDefinition:
    return ConstraintDefinition(name, metric, Op.GREATER_EQUAL, bound_)


def when(variable: str, *values: str) -> Guard:
    return Guard(variable, tuple(cat(v) for v in values))


def cost(experiments: int, solver_calls: int) -> dict[str, IntegerValue]:
    return {"experiments": IntegerValue(experiments), "solver_calls": IntegerValue(solver_calls)}


def channel(name: str) -> ObservationChannel:
    return ObservationChannel(name, synthetic(f"instrument/{name}"))


def provider(pid: str, version: str, *, available: bool = True) -> ProviderSnapshot:
    """A provider snapshot built by the provider authority's own records (ProviderStatus + assess_health)."""
    capability = ProviderCapability(pid, "synthetic", ProviderMode.LIBRARY, "synthetic-fixture", ("synthetic",))
    status = ProviderStatus(capability, Availability.AVAILABLE if available else Availability.UNAVAILABLE,
                            version=version, digest=hashlib.sha256(f"{pid}@{version}".encode()).hexdigest(),
                            reason="" if available else "synthetic: not installed here")
    return ProviderSnapshot.from_status(status, assess_health(status))


def build_digest(pid: str, version: str) -> str:
    return hashlib.sha256(f"{pid}@{version}".encode()).hexdigest()


def live_status(pid: str, version: str, *, available: bool = True) -> ProviderStatus:
    """The provider authority's live status for a synthetic provider (what ``ProviderRegistry.status`` returns)."""
    capability = ProviderCapability(pid, "synthetic", ProviderMode.LIBRARY, "synthetic-fixture", ("synthetic",))
    return ProviderStatus(capability, Availability.AVAILABLE if available else Availability.UNAVAILABLE,
                          version=version, digest=build_digest(pid, version),
                          reason="" if available else "synthetic: not installed here")


def model_registry(w: ScientificWorld) -> ModelRegistry:
    """A model registry holding the world's applicability models (the registry a gate verifies bindings against)."""
    return ModelRegistry(tuple(a.model for a in w.applicability))


def fresh(w: ScientificWorld, token: str) -> ScientificWorld:
    """The same world under its own revision (one more synthetic reference)."""
    return w.derive(reason=f"isolated for {token}", references=w.references + (synthetic(f"test/{token}"),))


def binding(pid: str, version: str) -> ProviderBinding:
    return ProviderBinding("use-" + hashlib.sha256(pid.encode()).hexdigest()[:12], pid, version)


def route_model(model_id: str, version: str, name: str, unit: str, lo: float, hi: float) -> ApplicabilityBinding:
    """A minimal model record whose validity domain is one range condition (the route's qualified envelope)."""
    return ApplicabilityBinding(ScientificModelDefinition(
        model_id, version, inputs=(ModelInputSpec(name, InputSourceKind.VARIABLE, unit_exemplar=unit),),
        exclusions=(), excludes_nothing_because="a synthetic contract fixture model excludes nothing it declares",
        validity=ValidityDomain((RangeCondition(name, minimum=q(lo, unit), maximum=q(hi, unit)),))))


def action(action_id: str, family: ActionFamily, mode: ActionMode, **kw: Any) -> ActionSpec:
    kw.setdefault("cost_basis", "synthetic protocol declares what one execution consumes")
    return ActionSpec(action_id, family, mode, declared_by=P, basis="synthetic protocol declares this action", **kw)


def budget(experiments: int, spent: int, *, solver: tuple[int, int] | None = None,
           wall: tuple[float, float] | None = None, ledger: str) -> WorldBudget:
    unbounded = {"cost": "synthetic: no monetary budget in this protocol"}
    if solver is None:
        unbounded["solver_calls"] = "synthetic: no solver is used in this protocol"
    if wall is None:
        unbounded["wall_time"] = "synthetic: no wall-time limit in this protocol"
    compute = None if solver is None and wall is None else ResourceBudget(
        max_wall_seconds=None if wall is None else wall[0], max_function_evaluations=None if solver is None else solver[0])
    used = None if compute is None else ResourceUsage(wall_seconds=0.0 if wall is None else wall[1],
                                                      function_evaluations=0 if solver is None else solver[1])
    return WorldBudget(experiments=experiments, observations_spent=spent, compute=compute,
                       compute_used=used, unbounded=unbounded, authority=synthetic(f"ledger/{ledger}"),
                       compute_spent=None if used is None else (used.wall_seconds, used.function_evaluations))


def world(world_id: str, variables: tuple[WorldVariable, ...], **kw: Any) -> ScientificWorld:
    return ScientificWorld(world_id, variables, declared_by=P, basis="synthetic contract fixture world", **kw)


HUMAN = ProposalProvenance(ProposerKind.HUMAN, "fixture")


def propose(w: ScientificWorld, action_id: str, assignments: Mapping[str, Any], observe: tuple[str, ...] = (),
            proposer: ProposalProvenance = HUMAN) -> ProposedAction:
    return ProposedAction(action_id, w.revision_id, dict(assignments), tuple(observe), proposer)


# ---- BATTERY -------------------------------------------------------------------------------------------------------------
def battery_world(n: Rename = same) -> ScientificWorld:
    I, t, Ta, mode, soc, V, Ts, Pel = (n(x) for x in ("I", "t_pulse", "T_amb", "mode", "SOC", "V", "T_surf", "P_el"))
    R0, R1, C1, ecm = n("R0"), n("R1"), n("C1"), n("sim.ecm")
    variables = (
        var(I, R.CONTROLLED_INPUT, "A", TS.PER_SEGMENT, domain=crange(I, "A", -5, 5), label="cell current"),
        var(t, R.CONTROLLED_INPUT, "s", TS.CONSTANT_PER_RUN, domain=crange(t, "s", 1, 3600)),
        var(Ta, R.CONTROLLED_INPUT, "degC", TS.CONSTANT_PER_RUN, domain=crange(Ta, "degC", -40, 85),
            label="climate chamber set point", **declared(q(25, "degC"))),
        var(mode, R.FIXED_PROTOCOL_CONDITION, DIMLESS, TS.CONSTANT_PER_RUN, role_source=P,
            domain=cats(mode, "charge", "discharge")),
        var(soc, R.STATE_VARIABLE, DIMLESS, TS.STATE_EVOLVING, role_source=P, driven_by=(I,),
            domain=crange(soc, DIMLESS, 0, 1, IR.STATE),
            **bound(q(0.8, DIMLESS), ValueOrigin.ESTIMATED, "coulomb-count/run-0", interval(0.8, 0.02, DIMLESS))),
        var(V, R.MEASUREMENT, "V", TS.TIME_SERIES, label="terminal voltage"),
        var(Ts, R.NUISANCE_VARIABLE, "degC", TS.TIME_SERIES),
        var(Pel, R.DERIVED_QUANTITY, "W", TS.TIME_SERIES, derived_from=(I, V)),
        var(R0, R.LATENT_PARAMETER, "ohm", TS.TIME_INVARIANT, **bound(q(0.012, "ohm"), ValueOrigin.ESTIMATED, "fit/ecm-1")),
        var(R1, R.LATENT_PARAMETER, "ohm", TS.TIME_INVARIANT),
        var(C1, R.LATENT_PARAMETER, "F", TS.TIME_INVARIANT),
    )
    t25 = fixed(Ta, q(25, "degC"))
    soc_floor = at_least(n("soc_floor"), soc, q(0.1, DIMLESS))
    soc_ceiling = at_most(n("soc_ceiling"), soc, q(0.95, DIMLESS))
    route = route_model(n("synthetic.ecm-route"), "1", Ta, "degC", 0, 50)
    pulse, signed, prep, sim, rest = (n(a) for a in ("pulse", "signed_pulse", "precondition_to_soc",
                                                    "simulate_pulse", "observe_rest"))
    actions = (
        action(pulse, ActionFamily.CHARACTERIZE, ActionMode.INTERVENE,
               controls=(ctrl(I, levels("A", 1.0, 2.0), P), ctrl(t, crange(t, "s", 10, 600))),
               fixed_conditions=(t25, fixed(mode, cat("charge"))), preconditions=(soc_floor,),
               expected_observables=(I, Ts, V), estimated_cost=cost(1, 0), estimated_duration=q(900, "s")),
        action(signed, ActionFamily.EXPLORE, ActionMode.INTERVENE,
               controls=(ctrl(mode, cats(mode, "charge", "discharge"), P), ctrl(I, crange(I, "A", -5, 5)),
                         ctrl(t, crange(t, "s", 10, 600))),
               fixed_conditions=(t25,), preconditions=(soc_floor, soc_ceiling), expected_observables=(I, V),
               estimated_cost=cost(1, 0), estimated_duration=q(900, "s")),
        action(prep, ActionFamily.CHARACTERIZE, ActionMode.INTERVENE,
               controls=(ctrl(soc, crange(soc, DIMLESS, 0.05, 0.95), P, state_intervention=True),),
               fixed_conditions=(t25,), expected_observables=(V,), estimated_cost=cost(1, 0),
               estimated_duration=q(7200, "s"), description="state preparation: its family label is an open owner decision"),
        action(sim, ActionFamily.EXPLORE, ActionMode.INTERVENE, execution=ExecutionKind.MODEL_EXECUTION,
               controls=(ctrl(I, crange(I, "A", 0.1, 5)), ctrl(Ta, crange(Ta, "degC", -40, 85)),
                         ctrl(t, crange(t, "s", 10, 600))),
               fixed_conditions=(fixed(mode, cat("charge")),), expected_observables=(V,),
               provider_requirements=(binding(ecm, "1.0"),), applicability=(route.binding_id,),
               estimated_cost=cost(0, 2), estimated_duration=q(30, "s")),
        action(rest, ActionFamily.CHARACTERIZE, ActionMode.OBSERVE, fixed_conditions=(t25,),
               expected_observables=(Ts, V), estimated_cost=cost(1, 0), estimated_duration=q(3600, "s")),
    )
    return world(
        "synthetic.battery.pulse-cell", variables,
        entities=(Entity(n("cell"), (C1, I, Pel, R0, R1, soc, Ts, V)), Entity(n("chamber"), (Ta,))),
        constraints=(
            DeclaredConstraint(n("charge_positive"), ConstraintDefinition(n("charge_positive"), I, Op.GREATER_THAN,
                                                                          q(0, "A")),
                               when(mode, "charge"), (pulse, signed, sim), P,
                               "synthetic protocol: charge pulses draw positive current"),
            DeclaredConstraint(n("discharge_negative"), ConstraintDefinition(n("discharge_negative"), I, Op.LESS_THAN,
                                                                             q(0, "A")),
                               when(mode, "discharge"), (pulse, signed, sim), P,
                               "synthetic protocol: discharge pulses draw negative current"),
        ),
        actions=actions, channels=(channel(I), channel(Ts), channel(V)), applicability=(route,),
        providers=(provider(ecm, "1.0"),), budget=budget(20, 3, solver=(10, 4), ledger="battery"),
        references=(synthetic("protocol/battery-pulse/1"),),
    )


# ---- HVAC (two tasks; same names, different declared roles) ---------------------------------------------------------------
def hvac_world(task: str = "chamber", n: Rename = same) -> ScientificWorld:
    if task not in ("chamber", "field"):
        raise ValueError(task)
    chamber = task == "chamber"
    speed, fan, hmode, Tout, Troom, Pel, cop, UA, occ = (n(x) for x in (
        "speed", "fan_stage", "hvac_mode", "T_out", "T_room", "P_el", "COP", "UA", "occupancy"))
    rc = n("sim.rc-building")
    t_out = (var(Tout, R.FIXED_PROTOCOL_CONDITION, "degC", TS.CONSTANT_PER_RUN, role_source=P,
                 domain=crange(Tout, "degC", -20, 50, IR.OBSERVABLE), **declared(q(35, "degC")))
             if chamber else
             var(Tout, R.NUISANCE_VARIABLE, "degC", TS.TIME_SERIES,
                 **bound(q(31, "degC"), ValueOrigin.OBSERVED, "weather-station/0", interval(31, 0.5, "degC"))))
    variables = (
        var(speed, R.CONTROLLED_INPUT, "rpm", TS.CONSTANT_PER_RUN, domain=crange(speed, "rpm", 1000, 6000),
            label="compressor speed"),
        var(fan, R.CONTROLLED_INPUT, DIMLESS, TS.CONSTANT_PER_RUN, domain=irange(fan, 1, 5)),
        var(hmode, R.FIXED_PROTOCOL_CONDITION, DIMLESS, TS.CONSTANT_PER_RUN, role_source=P,
            domain=cats(hmode, "cool", "heat")),
        t_out,
        var(Troom, R.STATE_VARIABLE, "degC", TS.STATE_EVOLVING, driven_by=(speed,),
            **bound(q(27, "degC"), ValueOrigin.OBSERVED, "thermostat/0", interval(27, 0.2, "degC"))),
        var(Pel, R.MEASUREMENT, "W", TS.TIME_SERIES, label="electrical power"),
        var(cop, R.DERIVED_QUANTITY, DIMLESS, TS.CONSTANT_PER_RUN, derived_from=(Pel, Troom)),
        var(UA, R.LATENT_PARAMETER, "W/K", TS.TIME_INVARIANT),
        var(occ, R.NUISANCE_VARIABLE, DIMLESS, TS.TIME_SERIES, domain=irange(occ, 0, 20, IR.OBSERVABLE),
            **bound(IntegerValue(2), ValueOrigin.OBSERVED, "occupancy-sensor/0")),
    )
    chamber_fixed = (fixed(Tout, q(35, "degC")),) if chamber else ()
    room_ok = (at_most(n("room_not_hot"), Troom, q(303.15, "K")),)
    route = route_model(n("synthetic.rc-building"), "2", Tout, "degC", -10, 40)
    step, change, sim, obs = (n(a) for a in ("step_speed", "mode_change", "simulate_building", "observe_room"))
    actions = (
        action(step, ActionFamily.CHARACTERIZE, ActionMode.INTERVENE,
               controls=(ctrl(speed, crange(speed, "rpm", 1500, 6000)), ctrl(fan, irange(fan, 1, 5))),
               fixed_conditions=(fixed(hmode, cat("cool")),) + chamber_fixed, preconditions=room_ok,
               expected_observables=(Pel, Troom), estimated_cost=cost(1, 0), estimated_duration=q(1800, "s")),
        action(change, ActionFamily.EXPLORE, ActionMode.INTERVENE,
               controls=(ctrl(hmode, cats(hmode, "cool", "heat"), P), ctrl(speed, crange(speed, "rpm", 1000, 6000))),
               fixed_conditions=chamber_fixed, expected_observables=(Pel, Troom), estimated_cost=cost(1, 0),
               estimated_duration=q(3600, "s")),
        action(sim, ActionFamily.EXPLORE, ActionMode.INTERVENE, execution=ExecutionKind.MODEL_EXECUTION,
               controls=(ctrl(speed, crange(speed, "rpm", 1000, 6000)),),
               fixed_conditions=(fixed(hmode, cat("cool")),) + chamber_fixed, expected_observables=(Troom,),
               provider_requirements=(binding(rc, "2.1"),), applicability=(route.binding_id,),
               estimated_cost=cost(0, 1), estimated_duration=q(60, "s")),
        action(obs, ActionFamily.CHARACTERIZE, ActionMode.OBSERVE,
               expected_observables=(Pel, Troom) + (() if chamber else (Tout,)), estimated_cost=cost(0, 0),
               estimated_duration=q(600, "s")),
    )
    return world(
        f"synthetic.hvac.{task}", variables,
        entities=(Entity(n("unit"), (UA, cop, fan, hmode, Pel, speed)), Entity(n("room"), (Troom, occ)),
                  Entity(n("outdoors"), (Tout,))),
        constraints=(DeclaredConstraint(n("heat_speed_cap"), at_most(n("heat_speed_cap"), speed, q(4000, "rpm")),
                                        when(hmode, "heat"), (step, change, sim), P,
                                        "synthetic protocol: heating runs cap the compressor speed"),),
        actions=actions, channels=tuple(channel(x) for x in (Pel, Troom, occ) + (() if chamber else (Tout,))),
        applicability=(route,), providers=(provider(rc, "2.1"),),
        budget=budget(10, 2, solver=(50, 10), wall=(8 * 3600.0, 2 * 3600.0), ledger=f"hvac-{task}"),
        references=(synthetic(f"protocol/hvac-{task}/1"),),
    )


# ---- DRONE ---------------------------------------------------------------------------------------------------------------
def drone_world(n: Rename = same) -> ScientificWorld:
    thrust, payload, fmode, wind, vel, alt, bV, drag, shaft = (n(x) for x in (
        "thrust_cmd", "payload", "flight_mode", "wind", "velocity", "altitude", "battery_V", "drag_coeff", "shaft_power"))
    sixdof = n("sim.6dof")
    variables = (
        var(thrust, R.CONTROLLED_INPUT, "N", TS.CONSTANT_PER_RUN, domain=crange(thrust, "N", 0, 40),
            label="commanded thrust"),
        var(payload, R.FIXED_PROTOCOL_CONDITION, "kg", TS.CONSTANT_PER_RUN, role_source=P, domain=levels("kg", 0, 0.5, 1.0)),
        var(fmode, R.FIXED_PROTOCOL_CONDITION, DIMLESS, TS.CONSTANT_PER_RUN, role_source=P,
            domain=cats(fmode, "hover", "climb")),
        var(wind, R.NUISANCE_VARIABLE, "m/s", TS.TIME_SERIES,
            **bound(q(4, "m/s"), ValueOrigin.OBSERVED, "anemometer/0", interval(4, 0.5, "m/s"))),
        var(vel, R.STATE_VARIABLE, "m/s", TS.STATE_EVOLVING, driven_by=(thrust,),
            **bound(q(0, "m/s"), ValueOrigin.OBSERVED, "gnss/0", interval(0, 0.05, "m/s"))),
        var(alt, R.STATE_VARIABLE, "m", TS.STATE_EVOLVING, driven_by=(thrust,),
            **bound(q(0, "m"), ValueOrigin.OBSERVED, "gnss/0", interval(0, 0.1, "m"))),
        var(bV, R.MEASUREMENT, "V", TS.TIME_SERIES),
        var(drag, R.LATENT_PARAMETER, DIMLESS, TS.TIME_INVARIANT),
        var(shaft, R.DERIVED_QUANTITY, "W", TS.TIME_SERIES, derived_from=(thrust, vel)),
    )
    at_rest = (at_most(n("still"), vel, q(0.5, "m/s")), at_most(n("near_ground"), alt, q(1, "m")))
    route = route_model(n("synthetic.6dof"), "0.9", wind, "m/s", 0, 12)
    hover, climb, sim, obs = (n(a) for a in ("hover_test", "climb_test", "simulate_flight", "observe_wind"))
    actions = (
        action(hover, ActionFamily.CHARACTERIZE, ActionMode.INTERVENE,
               controls=(ctrl(thrust, crange(thrust, "N", 0, 40)), ctrl(payload, levels("kg", 0, 0.5, 1.0), P)),
               fixed_conditions=(fixed(fmode, cat("hover")),), preconditions=at_rest,
               expected_observables=(alt, bV, vel), estimated_cost=cost(1, 0), estimated_duration=q(300, "s")),
        action(climb, ActionFamily.EXPLORE, ActionMode.INTERVENE,
               controls=(ctrl(fmode, cats(fmode, "hover", "climb"), P), ctrl(thrust, crange(thrust, "N", 0, 40))),
               fixed_conditions=(fixed(payload, q(0.5, "kg")),), preconditions=at_rest,
               expected_observables=(alt, bV, vel), estimated_cost=cost(1, 0), estimated_duration=q(300, "s")),
        action(sim, ActionFamily.EXPLORE, ActionMode.INTERVENE, execution=ExecutionKind.MODEL_EXECUTION,
               controls=(ctrl(thrust, crange(thrust, "N", 0, 40)),),
               fixed_conditions=(fixed(fmode, cat("hover")), fixed(payload, q(0.5, "kg"))),
               expected_observables=(alt, vel), provider_requirements=(binding(sixdof, "0.9"),),
               applicability=(route.binding_id,), estimated_cost=cost(0, 3), estimated_duration=q(20, "s")),
        action(obs, ActionFamily.CHARACTERIZE, ActionMode.OBSERVE, expected_observables=(wind,),
               estimated_cost=cost(0, 0), estimated_duration=q(60, "s")),
    )
    return world(
        "synthetic.drone.quadrotor", variables,
        entities=(Entity(n("airframe"), (alt, bV, drag, payload, shaft, thrust, vel)), Entity(n("atmosphere"), (wind,))),
        constraints=(DeclaredConstraint(n("climb_thrust"), at_least(n("climb_thrust"), thrust, q(20, "N")),
                                        when(fmode, "climb"), (climb, hover, sim), P,
                                        "synthetic protocol: a climb needs at least 20 N"),),
        actions=actions, channels=tuple(channel(x) for x in (alt, bV, vel, wind)), applicability=(route,),
        providers=(provider(sixdof, "0.9"),), budget=budget(5, 0, solver=(20, 0), ledger="drone"),
        references=(synthetic("protocol/drone-hover/1"),),
    )


# ---- ELECTRIC MOTOR ------------------------------------------------------------------------------------------------------
def motor_world(n: Rename = same) -> ScientificWorld:
    Icmd, iters, Vs, cmode, omega, Tw, torque, Rw, eff, Tamb = (n(x) for x in (
        "I_cmd", "solver_iterations", "V_supply", "ctrl_mode", "omega", "T_wind", "torque", "R_wind", "efficiency",
        "T_ambient"))
    lumped = n("sim.lumped-thermal")
    variables = (
        var(Icmd, R.CONTROLLED_INPUT, "A", TS.CONSTANT_PER_RUN, domain=crange(Icmd, "A", 0, 30), label="commanded current"),
        var(iters, R.CONTROLLED_INPUT, DIMLESS, TS.CONSTANT_PER_RUN, domain=irange(iters, 1, 1000)),
        var(Vs, R.FIXED_PROTOCOL_CONDITION, "V", TS.CONSTANT_PER_RUN, role_source=P, domain=levels("V", 24, 48)),
        var(cmode, R.FIXED_PROTOCOL_CONDITION, DIMLESS, TS.CONSTANT_PER_RUN, role_source=P,
            domain=cats(cmode, "torque", "speed")),
        var(omega, R.STATE_VARIABLE, "rad/s", TS.STATE_EVOLVING, driven_by=(Icmd,),
            **bound(q(0, "rad/s"), ValueOrigin.OBSERVED, "encoder/0", interval(0, 0.1, "rad/s"))),
        var(Tw, R.STATE_VARIABLE, "degC", TS.STATE_EVOLVING, driven_by=(Icmd,),
            **bound(q(40, "degC"), ValueOrigin.OBSERVED, "thermocouple/0", interval(40, 1.0, "degC"))),
        var(torque, R.MEASUREMENT, "N*m", TS.TIME_SERIES),
        var(Rw, R.LATENT_PARAMETER, "ohm", TS.TIME_INVARIANT),
        var(eff, R.DERIVED_QUANTITY, DIMLESS, TS.CONSTANT_PER_RUN, derived_from=(Icmd, Vs, omega, torque)),
        var(Tamb, R.NUISANCE_VARIABLE, "degC", TS.TIME_SERIES,
            **bound(q(22, "degC"), ValueOrigin.OBSERVED, "room-thermometer/0", interval(22, 0.5, "degC"))),
    )
    route = route_model(n("synthetic.lumped-thermal"), "3", Icmd, "A", 0, 25)
    load, sim, obs = (n(a) for a in ("load_step", "simulate_thermal", "observe_temperature"))
    actions = (
        action(load, ActionFamily.CHARACTERIZE, ActionMode.INTERVENE,
               controls=(ctrl(Icmd, crange(Icmd, "A", 0, 30)), ctrl(Vs, levels("V", 24, 48), P),
                         ctrl(cmode, cats(cmode, "torque", "speed"), P)),
               preconditions=(at_most(n("winding_cool"), Tw, q(393.15, "K")),),
               expected_observables=(Tw, omega, torque), estimated_cost=cost(1, 0), estimated_duration=q(120, "s")),
        action(sim, ActionFamily.EXPLORE, ActionMode.INTERVENE, execution=ExecutionKind.MODEL_EXECUTION,
               controls=(ctrl(Icmd, crange(Icmd, "A", 0, 30)), ctrl(iters, irange(iters, 1, 1000))),
               fixed_conditions=(fixed(Vs, q(48, "V")), fixed(cmode, cat("torque"))), expected_observables=(Tw,),
               provider_requirements=(binding(lumped, "3.2"),), applicability=(route.binding_id,),
               estimated_cost=cost(0, 1), estimated_duration=q(5, "s")),
        action(obs, ActionFamily.CHARACTERIZE, ActionMode.OBSERVE, expected_observables=(Tw,),
               estimated_cost=cost(0, 0), estimated_duration=q(60, "s")),
    )
    return world(
        "synthetic.motor.pmsm", variables,
        entities=(Entity(n("drive"), (Icmd, Vs, cmode, iters)), Entity(n("machine"), (Rw, Tw, eff, omega, torque)),
                  Entity(n("room"), (Tamb,))),
        constraints=(DeclaredConstraint(n("speed_mode_cap"), at_most(n("speed_mode_cap"), Icmd, q(20, "A")),
                                        when(cmode, "speed"), (load,), P,
                                        "synthetic protocol: speed mode caps the current"),),
        actions=actions, channels=tuple(channel(x) for x in (Tamb, Tw, omega, torque)), applicability=(route,),
        providers=(provider(lumped, "3.2"),), budget=budget(8, 1, solver=(100, 0), ledger="motor"),
        references=(synthetic("protocol/motor-load/1"),),
    )


# ---- the Gen1 failure class: a protocol offering two current levels -------------------------------------------------------
def gen1_pool_world(n: Rename = same) -> ScientificWorld:
    """Two declared current levels (protocol metadata) and a continuously settable pulse duration.

    This reproduces the CLASS of the Gen1 failure (a request for a current level the protocol does not offer), not
    battery_rediscovery_v1's recorded-pool mechanics (nearest-sample matching within a tolerance, each sample used
    once), which a declared-level world deliberately does not model."""
    IA, ton, y, soc, R0 = (n(x) for x in ("I_A", "t_on_s", "y", "soc", "R0"))
    return world(
        "synthetic.gen1.two-level-protocol",
        (var(IA, R.FIXED_PROTOCOL_CONDITION, "A", TS.CONSTANT_PER_RUN, role_source=P, domain=levels("A", 1.0, 2.0)),
         var(ton, R.CONTROLLED_INPUT, "s", TS.CONSTANT_PER_RUN, domain=crange(ton, "s", 20, 200)),
         var(y, R.MEASUREMENT, "V", TS.TIME_SERIES),
         var(soc, R.STATE_VARIABLE, DIMLESS, TS.STATE_EVOLVING, role_source=P, driven_by=(IA,)),
         var(R0, R.LATENT_PARAMETER, "ohm", TS.TIME_INVARIANT)),
        actions=(action(n("pool_query"), ActionFamily.EXPLORE, ActionMode.INTERVENE,
                        controls=(ctrl(IA, levels("A", 1.0, 2.0), P), ctrl(ton, crange(ton, "s", 20, 200))),
                        expected_observables=(y,), estimated_cost={"experiments": IntegerValue(1)}),),
        channels=(channel(y),), budget=budget(24, 0, ledger="gen1-pool"),
        references=(synthetic("protocol/two-level/1"),),
    )


WORLDS: dict[str, Callable[..., ScientificWorld]] = {
    "battery": battery_world,
    "hvac_chamber": lambda n=same: hvac_world("chamber", n),
    "hvac_field": lambda n=same: hvac_world("field", n),
    "drone": drone_world,
    "motor": motor_world,
}


def base(world_name: str, n: Rename = same) -> dict[str, tuple[dict[str, Any], tuple[str, ...]]]:
    """One FEASIBLE-by-construction proposal per action of a world: (assignments, OBSERVE targets), names renamed."""
    table: dict[str, dict[str, tuple[dict[str, Any], tuple[str, ...]]]] = {
        "battery": {
            "pulse": ({"I": q(1.0, "A"), "t_pulse": q(60, "s")}, ("V",)),
            "signed_pulse": ({"mode": cat("discharge"), "I": q(-2, "A"), "t_pulse": q(30, "s")}, ("V",)),
            "precondition_to_soc": ({"SOC": q(0.5, DIMLESS)}, ("V",)),
            "simulate_pulse": ({"I": q(2, "A"), "T_amb": q(25, "degC"), "t_pulse": q(60, "s")}, ("V",)),
            "observe_rest": ({}, ("T_surf", "V")),
        },
        "hvac_chamber": {
            "step_speed": ({"speed": q(3000, "rpm"), "fan_stage": IntegerValue(3)}, ("P_el",)),
            "mode_change": ({"hvac_mode": cat("heat"), "speed": q(3500, "rpm")}, ("P_el",)),
            "simulate_building": ({"speed": q(2000, "rpm")}, ("T_room",)),
            "observe_room": ({}, ("T_room",)),
        },
        "hvac_field": {
            "step_speed": ({"speed": q(3000, "rpm"), "fan_stage": IntegerValue(3)}, ("P_el",)),
            "mode_change": ({"hvac_mode": cat("heat"), "speed": q(3500, "rpm")}, ("P_el",)),
            "simulate_building": ({"speed": q(2000, "rpm")}, ("T_room",)),
            "observe_room": ({}, ("T_out", "T_room")),
        },
        "drone": {
            "hover_test": ({"thrust_cmd": q(12, "N"), "payload": q(0.5, "kg")}, ("altitude",)),
            "climb_test": ({"flight_mode": cat("climb"), "thrust_cmd": q(25, "N")}, ("altitude",)),
            "simulate_flight": ({"thrust_cmd": q(12, "N")}, ("altitude",)),
            "observe_wind": ({}, ("wind",)),
        },
        "motor": {
            "load_step": ({"I_cmd": q(10, "A"), "V_supply": q(48, "V"), "ctrl_mode": cat("torque")}, ("torque",)),
            "simulate_thermal": ({"I_cmd": q(10, "A"), "solver_iterations": IntegerValue(200)}, ("T_wind",)),
            "observe_temperature": ({}, ("T_wind",)),
        },
    }
    return {n(a): ({n(k): v for k, v in assignments.items()}, tuple(n(o) for o in observe))
            for a, (assignments, observe) in table[world_name].items()}
