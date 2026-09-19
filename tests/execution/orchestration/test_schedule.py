from engcore.execution.orchestration import *

def test_schedule_is_deterministic_and_budget_limited():
    p=SimulationPlan("p",("s1","s2","s3"),ExecutionBudget(max_attempts=2))
    assert schedule_attempts(p)==("s1","s2")
