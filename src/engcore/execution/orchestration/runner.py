from __future__ import annotations

from collections.abc import Mapping

from .attempt import AttemptState, SimulationAttempt
from .backend import BackendOutcome, SimulationBackend
from .checkpoint import CheckpointReference
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
    attempts=[]
    current_checkpoint=checkpoint
    for index,solver_id in enumerate(schedule_attempts(plan),start=1):
        backend=backends.get(solver_id)
        attempt_id=f"{plan.plan_id}:{index}:{solver_id}"
        if backend is None:
            attempts.append(SimulationAttempt(attempt_id,AttemptState.FAILED,index-1,"backend_missing"))
            if not policy.allow_solver_fallback:
                break
            continue
        try:
            outcome=backend.run(
                attempt_id=attempt_id,
                refinement_level=index-1,
                deterministic_seed=plan.deterministic_seed,
                checkpoint=current_checkpoint,
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
        if outcome.checkpoint is not None:
            current_checkpoint=outcome.checkpoint
        if outcome.state is AttemptState.CONVERGED:
            break
        if not policy.allow_solver_fallback:
            break
    return OrchestrationReport(tuple(attempts))
