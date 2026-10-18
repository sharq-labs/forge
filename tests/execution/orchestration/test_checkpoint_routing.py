"""A checkpoint is solver state: it never crosses a fallback boundary and a failed attempt never supplies one."""

import pytest

from engcore.execution.orchestration import (
    AdaptiveRefinementPolicy, AdvancedBackendOutcome, AdvancedStopReason, AttemptState, BackendOutcome, OrchestrationPolicy,
    CheckpointReference, ExecutionBudget, ProblemKind, RefinementDiagnostics, ResourceUsage, SimulationPlan,
    SimulationRequirements, SolverCapability, run_adaptive_plan, run_plan,
)
from engcore.execution.orchestration.checkpoint import adopt_checkpoint, resume_owner, resume_point_for

PROBLEM = "1" * 64


def _plan(*args, **kwargs):
    return SimulationPlan(*args, problem_digest=PROBLEM, **kwargs)


def _checkpoint(cid, digest, solver_id=""):
    # Producer returns can be adopted from known context; named resume points
    # explicitly carry the original build/problem, including expected records.
    return CheckpointReference(cid, digest, solver_id, f"{solver_id}@1" if solver_id else "",
                               PROBLEM if solver_id else "")


GOOD_A = _checkpoint("a:cp1", "a" * 64)
DIVERGED_A = _checkpoint("a:diverged", "d" * 64)


class Backend:
    def __init__(self, solver_id, outcomes):
        self.solver_id = solver_id
        self.solver_build = f"{solver_id}@1"
        self.outcomes = list(outcomes)
        self.received = []

    def run(self, **kw):
        self.received.append(kw["checkpoint"])
        return self.outcomes.pop(0)

    def run_advanced(self, **kw):
        self.received.append(kw["checkpoint"])
        return self.outcomes.pop(0)


def _adv(state, error=None, checkpoint=None, failure_code=""):
    return AdvancedBackendOutcome(state, ResourceUsage(), RefinementDiagnostics(error_indicator=error),
                                  failure_code=failure_code, checkpoint=checkpoint)


def _adaptive(a_outcomes, b_outcomes, checkpoint=None):
    a, b = Backend("a", a_outcomes), Backend("b", b_outcomes)
    report = run_adaptive_plan(
        _plan("q", ("a", "b"), ExecutionBudget(max_attempts=6, max_refinements=3)),
        SimulationRequirements(ProblemKind.ODE),
        (SolverCapability("a", (ProblemKind.ODE,), preference=2), SolverCapability("b", (ProblemKind.ODE,), preference=1)),
        {"a": a, "b": b},
        AdaptiveRefinementPolicy(target_error=1e-3, max_refinement_level=3),
        checkpoint=checkpoint,
    )
    return report, a, b


def test_checkpoint_of_a_failed_solver_never_reaches_the_fallback_solver():
    # run_plan runs each solver once, so this observes the routing rule; the discard of a
    # failed attempt's checkpoint is observed through run_adaptive_plan below
    a = Backend("a", [BackendOutcome(AttemptState.FAILED, "diverged", GOOD_A)])
    b = Backend("b", [BackendOutcome(AttemptState.CONVERGED)])
    report = run_plan(_plan("p", ("a", "b"), ExecutionBudget(max_attempts=2)), {"a": a, "b": b})
    assert report.converged
    assert b.received == [None]


def test_checkpoint_of_a_cancelled_solver_does_not_cross_to_another_solver():
    a = Backend("a", [BackendOutcome(AttemptState.CANCELLED, "", GOOD_A)])
    b = Backend("b", [BackendOutcome(AttemptState.CONVERGED)])
    run_plan(_plan("p", ("a", "b"), ExecutionBudget(max_attempts=2)), {"a": a, "b": b})
    assert b.received == [None]


