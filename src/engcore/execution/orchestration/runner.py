from __future__ import annotations

from collections.abc import Mapping

from .attempt import AttemptState, SimulationAttempt
from .backend import BackendOutcome, SimulationBackend
from .checkpoint import CheckpointReference, adopt_checkpoint, resume_owner, resume_point_for, resume_refusal
from .plan import SimulationPlan
from .policy import OrchestrationPolicy
from .report import OrchestrationReport
from .scheduler import schedule_attempts


def run_plan(
    plan:SimulationPlan,
    backends:Mapping[str,SimulationBackend],
    *,
    policy:OrchestrationPolicy=OrchestrationPolicy(),
    checkpoint:CheckpointReference|None=None,
)->OrchestrationReport:
    owner=resume_owner(checkpoint)
    if checkpoint is not None:
        # Phase 2 BR10: a caller's checkpoint resumes only the build and problem it was produced for
        refused=resume_refusal(checkpoint,solver_build=str(getattr(backends.get(owner),"solver_build","")),
                               problem_digest=plan.problem_digest)
        if refused:
            return OrchestrationReport((SimulationAttempt(f"{plan.plan_id}:0:{owner}",AttemptState.FAILED,0,
                                                          f"resume_checkpoint_refused: {refused}"),))
    attempts=[]
    current_checkpoint=checkpoint
    for index,solver_id in enumerate(schedule_attempts(plan),start=1):
        backend=backends.get(solver_id)
        attempt_id=f"{plan.plan_id}:{index}:{solver_id}"
        if owner is not None and solver_id!=owner:
            # a resumed run continues ONE solver's state; another solver cannot continue it
            attempts.append(SimulationAttempt(attempt_id,AttemptState.FAILED,index-1,f"resume_checkpoint_belongs_to_{owner}"))
            if not policy.allow_solver_fallback:
                break
            continue
        if backend is None:
            attempts.append(SimulationAttempt(attempt_id,AttemptState.FAILED,index-1,"backend_missing"))
            if not policy.allow_solver_fallback:
                break
            continue
        if str(getattr(backend,"solver_id","")).strip()!=solver_id:
            # a backend registered under another solver's name would receive that solver's state
            attempts.append(SimulationAttempt(attempt_id,AttemptState.FAILED,index-1,"backend_solver_identity_mismatch"))
            if not policy.allow_solver_fallback:
                break
            continue
        try:
            # a checkpoint is solver state: only the solver that produced it may resume from it
            build=str(getattr(backend,"solver_build","")).strip()
            outcome=backend.run(
                attempt_id=attempt_id,
                refinement_level=index-1,
                deterministic_seed=plan.deterministic_seed,
                checkpoint=resume_point_for(current_checkpoint,solver_id,solver_build=build,
                                            problem_digest=plan.problem_digest),
            )
        except Exception as exc:
            attempts.append(
                SimulationAttempt(
                    attempt_id,
                    AttemptState.FAILED,
                    index-1,
                    f"backend_exception:{type(exc).__name__}",
                )
            )
            if not policy.allow_solver_fallback:
                break
            continue
        if not isinstance(outcome,BackendOutcome):
            raise TypeError("simulation backend must return BackendOutcome")
        attempts.append(
            SimulationAttempt(
                attempt_id,
                outcome.state,
                index-1,
                outcome.failure_code,
            )
        )
        # OrchestrationReport has no problems channel (a schema change); a refused checkpoint is simply never
        # adopted, and in run_plan each solver runs once, so it could not have been resumed by anyone
        adopted,_problem=adopt_checkpoint(outcome.checkpoint,solver_id=solver_id,state=outcome.state,
                                          solver_build=str(getattr(backend,"solver_build","")).strip(),
                                          problem_digest=plan.problem_digest)
        if adopted is not None:
            current_checkpoint=adopted
        if outcome.state is AttemptState.CONVERGED:
            break
        if not policy.allow_solver_fallback:
            break
    return OrchestrationReport(tuple(attempts))
