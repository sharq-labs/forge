"""Reference electrothermal-aging system for the BIG 10 multi-timescale proofs.

NOT a test module (no ``test_`` prefix); imported by path from the core BIG 10
tests and from the FEniCSx provider tests.

System: a heater on a mineral-wool board in a climate chamber.

* Environment (BIG 3): a DECLARED cyclic damp-heat chamber program, hourly,
  shaped after the IEC 60068-2-30 Db cycle (25 C <-> upper temperature, wet
  during the cool-down phase).  Classified ``design_assumption`` -- it is a
  declared scenario, not measured weather, and conformance to the standard is
  not claimed.  A program change (upper temperature raised) is a declared BIG 2
  DISCONTINUITY event.
* Usage (BIG 2 USAGE history): heater supply voltage 10 V from 06:00 to 18:00,
  2 V standby otherwise (declared operating profile).
* Fast physics (BIG 9 MultiphysicsRuntime, implicit two-way coupling):
  thermal participant (lumped BIG 6 linear network here; FEniCSx plate in the
  provider tests) <-> electrical participant (SciPy root KVL, BIG 6).
* Slow state (BIG 4): board ``moisture_content`` (wetness-dose uptake) and
  heater ``resistance_drift`` (Arrhenius-equivalent-time drift from the fast
  heater temperature DWELL history).
* Materials (BIG 5): board conductivity re-resolved from ``moisture_content``
  on every fast execution.

All numbers are illustrative fixtures, not reference data.  Nothing here is
validation.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
from fractions import Fraction

import numpy as np

from engcore.coupling.adapters import CouplingRefusal
from engcore.coupling import ParticipantStateContract, StateCompleteness, provider_participant, scalar_port
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domains.electrical.heater_circuit import HeaterCircuit
from engcore.domains.electrical.resistance_drift import AGGREGATOR_ID, ArrheniusEquivalentTime, ArrheniusResistanceDrift
from engcore.domains.hygrothermal.moisture_uptake import LinearWetnessMoistureUptake
from engcore.execution.multiphysics import InitialStateDefinition, InitialStateValue, MultiphysicsRuntime
from engcore.materials import MaterialState
from engcore.multiscale import (
    AdaptationRule, AggregationSpec, EventHandling, FastExecutionResult, FastSystem, FastSystemIdentity, LifecycleBinding,
    MacroStepPolicy, MaterialBinding, MultiTimescaleRuntime, OutputSample, OutputSeries, RepresentativePolicy, ScaleHierarchy,
    ScaleLevel, StateChangeLimit, StateOwnership, ThresholdWatch,
)
from engcore.numerical import NumericalMethod, NumericalProblem, NumPyDenseLinearProvider, OperatorIdentity, ProblemKind, UnitBoundary, VariableSpec, array_digest
from engcore.scenarios import (
    AggregateForm, ChannelRepresentation, EnvironmentChannel, EnvironmentKindRegistry, EnvironmentSource, EnvironmentTimeline,
    HistoryEntry, InputBinding, NamedQuantity, QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification,
    TimeBasis, Timeline, TimelineEvent, TimelineEventKind, TimePoint, TimeWindow,
)
from engcore.scenarios.lifecycle import run_digest
from engcore.scientific.composition.conversion import EnergyConversion
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortRef, RelaxationKind, RelaxationPolicy, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.solvers.protocol import SolverSettings
from engcore.scientific.units.quantity import Quantity

_HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("materials_fixtures_ms", str(_HERE / "test_materials_engine.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

HOUR = 3600
DAY = 86400
BASIS = TimeBasis("chamber", "elapsed", "chamber program start")
LOW_K = 298.15
BOARD_T_RANGE = (Quantity(273.15, "K"), Quantity(473.15, "K"))


def board_set():
    """Illustrative mineral-wool conductivity vs moisture, DECLARED temperature-independent over
    273.15-473.15 K (fixture values, not reference data).  Every solve re-resolves the property at the
    solved board temperature bound and refuses if it leaves this range."""
    from engcore.materials import ApplicabilityRange, InterpolationRule
    rows = [(f"k-wide-m{m}", "thermal_conductivity", Quantity(v, "W/(m*K)"), None,
             (M.point("moisture_content", Quantity(m, "dimensionless")), ApplicabilityRange("temperature", *BOARD_T_RANGE)), "", "measured", None)
            for m, v in ((0.0, 0.035), (0.05, 0.045), (0.10, 0.060))]
    return M._dataset(M.BOARD, rows, source_id="fixture-board-wide", locator="tests/multiscale_reference.py::board_set",
                      set_id="board-props-wide", rules=(InterpolationRule("thermal_conductivity", "moisture_content", "linear"),))[0]
UNKNOWN = Uncertainty.unknown


def p(seconds) -> TimePoint:
    return TimePoint("chamber", Fraction(seconds))


# ---- declared chamber program -------------------------------------------------


def chamber_program(days: int, *, change_at_hour: int | None = None, upper=(328.15, 338.15), daily_rise=0.25, off_days=()):
    """Hourly (air K, relative humidity, surface wetness, supply V) for ``days`` days."""
    air, rh, wet, volts = [], [], [], []
    for h in range(days * 24):
        day, hod = divmod(h, 24)
        high = (upper[1] if change_at_hour is not None and h >= change_at_hour else upper[0]) + daily_rise * day
        if hod < 3:
            t = LOW_K + (high - LOW_K) * (hod + 1) / 3
        elif hod < 12:
            t = high
        elif hod < 18:
            t = high - (high - LOW_K) * (hod - 11) / 6
        else:
            t = LOW_K
        air.append(round(t, 6))
        rh.append(0.93 if 3 <= hod < 12 else 0.95)
        wet.append(1.0 if 12 <= hod < 18 else 0.0)
        volts.append(10.0 if 6 <= hod < 18 and day not in off_days else 2.0)
    return air, rh, wet, volts


def build_environment(days: int, *, change_at_hour: int | None = None, gap_hours=(), daily_rise=0.25, off_days=(), extra_events=()):
    air, rh, wet, volts = chamber_program(days, change_at_hour=change_at_hour, daily_rise=daily_rise, off_days=off_days)
    end = days * DAY
    scenario = ScenarioSpecification("chamber-program", "1", Quantity(0, "s"), Quantity(end, "s"),
                                     segments=(ScenarioSegment("program", Quantity(0, "s"), Quantity(end, "s")),))

    def history(hid, kind, qid, unit, values, skip=()):
        return QuantityHistory(hid, kind, qid, unit, tuple(
            HistoryEntry(TimeWindow(p(i * HOUR), p((i + 1) * HOUR)), NamedQuantity(qid, Quantity(v, unit)))
            for i, v in enumerate(values) if i not in skip))

    events = tuple(extra_events)
    if change_at_hour is not None:
        events += (TimelineEvent("program-change", TimelineEventKind.DISCONTINUITY, p(change_at_hour * HOUR), "air_temperature"),)
    timeline = Timeline.from_scenario(
        scenario, timeline_id="chamber", basis=BASIS,
        histories=(history("air", "exposure", "air_temperature", "K", air, set(gap_hours)),
                   history("rh", "exposure", "humidity", "dimensionless", rh),
                   history("wet", "exposure", "wetness", "dimensionless", wet),
                   history("supply", "usage", "supply_voltage", "V", volts)),
        extra_events=events)
    content = hashlib.sha256(json.dumps({"air": air, "rh": rh, "wet": wet}, sort_keys=True).encode()).hexdigest()
    source = EnvironmentSource("chamber-program", "design_assumption",
                               "declared cyclic damp-heat chamber program shaped after IEC 60068-2-30 Db (conformance not claimed)",
                               content, "1")
    ctx = ReferenceContext("chamber", "bench", "enu")
    horizon = TimeWindow(p(0), p(end))
    channels = (EnvironmentChannel("air_temperature", "ambient_temperature", "K", "chamber-program", ctx, horizon,
                                   ChannelRepresentation.INTERVAL_HISTORY, history_id="air"),
                EnvironmentChannel("humidity", "relative_humidity", "dimensionless", "chamber-program", ctx, horizon,
                                   ChannelRepresentation.INTERVAL_HISTORY, history_id="rh"),
                EnvironmentChannel("wetness", "surface_wetness", "dimensionless", "chamber-program", ctx, horizon,
                                   ChannelRepresentation.INTERVAL_HISTORY, history_id="wet"))
    return EnvironmentTimeline("chamber-env", timeline, EnvironmentKindRegistry.standard(), (source,), channels), scenario


# ---- scale hierarchy, lifecycle, aggregation, policy ------------------------------


def hierarchy(version="1"):
    return ScaleHierarchy("heater-board", version, (
        ScaleLevel("electrothermal_equilibrium", "fast", Quantity(60, "s"), "coupled heater circuit / board conduction (quasi-static per coupling window)"),
        ScaleLevel("operating_day", "operational", Quantity(1, "day"), "one chamber program cycle and heater duty cycle"),
        ScaleLevel("aging", "slow", Quantity(30, "day"), "board moisture uptake and heater resistance drift"),
    ), (StateOwnership("thermal", "moisture_content", "slow", "dimensionless"),
        StateOwnership("electrical", "resistance_drift", "slow", "dimensionless")))


TEQ = ArrheniusEquivalentTime(activation_energy=Quantity(50, "kJ/mol"), reference_temperature=Quantity(358.15, "K"),
                              valid_temperature=(Quantity(273.15, "K"), Quantity(473.15, "K")))


def aggregations():
    return (
        AggregationSpec("heater_teq", "heater_temperature", AggregateForm.DOMAIN_DEFINED, aggregator=TEQ),
        AggregationSpec("heater_temp_mean", "heater_temperature", AggregateForm.TIME_WEIGHTED_MEAN),
        AggregationSpec("heater_temp_max", "heater_temperature", AggregateForm.EXTREMA, statistic="max"),
        AggregationSpec("heater_hot_dwell", "heater_temperature", AggregateForm.DWELL_ABOVE, level=Quantity(373.15, "K")),
        AggregationSpec("heater_energy", "heater_power", AggregateForm.INTEGRAL_DOSE),
        AggregationSpec("heater_on_cycles", "heater_power", AggregateForm.CYCLE_COUNT, level=Quantity(1, "W")),
        AggregationSpec("heater_temp_histogram", "heater_temperature", AggregateForm.HISTOGRAM,
                        bin_edges=tuple(Quantity(v, "K") for v in (250, 300, 350, 400, 450, 500, 700))),
    )


def lifecycle(drift_model=None, drift_aggregate="heater_teq"):
    drift = drift_model or ArrheniusResistanceDrift(k_drift=Quantity(5.6e-9, "1/s"))
    return (
        LifecycleBinding("thermal", LinearWetnessMoistureUptake(k_uptake=Quantity(6e-8, "1/s"), max_wet_time=Quantity(10, "day")),
                         (InputBinding("wet_time", "wetness"),)),
        LifecycleBinding("electrical", drift, (InputBinding("equivalent_time", drift_aggregate),)),
    )


REPRESENTATIVE_DAY = RepresentativePolicy(
    "leading-day", "leading_period", Quantity(1, "day"),
    ("each represented day repeats the resolved day's heater temperature and power history",
     "environment-driven lifecycle doses are NOT repeated: they integrate the full BIG 3 history of the macro window",
     "slow state is held constant inside a macro window for the fast physics"),
    "only while the chamber program is 24 h periodic up to a slow drift; program changes are events that split macro windows",
    "extensive aggregates scale by the exact weight; order and extrema of unresolved days are not claimed",
    periodicity_tolerances=(("air_temperature", Quantity(2.0, "K")), ("humidity", Quantity(0.005, "dimensionless")),
                            ("wetness", Quantity(0.0, "dimensionless")), ("supply", Quantity(0.0, "V"))))
FULLY_RESOLVED = RepresentativePolicy(
    "fully-resolved", "fully_resolved", None, (), "every hour of every macro window is resolved by the fast physics",
    "aggregates are exact over the resolved coupling windows")


def policy(*, default_days=7, representative=REPRESENTATIVE_DAY, event_handling="split", limits=None, near_threshold=True,
           minimum_days=1, version="1"):
    rules = [AdaptationRule("default", "default", Quantity(default_days, "day"))]
    watches = ()
    if near_threshold:
        rules.append(AdaptationRule("near-moisture-breakpoint", "near_threshold", Quantity(2, "day"), participant_id="thermal",
                                    variable_id="moisture_content", threshold=Quantity(0.05, "dimensionless"),
                                    band=Quantity(0.008, "dimensionless")))
        watches = (ThresholdWatch("moisture-breakpoint", "thermal", "moisture_content", Quantity(0.05, "dimensionless"),
                                  Quantity(2, "day")),)
    if limits is None:
        limits = (StateChangeLimit("thermal", "moisture_content", Quantity(0.10, "dimensionless"), 0.3),
                  StateChangeLimit("electrical", "resistance_drift", Quantity(0.10, "dimensionless"), 0.5))
    return MacroStepPolicy("heater-board-macro", version, tuple(rules), Quantity(minimum_days, "day"), EventHandling(event_handling),
                           representative, tuple(limits), watches)


def initial_slow(moisture=0.0, drift=0.0):
    return {"thermal": {"moisture_content": InitialStateValue("moisture_content", Quantity(moisture, "dimensionless"), UNKNOWN("as installed"))},
            "electrical": {"resistance_drift": InitialStateValue("resistance_drift", Quantity(drift, "dimensionless"), UNKNOWN("as built"))}}


# ---- fast system ----------------------------------------------------------------

AREA, BOARD_L, FILM_H = 0.01, 0.005, 25.0  # m^2, m, W/(m^2 K): illustrative lumped geometry
COMPLETE = ("each solve is a pure function of its coupling inputs, the participant's declared (held) slow state, "
            "the window's environment/usage records and the fixed system definition; the provider problem is rebuilt "
            "per call and no provider keeps state between solves (quasi-static per coupling window)")


class _Record:
    def __init__(self, rec):
        self.succeeded, self.reason = rec.succeeded, getattr(rec, "reason", "")
        self.execution_identity = getattr(rec, "execution_identity", "")
        self.digest = getattr(rec, "digest", "")


def _spec(pid, ports, solver_id, solver_version):
    return ParticipantSpec(pid, f"{pid}-model", "1", f"{pid}-realization", "1", solver_id, solver_version, "forge.coupling", "1",
                           tuple(ports), transient=False, checkpointable=True, deterministic_restore=True,
                           description="quasi-static: solved to equilibrium once per coupling window; no time integration")


class ReferenceHeaterSystem(FastSystem):
    """BIG 9 coupled heater/board system seen as a BIG 10 fast subsystem."""

    thermal_solver = ("numpy.dense_lu", "BIG6")
    series_ohm = 1.0

    def __init__(self, environment: EnvironmentTimeline, *, coupling_window_s=HOUR, completeness=StateCompleteness.DECLARED_COMPLETE,
                 stale_material=False, fail_after_s=None):
        self.environment = environment
        self.timeline = environment.timeline
        self.coupling_window_s = coupling_window_s
        self.stale_material = stale_material
        self.fail_after_s = fail_after_s
        self.board = board_set()
        contracts = (ParticipantStateContract("electrical", ("resistance_drift",), (), completeness, COMPLETE),
                     ParticipantStateContract("thermal", ("moisture_content",), (), completeness, COMPLETE))
        self.identity = FastSystemIdentity(
            "heater-board-fast", "1", self._graph_fingerprint(),
            {"template_fingerprint": self._plan(0, coupling_window_s).fingerprint(), "coupling_window_s": coupling_window_s},
            (self.thermal_solver, ("scipy.optimize.root", "lm")), self.configuration(), contracts,
            (MaterialBinding("thermal", "moisture_content", M.BOARD.digest, "moisture_content"),),
            (("heater_temperature", "K"), ("heater_power", "W")), field_mapping=False, pure=True,
            purity_basis="every execution builds a fresh MultiphysicsRuntime, fresh participants and fresh provider problems "
                         "from the request only; declared initial coupling iterates are constants; no warm start")
        self.executions = 0

    # -- identity helpers --
    def configuration(self):
        return {"lumped": {"area_m2": AREA, "board_thickness_m": BOARD_L, "film_W_m2K": FILM_H},
                "circuit": {"series_ohm": self.series_ohm, "r0_ohm": 10.0, "t0_K": 293.15, "alpha_1_K": 0.004, "root_method": "lm"},
                "board_property_set": self.board.digest,
                "board_property_lookup": "resolved at the solved maximum temperature bounding the board; refused outside 273.15-473.15 K",
                "coupling": {"relaxation": 0.7, "tol_temperature_K": 1e-6, "tol_power_W": 1e-8, "max_iterations": 60}}

    def _graph(self, thermal_spec=None, electrical_spec=None):
        t = thermal_spec or _spec("thermal", [scalar_port("power", "input", "electrical_power", "W"), scalar_port("t_mean", "output", "temperature", "K")], *self.thermal_solver)
        e = electrical_spec or _spec("electrical", [scalar_port("temperature", "input", "temperature", "K"), scalar_port("power", "output", "electrical_power", "W")], "scipy.optimize.root", "lm")
        conversion = EnergyConversion("joule_heating", "electrical", "thermal", "W", efficiency=1.0,
                                      description="DECLARED model assumption: all heater dissipation is deposited in the heater node; "
                                                  "efficiency uncertainty not declared (UNKNOWN)")
        return PhysicsGraph("heater-board", (t, e), (CouplingEdge("e_temp", PortRef("thermal", "t_mean"), PortRef("electrical", "temperature")),
                                                     CouplingEdge("e_power", PortRef("electrical", "power"), PortRef("thermal", "power"),
                                                                  conversion=conversion)))

    def _graph_fingerprint(self):
        return self._graph().fingerprint()

    def _plan(self, start_s, end_s):
        return CouplingPlan("heater-board-plan", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                            TimePolicy(Quantity(start_s, "s"), Quantity(end_s, "s"), Quantity(self.coupling_window_s, "s")),
                            ("electrical", "thermal"),
                            (ConvergenceCriterion("e_temp", 0.0, Quantity(1e-6, "K")), ConvergenceCriterion("e_power", 0.0, Quantity(1e-8, "W"))),
                            RelaxationPolicy(RelaxationKind.CONSTANT, 0.7), 60, True)

    # -- physics --
    def conductivity(self, moisture, temperature):
        state = MaterialState(M.BOARD, (NamedQuantity("moisture_content", moisture), NamedQuantity("temperature", temperature)))
        resolved = self.board.resolve("thermal_conductivity", state)
        if resolved.status != "known":
            raise CouplingRefusal(f"board conductivity UNKNOWN at {temperature}: {resolved.reason}")
        return state, resolved

    def material_states(self, moisture, temperature):
        """Every (MaterialState, ResolvedProperty) the thermal solve uses at this slow state and temperature."""
        return (self.conductivity(moisture, temperature),)

    def thermal_solve(self, power_W, ambient_K, moisture, start_s):
        """Lumped 2-node network (heater node, board surface) through the BIG 6 dense LU provider.

        Returns (record, mean temperature, temperature bounding the board from above)."""
        _, resolved = self.conductivity(moisture, Quantity(ambient_K, "K"))
        k = resolved.value.value.magnitude_in("W/(m*K)")
        g1, g2 = k * AREA / BOARD_L, FILM_H * AREA
        a = np.array([[g1, -g1], [-g1, g1 + g2]])
        b = np.array([power_W, g2 * ambient_K])
        problem = NumericalProblem("lumped-heater-board", ProblemKind.LINEAR, OperatorIdentity("thermal.lumped_board", "1", array_digest(a, b), "array_bytes"),
                                   UnitBoundary((VariableSpec("T", "K", scale=1.0, size=2),)), {"matrix": a, "rhs": b})
        rec = NumPyDenseLinearProvider().execute(problem, NumericalMethod("dense_lu", SolverSettings({"residual_rtol": 1e-12}, {})))
        if not rec.succeeded:
            return _Record(rec), None, None
        heater = rec.outputs["T"][0].to("K")
        return _Record(rec), heater, heater

    def _env(self, channel, start_s):
        v = self.environment.channel_value(channel, p(start_s))
        if v.status.value != "known":
            raise CouplingRefusal(f"environment {channel} UNKNOWN at {start_s} s: {v.reason}")
        return v.value.value

    def _usage(self, start_s):
        v = self.timeline.history("supply").value_at(p(start_s))
        if v.status.value != "known":
            raise CouplingRefusal(f"supply voltage UNKNOWN at {start_s} s")
        return v.value.value

    def execute(self, request):
        from engcore.coupling import CouplingExecutionLog

        self.executions += 1
        start_s, end_s = float(request.window.start.seconds), float(request.window.end.seconds)
        if self.fail_after_s is not None and start_s >= self.fail_after_s:
            raise CouplingRefusal("declared participant failure for the refusal test")
        moisture = request.slow_state["thermal"]["moisture_content"].value
        drift = request.slow_state["electrical"]["resistance_drift"].value.magnitude_in("dimensionless")
        if self.stale_material:
            moisture = Quantity(0.0, "dimensionless")
        store = InMemoryBulkStore()
        seen: dict[tuple[float, float], dict] = {}
        materials = {}

        def thermal(inputs, start, end, uq, state):
            s = start.magnitude_in("s")
            m = state["moisture_content"].value if not self.stale_material else moisture
            ambient = self._env("air_temperature", s).to("K")
            rec, t, t_board_max = self.thermal_solve(inputs["power"].to("W").magnitude, ambient.magnitude, m, s)
            if t is None:
                return rec, {}
            # the property was resolved at the ambient temperature; re-resolve at the SOLVED bound and
            # refuse unless it is inside the data's applicability and gives the same value
            used = {ms.material.digest: r for ms, r in self.material_states(m, ambient)}
            for mstate, resolved in self.material_states(m, t_board_max):
                if resolved.value.value != used[mstate.material.digest].value.value:
                    raise CouplingRefusal("material property depends on the solved temperature; this quasi-static "
                                          "participant does not iterate it")
                materials[mstate.digest] = (mstate, resolved)
            seen.setdefault((s, end.magnitude_in("s")), {})["t"] = t
            return rec, {"t_mean": t}

        def electrical(inputs, start, end, uq, state):
            s = start.magnitude_in("s")
            circuit = HeaterCircuit(self._usage(s), Quantity(self.series_ohm, "ohm"), Quantity(10.0 * (1.0 + state["resistance_drift"].value.magnitude), "ohm"),
                                    Quantity(293.15, "K"), Quantity(0.004, "1/K"), root_method="lm")
            rec, power = circuit.solve(inputs["temperature"])
            if power is not None:
                seen.setdefault((s, end.magnitude_in("s")), {})["p"] = power
            return rec, ({} if power is None else {"power": power})

        tspec = _spec("thermal", [scalar_port("power", "input", "electrical_power", "W"), scalar_port("t_mean", "output", "temperature", "K")], *self.thermal_solver)
        espec = _spec("electrical", [scalar_port("temperature", "input", "temperature", "K"), scalar_port("power", "output", "electrical_power", "W")], "scipy.optimize.root", "lm")
        tp = provider_participant(tspec, solve=thermal, initial_outputs=lambda: {"t_mean": Quantity(300, "K")}, store=store,
                                  log=CouplingExecutionLog(), state_definitions=(InitialStateDefinition("moisture_content", "dimensionless"),),
                                  state_contract=self.identity.contract("thermal"))
        ep = provider_participant(espec, solve=electrical, initial_outputs=lambda: {"power": Quantity(0.1, "W")}, store=store,
                                  log=CouplingExecutionLog(), state_definitions=(InitialStateDefinition("resistance_drift", "dimensionless"),),
                                  state_contract=self.identity.contract("electrical"))
        runtime = MultiphysicsRuntime(self._graph(tspec, espec), self._plan(start_s, end_s), {"thermal": tp, "electrical": ep},
                                      resolver=BulkDataResolver(store), store=store)
        unknown = UNKNOWN("declared initial iterate")
        init = {pid: {k: InitialStateValue(k, v.value, v.uncertainty) for k, v in vals.items()} for pid, vals in request.slow_state.items()}
        run = runtime.run(f"fast-{int(start_s)}-{int(end_s)}", external_inputs={}, initial_state=init,
                          initial_coupling_values={"e_temp": Quantity(300, "K"), "e_power": Quantity(0.1, "W")},
                          initial_coupling_uncertainty={"e_temp": unknown, "e_power": unknown}, scenario_digest=request.scenario_digest)
        temps, powers = [], []
        for w in run.windows:
            key = (w.start.magnitude_in("s"), w.end.magnitude_in("s"))
            win = TimeWindow(p(Fraction(repr(key[0]))), p(Fraction(repr(key[1]))))
            temps.append(OutputSample(win, seen[key]["t"]))
            powers.append(OutputSample(win, seen[key]["p"]))
        # the observer's last window must be what the runtime reported
        assert abs(temps[-1].value.magnitude - run.final_outputs["thermal.t_mean"]["magnitude"]) < 1e-12
        digest = run_digest(run)
        series = (OutputSeries("heater_temperature", "K", tuple(temps), digest), OutputSeries("heater_power", "W", tuple(powers), digest))
        props = tuple({"property": "thermal_conductivity", "material": m.material.family, "value_W_mK": r.value.value.magnitude_in("W/(m*K)"),
                       "derivation": r.derivation.value, "state_digest": r.state_digest, "set_digest": r.set_digest, "digest": r.digest}
                      for _, (m, r) in sorted(materials.items()) if m.material.digest == M.BOARD.digest)
        props += tuple({"property": "thermal_conductivity", "material": m.material.family, "value_W_mK": r.value.value.magnitude_in("W/(m*K)"),
                        "derivation": r.derivation.value, "state_digest": r.state_digest, "set_digest": r.set_digest, "digest": r.digest}
                       for _, (m, r) in sorted(materials.items()) if m.material.digest != M.BOARD.digest)
        return FastExecutionResult(
            request.identity, (run.run_id,), (digest,), series, {}, tuple(m for _, (m, _) in sorted(materials.items())), props,
            len(run.windows), sum(len(w.iterations) for w in run.windows), tuple(w.outcome.value for w in run.windows),
            self.identity.providers, consumed_environment_digest=self.environment.digest, consumed_timeline_digest=self.timeline.digest)


def build_runtime(days=63, *, run_id="heater-board-ms", change_at_hour=None, system_cls=ReferenceHeaterSystem, system_kwargs=None,
                  environment=None, **policy_kwargs):
    env = environment or build_environment(days, change_at_hour=change_at_hour)[0]
    system = system_cls(env, **(system_kwargs or {}))
    runtime = MultiTimescaleRuntime(run_id=run_id, hierarchy=hierarchy(), policy=policy(**policy_kwargs), fast_system=system,
                                    environment=env, aggregations=aggregations(), lifecycle=lifecycle())
    return runtime, system, env
