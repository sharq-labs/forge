import pytest
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.combined import *

def interval(cid,source,lo,hi,digit):
    return UncertaintyContribution(cid,Uncertainty(kind=UncertaintyKind.INTERVAL,
        lower=Quantity(lo,"kelvin"),upper=Quantity(hi,"kelvin"),method="x",source_kind=source),
        digit*64,(digit*64,),"g-"+cid)

def standard(cid,source,u,digit):
    return UncertaintyContribution(cid,Uncertainty(kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(u,"kelvin"),method="x",source_kind=source),
        digit*64,(digit*64,),"g-"+cid)

def test_conservative_interval_adds_asymmetric_widths_without_independence_claim():
    report=combine_uncertainties(Quantity(300,"kelvin"),
        (interval("m",UncertaintySource.MEASUREMENT,299,302,"1"),
         interval("f",UncertaintySource.MODEL_FORM,298,301,"2")),
        CombinationPolicy(CombinationMode.CONSERVATIVE_INTERVAL))
    assert report.output.lower.magnitude_in("kelvin")==pytest.approx(297)
    assert report.output.upper.magnitude_in("kelvin")==pytest.approx(303)

def test_hybrid_interval_requires_explicit_k_and_records_it():
    with pytest.raises(ValueError,match="coverage"):
        CombinationPolicy(CombinationMode.HYBRID_INTERVAL)
    report=combine_uncertainties(Quantity(300,"kelvin"),
        (interval("f",UncertaintySource.MODEL_FORM,298,302,"1"),
         standard("n",UncertaintySource.NUMERICAL,1,"2")),
        CombinationPolicy(CombinationMode.HYBRID_INTERVAL,standard_coverage_factor=2))
    assert report.output.lower.magnitude_in("kelvin")==pytest.approx(296)
    assert report.output.upper.magnitude_in("kelvin")==pytest.approx(304)
    assert "declared_k=2.0" in report.assumptions[0]


def test_interval_that_does_not_contain_nominal_is_refused():
    bad=interval("bad",UncertaintySource.MEASUREMENT,290,299,"3")
    with pytest.raises(Exception,match="does not contain nominal"):
        combine_uncertainties(Quantity(300,"kelvin"),(bad,),
            CombinationPolicy(CombinationMode.CONSERVATIVE_INTERVAL))
