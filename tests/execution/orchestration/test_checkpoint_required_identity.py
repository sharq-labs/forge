"""R4 fail-closed legacy admission. Build-First: NOT RUN. No schema migration."""
import pytest

from engcore.execution.orchestration import (
    AdaptiveRefinementPolicy, AdvancedBackendOutcome, AttemptState, BackendOutcome, CheckpointReference, ProblemKind,
    RefinementDiagnostics, ResourceUsage,
    SimulationPlan, SimulationRequirements, SolverCapability, run_adaptive_plan, run_plan,
)
from engcore.execution.orchestration.checkpoint import (
    CheckpointConversion, adopt_checkpoint, converted_resume_point, resume_refusal,
)

PROBLEM = "a" * 64


class Backend:
    solver_id, solver_build = "s", "build-1"

    def __init__(self):
        self.calls = 0

    def run(self, **kwargs):
        self.calls += 1
        return BackendOutcome(AttemptState.CONVERGED)

    def run_advanced(self, **kwargs):
        raise AssertionError("inadmissible checkpoint reached execution")


@pytest.mark.parametrize("build,problem", [("", ""), ("", PROBLEM), ("build-1", "")])
def test_missing_checkpoint_bindings_refuse_before_either_runner_executes(build, problem):
    cp = CheckpointReference("legacy", "b" * 64, "s", build, problem)
    backend = Backend()
    plan = SimulationPlan("p", ("s",), problem_digest=PROBLEM)
    report = run_plan(plan, {"s": backend}, checkpoint=cp)
    assert not report.converged and backend.calls == 0
    assert "resume_checkpoint_refused" in report.attempts[0].failure_code
    report = run_adaptive_plan(plan, SimulationRequirements(ProblemKind.ODE),
        (SolverCapability("s", (ProblemKind.ODE,)),), {"s": backend},
        AdaptiveRefinementPolicy(target_error=1e-3, max_refinement_level=1), checkpoint=cp)
    assert not report.successful and backend.calls == 0
    assert "resume_checkpoint_refused" in report.problems[0]


@pytest.mark.parametrize("build,problem", [("", PROBLEM), ("build-1", ""), ("other", PROBLEM), ("build-1", "c" * 64)])
def test_missing_or_mismatched_execution_identity_refuses_bound_checkpoint(build, problem):
    cp = CheckpointReference("c", "b" * 64, "s", "build-1", PROBLEM)
    assert resume_refusal(cp, solver_build=build, problem_digest=problem)


@pytest.mark.parametrize("build,problem", [("", ""), ("", PROBLEM), ("build-1", "")])
def test_adoption_cannot_invent_missing_execution_context(build, problem):
    adopted, reason = adopt_checkpoint(CheckpointReference("new", "b" * 64), solver_id="s",
        state=AttemptState.CONVERGED, solver_build=build, problem_digest=problem)
    assert adopted is None and "missing_execution_build_or_problem" in reason


def test_known_producer_context_can_bind_a_new_checkpoint():
    cp, reason = adopt_checkpoint(CheckpointReference("new", "b" * 64), solver_id="s",
        state=AttemptState.CONVERGED, solver_build="build-1", problem_digest=PROBLEM)
    assert not reason and not resume_refusal(cp, solver_build="build-1", problem_digest=PROBLEM)


@pytest.mark.parametrize("problem", ["", "c" * 64])
def test_cross_solver_conversion_cannot_bypass_missing_or_different_problem(problem):
    cp = CheckpointReference("c", "b" * 64, "source", "source@1", PROBLEM)
    conversion = CheckpointConversion("map", "source", "source@1", "s", "build-1", "test declaration only")
    assert converted_resume_point(cp, solver_id="s", solver_build="build-1", conversions=(conversion,),
        accepts_converted=True, problem_digest=problem) == (None, None)


def test_cold_start_does_not_require_a_checkpoint_identity():
    backend = Backend()
    report = run_plan(SimulationPlan("p", ("s",)), {"s": backend})
    assert report.converged and backend.calls == 1


def test_build_switch_inside_execution_cannot_misbind_checkpoint_or_report_success():
    class Drifting(Backend):
        def run(self, **kwargs):
            self.calls += 1
            self.solver_build = "build-2"
            return BackendOutcome(AttemptState.CONVERGED, checkpoint=CheckpointReference("new", "b" * 64))

        def run_advanced(self, **kwargs):
            self.calls += 1
            self.solver_build = "build-2"
            return AdvancedBackendOutcome(AttemptState.CONVERGED, ResourceUsage(),
                RefinementDiagnostics(error_indicator=1e-4), checkpoint=CheckpointReference("new", "b" * 64))

    plan = SimulationPlan("p", ("s",), problem_digest=PROBLEM)
    backend = Drifting()
    report = run_plan(plan, {"s": backend})
    assert not report.converged and backend.calls == 1
    assert report.attempts[0].failure_code == "execution_build_drift_refused"
    backend = Drifting()
    report = run_adaptive_plan(plan, SimulationRequirements(ProblemKind.ODE),
        (SolverCapability("s", (ProblemKind.ODE,)),), {"s": backend},
        AdaptiveRefinementPolicy(target_error=1e-3, max_refinement_level=1))
    assert not report.successful and backend.calls == 1 and report.final_checkpoint is None
    assert report.attempts[0].checkpoint is None
