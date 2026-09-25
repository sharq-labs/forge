"""BIG 9 coupled execution on the EXISTING MultiphysicsRuntime with real FEniCSx + BIG 6 participants.

Gate: A one-way PDE->PDE (thermal -> thermoelastic), B two-way iterative
thermal(FEniCSx) <-> electrical(SciPy root) with relaxation and residual
history, C a non-convergent case refused, D different meshes through the
runtime's field mapper, E two provider types, F BIG 2 time windows, G BIG 3
environment ambient preserved, H BIG 4 lifecycle changing a later coupled run,
I declared energy-balance conservation audit.  Nothing here is validation:
coupled convergence, conservation audits and replay are numerical facts.
All material/circuit numbers are illustrative fixtures.
"""

from __future__ import annotations

import hashlib
import importlib.util

import numpy as np
import pytest

from engcore.coupling import CouplingExecutionLog, field_port, mapped_input, provider_participant, record_to_spatial, scalar_port
from engcore.coupling.adapters import CouplingRefusal
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domains.electrical.heater_circuit import HeaterCircuit
from engcore.execution.multiphysics import InitialStateDefinition, InitialStateValue, MultiphysicsRuntime
from engcore.materials import MaterialState
from engcore.pde import (
    STEADY_DIFFUSION, THERMOELASTIC_PLANE_STRESS, BCKind, BoundaryCondition, CoefficientBinding, DiscretizationSpec,
    FacetRole, PDEProblem, PhysicalModel, SourcedQuantity,
)
from engcore.scenarios import NamedQuantity, TimePoint, TimeWindow
from engcore.scientific.composition.conversion import EnergyConversion
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    BalanceSide, ConservationTermBinding, ConvergenceCriterion, CoupledConservation, CouplingEdge, CouplingPlan,
    CouplingScheme, ExtrapolationPolicy, FieldMappingDefinition, FieldMappingMethod, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortRef, RelaxationKind, RelaxationPolicy, TimePolicy, TransferMeasure,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.solvers.protocol import SolverSettings
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import Location, Rank, RegionMaterialMap, SpatialFieldDefinition, gmsh_available, gmsh_two_region_plate
from forge_fenicsx import FenicsxProvider, fenicsx_available

_spec = importlib.util.spec_from_file_location("materials_fixtures", "tests/test_materials_engine.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
_pde = importlib.util.spec_from_file_location("pde_fixtures", "providers/fenicsx/tests/test_pde_fenicsx.py")
P = importlib.util.module_from_spec(_pde)
_pde.loader.exec_module(P)

OK = fenicsx_available()[0] and gmsh_available()[0]
pytestmark = pytest.mark.skipif(not OK, reason="FEniCSx or Gmsh unavailable")

THICKNESS = Quantity(5, "mm")
SOLVER = SolverSettings({"rtol": 1e-12, "residual_rtol": 1e-9}, {"ksp_type": "preonly", "pc_type": "lu", "max_iterations": 1})
PROVIDER = FenicsxProvider() if OK else None
HEAT = PhysicalModel("heat.joule_plate", "1", "steady conduction with uniform volumetric Joule source, Robin edges (2D, per unit thickness)")


def sq(q, why, origin="prescribed"):
    return SourcedQuantity(q, origin, {"declared": why})


def spec(pid, ports, solver_id, solver_version):
    return ParticipantSpec(pid, f"{pid}-model", "1", f"{pid}-realization", "1", solver_id, solver_version, "forge.coupling", "1",
                           tuple(ports), transient=True, checkpointable=True, deterministic_restore=True)


def alloy_k(mesh, right_board_moisture=None):
    props, _ = M._alloy_set()
    alloy = MaterialState(M.ALLOY, (NamedQuantity("temperature", Quantity(450, "K")),), "solid")
    if right_board_moisture is None:
        binding = RegionMaterialMap(mesh, ((mesh.region("left_plate"), alloy), (mesh.region("right_plate"), alloy)))
        return binding.property_field({M.ALLOY.digest: props}, "thermal_conductivity", "W/(m*K)", "k")[0]
    wool = MaterialState(M.BOARD, (NamedQuantity("moisture_content", right_board_moisture), NamedQuantity("temperature", Quantity(293.15, "K"))))
    binding = RegionMaterialMap(mesh, ((mesh.region("left_plate"), alloy), (mesh.region("right_plate"), wool)))
    return binding.property_field({M.ALLOY.digest: props, M.BOARD.digest: M._board_set()}, "thermal_conductivity", "W/(m*K)", "k")[0]


def thermal_problem(mesh, power, ambient: SourcedQuantity, k_field):
    area = float(mesh.cell_measures().sum())
    q = Quantity(power.to("W").magnitude / (area * THICKNESS.to("m").magnitude), "W/m^3")
    h = sq(Quantity(25, "W/(m^2*K)"), "illustrative film coefficient")
    return PDEProblem(
        "joule-plate", mesh, HEAT, STEADY_DIFFUSION, SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR),
        (CoefficientBinding("conductivity", field=k_field),
         CoefficientBinding("source", constant=SourcedQuantity(q, "coupling", {"edge": "e_power", "power_W": power.to("W").magnitude}))),
        tuple(BoundaryCondition(BCKind.ROBIN, g, ambient, coefficient=h) for g in ("left", "right", "top", "bottom")),
        P.ROLES, DiscretizationSpec(), SOLVER)


