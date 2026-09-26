"""Regression tests for the BIG 9 re-review blockers fixed before BIG 10.

B10-2  the implicit fixed-point residual is measured on the UNRELAXED transfer
B10-3  an event from a participant not declared event_capable is refused, and
       event alignment requires deterministic checkpoints of every participant
B10-4  a STEP input change inside an event-shifted window becomes a boundary
       instead of being delivered late

These are numerical/orchestration facts, not validation.
"""

from __future__ import annotations

import hashlib

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime,
)
from engcore.execution.multiphysics.participant import ParticipantEvent, RuntimeCheckpoint
from engcore.execution.multiphysics.runtime import MultiphysicsExecutionError
from engcore.scenarios import InterpolationKind, ScenarioEvent, TimeSample, TimeSeriesInput
from engcore.scenarios.contracts import ComposedInputSchedule, SegmentContribution
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef,
    RelaxationKind, RelaxationPolicy, TimePolicy,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics.state import CheckpointRecord
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")
DIGEST = hashlib.sha256(b"stateless").hexdigest()


def _port(pid, direction, quantity="temperature", unit="K"):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, quantity, unit)


def _spec(pid, ports, **flags):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True, **flags)


def _stateless(spec, fn, initial, events=None):
    def initialize(_t, _i, _u):
        return InitializationResult({spec.outputs[0].port_id: initial}, {spec.outputs[0].port_id: UNKNOWN})

    def advance(request):
        value = fn(dict(request.inputs))
        evs = events(request) if events else ()
        end = evs[0].instant if evs else request.end
        return AdvanceResult(end, {spec.outputs[0].port_id: value}, {spec.outputs[0].port_id: UNKNOWN}, 1, True, events=tuple(evs))

    kwargs = {}
    if spec.checkpointable:
        kwargs = dict(checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, DIGEST, True), None),
                      restore=lambda cp: None)
    return CallbackParticipant(spec, initialize=initialize, advance=advance, **kwargs)


# ---- B10-2 -------------------------------------------------------------------


def _fixed_point_runtime(factor, max_iterations):
    # x = y/2 + 5, y = x  ->  fixed point x = y = 10 K
    a = _spec("a", [_port("y", "input"), _port("x", "output")], checkpointable=True, deterministic_restore=True)
    b = _spec("b", [_port("x", "input"), _port("y", "output")], checkpointable=True, deterministic_restore=True)
    pa = _stateless(a, lambda i: Quantity(i["y"].magnitude_in("K") / 2 + 5, "K"), Quantity(0, "K"))
    pb = _stateless(b, lambda i: Quantity(i["x"].magnitude_in("K"), "K"), Quantity(0, "K"))
    graph = PhysicsGraph("fp", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                        CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    kind = RelaxationKind.NONE if factor == 1.0 else RelaxationKind.CONSTANT
    plan = CouplingPlan("fp", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("a", "b"),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1.0, "K")), ConvergenceCriterion("e_y", 0.0, Quantity(1.0, "K"))),
                        RelaxationPolicy(kind, factor), max_iterations, True)
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store)


def _run_fp(runtime):
    return runtime.run("fp", external_inputs={},
                       initial_coupling_values={"e_x": Quantity(0, "K"), "e_y": Quantity(0, "K")},
                       initial_coupling_uncertainty={"e_x": UNKNOWN, "e_y": UNKNOWN})


def test_small_relaxation_factor_does_not_shrink_the_convergence_residual():
    # Before the fix the recorded residual was omega * r = 0.05 * 5 K = 0.25 K < 1 K,
    # so iteration 1 was labelled CONVERGED at x = 0.25 K (fixed point: 10 K).
    with pytest.raises(MultiphysicsExecutionError, match="without convergence"):
        _run_fp(_fixed_point_runtime(0.05, 3))


def test_converged_window_satisfies_the_fixed_point_to_the_declared_tolerance():
    run = _run_fp(_fixed_point_runtime(0.05, 2000))
    window = run.windows[0]
    assert window.outcome.value == "converged"
    x = run.final_outputs["a.x"]["magnitude"]
    y = run.final_outputs["b.y"]["magnitude"]
    # the declared criterion (1 K) holds on the COUPLED equations, not on the increment
    assert abs((y / 2 + 5) - x) <= 1.0 + 1e-9 and abs(x - y) <= 2.0
    first = [r.absolute.magnitude for r in window.iterations[0].residuals if r.edge_id == "e_x"][0]
    assert first == pytest.approx(5.0)  # r_1 = H(x_0) - x_0 = 5 K, not 0.05 * 5 K


# ---- B10-3 -------------------------------------------------------------------


def _event_runtime(*, event_capable, checkpointable):
    s = _spec("trip", [_port("f", "input"), _port("x", "output")], event_capable=event_capable,
              checkpointable=checkpointable, deterministic_restore=checkpointable)
    calls = []

    def events(request):
        calls.append(request.start.magnitude_in("s"))
        if request.start.magnitude_in("s") == 0 and request.end.magnitude_in("s") > 0.4:
            return (ParticipantEvent("trip", Quantity(0.4, "s")),)
        return ()

    p = _stateless(s, lambda i: Quantity(1, "K"), Quantity(0, "K"), events=events)
    graph = PhysicsGraph("ev", (s,), ())
    plan = CouplingPlan("ev", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, {"trip": p}, resolver=BulkDataResolver(store), store=store), calls


