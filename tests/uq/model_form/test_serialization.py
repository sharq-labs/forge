from engcore.uq.model_form import *
from engcore.uq.model_form.serialization import model_form_from_dict,model_form_to_dict

def scope(context="b"*64,dataset="c"*64):
    return ModelFormScope("model","a"*64,context,dataset,"temperature","kelvin")

def test_model_form_v2_round_trip_preserves_scope_and_fail_closed_status():
    e=ModelFormEstimate("temperature","kelvin",ModelFormStatus.UNRESOLVED,None,("a","b"),(),None,"unknown",scope=scope())
    assert model_form_from_dict(model_form_to_dict(e))==e

def test_v1_payload_is_read_as_unscoped_and_cannot_gain_scope():
    payload={"schema":"model_form_uncertainty_estimate/1","quantity":"temperature","units":"kelvin",
             "status":"validated","half_width":1.0,"calibration_groups":["a","b"],
             "validation_groups":["v1","v2"],"empirical_holdout_coverage":1.0,"reason":"legacy"}
    restored=model_form_from_dict(payload)
    assert restored.scope is None
    assert assess_promotion(restored,ModelFormPolicy()).decision is PromotionDecision.REFUSED
