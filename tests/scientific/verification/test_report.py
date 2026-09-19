import pytest
from engcore.scientific.verification import *

def test_verified_report_cannot_hide_disagreement():
    with pytest.raises(ValueError):
        VerificationReport(VerificationDecision.VERIFIED,(RouteComparison("p","v",False),),(IndependenceEvidence(IndependenceLevel.EXTERNAL),))
