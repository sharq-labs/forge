"""Adaptive coupling-window control (Engineering Runtime V1, Big Rock 1).

A window that fails NUMERICALLY (iteration limit, divergence, a participant's
internal non-convergence) is rolled back to its start and retried over a
shorter window, within a declared bound.  Refusals are never retried, a window
that still fails is reported exactly as before, and every rejected attempt is
logged.  NOT YET EXECUTED (build phase): see the deferred-validation backlog in
docs/work/PROGRESS.md.
"""

from __future__ import annotations

import hashlib

import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, CouplingWindowNotConverged, InitializationResult, MultiphysicsExecutionError,
    MultiphysicsRuntime,
)
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy, WindowControlPolicy,
    WindowOutcome,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _q(seconds):
    return Quantity(seconds, "s")


def _policy(minimum=0.1, factor=0.5, subdivisions=4, divergence=None):
    return WindowControlPolicy(_q(minimum), factor, subdivisions, divergence)


def _spec(pid, ports, checkpointable=True):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=checkpointable, deterministic_restore=checkpointable)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


class Stateful:
    """A participant whose state is the simulated time it has integrated (rollback must undo it)."""

    def __init__(self, spec, fn, *, max_stable_step=None, refuse=False):
        self.spec, self.fn = spec, fn
        self.max_stable_step = max_stable_step
        self.refuse = refuse
        self.state = {"integrated_s": 0.0}
        self.calls = 0
        self.restores = 0

    def _digest(self):
        return hashlib.sha256(repr(sorted(self.state.items())).encode()).hexdigest()

    def participant(self):
        out = self.spec.outputs[0].port_id

        def initialize(_t, _i, _u):
            return InitializationResult({out: Quantity(0, "K")}, {out: UNKNOWN})

        def advance(request):
            self.calls += 1
            if self.refuse:
                raise InvalidScientificProblem("participant refuses: a missing boundary condition is never defaulted")
            width = request.end.magnitude_in("s") - request.start.magnitude_in("s")
            self.state = {"integrated_s": self.state["integrated_s"] + width}
            converged = self.max_stable_step is None or width <= self.max_stable_step + 1e-12
            return AdvanceResult(request.end, {out: self.fn(dict(request.inputs), width)}, {out: UNKNOWN}, 1, converged)

        def checkpoint(instant):
            return RuntimeCheckpoint(CheckpointRecord(self.spec.participant_id, instant, self._digest(), True),
                                     dict(self.state))

        def restore(cp):
            self.restores += 1
            self.state = dict(cp.token)

        return CallbackParticipant(self.spec, initialize=initialize, advance=advance, checkpoint=checkpoint,
                                   restore=restore)


def _explicit_runtime(control, *, max_stable_step=0.25, refuse=False, end=1.0, window=0.5):
    """source -> sink, explicit; the sink's internal solve fails above max_stable_step."""
    src_spec = _spec("src", [_port("x", "output")])
    sink_spec = _spec("sink", [_port("x", "input"), _port("y", "output")])
    src = Stateful(src_spec, lambda _i, _w: Quantity(300, "K"))
    sink = Stateful(sink_spec, lambda i, _w: i["x"], max_stable_step=max_stable_step, refuse=refuse)
    graph = PhysicsGraph("wc-explicit", (src_spec, sink_spec), (CouplingEdge("e_x", PortRef("src", "x"), PortRef("sink", "x")),))
    plan = CouplingPlan("wc-explicit", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(_q(0), _q(end), _q(window)), window_control=control)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"src": src.participant(), "sink": sink.participant()},
                                  resolver=BulkDataResolver(store), store=store)
    return runtime, src, sink


def _run(runtime, **kw):
    return runtime.run("wc", external_inputs={}, **kw)


# ---- the policy record ---------------------------------------------------------------------


@pytest.mark.parametrize("kwargs", [dict(factor=0.0), dict(factor=1.0), dict(factor=float("nan")), dict(subdivisions=0),
                                    dict(subdivisions=65), dict(minimum=0.0), dict(divergence=1.0),
                                    dict(divergence=float("inf"))])
def test_policy_rejects_out_of_range_parameters(kwargs):
    with pytest.raises(InvalidScientificProblem):
        _policy(**kwargs)


def test_policy_requires_a_time_minimum_window_with_no_default():
    with pytest.raises(TypeError):
        WindowControlPolicy()  # how short a window may become is the plan's decision
    with pytest.raises(InvalidScientificProblem):
        WindowControlPolicy(Quantity(0.1, "m"))


def test_plan_without_window_control_keeps_its_serialized_identity():
    plan = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, TimePolicy(_q(0), _q(1), _q(0.5)))
    assert "window_control" not in plan.to_dict()
    assert CouplingPlan.from_dict(plan.to_dict()) == plan


