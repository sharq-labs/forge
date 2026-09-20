import math

import pytest

from engcore.scientific.numerics import (
    NumericHealth,
    NumericHealthStatus,
    assess_numeric_values,
)


@pytest.mark.parametrize("threshold", [0.0, -1.0, math.inf, math.nan])
def test_numeric_health_refuses_an_unusable_extreme_threshold(threshold):
    with pytest.raises(ValueError, match="finite and positive"):
        assess_numeric_values((1.0,), extreme_magnitude=threshold)


def test_numeric_health_refuses_boolean_values():
    with pytest.raises(ValueError, match="real numbers"):
        assess_numeric_values((True,))


def test_numeric_health_record_cannot_call_nonfinite_values_healthy():
    with pytest.raises(ValueError, match="require INVALID"):
        NumericHealth(NumericHealthStatus.HEALTHY, nonfinite_count=1)


def test_numeric_health_record_cannot_call_extreme_values_healthy():
    with pytest.raises(ValueError, match="cannot be reported as HEALTHY"):
        NumericHealth(NumericHealthStatus.HEALTHY, extreme_magnitude_count=1)


def test_assessment_classifies_nonfinite_and_extreme_values_fail_closed():
    invalid = assess_numeric_values((1.0, math.nan))
    degraded = assess_numeric_values((1.0, 1.0e10), extreme_magnitude=1.0e9)

    assert invalid.status is NumericHealthStatus.INVALID
    assert invalid.nonfinite_count == 1
    assert degraded.status is NumericHealthStatus.DEGRADED
    assert degraded.extreme_magnitude_count == 1
