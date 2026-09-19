from engcore.uq.model_form import *
from engcore.uq.model_form.serialization import model_form_from_dict,model_form_to_dict

def test_model_form_round_trip_preserves_fail_closed_status():
    e=ModelFormEstimate(ModelFormStatus.UNRESOLVED,None,("a","b"),(),None,"unknown")
    assert model_form_from_dict(model_form_to_dict(e))==e
