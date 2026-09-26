"""FLAGSHIP A - a liquid-cooled cell module over a 57-day declared operating profile, with degradation feeding back.

Engineering question
    How does a declared cell/cooling system behave over a long operating period under a declared usage and
    environment profile, and how does the degradation accumulated over that period change its LATER electrical
    and thermal behaviour?

System (one BIG 12 request)
    day_fresh    real PyBaMM cell <-> real TESPy cold plate on the BIG 9 coupling runtime, one operating day, new cell
    aging        the same coupled day as a BIG 10 FAST system inside a 56-day multi-timescale run (4 days resolved
                 of 56 represented, 14-day macro steps), BIG 4 throughput/temperature fade
                 commits the slow state ``capacity_fade``
    day_aged     the coupled day again at day 56, cell built from the COMMITTED fade
    day_control  the identical day-56 window with a NEW cell: isolates the effect of degradation from the effect of
                 the drifting environment
    shift        differences (aged - control = degradation effect, control - fresh = environment drift effect)

Every scenario input (usage current, coolant inlet profile, contact resistance, module multiplicity) is a DECLARED
illustrative fixture - not measured.  Cell parameters are the PyBaMM-bundled Chen2020 literature set (provider data,
content-digested).  This flagship demonstrates system execution, coupling, lifecycle propagation and numerical
behaviour.  It does not validate the battery model: no experimental dataset applicable to this cell was integrated.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import math
import re
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable

import numpy as np

from engcore.coupling import CouplingExecutionLog, provider_participant, scalar_port
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domains.battery.throughput_fade import ThroughputArrheniusFade
from engcore.execution.multiphysics import InitialStateValue, MultiphysicsRuntime
from engcore.materials import FluidIdentity, MaterialIdentity, MaterialState
from engcore.materials.properties import PropertyDerivation, ResolvedProperty
from engcore.multiscale import (
    AdaptationRule, AggregationSpec, FastExecutionResult, FastStateAtMacroStart, FastSystem, FastSystemIdentity, LifecycleBinding, MacroStepPolicy,
    MultiTimescaleRuntime, OutputSample, OutputSeries, RepresentativePolicy, ScaleHierarchy, ScaleLevel, StateChangeLimit, StateOwnership,
)
from engcore.multiscale.fast import slow_state_digest
from engcore.coupling import ParticipantStateContract, StateCompleteness
from engcore.providers import ProviderRefusal
from engcore.scenarios import (
    AggregateForm, ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource, EnvironmentTimeline, HistoryEntry,
    InputBinding, NamedQuantity, QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification, TimeBasis, Timeline, TimePoint, TimeWindow,
)
from engcore.scenarios.lifecycle import HistoryFeature
from engcore.scientific.composition.conversion import EnergyConversion
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortRef, RelaxationKind,
    RelaxationPolicy, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.twins import ScientificTwin, TwinKind
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime import (
    ApplicabilityReport, ArtifactRef, AuthorityRegistry, CallbackAuthority, ConstraintObservation, EnvironmentRequirement, ExecutionProfile, InitialStateSpec, LiteralInput,
    MaterialPropertyRef, ModelSelection, MultiphysicsAuthority, MultiscaleAuthority, NodeInput, NodeKind, NodeOutcome, NodeOutputSpec, NodeSpec,
    OutputValue, OwnerState, ProviderBinding, ProviderRecordRef, RequestedObservable, RuntimeContext, SystemRunRequest,
)
from engcore.system_runtime._common import digest_of
from engcore.systems import ComponentConnection, ComponentDefinition, ComponentInstance, ConstraintBinding, SystemDefinition

DAY, H = 86400, 3600
DAYS_AGED = 56                       # represented aging horizon
HORIZON_DAYS = 57                    # one further day after the aging horizon carries the later-run physics
N_CELLS = 100                        # DECLARED: identical, identically loaded cells in thermal parallel on one cold plate
R_CONTACT_K_PER_W = 2.0              # DECLARED (ASSUMED) cell-to-coolant thermal resistance per cell
MASS_FLOW = 0.02                     # kg/s, DECLARED loop flow
PRESSURE = 2e5                       # Pa
INITIAL_SOC = 0.8                    # DECLARED: the cell is recharged to this state of charge each day
SOC_WINDOW = (0.15, 0.95)            # DECLARED operating window (applicability), not a property of the cell
TEMP_WINDOW_K = (273.15, 333.15)     # DECLARED operating window for the cell temperature (applicability)
TMAX_K = 318.15                      # constraint: 45 degC
FADE_MAX = 0.10                      # constraint: illustrative end-of-life criterion
SOC_MIN_CONSTRAINT = 0.20
FADE_K = 2e-4                        # 1/(A h)   ThroughputArrheniusFade (BIG 11 declared)
FADE_EA = 30.0                       # kJ/mol
PARAMETER_SET = "Chen2020"
MODEL = "SPM"


@dataclass(frozen=True)
class Case:
    """A declared operating case.  Everything below is an assumption of the case, recorded in the request."""

    name: str
    site_air_mean_K: float
    site_air_swing_K: float
    inlet_above_air_K: float          # DECLARED: dry-cooler supply = site air + this offset
    discharge_A: float                # per-cell current in the discharge hour (negative charges)
    soc_window: tuple[float, float] = SOC_WINDOW
    description: str = ""


CASES = {
    "normal": Case("normal", 293.15, 6.0, 2.0, 2.5, description="20 degC mean site air, 0.5 C discharge hour and 0.5 C charge hour"),
    "hot": Case("hot", 313.15, 6.0, 2.0, 2.5, description="40 degC mean site air; the coolant inlet follows the air"),
    "overload": Case("overload", 293.15, 6.0, 2.0, 5.5, description="1.1 C discharge hour from 80 % SOC: more charge than the cell holds"),
    "outside_window": Case("outside_window", 293.15, 6.0, 2.0, 2.5, soc_window=(0.35, 0.95),
                           description="the normal duty against a declared SOC window that the discharge leaves"),
}


def p(seconds) -> TimePoint:
    return TimePoint("site", Fraction(seconds))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ==================================================================================================== environment (BIG 2 / BIG 3)
def build_environment(case: Case):
    hours = HORIZON_DAYS * 24
    air = [round(case.site_air_mean_K + case.site_air_swing_K * math.sin(2 * math.pi * (h % 24 - 9) / 24) + 0.05 * (h // 24), 6) for h in range(hours)]
    inlet = [round(a + case.inlet_above_air_K, 6) for a in air]
    load = [case.discharge_A if h % 24 == 8 else (-case.discharge_A if h % 24 == 14 else 0.0) for h in range(hours)]
    total = HORIZON_DAYS * DAY
    scenario = ScenarioSpecification(f"cell-cooling-{case.name}", "1", Quantity(0, "s"), Quantity(total, "s"),
                                     segments=(ScenarioSegment("duty", Quantity(0, "s"), Quantity(total, "s")),))
    hist = lambda hid, kind, qid, unit, vals: QuantityHistory(hid, kind, qid, unit, tuple(  # noqa: E731
        HistoryEntry(TimeWindow(p(i * H), p((i + 1) * H)), NamedQuantity(qid, Quantity(v, unit))) for i, v in enumerate(vals)))
    timeline = Timeline.from_scenario(scenario, timeline_id=f"cell-cooling-{case.name}", basis=TimeBasis("site", "elapsed", "install"),
                                      histories=(hist("inlet-h", "exposure", "coolant_inlet", "K", inlet), hist("load", "usage", "cell_current", "A", load)))
    channel = EnvironmentChannel("coolant_inlet", "ambient_temperature", "K", "site-cooler", ReferenceContext("loop", "site", "enu"),
                                 TimeWindow(p(0), p(total)), ChannelRepresentation.INTERVAL_HISTORY, history_id="inlet-h")
    source = EnvironmentSource("site-cooler", "design_assumption",
                               "declared diurnal site air profile, drift 0.05 K/day; dry-cooler supply = air + offset (illustrative, not measured)",
                               hashlib.sha256(repr((air, inlet, load)).encode()).hexdigest(), "1")
    return EnvironmentTimeline(f"cell-cooling-env-{case.name}", timeline, EnvironmentKindRegistry.standard(), (source,), (channel,)), scenario


ASSUMPTION_DOCUMENT = {"statement": "cell-to-coolant thermal resistance per cell is DECLARED, not measured or sourced", "value": R_CONTACT_K_PER_W, "unit": "K/W",
                       "basis": "illustrative; chosen so the cell runs a few kelvin above the coolant at the declared heat"}


def contact_resistance():
    state = MaterialState(MaterialIdentity("aluminium", grade="6061"))
    doc = digest_of(ASSUMPTION_DOCUMENT)          # the digest of the declared assumption document itself (its content is above), not a label
    prop = ResolvedProperty("contact_resistance", "known", PropertyDerivation.ASSUMED,
                            NamedQuantity("contact_resistance", Quantity(R_CONTACT_K_PER_W, "K/W")), doc, digest_of({"snapshot": ASSUMPTION_DOCUMENT, "property": "contact_resistance"}),
                            state.digest, (doc,), ("assumed",), (), None)
    return state, prop


# ==================================================================================================== the coupled plant (BIG 9)
def _spec(pid, ports, solver, version):
    return ParticipantSpec(pid, f"{pid}-model", "1", f"{pid}-real", "1", solver, version, "forge.coupling", "1", tuple(ports),
                           transient=True, checkpointable=True, deterministic_restore=True)


class Plant:
    """Builds the real cell <-> coolant coupled runtime over ONE window range.  Stateless: everything comes from its arguments."""

    def __init__(self, registry, environment: EnvironmentTimeline, scenario_digest: str, window_s: int = H) -> None:
        self.registry, self.environment, self.scenario_digest, self.window_s = registry, environment, scenario_digest, window_s
        self.pb, self.ts = registry.status("pybamm"), registry.status("tespy")
        self.cell_spec = _spec("cell", [scalar_port("temperature", "input", "temperature", "K"), scalar_port("heat", "output", "heat_rate", "W")],
                               "pybamm", self.pb.version)
        self.cool_spec = _spec("coolant", [scalar_port("heat", "input", "heat_rate", "W"), scalar_port("cell_temperature", "output", "temperature", "K")],
                               "tespy", self.ts.version)
        heat_edge = CouplingEdge("e_heat", PortRef("cell", "heat"), PortRef("coolant", "heat"),
                                 conversion=EnergyConversion("cell_heat_to_coolant", "electrochemical", "thermal", "W", efficiency=1.0,
                                                             description="DECLARED: all cell heat enters the coolant stream (no other loss path)"))
        self.graph = PhysicsGraph("cell-coolant", (self.cell_spec, self.cool_spec),
                                  (heat_edge, CouplingEdge("e_temp", PortRef("coolant", "cell_temperature"), PortRef("cell", "temperature"))))

    def plan(self, start_s: int, end_s: int) -> CouplingPlan:
        return CouplingPlan("cell-coolant-plan", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                            TimePolicy(Quantity(start_s, "s"), Quantity(end_s, "s"), Quantity(self.window_s, "s")), ("cell", "coolant"),
                            (ConvergenceCriterion("e_heat", 0.0, Quantity(1e-6, "W")), ConvergenceCriterion("e_temp", 0.0, Quantity(1e-6, "K"))),
                            RelaxationPolicy(RelaxationKind.CONSTANT, 0.8), 40, True)

    def configuration(self, r_contact: float) -> dict[str, Any]:
        return {"cell_model": f"PyBaMM {MODEL} {PARAMETER_SET} isothermal at the coupled temperature", "coolant_model": "TESPy water cold plate",
                "n_cells_in_module": N_CELLS, "r_contact_K_per_W": r_contact, "mass_flow_kg_s": MASS_FLOW, "pressure_Pa": PRESSURE,
                "cell_temperature_rule": "coolant mean temperature + cell heat x contact resistance (quasi-steady, declared)",
                "coupling": "implicit serial, relaxation 0.8, tolerances 1e-6 W / 1e-6 K, max 40 iterations",
                "window_s": self.window_s, "initial_iterate": "e_heat 0.1 W, e_temp 298.15 K (declared, seeds iteration 1 only)"}

    def runtime(self, start_s: int, end_s: int, *, soc0: float, fade: float, r_contact: float, load_history: str, cell_log: list, cool_log: list) -> MultiphysicsRuntime:
        from forge_pybamm.coupling import cell_participant
        from forge_tespy import ChainProblem, HeatExchangerSpec, TESPyProvider

        env = self.environment
        current_at = lambda start: env.timeline.history(load_history).value_at(p(start.magnitude_in("s"))).value.value  # noqa: E731
        cell = cell_participant(self.registry, self.cell_spec, parameter_set_name=PARAMETER_SET, model=MODEL, initial_soc=soc0, capacity_fade=fade,
                                current_at=current_at, log=cell_log)
        tespy = TESPyProvider(self.registry)
        store = InMemoryBulkStore()

        def coolant_solve(inputs, start, end, uq, state):
            inlet = env.channel_value("coolant_inlet", p(start.magnitude_in("s")))
            if inlet.status.value != "known":
                return type("R", (), {"succeeded": False, "reason": "coolant inlet UNKNOWN"})(), {}
            q_cell = inputs["heat"].to("W")
            q_module = Quantity(q_cell.magnitude * N_CELLS, "W")
            rec = tespy.solve(ChainProblem("cold-plate", FluidIdentity("water"), Quantity(MASS_FLOW, "kg/s"), Quantity(PRESSURE, "Pa"), inlet.value.value,
                                           (HeatExchangerSpec("cold_plate", q_module, 1.0),),
                                           inlet_provenance=(("inlet", hashlib.sha256(repr(inlet.to_dict()).encode()).hexdigest()),)))
            if not rec.succeeded:
                return rec, {}
            cool_log.append({"window": (start.magnitude_in("s"), end.magnitude_in("s")), "record": rec, "q_cell_W": q_cell.magnitude,
                             "inlet_K": rec.scalars["c1.temperature"].magnitude, "outlet_K": rec.scalars["c2.temperature"].magnitude,
                             "m_dh_W": MASS_FLOW * (rec.scalars["c2.enthalpy"].magnitude - rec.scalars["c1.enthalpy"].magnitude)})
            t_mean = 0.5 * (rec.scalars["c1.temperature"].magnitude + rec.scalars["c2.temperature"].magnitude)
            return rec, {"cell_temperature": Quantity(t_mean + q_cell.magnitude * r_contact, "K")}

        coolant = provider_participant(self.cool_spec, solve=coolant_solve, initial_outputs=lambda: {"cell_temperature": Quantity(298.15, "K")}, store=store,
                                       log=CouplingExecutionLog())
        return MultiphysicsRuntime(self.graph, self.plan(start_s, end_s), {"cell": cell, "coolant": coolant}, resolver=BulkDataResolver(store), store=store)

    def run_kwargs(self) -> dict[str, Any]:
        u = Uncertainty.unknown("declared initial iterate")
        return dict(external_inputs={}, initial_coupling_values={"e_heat": Quantity(0.1, "W"), "e_temp": Quantity(298.15, "K")},
                    initial_coupling_uncertainty={"e_heat": u, "e_temp": u}, scenario_digest=self.scenario_digest)


def _seconds(x) -> float:
    """A window edge from a log: a number, or the repr of one (possibly a Fraction)."""
    if isinstance(x, str):
        m = re.fullmatch(r"Fraction\((-?\d+),\s*(\d+)\)", x.strip())
        x = Fraction(int(m.group(1)), int(m.group(2))) if m else float(x)
    return round(float(x), 6)


@dataclass
class DayTable:
    """The converged (last-iteration) value of every window of one coupled day, and the dense voltage/heat series inside them."""

    rows: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_logs(cls, cell_log: list, cool_log: list) -> "DayTable":
        cell_last: dict[tuple, dict] = {}
        for e in cell_log:
            cell_last[tuple(_seconds(x) for x in e["window"])] = e
        cool_last: dict[tuple, dict] = {}
        for e in cool_log:
            cool_last[tuple(_seconds(x) for x in e["window"])] = e
        rows = []
        for key, e in sorted(cell_last.items()):
            start, end = key
            if key not in cool_last:
                raise ProviderRefusal(f"no coolant solve was logged for the window {key}")
            c = cool_last[key]
            rows.append({"start_s": start, "end_s": end, "current_A": e["current_A"], "cell_T_K": e["T_K"], "heat_W": e["heat_W"], "soc_end": e["soc"],
                         "voltage_mean_V": e["voltage_V_mean"], "voltage_end_V": e["voltage_V_end"], "voltage_min_V": e["voltage_V_min"],
                         "coolant_in_K": c["inlet_K"], "coolant_out_K": c["outlet_K"], "module_heat_removed_W": c["m_dh_W"],
                         "module_heat_generated_W": c["q_cell_W"] * N_CELLS, "series": e["series"], "record": c["record"]})
        return cls(rows)

    def csv_bytes(self) -> bytes:
        """One row per dense PyBaMM point: the histories an engineer plots.  Cell/coolant temperatures are window values (quasi-steady)."""
        buf = io.StringIO(newline="")
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["t_s", "current_A", "voltage_V", "cell_heat_W", "soc", "cell_temperature_K", "coolant_inlet_K", "coolant_outlet_K", "module_heat_removed_W"])
        for r in self.rows:
            s = r["series"]
            for t, v, hw, soc in zip(s["t_s"], s["voltage_V"], s["heat_W"], s["soc"]):
                w.writerow([repr(r["start_s"] + t), repr(r["current_A"]), repr(v), repr(hw), repr(soc), repr(r["cell_T_K"]), repr(r["coolant_in_K"]),
                            repr(r["coolant_out_K"]), repr(r["module_heat_removed_W"])])
        return buf.getvalue().encode("utf-8")


# ==================================================================================================== the coupled day as a BIG 10 fast system
OUTPUTS = (("abs_current", "A"), ("cell_temperature", "K"), ("voltage", "V"), ("heat", "W"), ("coolant_outlet", "K"))
FEATURES = (HistoryFeature.INTEGRAL, HistoryFeature.MEAN, HistoryFeature.DWELL, HistoryFeature.DISTRIBUTION, HistoryFeature.ORDER)


class CoupledCellCoolingFastSystem(FastSystem):
    """The real coupled cell <-> cold-plate day (BIG 9) seen from the slow scale (BIG 10).  Pure: everything comes from the request."""

    def __init__(self, plant: Plant, r_contact: float, r_contact_digest: str) -> None:
        self.plant, self.environment, self.timeline, self.r_contact = plant, plant.environment, plant.environment.timeline, r_contact
        self.executions = 0
        self.refs: dict[str, tuple[ProviderRecordRef, ...]] = {}
        from forge_pybamm import parameter_set
        self.pset, _ = parameter_set(PARAMETER_SET)
        pb, ts = plant.pb, plant.ts
        contracts = (ParticipantStateContract("cell", ("capacity_fade", "soc"), ("soc",), StateCompleteness.DECLARED_COMPLETE,
                                              "each execution builds a fresh PyBaMM simulation from (soc, capacity_fade, window records); the solution vector "
                                              "is not carried between executions - the declared initial state of a day is (soc, coupled T from the first iterate)",
                                              reset_state=("cell_temperature", "particle_concentration_profiles")),
                     ParticipantStateContract("coolant", (), (), StateCompleteness.DECLARED_COMPLETE,
                                              "the coolant is a quasi-steady TESPy solve per window: it carries no state between windows or executions"))
        cfg = plant.configuration(r_contact)
        cfg.update({"parameter_set": self.pset.to_dict(), "contact_resistance_record": r_contact_digest,
                    "outputs": "window means of the converged coupled iteration; voltage/heat means of the dense PyBaMM solution in the window"})
        self.identity = FastSystemIdentity(
            "cell-cooling-coupled-day", "1", plant.graph.fingerprint(), {"plan_template": plant.plan(0, DAY).fingerprint(), "window_s": plant.window_s},
            (("pybamm", pb.version), ("tespy", ts.version)), cfg, contracts, (), OUTPUTS, field_mapping=False,
            field_mapping_basis="scalar coupling edges only; no field is transferred", pure=True,
            purity_basis="every execution builds a fresh MultiphysicsRuntime, fresh participants and fresh provider problems from the request only; "
                         "the declared initial coupling iterates are constants; no warm start",
            participants=("cell", "coolant"), output_semantics=tuple((q, tuple(f.value for f in FEATURES), f"{plant.window_s}/1") for q, _ in OUTPUTS),
            slow_state_use=(("cell", "capacity_fade", "bound", "the cell is rebuilt with the loss-of-active-material mapping of the fade at every execution"),),
            time_inputs_via_request=True,
            time_inputs_basis="the coolant inlet is read from the request window's BIG 3 channel and the cell current from the BIG 2 usage history; "
                              "the configuration holds no time-varying load")

    def execute(self, request) -> FastExecutionResult:
        self.executions += 1
        start_s, end_s = int(request.window.start.seconds), int(request.window.end.seconds)
        soc0 = float(request.fast_state["cell"]["soc"].value.magnitude_in("dimensionless"))
        fade = float(request.slow_state["cell"]["capacity_fade"].value.magnitude_in("dimensionless"))
        cell_log, cool_log = [], []
        rt = self.plant.runtime(start_s, end_s, soc0=soc0, fade=fade, r_contact=self.r_contact, load_history="load", cell_log=cell_log, cool_log=cool_log)
        run = rt.run(f"fast-{start_s}", **self.plant.run_kwargs())
        if any(w.outcome.value != "converged" for w in run.windows):
            raise ProviderRefusal("a coupling window did not converge")
        table = DayTable.from_logs(cell_log, cool_log)
        if len(table.rows) != (end_s - start_s) // self.plant.window_s:
            raise ProviderRefusal("the coupled run did not produce every window")
        unit = dict(OUTPUTS)
        pick = {"abs_current": lambda r: abs(r["current_A"]), "cell_temperature": lambda r: r["cell_T_K"], "voltage": lambda r: r["voltage_mean_V"],
                "heat": lambda r: r["heat_W"], "coolant_outlet": lambda r: r["coolant_out_K"]}
        series = []
        for q, u in OUTPUTS:
            samples = tuple(OutputSample(TimeWindow(p(r["start_s"]), p(r["end_s"])), Quantity(float(pick[q](r)), u)) for r in table.rows)
            series.append(OutputSeries(q, u, samples, digest_of(run.to_dict()), f"means over each {self.plant.window_s} s coupling window", frozenset(FEATURES)))
        from engcore.scientific.multiphysics.receipts import StateVariableValue
        end_state = {"cell": {"soc": StateVariableValue("soc", Quantity(float(table.rows[-1]["soc_end"]), "dimensionless"),
                                                        Uncertainty.unknown("declared coulomb-counting definition"))}}
        pb = self.plant.pb
        refs = [ProviderRecordRef("pybamm", pb.version, pb.digest, e["execution_identity"], "", True) for e in
                {tuple(x["window"]): x for x in cell_log}.values()]
        refs += [ProviderRecordRef.of_record(c["record"]) for c in cool_log]
        result = FastExecutionResult(
            request.identity, (run.run_id,), (digest_of(run.to_dict()),), tuple(series), end_state, (), (), len(run.windows),
            sum(len(w.iterations) for w in run.windows), tuple(w.outcome.value for w in run.windows), self.identity.providers,
            consumed_environment_digest=self.environment.digest, consumed_timeline_digest=self.timeline.digest,
            consumed_slow_state_digest=slow_state_digest(request.slow_state))
        self.refs[result.request_identity] = tuple(sorted(set(refs)))
        return result


def build_multiscale_runtime(system: CoupledCellCoolingFastSystem, env: EnvironmentTimeline, *, macro_days: int = 14) -> MultiTimescaleRuntime:
    hierarchy = ScaleHierarchy("cell-cooling-aging", "1",
                               (ScaleLevel("coupled_window", "fast", Quantity(1, "hour"), "SPM cell <-> cold plate coupling window"),
                                ScaleLevel("duty_day", "operational", Quantity(1, "day"), "one charge/discharge duty day"),
                                ScaleLevel("aging", "slow", Quantity(30, "day"), "throughput/temperature capacity fade")),
                               (StateOwnership("cell", "soc", "fast", "dimensionless"), StateOwnership("cell", "capacity_fade", "slow", "dimensionless")))
    rep = RepresentativePolicy("duty-day", "leading_period", Quantity(1, "day"),
                               ("each represented day repeats the resolved day's current, temperature and voltage history",),
                               "while the duty cycle is 24 h periodic and the coolant inlet drifts by less than the declared tolerance",
                               "throughput scales by the exact weight; mean temperature is weight-invariant",
                               periodicity_tolerances=(("coolant_inlet", Quantity(3, "K")), ("load", Quantity(0, "A"))),
                               fast_state_tolerances=(("cell.soc", Quantity(0.005, "dimensionless")),))
    policy = MacroStepPolicy("cell-macro", "1", (AdaptationRule("default", "default", Quantity(macro_days, "day")),), Quantity(1, "day"), "split", rep,
                             (StateChangeLimit("cell", "capacity_fade", Quantity(0.1, "dimensionless"), 0.5),))
    model = ThroughputArrheniusFade(k_per_ampere_hour=Quantity(FADE_K, "1/(A*h)"), activation_energy=Quantity(FADE_EA, "kJ/mol"),
                                    reference_temperature=Quantity(298.15, "K"))
    lifecycle = (LifecycleBinding("cell", model, (InputBinding("charge_throughput", "throughput"), InputBinding("mean_cell_temperature", "cell_temp_mean"))),)
    aggs = (AggregationSpec("throughput", "abs_current", AggregateForm.INTEGRAL_DOSE),
            AggregationSpec("cell_temp_mean", "cell_temperature", AggregateForm.TIME_WEIGHTED_MEAN))
    return MultiTimescaleRuntime(run_id=f"cell-cooling-{env.timeline.timeline_id}", hierarchy=hierarchy, policy=policy, fast_system=system, environment=env,
                                 aggregations=aggs, lifecycle=lifecycle, fast_state_policy=FastStateAtMacroStart.DECLARED_INITIAL)


def initial_slow_state(fade: float = 0.0):
    u = Uncertainty.unknown("declared new cell")
    return {"cell": {"capacity_fade": InitialStateValue("capacity_fade", Quantity(fade, "dimensionless"), u)}}


def initial_fast_state():
    return {"cell": {"soc": InitialStateValue("soc", Quantity(INITIAL_SOC, "dimensionless"), Uncertainty.unknown("declared recharge target"))}}


# ==================================================================================================== the BIG 12 system
UNKNOWN = Uncertainty.unknown("declared or derived quantity; no uncertainty was quantified")
DAY_OUTPUTS = (("peak_cell_temperature", "K"), ("mean_cell_temperature", "K"), ("min_voltage", "V"), ("voltage_end_of_discharge", "V"),
               ("min_soc", "dimensionless"), ("end_soc", "dimensionless"), ("peak_heat", "W"), ("discharge_throughput", "A*h"),
               ("module_heat_generated", "W*h"), ("module_heat_removed", "W*h"), ("coolant_inlet_peak", "K"), ("coolant_outlet_peak", "K"), ("coolant_rise_peak", "K"))


def make_registry():
    from engcore.providers import ProviderRegistry
    from forge_pybamm import descriptor as pbd
    from forge_tespy import descriptor as tpd
    reg = ProviderRegistry()
    pbd.register(reg)
    tpd.register(reg)
    return reg


class ArtifactStore:
    """Bulk bytes produced by nodes (histories); the run bundle lists them by content digest.  Never inlined in a record."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.tables: dict[str, "DayTable"] = {}

    def put(self, name: str, data: bytes, kind: str, description: str) -> ArtifactRef:
        self.files[name] = data
        return ArtifactRef(name, kind, hashlib.sha256(data).hexdigest(), description)


