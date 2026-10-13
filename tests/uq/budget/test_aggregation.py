import pytest
from engcore.uq.budget import *

def test_independent_components_use_root_sum_square():
    r=aggregate_uncertainty((UncertaintyComponent("a",UncertaintySource.MEASUREMENT,3),UncertaintyComponent("b",UncertaintySource.NUMERICAL,4)))
    assert r.standard_uncertainty==pytest.approx(5)


def test_empty_budget_cannot_become_exact_zero():
    with pytest.raises(ValueError, match="missing uncertainty is not zero"):
        aggregate_uncertainty(())
    with pytest.raises(ValueError, match="missing uncertainty is not zero"):
        UncertaintyBudgetReport.build(())


def test_explicit_zero_component_is_still_representable():
    result = aggregate_uncertainty((UncertaintyComponent("exact", UncertaintySource.NUMERICAL, 0),))
    assert result.standard_uncertainty == 0
