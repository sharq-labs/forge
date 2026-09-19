import pytest
from engcore.uq.model_form import *

def scope(context="b"*64,dataset="c"*64):
    return ModelFormScope("model","a"*64,context,dataset,"temperature","kelvin")

def estimate(s=None,method=ModelFormEstimatorKind.CONSERVATIVE_MAX_EXCESS):
    return ModelFormEstimate("temperature","kelvin",ModelFormStatus.VALIDATED,2.0,("c1","c2"),("v1","v2"),1.0,"ok",method,s or scope())

def qualification(quantities=("temperature",),same_digest=False,reviewer="independent.reviewer",
                  estimators=(ModelFormEstimatorKind.CONSERVATIVE_MAX_EXCESS.value,)):
    return ProducerQualification("producer","method","a"*64,reviewer,
        ("a"*64 if same_digest else "b"*64),quantities,estimators)

def test_authority_requires_exact_target_scope():
    assert authorize_model_form(estimate(),qualification(),scope(context="d"*64)).decision is AuthorityDecision.REFUSED

def test_authority_requires_quantity_qualification():
    assert authorize_model_form(estimate(),qualification(("voltage",)),scope()).decision is AuthorityDecision.REFUSED

def test_authority_requires_independent_review_identity():
    with pytest.raises(ValueError,match="reviewer"):
        qualification(reviewer="producer")

def test_authority_requires_distinct_review_evidence():
    assert authorize_model_form(estimate(),qualification(same_digest=True),scope()).decision is AuthorityDecision.REFUSED

def test_authority_requires_estimator_qualification():
    e=estimate(method=ModelFormEstimatorKind.EMPIRICAL_QUANTILE_EXCESS)
    assert authorize_model_form(e,qualification(),scope()).decision is AuthorityDecision.REFUSED

def test_qualified_validated_scoped_estimate_can_be_authorized():
    assert authorize_model_form(estimate(),qualification(),scope()).decision is AuthorityDecision.AUTHORIZED