def _refs_from(cell_log: list, cool_log: list, registry) -> tuple[ProviderRecordRef, ...]:
    pb = registry.status("pybamm")
    refs = [ProviderRecordRef("pybamm", pb.version, pb.digest, e["execution_identity"], "", True) for e in {tuple(x["window"]): x for x in cell_log}.values()]
    refs += [ProviderRecordRef.of_record(c["record"]) for c in cool_log]
    return tuple(sorted(set(refs)))


def day_authority(name: str, plant: Plant, case: Case, start_s: int, end_s: int, store: ArtifactStore, registry) -> MultiphysicsAuthority:
    """One coupled operating day [start, end] as a BIG 12 multiphysics node.  The coupling loop is BIG 9's."""
    live: dict[str, Any] = {}

    def factory(call):
        cell_log, cool_log = [], []
        live.update(cell_log=cell_log, cool_log=cool_log)
        return plant.runtime(start_s, end_s, soc0=call.value("initial_soc").to("dimensionless").magnitude, fade=call.value("fade").to("dimensionless").magnitude,
                             r_contact=call.value("r_contact").to("K/W").magnitude, load_history="load", cell_log=cell_log, cool_log=cool_log)

    table = lambda: DayTable.from_logs(live["cell_log"], live["cool_log"])  # noqa: E731
    dt_h = plant.window_s / 3600.0

    def q(value, unit):
        return Quantity(float(value), unit)

    def discharge_end_voltage(t: DayTable) -> float:
        rows = [r for r in t.rows if r["current_A"] > 0]
        if not rows:
            raise ProviderRefusal("the day has no discharge window, so no end-of-discharge voltage exists")
        return rows[-1]["voltage_end_V"]

    extractors = {
        "peak_cell_temperature": lambda run, call: q(max(r["cell_T_K"] for r in table().rows), "K"),
        "mean_cell_temperature": lambda run, call: q(np.mean([r["cell_T_K"] for r in table().rows]), "K"),
        "min_voltage": lambda run, call: q(min(r["voltage_min_V"] for r in table().rows), "V"),
        "voltage_end_of_discharge": lambda run, call: q(discharge_end_voltage(table()), "V"),
        "min_soc": lambda run, call: q(min(min(r["series"]["soc"]) for r in table().rows), "dimensionless"),
        "end_soc": lambda run, call: q(table().rows[-1]["soc_end"], "dimensionless"),
        "peak_heat": lambda run, call: q(max(r["heat_W"] for r in table().rows), "W"),
        "discharge_throughput": lambda run, call: q(sum(abs(r["current_A"]) for r in table().rows) * dt_h, "A*h"),
        "module_heat_generated": lambda run, call: q(sum(r["module_heat_generated_W"] for r in table().rows) * dt_h, "W*h"),
        "module_heat_removed": lambda run, call: q(sum(r["module_heat_removed_W"] for r in table().rows) * dt_h, "W*h"),
        "coolant_inlet_peak": lambda run, call: q(max(r["coolant_in_K"] for r in table().rows), "K"),
        "coolant_outlet_peak": lambda run, call: q(max(r["coolant_out_K"] for r in table().rows), "K"),
        "coolant_rise_peak": lambda run, call: q(max(r["coolant_out_K"] - r["coolant_in_K"] for r in table().rows), "K"),
    }
    lo, hi = case.soc_window

    def applicability(run, call):
        t = table()
        soc_lo = min(min(r["series"]["soc"]) for r in t.rows)
        soc_hi = max(max(r["series"]["soc"]) for r in t.rows)
        temps = [r["cell_T_K"] for r in t.rows]
        return (ApplicabilityReport("soc_window", "within" if lo <= soc_lo and soc_hi <= hi else "outside",
                                    digest_of({"soc": [soc_lo, soc_hi], "window": [lo, hi]}), f"SOC range [{soc_lo:.4f}, {soc_hi:.4f}] against the declared window [{lo}, {hi}]"),
                ApplicabilityReport("cell_temperature_window", "within" if TEMP_WINDOW_K[0] <= min(temps) and max(temps) <= TEMP_WINDOW_K[1] else "outside",
                                    digest_of({"T": [min(temps), max(temps)], "window": list(TEMP_WINDOW_K)}),
                                    f"cell temperature [{min(temps):.2f}, {max(temps):.2f}] K against the declared window {list(TEMP_WINDOW_K)}"))

    def artifacts(run, call):
        t = table()
        store.tables[name] = t
        return (store.put(f"{name}_history.csv", t.csv_bytes(), "timeseries_csv",
                          "dense PyBaMM voltage/heat/SOC with the window's coupled cell and coolant temperatures; presentation of the run, not evidence"),)

    return MultiphysicsAuthority(
        f"cell-cooling-{name}", graph=plant.graph, plan=plant.plan(start_s, end_s), runtime_factory=factory, run_kwargs=lambda call: plant.run_kwargs(),
        outputs={}, extractors=extractors, artifacts=artifacts, applicability=applicability, state_owners={},
        providers=lambda run: _refs_from(live["cell_log"], live["cool_log"], registry),
        config={**plant.configuration(R_CONTACT_K_PER_W), "window": [start_s, end_s], "soc_window": list(case.soc_window), "temperature_window_K": list(TEMP_WINDOW_K)})


