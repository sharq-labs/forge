"""Opt-in explicit-coupling splitting-error estimate (Engineering Runtime V1, Big Rock 4).

Exact model problem: b outputs y(t) = t (per window end); a integrates
x += y * dt with the transferred y.  x(T) is then a Riemann sum whose splitting
error is exactly T * dt / 2 (first order): for T = 1 s and dt = 0.25, 0.125,
0.0625 s, x = 0.625, 0.5625, 0.53125 (exact in binary), the observed order is 1
and the Richardson estimate equals the true error 0.125.  NOT YET EXECUTED
(build phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.execution.multiphysics.numerical_error import (
    ErrorAccountingVerdict, ErrorSourceStatus, assess_coupling_numerical_error,
)
from engcore.execution.multiphysics.splitting import estimate_splitting_error
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics, ParticipantSpec,
    PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _spec(pid, ports, model="m", checkpointable=False):
    return ParticipantSpec(pid, model, "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=checkpointable, deterministic_restore=checkpointable)


def _checkpointing(spec):
    """Checkpoint callbacks for the implicit variant (admitted, then refused by the estimator itself)."""
    if not spec.checkpointable:
        return {}
    return dict(checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, "0" * 64, True), None),
                restore=lambda cp: None)


def _build(*, scheme=CouplingScheme.EXPLICIT, wrong_window=None, model_at=None, bias=None):
    """A factory for fresh runtimes of the same problem at a given coupling window."""

    def build(window: Quantity) -> MultiphysicsRuntime:
        dt = window.magnitude_in("s")
        a_model = (model_at or {}).get(dt, "m")
        implicit = scheme is CouplingScheme.IMPLICIT
        y_out = PortDefinition("y", PortDirection.OUTPUT, PortKind.SCALAR, "rate", "K/s")
        b = _spec("b", [y_out], checkpointable=implicit)
        a = _spec("a", [PortDefinition("y", PortDirection.INPUT, PortKind.SCALAR, "rate", "K/s"),
                        PortDefinition("x", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K"),
                        PortDefinition("z", PortDirection.OUTPUT, PortKind.SCALAR, "temperature", "K")], model=a_model,
                  checkpointable=implicit)
        state = {"x": 0.0}

        def advance_a(request):
            width = request.end.magnitude_in("s") - request.start.magnitude_in("s")
            state["x"] += request.inputs["y"].magnitude_in("K/s") * width
            z = 300.0 + (bias or {}).get(dt, 0.0)
            return AdvanceResult(request.end, {"x": Quantity(state["x"], "K"), "z": Quantity(z, "K")},
                                 {"x": UNKNOWN, "z": UNKNOWN}, 1, True)

        pa = CallbackParticipant(
            a, initialize=lambda *_: InitializationResult({"x": Quantity(0, "K"), "z": Quantity(300, "K")},
                                                          {"x": UNKNOWN, "z": UNKNOWN}),
            advance=advance_a, **_checkpointing(a))
        pb = CallbackParticipant(
            b, initialize=lambda *_: InitializationResult({"y": Quantity(0, "K/s")}, {"y": UNKNOWN}),
            advance=lambda r: AdvanceResult(r.end, {"y": Quantity(r.end.magnitude_in("s"), "K/s")}, {"y": UNKNOWN}, 1, True),
            **_checkpointing(b))
        graph = PhysicsGraph("split", (a, b), (CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y")),))
        built_window = Quantity(wrong_window, "s") if wrong_window is not None else window
        if scheme is CouplingScheme.EXPLICIT:
            plan = CouplingPlan("split", scheme, IterationSemantics.SERIAL,
                                TimePolicy(Quantity(0, "s"), Quantity(1, "s"), built_window))
        else:
            plan = CouplingPlan("split", scheme, IterationSemantics.SERIAL,
                                TimePolicy(Quantity(0, "s"), Quantity(1, "s"), built_window),
                                criteria=(ConvergenceCriterion("e_y", 0.0, Quantity(1e-9, "K/s")),), max_iterations=5)
        store = InMemoryBulkStore()
        return MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store)

    return build


def _estimate(build=None, **kwargs):
    kwargs.setdefault("quantities", ("a.x",))
    return estimate_splitting_error(build or _build(), coupling_window=Quantity(0.25, "s"), run_id="split",
                                    run_kwargs={"external_inputs": {}}, **kwargs)


def test_three_levels_observe_first_order_and_recover_the_exact_splitting_error():
    run, estimate = _estimate()
    item = estimate.quantities[0]
    assert item.values == pytest.approx((0.625, 0.5625, 0.53125))
    assert item.observed_order == pytest.approx(1.0)
    true_error = abs(run.final_outputs["a.x"]["magnitude"] - 0.5)
    assert item.relative * 0.625 == pytest.approx(true_error)  # 0.125 K
    assert estimate.windows_s == pytest.approx((0.25, 0.125, 0.0625))
    assert run.run_id == "split"


def test_assessment_with_the_estimate_reports_splitting_as_estimated_not_unquantified():
    run, estimate = _estimate()
    without = assess_coupling_numerical_error(run)
    with_estimate = assess_coupling_numerical_error(run, splitting=estimate)
    assert without.verdict is ErrorAccountingVerdict.INCOMPLETE
    assert with_estimate.verdict is ErrorAccountingVerdict.ESTIMATED
    assert with_estimate.estimated_relative == pytest.approx(0.2)
    assert with_estimate.quantified_relative_bound is None  # an estimate never becomes a bound


def test_estimate_is_bound_to_the_run_it_was_produced_with():
    _, estimate = _estimate()
    other, _ = _estimate()  # an identical problem re-run is a different record only if anything differs ...
    rerun = _build()(Quantity(0.25, "s")).run("another-run", external_inputs={})
    with pytest.raises(InvalidScientificProblem, match="another run"):
        assess_coupling_numerical_error(rerun, splitting=estimate)
    assess_coupling_numerical_error(other, splitting=estimate)  # ... a deterministic identical re-run is the same record


def test_two_levels_need_a_declared_order_with_a_basis():
    with pytest.raises(InvalidScientificProblem, match="declare it"):
        _estimate(levels=2)
    with pytest.raises(InvalidScientificProblem, match="declare it"):
        _estimate(levels=2, declared_order=1.0)
    _, estimate = _estimate(levels=2, declared_order=1.0, declared_order_basis="first-order staggering (test)")
    assert estimate.quantities[0].relative * 0.625 == pytest.approx(0.125)
    assert "declared order 1" in estimate.order_basis


def test_three_levels_refuse_a_declared_order():
    with pytest.raises(InvalidScientificProblem, match="observe the order"):
        _estimate(declared_order=1.0, declared_order_basis="x")


def test_a_refinement_that_changes_the_problem_is_refused():
    with pytest.raises(InvalidScientificProblem, match="changed the problem"):
        _estimate(_build(model_at={0.125: "another-model"}))


def test_a_build_that_ignores_the_requested_window_is_refused():
    with pytest.raises(InvalidScientificProblem, match="expected"):
        _estimate(_build(wrong_window=0.25))


def test_implicit_coupling_is_refused():
    with pytest.raises(InvalidScientificProblem, match="explicit coupling only"):
        _estimate(_build(scheme=CouplingScheme.IMPLICIT))


def test_non_asymptotic_refinement_leaves_the_quantity_unquantified():
    _, estimate = _estimate(_build(bias={0.25: 0.0, 0.125: 1.0, 0.0625: -1.0}), quantities=("a.x", "a.z"))
    by_name = {q.quantity: q for q in estimate.quantities}
    assert by_name["a.x"].estimated
    assert not by_name["a.z"].estimated and "asymptotic" in by_name["a.z"].detail
    run, estimate = _estimate(_build(bias={0.25: 0.0, 0.125: 1.0, 0.0625: -1.0}), quantities=("a.z",))
    statuses = {s.status for s in assess_coupling_numerical_error(run, splitting=estimate).sources}
    assert statuses == {ErrorSourceStatus.UNQUANTIFIED}


def test_an_unaffected_quantity_is_estimated_as_zero_not_skipped():
    _, estimate = _estimate(quantities=("a.z",))
    assert estimate.quantities[0].relative == 0.0


def test_unknown_or_duplicate_quantities_are_refused():
    with pytest.raises(InvalidScientificProblem, match="scalar output"):
        _estimate(quantities=("a.missing",))
    with pytest.raises(InvalidScientificProblem, match="unique"):
        _estimate(quantities=("a.x", "a.x"))
