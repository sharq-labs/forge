from engcore.uq.model_form import *

def estimate(quantity="temperature"):
    return ModelFormEstimate(quantity,"kelvin",ModelFormStatus.VALIDATED,2.0,("c1","c2"),("v1","v2"),1.0,"ok")

def qualification(quantities=("temperature",),same=False):
    return ProducerQualification("producer","method","a"*64,("a"*64 if same else "b"*64),quantities)

def test_authority_requires_quantity_qualification():
    assert authorize_model_form(estimate(),qualification(("voltage",))).decision is AuthorityDecision.REFUSED

def test_authority_requires_independent_review_identity():
    assert authorize_model_form(estimate(),qualification(same=True)).decision is AuthorityDecision.REFUSED

def test_qualified_validated_estimate_can_be_authorized():
    assert authorize_model_form(estimate(),qualification()).decision is AuthorityDecision.AUTHORIZED