@dataclass
class Flagship:
    case: Case
    request: SystemRunRequest
    context: RuntimeContext
    store: ArtifactStore
    plant: Plant
    system_obj: CoupledCellCoolingFastSystem
    runtime: MultiTimescaleRuntime
    environment: EnvironmentTimeline
    constraints: dict
    registry: Any
    aging_authority: MultiscaleAuthority


def build_system_definition(plant: Plant):
    twin = lambda n: ScientificTwin(n, "1", TwinKind.CONCEPT).reference  # noqa: E731
    graph = plant.graph
    definitions = (ComponentDefinition("assembly", "1"), ComponentDefinition("cell", "1", graph.participant("cell").ports),
                   ComponentDefinition("coolant", "1", graph.participant("coolant").ports))
    instances = (ComponentInstance("pack", "assembly", "1", twin("pack")),
                 ComponentInstance("cell", "cell", "1", twin("cell"), parent_id="pack", participant_id="cell"),
                 ComponentInstance("coolant", "coolant", "1", twin("coolant"), parent_id="pack", participant_id="coolant"))
    connections = tuple(ComponentConnection(e.edge_id, e.edge_id, e.source.participant_id, e.source.port_id, e.target.participant_id, e.target.port_id)
                        for e in graph.edges)
    t_max = ConstraintDefinition("max_cell_temperature", "cell_temperature", ConstraintOperator.LESS_EQUAL, Quantity(TMAX_K, "K"))
    soc_min = ConstraintDefinition("min_soc", "minimum_soc", ConstraintOperator.GREATER_EQUAL, Quantity(SOC_MIN_CONSTRAINT, "dimensionless"))
    fade_max = ConstraintDefinition("max_capacity_fade", "capacity_fade", ConstraintOperator.LESS_EQUAL, Quantity(FADE_MAX, "dimensionless"))
    bindings = tuple(ConstraintBinding(b, "cell", c) for b, c in (("b_tmax_fresh", "max_cell_temperature"), ("b_tmax_aged", "max_cell_temperature"),
                                                                    ("b_soc_fresh", "min_soc"), ("b_soc_aged", "min_soc"), ("b_fade", "max_capacity_fade")))
    system = SystemDefinition("cell-cooling-module", "1", definitions, instances, connections, constraint_bindings=bindings,
                              constraints=(t_max, soc_min, fade_max))
    system.validate_graph(graph)
    return system, {"max_cell_temperature": t_max, "min_soc": soc_min, "max_capacity_fade": fade_max}


