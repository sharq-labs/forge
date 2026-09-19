from engcore.execution.orchestration import *

class Backend:
    def __init__(self,solver_id,state,failure_code=""):
        self.solver_id=solver_id;self.state=state;self.failure_code=failure_code
    def run(self,**kwargs):
        return BackendOutcome(self.state,self.failure_code)

def test_runner_falls_back_deterministically_until_converged():
    plan=SimulationPlan("p",("bad","good"),ExecutionBudget(max_attempts=2),deterministic_seed=7)
    report=run_plan(plan,{
        "bad":Backend("bad",AttemptState.FAILED,"no_convergence"),
        "good":Backend("good",AttemptState.CONVERGED),
    })
    assert [a.state for a in report.attempts]==[AttemptState.FAILED,AttemptState.CONVERGED]
    assert report.converged

def test_runner_records_missing_backend_as_explicit_failure():
    plan=SimulationPlan("p",("missing",),ExecutionBudget(max_attempts=1))
    report=run_plan(plan,{})
    assert report.attempts[0].failure_code=="backend_missing"
