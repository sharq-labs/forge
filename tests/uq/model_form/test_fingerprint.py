from engcore.uq.model_form import *

def test_model_form_fingerprint_is_stable():
    e=ModelFormEstimate(ModelFormStatus.VALIDATED,1,("b","a"),("v2","v1"),1.0,"ok")
    assert model_form_estimate_fingerprint(e)==model_form_estimate_fingerprint(e)