def test_caller_checkpoint_resumes_only_the_solver_it_names_and_no_other_solver_runs_cold():
    bound = _checkpoint("b:cp", "b" * 64, "b")
    a = Backend("a", [BackendOutcome(AttemptState.CONVERGED)])
    b = Backend("b", [BackendOutcome(AttemptState.CONVERGED)])
    report = run_plan(_plan("p", ("a", "b"), ExecutionBudget(max_attempts=2)), {"a": a, "b": b}, checkpoint=bound)
    assert a.received == []  # a cannot continue b's state, and is not run cold in its place
    assert report.attempts[0].failure_code == "resume_checkpoint_belongs_to_b"
    assert b.received == [bound]


def test_caller_checkpoint_of_a_solver_that_does_not_run_yields_no_success():
    a = Backend("a", [BackendOutcome(AttemptState.CONVERGED)])
    report = run_plan(_plan("p", ("a",)), {"a": a}, checkpoint=_checkpoint("b:cp", "b" * 64, "b"))
    assert a.received == [] and not report.converged


def test_unbound_caller_checkpoint_is_refused_not_turned_into_a_cold_start():
    a = Backend("a", [BackendOutcome(AttemptState.CONVERGED)])
    with pytest.raises(ValueError, match="does not name the solver"):
        run_plan(_plan("p", ("a",)), {"a": a}, checkpoint=GOOD_A)
    with pytest.raises(ValueError, match="does not name the solver"):
        _adaptive([_adv(AttemptState.CONVERGED, 1e-4)], [], checkpoint=GOOD_A)
    assert a.received == []


def test_adaptive_same_solver_refinement_resumes_from_its_own_checkpoint():
    accepted = _checkpoint("a:cp2", "c" * 64)
    report, a, _ = _adaptive([_adv(AttemptState.CONVERGED, 1.0, GOOD_A), _adv(AttemptState.CONVERGED, 1e-4, accepted)], [])
    assert report.stop_reason is AdvancedStopReason.ERROR_TARGET_SATISFIED
    assert a.received == [None, _checkpoint("a:cp1", "a" * 64, "a")]
    assert report.final_checkpoint == _checkpoint("a:cp2", "c" * 64, "a")


def test_adaptive_accepted_attempt_without_a_checkpoint_does_not_inherit_the_rejected_refinements():
    # r0 (error 1.0) was REJECTED for its error; its state is not the accepted result's state
    report, _, _ = _adaptive([_adv(AttemptState.CONVERGED, 1.0, GOOD_A), _adv(AttemptState.CONVERGED, 1e-4)], [])
    assert report.stop_reason is AdvancedStopReason.ERROR_TARGET_SATISFIED
    assert report.final_checkpoint is None


def test_adaptive_diverged_checkpoint_neither_resumes_the_fallback_nor_becomes_the_final_checkpoint():
    report, a, b = _adaptive(
        [_adv(AttemptState.CONVERGED, 1.0, GOOD_A), _adv(AttemptState.DIVERGED, None, DIVERGED_A, "nan")],
        [_adv(AttemptState.CONVERGED, 1e-4)],
    )
    assert report.stop_reason is AdvancedStopReason.ERROR_TARGET_SATISFIED
    assert b.received == [None]
    # B accepted with no checkpoint of its own: the report must not hand out A's state as the accepted result's
    assert report.final_checkpoint is None
    assert "a:checkpoint_of_diverged_attempt_discarded" in report.problems
    # the diverged attempt's record does not carry its refused checkpoint as if usable
    assert [r.checkpoint for r in report.attempts] == [_checkpoint("a:cp1", "a" * 64, "a"), None, None]


def test_adaptive_diverged_checkpoint_does_not_replace_the_last_good_one():
    report, _, b = _adaptive(
        [_adv(AttemptState.CONVERGED, 1.0, GOOD_A), _adv(AttemptState.DIVERGED, None, DIVERGED_A, "nan")],
        [_adv(AttemptState.FAILED, None, None, "no_convergence")],
    )
    assert not report.successful
    assert report.final_checkpoint == _checkpoint("a:cp1", "a" * 64, "a")


