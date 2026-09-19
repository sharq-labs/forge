import pytest
from engcore.scientific.verification import *
from engcore.scientific.verification.serialization import verification_from_dict,verification_to_dict

def test_verification_round_trip_rederives_decision():
    r=VerificationReport(VerificationDecision.INSUFFICIENT_INDEPENDENCE,(RouteComparison("p","v",True),),(IndependenceEvidence(IndependenceLevel.PARTIAL,("shared",)),))
    p=verification_to_dict(r);p["decision"]="verified"
    with pytest.raises(ValueError,match="does not match"):
        verification_from_dict(p)
