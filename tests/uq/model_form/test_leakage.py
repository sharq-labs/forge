import pytest
from engcore.uq.model_form import *

def scope(context="b"*64,dataset="c"*64):
    return ModelFormScope("model","a"*64,context,dataset,"temperature","kelvin")

def item(i,g,held,unit="kelvin",quantity="temperature"):
    return ModelResidualObservation(i,g,quantity,unit,2,1,held)

def test_calibration_holdout_group_leakage_is_refused():
    with pytest.raises(ValueError,match="leak"):
        ModelFormStudy((item("a","g",False),item("b","g",True)),scope=scope())

def test_one_study_cannot_mix_quantities():
    with pytest.raises(ValueError,match="one model-form study"):
        ModelFormStudy((item("a","a",False),item("b","b",False,quantity="voltage")),scope=scope())

def test_one_study_cannot_mix_incompatible_dimensions():
    with pytest.raises(Exception):
        ModelFormStudy((item("a","a",False),item("b","b",False,unit="volt")),scope=scope())

def test_study_scope_must_name_the_same_quantity():
    wrong=ModelFormScope("model","a"*64,"b"*64,"c"*64,"voltage","kelvin")
    with pytest.raises(ValueError,match="scope"):
        ModelFormStudy((item("a","a",False),item("b","b",False)),scope=wrong)