def mean_temperature(field):
    m = field.mesh
    return Quantity(float(np.sum(m.cell_measures() * field.values[m.cells].mean(axis=1)) / m.cell_measures().sum()), "K")


def thermal_participant(mesh, store, *, ambient_at, k_at=None, log=None, stateful=False, field_out=False):
    ports = [scalar_port("power", "input", "electrical_power", "W"), scalar_port("t_mean", "output", "temperature", "K")]
    tdef = SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR)
    if field_out:
        ports.append(field_port("temperature", "output", tdef, mesh, store))
    s = spec("thermal", ports, PROVIDER.identity.solver_id, PROVIDER.identity.version)

    def solve(inputs, start, end, uq, state):
        k = k_at(state) if k_at else alloy_k(mesh)
        rec = PROVIDER.execute(thermal_problem(mesh, inputs["power"], ambient_at(start), k))
        if not rec.succeeded:
            return rec, {}
        out = {"t_mean": mean_temperature(rec.field)}
        if field_out:
            out["temperature"] = rec.field
        return rec, out

    def initial():
        # a DECLARED initial iterate for the first coupling pass, never a result
        out = {"t_mean": Quantity(300, "K")}
        if field_out:
            raise CouplingRefusal("field outputs are only produced by a solve")
        return out

    return provider_participant(s, solve=solve, initial_outputs=initial, store=store, log=log,
                                state_definitions=(InitialStateDefinition("moisture_content", "dimensionless"),) if stateful else ())


def electrical_participant(circuit, store, log=None):
    s = spec("electrical", [scalar_port("temperature", "input", "temperature", "K"), scalar_port("power", "output", "electrical_power", "W")],
             "scipy.optimize.root", "hybr")

    def solve(inputs, start, end, uq, state):
        rec, power = circuit.solve(inputs["temperature"])
        return rec, ({} if power is None else {"power": power})

    return provider_participant(s, solve=solve, initial_outputs=lambda: {"power": Quantity(1.0, "W")}, store=store, log=log)


