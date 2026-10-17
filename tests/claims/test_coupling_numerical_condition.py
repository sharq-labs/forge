"""Coupling-numerical error conditions a claim's NUMERICAL channel; it never supplies, widens or is covered.

Engineering Runtime V1, Big Rock 6 (after the static review's F1-F6).  The
assessment is computed from the run record inside the condition; the study
record is re-derived through the canonical claims estimator; the study must be
about the coupled run.  NOT YET EXECUTED (build phase): see
docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import pytest

from engcore.claims.coupling_numerical import (
    CouplingConditionAction, CouplingConditionError, condition_numerical_uncertainty,
)
from engcore.claims.numerical_uq import RefinementLevel, estimate_numerical_uncertainty
from engcore.claims.uncertainty import transport
from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime
from engcore.execution.multiphysics.numerical_error import assess_coupling_numerical_error
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


# ---- runs ----------------------------------------------------------------------------------


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
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, "0" * 64, True), None),
        restore=lambda cp: None)


def _loop_run(run_id, **plan_kwargs):
    """x = 0.5 y + 5 (or 2 y + 5 when gain=2), y = x."""
    gain = plan_kwargs.pop("gain", 0.5)
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    graph = PhysicsGraph("cn", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                        CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("cn", time=TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")),
                        participant_order=("a", "b"), **plan_kwargs)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(
        graph, plan,
        {"a": _participant(a, lambda i: Quantity(gain * i["y"].magnitude_in("K") + 5, "K")),
         "b": _participant(b, lambda i: Quantity(i["x"].magnitude_in("K"), "K"))},
        resolver=BulkDataResolver(store), store=store)
    return runtime.run(run_id, external_inputs={}, initial_coupling_values={"e_x": Quantity(0, "K"), "e_y": Quantity(0, "K")},
                       initial_coupling_uncertainty={"e_x": UNKNOWN, "e_y": UNKNOWN})


def _explicit(run_id="coupled"):
    return _loop_run(run_id, scheme=CouplingScheme.EXPLICIT, iteration_semantics=IterationSemantics.SERIAL)


def _implicit(run_id="coupled", *, fail=True, max_iterations=200, gain=0.5):
    return _loop_run(run_id, scheme=CouplingScheme.IMPLICIT, iteration_semantics=IterationSemantics.SERIAL,
                     criteria=(ConvergenceCriterion("e_x", 0.0, Quantity(1e-6, "K")),
                               ConvergenceCriterion("e_y", 0.0, Quantity(1e-6, "K"))),
                     max_iterations=max_iterations, fail_on_nonconvergence=fail, gain=gain)


def _uncoupled(run_id="coupled"):
    a = _spec("a", [_port("x", "output")])
    plan = CouplingPlan("solo", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    return MultiphysicsRuntime(PhysicsGraph("solo", (a,), ()), plan, {"a": _participant(a, lambda _i: Quantity(1, "K"))},
                               resolver=BulkDataResolver(store), store=store).run(run_id, external_inputs={})


# ---- study records (the shape uq_studies._refinement writes) -------------------------------


def _study(run_id="coupled", *, values=(2.0, 3.0, 5.0), problem=None):
    levels = tuple(RefinementLevel(k, v, {"n": 2 ** (2 - k)}, f"{run_id}~numerical~{k}") for k, v in enumerate(values))
    estimate = estimate_numerical_uncertainty(levels, quantity="q", units="K", refinement_ratio=2.0, formal_order=1.0,
                                              order_tolerance=0.1)
    uncertainty = estimate.to_uncertainty() if problem is None else Uncertainty.unknown(f"numerical uncertainty not quantified: {problem}")
    return {
        "channel": UncertaintyChannel.NUMERICAL.value, "kind": "refinement", "spec": {"ratio": 2.0},
        "runs": [{"run_id": level.run_id, "value": level.value} for level in levels],
        "estimate": estimate.to_dict(), "problem": problem, "uncertainty": uncertainty.to_dict(),
    }


def test_the_study_fixture_is_a_quantified_numerical_record():
    assert Uncertainty.from_dict(_study()["uncertainty"]).is_quantified


# ---- rules ---------------------------------------------------------------------------------


def test_an_uncoupled_run_passes_the_study_record_unchanged():
    out = condition_numerical_uncertainty(_study(), _uncoupled())
    assert out.action is CouplingConditionAction.PASSED
    assert out.uncertainty.to_dict() == _study()["uncertainty"]


def test_explicit_splitting_vetoes_the_numerical_channel():
    out = condition_numerical_uncertainty(_study(), _explicit())
    assert out.action is CouplingConditionAction.VETOED and not out.uncertainty.is_quantified
    assert "splitting" in out.reason


def test_an_estimated_iteration_error_never_counts_as_a_bound():
    out = condition_numerical_uncertainty(_study(), _implicit())
    assert assess_coupling_numerical_error(_implicit()).estimated_relative is not None
    assert out.action is CouplingConditionAction.VETOED


def test_a_window_that_did_not_complete_vetoes():
    out = condition_numerical_uncertainty(_study(), _implicit(fail=False, max_iterations=5, gain=2.0))
    assert out.action is CouplingConditionAction.VETOED and "did not complete" in str(out.uncertainty.to_dict())


def test_an_unknown_study_record_stays_unknown():
    out = condition_numerical_uncertainty(_study(problem="refinement level 1 is not usable"), _uncoupled())
    assert out.action is CouplingConditionAction.UNCHANGED_UNKNOWN and not out.uncertainty.is_quantified


def test_the_veto_reaches_the_claims_transport_as_an_unknown_numerical_channel():
    vetoed = condition_numerical_uncertainty(_study(), _explicit())
    passed = condition_numerical_uncertainty(_study(), _uncoupled())
    assert transport({"q": vetoed.uncertainty}).state_of(UncertaintyChannel.NUMERICAL) == "unknown"
    assert transport({"q": passed.uncertainty}).state_of(UncertaintyChannel.NUMERICAL) == "quantified"


def test_the_condition_records_the_assessment_bound_to_the_run_digest():
    run = _explicit()
    out = condition_numerical_uncertainty(_study(), run)
    assert out.to_dict()["assessment"]["run_digest"] == assess_coupling_numerical_error(run).run_digest


# ---- nothing is taken on trust (review F1-F3) ----------------------------------------------


def test_no_caller_can_declare_coverage():
    with pytest.raises(TypeError):
        condition_numerical_uncertainty(_study(), _explicit(), covered_kinds=("splitting",), coverage_basis="trust me")


def test_a_hand_built_assessment_cannot_stand_in_for_the_run():
    with pytest.raises(CouplingConditionError, match="MultiphysicsRunRecord"):
        condition_numerical_uncertainty(_study(), assess_coupling_numerical_error(_explicit()))


def test_a_study_about_another_run_is_refused():
    with pytest.raises(CouplingConditionError, match="not about this coupled run"):
        condition_numerical_uncertainty(_study(run_id="other"), _explicit())


def test_an_edited_study_interval_is_refused():
    record = _study()
    record["uncertainty"] = dict(record["uncertainty"], upper={**record["uncertainty"]["upper"], "magnitude": 99.0})
    with pytest.raises(CouplingConditionError, match="derives"):
        condition_numerical_uncertainty(record, _uncoupled())


def test_a_non_numerical_study_record_is_refused():
    record = dict(_study(), channel=UncertaintyChannel.MODEL_FORM.value)
    with pytest.raises(CouplingConditionError, match="NUMERICAL"):
        condition_numerical_uncertainty(record, _uncoupled())


def test_conditioning_a_coupled_run_never_does_better_than_its_study_alone():
    study = Uncertainty.from_dict(_study()["uncertainty"])
    for run in (_explicit(), _implicit(), _implicit(fail=False, max_iterations=5, gain=2.0), _uncoupled()):
        out = condition_numerical_uncertainty(_study(), run)
        # either the study's own record, unchanged, or UNKNOWN: never narrower, never newly quantified
        assert out.uncertainty.to_dict() == study.to_dict() or not out.uncertainty.is_quantified