def build_flagship(case: Case, registry=None, *, macro_days: int = 14, window_s: int = H, only_day: bool = False) -> Flagship:
    """``only_day`` builds the single fresh-cell coupled day (used by the window-size refinement study); the full flagship is the default."""
    registry = registry or make_registry()
    env, scenario = build_environment(case)
    plant = Plant(registry, env, scenario.digest, window_s)
    system, defs = build_system_definition(plant)
    mat_state, resolved = contact_resistance()
    store = ArtifactStore()
    pb, ts = registry.status("pybamm"), registry.status("tespy")
    fast = CoupledCellCoolingFastSystem(plant, R_CONTACT_K_PER_W, resolved.digest)
    runtime = build_multiscale_runtime(fast, env, macro_days=macro_days)
    aged_start = DAYS_AGED * DAY
    fresh_auth = day_authority("day-fresh", plant, case, 0, DAY, store, registry)
    aged_auth = day_authority("day-aged", plant, case, aged_start, aged_start + DAY, store, registry)
    control_auth = day_authority("day-control", plant, case, aged_start, aged_start + DAY, store, registry)

    def aging_providers(record):
        refs: set = set()
        for step in record.steps:
            for res in step.results:
                refs.update(fast.refs[res.request_identity])
        return tuple(sorted(refs))

    def aging_applicability(record, call):
        fade = record.final_slow_state["cell"]["capacity_fade"].value.magnitude_in("dimensionless")
        return (ApplicabilityReport("fade_mapping_range", "within" if 0.0 <= fade < 0.5 else "outside", digest_of({"fade": fade}),
                                    f"final fade {fade:.5f} against the declared loss-of-active-material mapping range [0, 0.5)"),)

    fade_of = lambda r: Quantity(r.final_slow_state["cell"]["capacity_fade"].value.magnitude, "dimensionless")  # noqa: E731
    aging_auth = MultiscaleAuthority(
        "cell-cooling-aging", runtime, initial_slow_state=initial_slow_state(), initial_fast_state=initial_fast_state(),
        extractors={"final_fade": fade_of, "represented_days": lambda r: Quantity(float(Fraction(r.accounting["represented_seconds"])) / DAY, "day"),
                    "resolved_days": lambda r: Quantity(float(Fraction(r.accounting["resolved_seconds"])) / DAY, "day")},
        slow_state_owners={"cell": "cell_slow"}, until=p(aged_start), providers=aging_providers, applicability=aging_applicability,
        config={"fade_model": f"ThroughputArrheniusFade k={FADE_K}/(A h) Ea={FADE_EA} kJ/mol Tref=298.15 K", "represented_days": DAYS_AGED,
                "macro_days": macro_days, "fast_system": fast.identity.digest})

    def shift_fn(call):
        v = lambda n: call.value(n).to("V").magnitude  # noqa: E731
        k = lambda n: call.value(n).to("K").magnitude  # noqa: E731
        w = lambda n: call.value(n).to("W").magnitude  # noqa: E731
        out = {"voltage_shift_degradation": OutputValue(Quantity(v("v_aged") - v("v_control"), "V"), UNKNOWN, "aged - control (same day-56 window)"),
               "voltage_shift_environment": OutputValue(Quantity(v("v_control") - v("v_fresh"), "V"), UNKNOWN, "control - fresh (day 56 vs day 0, both new cells)"),
               "peak_temperature_shift_degradation": OutputValue(Quantity(k("t_aged") - k("t_control"), "K"), UNKNOWN, "aged - control"),
               "peak_heat_shift_degradation": OutputValue(Quantity(w("q_aged") - w("q_control"), "W"), UNKNOWN, "aged - control")}
        return NodeOutcome("succeeded", out)
    shift_auth = CallbackAuthority("cell-cooling-shift", shift_fn, config={"definition": "aged - control (degradation); control - fresh (environment drift)"},
                                   deterministic=True)

    conf = digest_of({"graph": plant.graph.fingerprint(), "scenario": scenario.digest, "case": case.name})
    r_ref = MaterialPropertyRef("r_contact", "coolant", "contact_resistance", resolved.digest, "K/W")
    day_out = tuple(NodeOutputSpec(n, u) for n, u in DAY_OUTPUTS)
    binds = ("pybamm_cell", "tespy_coolant")
    checks = ("soc_window", "cell_temperature_window")

    def day_node(nid, auth, start_s, fade_input=None):
        lit = [LiteralInput("initial_soc", Quantity(INITIAL_SOC, "dimensionless"), Uncertainty.unknown("declared recharge target"))]
        inputs = ()
        if fade_input is None:
            lit.append(LiteralInput("fade", Quantity(0.0, "dimensionless"), Uncertainty.unknown("declared new cell")))
        else:
            inputs = (NodeInput("fade", fade_input, "final_fade", "dimensionless"),)
        return NodeSpec(nid, NodeKind.MULTIPHYSICS_EXECUTION, auth.ref, day_out, inputs=inputs, literals=tuple(lit), provider_binding_ids=binds,
                        material_refs=(r_ref,), environment_requirements=(EnvironmentRequirement("inlet", "coolant_inlet", Quantity(start_s, "s"), "K"),),
                        applicability_checks=checks, configuration_digest=conf)

    shift_out = (("voltage_shift_degradation", "V"), ("voltage_shift_environment", "V"), ("peak_temperature_shift_degradation", "K"),
                 ("peak_heat_shift_degradation", "W"))
    nodes = [day_node("day_fresh", fresh_auth, 0),
             NodeSpec("aging", NodeKind.MULTISCALE_EXECUTION, aging_auth.ref,
                      (NodeOutputSpec("final_fade", "dimensionless"), NodeOutputSpec("represented_days", "day"), NodeOutputSpec("resolved_days", "day")),
                      depends_on=("day_fresh",), provider_binding_ids=binds, commits_state=True, writes_owners=("cell_slow",),
                      applicability_checks=("fade_mapping_range",), checkpointable=True,
                      configuration_digest=digest_of({"policy": "macro", "days": macro_days, "case": case.name})),
             day_node("day_aged", aged_auth, aged_start, "aging"), day_node("day_control", control_auth, aged_start),
             NodeSpec("shift", NodeKind.AGGREGATE, shift_auth.ref, tuple(NodeOutputSpec(n, u) for n, u in shift_out),
                      inputs=(NodeInput("v_aged", "day_aged", "voltage_end_of_discharge", "V"), NodeInput("v_control", "day_control", "voltage_end_of_discharge", "V"),
                              NodeInput("v_fresh", "day_fresh", "voltage_end_of_discharge", "V"), NodeInput("t_aged", "day_aged", "peak_cell_temperature", "K"),
                              NodeInput("t_control", "day_control", "peak_cell_temperature", "K"), NodeInput("q_aged", "day_aged", "peak_heat", "W"),
                              NodeInput("q_control", "day_control", "peak_heat", "W")))]
    if only_day:
        nodes = nodes[:1]
    obs = []
    for tag, node in (("fresh", "day_fresh"), ("aged", "day_aged"), ("control", "day_control")):
        for n, u in DAY_OUTPUTS:
            obs.append(RequestedObservable(f"{n}_{tag}", node, n, u))
    obs += [RequestedObservable(n, "aging", n, u) for n, u in (("final_fade", "dimensionless"), ("represented_days", "day"), ("resolved_days", "day"))]
    obs += [RequestedObservable(n, "shift", n, u) for n, u in shift_out]
    if only_day:
        obs = [o for o in obs if o.observable_id.endswith("_fresh")]
    cdig = {k: digest_of(v.to_dict()) for k, v in defs.items()}
    cobs = (ConstraintObservation("b_tmax_fresh", "max_cell_temperature", cdig["max_cell_temperature"], "peak_cell_temperature_fresh"),
            ConstraintObservation("b_tmax_aged", "max_cell_temperature", cdig["max_cell_temperature"], "peak_cell_temperature_aged"),
            ConstraintObservation("b_soc_fresh", "min_soc", cdig["min_soc"], "min_soc_fresh"),
            ConstraintObservation("b_soc_aged", "min_soc", cdig["min_soc"], "min_soc_aged"),
            ConstraintObservation("b_fade", "max_capacity_fade", cdig["max_capacity_fade"], "final_fade"))
    if only_day:
        cobs = cobs[:1] + cobs[2:3]
    initial = InitialStateSpec(Quantity(0, "s"), (OwnerState("cell_slow", "slow", (InitialStateValue("capacity_fade", Quantity(0.0, "dimensionless"),
                                                                                                        Uncertainty.unknown("declared new cell")),)),),
                               (("coolant", mat_state.digest),))
    request = SystemRunRequest.build(
        request_id=f"flagship-a-battery-cooling-lifecycle-{case.name}", system=system, scenario=scenario, timeline=env.timeline, environment=env,
        initial_state=initial, nodes=tuple(nodes), observables=tuple(obs), materials=(mat_state,),
        model_selections=(ModelSelection("cell", "pybamm-spm-chen2020", pb.version), ModelSelection("coolant", "tespy-cold-plate-water", ts.version)),
        provider_bindings=(ProviderBinding("pybamm_cell", "pybamm", pb.version, pb.digest), ProviderBinding("tespy_coolant", "tespy", ts.version, ts.digest)),
        constraint_observations=cobs, profile=ExecutionProfile(("multiphysics", "multiscale", "lifecycle"), "off", True, ()))
    authorities = AuthorityRegistry((fresh_auth,) if only_day else (fresh_auth, aging_auth, aged_auth, control_auth, shift_auth))
    context = RuntimeContext(authorities, system=system, scenario=scenario, timeline=env.timeline, environment=env, material_states={mat_state.digest: mat_state},
                             resolved_properties={resolved.digest: resolved}, constraints={v: defs[k] for k, v in cdig.items()}, providers=registry)
    return Flagship(case, request, context, store, plant, fast, runtime, env, defs, registry, aging_auth)


