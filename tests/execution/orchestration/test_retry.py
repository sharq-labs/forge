from engcore.execution.orchestration import *

def test_failed_attempt_retries_only_inside_budget():
    a=SimulationAttempt("a",AttemptState.FAILED,0,"solver_error")
    assert decide_retry(a,1,ExecutionBudget(max_attempts=2)).decision is RetryDecision.RETRY
    assert decide_retry(a,2,ExecutionBudget(max_attempts=2)).decision is RetryDecision.STOP_BUDGET