def test_plan_with_window_control_round_trips_and_changes_its_fingerprint():
    base = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, TimePolicy(_q(0), _q(1), _q(0.5)))
    controlled = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, TimePolicy(_q(0), _q(1), _q(0.5)),
                              window_control=_policy())
    assert CouplingPlan.from_dict(controlled.to_dict()) == controlled
    assert controlled.fingerprint() != base.fingerprint()


def test_minimum_window_larger_than_the_coupling_window_is_refused():
    with pytest.raises(InvalidScientificProblem, match="minimum_window"):
        CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, TimePolicy(_q(0), _q(1), _q(0.5)),
                     window_control=_policy(minimum=0.6))


def test_divergence_factor_on_an_explicit_plan_is_refused():
    with pytest.raises(InvalidScientificProblem, match="implicit"):
        CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, TimePolicy(_q(0), _q(1), _q(0.5)),
                     window_control=_policy(divergence=10.0))


def test_window_control_requires_deterministic_restore_on_every_participant():
    a, b = _spec("a", [_port("x", "output")]), _spec("b", [_port("x", "input"), _port("y", "output")], checkpointable=False)
    graph = PhysicsGraph("g", (a, b), (CouplingEdge("e", PortRef("a", "x"), PortRef("b", "x")),))
    plan = CouplingPlan("p", CouplingScheme.EXPLICIT, IterationSemantics.SERIAL, TimePolicy(_q(0), _q(1), _q(0.5)),
                        window_control=_policy())
    with pytest.raises(InvalidScientificProblem, match="rolls every participant back"):
        plan.validate_against(graph)


# ---- runtime behaviour ---------------------------------------------------------------------


def test_without_a_policy_an_internal_non_convergence_fails_the_run_as_before():
    runtime, _, _ = _explicit_runtime(None)
    with pytest.raises(CouplingWindowNotConverged, match="did not converge internally"):
        _run(runtime)
    assert issubclass(CouplingWindowNotConverged, MultiphysicsExecutionError)


def test_subdivision_completes_the_run_and_rolls_back_every_rejected_attempt():
    runtime, src, sink = _explicit_runtime(_policy(minimum=0.1))
    run = _run(runtime)
    widths = [w.end.magnitude_in("s") - w.start.magnitude_in("s") for w in run.windows]
    assert run.ended_at.magnitude_in("s") == pytest.approx(1.0)
    assert all(width <= 0.25 + 1e-12 for width in widths)
    # rollback: each participant integrated exactly the horizon, not the horizon plus rejected attempts
    assert src.state["integrated_s"] == pytest.approx(1.0) and sink.state["integrated_s"] == pytest.approx(1.0)
    events = run.final_outputs["_window_control"]["events"]
    assert any(e["action"] == "subdivided" and "did not converge internally" in e["reason"] for e in events)
    assert any(e["action"] == "accepted_after_subdivision" for e in events)
    assert all(e["action"] != "exhausted" for e in events)
    assert sink.restores >= 1


def test_exhausted_subdivision_fails_with_the_numerical_cause_and_records_it():
    # 0.5 s fails -> 0.25 s (>= 0.2) fails -> 0.125 s would be below the minimum: exhausted after one subdivision
    runtime, _, _ = _explicit_runtime(_policy(minimum=0.2), max_stable_step=0.1)
    with pytest.raises(CouplingWindowNotConverged, match="after 1 window subdivision"):
        _run(runtime)
    assert runtime._window_control_log[-1]["action"] == "exhausted"


def test_a_refusal_is_never_retried():
    runtime, _, sink = _explicit_runtime(_policy(minimum=0.1), refuse=True)
    with pytest.raises(InvalidScientificProblem, match="never defaulted") as caught:
        _run(runtime)
    assert not isinstance(caught.value, CouplingWindowNotConverged)
    assert sink.calls == 1 and sink.restores == 0
    assert runtime._window_control_log == []


def test_runs_that_never_fail_record_no_window_control_events():
    runtime, _, _ = _explicit_runtime(_policy(minimum=0.1), max_stable_step=None)
    run = _run(runtime)
    assert run.final_outputs["_window_control"]["events"] == []
    assert len(run.windows) == 2


def test_runs_without_a_policy_carry_no_window_control_record():
    runtime, _, _ = _explicit_runtime(None, max_stable_step=None)
    assert "_window_control" not in _run(runtime).final_outputs


# ---- implicit coupling ---------------------------------------------------------------------


