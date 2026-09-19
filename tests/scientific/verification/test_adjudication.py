from engcore.scientific.verification import *

def test_agreement_without_independence_is_not_verified():
    c=(RouteComparison("p","v",True,0.0),)
    i=(IndependenceEvidence("p","v",IndependenceLevel.PARTIAL,("shared_model",)),)
    assert adjudicate(c,i) is VerificationDecision.INSUFFICIENT_INDEPENDENCE