# ==================================================================================================== verification, summary, bundle
HEAT_BALANCE_TOL_WH = 1e-6          # DECLARED before any run: absolute closure of generated vs removed module heat (W h)
FIRST_LAW_MIN_HEAT_W = 0.5              # windows carrying less module heat than this are not used by the first-law check (a ratio of tiny numbers)
FIRST_LAW_REL_TOL = 5e-3            # DECLARED before any run: TESPy coolant temperature rise vs Q / (m cp)
REFINEMENT_TOL = {"peak_cell_temperature": Quantity(0.05, "K"), "voltage_end_of_discharge": Quantity(0.002, "V")}   # DECLARED before any run
REFINEMENT_PEAK_HEAT_REL = 0.02     # DECLARED before any run: relative change of the peak cell heat between window sizes


def first_law_reference():
    from engcore.engineering import EnvelopeBound, ReferenceCondition, ReferenceRecord
    from engcore.scientific.oracles import OracleKind
    return ReferenceRecord(
        "first-law-cold-plate", "Steady single-phase heat balance Q = m cp (T_out - T_in)", "textbook thermodynamics (no source file: derived)",
        "first law for a steady-flow control volume", "", "derived relation, not copied data", OracleKind.ANALYTIC_REFERENCE,
        (ReferenceCondition("pressure", 2e5, "Pa"), ReferenceCondition("mean_temperature", 300.0, "K")), (("delta_T_relative_difference", "dimensionless"),), (), "",
        "cp from CoolProp at the stream mean temperature (the same property backend TESPy uses: this verifies the energy-balance implementation, "
        "not the property data)", (EnvelopeBound("pressure", 1e5, 1e7, "Pa"), EnvelopeBound("mean_temperature", 274.0, 370.0, "K")),
        comparable_quantities=("delta_T_relative_difference",))


