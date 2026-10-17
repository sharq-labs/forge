"""An event-aligned window keeps its own failure outcome (Engineering Runtime V1, Big Rock 12).

Defect (found by static review, build phase): ``_window`` re-ran an implicit
window up to a terminal event and ALWAYS labelled the result EVENT_ALIGNED,
discarding the re-run's own outcome.  With ``fail_on_nonconvergence=False`` a
re-run that ended at its iteration limit was recorded as EVENT_ALIGNED -- a
non-converged window reported as a completed one.  Now only a completed re-run
is EVENT_ALIGNED.  NOT YET EXECUTED (build phase): see
docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.numerical_error import ErrorSourceStatus, assess_coupling_numerical_error
from engcore.execution.multiphysics.participant import ParticipantEvent, RuntimeCheckpoint
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy, WindowOutcome,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")
DIGEST = "0" * 64


def _spec(pid, ports, *, event_capable=False):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True, event_capable=event_capable)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _participant(spec, fn, *, trips_at=None):
    out = spec.outputs[0].port_id

    def advance(request):
        start, end = request.start.magnitude_in("s"), request.end.magnitude_in("s")
        events = ()
        if trips_at is not None and start < trips_at < end:
            events = (ParticipantEvent("trip", Quantity(trips_at, "s")),)
            end_q = Quantity(trips_at, "s")
        else:
            end_q = request.end
        return AdvanceResult(end_q, {out: fn(dict(request.inputs))}, {out: UNKNOWN}, 1, True, events=events)

    return CallbackParticipant(
        spec, initialize=lambda *_: InitializationResult({out: Quantity(0, "K")}, {out: UNKNOWN}), advance=advance,
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, DIGEST, True), None),
        restore=lambda cp: None)


def _run(gain):
    """x = gain * y + 5, y = x; participant b trips a terminal event at t = 0.5 s inside the 1 s window."""
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")], event_capable=True)
    graph = PhysicsGraph("ev-aligned", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                                CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("ev-aligned", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s"), align_events=True), ("a", "b"),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-6, "K")), ConvergenceCriterion("e_y", 0.0, Quantity(1e-6, "K"))),
                        max_iterations=3 if gain > 1 else 200, fail_on_nonconvergence=False)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(
        graph, plan,
        {"a": _participant(a, lambda i: Quantity(gain * i["y"].magnitude_in("K") + 5, "K")),
         "b": _participant(b, lambda i: Quantity(i["x"].magnitude_in("K"), "K"), trips_at=0.5)},
        resolver=BulkDataResolver(store), store=store)
    return runtime.run("ev", external_inputs={}, initial_coupling_values={"e_x": Quantity(0, "K"), "e_y": Quantity(0, "K")},
                       initial_coupling_uncertainty={"e_x": UNKNOWN, "e_y": UNKNOWN})


def test_a_non_converged_aligned_window_keeps_its_iteration_limit_outcome():
    run = _run(gain=2.0)  # x = 2y + 5 never converges in 3 iterations
    first = run.windows[0]
    assert first.end.magnitude_in("s") == 0.5 and first.event is not None
    assert first.outcome is WindowOutcome.ITERATION_LIMIT  # was relabelled EVENT_ALIGNED before the fix


def test_the_numerical_error_accounting_sees_the_unconverged_aligned_window_itself():
    # the second window also fails, so the run verdict alone would not show the fix: assert on window 0
    sources = {s.source: s for s in assess_coupling_numerical_error(_run(gain=2.0)).sources}
    assert sources["window:0:iteration"].status is ErrorSourceStatus.UNBOUNDED


def test_a_converged_aligned_window_is_still_event_aligned():
    run = _run(gain=0.5)  # x = y/2 + 5 converges
    first = run.windows[0]
    assert first.outcome is WindowOutcome.EVENT_ALIGNED and first.end.magnitude_in("s") == 0.5
