from engcore.scientific.verification import *

def test_disagreement_dominates_independence():
    c=(RouteComparison("p","v",False,2.0),)
    i=(IndependenceEvidence(IndependenceLevel.EXTERNAL),)
    assert adjudicate(c,i) is VerificationDecision.DISAGREEMENT
