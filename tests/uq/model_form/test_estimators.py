import pytest
from engcore.uq.model_form import *

def test_empirical_quantile_policy_requires_meaningful_calibration_population():
    with pytest.raises(ValueError,match="at least 10"):
        ModelFormPolicy(estimator=ModelFormEstimatorKind.EMPIRICAL_QUANTILE_EXCESS,
                        minimum_calibration_observations=5)

def test_empirical_quantile_estimator_uses_declared_nearest_rank():
    assert estimate_excess((1,2,3,4,5,6,7,8,9,10),ModelFormEstimatorKind.EMPIRICAL_QUANTILE_EXCESS,0.9)==9
