import pytest
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.combined import *

def test_combined_uq_refuses_dimensionally_foreign_component():
    item=UncertaintyContribution("x",Uncertainty(kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(1,"volt"),method="x",source_kind=UncertaintySource.MEASUREMENT),
        "a"*64,("b"*64,),"g")
    with pytest.raises(Exception,match="incompatible"):
        combine_uncertainties(Quantity(300,"kelvin"),(item,),
            CombinationPolicy(CombinationMode.STANDARD_RSS))

def test_combined_or_unknown_source_cannot_reenter_combiner():
    with pytest.raises(Exception,match="primitive"):
        UncertaintyContribution("x",Uncertainty(kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(1,"kelvin"),method="x",source_kind=UncertaintySource.COMBINED),
            "a"*64,("b"*64,),"g")
