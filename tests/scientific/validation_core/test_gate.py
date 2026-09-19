from engcore.scientific.validation_core import ValidationDecision, ValidationPipeline, StageResult, ValidationStage

def test_missing_required_stage_is_incomplete():
    report=ValidationPipeline().assess(StageResult(ValidationStage.CONTRACT, True))
    assert report.decision is ValidationDecision.INCOMPLETE