def first_law_check(table: DayTable):
    """Max relative difference between TESPy's coolant rise and Q/(m cp) over the windows that carry heat."""
    import CoolProp.CoolProp as CP
    worst, mean_T, used = 0.0, [], 0
    for r in table.rows:
        q = r["module_heat_generated_W"]
        if q < FIRST_LAW_MIN_HEAT_W:
            continue
        tm = 0.5 * (r["coolant_in_K"] + r["coolant_out_K"])
        cp = CP.PropsSI("CPMASS", "T", tm, "P", PRESSURE, "Water")
        analytic = q / (MASS_FLOW * cp)
        worst = max(worst, abs((r["coolant_out_K"] - r["coolant_in_K"]) - analytic) / analytic)
        mean_T.append(tm)
        used += 1
    if not used:
        raise ProviderRefusal("no window carries enough heat for the first-law check")
    return worst, float(np.mean(mean_T)), used


@dataclass
class FlagshipRun:
    flagship: Flagship
    result: Any
    preflight: Any
    wall_s: float
    constraints: tuple
    conservation: tuple
    summary: Any = None
    uncertainty: Any = None
    comparisons: tuple = ()
    references: tuple = ()
    ladder: Any = None
    study: dict = field(default_factory=dict)
    references_considered: tuple = ()