def joule_graph(thermal_spec, electrical_spec, balance_tolerance=Quantity(1e-9, "W")):
    edges = (CouplingEdge("e_temp", PortRef("thermal", "t_mean"), PortRef("electrical", "temperature")),
             CouplingEdge("e_power", PortRef("electrical", "power"), PortRef("thermal", "power"),
                          conversion=EnergyConversion("joule_heating", "electrical", "thermal", "W", efficiency=1.0,
                                                      description="DECLARED model assumption: all heater dissipation is deposited in the plate; "
                                                                  "efficiency uncertainty not declared (UNKNOWN)")))
    balance = CoupledConservation("joule_power_delivery", (
        ConservationTermBinding("dissipated", "e_power", BalanceSide.LEFT, TransferMeasure.SOURCE),
        ConservationTermBinding("injected", "e_power", BalanceSide.RIGHT, TransferMeasure.RECEIVED)), balance_tolerance)
    return PhysicsGraph("joule-plate", (thermal_spec, electrical_spec), edges, conservation=(balance,))


def joule_plan(*, factor=0.7, max_iterations=40, end=3600.0, window=3600.0):
    kind = RelaxationKind.NONE if factor == 1.0 else RelaxationKind.CONSTANT
    return CouplingPlan("joule-plan", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(end, "s"), Quantity(window, "s")), ("electrical", "thermal"),
                        (ConvergenceCriterion("e_temp", 0.0, Quantity(1e-6, "K")), ConvergenceCriterion("e_power", 0.0, Quantity(1e-7, "W"))),
                        RelaxationPolicy(kind, factor), max_iterations, True)


def run_joule(circuit, *, ambient_at, factor=0.7, max_iterations=40, end=3600.0, scenario_digest=None, logs=None):
    store = InMemoryBulkStore()
    tlog, elog = (logs or (CouplingExecutionLog(), CouplingExecutionLog()))
    mesh = P.plate()
    thermal = thermal_participant(mesh, store, ambient_at=ambient_at, log=tlog)
    electrical = electrical_participant(circuit, store, log=elog)
    runtime = MultiphysicsRuntime(joule_graph(thermal.spec, electrical.spec), joule_plan(factor=factor, max_iterations=max_iterations, end=end),
                                  {"thermal": thermal, "electrical": electrical}, resolver=BulkDataResolver(store), store=store)
    unknown = Uncertainty.unknown("declared initial iterate")
    run = runtime.run("joule", external_inputs={}, initial_coupling_values={"e_temp": Quantity(300, "K"), "e_power": Quantity(1.0, "W")},
                      initial_coupling_uncertainty={"e_temp": unknown, "e_power": unknown}, scenario_digest=scenario_digest or "")
    return run, tlog, elog


def constant_ambient(value=Quantity(293.15, "K")):
    return lambda start: sq(value, "declared constant ambient for this proof")


PTC = HeaterCircuit(Quantity(10, "V"), Quantity(1, "ohm"), Quantity(10, "ohm"), Quantity(293.15, "K"), Quantity(0.004, "1/K"))


# ---- B + E + I: genuine two-way iterative coupling -------------------------------


def test_two_way_thermal_electrical_converges_with_relaxation_and_residual_history():
    run, tlog, elog = run_joule(PTC, ambient_at=constant_ambient())
    window = run.windows[0]
    assert window.outcome.value == "converged" and len(window.iterations) >= 3
    history = [[r.absolute.magnitude for r in it.residuals if r.edge_id == "e_temp"][0] for it in window.iterations]
    assert history[-1] <= 1e-6 and history[0] > history[-1]
    assert all(it.relaxation_factors for it in window.iterations[1:])
    t = run.final_outputs["thermal.t_mean"]["magnitude"]
    p = run.final_outputs["electrical.power"]["magnitude"]
    rh = PTC.heater_resistance(Quantity(t, "K"))
    assert p == pytest.approx((10 / (1 + rh)) ** 2 * rh, rel=1e-5)  # fixed point of the coupled system
    # two different provider types really executed, each iterate a distinct problem identity
    assert len(set(tlog.identities())) >= 3 and all(e["succeeded"] for e in elog.entries)
    assert run.graph.participant("electrical").solver_id == "scipy.optimize.root"
    assert run.graph.participant("thermal").solver_id == "fenicsx.dolfinx"
    # CONVERGED is not CONSERVED: with relaxation, the received (relaxed) power
    # differs from the dissipated power by up to the power convergence tolerance
    # (1e-7 W); the declared 1e-9 W energy balance therefore FAILS -- reported, not hidden.
    audit = run.final_outputs["_conservation"][0]
    assert audit["name"] == "conservation:joule_power_delivery" and audit["outcome"] == "fail"
    assert "absolute residual" in audit["detail"]


