"""Lifecycle / Degradation Engine (BIG 4): closed-loop and adversarial tests.

The reference degradation models are architectural probes with uncalibrated
parameters.  Nothing here validates a physical claim; replay agreement is
reproducibility only.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domains.battery.aging import CalendarCycleCapacityFade
from engcore.domains.corrosion.thickness_loss import LinearDoseThicknessLoss
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitialStateDefinition, InitialStateReceipt,
    InitialStateValue, InitializationResult, MultiphysicsRuntime,
)
from engcore.scenarios import (
    ChannelRepresentation, CycleHistory, CycleRecord, DegradationStepRecord, EnvironmentChannel,
    EnvironmentKindRegistry, EnvironmentSample, EnvironmentSource, EnvironmentTimeline,
    HistoryEntry, InputBinding, InterpolationContract, LifecycleChain, NamedQuantity,
    QuantityHistory, ReferenceContext, ScenarioSegment, ScenarioSpecification, StepStatus,
    TimeBasis, Timeline, TimePoint, TimeWindow, WindowClosure, carry_forward,
    evaluate_degradation, run_lifecycle,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.multiphysics.receipts import StateVariableValue
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.units.quantity import Quantity

B = "life"
BASIS = TimeBasis(B, "elapsed", "commissioning")
DAY = 86400


def D(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


def tp(days):
    return TimePoint(B, Quantity(days, "day"))


def dwin(a, b, closure=WindowClosure.HALF_OPEN):
    return TimeWindow(tp(a), tp(b), closure)


def std(v, unit):
    return Uncertainty(kind="standard", standard_uncertainty=Quantity(v, unit), method="site spec")


SCENARIO = ScenarioSpecification("service-life", "1", Quantity(0, "day"), Quantity(3, "day"),
                                 segments=(ScenarioSegment("service", Quantity(0, "day"), Quantity(3, "day")),))
SOURCES = (
    EnvironmentSource("site-met", "measured", "operator", D("met"), "1"),
    EnvironmentSource("candle", "measured", "operator", D("candle"), "1"),
)
SITE = ReferenceContext("site", "yard", "enu")
UNKNOWN = Uncertainty.unknown("not quantified")


# ---- physics participants that READ the degradable state ------------------


def _stateful_participant(pid, variable, unit, output, output_unit, physics):
    """A transient participant whose output over a window depends on its state variable."""
    spec = ParticipantSpec(pid, "model", "1", "realization", "1", "solver", "1", "adapter", "1",
                           (PortDefinition(output, PortDirection.OUTPUT, PortKind.SCALAR, output, output_unit),),
                           transient=True)
    held = {}

    def digest(value):
        return hashlib.sha256(f"{variable}={value.magnitude_in(unit)!r}".encode()).hexdigest()

    def initialize(_instant, _inputs, _uq):
        raise InvalidScientificProblem("this participant requires an explicit initial state")

    def initialize_state(instant, state, _inputs, _uq):
        value = state[variable]
        held["value"], held["uq"] = value.value, value.uncertainty
        receipt = InitialStateReceipt(pid, instant, (InitialStateValue(variable, value.value, value.uncertainty),), digest(value.value))
        return InitializationResult({output: physics(held["value"], Quantity(0, "s"))}, {output: UNKNOWN}, initial_state_receipt=receipt)

    def advance(request):
        dt = request.end.to("s") if hasattr(request.end, "to") else request.end
        span = Quantity(request.end.magnitude_in("s") - request.start.magnitude_in("s"), "s")
        return AdvanceResult(request.end, {output: physics(held["value"], span)}, {output: UNKNOWN}, 1, True)

    participant = CallbackParticipant(
        spec, initialize=initialize, advance=advance,
        initial_state_definitions=(InitialStateDefinition(variable, unit),),
        initialize_state=initialize_state,
        state_identity=lambda _t: digest(held["value"]),
        public_state=lambda _t: (StateVariableValue(variable, held["value"], held["uq"]),),
    )
    return spec, participant


def _executor(pid, variable, unit, output, output_unit, physics, scenario=SCENARIO):
    def execute(run_id, window, initial_state):
        spec, participant = _stateful_participant(pid, variable, unit, output, output_unit, physics)
        start, end = window.start.quantity, window.end.quantity
        plan = CouplingPlan(f"{run_id}-plan", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                            TimePolicy(start, end, Quantity(end.magnitude - start.magnitude, "s")))
        store = InMemoryBulkStore()
        runtime = MultiphysicsRuntime(PhysicsGraph(f"{run_id}-g", (spec,), ()), plan, {pid: participant},
                                      resolver=BulkDataResolver(store), store=store)
        return runtime.run(run_id, external_inputs={}, initial_state=initial_state, scenario_digest=scenario.digest)
    return execute


# battery: state-of-charge swing for a fixed 2 A draw over the window, in "fraction of capacity"
def _soc_drop(capacity, span):
    return Quantity(2.0 * span.magnitude_in("h") / capacity.magnitude_in("A*h"), "dimensionless")


# wall: conductive heat flux through the wall, k * dT / thickness
def _heat_flux(thickness, _span):
    return Quantity(50.0 * 20.0 / thickness.magnitude_in("m"), "W/m^2")


BATTERY = dict(pid="cell", variable="capacity", unit="A*h", output="soc_drop", output_unit="dimensionless", physics=_soc_drop)
WALL = dict(pid="wall", variable="wall_thickness", unit="m", output="heat_flux", output_unit="W/m^2", physics=_heat_flux)
WINDOWS = (dwin(0, 1), dwin(1, 2), dwin(2, 3))


# ---- environment -------------------------------------------------------------


def _interval(hid, qid, unit, values, uq=None):
    return QuantityHistory(hid, "exposure", qid, unit, tuple(
        HistoryEntry(dwin(i, i + 1), NamedQuantity(qid, Quantity(v, unit), uq)) for i, v in enumerate(values) if v is not None
    ))


def _environment(*, chloride=(100, 150, 120), temps=(298.15, 313.15, 303.15), cycle_hours=12, extra_channels=()):
    histories = (
        _interval("temp-days", "air-temp", "K", temps, std(0.5, "K")),
        _interval("wet-days", "wetness", "dimensionless", (0.3, 0.6, 0.4)),
        _interval("cl-days", "chloride", "mg/m^2/day", chloride),
    )
    n = 72 // cycle_hours
    cycles = CycleHistory("efc", "equivalent_full_cycle", tuple(
        CycleRecord(f"c{i}", i, TimeWindow(TimePoint(B, Quantity(i * cycle_hours, "hour")), TimePoint(B, Quantity((i + 1) * cycle_hours, "hour"))))
        for i in range(n)
    ))
    timeline = Timeline.from_scenario(SCENARIO, timeline_id="life", basis=BASIS, histories=histories, cycle_histories=(cycles,))
    horizon = dwin(0, 3)
    channels = (
        EnvironmentChannel("air-temp", "ambient_temperature", "K", "site-met", SITE, horizon, ChannelRepresentation.INTERVAL_HISTORY, history_id="temp-days"),
        EnvironmentChannel("wetness", "surface_wetness", "dimensionless", "site-met", SITE, horizon, ChannelRepresentation.INTERVAL_HISTORY, history_id="wet-days"),
        EnvironmentChannel("chloride", "chloride_deposition_rate", "mg/m^2/day", "candle", SITE, horizon, ChannelRepresentation.INTERVAL_HISTORY, history_id="cl-days"),
    ) + tuple(extra_channels)
    return EnvironmentTimeline("life-env", timeline, EnvironmentKindRegistry.standard(), SOURCES, channels)


def _battery_model():
    return CalendarCycleCapacityFade(
        nominal_capacity=Quantity(5, "A*h"), k_calendar=Quantity(2e-7, "1/s"),
        activation_energy=Quantity(50e3, "J/mol"), reference_temperature=Quantity(298.15, "K"),
        k_cycle=Quantity(2e-4, "dimensionless"),
    )


def _corrosion_model(max_dose=Quantity(1, "g/m^2")):
    return LinearDoseThicknessLoss(k_wet=Quantity(1e-11, "m/s"), k_chloride=Quantity(2e-3, "m / (kg/m^2)"), max_chloride_dose=max_dose)


BATTERY_BINDINGS = (InputBinding("mean_temperature", "air-temp"), InputBinding("full_cycles", "efc"))
CORROSION_BINDINGS = (InputBinding("wet_time", "wetness"), InputBinding("chloride_dose", "chloride"))


def _initial(pid, variable, value, unit):
    return {pid: {variable: InitialStateValue(variable, Quantity(value, unit), Uncertainty.unknown("as-built value not measured"))}}


def _battery_loop(env=None, model=None):
    return run_lifecycle(
        model=model or _battery_model(), environment=env or _environment(), participant_id="cell",
        definitions=(InitialStateDefinition("capacity", "A*h"),),
        initial_state=_initial("cell", "capacity", 5.0, "A*h"), windows=WINDOWS,
        execute=_executor(**BATTERY), bindings=BATTERY_BINDINGS,
    )


def _wall_loop(env=None, model=None):
    return run_lifecycle(
        model=model or _corrosion_model(), environment=env or _environment(), participant_id="wall",
        definitions=(InitialStateDefinition("wall_thickness", "m"),),
        initial_state=_initial("wall", "wall_thickness", 0.002, "m"), windows=WINDOWS,
        execute=_executor(**WALL), bindings=CORROSION_BINDINGS,
    )


def _output(run, name):
    pid = "cell" if name == "soc_drop" else "wall"
    return run.final_outputs[f"{pid}.{name}"]["magnitude"]


# ---- closed loop: degradation changes FUTURE physics ------------------------


def test_battery_capacity_fade_feeds_forward_into_later_windows():
    chain, runs = _battery_loop()
    assert [s.status for s in chain.steps] == [StepStatus.APPLIED] * 3
    capacities = [5.0] + [s.resulting_values[0].value.magnitude for s in chain.steps]
    assert all(a > b for a, b in zip(capacities, capacities[1:]))
    # physics in window k+1 used the degraded capacity from step k
    swings = [_output(r, "soc_drop") for r in runs]
    assert swings == pytest.approx([2 * 24 / c for c in capacities[:3]])
    assert swings[0] < swings[1] < swings[2]
    # a counterfactual loop with no feed-forward would have produced identical swings
    undegraded = _executor(**BATTERY)("static", dwin(1, 2), _initial("cell", "capacity", 5.0, "A*h"))
    assert _output(undegraded, "soc_drop") != pytest.approx(swings[1])
    # hotter day 2 degrades faster than day 1 (same cycles)
    assert (capacities[1] - capacities[2]) > (capacities[0] - capacities[1])


def test_corrosion_thickness_loss_feeds_forward_into_heat_flux():
    chain, runs = _wall_loop()
    thickness = [0.002] + [s.resulting_values[0].value.magnitude for s in chain.steps]
    assert all(a > b for a, b in zip(thickness, thickness[1:]))
    fluxes = [_output(r, "heat_flux") for r in runs]
    assert fluxes == pytest.approx([1000 / t for t in thickness[:3]])
    assert fluxes[0] < fluxes[1] < fluxes[2]


def test_step_binds_scenario_environment_run_inputs_model_and_provenance():
    env = _environment()
    chain, runs = _wall_loop(env)
    step = chain.steps[1]
    assert step.scenario_digest == SCENARIO.digest and step.environment_digest == env.digest
    assert step.window == dwin(1, 2)
    assert step.prior_state_digest == max(runs[1].state_transitions, key=lambda t: t.window_index).end_state_digest
    cl = next(i for i in step.inputs if i.input_id == "chloride_dose")
    assert (cl.record_id, cl.context_id, cl.source_id, cl.source_content_digest) == ("chloride", "site", "candle", D("candle"))
    assert cl.source_classification == "imposed_environment_input"
    assert step.model.model_id == "corrosion.linear_dose_thickness_loss"
    assert step.to_dict()["classification"] == "degradation_model_output_not_evidence"


def test_uncertainty_components_are_separated_and_result_stays_unknown():
    chain, _ = _battery_loop()
    status = dict(chain.steps[0].uncertainty_status)
    assert status["model_discrepancy"] == "unknown"
    assert status["input:mean_temperature"] == "unknown"  # bound is not a 1-sigma
    assert status["input:full_cycles"] == "unknown"
    assert status["resulting_state"] == "unknown"
    assert chain.steps[0].resulting_values[0].uncertainty.kind is UncertaintyKind.UNKNOWN


def test_replay_reproduces_chain_identity_and_roundtrips():
    first, runs = _battery_loop()
    second, _ = _battery_loop()
    assert first.digest == second.digest
    again = LifecycleChain.from_dict(json.loads(json.dumps(first.to_dict())))
    assert again.digest == first.digest
    again.verify(runs)
    assert DegradationStepRecord.from_dict(first.steps[0].to_dict()) == first.steps[0]


def test_replay_detects_changed_parameters_or_environment():
    base, _ = _battery_loop()
    hotter, _ = _battery_loop(env=_environment(temps=(299.15, 313.15, 303.15)))
    faster = CalendarCycleCapacityFade(nominal_capacity=Quantity(5, "A*h"), k_calendar=Quantity(3e-7, "1/s"),
                                       activation_energy=Quantity(50e3, "J/mol"), reference_temperature=Quantity(298.15, "K"),
                                       k_cycle=Quantity(2e-4, "dimensionless"))
    tuned, _ = _battery_loop(model=faster)
    assert len({base.digest, hotter.digest, tuned.digest}) == 3


# ---- fail-closed -------------------------------------------------------------


def test_exposure_gap_stops_the_loop_instead_of_meaning_zero():
    chain, runs = _wall_loop(_environment(chloride=(100, 150, None)))
    assert [s.status for s in chain.steps] == [StepStatus.APPLIED, StepStatus.APPLIED, StepStatus.UNKNOWN_INPUT]
    assert "not zero" in chain.steps[2].reason and not chain.steps[2].resulting_values
    with pytest.raises(InvalidScientificProblem, match="no degraded state"):
        carry_forward(chain.steps[2], runs[2], (InitialStateDefinition("wall_thickness", "m"),))


def test_out_of_applicability_is_not_applied():
    chain, _ = _wall_loop(model=_corrosion_model(max_dose=Quantity(0.12, "g/m^2")))
    assert [s.status for s in chain.steps] == [StepStatus.APPLIED, StepStatus.NOT_APPLICABLE]
    chain, _ = _battery_loop(env=_environment(temps=(298.15, 330.0, 303.15)))
    assert chain.steps[-1].status is StepStatus.NOT_APPLICABLE


def test_partial_or_unrecorded_cycles_are_unknown():
    # 7 h cycles straddle the 24 h window boundary
    chain, _ = _battery_loop(env=_environment(cycle_hours=7))
    assert chain.steps[0].status is StepStatus.UNKNOWN_INPUT
    assert "straddle" in next(i for i in chain.steps[0].inputs if i.input_id == "full_cycles").reason
    # 10 cycles of 7 h end at 70 h: day 3 reaches past the recorded span -> UNKNOWN, not zero


def test_point_sample_channel_provides_no_dose():
    point = EnvironmentChannel("cl-spot", "chloride_deposition_rate", "mg/m^2/day", "candle",
                               ReferenceContext("spot", "yard", "enu"), dwin(0, 3, WindowClosure.CLOSED), "point_samples",
                               tuple(EnvironmentSample(tp(d), NamedQuantity("cl-spot", Quantity(100, "mg/m^2/day"))) for d in (0, 1, 2, 3)),
                               InterpolationContract("linear", Quantity(1, "day")))
    env = _environment(extra_channels=(point,))
    run = _executor(**WALL)("w", dwin(0, 1), _initial("wall", "wall_thickness", 0.002, "m"))
    step = evaluate_degradation(_corrosion_model(), environment=env, run=run, participant_id="wall",
                                bindings=(InputBinding("wet_time", "wetness"), InputBinding("chloride_dose", "cl-spot")))
    assert step.status is StepStatus.UNKNOWN_INPUT


def test_bindings_are_explicit_and_kind_checked():
    env = _environment()
    run = _executor(**WALL)("w", dwin(0, 1), _initial("wall", "wall_thickness", 0.002, "m"))
    with pytest.raises(InvalidScientificProblem, match="exactly the model's inputs"):
        evaluate_degradation(_corrosion_model(), environment=env, run=run, participant_id="wall", bindings=CORROSION_BINDINGS[:1])
    with pytest.raises(InvalidScientificProblem, match="carries 'ambient_temperature'"):
        evaluate_degradation(_corrosion_model(), environment=env, run=run, participant_id="wall",
                             bindings=(InputBinding("wet_time", "wetness"), InputBinding("chloride_dose", "air-temp")))


def test_run_for_another_scenario_is_refused():
    other = ScenarioSpecification("elsewhere", "1", Quantity(0, "day"), Quantity(3, "day"))
    run = _executor(**WALL, scenario=other)("w", dwin(0, 1), _initial("wall", "wall_thickness", 0.002, "m"))
    with pytest.raises(InvalidScientificProblem, match="different scenario"):
        evaluate_degradation(_corrosion_model(), environment=_environment(), run=run, participant_id="wall", bindings=CORROSION_BINDINGS)


def test_state_not_published_is_unknown_state():
    run = _executor(**WALL)("w", dwin(0, 1), _initial("wall", "wall_thickness", 0.002, "m"))
    step = evaluate_degradation(_battery_model(), environment=_environment(), run=run, participant_id="wall", bindings=BATTERY_BINDINGS)
    assert step.status is StepStatus.UNKNOWN_STATE


def test_chain_refuses_a_window_that_did_not_start_from_the_degraded_state():
    chain, runs = _wall_loop()
    stale = _executor(**WALL)(runs[1].run_id, dwin(1, 2), _initial("wall", "wall_thickness", 0.002, "m"))
    forged_runs = (runs[0], stale, runs[2])
    with pytest.raises(InvalidScientificProblem, match="not the run"):
        chain.verify(forged_runs)
    # even with a step recomputed on the stale run, the chain link is refused
    env = _environment()
    restep = evaluate_degradation(_corrosion_model(), environment=env, run=stale, participant_id="wall", bindings=CORROSION_BINDINGS)
    relinked = LifecycleChain("wall", (chain.steps[0], restep))
    with pytest.raises(InvalidScientificProblem, match="did not start from the degraded"):
        relinked.verify((runs[0], stale))


def test_chain_refuses_mixed_environments_and_gaps():
    a, _ = _wall_loop()
    b, _ = _wall_loop(_environment(chloride=(100, 151, 120)))
    with pytest.raises(InvalidScientificProblem, match="mixes"):
        LifecycleChain("wall", (a.steps[0], b.steps[1]))
    with pytest.raises(InvalidScientificProblem, match="contiguous"):
        LifecycleChain("wall", (a.steps[0], a.steps[2]))


def test_verify_refuses_next_window_with_quantified_uncertainty_forgery():
    chain, runs = _wall_loop()
    degraded = chain.steps[0].resulting_values[0]
    forged_state = {"wall": {"wall_thickness": InitialStateValue(
        "wall_thickness", degraded.value,
        Uncertainty(kind="standard", standard_uncertainty=Quantity(1e-6, "m"), method="invented"))}}
    forged = _executor(**WALL)(runs[1].run_id, dwin(1, 2), forged_state)
    env = _environment()
    restep = evaluate_degradation(_corrosion_model(), environment=env, run=forged, participant_id="wall", bindings=CORROSION_BINDINGS)
    with pytest.raises(InvalidScientificProblem, match="did not start from the degraded"):
        LifecycleChain("wall", (chain.steps[0], restep)).verify((runs[0], forged))


def test_model_without_applicability_is_refused():
    model = _corrosion_model()
    model.applicability = ()
    with pytest.raises(InvalidScientificProblem, match="declares no applicability"):
        _wall_loop(model=model)


def test_chain_refuses_mixed_models():
    a, _ = _wall_loop()
    other = LinearDoseThicknessLoss(k_wet=Quantity(2e-11, "m/s"), k_chloride=Quantity(2e-3, "m / (kg/m^2)"), max_chloride_dose=Quantity(1, "g/m^2"))
    b, _ = _wall_loop(model=other)
    with pytest.raises(InvalidScientificProblem, match="mixes degradation models"):
        LifecycleChain("wall", (a.steps[0], b.steps[1]))


def test_executor_running_a_different_window_is_refused():
    inner = _executor(**WALL)
    with pytest.raises(InvalidScientificProblem, match="different window"):
        run_lifecycle(model=_corrosion_model(), environment=_environment(), participant_id="wall",
                      definitions=(InitialStateDefinition("wall_thickness", "m"),),
                      initial_state=_initial("wall", "wall_thickness", 0.002, "m"), windows=WINDOWS,
                      execute=lambda rid, w, st: inner(rid, dwin(0, 2), st), bindings=CORROSION_BINDINGS)


def test_carry_forward_refuses_definitions_that_drop_degraded_state():
    chain, runs = _wall_loop()
    with pytest.raises(InvalidScientificProblem, match="omit degraded"):
        carry_forward(chain.steps[0], runs[0], ())
