import pytest
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.combined import *

def test_combination_wire_output_is_recomputed_from_inputs():
    item=UncertaintyContribution("x",Uncertainty(kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(2,"kelvin"),method="x",source_kind=UncertaintySource.MEASUREMENT),
        "a"*64,("b"*64,),"g")
    report=combine_uncertainties(Quantity(300,"kelvin"),(item,),CombinationPolicy(CombinationMode.STANDARD_RSS))
    payload=report_to_dict(report)
    payload["output"]["method"]="forged"
    with pytest.raises(InvalidScientificProblem,match="forged"):
        report_from_dict(payload)

def test_combination_round_trip_is_stable():
    item=UncertaintyContribution("x",Uncertainty(kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(2,"kelvin"),method="x",source_kind=UncertaintySource.MEASUREMENT),
        "a"*64,("b"*64,),"g")
    report=combine_uncertainties(Quantity(300,"kelvin"),(item,),CombinationPolicy(CombinationMode.STANDARD_RSS))
    assert report_to_dict(report_from_dict(report_to_dict(report)))==report_to_dict(report)