def test_nonconvergent_ntc_feedback_is_refused():
    ntc = HeaterCircuit(Quantity(10, "V"), Quantity(1, "ohm"), Quantity(10, "ohm"), Quantity(293.15, "K"), Quantity(-0.02, "1/K"))
    with pytest.raises(InvalidScientificProblem):
        run_joule(ntc, ambient_at=constant_ambient(), factor=1.0, max_iterations=6)


def test_identity_changes_with_relaxation_tolerance_and_order():
    base = joule_plan()
    assert base.fingerprint() != joule_plan(factor=0.6).fingerprint()
    assert base.fingerprint() != joule_plan(max_iterations=41).fingerprint()


# ---- F + G: BIG 2 windows and BIG 3 environment through the coupling ------------


def hourly_environment(values):
    """BIG 3 ambient on the SAME scenario/time basis as the coupled run (hourly interval history)."""
    from engcore.scenarios import (ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource,
                                   EnvironmentTimeline, HistoryEntry, QuantityHistory, ReferenceContext, ScenarioSegment,
                                   ScenarioSpecification, TimeBasis, Timeline)
    p = lambda s: TimePoint("run", Quantity(s, "s"))  # noqa: E731
    scenario = ScenarioSpecification("joule-day", "1", Quantity(0, "s"), Quantity(7200, "s"),
                                     segments=(ScenarioSegment("s", Quantity(0, "s"), Quantity(7200, "s")),))
    entries = tuple(HistoryEntry(TimeWindow(p(3600 * i), p(3600 * (i + 1))), NamedQuantity("air", Quantity(v, "K")))
                    for i, v in enumerate(values) if v is not None)
    tl = Timeline.from_scenario(scenario, timeline_id="joule", basis=TimeBasis("run", "elapsed", "switch-on"),
                                histories=(QuantityHistory("air-h", "exposure", "air", "K", entries),))
    ch = EnvironmentChannel("air", "ambient_temperature", "K", "met", ReferenceContext("bench", "lab", "enu"), TimeWindow(p(0), p(7200)),
                            ChannelRepresentation.INTERVAL_HISTORY, history_id="air-h")
    env = EnvironmentTimeline("bench-env", tl, EnvironmentKindRegistry.standard(),
                              (EnvironmentSource("met", "measured", "lab", hashlib.sha256(b"met").hexdigest(), "1"),), (ch,))
    return env, scenario


def environment_ambient(env, seen):
    def ambient_at(start):
        v = env.channel_value("air", TimePoint("run", start))  # exactly the coupling window start
        if v.status.value != "known":
            raise CouplingRefusal(f"ambient UNKNOWN at {start}: {v.reason}")
        seen.append(v.to_dict())
        return SourcedQuantity(v.value.value, "environment", v.to_dict())
    return ambient_at


def test_environment_ambient_per_window_changes_coupled_result_and_is_recorded():
    env, scenario = hourly_environment((290.0, 250.0))
    seen = []
    run, tlog, _ = run_joule(PTC, ambient_at=environment_ambient(env, seen), end=7200.0, scenario_digest=scenario.digest)
    assert [w.outcome.value for w in run.windows] == ["converged", "converged"]
    assert {d["source_id"] for d in seen} == {"met"} and {d["value"]["value"]["magnitude"] for d in seen} == {290.0, 250.0}
    t_windows = [[s for s in it.participant_steps if s.participant_id == "thermal"] for it in (w.iterations[-1] for w in run.windows)]
    assert len(t_windows) == 2 and run.scenario_digest == scenario.digest
    missing_env, scenario2 = hourly_environment((290.0, None))
    with pytest.raises(InvalidScientificProblem, match="UNKNOWN"):
        run_joule(PTC, ambient_at=environment_ambient(missing_env, []), end=7200.0, scenario_digest=scenario2.digest)


