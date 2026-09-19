import pytest
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.budget import Correlation
from engcore.uq.combined import *

def c(cid,source,digit):
    return UncertaintyContribution(cid,Uncertainty(kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(1,"kelvin"),method="x",source_kind=source),
        digit*64,(digit*64,),"g-"+cid)

def test_combined_standard_uq_refuses_non_psd_declared_correlation_matrix():
    items=(c("a",UncertaintySource.MEASUREMENT,"1"),c("b",UncertaintySource.PARAMETER,"2"),
           c("c",UncertaintySource.NUMERICAL,"3"))
    correlations=(Correlation("a","b",-0.9),Correlation("a","c",-0.9),Correlation("b","c",-0.9))
    with pytest.raises(ValueError,match="positive-semidefinite"):
        combine_uncertainties(Quantity(300,"kelvin"),items,
            CombinationPolicy(CombinationMode.STANDARD_RSS),correlations)
