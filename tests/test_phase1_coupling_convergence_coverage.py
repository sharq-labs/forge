"""Phase 1 BR1 -- true coupling convergence.

* An EXPLICIT plan without criteria is valid again (commit 35d8f557 attached the
  implicit "requires criteria" check to the IQN-ILS test, refusing every
  explicit plan).
* An IMPLICIT plan must monitor every interface the iteration updates with a
  lagged or relaxed iterate (``CouplingPlan.required_convergence_edges``);
  incomplete coverage is refused before execution.
* An overflowing residual is a numerical window failure, never an
  ITERATION_LIMIT the plan may accept.
* Field residuals are taken only between iterates on one support.

NOT RUN (Phase 1 build phase): see docs/work/DEFERRED_VALIDATION.md, DV-31.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, CouplingWindowNotConverged, InitializationResult, MultiphysicsRuntime,
    NonFiniteCouplingResidual, ResidualCalculator,
)
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, RelaxationKind,
    RelaxationPolicy, TimePolicy, WindowOutcome,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _q(seconds):
    return Quantity(seconds, "s")


def _time(end=1.0, window=0.5):
    return TimePolicy(_q(0), _q(end), _q(window))


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _criterion(edge_id):
    return ConvergenceCriterion(edge_id, 0.0, Quantity(1e-9, "K"))


class _Restorable:
    """A deterministic participant whose output is ``fn(inputs, calls)``; restore undoes nothing but the counter digest."""

    def __init__(self, spec, fn):
        self.spec, self.fn = spec, fn
        self.state = {"steps": 0}

    def _digest(self):
        return hashlib.sha256(repr(sorted(self.state.items())).encode()).hexdigest()

    def participant(self):
        outs = [p.port_id for p in self.spec.outputs]

        def initialize(_t, _i, _u):
            return InitializationResult({o: Quantity(300.0, "K") for o in outs}, {o: UNKNOWN for o in outs})

        def advance(request):
            self.state = {"steps": self.state["steps"] + 1}
            values = self.fn(dict(request.inputs), self.state["steps"])
            return AdvanceResult(request.end, values, {o: UNKNOWN for o in values}, 1, True)

        def checkpoint(instant):
            return RuntimeCheckpoint(CheckpointRecord(self.spec.participant_id, instant, self._digest(), True), dict(self.state))

        def restore(cp):
            self.state = dict(cp.token)

        return CallbackParticipant(self.spec, initialize=initialize, advance=advance, checkpoint=checkpoint, restore=restore)


def _two_way_graph():
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    edges = (CouplingEdge("e_ab", PortRef("a", "x"), PortRef("b", "x")),
             CouplingEdge("e_ba", PortRef("b", "y"), PortRef("a", "y")))
    return PhysicsGraph("two-way", (a, b), edges), a, b


def _implicit(semantics, criteria, relaxation=RelaxationPolicy(), max_iterations=50, fail=True, order=("a", "b")):
    return CouplingPlan("p", CouplingScheme.IMPLICIT, semantics, _time(), order, tuple(criteria), relaxation,
                        max_iterations, fail)


# ---- explicit plans are valid again ---------------------------------------------------------


def test_an_explicit_plan_without_criteria_is_valid():
    plan = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, _time())
    assert plan.criteria == ()
    assert CouplingPlan.from_dict(plan.to_dict()) == plan


def test_an_explicit_jacobi_plan_without_criteria_is_valid():
    CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.JACOBI, _time())


def test_explicit_plans_still_refuse_criteria_iterations_and_relaxation():
    with pytest.raises(InvalidScientificProblem, match="no coupling-convergence criteria"):
        CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, _time(), criteria=(_criterion("e"),))
    with pytest.raises(InvalidScientificProblem, match="one coupling iteration"):
        CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, _time(), max_iterations=2)
    with pytest.raises(InvalidScientificProblem, match="does not relax"):
        CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, _time(),
                     relaxation=RelaxationPolicy(RelaxationKind.CONSTANT, 0.5))


def test_an_implicit_plan_without_criteria_is_still_refused():
    with pytest.raises(InvalidScientificProblem, match="requires convergence criteria"):
        CouplingPlan("p", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL, _time(), max_iterations=5)


def test_iqn_ils_with_serial_semantics_is_still_refused():
    # Phase 3 BR14 names the kind by its value (`iqn_ils`) in the refusal; the
    # refusal and its reason (serial Gauss-Seidel) are what this test pins.
    with pytest.raises(InvalidScientificProblem, match=r"(?i)iqn[-_]ils.*serial"):
        CouplingPlan("p", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL, _time(), criteria=(_criterion("e"),),
                     relaxation=RelaxationPolicy(RelaxationKind.IQN_ILS, iqn_columns=3), max_iterations=5)


# ---- the required-coverage policy -----------------------------------------------------------


def test_an_explicit_plan_requires_no_monitored_edge():
    graph, _, _ = _two_way_graph()
    plan = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, _time(), ("a", "b"))
    assert plan.required_convergence_edges(graph) == ()


def test_jacobi_requires_every_edge():
    graph, _, _ = _two_way_graph()
    plan = _implicit(IterationSemantics.JACOBI, [_criterion("e_ab"), _criterion("e_ba")])
    assert plan.required_convergence_edges(graph) == ("e_ab", "e_ba")


def test_serial_without_relaxation_requires_exactly_the_lagged_edges():
    graph, _, _ = _two_way_graph()
    # order a, b: e_ab is forward (b reads this iteration's transfer), e_ba is lagged
    plan = _implicit(IterationSemantics.SERIAL, [_criterion("e_ba")], order=("a", "b"))
    assert plan.required_convergence_edges(graph) == ("e_ba",)
    reversed_plan = _implicit(IterationSemantics.SERIAL, [_criterion("e_ab")], order=("b", "a"))
    assert reversed_plan.required_convergence_edges(graph) == ("e_ab",)


def test_serial_with_relaxation_requires_every_edge():
    graph, _, _ = _two_way_graph()
    plan = _implicit(IterationSemantics.SERIAL, [_criterion("e_ab"), _criterion("e_ba")],
                     relaxation=RelaxationPolicy(RelaxationKind.CONSTANT, 0.5))
    assert plan.required_convergence_edges(graph) == ("e_ab", "e_ba")


def test_a_self_loop_is_a_lagged_edge():
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    graph = PhysicsGraph("loop", (a,), (CouplingEdge("e_aa", PortRef("a", "x"), PortRef("a", "y")),))
    plan = _implicit(IterationSemantics.SERIAL, [_criterion("e_aa")], order=("a",))
    assert plan.required_convergence_edges(graph) == ("e_aa",)


@pytest.mark.parametrize("semantics, criteria, relaxation, missing", [
    (IterationSemantics.JACOBI, ["e_ab"], RelaxationPolicy(), "e_ba"),
    (IterationSemantics.SERIAL, ["e_ab"], RelaxationPolicy(), "e_ba"),
    (IterationSemantics.SERIAL, ["e_ba"], RelaxationPolicy(RelaxationKind.CONSTANT, 0.5), "e_ab"),
])
def test_incomplete_required_coverage_is_refused_before_execution(semantics, criteria, relaxation, missing):
    graph, a, b = _two_way_graph()
    plan = _implicit(semantics, [_criterion(e) for e in criteria], relaxation=relaxation)
    with pytest.raises(InvalidScientificProblem, match=missing):
        plan.validate_against(graph)
    store = InMemoryBulkStore()
    participants = {"a": _Restorable(a, lambda i, n: {"x": Quantity(300, "K")}).participant(),
                    "b": _Restorable(b, lambda i, n: {"y": Quantity(300, "K")}).participant()}
    with pytest.raises(InvalidScientificProblem, match=missing):
        MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store)


def test_complete_coverage_reaches_a_converged_window_monitoring_every_required_edge():
    graph, a, b = _two_way_graph()
    plan = _implicit(IterationSemantics.JACOBI, [_criterion("e_ab"), _criterion("e_ba")], max_iterations=200)

    def fa(inputs, _n):
        return {"x": Quantity(0.5 * inputs["y"].magnitude_in("K") + 100.0, "K")}

    def fb(inputs, _n):
        return {"y": Quantity(0.5 * inputs["x"].magnitude_in("K") + 50.0, "K")}

    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"a": _Restorable(a, fa).participant(), "b": _Restorable(b, fb).participant()},
                                  resolver=BulkDataResolver(store), store=store)
    run = runtime.run("cov", external_inputs={})
    for window in run.windows:
        assert window.outcome is WindowOutcome.CONVERGED
        assert {r.edge_id for r in window.iterations[-1].residuals} >= set(plan.required_convergence_edges(graph))


# ---- non-finite iterates fail the window ---------------------------------------------------


def test_an_overflowing_scalar_residual_is_refused():
    calculator = ResidualCalculator(BulkDataResolver(InMemoryBulkStore()), {})
    with pytest.raises(NonFiniteCouplingResidual):
        calculator.compare(_criterion("e"), Quantity(1e308, "K"), Quantity(-1e308, "K"), unit="K")


def test_an_overflowing_iterate_fails_the_window_even_when_nonconvergence_is_allowed():
    graph, a, b = _two_way_graph()
    plan = _implicit(IterationSemantics.JACOBI, [_criterion("e_ab"), _criterion("e_ba")], max_iterations=5, fail=False)
    store = InMemoryBulkStore()
    flip = {"a": _Restorable(a, lambda i, n: {"x": Quantity((-1.0) ** n * 1e308, "K")}).participant(),
            "b": _Restorable(b, lambda i, n: {"y": Quantity(300.0, "K")}).participant()}
    runtime = MultiphysicsRuntime(graph, plan, flip, resolver=BulkDataResolver(store), store=store)
    with pytest.raises(CouplingWindowNotConverged, match="not finite|overflow"):
        runtime.run("overflow", external_inputs={})


# ---- field-valued interfaces ---------------------------------------------------------------


def _field(store, mesh, field_id="T"):
    definition = FieldDefinition(field_id, "K", mesh.mesh_id, FieldLocation.NODE)
    record, _ = FieldValue(definition, mesh, np.full(mesh.node_shape, 300.0)).store(store)
    return record


def test_a_field_residual_between_two_supports_is_refused():
    store = InMemoryBulkStore()
    left = StructuredMesh("left", Quantity(1, "m"), Quantity(1, "m"), 3, 3)
    right = StructuredMesh("right", Quantity(2, "m"), Quantity(2, "m"), 3, 3)  # same shape, another support
    calculator = ResidualCalculator(BulkDataResolver(store), {"left": left, "right": right})
    criterion = ConvergenceCriterion("e_field", 0.0, Quantity(1e-9, "K"))
    with pytest.raises(InvalidScientificProblem, match="changed support"):
        calculator.compare(criterion, _field(store, left), _field(store, right), unit="K")


def test_a_field_residual_on_one_support_is_measured():
    store = InMemoryBulkStore()
    mesh = StructuredMesh("m", Quantity(1, "m"), Quantity(1, "m"), 3, 3)
    calculator = ResidualCalculator(BulkDataResolver(store), {"m": mesh})
    criterion = ConvergenceCriterion("e_field", 0.0, Quantity(1e-9, "K"))
    residual = calculator.compare(criterion, _field(store, mesh), _field(store, mesh, "T2"), unit="K")
    assert residual.satisfied and residual.absolute.magnitude == 0.0