def test_adaptive_checkpoint_claiming_another_solver_is_refused():
    forged = _checkpoint("b:cp", "b" * 64, "b")
    report, a, b = _adaptive(
        [_adv(AttemptState.CONVERGED, 1.0, forged), _adv(AttemptState.FAILED, None, None, "x")],
        [_adv(AttemptState.CONVERGED, 1e-4)],
    )
    assert a.received == [None, None]
    assert b.received == [None]
    assert "a:checkpoint_names_solver_b_refused" in report.problems


def test_adaptive_caller_checkpoint_skips_other_solvers_with_a_recorded_problem():
    bound = _checkpoint("b:cp", "b" * 64, "b")
    report, a, b = _adaptive([_adv(AttemptState.CONVERGED, 1e-4)], [_adv(AttemptState.CONVERGED, 1e-4)], checkpoint=bound)
    assert a.received == [] and b.received == [bound]
    assert "a:resume_checkpoint_belongs_to_b" in report.problems
    assert report.stop_reason is AdvancedStopReason.ERROR_TARGET_SATISFIED


def test_adaptive_backend_exception_records_no_checkpoint():
    class Raises(Backend):
        def run_advanced(self, **kw):
            self.received.append(kw["checkpoint"])
            raise RuntimeError("boom")

    a = Raises("a", [])
    b = Backend("b", [_adv(AttemptState.CONVERGED, 1e-4)])
    report = run_adaptive_plan(
        _plan("q", ("a", "b"), ExecutionBudget(max_attempts=3)), SimulationRequirements(ProblemKind.ODE),
        (SolverCapability("a", (ProblemKind.ODE,), preference=2), SolverCapability("b", (ProblemKind.ODE,), preference=1)),
        {"a": a, "b": b}, AdaptiveRefinementPolicy(target_error=1e-3, max_refinement_level=0),
    )
    assert report.attempts[0].checkpoint is None
    assert a.received == [None] and b.received == [None]
    assert report.successful


@pytest.mark.parametrize("state", [AttemptState.FAILED, AttemptState.DIVERGED])
def test_adopt_refuses_unusable_states(state):
    assert adopt_checkpoint(GOOD_A, solver_id="a", state=state)[0] is None


def test_adopt_and_resume_helpers():
    bound, problem = adopt_checkpoint(GOOD_A, solver_id="a", state=AttemptState.CONVERGED, solver_build="a@1", problem_digest=PROBLEM)
    assert problem == "" and bound.solver_id == "a"
    assert resume_point_for(bound, "a", solver_build="a@1", problem_digest=PROBLEM) is bound
    assert resume_point_for(bound, "b") is None
    assert resume_point_for(GOOD_A, "a") is None
    assert adopt_checkpoint("not-a-checkpoint", solver_id="a", state="converged") == (None, "a:checkpoint_not_a_reference")
    assert resume_owner(None) is None and resume_owner(bound) == "a"
    with pytest.raises(ValueError):
        resume_owner(GOOD_A)


def test_adaptive_resume_owner_that_is_not_capable_stops_as_no_capable_solver():
    report, a, b = _adaptive([_adv(AttemptState.CONVERGED, 1e-4)], [_adv(AttemptState.CONVERGED, 1e-4)],
                             checkpoint=_checkpoint("z:cp", "e" * 64, "z"))
    assert report.stop_reason is AdvancedStopReason.NO_CAPABLE_SOLVER
    assert a.received == [] and b.received == [] and report.attempts == ()
    assert report.problems == ("resume_checkpoint_owner_z_not_a_capable_declared_solver",)


