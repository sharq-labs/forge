import pytest

from engcore.claims.model_form_uncertainty import ModelFormAuthorityError, promote_model_form_interval
from engcore.scientific.results.uncertainty import UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.model_form import *


def estimate(status=ModelFormStatus.VALIDATED):
    return ModelFormEstimate("temperature","kelvin",status,2.0,("c1","c2"),("v1","v2"),1.0 if status is ModelFormStatus.VALIDATED else None,"test")


def qualification():
    return ProducerQualification("reviewed.producer","interval.v1","a"*64,"b"*64,("temperature",))


def test_authorized_model_form_produces_explicit_interval_source():
    record=promote_model_form_interval(estimate(),qualification(),Quantity(300,"kelvin"))
    assert record.kind is UncertaintyKind.INTERVAL
    assert record.source_kind is UncertaintySource.MODEL_FORM
    assert record.lower.magnitude_in("kelvin")==pytest.approx(298)
    assert record.upper.magnitude_in("kelvin")==pytest.approx(302)


def test_unvalidated_model_form_cannot_cross_authority_boundary():
    with pytest.raises(ModelFormAuthorityError):
        promote_model_form_interval(estimate(ModelFormStatus.CALIBRATED_UNVALIDATED),qualification(),Quantity(300,"kelvin"))
