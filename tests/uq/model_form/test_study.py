from engcore.uq.model_form import *

def obs(i,g,r,u,held): return ModelResidualObservation(i,g,r,u,held)

def test_model_form_requires_independent_holdout_coverage():
    study=ModelFormStudy((
        obs("c1","c1",3,1,False),obs("c2","c2",4,1,False),
        obs("v1","v1",2,1,True),obs("v2","v2",2,1,True),
    ))
    result=evaluate_model_form_study(study)
    assert result.status is ModelFormStatus.VALIDATED
