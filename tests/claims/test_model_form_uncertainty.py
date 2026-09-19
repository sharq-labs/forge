import pytest
from engcore.claims.model_form_uncertainty import ModelFormAuthorityError,promote_model_form_interval
from engcore.scientific.results.uncertainty import UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.model_form import *

def scope(context="b"*64):
    return ModelFormScope("model","a"*64,context,"c"*64,"temperature","kelvin")

def estimate(status=ModelFormStatus.VALIDATED,s=None):
    return ModelFormEstimate("temperature","kelvin",status,2.0,("c1","c2"),("v1","v2"),
        1.0 if status is ModelFormStatus.VALIDATED else None,"test",scope=s or scope())

def qualification():
    return ProducerQualification("reviewed.producer","interval.v1","a"*64,
        "independent.reviewer","b"*64,("temperature",))

def test_authorized_model_form_produces_explicit_interval_source():
    s=scope()
    record=promote_model_form_interval(estimate(s=s),qualification(),Quantity(300,"kelvin"),target_scope=s)
    assert record.kind is UncertaintyKind.INTERVAL
    assert record.source_kind is UncertaintySource.MODEL_FORM
    assert record.lower.magnitude_in("kelvin")==pytest.approx(298)
    assert record.upper.magnitude_in("kelvin")==pytest.approx(302)
    assert s.digest in record.notes

def test_unvalidated_model_form_cannot_cross_authority_boundary():
    s=scope()
    with pytest.raises(ModelFormAuthorityError):
        promote_model_form_interval(estimate(ModelFormStatus.CALIBRATED_UNVALIDATED,s),qualification(),
                                    Quantity(300,"kelvin"),target_scope=s)

def test_scoped_model_form_cannot_be_reused_in_another_operating_context():
    with pytest.raises(ModelFormAuthorityError,match="scope"):
        promote_model_form_interval(estimate(),qualification(),Quantity(300,"kelvin"),
                                    target_scope=scope(context="d"*64))
