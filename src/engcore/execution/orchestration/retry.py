from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .attempt import AttemptState, SimulationAttempt
from .budget import ExecutionBudget

class RetryDecision(str,Enum):
    STOP_SUCCESS="stop_success"
    RETRY="retry"
    STOP_BUDGET="stop_budget"
    STOP_TERMINAL="stop_terminal"

@dataclass(frozen=True)
class RetryAssessment:
    decision:RetryDecision
    reason:str

def decide_retry(attempt:SimulationAttempt,attempt_count:int,budget:ExecutionBudget)->RetryAssessment:
    if attempt.state is AttemptState.CONVERGED:
        return RetryAssessment(RetryDecision.STOP_SUCCESS,"attempt converged")
    if attempt.state in {AttemptState.CANCELLED}:
        return RetryAssessment(RetryDecision.STOP_TERMINAL,"attempt was cancelled")
    if attempt_count>=budget.max_attempts:
        return RetryAssessment(RetryDecision.STOP_BUDGET,"attempt budget exhausted")
    return RetryAssessment(RetryDecision.RETRY,"attempt may be retried within budget")
