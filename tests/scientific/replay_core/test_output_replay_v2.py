import pytest

from engcore.scientific.replay_core import (
    OutputExpectation,OutputObservation,compare_output,
)
from engcore.scientific.units.quantity import Quantity


def test_typed_output_comparison_accepts_value_inside_declared_tolerance():
    expected=OutputExpectation("temperature",Quantity(300,"kelvin"),Quantity(0.5,"kelvin"),0)
    actual=OutputObservation("temperature",Quantity(300.4,"kelvin"),"a"*64)
    result=compare_output(expected,actual)
    assert result.matched and result.absolute_error==pytest.approx(0.4)


def test_typed_output_comparison_refuses_dimensionally_foreign_output():
    expected=OutputExpectation("temperature",Quantity(300,"kelvin"),Quantity(0.5,"kelvin"),0)
    actual=OutputObservation("temperature",Quantity(1,"volt"),"a"*64)
    result=compare_output(expected,actual)
    assert not result.matched and "dimension mismatch" in result.problem


def test_relative_tolerance_must_be_finite_and_nonnegative():
    with pytest.raises(Exception,match="finite"):
        OutputExpectation("x",Quantity(1,"meter"),Quantity(0,"meter"),float("nan"))
