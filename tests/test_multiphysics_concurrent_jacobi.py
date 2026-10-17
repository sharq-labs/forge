"""Opt-in concurrent advance inside a Jacobi coupling iteration (Engineering Runtime V1, Big Rock 5).

Declared participants advance concurrently; undeclared ones advance alone and
first; results apply in plan order so the run equals sequential Jacobi; a
failure is the first in plan order.  NOT YET EXECUTED (build phase): see
docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import threading
import time

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, CouplingWindowNotConverged, InitializationResult, MultiphysicsRuntime,
)
from engcore.execution.multiphysics.concurrency import ConcurrentAdvancePolicy, advance_in_plan_order
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition,
    PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _policy(participants=("a", "b"), workers=2, basis="independent in-process closures with no shared state (test)"):
    return ConcurrentAdvancePolicy(tuple(participants), workers, basis)


# ---- the policy record ---------------------------------------------------------------------


@pytest.mark.parametrize("kwargs", [dict(participants=("a",)), dict(participants=("a", "a")), dict(participants=("a", "")),
                                    dict(workers=1), dict(workers=65), dict(workers=True), dict(basis="  ")])
def test_policy_rejects_incomplete_declarations(kwargs):
    with pytest.raises(InvalidScientificProblem):
        _policy(**kwargs)


# ---- the scheduling helper -----------------------------------------------------------------


def test_fewer_than_two_declared_participants_run_sequentially_in_order():
    seen = []
    out = advance_in_plan_order(("b", "a", "c"), frozenset({"a"}), 4, lambda pid: seen.append(pid) or pid.upper())
    assert seen == ["b", "a", "c"]
    assert list(out) == ["b", "a", "c"] and out["a"] == "A"


def test_declared_participants_really_run_at_the_same_time():
    barrier = threading.Barrier(2, timeout=10)

    def advance(pid):
        barrier.wait()  # times out (BrokenBarrierError) if the two never overlap
        return pid

    out = advance_in_plan_order(("a", "b"), frozenset({"a", "b"}), 2, advance)
    assert list(out) == ["a", "b"]


def test_undeclared_participants_run_alone_before_declared_ones():
    events = []
    lock = threading.Lock()

    def advance(pid):
        with lock:
            events.append(("start", pid))
        time.sleep(0.05)
        with lock:
            events.append(("end", pid))
        return pid

    out = advance_in_plan_order(("a", "solo", "b"), frozenset({"a", "b"}), 2, advance)
    assert events[:2] == [("start", "solo"), ("end", "solo")]
    assert list(out) == ["a", "solo", "b"]  # results keyed in plan order


def test_the_failure_raised_is_the_first_in_plan_order_not_the_first_to_finish():
    def advance(pid):
        if pid == "a":
            time.sleep(0.2)
            raise CouplingWindowNotConverged("a failed (later)")
        raise CouplingWindowNotConverged("b failed (first)")

    with pytest.raises(CouplingWindowNotConverged, match="a failed"):
        advance_in_plan_order(("a", "b"), frozenset({"a", "b"}), 2, advance)


# ---- runtime -------------------------------------------------------------------------------


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _runtime(*, concurrency=None, semantics=IterationSemantics.JACOBI, barrier=None):
    """Explicit Jacobi coupling a <-> b with integrating state: x += y * dt, y = x / 2 + 1."""
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    state = {"x": 1.0}

    def advance_a(request):
        if barrier is not None:
            barrier.wait()
        dt = request.end.magnitude_in("s") - request.start.magnitude_in("s")
        state["x"] += request.inputs["y"].magnitude_in("K") * dt
        return AdvanceResult(request.end, {"x": Quantity(state["x"], "K")}, {"x": UNKNOWN}, 1, True)

    def advance_b(request):
        if barrier is not None:
            barrier.wait()
        return AdvanceResult(request.end, {"y": Quantity(request.inputs["x"].magnitude_in("K") / 2 + 1, "K")},
                             {"y": UNKNOWN}, 1, True)

    pa = CallbackParticipant(a, initialize=lambda *_: InitializationResult({"x": Quantity(1, "K")}, {"x": UNKNOWN}),
                             advance=advance_a)
    pb = CallbackParticipant(b, initialize=lambda *_: InitializationResult({"y": Quantity(1, "K")}, {"y": UNKNOWN}),
                             advance=advance_b)
    graph = PhysicsGraph("conc", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                          CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("conc", CouplingScheme.EXPLICIT, semantics,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(0.25, "s")),
                        participant_order=("a", "b"))
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store,
                               concurrency=concurrency)


def _run(runtime):
    return runtime.run("conc", external_inputs={},
                       initial_coupling_values={"e_x": Quantity(1, "K"), "e_y": Quantity(1, "K")},
                       initial_coupling_uncertainty={"e_x": UNKNOWN, "e_y": UNKNOWN})


def test_concurrent_jacobi_run_equals_the_sequential_run():
    sequential = _run(_runtime()).to_dict()
    concurrent = _run(_runtime(concurrency=_policy())).to_dict()
    recorded = concurrent["final_outputs"].pop("_concurrency")
    assert recorded["participants"] == ["a", "b"] and recorded["basis"]
    assert concurrent == sequential


def test_the_runtime_really_advances_declared_participants_concurrently():
    _run(_runtime(concurrency=_policy(), barrier=threading.Barrier(2, timeout=10)))


def test_a_sequential_run_records_no_concurrency():
    assert "_concurrency" not in _run(_runtime()).final_outputs


def test_concurrency_with_serial_gauss_seidel_coupling_is_refused():
    with pytest.raises(InvalidScientificProblem, match="Jacobi"):
        _runtime(concurrency=_policy(), semantics=IterationSemantics.SERIAL)


def test_concurrency_naming_an_unknown_participant_is_refused():
    with pytest.raises(InvalidScientificProblem, match="outside the graph"):
        _runtime(concurrency=_policy(participants=("a", "ghost")))
