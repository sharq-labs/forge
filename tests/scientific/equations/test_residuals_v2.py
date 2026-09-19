import pytest

from engcore.scientific.equations import Constant, Equation, ResidualDefinition, Symbol
from engcore.scientific.units.quantity import Quantity


def test_residual_can_remain_physical_or_be_explicitly_normalized():
    equation=Equation(Symbol("T"),Constant(Quantity(300,"kelvin")))
    physical=ResidualDefinition("temperature",equation)
    normalized=ResidualDefinition("temperature-normalized",equation,Quantity(10,"kelvin"))
    bindings={"T":Quantity(310,"kelvin")}
    assert physical.evaluate(bindings).magnitude_in("kelvin")==pytest.approx(10)
    assert normalized.evaluate(bindings).magnitude_in("dimensionless")==pytest.approx(1)
    assert ResidualDefinition.from_dict(normalized.to_dict())==normalized
