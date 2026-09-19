from engcore.uq.model_form import *

def scope(context="b"*64,dataset="c"*64):
    return ModelFormScope("model","a"*64,context,dataset,"temperature","kelvin")

def test_residual_inside_known_uncertainty_does_not_establish_zero_model_form():
    s=ModelFormStudy((
        ModelResidualObservation("a","a","temperature","kelvin",0.5,1,False),
        ModelResidualObservation("b","b","temperature","kelvin",0.5,1,False),
    ),scope=scope())
    assert evaluate_model_form_study(s).status is ModelFormStatus.UNRESOLVED
