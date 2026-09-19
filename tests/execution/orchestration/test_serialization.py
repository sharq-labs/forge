import pytest
from engcore.execution.orchestration import *
from engcore.execution.orchestration.serialization import orchestration_from_dict,orchestration_to_dict

def test_orchestration_round_trip_rederives_convergence():
    r=OrchestrationReport((SimulationAttempt("a",AttemptState.FAILED,0,"x"),))
    p=orchestration_to_dict(r);p["converged"]=True
    with pytest.raises(ValueError,match="convergence"):
        orchestration_from_dict(p)
