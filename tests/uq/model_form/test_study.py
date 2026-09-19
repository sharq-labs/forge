from engcore.uq.model_form import *

def scope(context="b"*64,dataset="c"*64):
    return ModelFormScope("model","a"*64,context,dataset,"temperature","kelvin")

def obs(i,g,r,u,held,unit="kelvin"):
    return ModelResidualObservation(i,g,"temperature",unit,r,u,held)

def test_model_form_requires_independent_holdout_coverage_and_scope():
    study=ModelFormStudy((
        obs("c1","c1",3,1,False),obs("c2","c2",4,1,False),
        obs("v1","v1",2,1,True),obs("v2","v2",2,1,True),
    ),scope=scope())
    result=evaluate_model_form_study(study)
    assert result.status is ModelFormStatus.VALIDATED
    assert result.scope==scope()

def test_compatible_units_are_normalized_before_residual_comparison():
    study=ModelFormStudy((
        obs("c1","c1",3,1,False,"kelvin"),
        obs("c2","c2",4,1,False,"delta_degC"),
        obs("v1","v1",2,1,True,"kelvin"),
        obs("v2","v2",2,1,True,"delta_degC"),
    ),scope=scope())
    assert evaluate_model_form_study(study).status is ModelFormStatus.VALIDATED
