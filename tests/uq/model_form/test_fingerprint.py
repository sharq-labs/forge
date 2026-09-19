from engcore.uq.model_form import *

def scope(context="b"*64,dataset="c"*64):
    return ModelFormScope("model","a"*64,context,dataset,"temperature","kelvin")

def estimate(s):
    return ModelFormEstimate("temperature","kelvin",ModelFormStatus.VALIDATED,1,("b","a"),("v2","v1"),1.0,"ok",scope=s)

def test_model_form_fingerprint_binds_model_context_and_dataset_scope():
    base=estimate(scope())
    changed=estimate(scope(context="d"*64))
    assert model_form_estimate_fingerprint(base)!=model_form_estimate_fingerprint(changed)