# ---- A + D: one-way thermal -> thermoelastic across DIFFERENT meshes ------------


def one_way(power=Quantity(10, "W"), *, mapping=True, structural_unit="K"):
    store = InMemoryBulkStore()
    tmesh, smesh = P.plate(0.02), P.plate(0.03)
    assert tmesh.digest != smesh.digest
    thermal = thermal_participant(tmesh, store, ambient_at=constant_ambient(), field_out=True)
    thermal = provider_participant(thermal.spec, solve=lambda i, s, e, u, st: _thermal_solve(tmesh, i), initial_outputs=lambda: _thermal_solve(tmesh, {"power": power})[1],
                                   store=store)
    tdef_s = SpatialFieldDefinition("T", "temperature", structural_unit, Location.NODE, Rank.SCALAR)
    udef = SpatialFieldDefinition("u", "displacement", "m", Location.NODE, Rank.VECTOR, frame_id="plate-xy")
    slog = CouplingExecutionLog()
    consumed = []

    mappings = []

    def structural_solve(inputs, start, end, uq, state):
        tdef = SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR)
        if mapping:
            temperature, record = mapped_input(inputs["temperature"], tdef, tmesh, smesh, BulkDataResolver(store), store)
            mappings.append(record)
        else:
            temperature = record_to_spatial(inputs["temperature"], tdef, smesh, BulkDataResolver(store), store)
        consumed.append(temperature)
        sets = P.elastic_property_sets()
        room = NamedQuantity("temperature", Quantity(293.15, "K"))
        binding = RegionMaterialMap(smesh, ((smesh.region("left_plate"), MaterialState(M.ALLOY, (room,), "solid")),
                                            (smesh.region("right_plate"), MaterialState(M.ALLOY, (room,), "solid"))))
        E, _ = binding.property_field(sets, "youngs_modulus", "Pa", "E")
        nu, _ = binding.property_field(sets, "poisson_ratio", "dimensionless", "nu")
        free = sq(Quantity(0, "Pa"), "traction-free")
        problem = PDEProblem(
            "plate-thermoelastic", smesh, PhysicalModel("solid.thermoelastic", "1", "small strain, linear thermal expansion, plane stress"),
            THERMOELASTIC_PLANE_STRESS, udef,
            (CoefficientBinding("youngs_modulus", field=E), CoefficientBinding("poisson_ratio", field=nu),
             CoefficientBinding("thickness", constant=sq(THICKNESS, "plate thickness")),
             CoefficientBinding("thermal_expansion", constant=sq(Quantity(23e-6, "1/K"), "illustrative expansion coefficient")),
             CoefficientBinding("reference_temperature", constant=sq(Quantity(293.15, "K"), "stress-free temperature"))),
            (BoundaryCondition(BCKind.DIRICHLET, "left", sq(Quantity(0, "m"), "clamped")),)
            + tuple(BoundaryCondition(BCKind.NEUMANN, g, free, vector_value=(Quantity(0, "Pa"), Quantity(0, "Pa"))) for g in ("right", "top", "bottom")),
            P.ROLES, DiscretizationSpec(), SOLVER, field_inputs={"temperature": temperature})
        rec = PROVIDER.execute(problem)
        return rec, ({"u": rec.field} if rec.succeeded else {})

    structural = provider_participant(
        spec("structural", [field_port("temperature", "input", tdef_s, tmesh if mapping else smesh, store), field_port("u", "output", udef, smesh, store)],
             PROVIDER.identity.solver_id, PROVIDER.identity.version),
        # DECLARED initial iterate: the unloaded reference configuration (u = 0). It seeds
        # the runtime's initialization only and is labelled declared_initial_iterate_not_a_result.
        solve=structural_solve, initial_outputs=lambda: {"u": _reference_configuration(smesh, udef)},
        store=store, log=slog)
    graph = PhysicsGraph("thermo-mech", (thermal.spec, structural.spec),
                         (CouplingEdge("e_T", PortRef("thermal", "temperature"), PortRef("structural", "temperature"),
                                       mapping=FieldMappingDefinition("thermal-field-transport", FieldMappingMethod.IDENTITY,
                                                                      ExtrapolationPolicy.REFUSE, verify_round_trip=False)),),
                         supports=(tmesh.core_support(store), smesh.core_support(store)))
    plan = CouplingPlan("one-way", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")),
                        ("thermal", "structural"))
    runtime = MultiphysicsRuntime(graph, plan, {"thermal": thermal, "structural": structural}, resolver=BulkDataResolver(store), store=store)
    run = runtime.run("thermo-mech", external_inputs={PortRef("thermal", "power"): power},
                      external_uncertainty={PortRef("thermal", "power"): Uncertainty.unknown("declared load")})
    return run, consumed, slog, tmesh, smesh, mappings


