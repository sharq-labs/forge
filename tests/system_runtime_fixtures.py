"""Shared fixtures for the system-runtime tests: real scientific records + in-process authorities.

The authorities are deliberately trivial arithmetic (not physics): the tests are about orchestration
semantics (identity, blocking, atomic state, staleness, checkpointing), and every parameter of an
authority is part of its config so it is part of its identity.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable

from engcore.materials import MaterialIdentity, MaterialState
from engcore.materials.properties import PropertyDerivation, ResolvedProperty
from engcore.scenarios import (
    ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource, EnvironmentTimeline, HistoryEntry, NamedQuantity,
    QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline, TimePoint, TimeWindow,
)
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.twins import ScientificTwin, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.systems import ComponentDefinition, ComponentInstance, ConstraintBinding, SystemDefinition
from engcore.system_runtime import (
    ApplicabilityReport, AuthorityRegistry, CallbackAuthority, ConstraintObservation, EnvironmentRequirement, ExecutionProfile, InitialStateSpec,
    LiteralInput, MaterialPropertyRef, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeInput, OperationalContext, OutputValue, OwnerState,
    RequestedObservable, RuntimeContext, StateProposal, SystemRunRequest,
)

UNKNOWN = Uncertainty.unknown("fixture: not quantified")
H = 3600


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def p(seconds: float) -> TimePoint:
    return TimePoint("sys", Quantity(seconds, "s"))


def scenario(version: str = "1") -> ScenarioSpecification:
    return ScenarioSpecification("sys-hour", version, Quantity(0, "s"), Quantity(H, "s"),
                                 segments=(ScenarioSegment("s", Quantity(0, "s"), Quantity(H, "s")),))


def timeline(scn: ScenarioSpecification, ambient: tuple[float, ...] = (293.15, 295.15)) -> Timeline:
    entries = tuple(HistoryEntry(TimeWindow(p(H / len(ambient) * i), p(H / len(ambient) * (i + 1))), NamedQuantity("ambient", Quantity(v, "K")))
                    for i, v in enumerate(ambient))
    return Timeline.from_scenario(scn, timeline_id="sys", basis=TimeBasis("sys", "elapsed", "start"),
                                  histories=(QuantityHistory("amb-h", "exposure", "ambient", "K", entries),))


def environment(tl: Timeline, *, source_note: str = "declared chiller schedule") -> EnvironmentTimeline:
    ch = EnvironmentChannel("ambient", "ambient_temperature", "K", "site", ReferenceContext("bay", "site", "enu"), TimeWindow(p(0), p(H)),
                            ChannelRepresentation.INTERVAL_HISTORY, history_id="amb-h")
    src = EnvironmentSource("site", "design_assumption", source_note, sha(source_note), "1")
    return EnvironmentTimeline("sys-env", tl, EnvironmentKindRegistry.standard(), (src,), (ch,))


def material_property(value: float = 16.2, *, known: bool = True) -> tuple[MaterialState, ResolvedProperty]:
    state = MaterialState(MaterialIdentity("steel", specification="AISI 304"))
    if not known:
        return state, ResolvedProperty("thermal_conductivity", "unknown", PropertyDerivation.NONE, None, sha("set"), sha("snap"), state.digest, (), (), (), None, "no admissible datum")
    prop = ResolvedProperty("thermal_conductivity", "known", PropertyDerivation.SOURCED, NamedQuantity("thermal_conductivity", Quantity(value, "W/(m*K)")),
                            sha("set"), sha("snap"), state.digest, (sha("claim"),), ("measured",), (), None)
    return state, prop


def constraint(limit: float = 373.15) -> ConstraintDefinition:
    return ConstraintDefinition("max_cell_temperature", "cell_temperature", ConstraintOperator.LESS_EQUAL, Quantity(limit, "K"))


def system(*, with_constraint: bool = True) -> SystemDefinition:
    root = ScientificTwin("pack-root", "1", TwinKind.CONCEPT)
    cell = ScientificTwin("cell-twin", "1", TwinKind.CONCEPT)
    cooler = ScientificTwin("cooler-twin", "1", TwinKind.CONCEPT)
    definitions = (ComponentDefinition("assembly", "1"), ComponentDefinition("cell", "1"), ComponentDefinition("cooler", "1"))
    instances = (ComponentInstance("pack", "assembly", "1", root.reference), ComponentInstance("cell", "cell", "1", cell.reference, parent_id="pack"),
                 ComponentInstance("cooler", "cooler", "1", cooler.reference, parent_id="pack"))
    return SystemDefinition("pack-system", "1", definitions, instances,
                            constraint_bindings=(ConstraintBinding("b_tmax", "cell", "max_cell_temperature"),) if with_constraint else (),
                            constraints=(constraint(),) if with_constraint else ())


@dataclass
class Knobs:
    """Every parameter here is inside an authority's config, hence inside its identity."""
    current_a: float = 10.0
    volts: float = 3.7
    thermal_gain: float = 0.05        # K per W above ambient
    heat_fails: bool = False
    thermal_raises: bool = False
    hot_limit_k: float = 400.0        # runtime applicability bound on the solved temperature
    extra_output: bool = False        # thermal returns an undeclared output
    propose_bad_owner: bool = False
    omit_applicability: bool = False   # thermal reports no runtime applicability check at all
    provider_ref: Any = None          # ProviderRecordRef to report, if any
    calls: dict = field(default_factory=lambda: {"heat": 0, "thermal": 0, "report": 0})


