import pytest
from engcore.execution.orchestration import *

def test_failed_attempt_requires_failure_code():
    with pytest.raises(ValueError):
        SimulationAttempt("a",AttemptState.FAILED)
