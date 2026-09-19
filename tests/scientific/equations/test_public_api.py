from engcore import scientific
from engcore.scientific.equations import LawDefinition


def test_equation_ir_is_exposed_from_scientific_core():
    assert scientific.LawDefinition is LawDefinition
    assert scientific.Equation is not None
    assert scientific.DimensionVector is not None
