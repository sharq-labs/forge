"""Proof F (+H environment): PyBaMM cell <-> TESPy coolant stream on the BIG 9 MultiphysicsRuntime.

Cell: isothermal PyBaMM SPM at the coupled temperature -> window-mean heat.
Coolant: TESPy chain (inlet -> cold plate -> outlet) with the cell heat as its
heat input and the inlet temperature from a BIG 3 environment channel; the cell
temperature is the coolant mean temperature + heat x a DECLARED contact
resistance (a quasi-steady thermal assumption, recorded).  Implicit coupling per
window.  Convergence and agreement are numerical facts, not validation.
"""

from __future__ import annotations

import hashlib

import pytest

from engcore.coupling import CouplingExecutionLog, provider_participant, scalar_port
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import MultiphysicsRuntime
from engcore.materials import FluidIdentity
from engcore.providers import ProviderRegistry
from engcore.scenarios import (
    ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource, EnvironmentTimeline, HistoryEntry,
    NamedQuantity, QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline, TimePoint, TimeWindow,
)
from engcore.scientific.composition.conversion import EnergyConversion
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortRef,
    RelaxationKind, RelaxationPolicy, TimePolicy,
)
from engcore.scientific.units.quantity import Quantity

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
R_CONTACT = Quantity(2.0, "K/W")  # DECLARED cell-to-coolant thermal resistance (illustrative)
H = 3600


def _records():
    p = lambda s: TimePoint("pack", Quantity(s, "s"))  # noqa: E731
    scenario = ScenarioSpecification("pack-hour", "1", Quantity(0, "s"), Quantity(H, "s"), segments=(ScenarioSegment("s", Quantity(0, "s"), Quantity(H, "s")),))
    inlet = QuantityHistory("inlet-h", "exposure", "coolant_inlet", "K", tuple(
        HistoryEntry(TimeWindow(p(600 * i), p(600 * (i + 1))), NamedQuantity("coolant_inlet", Quantity(v, "K"))) for i, v in enumerate((293.15, 293.15, 295.15, 297.15, 297.15, 295.15))))
    load = QuantityHistory("load", "usage", "cell_current", "A", tuple(
        HistoryEntry(TimeWindow(p(600 * i), p(600 * (i + 1))), NamedQuantity("cell_current", Quantity(v, "A"))) for i, v in enumerate((10.0, 10.0, 0.0, 0.0, -5.0, -5.0))))
    tl = Timeline.from_scenario(scenario, timeline_id="pack", basis=TimeBasis("pack", "elapsed", "start"), histories=(inlet, load))
    ch = EnvironmentChannel("coolant_inlet", "ambient_temperature", "K", "chiller", ReferenceContext("loop", "bench", "enu"), TimeWindow(p(0), p(H)),
                            ChannelRepresentation.INTERVAL_HISTORY, history_id="inlet-h")
    env = EnvironmentTimeline("pack-env", tl, EnvironmentKindRegistry.standard(),
                              (EnvironmentSource("chiller", "design_assumption", "BIG 11 declared chiller schedule", hashlib.sha256(b"chiller").hexdigest(), "1"),), (ch,))
    return env, scenario, p


def _spec(pid, ports, solver, version):
    return ParticipantSpec(pid, f"{pid}-model", "1", f"{pid}-real", "1", solver, version, "forge.coupling", "1", tuple(ports),
                           transient=True, checkpointable=True, deterministic_restore=True)


