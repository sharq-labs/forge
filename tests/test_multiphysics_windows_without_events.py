"""Regression: a coupled run with no scheduled event and no condition change.

Phase 1 BR4 (``b71eeb3e``) wrote the next forced window boundary as
``min(end_exact, *pending_events, *pending_changes)``. With nothing pending
that call receives one ``Fraction`` and tries to iterate it, so every run
without a future event or operating-condition change raised ``TypeError``
before its first window -- the ordinary case, not an edge case. These tests
pin the ordinary case directly rather than relying on suites that happen to
reach it.
"""

from __future__ import annotations

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.scientific.multiphysics import (
    CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph,
    PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True)


def _run(end_s: float, width_s: float):
    source = _spec("src", [PortDefinition("t", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")])
    sink = _spec("sink", [PortDefinition("t_in", PortDirection.INPUT, PortKind.SCALAR, "temperature", "K"),
                          PortDefinition("o", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")])
    graph = PhysicsGraph("no-events", (source, sink), (CouplingEdge("e", PortRef("src", "t"), PortRef("sink", "t_in")),))
    value = Quantity(300.0, "K")
    seen: list[Quantity] = []

    def advance(request):
        seen.append(request.inputs["t_in"])
        return AdvanceResult(request.end, {"o": Quantity(0.0, "K")}, {"o": UNKNOWN}, 1, True)

    participants = {
        "src": CallbackParticipant(
            graph.participant("src"),
            initialize=lambda *_: InitializationResult({"t": value}, {"t": UNKNOWN}),
            advance=lambda r: AdvanceResult(r.end, {"t": value}, {"t": UNKNOWN}, 1, True),
        ),
        "sink": CallbackParticipant(
            graph.participant("sink"),
            initialize=lambda *_: InitializationResult({"o": Quantity(0.0, "K")}, {"o": UNKNOWN}),
            advance=advance,
        ),
    }
    plan = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0.0, "s"), Quantity(end_s, "s"), Quantity(width_s, "s")))
    store = InMemoryBulkStore()
    record = MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store).run(
        "r", external_inputs={}, external_uncertainty={})
    return record, seen


def test_a_single_window_run_without_events_completes():
    record, seen = _run(1.0, 1.0)
    assert len(record.windows) == 1
    assert record.windows[0].end.to("s").magnitude == 1.0
    assert seen == [Quantity(300.0, "K")]


def test_a_multi_window_run_without_events_tiles_the_horizon_exactly():
    record, seen = _run(3.0, 1.0)
    assert [w.end.to("s").magnitude for w in record.windows] == [1.0, 2.0, 3.0]
    assert [w.start.to("s").magnitude for w in record.windows] == [0.0, 1.0, 2.0]
    assert len(seen) == 3
