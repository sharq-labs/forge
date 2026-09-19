import pytest
from engcore.scientific.verification import *

def test_verification_report_cannot_hide_a_decision_its_contents_do_not_derive():
    with pytest.raises(ValueError):
        VerificationReport(VerificationDecision.VERIFIED,(RouteComparison("p","v",False),),(IndependenceEvidence("p","v",IndependenceLevel.EXTERNAL),))
