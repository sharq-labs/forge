"""BIG 12 real end-to-end proofs: the system runtime over PyBaMM, TESPy, BIG 9 coupling and BIG 10 long horizons.

Every number below comes from a real provider execution (PyBaMM 26.x, TESPy 0.11.x).  The runtime adds
orchestration only: the coupling loop is the BIG 9 ``MultiphysicsRuntime``, the long horizon is the BIG 10
``MultiTimescaleRuntime``, providers are the BIG 11 adapters.  Illustrative fixtures (declared chiller
schedule, declared contact resistance, declared duty cycle) are labelled as such and prove mechanics, not
physics; agreement, convergence and reproducibility here are never validation.

Gates covered here: A (single provider), B (coupled multi-provider), C (multi-timescale lifecycle),
E (system checkpoint -> serialize -> fresh runtime -> resume), G (unavailable provider), H (runtime
applicability rollback on a real solved state), I (full trace), L (trust separation).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
from dataclasses import replace
from fractions import Fraction

import pytest

from engcore.coupling import CouplingExecutionLog, provider_participant, scalar_port
from engcore.credibility.evidence import CredibilityVerdict
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import MultiphysicsRuntime
from engcore.materials import FluidIdentity, MaterialIdentity, MaterialState
from engcore.materials.properties import PropertyDerivation, ResolvedProperty
from engcore.providers import ProviderRegistry, default_registry
from engcore.scenarios import NamedQuantity
from engcore.scientific.composition.conversion import EnergyConversion
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortRef, RelaxationKind,
    RelaxationPolicy, TimePolicy,
)
from engcore.scientific.multiphysics.state import InitialStateValue
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.twins import ScientificTwin, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport, AuthorityRegistry, Availability, CallbackAuthority, ConstraintObservation, EnvironmentRequirement, ExecutionProfile, InitialStateSpec,
    LiteralInput, MaterialPropertyRef, MultiphysicsAuthority, MultiscaleAuthority, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec, NodeStatus,
    ModelSelection, OutputValue, OwnerState, PreflightStatus, ProviderAuthority, ProviderBinding, ProviderRecordRef, RequestedObservable, RunStatus, RuntimeContext,
    SystemCheckpoint, SystemExecutor, SystemRunRequest, assess_constraints, compare_runs, compile_plan, preflight, trace_result, trust_handoff,
)
from engcore.system_runtime._common import digest_of
from engcore.systems import ComponentConnection, ComponentDefinition, ComponentInstance, ConstraintBinding, SystemDefinition

HERE = pathlib.Path(__file__).parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REG = ProviderRegistry()
try:
    from forge_pybamm import descriptor as pbd
    from forge_tespy import descriptor as tpd
    pbd.register(REG)
    tpd.register(REG)
    OK = REG.status("pybamm").available and REG.status("tespy").available
except ImportError:
    OK = False
pytestmark = pytest.mark.skipif(not OK, reason="PyBaMM and TESPy are both required")

UNKNOWN = Uncertainty.unknown("declared, not quantified")
H = 3600
R_CONTACT = 2.0  # K/W, DECLARED cell-to-coolant thermal resistance (an assumption, not evidence)
DAY = 86400


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ==================================================================================================== shared fixtures
def _refs(pybamm_log, tespy_records):
    """ProviderRecordRefs for what actually executed: last PyBaMM iteration per window, every TESPy record."""
    status = REG.status("pybamm")
    last = {}
    for entry in pybamm_log:
        last[tuple(entry["window"])] = entry
    refs = [ProviderRecordRef("pybamm", status.version, status.digest, e["execution_identity"], "", True) for e in last.values()]
    refs += [ProviderRecordRef.of_record(r) for r in tespy_records]
    return tuple(sorted(set(refs)))


def _coupling():
    pf = _load("test_pybamm_multiphysics")
    env, scenario, p = pf._records()
    cell_spec = pf._spec("cell", [scalar_port("temperature", "input", "temperature", "K"), scalar_port("heat", "output", "heat_rate", "W")],
                         "pybamm", REG.status("pybamm").version)
    cool_spec = pf._spec("coolant", [scalar_port("heat", "input", "heat_rate", "W"), scalar_port("cell_temperature", "output", "temperature", "K")],
                         "tespy", REG.status("tespy").version)
    heat_edge = CouplingEdge("e_heat", PortRef("cell", "heat"), PortRef("coolant", "heat"),
                             conversion=EnergyConversion("cell_heat_to_coolant", "electrochemical", "thermal", "W", efficiency=1.0,
                                                         description="DECLARED: all cell heat enters the coolant stream (no other loss path)"))
    graph = PhysicsGraph("cell-coolant", (cell_spec, cool_spec), (heat_edge, CouplingEdge("e_temp", PortRef("coolant", "cell_temperature"), PortRef("cell", "temperature"))))
    plan = CouplingPlan("cell-coolant-plan", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL, TimePolicy(Quantity(0, "s"), Quantity(H, "s"), Quantity(600, "s")),
                        ("cell", "coolant"), (ConvergenceCriterion("e_heat", 0.0, Quantity(1e-6, "W")), ConvergenceCriterion("e_temp", 0.0, Quantity(1e-6, "K"))),
                        RelaxationPolicy(RelaxationKind.CONSTANT, 0.8), 40, True)
    return pf, env, scenario, p, cell_spec, cool_spec, graph, plan


def _system(graph):
    twins = {n: ScientificTwin(n, "1", TwinKind.CONCEPT) for n in ("pack", "cell", "coolant")}
    definitions = (ComponentDefinition("assembly", "1"), ComponentDefinition("cell", "1", graph.participant("cell").ports),
                   ComponentDefinition("coolant", "1", graph.participant("coolant").ports))
    instances = (ComponentInstance("pack", "assembly", "1", twins["pack"].reference),
                 ComponentInstance("cell", "cell", "1", twins["cell"].reference, parent_id="pack", participant_id="cell"),
                 ComponentInstance("coolant", "coolant", "1", twins["coolant"].reference, parent_id="pack", participant_id="coolant"))
    connections = tuple(ComponentConnection(e.edge_id, e.edge_id, e.source.participant_id, e.source.port_id, e.target.participant_id, e.target.port_id)
                        for e in graph.edges)
    t_max = ConstraintDefinition("max_cell_temperature", "cell_temperature", ConstraintOperator.LESS_EQUAL, Quantity(318.15, "K"))
    soc_min = ConstraintDefinition("min_end_soc", "end_soc", ConstraintOperator.GREATER_EQUAL, Quantity(0.2, "dimensionless"))
    system = SystemDefinition("battery-cooling", "1", definitions, instances, connections,
                              constraint_bindings=(ConstraintBinding("b_tmax", "cell", "max_cell_temperature"), ConstraintBinding("b_soc", "cell", "min_end_soc")),
                              constraints=(t_max, soc_min))
    system.validate_graph(graph)                                            # the topology is exactly the coupling graph
    return system, t_max, soc_min


def _contact_resistance():
    state = MaterialState(MaterialIdentity("aluminium", grade="6061"))
    prop = ResolvedProperty("contact_resistance", "known", PropertyDerivation.ASSUMED,
                            NamedQuantity("contact_resistance", Quantity(R_CONTACT, "K/W")), sha("assumption-set"), sha("assumption-snapshot"), state.digest,
                            (sha("declared-assumption"),), ("assumed",), (), None)
    return state, prop


def coupled_kit(*, soc_lower: float = 0.05, soc_upper: float = 0.95, initial_soc: float = 0.9):
    """The real cell <-> coolant system.  The cell participant is built from the committed state each time the node runs."""
    from forge_pybamm.coupling import cell_participant
    from forge_tespy import ChainProblem, HeatExchangerSpec, TESPyProvider
    pf, env, scenario, p, cell_spec, cool_spec, graph, plan = _coupling()
    system, t_max, soc_min = _system(graph)
    mat_state, resolved = _contact_resistance()
    current_at = lambda start: env.timeline.history("load").value_at(p(start.magnitude_in("s"))).value.value  # noqa: E731
    live: dict = {}

    def factory(call):
        soc0 = call.state.owner("cell").values[0].value.magnitude
        cell_log, tespy_records = [], []
        live.update(cell_log=cell_log, tespy=tespy_records)
        r_contact = call.value("r_contact").to("K/W").magnitude
        cell = cell_participant(REG, cell_spec, parameter_set_name="Chen2020", model="SPM", initial_soc=soc0, current_at=current_at, log=cell_log)
        tespy = TESPyProvider(REG)
        store = InMemoryBulkStore()

        def coolant_solve(inputs, start, end, uq, state):
            inlet = env.channel_value("coolant_inlet", p(start.magnitude_in("s")))
            if inlet.status.value != "known":
                return type("R", (), {"succeeded": False, "reason": "coolant inlet UNKNOWN"})(), {}
            q = inputs["heat"].to("W")
            rec = tespy.solve(ChainProblem("cold-plate", FluidIdentity("water"), Quantity(0.01, "kg/s"), Quantity(2, "bar"), inlet.value.value,
                                           (HeatExchangerSpec("cold_plate", q, 1.0),),
                                           inlet_provenance=(("inlet", hashlib.sha256(repr(inlet.to_dict()).encode()).hexdigest()),)))
            if not rec.succeeded:
                return rec, {}
            tespy_records.append(rec)
            t_mean = 0.5 * (rec.scalars["c1.temperature"].magnitude + rec.scalars["c2.temperature"].magnitude)
            return rec, {"cell_temperature": Quantity(t_mean + q.magnitude * r_contact, "K")}

        coolant = provider_participant(cool_spec, solve=coolant_solve, initial_outputs=lambda: {"cell_temperature": Quantity(298.15, "K")}, store=store,
                                       log=CouplingExecutionLog())
        return MultiphysicsRuntime(graph, plan, {"cell": cell, "coolant": coolant}, resolver=BulkDataResolver(store), store=store)

    def run_kwargs(call):
        u = Uncertainty.unknown("declared initial iterate")
        return dict(external_inputs={}, initial_coupling_values={"e_heat": Quantity(0.1, "W"), "e_temp": Quantity(298.15, "K")},
                    initial_coupling_uncertainty={"e_heat": u, "e_temp": u}, scenario_digest=scenario.digest)

    def applicability(run, call):
        soc = [t for t in run.state_transitions if t.participant_id == "cell"][-1].end_values[0].value.magnitude
        status = "within" if soc_lower <= soc <= soc_upper else "outside"
        return (ApplicabilityReport("soc_window", status, digest_of({"soc": soc, "bounds": [soc_lower, soc_upper]}),
                                    f"end SOC {soc:.4f} against the declared window [{soc_lower}, {soc_upper}]"),)

    authority = MultiphysicsAuthority(
        "battery-cooling-coupled", graph=graph, plan=plan, runtime_factory=factory, run_kwargs=run_kwargs,
        outputs={"cell_temperature": "coolant.cell_temperature"}, state_outputs={"soc": ("cell", "soc")},
        state_owners={"cell": "cell"}, applicability=applicability, providers=lambda run: _refs(live["cell_log"], live["tespy"]),
        config={"cell_model": "PyBaMM SPM Chen2020 isothermal at the coupled temperature", "coolant_model": "TESPy water cold plate",
                "declared_contact_resistance_K_per_W_source": "material node (ASSUMED)", "environment": env.digest,
                "load": digest_of([e.to_dict() for e in env.timeline.history("load").entries]),
                "soc_window": [soc_lower, soc_upper]})
    pb, ts = REG.status("pybamm"), REG.status("tespy")
    node = NodeSpec(
        "coupled", NodeKind.MULTIPHYSICS_EXECUTION, authority.ref, (NodeOutputSpec("cell_temperature", "K"), NodeOutputSpec("soc", "dimensionless")),
        inputs=(), provider_binding_ids=("pybamm_cell", "tespy_coolant"),
        material_refs=(MaterialPropertyRef("r_contact", "coolant", "contact_resistance", resolved.digest, "K/W"),),
        commits_state=True, writes_owners=("cell",), applicability_checks=("soc_window",), checkpointable=True,
        configuration_digest=digest_of({"graph": graph.fingerprint(), "plan": plan.fingerprint(), "scenario": scenario.digest}))
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("cell", "component", (InitialStateValue("soc", Quantity(initial_soc, "dimensionless"),
                                                                                                       Uncertainty.unknown("declared initial state of charge")),)),),
                               (("coolant", mat_state.digest),))
    request = SystemRunRequest.build(
        request_id="battery-cooling-hour", system=system, scenario=scenario, timeline=env.timeline, environment=env, initial_state=initial, nodes=(node,),
        observables=(RequestedObservable("cell_temperature_final", "coupled", "cell_temperature", "K"), RequestedObservable("end_soc", "coupled", "soc", "dimensionless")),
        materials=(mat_state,), model_selections=(ModelSelection("cell", "pybamm-spm-chen2020", pb.version), ModelSelection("coolant", "tespy-cold-plate-water", ts.version)),
        provider_bindings=(ProviderBinding("pybamm_cell", "pybamm", pb.version, pb.digest), ProviderBinding("tespy_coolant", "tespy", ts.version, ts.digest)),
        constraint_observations=(ConstraintObservation("b_tmax", "max_cell_temperature", digest_of(t_max.to_dict()), "cell_temperature_final"),
                                 ConstraintObservation("b_soc", "min_end_soc", digest_of(soc_min.to_dict()), "end_soc")),
        profile=ExecutionProfile(("multiphysics",), "off", True, ("coupled",)))
    context = RuntimeContext(AuthorityRegistry((authority,)), system=system, scenario=scenario, timeline=env.timeline, environment=env,
                             material_states={mat_state.digest: mat_state}, resolved_properties={resolved.digest: resolved},
                             constraints={digest_of(t_max.to_dict()): t_max, digest_of(soc_min.to_dict()): soc_min}, providers=REG)
    return request, context, authority


# ==================================================================================================== Gate B (+ I, L)
def test_gate_b_pybamm_and_tespy_run_as_one_system_through_the_big9_runtime_and_the_full_trace_holds():
    request, context, authority = coupled_kit()
    plan = compile_plan(request)
    report = preflight(request, plan, context)
    assert report.status is PreflightStatus.DEFERRED_CHECKS, report.to_dict()          # ready; one applicability check is deferred to the solved state
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.status.value, r.reason) for r in result.node_receipts]
    receipt = result.receipt("coupled")
    # the coupling loop is BIG 9's: the runtime only delegated, and the delegated run record is referenced
    assert authority.kind == "multiphysics" and receipt.delegated_record_digest
    assert receipt.node_id == "coupled" and result.trust_inputs.execution_status == "succeeded"
    T = result.observable("cell_temperature_final").value.value.magnitude
    soc = result.observable("end_soc").value.value.magnitude
    assert 295.15 < T < 310 and 0.5 < soc < 0.65                                        # BIG 11 Proof F range: 296.11 K and 0.567
    # both real providers executed and are authorised by explicit bindings (versions from the live registry)
    ids = {(p.provider_id, p.provider_version) for p in receipt.provider_records}
    assert ids == {("pybamm", REG.status("pybamm").version), ("tespy", REG.status("tespy").version)}
    pybamm_refs = [r for r in receipt.provider_records if r.provider_id == "pybamm"]
    tespy_refs = [r for r in receipt.provider_records if r.provider_id == "tespy"]
    assert len(pybamm_refs) == 6 and len(tespy_refs) > 6                                # PyBaMM: last iteration of each of 6 windows; TESPy: every iteration's solve
    assert all(r.succeeded and r.execution_identity_digest for r in receipt.provider_records)
    # state committed once, atomically: SOC fell from 0.9 and is the value the observable reports
    assert len(result.state_history) == 2 and result.final_state.owner("cell").values[0].value.magnitude == pytest.approx(soc)
    assert result.final_state.time.magnitude_in("second") == pytest.approx(H)
    # engineering checks on the real numbers (constraint assessment is not validation)
    a = {c.binding_id: c for c in assess_constraints(result, context.system, context.constraints)}
    assert a["b_tmax"].status == "satisfied" and a["b_soc"].status == "satisfied"
    assert a["b_soc"].check.margin.magnitude == pytest.approx(soc - 0.2)
    # Gate I: the full trace of the final number
    trace = trace_result(result, "cell_temperature_final")
    assert {"result", "node", "authority", "execution_record", "provider", "provider_execution", "material", "state", "system", "scenario", "timeline",
            "environment", "configuration"} <= set(trace.levels()), trace.levels()
    assert trace.complete, trace.gaps
    # Gate L: execution succeeded, and that is all it says
    handoff = trust_handoff(result, request)
    assert handoff.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE
    assert result.trust_inputs.validation_evidence == ()
    assert set(result.trust_inputs.provider_execution_identities) == {r.execution_identity_digest for r in receipt.provider_records}
    print("GATE_B", {"T_K": round(T, 3), "soc": round(soc, 4), "wall_s": round(receipt.resource_usage.wall_seconds, 1), "records": len(receipt.provider_records)})


def test_the_result_of_the_real_system_round_trips_and_a_tampered_real_result_is_refused():
    from engcore.system_runtime import SystemRunResult
    request, context, authority = coupled_kit()
    result = SystemExecutor(context).run(request)
    wire = json.loads(json.dumps(result.to_dict()))
    assert SystemRunResult.from_dict(wire).digest == result.digest
    wire["observables"][0]["value"]["value"]["magnitude"] += 5.0
    with pytest.raises(Exception, match="does not carry the value"):
        SystemRunResult.from_dict(wire)


# ==================================================================================================== Gate H (real)
def test_gate_h_a_real_solved_state_that_leaves_applicability_is_not_committed_and_blocks_downstream():
    request, context, authority = coupled_kit(soc_lower=0.6)                            # the solved end SOC (~0.567) is below the declared window
    result = SystemExecutor(context).run(request)
    receipt = result.receipt("coupled")
    assert receipt.status is NodeStatus.REFUSED and "left applicability" in receipt.reason and "soc_window" in receipt.reason
    assert len(result.state_history) == 1 and result.final_state.owner("cell").values[0].value.magnitude == pytest.approx(0.9)    # previous state authoritative
    assert result.observable("end_soc").availability is Availability.BLOCKED or result.observable("end_soc").availability is Availability.REFUSED
    assert result.observable("cell_temperature_final").value is None and result.node_outputs.get("coupled") is None
    assert result.receipt("constraint.b_tmax").status is NodeStatus.BLOCKED and result.receipt("constraint.b_soc").status is NodeStatus.BLOCKED
    assert [c.status for c in assess_constraints(result, context.system, context.constraints)] == ["unavailable", "unavailable"]
    assert receipt.applicability[0].status == "outside" and receipt.state_after_digest == ""


# ==================================================================================================== Gate G (real)
def test_gate_g_a_required_provider_that_is_not_installed_refuses_and_pybamm_is_not_substituted():
    request, context, authority = coupled_kit()
    registry = default_registry()                                                         # every known adapter; CalculiX is not in this environment
    assert not registry.status("calculix").available
    node = replace(request.nodes[0], provider_binding_ids=("pybamm_cell", "tespy_coolant", "structural"))
    bindings = request.provider_bindings + (ProviderBinding("structural", "calculix", "2.23"),)
    request = replace(request, nodes=(node,), provider_bindings=bindings)
    context.providers = registry
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.REFUSED
    assert any(f.code == "PROVIDER_UNAVAILABLE" and "calculix" in f.message and "no substitute" in f.message for f in result.preflight.findings)
    assert result.node_outputs == {} and all(r.status is not NodeStatus.SUCCEEDED for r in result.node_receipts)   # nothing ran, nothing was substituted


# ==================================================================================================== Gate A (real, single provider)
def test_gate_a_one_real_provider_request_to_result_to_receipt_to_trace():
    from forge_tespy import ChainProblem, HeatExchangerSpec, TESPyProvider
    pf, env, scenario, p, cell_spec, cool_spec, graph, plan = _coupling()
    system, _, _ = _system(graph)
    tespy = TESPyProvider(REG)
    Q = 500.0

    def solve(call):
        inlet = call.inputs["inlet"]
        return tespy.solve(ChainProblem("cold-plate", FluidIdentity("water"), Quantity(0.01, "kg/s"), Quantity(2, "bar"), inlet.value,
                                        (HeatExchangerSpec("cold_plate", call.value("heat").to("W"), 1.0),),
                                        inlet_provenance=(("inlet", inlet.producer_stamp),)))

    ts = REG.status("tespy")
    authority = ProviderAuthority("tespy-cold-plate", REG, "tespy", solve, {"outlet_temperature": "c2.temperature"}, config={"fluid": "water", "mass_flow": "0.01 kg/s"})
    node = NodeSpec("chain", NodeKind.PROVIDER_EXECUTION, authority.ref, (NodeOutputSpec("outlet_temperature", "K"),),
                    literals=(LiteralInput("heat", Quantity(Q, "W"), UNKNOWN),), provider_binding_ids=("tespy",),
                    environment_requirements=(EnvironmentRequirement("inlet", "coolant_inlet", Quantity(0, "s"), "K"),),
                    configuration_digest=digest_of({"problem": "cold-plate", "fluid": "water", "heat_W": Q}))
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("cell", "component", (InitialStateValue("soc", Quantity(0.9, "dimensionless"), UNKNOWN),)),))
    request = SystemRunRequest.build(request_id="cold-plate", system=system, scenario=scenario, timeline=env.timeline, environment=env, initial_state=initial,
                                     nodes=(node,), observables=(RequestedObservable("outlet_temperature", "chain", "outlet_temperature", "K"),),
                                     model_selections=(ModelSelection("cell", "pybamm-spm-chen2020", REG.status("pybamm").version),
                                                       ModelSelection("coolant", "tespy-cold-plate-water", ts.version)),
                                     provider_bindings=(ProviderBinding("tespy", "tespy", ts.version, ts.digest),))
    context = RuntimeContext(AuthorityRegistry((authority,)), system=system, scenario=scenario, timeline=env.timeline, environment=env, providers=REG)
    result = SystemExecutor(context).run(request)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.reason) for r in result.node_receipts]
    outlet = result.observable("outlet_temperature").value.value.magnitude
    inlet = result.node_outputs["env.chain.inlet"]["value"].value.magnitude
    assert inlet == pytest.approx(293.15) and 303.0 < outlet < 306.5                     # 500 W into 0.01 kg/s of water: about +12 K
    (ref,) = result.receipt("chain").provider_records
    assert (ref.provider_id, ref.provider_version) == ("tespy", ts.version) and ref.record_digest and ref.execution_identity_digest
    assert len(result.state_history) == 1                                                 # a node that commits nothing advances nothing
    trace = trace_result(result, "outlet_temperature")
    assert trace.complete and {"provider", "provider_execution", "environment", "configuration"} <= set(trace.levels())
    print("GATE_A", {"inlet_K": round(inlet, 3), "outlet_K": round(outlet, 3)})


# ==================================================================================================== Gate C + E (real, long horizon)
def _multiscale_kit(*, staged: bool, day_nodes: bool):
    """The BIG 10 PyBaMM long-horizon system (56 represented days, 8 resolved) as system nodes."""
    ms = _load("test_pybamm_multiscale")
    env = ms.environment()
    rt, system = ms.build(env)
    slow, fast = ms.states()
    pb = REG.status("pybamm")

    def providers(record):
        refs = set()
        for step in record.steps:
            for res in step.results:
                refs.update(ProviderRecordRef("pybamm", pb.version, pb.digest, rid, rd, True) for rid, rd in zip(res.run_ids, res.run_digests))
        return tuple(sorted(refs))

    fade = lambda r: Quantity(r.final_slow_state["cell"]["capacity_fade"].value.magnitude, "dimensionless")  # noqa: E731
    days = lambda r: Quantity(float(Fraction(r.accounting["represented_seconds"])) / DAY, "day")             # noqa: E731
    horizon_end = env.timeline.horizon.end
    from engcore.scenarios import TimePoint
    half = TimePoint(horizon_end.basis_id, Fraction(28 * DAY))
    extractors = {"final_fade": fade, "represented_days": days}
    if staged:
        stages = {"aging_a": {"until": half, "resume": False}, "aging_b": {"until": None, "resume": True}}
        authority = MultiscaleAuthority("battery-aging-staged", rt, initial_slow_state=slow, initial_fast_state=fast, extractors=extractors,
                                        slow_state_owners={"cell": "cell_slow"}, stages=stages, providers=providers,
                                        config={"fade_model": "ThroughputArrheniusFade k=2e-4/(A h) Ea=30 kJ/mol", "represented_days": 56})
    else:
        authority = MultiscaleAuthority("battery-aging-full", rt, initial_slow_state=slow, initial_fast_state=fast, extractors=extractors,
                                        slow_state_owners={"cell": "cell_slow"}, providers=providers,
                                        config={"fade_model": "ThroughputArrheniusFade k=2e-4/(A h) Ea=30 kJ/mol", "represented_days": 56})
    return ms, env, rt, system, authority, providers


def _aging_request(ms, env, authority, system_def, *, staged: bool, day_nodes: bool, extra_authorities=()):
    outs = (NodeOutputSpec("final_fade", "dimensionless"), NodeOutputSpec("represented_days", "day"))
    common = dict(provider_binding_ids=("pybamm_cell",), commits_state=True, writes_owners=("cell_slow",), applicability_checks=(),
                  applicability_waiver="the aging map is exercised only inside its declared weekly-window policy; this node asserts no runtime applicability bound",
                  configuration_digest=digest_of({"policy": "weekly macro windows", "hierarchy": "cell-aging"}))
    if staged:
        nodes = [NodeSpec("aging_a", NodeKind.MULTISCALE_EXECUTION, authority.ref, outs, checkpointable=True, **common),
                 NodeSpec("aging_b", NodeKind.MULTISCALE_EXECUTION, authority.ref, outs, depends_on=("aging_a",), checkpointable=True, **common)]
        last = "aging_b"
    else:
        nodes = [NodeSpec("aging", NodeKind.MULTISCALE_EXECUTION, authority.ref, outs, checkpointable=True, **common)]
        last = "aging"
    observables = [RequestedObservable("final_fade", last, "final_fade", "dimensionless"), RequestedObservable("represented_days", last, "represented_days", "day")]
    return nodes, observables, last


def _sys_definition():
    twin = lambda n: ScientificTwin(n, "1", TwinKind.CONCEPT).reference  # noqa: E731
    return SystemDefinition("cell-aging-system", "1", (ComponentDefinition("assembly", "1"), ComponentDefinition("cell", "1")),
                            (ComponentInstance("site", "assembly", "1", twin("site")), ComponentInstance("cell", "cell", "1", twin("cell-i"), parent_id="site")))


def _aging_run(*, staged: bool, checkpoint: SystemCheckpoint | None = None, stop_after: str | None = None, day_nodes: bool = False):
    ms, env, rt, system, authority, providers = _multiscale_kit(staged=staged, day_nodes=day_nodes)
    sysdef = _sys_definition()
    nodes, observables, last = _aging_request(ms, env, authority, sysdef, staged=staged, day_nodes=day_nodes)
    pb = REG.status("pybamm")
    extra = []
    if day_nodes:
        # later physics starting from the aged cell: one real PyBaMM day, executed from an explicit fade input
        def day(call):
            from engcore.multiscale import FastExecutionRequest
            fade = call.value("fade").magnitude
            u = Uncertainty.unknown("declared")
            slow_state = {"cell": {"capacity_fade": ms.InitialStateValue("capacity_fade", Quantity(fade, "dimensionless"), u)}}
            # the first resolved day of the horizon (the BIG 11 proof-G construction): the only thing that differs between the two nodes is the fade input
            from engcore.scenarios import TimePoint, TimeWindow
            basis = env.timeline.basis.basis_id
            first = TimeWindow(TimePoint(basis, Fraction(0)), TimePoint(basis, Fraction(DAY)))
            req = FastExecutionRequest("later-day", system.identity.digest, env.timeline.scenario_digest, env.timeline.digest, env.digest, first, slow_state,
                                       {"cell": dict(rt._declared_fast["cell"])}, rt._environment_context(first), rt._usage_context(first))
            res = system.execute(req)
            v = res.series_for("voltage").samples[9].value.magnitude
            ref = ProviderRecordRef("pybamm", pb.version, pb.digest, res.run_ids[0], res.run_digests[0], True)
            return NodeOutcome("succeeded", {"voltage": OutputValue(Quantity(v, "V"), UNKNOWN, "pybamm end of discharge hour")}, provider_records=(ref,),
                               delegated_record_digest=res.digest)
        day_auth = CallbackAuthority("later-day", day, config={"cell": "Chen2020 SPM", "hour": 9}, kind="provider")
        extra.append(day_auth)
        vout = (NodeOutputSpec("voltage", "V"),)
        nodes += [NodeSpec("day_fresh", NodeKind.PROVIDER_EXECUTION, day_auth.ref, vout, literals=(LiteralInput("fade", Quantity(0.0, "dimensionless"), UNKNOWN),),
                           provider_binding_ids=("pybamm_cell",), configuration_digest=digest_of({"day": 0, "counterfactual": "fresh cell"})),
                  NodeSpec("day_aged", NodeKind.PROVIDER_EXECUTION, day_auth.ref, vout, inputs=(NodeInput("fade", last, "final_fade", "dimensionless"),),
                           provider_binding_ids=("pybamm_cell",), configuration_digest=digest_of({"day": 0, "counterfactual": "after aging"}))]
        shift = CallbackAuthority("voltage-shift", lambda c: NodeOutcome("succeeded", {"shift": OutputValue(Quantity(c.value("aged").magnitude - c.value("fresh").magnitude, "V"), UNKNOWN, "difference")}),
                                  config={}, deterministic=True)
        extra.append(shift)
        nodes.append(NodeSpec("shift", NodeKind.AGGREGATE, shift.ref, (NodeOutputSpec("shift", "V"),),
                              inputs=(NodeInput("aged", "day_aged", "voltage", "V"), NodeInput("fresh", "day_fresh", "voltage", "V"))))
        observables.append(RequestedObservable("voltage_shift", "shift", "shift", "V"))
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("cell_slow", "slow", (InitialStateValue("capacity_fade", Quantity(0.0, "dimensionless"),
                                                                                                      Uncertainty.unknown("declared new cell")),)),))
    scn = ms.ScenarioSpecification("cell-duty", "1", Quantity(0, "s"), Quantity(ms.DAYS * DAY, "s"),
                                   segments=(ms.ScenarioSegment("duty", Quantity(0, "s"), Quantity(ms.DAYS * DAY, "s")),))
    request = SystemRunRequest.build(
        request_id="cell-aging", system=sysdef, scenario=scn, timeline=env.timeline, environment=env, initial_state=initial, nodes=tuple(nodes),
        observables=tuple(observables), provider_bindings=(ProviderBinding("pybamm_cell", "pybamm", pb.version, pb.digest),),
        profile=ExecutionProfile(("multiscale", "lifecycle"), "off", True, ("aging_a",) if staged else ()))
    context = RuntimeContext(AuthorityRegistry((authority, *extra)), system=sysdef, scenario=scn, timeline=env.timeline, environment=env, providers=REG)
    executor = SystemExecutor(context)
    result = executor.run(request, stop_after=stop_after, resume=checkpoint)
    return request, context, result, authority


def test_gate_c_a_real_long_horizon_run_degrades_state_that_changes_later_physics():
    request, context, result, authority = _aging_run(staged=False, day_nodes=True)
    assert result.status is RunStatus.SUCCEEDED, [(r.node_id, r.status.value, r.reason) for r in result.node_receipts]
    fade = result.observable("final_fade").value.value.magnitude
    assert 0.02 < fade < 0.1 and result.observable("represented_days").value.value.magnitude == pytest.approx(56.0)
    # the degraded value is the committed authoritative state, and it is what later physics consumed
    assert result.final_state.owner("cell_slow").values[0].value.magnitude == pytest.approx(fade)
    fresh = result.node_outputs["day_fresh"]["voltage"].value.magnitude
    aged = result.node_outputs["day_aged"]["voltage"].value.magnitude
    shift = result.observable("voltage_shift").value.value.magnitude
    assert aged < fresh - 1e-3 and shift == pytest.approx(aged - fresh)                  # the faded cell sits lower at the end of the discharge hours
    assert result.receipt("day_aged").input_digests != result.receipt("day_fresh").input_digests   # different input identity, different execution
    assert result.receipt("aging").delegated_record_digest and result.receipt("aging").provider_records
    trace = trace_result(result, "voltage_shift")
    assert trace.complete, trace.gaps
    assert {"provider", "provider_execution", "state", "system", "scenario", "timeline", "environment"} <= set(trace.levels())
    print("GATE_C", {"fade": round(fade, 5), "v_fresh": round(fresh, 4), "v_aged": round(aged, 4), "shift_V": round(shift, 5),
                     "pybamm_refs": len(result.receipt("aging").provider_records), "wall_s": round(result.receipt("aging").resource_usage.wall_seconds, 1)})


def test_gate_e_real_system_checkpoint_serialize_fresh_runtime_resume_matches_the_uninterrupted_run():
    _, _, full, _ = _aging_run(staged=False)
    assert full.status is RunStatus.SUCCEEDED
    request, context, part1, authority = _aging_run(staged=True, stop_after="aging_a")
    assert part1.status is RunStatus.PAUSED and part1.receipt("aging_b").status is NodeStatus.PENDING
    checkpoint = part1.checkpoints[-1]
    assert checkpoint.complete, checkpoint.incomplete_reason
    payload = next(a for a in checkpoint.authority_checkpoints if a.node_id == "aging_a").payload
    assert payload and "checkpoint" in payload                                            # the BIG 10 MacroCheckpoint travels with the system checkpoint
    wire = json.dumps(checkpoint.to_dict(), sort_keys=True)                               # ---- process boundary: serialize ----
    restored = SystemCheckpoint.from_dict(json.loads(wire))                               # ---- fresh objects: nothing shared with part 1 ----
    request2, context2, resumed, authority2 = _aging_run(staged=True, checkpoint=restored)
    assert resumed.status is RunStatus.SUCCEEDED, [(r.node_id, r.status.value, r.reason) for r in resumed.node_receipts]
    f_full = full.observable("final_fade").value.value.magnitude
    f_resumed = resumed.observable("final_fade").value.value.magnitude
    assert f_resumed == pytest.approx(f_full, rel=1e-12, abs=1e-15)                        # reproducibility of the slow state, exactly
    assert resumed.final_state.owner("cell_slow").values[0].value.magnitude == pytest.approx(f_full, rel=1e-12, abs=1e-15)
    assert resumed.observable("represented_days").value.value.magnitude == pytest.approx(56.0)
    comparison = compare_runs(full, resumed, rel_tol=1e-12)
    assert comparison.classification == "reproducibility_not_validation" and comparison.scientific_validation == "not_assessed"
    print("GATE_E", {"fade_uninterrupted": f_full, "fade_resumed": f_resumed, "abs_diff": abs(f_full - f_resumed),
                     "checkpoint_digest": restored.digest[:16]})


def test_resume_is_refused_when_the_serialized_checkpoint_meets_a_changed_long_horizon_context():
    request, context, part1, authority = _aging_run(staged=True, stop_after="aging_a")
    checkpoint = SystemCheckpoint.from_dict(json.loads(json.dumps(part1.checkpoints[-1].to_dict())))
    request2, context2, _, _ = _aging_run(staged=True, stop_after="aging_a")
    from engcore.system_runtime import ResumeRefused, verify_checkpoint
    changed = replace(request2, initial_state=InitialStateSpec(request2.initial_state.time, (OwnerState("cell_slow", "slow", (InitialStateValue(
        "capacity_fade", Quantity(0.01, "dimensionless"), UNKNOWN),)),)))
    with pytest.raises(ResumeRefused, match="request changed"):
        verify_checkpoint(checkpoint, changed, compile_plan(changed), (), context2)
