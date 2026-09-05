"""Component-level validation for Electrical DC V0."""

from __future__ import annotations

import sys

from src.engcore.domains.electrical.dc import (
    DCCurrentSource,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
)
from src.engcore.scientific import (
    InvalidScientificProblem,
    Quantity,
    UnitCompatibilityError,
)


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


# ---- nodes ------------------------------------------------------------

def test_node_requires_id_and_reference_is_explicit():
    node = ElectricalNode("n1")
    assert node.node_id == "n1"
    # No hidden convention: a node called "0" is NOT ground unless declared.
    assert ElectricalNode("0").is_reference is False
    assert ElectricalNode("gnd").is_reference is False
    assert ElectricalNode("gnd", is_reference=True).is_reference is True
    _raises(InvalidScientificProblem, ElectricalNode, "   ")


def test_node_round_trip():
    node = ElectricalNode("gnd", label="ground", is_reference=True)
    assert ElectricalNode.from_dict(node.to_dict()) == node


# ---- resistors --------------------------------------------------------

def test_resistor_accepts_compatible_resistance_units():
    for value, unit, expected_ohm in (
        (1.0, "ohm", 1.0),
        (1.0, "kohm", 1000.0),
        (500.0, "milliohm", 0.5),
    ):
        resistor = Resistor("R1", "a", "b", Quantity(value, unit))
        assert abs(resistor.resistance_ohm - expected_ohm) < 1e-12
        assert abs(resistor.conductance_siemens - 1.0 / expected_ohm) < 1e-12


def test_resistor_rejects_non_positive_resistance():
    _raises(
        InvalidScientificProblem, Resistor, "R1", "a", "b", Quantity(0.0, "ohm")
    )
    _raises(
        InvalidScientificProblem, Resistor, "R1", "a", "b", Quantity(-5.0, "ohm")
    )


def test_resistor_rejects_wrong_dimension():
    _raises(
        UnitCompatibilityError, Resistor, "R1", "a", "b", Quantity(5.0, "volt")
    )
    _raises(
        UnitCompatibilityError, Resistor, "R1", "a", "b", Quantity(5.0, "kg")
    )


def test_resistor_rejects_self_connection_and_empty_ids():
    _raises(
        InvalidScientificProblem, Resistor, "R1", "a", "a", Quantity(1.0, "ohm")
    )
    _raises(
        InvalidScientificProblem, Resistor, "", "a", "b", Quantity(1.0, "ohm")
    )


def test_resistor_round_trip():
    resistor = Resistor("R1", "a", "b", Quantity(2.2, "kohm"))
    assert Resistor.from_dict(resistor.to_dict()) == resistor


# ---- voltage sources --------------------------------------------------

def test_voltage_source_accepts_sign_and_units():
    for value, unit, expected_volt in (
        (10.0, "volt", 10.0),
        (500.0, "millivolt", 0.5),
        (-5.0, "volt", -5.0),
        (0.0, "volt", 0.0),
    ):
        source = DCVoltageSource("V1", "p", "n", Quantity(value, unit))
        assert abs(source.voltage_volt - expected_volt) < 1e-12


def test_voltage_source_rejects_wrong_dimension_and_self_connection():
    _raises(
        UnitCompatibilityError, DCVoltageSource, "V1", "p", "n",
        Quantity(1.0, "ampere"),
    )
    _raises(
        InvalidScientificProblem, DCVoltageSource, "V1", "p", "p",
        Quantity(1.0, "volt"),
    )


def test_voltage_source_round_trip():
    source = DCVoltageSource("V1", "p", "n", Quantity(-3.3, "volt"))
    assert DCVoltageSource.from_dict(source.to_dict()) == source


# ---- current sources --------------------------------------------------

def test_current_source_accepts_sign_and_units():
    for value, unit, expected_ampere in (
        (2.0, "ampere", 2.0),
        (2.0, "milliampere", 0.002),
        (-1.0, "ampere", -1.0),
        (0.0, "ampere", 0.0),
    ):
        source = DCCurrentSource("I1", "a", "b", Quantity(value, unit))
        assert abs(source.current_ampere - expected_ampere) < 1e-15


def test_current_source_rejects_wrong_dimension_and_self_connection():
    _raises(
        UnitCompatibilityError, DCCurrentSource, "I1", "a", "b",
        Quantity(1.0, "volt"),
    )
    _raises(
        InvalidScientificProblem, DCCurrentSource, "I1", "a", "a",
        Quantity(1.0, "ampere"),
    )


def test_current_source_round_trip():
    source = DCCurrentSource("I1", "a", "b", Quantity(5.0, "milliampere"))
    assert DCCurrentSource.from_dict(source.to_dict()) == source


def _all_tests():
    module = sys.modules[__name__]
    return [
        (n, getattr(module, n))
        for n in sorted(dir(module))
        if n.startswith("test_") and callable(getattr(module, n))
    ]


def main() -> int:
    failures = 0
    for name, test in _all_tests():
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print(f"components: {'FAIL' if failures else 'PASS'} "
          f"({len(_all_tests()) - failures}/{len(_all_tests())})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
