import pytest
from engcore.scientific.verification import VerificationObservation,compare_observations
from engcore.scientific.units.quantity import Quantity

def obs(route,value,unit="kelvin",converged=True,digit="a"):
    return VerificationObservation(route,Quantity(value,unit),digit*64,converged)

def test_quantity_comparison_uses_typed_positive_tolerance():
    comparison=compare_observations(obs("p",300,digit="a"),obs("v",300.5,digit="b"),Quantity(1,"kelvin"))
    assert comparison.agreement and comparison.normalized_error==pytest.approx(0.5)

def test_nonconverged_route_cannot_agree():
    comparison=compare_observations(obs("p",300,digit="a"),obs("v",300,converged=False,digit="b"),Quantity(1,"kelvin"))
    assert not comparison.agreement and comparison.normalized_error is None

def test_dimensionally_foreign_verification_value_is_refused():
    with pytest.raises(Exception,match="dimensions"):
        compare_observations(obs("p",300,digit="a"),obs("v",1,"volt",digit="b"),Quantity(1,"kelvin"))