def test_proof_f_pybamm_and_tespy_couple_through_the_big9_runtime():
    from forge_pybamm.coupling import cell_participant
    from forge_tespy import ChainProblem, HeatExchangerSpec, TESPyProvider
    env, scenario, p = _records()
    store = InMemoryBulkStore()
    cell_log, env_seen = [], []
    cell_spec = _spec("cell", [scalar_port("temperature", "input", "temperature", "K"), scalar_port("heat", "output", "heat_rate", "W")],
                      "pybamm", REG.status("pybamm").version)
    cool_spec = _spec("coolant", [scalar_port("heat", "input", "heat_rate", "W"), scalar_port("cell_temperature", "output", "temperature", "K")],
                      "tespy", REG.status("tespy").version)
    current_at = lambda start: env.timeline.history("load").value_at(p(start.magnitude_in("s"))).value.value  # noqa: E731
    cell = cell_participant(REG, cell_spec, parameter_set_name="Chen2020", model="SPM", initial_soc=0.9, capacity_fade=0.0, current_at=current_at, log=cell_log)
    tespy = TESPyProvider(REG)

    def coolant_solve(inputs, start, end, uq, state):
        inlet = env.channel_value("coolant_inlet", p(start.magnitude_in("s")))
        if inlet.status.value != "known":
            return type("R", (), {"succeeded": False, "reason": "coolant inlet UNKNOWN"})(), {}
        env_seen.append(inlet.to_dict())
        q = inputs["heat"].to("W")
        rec = tespy.solve(ChainProblem("cold-plate", FluidIdentity("water"), Quantity(0.01, "kg/s"), Quantity(2, "bar"), inlet.value.value,
                                       (HeatExchangerSpec("cold_plate", q, 1.0),),
                                       inlet_provenance=(("inlet", hashlib.sha256(repr(inlet.to_dict()).encode()).hexdigest()),)))
        if not rec.succeeded:
            return rec, {}
        t_mean = 0.5 * (rec.scalars["c1.temperature"].magnitude + rec.scalars["c2.temperature"].magnitude)
        return rec, {"cell_temperature": Quantity(t_mean + q.magnitude * R_CONTACT.magnitude, "K")}

    coolant = provider_participant(cool_spec, solve=coolant_solve, initial_outputs=lambda: {"cell_temperature": Quantity(298.15, "K")}, store=store,
                                   log=CouplingExecutionLog())
    heat_edge = CouplingEdge("e_heat", PortRef("cell", "heat"), PortRef("coolant", "heat"),
                             conversion=EnergyConversion("cell_heat_to_coolant", "electrochemical", "thermal", "W", efficiency=1.0,
                                                         description="DECLARED: all cell heat enters the coolant stream (no other loss path)"))
    graph = PhysicsGraph("cell-coolant", (cell_spec, cool_spec), (heat_edge, CouplingEdge("e_temp", PortRef("coolant", "cell_temperature"), PortRef("cell", "temperature"))))
    plan = CouplingPlan("cell-coolant-plan", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL, TimePolicy(Quantity(0, "s"), Quantity(H, "s"), Quantity(600, "s")),
                        ("cell", "coolant"), (ConvergenceCriterion("e_heat", 0.0, Quantity(1e-6, "W")), ConvergenceCriterion("e_temp", 0.0, Quantity(1e-6, "K"))),
                        RelaxationPolicy(RelaxationKind.CONSTANT, 0.8), 40, True)
    runtime = MultiphysicsRuntime(graph, plan, {"cell": cell, "coolant": coolant}, resolver=BulkDataResolver(store), store=store)
    from engcore.scientific.results.uncertainty import Uncertainty
    u = Uncertainty.unknown("declared initial iterate")
    run = runtime.run("cell-coolant", external_inputs={}, initial_coupling_values={"e_heat": Quantity(0.1, "W"), "e_temp": Quantity(298.15, "K")},
                      initial_coupling_uncertainty={"e_heat": u, "e_temp": u}, scenario_digest=scenario.digest)
    assert [w.outcome.value for w in run.windows] == ["converged"] * 6
    assert sum(len(w.iterations) for w in run.windows) > 6  # genuine two-way iteration
    socs = [t.end_values[0].value.magnitude for t in run.state_transitions if t.participant_id == "cell"]
    assert socs[1] < socs[0] < 0.9 and socs[2] == pytest.approx(socs[1]) and socs[5] > socs[3]  # discharge, rest, charge: state progresses
    heats = [e["heat_W"] for e in cell_log]
    assert max(heats) > 0.1 and {d["value"]["value"]["magnitude"] for d in env_seen} == {293.15, 295.15, 297.15}
    t_cell = run.final_outputs["coolant.cell_temperature"]["magnitude"]
    assert 295.15 < t_cell < 310  # above the final coolant inlet: heat flows cell -> coolant
    print("PROOF_F", {"iterations": [len(w.iterations) for w in run.windows], "soc": [round(s, 4) for s in socs],
                      "final_heat_W": round(heats[-1], 4), "final_cell_T_K": round(t_cell, 3)})
