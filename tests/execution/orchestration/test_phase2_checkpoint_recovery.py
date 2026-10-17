"""Phase 2 BR10 -- checkpoints are bound to a solver BUILD and a PROBLEM; portability needs a qualified conversion.

NOT RUN (Phase 2 build phase): docs/work/DEFERRED_VALIDATION.md, DV-54, DV-55.
"""

import pytest

from engcore.data import InMemoryBulkStore
from engcore.execution.orchestration import (
    AdaptiveRefinementPolicy, AdvancedBackendOutcome, AdvancedStopReason, AttemptState, BackendOutcome,
    CheckpointReference, ExecutionBudget, ProblemKind, RefinementDiagnostics, ResourceUsage, SimulationPlan,
    SimulationRequirements, SolverCapability, run_adaptive_plan, run_plan,
)
from engcore.execution.orchestration.checkpoint import (
    CheckpointConversion, adopt_checkpoint, converted_resume_point, resume_point_for, resume_refusal,
)

PROBLEM = "1" * 64
OTHER_PROBLEM = "2" * 64


class Backend:
    def __init__(self, solver_id, outcomes, build="", accepts_converted=False):
        self.solver_id = solver_id
        self.solver_build = build
        self.accepts_converted_checkpoints = accepts_converted
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


def _adaptive(a, b, *, checkpoint=None, conversions=(), problem=PROBLEM):
    return run_adaptive_plan(
        SimulationPlan("q", ("a", "b"), ExecutionBudget(max_attempts=6, max_refinements=3), problem_digest=problem),
        SimulationRequirements(ProblemKind.ODE),
        (SolverCapability("a", (ProblemKind.ODE,), preference=2), SolverCapability("b", (ProblemKind.ODE,), preference=1)),
        {"a": a, "b": b}, AdaptiveRefinementPolicy(target_error=1e-3, max_refinement_level=3),
        checkpoint=checkpoint, conversions=conversions,
    )


# ---- the record ---------------------------------------------------------------------------------------------


def test_a_problem_digest_must_be_sha256():
    with pytest.raises(ValueError):
        CheckpointReference("c", "a" * 64, "a", "build-1", "not-a-digest")
    with pytest.raises(ValueError):
        SimulationPlan("p", ("a",), problem_digest="nope")


def test_adoption_binds_the_build_and_problem_that_produced_the_checkpoint():
    adopted, problem = adopt_checkpoint(CheckpointReference("c", "a" * 64), solver_id="a", state=AttemptState.CONVERGED,
                                        solver_build="a@1", problem_digest=PROBLEM)
    assert problem == "" and (adopted.solver_id, adopted.solver_build, adopted.problem_digest) == ("a", "a@1", PROBLEM)


@pytest.mark.parametrize("checkpoint, reason", [
    (CheckpointReference("c", "a" * 64, "a", "a@0"), "build"),
    (CheckpointReference("c", "a" * 64, "a", "", OTHER_PROBLEM), "another_problem"),
])
def test_adoption_refuses_another_build_or_problem(checkpoint, reason):
    adopted, problem = adopt_checkpoint(checkpoint, solver_id="a", state=AttemptState.CONVERGED,
                                        solver_build="a@1", problem_digest=PROBLEM)
    assert adopted is None and reason in problem


@pytest.mark.parametrize("state", [AttemptState.FAILED, AttemptState.DIVERGED])
def test_a_failed_or_diverged_attempt_never_supplies_a_checkpoint(state):
    adopted, problem = adopt_checkpoint(CheckpointReference("c", "a" * 64, "a"), solver_id="a", state=state)
    assert adopted is None and "discarded" in problem


@pytest.mark.parametrize("kwargs, fragment", [
    ({"solver_build": ""}, "states no build"),
    ({"solver_build": "a@2"}, "not 'a@2'"),
    ({"solver_build": "a@1", "problem_digest": ""}, "plan states none"),
    ({"solver_build": "a@1", "problem_digest": OTHER_PROBLEM}, "another problem"),
])
def test_resume_is_refused_on_build_drift_another_problem_or_ambiguity(kwargs, fragment):
    checkpoint = CheckpointReference("c", "a" * 64, "a", "a@1", PROBLEM)
    assert fragment in resume_refusal(checkpoint, **kwargs)
    assert resume_point_for(checkpoint, "a", **kwargs) is None


