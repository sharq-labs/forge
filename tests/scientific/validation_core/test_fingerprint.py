from engcore.scientific.validation_core import *

def test_validation_report_fingerprint_is_stable():
    report=ValidationReport(ValidationDecision.ACCEPTED,(StageResult(ValidationStage.CONTRACT,True),))
    assert validation_report_fingerprint(report)==validation_report_fingerprint(ValidationReport.from_dict(report.to_dict()))
