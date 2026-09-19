from engcore.uq.model_form import *

def obs(i,g,r,u,held,unit="kelvin"): return ModelResidualObservation(i,g,"temperature",unit,r,u,held)

def test_model_form_requires_independent_holdout_coverage():
    study=ModelFormStudy((
        obs("c1","c1",3,1,False),obs("c2","c2",4,1,False),
        obs("v1","v1",2,1,True),obs("v2","v2",2,1,True),
    ))
    result=evaluate_model_form_study(study)
    assert result.status is ModelFormStatus.VALIDATED
    assert result.quantity=="temperature"
    assert result.units=="kelvin"

def test_compatible_units_are_normalized_before_residual_comparison():
    study=ModelFormStudy((
        obs("c1","c1",3,1,False,"kelvin"),
        obs("c2","c2",4,1,False,"delta_degC"),
        obs("v1","v1",2,1,True,"kelvin"),
        obs("v2","v2",2,1,True,"delta_degC"),
    ))
    assert evaluate_model_form_study(study).status is ModelFormStatus.VALIDATED
