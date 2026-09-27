"""Units audit U-01..U-03 (docs/code_audit/MODULE_BY_MODULE_REVIEW.md): one type rule at every door into a Quantity.

The constructor refuses a ``bool`` or ``str`` magnitude (R-75). The wire reader
(U-01), the sanctioned numeric boundary ``coerce_quantity`` (U-02) and scalar
``*`` / ``/`` (U-03) each called ``float`` first, which turned ``True`` into one
volt and ``"5"`` into five before anything could refuse them. numpy's bool and
raw bytes slip past an ``isinstance(x, bool/str)`` test the same way.
"""

from __future__ import annotations

import array
import json

from decimal import Decimal
from fractions import Fraction

import numpy as np
import pytest

from engcore.scientific.errors import ScientificCoreError, UnitCompatibilityError
from engcore.scientific.units.quantity import Quantity, coerce_quantity

NOT_NUMBERS = (True, False, np.True_, np.bool_(False), "5", "1e3", b"5", bytearray(b"5"),
               memoryview(b"5"), np.array(True), np.array("5"), np.array(b"5"),
               np.complex128(1 + 2j), np.array(True, dtype=object), np.timedelta64(5, "s"), array.array("b", b"5"))


def _id(value) -> str:
    """A test id with no memory address in it, so every xdist worker collects the same tests."""
    if isinstance(value, memoryview):
        return f"memoryview({bytes(value)!r})"
    if type(value) is object:
        return "object()"
    if isinstance(value, array.array):
        return f"array.array({value.typecode!r}, {value.tobytes()!r})"
    return f"{type(value).__name__}:{value!r}"


@pytest.mark.parametrize("value", NOT_NUMBERS, ids=_id)
def test_the_wire_reader_refuses_what_the_constructor_refuses(value):
    wire = Quantity(1.0, "volt").to_dict()
    with pytest.raises(UnitCompatibilityError, match="must be a number"):
        Quantity.from_dict({**wire, "magnitude": value})


@pytest.mark.parametrize("units", (1, 1.0, 5, None, ["volt"], b"volt"), ids=_id)
def test_the_wire_reader_refuses_units_that_are_not_text(units):
    wire = Quantity(1.0, "volt").to_dict()
    with pytest.raises(UnitCompatibilityError, match="units must be a string"):
        Quantity.from_dict({**wire, "units": units})


@pytest.mark.parametrize("value", NOT_NUMBERS[:4] + NOT_NUMBERS[6:], ids=_id)  # text goes through Quantity.parse
def test_the_numeric_boundary_refuses_truth_values_and_bytes(value):
    with pytest.raises(UnitCompatibilityError, match="must be a number"):
        coerce_quantity(value, "volt")


@pytest.mark.parametrize("value", NOT_NUMBERS, ids=_id)
def test_the_constructor_refuses_every_non_number_too(value):
    with pytest.raises(UnitCompatibilityError, match="must be a number"):
        Quantity(value, "volt")


@pytest.mark.parametrize("factor", NOT_NUMBERS + (object(),), ids=_id)
def test_scalar_arithmetic_refuses_what_is_not_a_scale_factor(factor):
    length = Quantity(2.0, "meter")
    with pytest.raises((UnitCompatibilityError, TypeError)):
        length * factor
    with pytest.raises((UnitCompatibilityError, TypeError)):
        length / factor


@pytest.mark.parametrize("units", (1, 1.0, True, np.float64(1.0), Decimal(1), Fraction(1), 1j), ids=_id)
def test_a_number_is_never_a_unit(units):
    with pytest.raises(UnitCompatibilityError, match="a number is not a unit"):
        Quantity(5.0, units)


def test_numpy_text_is_still_a_unit_expression():
    assert Quantity(5.0, np.str_("volt")) == Quantity(5.0, "volt")
    with pytest.raises(UnitCompatibilityError, match="a number is not a unit"):
        Quantity(5.0, np.int32(1))


def test_scalar_division_by_zero_raises_and_never_returns_an_infinity():
    with pytest.raises(ZeroDivisionError):
        Quantity(2.0, "meter") / 0
    with pytest.raises((ZeroDivisionError, ScientificCoreError)):
        Quantity(2.0, "meter") / Quantity(0.0, "second")


def test_every_number_that_passed_before_still_passes():
    wire = json.loads(json.dumps(Quantity(12.5, "volt").to_dict()))
    assert Quantity.from_dict(wire) == Quantity(12.5, "volt")
    assert Quantity.from_dict({**wire, "magnitude": 12}) == Quantity(12.0, "volt")      # a JSON integer
    for number in (3, 3.0, np.float64(3.0), np.int32(3), np.array(3.0)[()]):
        assert coerce_quantity(number, "volt") == Quantity(3.0, "volt")
        assert (Quantity(2.0, "meter") * number).magnitude == 6.0
        assert (Quantity(6.0, "meter") / number).magnitude == 2.0
    assert coerce_quantity("3 V", "volt") == Quantity(3.0, "volt")                      # text goes through parse
    with pytest.raises(UnitCompatibilityError):
        coerce_quantity("3", "volt")                                                     # a bare number in text states no unit
