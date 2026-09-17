"""Core re-audit 2026-09-16, batch 26: a declaration is a magnitude and a unit, and a span is not a point.

Problem R-75 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-22 part A of
three, under benchmarks/core_v4_false_confidence/BATCH26_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import copy

import pytest

from engcore.mcp.errors import WrongDimensionError
from engcore.mcp.problem import build_electrothermal_problems, example_electrothermal_payload
from engcore.scientific.errors import ScientificCoreError, UnitCompatibilityError
from engcore.scientific.units import quantity as q
from engcore.scientific.units.quantity import Quantity

BODY = ("stages", 0, "body")


def _symbol(name: str):
    """Assert the named module symbol exists, so a missing one fails ON AN ASSERTION."""
    assert hasattr(q, name), (
        f"engcore.scientific.units.quantity has no {name!r}; the rule that needs it is "
        f"'a_difference_unit_is_not_an_absolute_value' in BATCH26_THRESHOLD_PROTOCOL.json"
    )
    return getattr(q, name)


def _payload_with(path, key, value):
    payload = example_electrothermal_payload()
    target = payload = copy.deepcopy(payload)
    for step in path:
        target = target[step]
    target[key] = value
    return payload


def _refused(text: str) -> bool:
    try:
        Quantity.parse(text)
    except ScientificCoreError:
        return True
    return False


# ---------------------------------------------------------------------------
# whitespace_means_a_declaration_not_an_expression
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-75: the split refusal is swallowed and the string is evaluated")
def test_r75_text_after_the_unit_is_not_folded_into_the_magnitude():
    assert _refused("5 volt 2"), (
        f"'5 volt 2' parsed as {Quantity.parse('5 volt 2')}: the trailing 2 multiplied a magnitude "
        f"the caller wrote once"
    )


@pytest.mark.xfail(strict=True, reason="R-75: the fallback evaluates the whole string as arithmetic")
def test_r75_an_arithmetic_expression_is_not_a_declaration():
    assert _refused("2 volt + 3 volt"), f"parsed as {Quantity.parse('2 volt + 3 volt')}"
    assert _refused("2volt+3volt"), f"parsed as {Quantity.parse('2volt+3volt')}"


# ---------------------------------------------------------------------------
# the_magnitude_written_is_the_magnitude_parsed
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-75: a bare unit becomes one of it, the mirror of the bare number already refused")
def test_r75_a_unit_with_no_magnitude_is_refused():
    assert _refused("volt"), f"'volt' parsed as {Quantity.parse('volt')}"


def test_r75_the_spellings_that_were_always_meant_still_parse():
    """The control. Not an xfail: these pass before the fix and must pass after it."""
    assert Quantity.parse("5volt") == Quantity(5.0, "volt")
    assert Quantity.parse("12 V") == Quantity(12.0, "volt")
    assert Quantity.parse("20 degC") == Quantity(20.0, "degC")
    assert Quantity.parse("1 1/kelvin") == Quantity(1.0, "1/kelvin")
    assert Quantity.parse("1 kg m / s**2") == Quantity(1.0, "kg m / s**2")
    assert Quantity.parse("1e3 volt") == Quantity(1000.0, "volt")
    assert Quantity.parse("+.5 volt") == Quantity(0.5, "volt")
    assert Quantity.parse("  7  ohm ") == Quantity(7.0, "ohm")
    assert Quantity.parse("1.589e-5 meter**2/second") == Quantity(1.589e-5, "meter**2/second")
    with pytest.raises(UnitCompatibilityError, match="carries no unit"):
        Quantity.parse("5")


# ---------------------------------------------------------------------------
# a_magnitude_is_a_number
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-75: bool is an int, so a flag is one volt")
def test_r75_a_bool_is_not_a_magnitude():
    with pytest.raises(UnitCompatibilityError):
        Quantity(True, "volt")


@pytest.mark.xfail(strict=True, reason="R-75: float() of a numeric string is silently accepted")
def test_r75_a_string_is_not_a_magnitude():
    with pytest.raises(UnitCompatibilityError):
        Quantity("5", "volt")


def test_r75_the_magnitudes_that_were_always_meant_are_still_accepted():
    """The control for the constructor rule: the test is by TYPE, so no number changes."""
    import numpy as np

    assert Quantity(5, "volt").magnitude == 5.0
    assert Quantity(5.0, "volt").magnitude == 5.0
    assert Quantity(np.float64(5.0), "volt").magnitude == 5.0
    assert Quantity(np.int64(5), "volt").magnitude == 5.0
    with pytest.raises(UnitCompatibilityError, match="must be finite"):
        Quantity(float("nan"), "volt")


# ---------------------------------------------------------------------------
# a_difference_unit_is_not_an_absolute_value
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-75: there is no name for the delta scales yet")
def test_r75_the_difference_scales_have_a_name():
    is_delta_unit = _symbol("is_delta_unit")
    assert is_delta_unit("delta_degC") is True
    assert is_delta_unit("delta_degF") is True
    assert is_delta_unit("millidelta_degC") is True, "an SI prefix does not stop it being a difference"
    assert is_delta_unit("watt/delta_degC") is True
    assert is_delta_unit("degC") is False
    assert is_delta_unit("kelvin") is False, "kelvin is absolute, even though a kelvin span is one kelvin"
    assert is_delta_unit("ohm") is False


@pytest.mark.xfail(strict=True, reason="R-75: the check is dimension-only, and a delta shares the dimension")
def test_r75_a_delta_temperature_is_refused_where_an_absolute_one_is_required():
    payload = _payload_with(BODY, "ambient_temperature", "27 delta_degC")
    with pytest.raises(WrongDimensionError, match="ambient_temperature"):
        build_electrothermal_problems(payload)


@pytest.mark.xfail(strict=True, reason="R-75: reaches production -- the boundary reads the expression as 10 V")
def test_r75_an_expression_at_the_mcp_boundary_is_refused():
    payload = example_electrothermal_payload()
    payload["source_voltage"] = "5 volt 2"
    with pytest.raises(ScientificCoreError, match="source_voltage"):
        build_electrothermal_problems(payload)


def test_r75_the_example_payload_still_builds():
    """The control for the boundary rules: every value the shipped example declares still reads."""
    assert len(build_electrothermal_problems(example_electrothermal_payload())) == 3
