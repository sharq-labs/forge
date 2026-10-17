"""Coupling numerical-error accounting (Engineering Runtime V1, Big Rock 3).

Derived from a run record without changing it: what the run QUANTIFIED,
ESTIMATED, left UNQUANTIFIED, or knows to be UNBOUNDED.  Estimates are never
added to the bound and nothing open is read as zero.  NOT YET EXECUTED (build
phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.numerical_error import (
    ErrorAccountingVerdict, ErrorSourceStatus, NumericalErrorSource, assess_coupling_numerical_error,
)
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, RelaxationKind, RelaxationPolicy,
    TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")
DIGEST = "0" * 64


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _participant(spec, fn):
    out = spec.outputs[0].port_id
    return CallbackParticipant(
        spec, initialize=lambda *_: InitializationResult({out: Quantity(0, "K")}, {out: UNKNOWN}),
        advance=lambda r: AdvanceResult(r.end, {out: fn(dict(r.inputs))}, {out: UNKNOWN}, 1, True),
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, DIGEST, True), None),
        restore=lambda cp: None)


def _loop(plan_kwargs, *, gain=0.5, offset=5.0):
    """x = gain * y + offset, y = x."""
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    pa = _participant(a, lambda i: Quantity(gain * i["y"].magnitude_in("K") + offset, "K"))
    pb = _participant(b, lambda i: Quantity(i["x"].magnitude_in("K"), "K"))
    graph = PhysicsGraph("acc", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                         CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("acc", time=TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")),
                        participant_order=("a", "b"), **plan_kwargs)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"a": pa, "b": pb}, resolver=BulkDataResolver(store), store=store)
    return runtime.run("acc", external_inputs={}, initial_coupling_values={"e_x": Quantity(0, "K"), "e_y": Quantity(0, "K")},
                       initial_coupling_uncertainty={"e_x": UNKNOWN, "e_y": UNKNOWN})


def _implicit(relaxation=RelaxationPolicy(), *, max_iterations=200, fail=True, gain=0.5):
    return _loop(dict(scheme=CouplingScheme.IMPLICIT, iteration_semantics=IterationSemantics.SERIAL,
                      criteria=(ConvergenceCriterion("e_x", 0.0, Quantity(1e-6, "K")),
                                ConvergenceCriterion("e_y", 0.0, Quantity(1e-6, "K"))),
                      relaxation=relaxation, max_iterations=max_iterations, fail_on_nonconvergence=fail), gain=gain)


# ---- records -----------------------------------------------------------------------------


@pytest.mark.parametrize("status", [ErrorSourceStatus.UNQUANTIFIED, ErrorSourceStatus.UNBOUNDED])
def test_an_open_source_never_carries_a_value(status):
    with pytest.raises(InvalidScientificProblem, match="never zero"):
        NumericalErrorSource("s", "iteration", status, 0.0, "m")


@pytest.mark.parametrize("status", [ErrorSourceStatus.QUANTIFIED, ErrorSourceStatus.ESTIMATED])
@pytest.mark.parametrize("value", [None, -1.0, float("nan")])
def test_a_quantified_or_estimated_source_carries_a_finite_value(status, value):
    with pytest.raises(InvalidScientificProblem):
        NumericalErrorSource("s", "iteration", status, value, "m")


# ---- assessments -------------------------------------------------------------------------


def test_explicit_coupling_reports_an_unquantified_splitting_error_not_a_bound():
    run = _loop(dict(scheme=CouplingScheme.EXPLICIT, iteration_semantics=IterationSemantics.SERIAL))
    assessment = assess_coupling_numerical_error(run)
    assert assessment.verdict is ErrorAccountingVerdict.INCOMPLETE
    assert [s.kind for s in assessment.sources] == ["splitting"]
    assert assessment.quantified_relative_bound is None and assessment.estimated_relative is None


def test_plain_fixed_point_iteration_error_is_an_estimate_that_covers_the_true_error_of_a_linear_contraction():
    run = _implicit()
    assessment = assess_coupling_numerical_error(run)
    assert assessment.verdict is ErrorAccountingVerdict.ESTIMATED
    assert assessment.quantified_relative_bound is None  # an estimate is never promoted to a bound
    estimate = {s.source: s.relative for s in assessment.sources}["window:0:edge:e_x:iteration"]
    x = run.final_outputs["a.x"]["magnitude"]
    true_relative_error = abs(x - 10.0) / abs(x)
    assert estimate >= true_relative_error * (1.0 - 1e-9)


def test_an_accelerated_iteration_is_unquantified():
    run = _implicit(RelaxationPolicy(RelaxationKind.AITKEN, 0.5, 0.05, 1.0))
    assessment = assess_coupling_numerical_error(run)
    assert assessment.verdict is ErrorAccountingVerdict.INCOMPLETE
    assert all(s.method == "accelerated_iteration" for s in assessment.sources if s.kind == "iteration")


def test_a_window_at_its_iteration_limit_is_unbounded():
    run = _implicit(max_iterations=5, fail=False, gain=2.0)
    assessment = assess_coupling_numerical_error(run)
    assert assessment.verdict is ErrorAccountingVerdict.UNBOUNDED
    assert any(s.status is ErrorSourceStatus.UNBOUNDED and s.method == "window_iteration_limit" for s in assessment.sources)


def test_a_coupled_run_is_never_reported_as_having_no_coupling_and_the_assessment_binds_its_digest():
    run = _implicit()
    assessment = assess_coupling_numerical_error(run)
    assert assessment.coupled and assessment.verdict is not ErrorAccountingVerdict.NO_COUPLING
    from engcore.execution.multiphysics.numerical_error import run_digest
    assert assessment.run_digest == run_digest(run)


def test_an_assessment_cannot_claim_no_coupling_for_sources_or_skip_its_digest():
    from engcore.execution.multiphysics.numerical_error import CouplingNumericalErrorAssessment
    with pytest.raises(InvalidScientificProblem):
        CouplingNumericalErrorAssessment("r", "not-a-digest", True, ())
    with pytest.raises(InvalidScientificProblem):
        CouplingNumericalErrorAssessment(
            "r", "a" * 64, False, (NumericalErrorSource("s", "splitting", ErrorSourceStatus.UNQUANTIFIED, None, "m"),))
    # a coupled run with no assessed source is INCOMPLETE, never NO_COUPLING
    assert CouplingNumericalErrorAssessment("r", "a" * 64, True, ()).verdict is ErrorAccountingVerdict.INCOMPLETE


def test_a_run_without_coupling_edges_has_no_coupling_error_source():
    a = _spec("a", [_port("x", "output")])
    graph = PhysicsGraph("solo", (a,), ())
    plan = CouplingPlan("solo", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    run = MultiphysicsRuntime(graph, plan, {"a": _participant(a, lambda _i: Quantity(1, "K"))},
                              resolver=BulkDataResolver(store), store=store).run("solo", external_inputs={})
    assert assess_coupling_numerical_error(run).verdict is ErrorAccountingVerdict.NO_COUPLING


def test_assessment_leaves_the_run_record_unchanged():
    run = _implicit()
    before = run.to_dict()
    assess_coupling_numerical_error(run)
    assert run.to_dict() == before
    assert "_numerical_error" not in run.final_outputs


def test_assessment_refuses_anything_but_a_run_record():
    with pytest.raises(InvalidScientificProblem):
        assess_coupling_numerical_error({"final_outputs": {}})