def test_adaptive_resume_owner_failure_does_not_fall_back_to_a_cold_solver():
    bound = _checkpoint("a:cp", "a" * 64, "a")
    report, a, b = _adaptive([_adv(AttemptState.FAILED, None, None, "no_convergence")], [_adv(AttemptState.CONVERGED, 1e-4)],
                             checkpoint=bound)
    assert a.received == [bound] and b.received == []
    assert not report.successful
    assert "b:resume_checkpoint_belongs_to_a" in report.problems


def test_adaptive_refinement_budget_stop_reports_the_last_adopted_resume_point_bound_to_its_solver():
    a = Backend("a", [_adv(AttemptState.CONVERGED, 1.0, GOOD_A), _adv(AttemptState.CONVERGED, 1.0)])
    report = run_adaptive_plan(
        _plan("q", ("a",), ExecutionBudget(max_attempts=5, max_refinements=1)), SimulationRequirements(ProblemKind.ODE),
        (SolverCapability("a", (ProblemKind.ODE,)),), {"a": a}, AdaptiveRefinementPolicy(target_error=1e-3, max_refinement_level=5))
    assert report.stop_reason is AdvancedStopReason.REFINEMENT_BUDGET and not report.successful
    assert report.final_checkpoint == _checkpoint("a:cp1", "a" * 64, "a")


def test_run_plan_without_fallback_stops_when_the_first_solver_cannot_continue_the_resume():
    a = Backend("a", [BackendOutcome(AttemptState.CONVERGED)])
    b = Backend("b", [BackendOutcome(AttemptState.CONVERGED)])
    report = run_plan(_plan("p", ("a", "b"), ExecutionBudget(max_attempts=2)), {"a": a, "b": b},
                      policy=OrchestrationPolicy(allow_solver_fallback=False), checkpoint=_checkpoint("b:cp", "b" * 64, "b"))
    assert a.received == [] and b.received == [] and not report.converged
    assert [x.failure_code for x in report.attempts] == ["resume_checkpoint_belongs_to_b"]


def test_run_plan_refuses_a_backend_registered_under_another_solvers_name():
    impostor = Backend("t", [BackendOutcome(AttemptState.CONVERGED)])
    impostor.solver_build = "s@1"  # isolate solver-id mismatch from the earlier build guard
    bound = _checkpoint("s:cp", "f" * 64, "s")
    report = run_plan(_plan("p", ("s",)), {"s": impostor}, checkpoint=bound)
    assert impostor.received == [] and not report.converged
    assert report.attempts[0].failure_code == "backend_solver_identity_mismatch"


@pytest.mark.parametrize("state", [AttemptState.PLANNED, AttemptState.RUNNING])
def test_non_terminal_attempt_never_supplies_a_resume_point(state):
    assert adopt_checkpoint(GOOD_A, solver_id="a", state=state)[0] is None
    a = Backend("a", [AdvancedBackendOutcome(state, ResourceUsage(), checkpoint=GOOD_A)])
    report = run_adaptive_plan(
        _plan("q", ("a",), ExecutionBudget(max_attempts=1)), SimulationRequirements(ProblemKind.ODE),
        (SolverCapability("a", (ProblemKind.ODE,)),), {"a": a}, AdaptiveRefinementPolicy(target_error=1e-3, max_refinement_level=0))
    assert not report.successful
    assert report.final_checkpoint is None and report.attempts[0].checkpoint is None


def test_a_fallback_route_starts_at_its_own_refinement_level_zero():
    # review F-5: solver a refined to level 1 and diverged; b must not inherit a's refinement request
    report, a, b = _adaptive([_adv(AttemptState.CONVERGED, 1.0), _adv(AttemptState.DIVERGED, None, None, "nan")],
                             [_adv(AttemptState.CONVERGED, 1e-4)])
    assert report.stop_reason is AdvancedStopReason.ERROR_TARGET_SATISFIED
    last = report.attempts[-1]
    assert last.solver_id == "b" and last.refinement is None and last.attempt.refinement_level == 0
    assert last.attempt.attempt_id.endswith(":b:r0")