def build(knobs: Knobs | None = None, *, ambient: tuple[float, ...] = (293.15, 295.15), scn_version: str = "1", conductivity: float = 16.2,
          limit: float = 373.15, cache: str = "off", allow_partial: bool = True, checkpoint_after: tuple[str, ...] = (), workspace: str = "",
          extra_authorities: tuple[CallbackAuthority, ...] = (), initial_temperature: float = 300.0):
    k = knobs or Knobs()
    scn = scenario(scn_version)
    tl = timeline(scn, ambient)
    env = environment(tl)
    sysdef = system()
    mat_state, prop = material_property(conductivity)
    limit_def = constraint(limit)
    sysdef = SystemDefinition(sysdef.system_id, sysdef.version, sysdef.definitions, sysdef.instances, sysdef.connections, (), (),
                              sysdef.constraint_bindings, (limit_def,))

    def heat_fn(call):
        k.calls["heat"] += 1
        if k.heat_fails:
            return NodeOutcome.failed("heat source model failed")
        i = call.value("current")
        return NodeOutcome("succeeded", {"power": OutputValue(Quantity(i.magnitude * k.volts, "W"), UNKNOWN, "heat-auth")})

    def thermal_fn(call):
        k.calls["thermal"] += 1
        if k.thermal_raises:
            raise RuntimeError("solver blew up")
        amb = call.value("ambient").to("K").magnitude
        power = call.value("heat_in").to("W").magnitude
        temperature = amb + power * k.thermal_gain
        outputs = {"temperature": OutputValue(Quantity(temperature, "K"), UNKNOWN, "thermal-auth")}
        if k.extra_output:
            outputs["surprise"] = OutputValue(Quantity(1.0, "K"), UNKNOWN, "thermal-auth")
        owner = "ghost" if k.propose_bad_owner else "cell"
        prev = call.state.owner("cell")
        new_owner = OwnerState(owner, "component", (InitialStateValue("temperature", Quantity(temperature, "K"), UNKNOWN),))
        status = "within" if temperature <= k.hot_limit_k else "outside"
        reports = () if k.omit_applicability else (ApplicabilityReport("temp_in_range", status, sha("evidence"), f"T={temperature}"),)
        return NodeOutcome("succeeded", outputs, applicability=reports,
                           state_proposal=StateProposal(Quantity(H / 2, "s"), (new_owner,)),
                           provider_records=() if k.provider_ref is None else (k.provider_ref,))

    def report_fn(call):
        k.calls["report"] += 1
        return NodeOutcome("succeeded", {"peak": OutputValue(call.value("t").to("K"), UNKNOWN, "report-auth")})

    heat = CallbackAuthority("heat-auth", heat_fn, config={"volts": k.volts, "fails": k.heat_fails}, deterministic=True)
    thermal = CallbackAuthority("thermal-auth", thermal_fn, config={"gain": k.thermal_gain, "hot_limit": k.hot_limit_k}, deterministic=True)
    report = CallbackAuthority("report-auth", report_fn, config={}, deterministic=True)
    authorities = AuthorityRegistry((heat, thermal, report, *extra_authorities))

    nodes = (
        NodeSpec("heat", NodeKind.NUMERICAL_EXECUTION, heat.ref, (NodeOutputSpec("power", "W"),), literals=(LiteralInput("current", Quantity(k.current_a, "A"), UNKNOWN),)),
        NodeSpec("thermal", NodeKind.PROVIDER_EXECUTION, thermal.ref, (NodeOutputSpec("temperature", "K"),),
                 inputs=(NodeInput("heat_in", "heat", "power", "W"),),
                 material_refs=(MaterialPropertyRef("k", "cell", "thermal_conductivity", prop.digest, "W/(m*K)"),),
                 environment_requirements=(EnvironmentRequirement("ambient", "ambient", Quantity(0, "s"), "K"),),
                 commits_state=True, writes_owners=("cell",), applicability_checks=("temp_in_range",), checkpointable=True),
        NodeSpec("report", NodeKind.AGGREGATE, report.ref, (NodeOutputSpec("peak", "K"),), inputs=(NodeInput("t", "thermal", "temperature", "K"),)),
    )
    observables = (RequestedObservable("peak_temperature", "report", "peak", "K"), RequestedObservable("heat_power", "heat", "power", "W"))
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("cell", "component", (InitialStateValue("temperature", Quantity(initial_temperature, "K"), UNKNOWN),)),),
                               ((("cell", mat_state.digest),)))
    request = SystemRunRequest.build(
        request_id="pack-run", system=sysdef, scenario=scn, timeline=tl, environment=env, initial_state=initial, nodes=nodes, observables=observables,
        materials=(mat_state,), constraint_observations=(ConstraintObservation("b_tmax", "max_cell_temperature", _cdigest(limit_def), "peak_temperature"),),
        profile=ExecutionProfile((), cache, allow_partial, checkpoint_after), operational=OperationalContext(workspace_hint=workspace))
    context = RuntimeContext(authorities, system=sysdef, scenario=scn, timeline=tl, environment=env, material_states={mat_state.digest: mat_state},
                             resolved_properties={prop.digest: prop}, constraints={_cdigest(limit_def): limit_def})
    return request, context, k


def _cdigest(defn: ConstraintDefinition) -> str:
    from engcore.system_runtime._common import digest_of
    return digest_of(defn.to_dict())
