import pytest
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.validation_core import ValidationDecision, ValidationReport, StageResult, ValidationStage

def test_accepted_report_cannot_hide_failed_stage():
    with pytest.raises(InvalidScientificProblem):
        ValidationReport(ValidationDecision.ACCEPTED,(StageResult(ValidationStage.CONTRACT,False),))