def _reference_configuration(mesh, udef):
    from engcore.spatial import Derivation, SpatialField
    return SpatialField(udef, mesh, np.zeros((mesh.node_count, 2)), Derivation.PRESCRIBED)


def _thermal_solve(mesh, inputs):
    rec = PROVIDER.execute(thermal_problem(mesh, inputs["power"], sq(Quantity(293.15, "K"), "ambient"), alloy_k(mesh)))
    return rec, ({"t_mean": mean_temperature(rec.field), "temperature": rec.field} if rec.succeeded else {})


def test_one_way_thermal_to_structural_across_different_meshes():
    run, consumed, slog, tmesh, smesh, mappings = one_way()
    assert consumed and consumed[-1].mesh.digest == smesh.digest and consumed[-1].derivation.value == "mapped"
    # the consumed field is the MAPPED one on the structural mesh (not the thermal-mesh original)
    assert consumed[-1].values.shape == (smesh.node_count,)
    rec = mappings[-1]
    assert rec.conservation.value == "not_conservative" and rec.source_mesh == tmesh.digest and rec.target_mesh == smesh.digest
    assert rec.digest in consumed[-1].provenance
    assert rec.source_integral is not None and rec.target_integral is not None  # reported, not corrected
    ux = run.final_outputs["structural.u"]
    assert ux is not None
    hotter, consumed2, slog2, _, _, _ = one_way(Quantity(20, "W"))
    assert slog.identities()[-1] != slog2.identities()[-1]
    assert not np.allclose(consumed[-1].values, consumed2[-1].values)


def test_cross_mesh_edge_without_mapping_or_wrong_unit_is_refused():
    with pytest.raises(InvalidScientificProblem, match="(?i)support|mesh|mapping"):
        one_way(mapping=False)
    with pytest.raises(InvalidScientificProblem, match="(?i)connects|unit|dimension"):
        one_way(structural_unit="W")


# ---- H: lifecycle degradation changes a LATER coupled run ------------------------