def run_flagship(case_name: str, registry=None, *, first_law: bool = True, refinement: bool = False) -> FlagshipRun:
    from engcore.engineering import (
        EvidenceLink, LevelEntry, LevelStatus, PredeclaredCriterion, UncertaintyStatement, VerificationLadder, build_summary, compare_to_reference,
        contract_integrity_entry,
    )
    from engcore.system_runtime import BalanceSpec, RunStatus, SystemExecutor, TermSource, assess_conservation, assess_constraints, compile_plan, preflight

    fl = build_flagship(CASES[case_name], registry)
    report = preflight(fl.request, compile_plan(fl.request), fl.context)
    t0 = time.perf_counter()
    result = SystemExecutor(fl.context).run(fl.request)
    wall = time.perf_counter() - t0
    constraints = assess_constraints(result, fl.context.system, fl.context.constraints)
    specs = tuple(BalanceSpec(f"module_heat_{tag}", (TermSource("generated", f"module_heat_generated_{tag}"),), (TermSource("removed", f"module_heat_removed_{tag}"),),
                              Quantity(HEAT_BALANCE_TOL_WH, "W*h")) for tag in ("fresh", "aged", "control"))
    conservation = assess_conservation(result, specs)
    run = FlagshipRun(fl, result, report, wall, constraints, conservation)
    # ---- ladder
    entries = [contract_integrity_entry(report, result)]
    closed = [c for c in conservation if c.status == "closed"]
    if conservation and len(closed) == len(conservation):
        entries.append(LevelEntry(2, LevelStatus.REACHED, tuple(EvidenceLink.of_record("conservation_assessment", c.to_dict(), "conservation_residual", "met",
                                                                                     f"{c.balance_id}: residual {c.residual.magnitude:.2e} {c.residual.units}") for c in closed),
                                  "INTERFACE consistency, not an independent conservation law: TESPy is handed the cell heat as its heat duty, so closure of generated heat against m dh shows the solver honoured the duty "
                                  "(tolerance pre-registered). It would fail on a solver or unit error; it cannot detect a wrong heat model"))
    else:
        entries.append(LevelEntry(2, LevelStatus.ATTEMPTED_NOT_REACHED if conservation else LevelStatus.NOT_ATTEMPTED, (), "; ".join(
            f"{c.balance_id}: {c.status}" for c in conservation) or "no balance could be assessed"))
    comparisons = []
    references = []
    tables = fl.store.tables
    if first_law and "day-fresh" in tables and result.receipt("day_fresh").status.value == "succeeded":
        ref = first_law_reference()
        worst, mean_T, used = first_law_check(tables["day-fresh"])
        crit = PredeclaredCriterion("first_law_delta_T", "delta_T_relative_difference", "max_relative", Quantity(FIRST_LAW_REL_TOL, "dimensionless"),
                                    "flagships/forge_flagships/battery_cooling.py:FIRST_LAW_REL_TOL (pre-registered)")
        cmp_ = compare_to_reference(ref, crit, {"pressure": Quantity(PRESSURE, "Pa"), "mean_temperature": Quantity(mean_T, "K")},
                                    value=Quantity(worst, "dimensionless"), compared_identity=digest_of(sorted(r.execution_identity_digest for r in
                                                                                                             result.receipt("day_fresh").provider_records)),
                                    note=f"{used} heat-carrying windows of the fresh day")
        comparisons.append(cmp_)
        references.append(ref)
        entries.append(LevelEntry(3, LevelStatus.REACHED if cmp_.outcome == "met" else LevelStatus.ATTEMPTED_NOT_REACHED, (EvidenceLink.of_comparison(cmp_),),
                                  "first-law coolant temperature rise vs Q/(m cp): verifies the heat -> enthalpy -> temperature implementation only"))
    if refinement and result.status.value == "succeeded":
        study = window_refinement_study(registry, case_name)
        run.study = study
        q = study["quantities"]
        entries.append(LevelEntry(4, LevelStatus.REACHED if study["met"] else LevelStatus.ATTEMPTED_NOT_REACHED,
                                  (EvidenceLink.of_record("window_refinement", study, "discretisation_convergence", "met" if study["met"] else "not_met",
                                                        f"coupling windows {study['windows_s']} s (three separate BIG 12 requests, digests {study['digest']}): {q}; observed orders {study['orders']}"),),
                                  "the fresh-cell coupled day at three coupling-window sizes, each a separate BIG 12 request (evidence from OTHER requests than this run's). Criteria: finest-pair "
                                  f"differences within {REFINEMENT_TOL['peak_cell_temperature'].magnitude:g} K / {1e3 * REFINEMENT_TOL['voltage_end_of_discharge'].magnitude:g} mV / {100 * REFINEMENT_PEAK_HEAT_REL:g} % of peak heat (pre-registered, two-level version) AND monotonically decreasing successive differences "
                                  "(added after the review, with the third level; the two-level result had already met the tolerances). Only the coupling window is refined: the cell model's own "
                                  "solver tolerances and points-per-window are not varied"))
    else:
        entries.append(LevelEntry(4, LevelStatus.NOT_ATTEMPTED, (), "window-size refinement is a separate set of BIG 12 requests (window_refinement_study); not run here, or this run did not succeed"))
    nasa = nasa_reference()
    applic = nasa.applicability({})
    run.references_considered = ((nasa, applic),)
    entries += [LevelEntry(5, LevelStatus.NOT_AVAILABLE, (), "no second, independent battery provider exists in the provider ecosystem; PyBaMM SPM vs SPMe would be the same provider "
                                                             "and compare_providers refuses that pair as non-independent"),
                LevelEntry(6, LevelStatus.NOT_AVAILABLE, (), "no published numerical benchmark for this module/duty was integrated"),
                LevelEntry(7, LevelStatus.NOT_AVAILABLE, (), "no experimental dataset applicable to this cell was integrated. The NASA PCoE Li-ion aging dataset (repository-pinned manifest) was considered: "
                                                             f"the reference record Forge wrote for it (envelope authored here from the pack's description, not from the dataset's own metadata) states only the cell-format diameter (18 mm, from the '18650' name) as an envelope term and this flagship states no recorded cell format for the PyBaMM parameter set, so its applicability is {applic.status.upper()} ({'; '.join(applic.reasons)}); no comparison was made and none is claimed")]
    if not any(e.level == 3 for e in entries):
        entries.append(LevelEntry(3, LevelStatus.NOT_ATTEMPTED, (), "the coupled day produced no result to check against the first-law relation"))
    run.ladder = VerificationLadder(tuple(entries))
    run.comparisons, run.references = tuple(comparisons), tuple(references)
    unknown_inputs = ("coolant inlet profile (declared)", "cell current profile (declared)", "initial state of charge (declared)", "contact resistance (ASSUMED)",
                      "cells-in-module multiplicity (declared)", "fade-law constants (declared)", "PyBaMM Chen2020 parameters (provider-bundled literature data)")
    uncertainty = UncertaintyStatement(
        (), unknown_inputs, "NOT QUANTIFIED for the SPM cell model, the quasi-steady thermal rule, the loss-of-active-material fade mapping or the representative-day "
                            "approximation (unknown, not zero)",
        (f"contact resistance record {digest_of({'r': R_CONTACT_K_PER_W})[:12]}.. (ASSUMED)", f"PyBaMM parameter set {PARAMETER_SET} (provider-bundled literature set)"),
        f"cell temperature window {list(TEMP_WINDOW_K)} K and SOC window {list(fl.case.soc_window)} were checked on every solved day; the aging map range [0, 0.5) on the slow state. "
        "The applicability of the Chen2020 parameters to the temperatures and duty of this case is UNKNOWN to Forge",
        "no benchmark was used: the NASA PCoE Li-ion aging dataset (repository-pinned; 18650 cells) has a Forge-authored reference record with one envelope term (cell format) that this flagship cannot state for its parameter set, so its applicability is UNKNOWN and it is not compared")
    if True:
        run.summary = build_summary(
            f"Cell module with liquid cooling, 57-day declared profile ({fl.case.name})", fl.request, result,
            outputs=[("Peak cell temperature, fresh day", "peak_cell_temperature_fresh"), ("Peak cell temperature, day 56 (aged)", "peak_cell_temperature_aged"),
                     ("Coolant temperature rise, fresh day (peak)", "coolant_rise_peak_fresh"), ("Module heat removed, fresh day", "module_heat_removed_fresh"),
                     ("End-of-discharge voltage, fresh day", "voltage_end_of_discharge_fresh"), ("End-of-discharge voltage, aged cell", "voltage_end_of_discharge_aged"),
                     ("Voltage shift caused by degradation", "voltage_shift_degradation"), ("Voltage shift caused by environment drift", "voltage_shift_environment"),
                     ("End SOC, fresh day", "end_soc_fresh"), ("Minimum SOC, aged day", "min_soc_aged"), ("Capacity fade after 56 days", "final_fade"),
                     ("Peak cell heat shift caused by degradation", "peak_heat_shift_degradation")],
            constraints=constraints, conservation=conservation, ladder=run.ladder, comparisons=comparisons, references=references, uncertainty=uncertainty,
            trace_observable="voltage_shift_degradation" if result.observable("voltage_shift_degradation").value is not None else "final_fade"
            if result.observable("final_fade").value is not None else "peak_cell_temperature_fresh",
            notes=(f"case {fl.case.name}: {fl.case.description}", "all scenario inputs are declared illustrative fixtures, not measurements"))
    run.uncertainty = uncertainty
    return run