def test_event_from_undeclared_participant_is_refused():
    runtime, _ = _event_runtime(event_capable=False, checkpointable=False)
    with pytest.raises(MultiphysicsExecutionError, match="not declared event_capable"):
        runtime.run("ev", external_inputs={PortRef("trip", "f"): Quantity(0, "K")},
                    external_uncertainty={PortRef("trip", "f"): UNKNOWN})


def test_event_alignment_without_checkpoints_is_refused():
    # Plan admission refuses this before execution; the runtime keeps its own
    # guard as defense in depth for participants built outside admission.
    with pytest.raises((InvalidScientificProblem, MultiphysicsExecutionError), match="deterministic checkpoint"):
        runtime, _ = _event_runtime(event_capable=True, checkpointable=False)
        runtime.run("ev", external_inputs={PortRef("trip", "f"): Quantity(0, "K")},
                    external_uncertainty={PortRef("trip", "f"): UNKNOWN})


def test_event_alignment_with_checkpoints_still_aligns():
    runtime, _ = _event_runtime(event_capable=True, checkpointable=True)
    run = runtime.run("ev", external_inputs={PortRef("trip", "f"): Quantity(0, "K")},
                      external_uncertainty={PortRef("trip", "f"): UNKNOWN})
    assert run.windows[0].outcome.value == "event_aligned"
    assert run.windows[0].end.magnitude_in("s") == pytest.approx(0.4)


# ---- B10-4 -------------------------------------------------------------------


def test_step_input_change_inside_an_event_shifted_window_is_a_boundary():
    s = _spec("body", [_port("f", "input"), _port("x", "output")])
    p = _stateless(s, lambda i: i["f"], Quantity(0, "K"))
    graph = PhysicsGraph("step", (s,), ())
    plan = CouplingPlan("step", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(30, "s"), Quantity(10, "s")))
    schedule = ComposedInputSchedule("f", TimeSeriesInput("f", (
        TimeSample(Quantity(0, "s"), Quantity(1, "K")), TimeSample(Quantity(10, "s"), Quantity(2, "K")),
        TimeSample(Quantity(30, "s"), Quantity(2, "K"))), InterpolationKind.STEP),
        (SegmentContribution("drive", Quantity(0, "s"), Quantity(30, "s")),))
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"body": p}, resolver=BulkDataResolver(store), store=store)
    ref = PortRef("body", "f")
    run = runtime.run("step", external_inputs={ref: Quantity(1, "K")}, external_uncertainty={ref: UNKNOWN},
                      external_input_schedules={ref: schedule}, scheduled_events=(ScenarioEvent("shift", Quantity(5, "s")),),
                      scenario_digest="d" * 64)
    starts = [w.start.magnitude_in("s") for w in run.windows]
    assert 10.0 in starts  # before the fix the grid was 0, 5, 15, 25 and the 10 s change arrived at 15 s
    receipt = next(r for r in run.scenario_input_receipts if r.instant.magnitude_in("s") == 10.0)
    assert receipt.value.magnitude_in("K") == 2
    assert all(r.value.magnitude_in("K") == (1 if r.instant.magnitude_in("s") < 10 else 2) for r in run.scenario_input_receipts)


def test_operating_condition_segment_start_is_a_window_boundary():
    from engcore.execution.multiphysics.participant import OperatingConditionDefinition
    from engcore.scenarios.contracts import ComposedOperatingCondition, OperatingCondition

    s = _spec("body", [_port("f", "input"), _port("x", "output")])
    applied = []

    def initialize(_t, _i, _u):
        return InitializationResult({"x": Quantity(0, "K")}, {"x": UNKNOWN})

    def advance(request):
        return AdvanceResult(request.end, {"x": Quantity(applied[-1], "K")}, {"x": UNKNOWN}, 1, True)

    def apply(instant, values):
        applied.append(values["load"].value.magnitude_in("K"))
        return tuple(sorted(values.values()))

    p = CallbackParticipant(s, initialize=initialize, advance=advance,
                            operating_condition_definitions=(OperatingConditionDefinition("load", "K"),), apply_operating_conditions=apply)
    graph = PhysicsGraph("oc", (s,), ())
    plan = CouplingPlan("oc", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(30, "s"), Quantity(10, "s")))
    load = ComposedOperatingCondition("load", (
        (SegmentContribution("a", Quantity(0, "s"), Quantity(15, "s")), OperatingCondition("load", Quantity(1, "K"), UNKNOWN)),
        (SegmentContribution("b", Quantity(15, "s"), Quantity(30, "s")), OperatingCondition("load", Quantity(2, "K"), UNKNOWN))))
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"body": p}, resolver=BulkDataResolver(store), store=store)
    ref = PortRef("body", "f")
    run = runtime.run("oc", external_inputs={ref: Quantity(0, "K")}, external_uncertainty={ref: UNKNOWN},
                      operating_conditions=(load,), scenario_digest="e" * 64)
    starts = [w.start.magnitude_in("s") for w in run.windows]
    assert 15.0 in starts  # before the fix the grid was 0, 10, 20 and segment b's load arrived at 20 s
    at15 = [r for r in run.operating_condition_receipts if r.instant.magnitude_in("s") == 15.0]
    assert at15 and at15[0].value.magnitude_in("K") == 2 and at15[0].segment_id == "b"