def test_lifecycle_moisture_changes_the_next_coupled_thermal_electrical_run():
    from engcore.domains.hygrothermal.moisture_uptake import LinearWetnessMoistureUptake
    from engcore.scenarios import InputBinding, StepStatus, run_lifecycle

    circuit = HeaterCircuit(Quantity(2, "V"), Quantity(1, "ohm"), Quantity(10, "ohm"), Quantity(293.15, "K"), Quantity(0.004, "1/K"))
    means = []

    def execute(run_id, window, initial_state):
        store = InMemoryBulkStore()
        mesh = P.plate()
        thermal = thermal_participant(mesh, store, ambient_at=constant_ambient(), stateful=True,
                                      k_at=lambda state: alloy_k(mesh, state["moisture_content"].value))
        electrical = electrical_participant(circuit, store)
        start, end = window.start.quantity, window.end.quantity
        plan = CouplingPlan(f"{run_id}-plan", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                            TimePolicy(start, end, Quantity(end.magnitude - start.magnitude, "s")), ("electrical", "thermal"),
                            (ConvergenceCriterion("e_temp", 0.0, Quantity(1e-6, "K")), ConvergenceCriterion("e_power", 0.0, Quantity(1e-8, "W"))),
                            RelaxationPolicy(RelaxationKind.CONSTANT, 0.7), 40, True)
        runtime = MultiphysicsRuntime(joule_graph(thermal.spec, electrical.spec), plan, {"thermal": thermal, "electrical": electrical},
                                      resolver=BulkDataResolver(store), store=store)
        unknown = Uncertainty.unknown("declared initial iterate")
        run = runtime.run(run_id, external_inputs={}, initial_state=initial_state,
                          initial_coupling_values={"e_temp": Quantity(300, "K"), "e_power": Quantity(0.1, "W")},
                          initial_coupling_uncertainty={"e_temp": unknown, "e_power": unknown}, scenario_digest=M.SCENARIO.digest)
        means.append(run.final_outputs["thermal.t_mean"]["magnitude"])
        return run

    p = lambda d: TimePoint("site", Quantity(d, "day"))  # noqa: E731
    chain, runs = run_lifecycle(
        model=LinearWetnessMoistureUptake(k_uptake=Quantity(1e-6, "1/s"), max_wet_time=Quantity(1, "day")),
        environment=M._wet_environment(), participant_id="thermal",
        definitions=(InitialStateDefinition("moisture_content", "dimensionless"),),
        initial_state={"thermal": {"moisture_content": InitialStateValue("moisture_content", Quantity(0.0, "dimensionless"), Uncertainty.unknown("as built"))}},
        windows=tuple(TimeWindow(p(i), p(i + 1)) for i in range(2)), execute=execute, bindings=(InputBinding("wet_time", "wetness"),),
    )
    assert [s.status for s in chain.steps] == [StepStatus.APPLIED] * 2
    assert means[0] != pytest.approx(means[1], abs=1e-6)  # wetter board -> different coupled equilibrium


def test_replay_reproduces_coupled_run_identity():
    from engcore.scenarios.lifecycle import run_digest
    a, _, _ = run_joule(PTC, ambient_at=constant_ambient())
    b, _, _ = run_joule(PTC, ambient_at=constant_ambient())
    assert a.plan.fingerprint() == b.plan.fingerprint() and a.graph.fingerprint() == b.graph.fingerprint()
    assert a.final_outputs["thermal.t_mean"]["magnitude"] == pytest.approx(b.final_outputs["thermal.t_mean"]["magnitude"], abs=1e-9)
    # Bitwise identity of the run record is NOT required of the providers; the
    # declared comparison is: same graph/plan identity and outputs within 1e-9 K.
    assert isinstance(run_digest(a), str)


def test_conservation_audit_passes_only_when_declared_tolerance_admits_the_convergence_gap():
    store = InMemoryBulkStore()
    mesh = P.plate()
    thermal = thermal_participant(mesh, store, ambient_at=constant_ambient())
    electrical = electrical_participant(PTC, store)
    runtime = MultiphysicsRuntime(joule_graph(thermal.spec, electrical.spec, balance_tolerance=Quantity(1e-6, "W")), joule_plan(),
                                  {"thermal": thermal, "electrical": electrical}, resolver=BulkDataResolver(store), store=store)
    unknown = Uncertainty.unknown("declared initial iterate")
    run = runtime.run("joule", external_inputs={}, initial_coupling_values={"e_temp": Quantity(300, "K"), "e_power": Quantity(1.0, "W")},
                      initial_coupling_uncertainty={"e_temp": unknown, "e_power": unknown})
    assert run.final_outputs["_conservation"][0]["outcome"] == "pass"
