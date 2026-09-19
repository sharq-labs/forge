from engcore.scientific import equations


def test_equation_ir_is_a_core_subpackage_without_freezing_root_api_yet():
    assert equations.LawDefinition is not None
    assert equations.Equation is not None
    assert equations.DimensionVector is not None
