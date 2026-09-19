import pytest
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.budget import Correlation
from engcore.uq.combined import *

def contribution(cid,source,u,lineage):
    return UncertaintyContribution(cid,
        Uncertainty(kind=UncertaintyKind.STANDARD,standard_uncertainty=Quantity(u,"kelvin"),
                    method="test",source_kind=source),
        cid[0]*64,(lineage*64,),"independent-"+cid)

def test_rss_requires_explicit_pair_correlation_by_default():
    items=(contribution("a1",UncertaintySource.MEASUREMENT,3,"1"),
           contribution("b1",UncertaintySource.PARAMETER,4,"2"))
    with pytest.raises(Exception,match="unspecified"):
        combine_uncertainties(Quantity(300,"kelvin"),items,CombinationPolicy(CombinationMode.STANDARD_RSS))

def test_rss_with_explicit_zero_correlation_produces_five():
    items=(contribution("a1",UncertaintySource.MEASUREMENT,3,"1"),
           contribution("b1",UncertaintySource.PARAMETER,4,"2"))
    report=combine_uncertainties(Quantity(300,"kelvin"),items,
        CombinationPolicy(CombinationMode.STANDARD_RSS),(Correlation("a1","b1",0),))
    assert report.output.source_kind is UncertaintySource.COMBINED
    assert report.output.standard_uncertainty.magnitude_as_spread_in("kelvin")==pytest.approx(5)

def test_assume_zero_is_recorded_as_an_assumption_not_silent():
    items=(contribution("a1",UncertaintySource.MEASUREMENT,3,"1"),
           contribution("b1",UncertaintySource.PARAMETER,4,"2"))
    report=combine_uncertainties(Quantity(300,"kelvin"),items,
        CombinationPolicy(CombinationMode.STANDARD_RSS,MissingCorrelationPolicy.ASSUME_ZERO))
    assert report.assumptions==("assumed_zero_correlation:a1:b1",)