def nasa_reference():
    """The NASA PCoE Li-ion aging dataset AS PINNED BY THE REPOSITORY (manifest identity only; no data copied).  The one envelope term
    (cell format, 18 mm) is AUTHORED HERE from the pack's public description of the cells, not read from the dataset's own metadata.  This
    flagship cannot state a recorded cell format for its PyBaMM parameter set, so applicability is UNKNOWN and no comparison is made."""
    from engcore.engineering import EnvelopeBound, ReferenceCondition, ReferenceRecord
    from engcore.scientific.oracles import OracleKind
    m = json.loads(open(os.path.join(os.path.dirname(__file__), "..", "..", "benchmarks", "measurements", "nasa_battery_aging", "manifest.json"), "rb").read().decode())
    return ReferenceRecord(
        m["dataset_id"], m["title"], m["citation"], f"{m['publisher']}, version {m['version']}", m["landing_page"],
        "NASA open data; NOT copied into this repository - only the pinned manifest identity is referenced", OracleKind.EXPERIMENTAL_DATASET,
        (ReferenceCondition("cell_format_diameter", 18.0, "mm"),), (("terminal_voltage", "V"), ("discharge_capacity", "A*h")), (), m["catalog_source_hash"],
        "no values extracted; the repository pack describes commercial 18650 cells cycled at several ambient temperatures (benchmarks/measurements/nasa_battery_aging/README.md)",
        (EnvelopeBound("cell_format_diameter", 17.5, 18.5, "mm"),))


def window_refinement_study(registry=None, case_name: str = "normal", windows=(3600, 1800, 900)) -> dict:
    """The fresh-cell coupled day at three coupling-window sizes, each through BIG 12.  Returns differences, observed orders and the outcome."""
    from engcore.system_runtime import SystemExecutor
    out: dict = {"windows_s": list(windows), "quantities": {}, "orders": {}, "status": {}, "digest": {}}
    results = {}
    for w in windows:
        fl = build_flagship(CASES[case_name], registry, window_s=w, only_day=True)
        res = SystemExecutor(fl.context).run(fl.request)
        results[w] = res
        out["status"][str(w)] = res.status.value
        out["digest"][str(w)] = res.digest[:16]
    if not all(r.status.value == "succeeded" for r in results.values()):
        out["met"] = False
        return out
    w0, w1, w2 = windows
    tol_ok, mono_ok = True, True
    for name in ("peak_cell_temperature", "voltage_end_of_discharge", "peak_heat"):
        v = [results[w].observable(f"{name}_fresh").value.value.magnitude for w in windows]
        d1, d2 = abs(v[1] - v[0]), abs(v[2] - v[1])
        out["quantities"][name] = {str(w): x for w, x in zip(windows, v)} | {"abs_difference_coarse_pair": d1, "abs_difference_fine_pair": d2}
        out["orders"][name] = float(math.log2(d1 / d2)) if d1 > 0 and d2 > 0 else None
        mono_ok = mono_ok and d2 < d1
        if name == "peak_heat":
            tol_ok = tol_ok and d2 / abs(v[2]) <= REFINEMENT_PEAK_HEAT_REL
        else:
            tol_ok = tol_ok and d2 <= REFINEMENT_TOL[name].magnitude
    out["tolerances_met"], out["monotone_met"] = tol_ok, mono_ok
    out["met"] = tol_ok and mono_ok
    return out