def _implicit_runtime(control, *, gain, fail_on_nonconvergence=True, max_iterations=30):
    """x = gain(width) * y + 5, y = x; contracts only while |gain(width)| < 1."""
    a_spec = _spec("a", [_port("y", "input"), _port("x", "output")])
    b_spec = _spec("b", [_port("x", "input"), _port("y", "output")])
    a = Stateful(a_spec, lambda i, w: Quantity(gain(w) * i["y"].magnitude_in("K") + 5, "K"))
    b = Stateful(b_spec, lambda i, _w: Quantity(i["x"].magnitude_in("K"), "K"))
    graph = PhysicsGraph("wc-implicit", (a_spec, b_spec), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                                           CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    plan = CouplingPlan("wc-implicit", CouplingScheme.IMPLICIT, IterationSemantics.SERIAL,
                        TimePolicy(_q(0), _q(1), _q(1)), ("a", "b"),
                        (ConvergenceCriterion("e_x", 0.0, Quantity(1e-6, "K")), ConvergenceCriterion("e_y", 0.0, Quantity(1e-6, "K"))),
                        max_iterations=max_iterations, fail_on_nonconvergence=fail_on_nonconvergence, window_control=control)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(graph, plan, {"a": a.participant(), "b": b.participant()},
                                  resolver=BulkDataResolver(store), store=store)
    return runtime, a, b


def _run_implicit(runtime):
    return runtime.run("wc-i", external_inputs={}, initial_coupling_values={"e_x": Quantity(0, "K"), "e_y": Quantity(0, "K")},
                       initial_coupling_uncertainty={"e_x": UNKNOWN, "e_y": UNKNOWN})


def test_implicit_window_that_only_contracts_when_shorter_converges_after_subdivision():
    # gain = 2 * width: a 1 s window has gain 2 (no fixed-point convergence), 0.25 s has gain 0.5
    runtime, a, _ = _implicit_runtime(_policy(minimum=0.125), gain=lambda w: 2.0 * w)
    run = _run_implicit(runtime)
    assert all(w.outcome is WindowOutcome.CONVERGED for w in run.windows)
    assert run.ended_at.magnitude_in("s") == pytest.approx(1.0)
    assert a.state["integrated_s"] == pytest.approx(1.0)
    reasons = [e["reason"] for e in run.final_outputs["_window_control"]["events"] if e["action"] == "subdivided"]
    assert reasons and all("without convergence" in r for r in reasons)


def test_implicit_iteration_limit_without_failing_is_still_reported_as_iteration_limit_when_exhausted():
    runtime, _, _ = _implicit_runtime(_policy(minimum=0.5, subdivisions=1), gain=lambda _w: 2.0,
                                      fail_on_nonconvergence=False, max_iterations=5)
    run = _run_implicit(runtime)
    assert run.windows[0].outcome is WindowOutcome.ITERATION_LIMIT  # never relabelled as converged
    assert any(e["action"] == "exhausted" for e in run.final_outputs["_window_control"]["events"])


def test_divergence_is_detected_before_the_iteration_limit_is_spent():
    runtime, a, _ = _implicit_runtime(_policy(minimum=1.0, subdivisions=1, divergence=10.0), gain=lambda _w: 3.0,
                                      max_iterations=200)
    with pytest.raises(CouplingWindowNotConverged, match="diverging"):
        _run_implicit(runtime)
    # residual grows 3x per iteration: past 10x within a handful of iterations, far below 200
    assert a.calls < 20


# ---- BR11: step-size memory (growth_factor) --------------------------------------------------


@pytest.mark.parametrize("growth", [1.0, 0.5, 10.5, float("nan")])
def test_growth_factor_is_bounded(growth):
    with pytest.raises(InvalidScientificProblem, match="growth_factor"):
        WindowControlPolicy(_q(0.1), 0.5, 4, None, growth)


def test_policies_without_step_size_memory_keep_their_identity():
    assert "growth_factor" not in _policy().to_dict()
    remembered = WindowControlPolicy(_q(0.1), 0.5, 4, None, 2.0)
    assert WindowControlPolicy.from_dict(remembered.to_dict()) == remembered
    assert remembered.to_dict()["growth_factor"] == 2.0


def _subdivisions(run):
    return sum(1 for e in run.final_outputs["_window_control"]["events"] if e["action"] == "subdivided")


def test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable():
    without, _, _ = _explicit_runtime(_policy(minimum=0.1), end=2.0)
    remembered_runtime, src, sink = _explicit_runtime(WindowControlPolicy(_q(0.1), 0.5, 4, None, 2.0), end=2.0)
    plain, remembered = _run(without), _run(remembered_runtime)
    # nominal 0.5 s always fails (> 0.25 s): 8 subdivisions without memory; with growth 2, every other window
    assert _subdivisions(plain) == 8 and _subdivisions(remembered) == 4
    widths = [w.end.magnitude_in("s") - w.start.magnitude_in("s") for w in remembered.windows]
    assert all(width <= 0.25 + 1e-12 for width in widths)
    assert remembered.ended_at.magnitude_in("s") == pytest.approx(2.0)
    assert sink.state["integrated_s"] == pytest.approx(2.0)  # rollback still exact
    changes = [e for e in remembered.final_outputs["_window_control"]["events"] if e["action"] == "width_changed"]
    assert changes and {c["reason"] for c in changes} >= {"accepted after subdivision", "grown by 2"}


def test_without_growth_factor_no_width_change_is_logged():
    run = _run(_explicit_runtime(_policy(minimum=0.1), end=2.0)[0])
    assert all(e["action"] != "width_changed" for e in run.final_outputs["_window_control"]["events"])