def test_the_same_build_and_problem_resume():
    checkpoint = CheckpointReference("c", "a" * 64, "a", "a@1", PROBLEM)
    assert resume_point_for(checkpoint, "a", solver_build="a@1", problem_digest=PROBLEM) is checkpoint


# ---- runners ---------------------------------------------------------------------------------------------------


def test_the_same_build_resumes_and_a_fallback_solver_cold_starts_on_record():
    # a converges but must refine (error 1.0 > 1e-3), resumes its own adopted checkpoint, then fails;
    # b may not continue a's state and starts cold from the admitted problem
    a = Backend("a", [_adv(AttemptState.CONVERGED, 1.0, checkpoint=CheckpointReference("a:cp", "a" * 64)),
                      _adv(AttemptState.FAILED, failure_code="diverged")], build="a@1")
    b = Backend("b", [_adv(AttemptState.CONVERGED, 1e-4)], build="b@1")
    report = _adaptive(a, b)
    assert report.successful
    resumed = a.received[1]
    assert (resumed.solver_id, resumed.solver_build, resumed.problem_digest) == ("a", "a@1", PROBLEM)
    assert b.received == [None]
    assert "b:cold_start_from_admitted_problem" in report.problems
    assert report.final_checkpoint is None  # b returned none; a's state is never presented as b's result


def test_a_caller_checkpoint_of_another_build_is_refused_before_anything_runs():
    a = Backend("a", [_adv(AttemptState.CONVERGED, 1e-4)], build="a@2")
    b = Backend("b", [], build="b@1")
    report = _adaptive(a, b, checkpoint=CheckpointReference("a:cp", "a" * 64, "a", "a@1", PROBLEM))
    assert report.stop_reason is AdvancedStopReason.NO_CAPABLE_SOLVER
    assert a.received == [] and "resume_checkpoint_refused" in report.problems[0]


def test_a_caller_checkpoint_of_another_problem_is_refused_by_the_basic_runner():
    a = Backend("a", [BackendOutcome(AttemptState.CONVERGED)], build="a@1")
    report = run_plan(SimulationPlan("p", ("a",), problem_digest=OTHER_PROBLEM), {"a": a},
                      checkpoint=CheckpointReference("a:cp", "a" * 64, "a", "a@1", PROBLEM))
    assert a.received == [] and not report.converged
    assert "another problem" in report.attempts[0].failure_code


def test_build_drift_between_attempts_is_refused():
    class Drifting(Backend):
        def run_advanced(self, **kw):
            outcome = super().run_advanced(**kw)
            self.solver_build = "a@2"  # the backend reloaded a different build
            return outcome

    a = Drifting("a", [_adv(AttemptState.CONVERGED, 1.0), _adv(AttemptState.CONVERGED, 1e-4)], build="a@1")
    b = Backend("b", [_adv(AttemptState.CONVERGED, 1e-4)], build="b@1")
    report = _adaptive(a, b)
    assert "a:build_drift_a@1_to_a@2_refused" in report.problems
    assert len(a.received) == 1


def test_a_qualified_conversion_carries_state_only_into_a_backend_that_accepts_it():
    checkpoint = CheckpointReference("a:cp", "a" * 64, "a", "a@1", PROBLEM)
    conversion = CheckpointConversion("a-to-b", "a", "a@1", "b", "b@1", "same state variables, verified mapping")
    assert converted_resume_point(checkpoint, solver_id="b", solver_build="b@1", conversions=(conversion,),
                                  accepts_converted=True) == (checkpoint, conversion)
    assert converted_resume_point(checkpoint, solver_id="b", solver_build="b@1", conversions=(conversion,),
                                  accepts_converted=False) == (None, None)
    assert converted_resume_point(checkpoint, solver_id="b", solver_build="b@2", conversions=(conversion,),
                                  accepts_converted=True) == (None, None)
    assert converted_resume_point(checkpoint, solver_id="b", solver_build="b@1", conversions=(),
                                  accepts_converted=True) == (None, None)


