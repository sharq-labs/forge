from engcore.scientific.assurance_flow import decide_assurance, AssuranceDecision
from engcore.scientific.validation_core import *
from engcore.scientific.verification import *
from engcore.scientific.certification_core import CertificationVerification

def test_trust_requires_all_three_layers_green():
    validation=ValidationReport(ValidationDecision.ACCEPTED,(StageResult(ValidationStage.CONTRACT,True),))
    verification=VerificationReport(VerificationDecision.VERIFIED,(RouteComparison("p","v",True),),(IndependenceEvidence("p","v",IndependenceLevel.EXTERNAL),))
    assert decide_assurance(validation,verification,CertificationVerification(True,())) is AssuranceDecision.TRUSTED
    assert decide_assurance(validation,verification,CertificationVerification(False,("bad",))) is AssuranceDecision.REFUSED
