import pytest
from engcore.uq.model_form import *

def item(i,g,held,unit="kelvin",quantity="temperature"):
    return ModelResidualObservation(i,g,quantity,unit,2,1,held)

def test_calibration_holdout_group_leakage_is_refused():
    with pytest.raises(ValueError,match="leak"):
        ModelFormStudy((item("a","g",False),item("b","g",True)))

def test_one_study_cannot_mix_quantities():
    with pytest.raises(ValueError,match="one model-form study"):
        ModelFormStudy((item("a","a",False),item("b","b",False,quantity="voltage")))

def test_one_study_cannot_mix_incompatible_dimensions():
    with pytest.raises(Exception):
        ModelFormStudy((item("a","a",False),item("b","b",False,unit="volt")))
