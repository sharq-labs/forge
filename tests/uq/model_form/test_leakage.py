import pytest
from engcore.uq.model_form import *

def test_calibration_holdout_group_leakage_is_refused():
    with pytest.raises(ValueError,match="leak"):
        ModelFormStudy((
            ModelResidualObservation("a","g",2,1,False),
            ModelResidualObservation("b","g",2,1,True),
        ))
