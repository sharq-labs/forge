import pytest
from engcore.uq.budget import *

def test_independent_components_use_root_sum_square():
    r=aggregate_uncertainty((UncertaintyComponent("a",UncertaintySource.MEASUREMENT,3),UncertaintyComponent("b",UncertaintySource.NUMERICAL,4)))
    assert r.standard_uncertainty==pytest.approx(5)
