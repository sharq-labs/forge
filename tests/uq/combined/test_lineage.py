import pytest
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.combined import *

def c(cid,source,lineage):
    return UncertaintyContribution(cid,Uncertainty(kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(1,"kelvin"),method="x",source_kind=source),
        cid[0]*64,(lineage,),"g-"+cid)

def test_shared_primitive_lineage_is_refused_before_combination():
    shared="f"*64
    with pytest.raises(Exception,match="double-counted"):
        combine_uncertainties(Quantity(300,"kelvin"),
            (c("a1",UncertaintySource.MEASUREMENT,shared),c("b1",UncertaintySource.PARAMETER,shared)),
            CombinationPolicy(CombinationMode.STANDARD_RSS,MissingCorrelationPolicy.ASSUME_ZERO))

def test_required_uncertainty_channels_must_be_present():
    item=c("a1",UncertaintySource.MEASUREMENT,"e"*64)
    with pytest.raises(Exception,match="missing required"):
        combine_uncertainties(Quantity(300,"kelvin"),(item,),
            CombinationPolicy(CombinationMode.STANDARD_RSS,
                required_sources=(UncertaintySource.MEASUREMENT,UncertaintySource.MODEL_FORM)))
