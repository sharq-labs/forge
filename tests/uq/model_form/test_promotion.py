from engcore.uq.model_form import *

def test_unvalidated_estimate_cannot_be_promoted():
    e=ModelFormEstimate(ModelFormStatus.CALIBRATED_UNVALIDATED,1,("a","b"),(),None,"x")
    assert assess_promotion(e,ModelFormPolicy()).decision is PromotionDecision.REFUSED
