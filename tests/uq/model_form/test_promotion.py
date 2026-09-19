from engcore.uq.model_form import *

def scope(context="b"*64,dataset="c"*64):
    return ModelFormScope("model","a"*64,context,dataset,"temperature","kelvin")

def test_unvalidated_estimate_cannot_be_promoted():
    e=ModelFormEstimate("temperature","kelvin",ModelFormStatus.CALIBRATED_UNVALIDATED,
        1,("a","b"),("v1","v2"),1.0,"x",scope=scope())
    report=assess_promotion(e,ModelFormPolicy())
    assert report.decision is PromotionDecision.REFUSED
    assert report.reasons == ("estimate status is calibrated_unvalidated, not validated",)

def test_even_validated_unscoped_estimate_is_not_promotable():
    e=ModelFormEstimate("temperature","kelvin",ModelFormStatus.VALIDATED,1,("a","b"),("v1","v2"),1.0,"x")
    report=assess_promotion(e,ModelFormPolicy())
    assert report.decision is PromotionDecision.REFUSED
    assert any("scope" in reason for reason in report.reasons)
