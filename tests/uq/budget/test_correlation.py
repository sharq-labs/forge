import pytest
from engcore.uq.budget import *

def test_unknown_correlation_component_is_refused():
    with pytest.raises(ValueError):
        aggregate_uncertainty((UncertaintyComponent("a",UncertaintySource.MEASUREMENT,1),),(Correlation("a","b",0.5),))
