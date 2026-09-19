from engcore.scientific.verification import *

def test_independence_evidence_for_another_route_pair_does_not_verify_this_comparison():
    comparisons=(RouteComparison("p","v",True,0.0),)
    independence=(IndependenceEvidence("p","other",IndependenceLevel.EXTERNAL),)
    assert adjudicate(comparisons,independence) is VerificationDecision.INSUFFICIENT_INDEPENDENCE

def test_every_agreeing_route_requires_its_own_independence_evidence():
    comparisons=(RouteComparison("p","v1",True,0.0),RouteComparison("p","v2",True,0.0))
    independence=(IndependenceEvidence("p","v1",IndependenceLevel.EXTERNAL),)
    assert adjudicate(comparisons,independence) is VerificationDecision.INSUFFICIENT_INDEPENDENCE
