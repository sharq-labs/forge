import pytest
from engcore.uq.budget import *

def test_independent_components_use_root_sum_square():
    r=aggregate_uncertainty((UncertaintyComponent("a",UncertaintySource.MEASUREMENT,3),UncertaintyComponent("b",UncertaintySource.NUMERICAL,4)),
                            (Correlation("a","b",0.0),))
    assert r.standard_uncertainty==pytest.approx(5)


def test_an_empty_budget_is_unknown_not_zero():
    with pytest.raises(ValueError,match="UNKNOWN, not zero"):
        aggregate_uncertainty(())
    with pytest.raises(ValueError,match="UNKNOWN, not zero"):
        UncertaintyBudgetReport.build(())


def test_an_undeclared_pair_is_not_read_as_independent():
    a=UncertaintyComponent("a",UncertaintySource.MEASUREMENT,3)
    b=UncertaintyComponent("b",UncertaintySource.NUMERICAL,4)
    c=UncertaintyComponent("c",UncertaintySource.NUMERICAL,1)
    with pytest.raises(ValueError,match=r"undeclared for component pairs \[\('a', 'b'\)\]"):
        aggregate_uncertainty((a,b))
    with pytest.raises(ValueError,match="undeclared"):
        aggregate_uncertainty((a,b,c),(Correlation("a","b",0.0),Correlation("a","c",0.0)))
    full=aggregate_uncertainty((a,b),(Correlation("a","b",1.0),))
    assert full.standard_uncertainty==pytest.approx(7)  # a declared correlation is used as declared


def test_a_single_component_needs_no_correlation():
    assert aggregate_uncertainty((UncertaintyComponent("a",UncertaintySource.MEASUREMENT,2),)).standard_uncertainty==2


def test_explicit_zero_component_is_still_representable():
    result = aggregate_uncertainty((UncertaintyComponent("exact", UncertaintySource.NUMERICAL, 0),))
    assert result.standard_uncertainty == 0
