from engcore.claims.model_form_uncertainty import promote_model_form_interval
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.uq.combined import *
from engcore.uq.model_form import *

def scope():
    return ModelFormScope("model","a"*64,"b"*64,"c"*64,"temperature","kelvin")

def test_authorized_model_form_interval_combines_with_numerical_without_losing_source_identity():
    s=scope()
    estimate=ModelFormEstimate("temperature","kelvin",ModelFormStatus.VALIDATED,2,
        ("c1","c2"),("v1","v2"),1.0,"ok",scope=s)
    qualification=ProducerQualification("producer","method","d"*64,"reviewer","e"*64,("temperature",))
    model_form=promote_model_form_interval(estimate,qualification,Quantity(300,"kelvin"),target_scope=s)
    numerical=Uncertainty(kind=UncertaintyKind.STANDARD,standard_uncertainty=Quantity(1,"kelvin"),
                          method="grid",source_kind=UncertaintySource.NUMERICAL)
    report=combine_uncertainties(Quantity(300,"kelvin"),(
        UncertaintyContribution("model_form",model_form,"f"*64,("1"*64,),"mf"),
        UncertaintyContribution("numerical",numerical,"9"*64,("2"*64,),"num"),
    ),CombinationPolicy(CombinationMode.HYBRID_INTERVAL,standard_coverage_factor=2,
                        required_sources=(UncertaintySource.MODEL_FORM,UncertaintySource.NUMERICAL)))
    assert report.output.lower.magnitude_in("kelvin")==296
    assert report.output.upper.magnitude_in("kelvin")==304
