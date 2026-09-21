"""World Runtime: a multi-segment mission, executed and evidenced end to end.

The scenario is a six-phase mission -- takeoff, climb, cruise, hover, descent,
landing -- reusing one control input across every phase.  There is deliberately
no vehicle physics here: the participants integrate what they are handed.  What
is under test is the generic runtime, which must be able to say afterwards
exactly which world it executed and what it consumed to do it.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domainpacks.builtin_battery import (
    BUILTIN_BATTERY_CELL_PACK,
    MANIFEST as BATTERY_MANIFEST,
)
from engcore.domainpacks.validation import validate_domain_pack
from engcore.execution.multiphysics import (
    AdvanceResult,
    CallbackParticipant,
    InitializationResult,
    InitialStateDefinition,
    InitialStateReceipt,
    InitialStateValue,
    MultiphysicsRuntime,
    OperatingConditionDefinition,
    ParameterDefinition,
    ParameterValue,
    ParticipantFactoryDeclaration,
    ParticipantFactoryRegistry,
    StateVariableValue,
)
from engcore.planning.records import (
    GraphPlan,
    PlannedExternalInput,
    PlannedQuantityBinding,
    ResourceEstimate,
)
from engcore.scenarios import (
    InterpolationKind,
    NamedQuantity,
    OperatingCondition,
    QuantityOfInterest,
    ScenarioEvent,
    ScenarioSegment,
    ScenarioSpecification,
    StateSnapshot,
    StateVariable,
    TerminationCondition,
    TimeSample,
    TimeSeriesInput,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.ir.constraints import ConstraintDefinition, ConstraintOperator
from engcore.scientific.multiphysics import (
    CouplingEdge,
    CouplingPlan,
    CouplingScheme,
    IterationSemantics,
    MultiphysicsRunRecord,
    ParticipantSpec,
    PhysicsGraph,
    PortDefinition,
    PortDirection,
    PortKind,
    PortRef,
    TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("this fixture quantifies no uncertainty")

HORIZON = Quantity(60, "s")
WINDOW = Quantity(5, "s")

#: takeoff, climb, cruise, hover, descent, landing -- ten seconds each.
PHASES = (
    ("takeoff", 0, 10, 900.0, 1.225),
    ("climb", 10, 20, 800.0, 1.112),
    ("cruise", 20, 30, 500.0, 1.007),
    ("hover", 30, 40, 600.0, 1.007),
    ("descent", 40, 50, 300.0, 1.112),
    ("landing", 50, 60, 200.0, 1.225),
)

THRUST = "thrust.command"
DENSITY = "air.density"
ENERGY = "mission.energy"
ALTITUDE = "mission.altitude"
ENERGY_BUDGET = "mission.energy.budget"


# =====================================================================
# A vehicle that integrates what it is handed, and a monitor watching it.
# =====================================================================

def _vehicle_factory(spec: ParticipantSpec) -> CallbackParticipant:
    held = {"altitude": Quantity(0.0, "m"), "energy_used": Quantity(0.0, "J")}
    seen = {"density": None, "mass": None}

    def digest() -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "altitude": held["altitude"].magnitude_in("m"),
                    "energy_used": held["energy_used"].magnitude_in("J"),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    def outputs():
        return (
            {"altitude": held["altitude"], "energy_used": held["energy_used"]},
            {"altitude": UNKNOWN, "energy_used": UNKNOWN},
        )

    def initialize(_instant, _inputs, _uq):
        return InitializationResult(*outputs())

    def initialize_state(instant, state, _inputs, _uq):
        held["altitude"] = state["altitude"].value
        held["energy_used"] = state["energy_used"].value
        acknowledged = tuple(sorted(state.values()))
        return InitializationResult(
            *outputs(),
            initial_state_receipt=InitialStateReceipt(
                spec.participant_id, instant, acknowledged, digest()
            ),
        )

    def advance(request):
        span = request.end.magnitude_in("s") - request.start.magnitude_in("s")
        thrust = request.inputs["thrust_command"].magnitude_in("W")
        held["energy_used"] = Quantity(
            held["energy_used"].magnitude_in("J") + thrust * span, "J"
        )
        # Altitude here is a bookkeeping integral, not aerodynamics.
        held["altitude"] = Quantity(
            held["altitude"].magnitude_in("m") + (thrust - 500.0) * span / 100.0, "m"
        )
        return AdvanceResult(request.end, *outputs(), 1, True)

    def apply_operating_conditions(_instant, values):
        seen["density"] = values[DENSITY].value
        return tuple(sorted(values.values()))

    def apply_parameters(values):
        seen["mass"] = values["mass"].value
        return tuple(sorted(values.values()))

    def public_state(_instant):
        return (
            StateVariableValue("altitude", held["altitude"], UNKNOWN),
            StateVariableValue("energy_used", held["energy_used"], UNKNOWN),
        )

    return CallbackParticipant(
        spec,
        initialize=initialize,
        advance=advance,
        initial_state_definitions=(
            InitialStateDefinition("altitude", "m"),
            InitialStateDefinition("energy_used", "J"),
        ),
        initialize_state=initialize_state,
        operating_condition_definitions=(
            OperatingConditionDefinition(DENSITY, "kg/m^3"),
        ),
        apply_operating_conditions=apply_operating_conditions,
        parameter_definitions=(ParameterDefinition("mass", "kg"),),
        apply_parameters=apply_parameters,
        state_identity=lambda _instant: digest(),
        public_state=public_state,
    )


def _monitor_factory(spec: ParticipantSpec) -> CallbackParticipant:
    # Its one input arrives over a coupling edge, and edge values are resolved
    # after every participant has initialized, so initialization sees no input
    # at all. The monitor therefore opens on its own declared ground datum
    # rather than on a value it was not given.
    ground = Quantity(0.0, "m")

    def margin(altitude):
        return (
            {"altitude_margin": Quantity(120.0 - altitude.magnitude_in("m"), "m")},
            {"altitude_margin": UNKNOWN},
        )

    def initialize(_instant, _inputs, _uq):
        return InitializationResult(*margin(ground))

    def advance(request):
        return AdvanceResult(request.end, *margin(request.inputs["altitude"]), 1, True)

    return CallbackParticipant(spec, initialize=initialize, advance=advance)


VEHICLE = ParticipantSpec(
    "vehicle", "mission.vehicle", "1", "mission.vehicle.integral", "1",
    "mission.vehicle.solver", "1", "mission.vehicle.adapter", "1",
    (
        PortDefinition("thrust_command", PortDirection.INPUT, PortKind.SCALAR, "power", "W"),
        PortDefinition("altitude", PortDirection.OUTPUT, PortKind.SCALAR, "length", "m"),
        PortDefinition("energy_used", PortDirection.OUTPUT, PortKind.SCALAR, "energy", "J"),
    ),
    transient=True,
)

MONITOR = ParticipantSpec(
    "monitor", "mission.monitor", "1", "mission.monitor.direct", "1",
    "mission.monitor.solver", "1", "mission.monitor.adapter", "1",
    (
        PortDefinition("altitude", PortDirection.INPUT, PortKind.SCALAR, "length", "m"),
        PortDefinition("altitude_margin", PortDirection.OUTPUT, PortKind.SCALAR, "length", "m"),
    ),
    transient=True,
)


def _graph() -> PhysicsGraph:
    return PhysicsGraph(
        "mission",
        (VEHICLE, MONITOR),
        (
            CouplingEdge(
                "vehicle-altitude",
                PortRef("vehicle", "altitude"),
                PortRef("monitor", "altitude"),
            ),
        ),
    )


def _plan() -> CouplingPlan:
    return CouplingPlan(
        "mission-plan",
        CouplingScheme.EXPLICIT,
        IterationSemantics.SERIAL,
        TimePolicy(Quantity(0, "s"), HORIZON, WINDOW, max_windows=64),
    )


def _registry() -> ParticipantFactoryRegistry:
    return ParticipantFactoryRegistry(
        (
            ParticipantFactoryDeclaration(
                VEHICLE.model_id, VEHICLE.model_version,
                VEHICLE.realization_id, VEHICLE.realization_version,
                VEHICLE.solver_id, VEHICLE.solver_version,
                VEHICLE.adapter_id, VEHICLE.adapter_version,
                _vehicle_factory,
            ),
            ParticipantFactoryDeclaration(
                MONITOR.model_id, MONITOR.model_version,
                MONITOR.realization_id, MONITOR.realization_version,
                MONITOR.solver_id, MONITOR.solver_version,
                MONITOR.adapter_id, MONITOR.adapter_version,
                _monitor_factory,
            ),
        )
    )


def _segment(name: str, start: int, end: int, thrust: float, density: float) -> ScenarioSegment:
    return ScenarioSegment(
        name,
        Quantity(start, "s"),
        Quantity(end, "s"),
        inputs=(
            TimeSeriesInput(
                THRUST,
                (
                    TimeSample(Quantity(start, "s"), Quantity(thrust, "W")),
                    TimeSample(Quantity(end, "s"), Quantity(thrust, "W")),
                ),
                InterpolationKind.STEP,
            ),
        ),
        operating_conditions=(
            OperatingCondition(DENSITY, Quantity(density, "kg/m^3"), UNKNOWN),
        ),
    )


def _mission(**overrides) -> ScenarioSpecification:
    defaults = dict(
        state_variables=(
            StateVariable("altitude", "m", "vehicle"),
            StateVariable("energy_used", "J", "vehicle"),
        ),
        initial_state=StateSnapshot(
            Quantity(0, "s"),
            (
                NamedQuantity("altitude", Quantity(0.0, "m"), UNKNOWN),
                NamedQuantity("energy_used", Quantity(0.0, "J"), UNKNOWN),
            ),
        ),
        segments=tuple(_segment(*phase) for phase in PHASES),
        events=(ScenarioEvent("hover.entry", Quantity(30, "s")),),
        quantities_of_interest=(
            QuantityOfInterest("mission.energy.total", ENERGY, "J"),
            QuantityOfInterest("mission.altitude.final", ALTITUDE, "m"),
        ),
        termination_conditions=(
            TerminationCondition(
                ENERGY_BUDGET,
                ConstraintDefinition(
                    ENERGY_BUDGET, ENERGY,
                    ConstraintOperator.GREATER_EQUAL, Quantity(30000, "J"),
                ),
            ),
        ),
    )
    defaults.update(overrides)
    return ScenarioSpecification(
        "mission.six_phase", "1", Quantity(0, "s"), HORIZON, **defaults
    )


BINDINGS = (
    PlannedQuantityBinding(ENERGY, PortRef("vehicle", "energy_used")),
    PlannedQuantityBinding(ALTITUDE, PortRef("vehicle", "altitude")),
)


def _graph_plan(scenario: ScenarioSpecification) -> GraphPlan:
    return GraphPlan(
        "mission.capability",
        "mission.blueprint",
        "1",
        _graph(),
        _plan(),
        ResourceEstimate(
            12, 12, Quantity(1, "s"), True, "one serial pass per coupling window"
        ),
        external_inputs=(
            PlannedExternalInput(
                PortRef("vehicle", "thrust_command"), THRUST, Quantity(900, "W")
            ),
        ),
        quantity_bindings=BINDINGS,
        scenario=scenario,
    )


def _execute(scenario: ScenarioSpecification, *, run_id: str) -> MultiphysicsRunRecord:
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime.from_factory_registry(
        _graph(), _plan(), _registry(),
        resolver=BulkDataResolver(store), store=store,
    )
    values = {item.quantity_id: item for item in scenario.initial_state.values}
    return runtime.run(
        run_id,
        external_inputs={PortRef("vehicle", "thrust_command"): Quantity(900, "W")},
        external_input_schedules={
            PortRef("vehicle", "thrust_command"): schedule
            for schedule in scenario.composed_input_schedules()
        },
        operating_conditions=scenario.composed_operating_conditions(),
        initial_state={
            "vehicle": {
                variable.variable_id: InitialStateValue(
                    variable.variable_id,
                    values[variable.variable_id].value,
                    values[variable.variable_id].uncertainty,
                )
                for variable in scenario.state_variables
            }
        },
        parameter_bindings={
            "vehicle": {"mass": ParameterValue("mass", Quantity(2.5, "kg"))}
        },
        scheduled_events=scenario.events,
        termination_conditions=scenario.termination_conditions,
        quantity_bindings={item.quantity_id: item.port for item in BINDINGS},
        quantities_of_interest=scenario.quantities_of_interest,
        scenario_digest=scenario.digest,
    )


# =====================================================================
# THE END-TO-END MISSION
# =====================================================================

def test_six_phase_mission_produces_complete_typed_execution_evidence():
    scenario = _mission()
    plan = _graph_plan(scenario)
    assert GraphPlan.from_dict(plan.to_dict()) == plan

    run = _execute(scenario, run_id="mission-run")

    # Scenario identity, bound to the run itself.
    assert run.scenario_digest == scenario.digest

    # Initial state, acknowledged by the participant that took it.
    receipt = run.initial_state_receipts[0]
    assert receipt.participant_id == "vehicle"
    assert {item.variable_id for item in receipt.values} == {"altitude", "energy_used"}

    # One control input, reused across all six phases, consumed per window.
    thrust = [item for item in run.scenario_input_receipts if item.input_id == THRUST]
    assert [item.boundary_index for item in thrust] == list(range(10))
    by_segment = {item.segment_id: item.value.magnitude_in("W") for item in thrust}
    assert by_segment == {
        "takeoff": 900.0, "climb": 800.0, "cruise": 500.0,
        "hover": 600.0, "descent": 300.0,
    }
    # The later segment owns a shared boundary: t=10 is climb, never takeoff.
    at_ten = next(item for item in thrust if item.instant.magnitude_in("s") == 10.0)
    assert at_ten.segment_id == "climb"

    # Operating conditions reached the one participant that declared them.
    densities = {
        item.segment_id: item.value.magnitude_in("kg/m^3")
        for item in run.operating_condition_receipts
    }
    assert densities == {
        "takeoff": 1.225, "climb": 1.112, "cruise": 1.007,
        "hover": 1.007, "descent": 1.112,
    }
    assert {item.participant_id for item in run.operating_condition_receipts} == {"vehicle"}

    # State evolution, proved by identity rather than asserted.
    transitions = [item for item in run.state_transitions if item.participant_id == "vehicle"]
    assert [item.window_index for item in transitions] == list(range(10))
    assert all(item.state_changed for item in transitions)
    assert transitions[0].end_state_digest == transitions[1].start_state_digest
    assert transitions[-1].end_values[1].value.magnitude_in("J") == 31000.0

    # The scheduled event created an exact synchronization boundary.
    assert [item.event_id for item in run.scheduled_events] == ["hover.entry"]
    reached = run.reached_scheduled_events[0]
    assert reached.instant.magnitude_in("s") == 30.0
    assert run.windows[reached.boundary_index - 1].end.magnitude_in("s") == 30.0

    # Termination: an early end, with the numbers it was decided on.
    assert run.ended_at.magnitude_in("s") == 50.0
    assert run.termination is not None
    assert run.termination.condition_id == ENERGY_BUDGET
    assert run.termination.boundary_index == 10
    assert run.termination.check.value.magnitude_in("J") == 31000.0
    assert run.termination.reason == "mission.energy >= 30000 joule"
    assert run.termination.scenario_digest == scenario.digest

    # Requested quantities, bound to the outputs that produced them.
    produced = {item.qoi_id: item for item in run.quantities_of_interest}
    assert set(produced) == {"mission.energy.total", "mission.altitude.final"}
    assert produced["mission.energy.total"].port == PortRef("vehicle", "energy_used")
    assert produced["mission.energy.total"].value.magnitude_in("J") == 31000.0

    # Graph and execution authority.
    assert run.graph_id == "mission"
    assert run.graph_fingerprint == _graph().fingerprint()
    assert run.plan_fingerprint == _plan().fingerprint()

    # Consumed inputs are evidence, not outputs.
    assert "_time_varying_external_inputs" not in run.final_outputs

    # And all of it survives a roundtrip.
    restored = MultiphysicsRunRecord.from_dict(run.to_dict())
    assert restored.scenario_digest == run.scenario_digest
    assert restored.scenario_input_receipts == run.scenario_input_receipts
    assert restored.operating_condition_receipts == run.operating_condition_receipts
    assert restored.state_transitions == run.state_transitions
    assert restored.termination == run.termination
    assert restored.quantities_of_interest == run.quantities_of_interest
    assert restored.initial_state_receipts == run.initial_state_receipts


# =====================================================================
# SCENARIO IDENTITY (Sprint 1 P0)
# =====================================================================

def test_scenario_identity_is_bound_without_any_scheduled_event():
    scenario = _mission(events=())
    run = _execute(scenario, run_id="no-events")

    assert run.scheduled_events == ()
    assert run.scenario_digest == scenario.digest


def test_two_missions_differing_only_in_a_phase_do_not_share_an_identity():
    other = list(PHASES)
    other[2] = ("cruise", 20, 30, 520.0, 1.007)
    changed = _mission(segments=tuple(_segment(*phase) for phase in other))

    assert changed.digest != _mission().digest
    assert _execute(changed, run_id="changed").scenario_digest == changed.digest


def test_a_scenario_bound_run_refuses_to_replay_without_its_scenario():
    run = _execute(_mission(), run_id="replay-source")
    store = InMemoryBulkStore()
    with pytest.raises(InvalidScientificProblem, match="requires its authorized scenario"):
        MultiphysicsRuntime.replay_with_factory_registry(
            run, _registry(), replay_run_id="replay",
            resolver=BulkDataResolver(store), store=store,
        )


# =====================================================================
# FAIL-CLOSED COMPOSITION AND BOUNDARY SEMANTICS
# =====================================================================

def test_segment_boundary_ownership_is_the_later_segment_everywhere():
    scenario = _mission()
    assert scenario.segment_at(Quantity(9.999, "s")).segment_id == "takeoff"
    assert scenario.segment_at(Quantity(10, "s")).segment_id == "climb"
    assert scenario.segment_at(Quantity(60, "s")).segment_id == "landing"
    assert scenario.inputs_at(Quantity(10, "s"))[THRUST].magnitude_in("W") == 800.0
    assert scenario.inputs_at(Quantity(9.5, "s"))[THRUST].magnitude_in("W") == 900.0
    assert scenario.operating_conditions_at(Quantity(20, "s"))[0].value.magnitude_in(
        "kg/m^3"
    ) == 1.007


def test_repeated_input_across_segments_composes_into_one_schedule():
    schedules = _mission().composed_input_schedules()
    assert len(schedules) == 1
    schedule = schedules[0]
    assert [item.segment_id for item in schedule.contributions] == [
        name for name, *_ in PHASES
    ]
    # Six ten-second phases share five boundaries, so the merged schedule has
    # one sample per phase plus the terminal endpoint -- no duplicated instant.
    assert len(schedule.series.samples) == 7
    assert schedule.segment_at(Quantity(10, "s")) == "climb"


def test_incompatible_units_across_segments_are_refused():
    phases = list(PHASES)
    bad = _segment(*phases[1])
    bad = replace(
        bad,
        inputs=(
            TimeSeriesInput(
                THRUST,
                (
                    TimeSample(Quantity(10, "s"), Quantity(800, "N")),
                    TimeSample(Quantity(20, "s"), Quantity(800, "N")),
                ),
                InterpolationKind.STEP,
            ),
        ),
    )
    segments = tuple(
        bad if index == 1 else _segment(*phase) for index, phase in enumerate(phases)
    )
    with pytest.raises(Exception, match="incompatible units"):
        _mission(segments=segments)


def test_an_input_that_skips_a_phase_is_refused_rather_than_filled_in():
    phases = list(PHASES)
    gapped = replace(_segment(*phases[3]), inputs=())
    segments = tuple(
        gapped if index == 3 else _segment(*phase) for index, phase in enumerate(phases)
    )
    with pytest.raises(InvalidScientificProblem, match="skips a segment"):
        _mission(segments=segments)


def test_mixed_interpolation_semantics_across_segments_are_refused():
    phases = list(PHASES)
    linear = replace(
        _segment(*phases[2]),
        inputs=(
            TimeSeriesInput(
                THRUST,
                (
                    TimeSample(Quantity(20, "s"), Quantity(500, "W")),
                    TimeSample(Quantity(30, "s"), Quantity(500, "W")),
                ),
                InterpolationKind.LINEAR,
            ),
        ),
    )
    segments = tuple(
        linear if index == 2 else _segment(*phase) for index, phase in enumerate(phases)
    )
    with pytest.raises(InvalidScientificProblem, match="changes interpolation semantics"):
        _mission(segments=segments)


def test_linear_interpolation_remains_unsupported_by_the_runtime():
    start, end = Quantity(0, "s"), HORIZON
    scenario = ScenarioSpecification(
        "mission.linear", "1", start, end,
        segments=(
            ScenarioSegment(
                "whole", start, end,
                inputs=(
                    TimeSeriesInput(
                        THRUST,
                        (
                            TimeSample(start, Quantity(900, "W")),
                            TimeSample(end, Quantity(200, "W")),
                        ),
                        InterpolationKind.LINEAR,
                    ),
                ),
            ),
        ),
    )
    assert scenario.unsupported_runtime_features == ("linear_interpolation",)
    with pytest.raises(ValueError, match="linear_interpolation"):
        _graph_plan(scenario)


# =====================================================================
# TERMINATION, QoI AND OPERATING-CONDITION REFUSALS
# =====================================================================

def test_a_condition_already_satisfied_at_the_start_refuses_to_execute():
    scenario = _mission(
        termination_conditions=(
            TerminationCondition(
                ENERGY_BUDGET,
                ConstraintDefinition(
                    ENERGY_BUDGET, ENERGY,
                    ConstraintOperator.GREATER_EQUAL, Quantity(0, "J"),
                ),
            ),
        ),
    )
    with pytest.raises(InvalidScientificProblem, match="already.*satisfied at the scenario start"):
        _execute(scenario, run_id="already-stopped")


def test_a_termination_condition_must_watch_a_declared_quantity():
    with pytest.raises(InvalidScientificProblem, match="not a declared quantity of interest"):
        _mission(
            termination_conditions=(
                TerminationCondition(
                    "mission.undeclared",
                    ConstraintDefinition(
                        "mission.undeclared", "mission.nothing",
                        ConstraintOperator.GREATER_EQUAL, Quantity(1, "J"),
                    ),
                ),
            ),
        )


def test_a_requested_quantity_with_no_producing_output_is_refused():
    scenario = _mission(
        quantities_of_interest=(
            QuantityOfInterest("mission.energy.total", ENERGY, "J"),
            QuantityOfInterest("mission.altitude.final", ALTITUDE, "m"),
            QuantityOfInterest("mission.range", "mission.range", "m"),
        ),
    )
    with pytest.raises(ValueError, match="no GraphPlan quantity binding"):
        _graph_plan(scenario)


def test_an_operating_condition_no_participant_consumes_is_refused():
    phases = list(PHASES)
    extra = OperatingCondition("air.pressure", Quantity(101325, "Pa"), UNKNOWN)
    segments = tuple(
        replace(
            _segment(*phase),
            operating_conditions=(
                OperatingCondition(DENSITY, Quantity(phase[4], "kg/m^3"), UNKNOWN),
                extra,
            ),
        )
        for phase in phases
    )
    with pytest.raises(InvalidScientificProblem, match="reach no authorized consumer"):
        _execute(_mission(segments=segments), run_id="unconsumed-condition")


def test_a_run_that_ends_early_without_a_receipt_is_refused():
    run = _execute(_mission(), run_id="truncated")
    payload = run.to_dict()
    payload["termination"] = None
    with pytest.raises(
        InvalidScientificProblem, match="must carry the termination receipt"
    ):
        MultiphysicsRunRecord.from_dict(payload)


def test_consumed_inputs_may_not_be_smuggled_back_into_the_output_map():
    run = _execute(_mission(), run_id="smuggle")
    payload = run.to_dict()
    payload["final_outputs"]["_time_varying_external_inputs"] = [{"instant": 0}]
    with pytest.raises(InvalidScientificProblem, match="execution evidence"):
        MultiphysicsRunRecord.from_dict(payload)


def test_scenario_evidence_must_be_bound_to_the_runs_own_scenario():
    run = _execute(_mission(), run_id="mismatched-evidence")
    payload = run.to_dict()
    payload["scenario_input_receipts"][0]["scenario_digest"] = "f" * 64
    with pytest.raises(
        InvalidScientificProblem, match="bound to a different scenario"
    ):
        MultiphysicsRunRecord.from_dict(payload)


# =====================================================================
# DOMAIN PACK AUTHORITY
# =====================================================================

def test_battery_pack_authority_is_singular_and_excludes_the_thevenin_kernel():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("engcore.domains.battery.pack")

    report = validate_domain_pack(BUILTIN_BATTERY_CELL_PACK)
    assert report.valid, report.errors

    declared = {item.artifact_id for item in BATTERY_MANIFEST.models}
    assert not any("thevenin" in item for item in declared)
    assert {item.artifact_id for item in BATTERY_MANIFEST.calibration_protocols} == {
        "battery.calibration.ocv_chord",
        "battery.calibration.ocv_curve",
    }
    assert {item.artifact_id for item in BATTERY_MANIFEST.validation_protocols} == {
        "battery.validation.ocv_empirical_adequacy",
    }


# =====================================================================
# TOPOLOGY BINDINGS
# =====================================================================

def _topology(**overrides):
    from engcore.scientific.twins import ScientificTwin, TwinDatum, TwinDatumRole, TwinKind
    from engcore.systems import (
        ComponentConnection, ComponentDefinition, ComponentInstance,
        ParameterBinding, StateBinding, SystemDefinition,
    )

    twin = ScientificTwin(
        "vehicle-twin", "1", TwinKind.CONCEPT,
        declarations=(
            TwinDatum("mass", Quantity(2.5, "kg"), TwinDatumRole.PARAMETER),
            TwinDatum("altitude", Quantity(0.0, "m"), TwinDatumRole.STATE),
        ),
    )
    monitor_twin = ScientificTwin("monitor-twin", "1", TwinKind.CONCEPT)
    twins = {twin.reference.key: twin, monitor_twin.reference.key: monitor_twin}
    kwargs = dict(
        definitions=(
            ComponentDefinition("vehicle", "1", VEHICLE.ports),
            ComponentDefinition("monitor", "1", MONITOR.ports),
        ),
        instances=(
            ComponentInstance("vehicle", "vehicle", "1", twin.reference, participant_id="vehicle"),
            ComponentInstance("monitor", "monitor", "1", monitor_twin.reference, participant_id="monitor"),
        ),
        connections=(
            ComponentConnection(
                "vehicle-altitude", "vehicle-altitude",
                "vehicle", "altitude", "monitor", "altitude",
            ),
        ),
        parameter_bindings=(ParameterBinding("mass-binding", "vehicle", "mass", "mass"),),
        state_bindings=(StateBinding("altitude-binding", "vehicle", "altitude", "altitude"),),
    )
    kwargs.update(overrides)
    return SystemDefinition("mission-system", "1", **kwargs), twins


def test_supported_parameter_and_state_bindings_are_no_longer_refused():
    topology, twins = _topology()

    assert topology.unsupported_execution_bindings == ()
    assert topology.parameter_values(twins) == {
        "vehicle": {"mass": Quantity(2.5, "kg")}
    }
    assert topology.state_variable_owners() == {"altitude": "vehicle"}


def test_two_authorities_for_one_participant_parameter_are_refused():
    from engcore.systems import ParameterBinding

    topology, twins = _topology(
        parameter_bindings=(
            ParameterBinding("mass-binding", "vehicle", "mass", "mass"),
            ParameterBinding("mass-again", "vehicle", "mass", "mass"),
        ),
    )
    with pytest.raises(InvalidScientificProblem, match="more than one authority"):
        topology.parameter_values(twins)


def test_a_state_binding_that_disagrees_with_the_scenario_owner_is_refused():
    from engcore.systems import StateBinding

    topology, _ = _topology(
        state_bindings=(StateBinding("altitude-binding", "monitor", "altitude", "altitude"),),
    )
    with pytest.raises(ValueError, match="owned by"):
        replace(_graph_plan(_mission()), system_definition=topology)


def test_a_participant_that_declares_no_such_parameter_refuses_the_binding():
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime.from_factory_registry(
        _graph(), _plan(), _registry(),
        resolver=BulkDataResolver(store), store=store,
    )
    with pytest.raises(InvalidScientificProblem, match="does not accept parameter bindings"):
        runtime.run(
            "unbound-parameter",
            external_inputs={PortRef("vehicle", "thrust_command"): Quantity(900, "W")},
            operating_conditions=_mission().composed_operating_conditions(),
            scenario_digest=_mission().digest,
            parameter_bindings={
                "vehicle": {"wingspan": ParameterValue("wingspan", Quantity(1.2, "m"))}
            },
        )
