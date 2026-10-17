"""Phase 1 BR7 -- coupled-run outcome semantics in the system runtime.

``MultiphysicsAuthority`` exposed outputs only when every window said
``converged``, so every explicit run and every event-aligned window failed the
node.  Outcomes are now typed: an explicit run is COMPLETED_EXPLICIT (no
convergence claim), an implicit run is CONVERGED only when every window
satisfied every required interface, anything else exposes nothing.

NOT RUN (Phase 1 build phase): docs/work/DEFERRED_VALIDATION.md, DV-45.
"""

from __future__ import annotations

import dataclasses
import hashlib
from types import SimpleNamespace

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, CouplingRunOutcome, InitializationResult, MultiphysicsRuntime,
    assess_run_outcome,
)
from engcore.execution.multiphysics.numerical_error import ErrorSourceStatus, assess_coupling_numerical_error
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, CouplingWindowRecord,
    IterationSemantics, ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, TimePolicy,
    WindowOutcome,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.system_runtime.authorities import MultiphysicsAuthority

UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


def _spec(pid, ports):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=True,
                           checkpointable=True, deterministic_restore=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _participant(spec, fn):
    out = spec.outputs[0].port_id
    state = {"n": 0}

    def advance(request):
        state["n"] += 1
        return AdvanceResult(request.end, {out: fn(dict(request.inputs))}, {out: UNKNOWN}, 1, True)

    def checkpoint(instant):
        digest = hashlib.sha256(repr(state["n"]).encode()).hexdigest()
        return RuntimeCheckpoint(CheckpointRecord(spec.participant_id, instant, digest, True), dict(state))

    return CallbackParticipant(spec, initialize=lambda *_: InitializationResult({out: Quantity(300, "K")}, {out: UNKNOWN}),
                               advance=advance, checkpoint=checkpoint, restore=lambda cp: state.update(cp.token))


def _runtime(scheme, *, gain=0.5, max_iterations=200, fail=True):
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    graph = PhysicsGraph("outcome", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                             CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    time = TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(0.5, "s"))
    if scheme is CouplingScheme.EXPLICIT:
        plan = CouplingPlan("outcome", scheme, IterationSemantics.SERIAL, time, ("a", "b"))
    else:
        plan = CouplingPlan("outcome", scheme, IterationSemantics.SERIAL, time, ("a", "b"),
                            (ConvergenceCriterion("e_y", 0.0, Quantity(1e-9, "K")),), max_iterations=max_iterations,
                            fail_on_nonconvergence=fail)
    store = InMemoryBulkStore()
    participants = {"a": _participant(a, lambda i: Quantity(gain * i["y"].magnitude_in("K") + 100.0, "K")),
                    "b": _participant(b, lambda i: Quantity(i["x"].magnitude_in("K"), "K"))}
    return MultiphysicsRuntime(graph, plan, participants, resolver=BulkDataResolver(store), store=store)


def _call():
    return SimpleNamespace(run_id="sys", node=SimpleNamespace(node_id="mp", commits_state=False))


def _authority(runtime=None, **kw):
    return MultiphysicsAuthority("coupled-node", runtime, run_kwargs=lambda call: {"external_inputs": {}},
                                 outputs={"x": "a.x"}, **kw)


# ---- the typed assessment --------------------------------------------------------------------------


def test_an_explicit_run_is_completed_and_makes_no_convergence_claim():
    assessment = assess_run_outcome(_runtime(CouplingScheme.EXPLICIT).run("r", external_inputs={}))
    assert assessment.outcome is CouplingRunOutcome.COMPLETED_EXPLICIT
    assert assessment.completed and not assessment.mathematically_converged


def test_an_implicit_run_whose_windows_converged_is_converged():
    assessment = assess_run_outcome(_runtime(CouplingScheme.IMPLICIT).run("r", external_inputs={}))
    assert assessment.outcome is CouplingRunOutcome.CONVERGED
    assert assessment.required_edges == ("e_y",)


def test_an_implicit_run_at_its_iteration_limit_is_not_completed():
    run = _runtime(CouplingScheme.IMPLICIT, max_iterations=1, fail=False).run("r", external_inputs={})
    assert any(w.outcome is WindowOutcome.ITERATION_LIMIT for w in run.windows)
    assessment = assess_run_outcome(run)
    assert assessment.outcome is CouplingRunOutcome.NOT_COMPLETED
    assert any("iteration_limit" in p for p in assessment.problems)


def test_an_implicit_window_relabelled_explicit_completed_is_refused():
    run = _runtime(CouplingScheme.IMPLICIT).run("r", external_inputs={})
    first = run.windows[0]
    forged = CouplingWindowRecord(first.index, first.start, first.end, WindowOutcome.EXPLICIT_COMPLETED, first.iterations)
    forged_run = dataclasses.replace(run, windows=(forged,) + tuple(run.windows[1:]))
    assessment = assess_run_outcome(forged_run)
    assert assessment.outcome is CouplingRunOutcome.NOT_COMPLETED
    assert assessment.windows[0]["classification"] == "inconsistent"
    accounting = assess_coupling_numerical_error(forged_run)
    assert any(s.status is ErrorSourceStatus.UNBOUNDED and s.method == "window_inconsistent" for s in accounting.sources)


# ---- the authority -------------------------------------------------------------------------------------


def test_the_authority_exposes_an_explicit_run_and_labels_it():
    outcome = _authority(_runtime(CouplingScheme.EXPLICIT)).execute(_call())
    assert outcome.status == "succeeded", outcome.reason
    assert outcome.diagnostics["coupling_outcome"] == "completed_explicit"
    assert "no convergence claim" in str(outcome.outputs["x"].uncertainty.to_dict())
    assert not outcome.outputs["x"].uncertainty.is_quantified


def test_the_authority_exposes_a_converged_implicit_run():
    outcome = _authority(_runtime(CouplingScheme.IMPLICIT)).execute(_call())
    assert outcome.status == "succeeded", outcome.reason
    assert outcome.diagnostics["coupling_outcome"] == "converged"


def test_the_authority_refuses_an_unconverged_implicit_run():
    outcome = _authority(_runtime(CouplingScheme.IMPLICIT, max_iterations=1, fail=False)).execute(_call())
    assert outcome.status == "failed" and "did not complete" in outcome.reason
    assert not outcome.outputs


def test_the_authority_refuses_something_that_is_not_a_run_record():
    real = _runtime(CouplingScheme.EXPLICIT)
    fake = SimpleNamespace(graph=real.graph, plan=real.plan, participants={},
                           run=lambda run_id, **kw: SimpleNamespace(run_id=run_id, windows=()))
    outcome = _authority(fake).execute(_call())
    assert outcome.status == "failed" and "no run record" in outcome.reason


def test_the_authority_refuses_a_run_produced_for_another_call():
    real = _runtime(CouplingScheme.EXPLICIT)
    relabelled = SimpleNamespace(graph=real.graph, plan=real.plan, participants=real.participants,
                                 run=lambda run_id, **kw: real.run("someone-else", **kw))
    outcome = _authority(relabelled).execute(_call())
    assert outcome.status == "failed" and "not the run" in outcome.reason
