from engcore.execution.orchestration import *

def test_report_exposes_convergence_without_inventing_it():
    r=OrchestrationReport((SimulationAttempt("a",AttemptState.FAILED,0,"x"),))
    assert not r.converged