def test_a_conversion_needs_both_builds_and_a_qualification():
    with pytest.raises(ValueError):
        CheckpointConversion("x", "a", "", "b", "b@1", "basis")
    with pytest.raises(ValueError):
        CheckpointConversion("x", "a", "a@1", "b", "b@1", "")
    with pytest.raises(ValueError):
        CheckpointConversion("x", "a", "a@1", "a", "a@1", "basis")


# ---- provider participants -------------------------------------------------------------------------------------


def _provider_participant(build=None):
    from types import SimpleNamespace

    from engcore.coupling.adapters import provider_participant, scalar_port
    from engcore.scientific.multiphysics import ParticipantSpec
    from engcore.scientific.units.quantity import Quantity

    spec = ParticipantSpec("cell", "m", "1", "r", "1", "s", "1", "a", "1", (scalar_port("heat", "output", "power", "W"),),
                           transient=True, checkpointable=True, deterministic_restore=True)
    identity = SimpleNamespace(provider_id="prov", provider_version="1.0", provider_digest="d" * 64,
                               adapter_id="adapter", adapter_version="1")
    current = {"identity": identity}

    def solve(inputs, start, end, uq, state):
        return SimpleNamespace(identity=current["identity"], succeeded=True, reason="", execution_identity="e", digest="r"), \
            {"heat": Quantity(1.0, "W")}

    participant = provider_participant(spec, solve=solve, initial_outputs=lambda: {"heat": Quantity(0.0, "W")},
                                       store=InMemoryBulkStore(), expected_build=build)
    return participant, current, identity


def _advance(participant):
    from engcore.execution.multiphysics import AdvanceRequest
    from engcore.scientific.units.quantity import Quantity

    return participant.advance(AdvanceRequest(Quantity(0, "s"), Quantity(1, "s"), {}, {}))


def test_a_provider_build_drift_inside_a_run_is_refused():
    from types import SimpleNamespace

    from engcore.coupling.adapters import CouplingRefusal

    participant, current, identity = _provider_participant()
    _advance(participant)
    current["identity"] = SimpleNamespace(**{**vars(identity), "provider_version": "2.0"})
    with pytest.raises(CouplingRefusal, match="build drift"):
        _advance(participant)


def test_an_execution_of_another_build_than_the_admitted_one_is_refused():
    from engcore.coupling.adapters import CouplingRefusal

    admitted = {"provider_id": "prov", "provider_version": "0.9", "provider_digest": "d" * 64,
                "adapter_id": "adapter", "adapter_version": "1"}
    participant, _, _ = _provider_participant(build=admitted)
    with pytest.raises(CouplingRefusal, match="build drift"):
        _advance(participant)


def test_a_corrupted_checkpoint_token_is_refused():
    from engcore.coupling.adapters import CouplingRefusal
    from engcore.execution.multiphysics.participant import RuntimeCheckpoint
    from engcore.execution.multiphysics import InitialStateValue
    from engcore.scientific.results.uncertainty import Uncertainty
    from engcore.scientific.units.quantity import Quantity

    participant, _, _ = _provider_participant()
    _advance(participant)
    checkpoint = participant.checkpoint(Quantity(1, "s"))
    forged = RuntimeCheckpoint(checkpoint.record, {"soc": InitialStateValue("soc", Quantity(0.5, "dimensionless"),
                                                                           Uncertainty.unknown("forged"))})
    with pytest.raises(CouplingRefusal, match="does not hold the state"):
        participant.restore(forged)
    participant.restore(checkpoint)  # its own, intact checkpoint restores


def test_a_checkpoint_of_another_build_is_refused_on_restore():
    from types import SimpleNamespace

    from engcore.coupling.adapters import CouplingRefusal
    from engcore.scientific.units.quantity import Quantity

    first, _, identity = _provider_participant()
    _advance(first)
    checkpoint = first.checkpoint(Quantity(1, "s"))
    second, current, _ = _provider_participant()
    current["identity"] = SimpleNamespace(**{**vars(identity), "provider_digest": "e" * 64})
    _advance(second)
    with pytest.raises(CouplingRefusal, match="another provider build"):
        second.restore(checkpoint)
