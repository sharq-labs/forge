"""A declaration may state a temperature in degrees Celsius (blind/v1, T2).

The finding
-----------

``Quantity(20.0, "degC").magnitude_in("kelvin")`` has always returned 293.15,
and ``tests/test_offset_unit_arithmetic.py`` pins a whole page of correct
offset-unit behaviour on top of it. But ``Quantity.parse("20 degC")`` — the
**only** path a declaration can take through the payload boundary — raised
``UnitCompatibilityError``, because it handed the whole string to the units
backend's string parser, which reads it as the multiplication ``20 * degC``.
Multiplying by an offset unit is ambiguous, and the backend refuses it.

So the core supported degrees Celsius everywhere except where a caller could
write one, and the refusal misreported its own cause: the message said the
quantity could not be *read*, when the unit was perfectly readable and only the
multiplication was ambiguous.

It also contradicted the boundary's own stated rule. ``tests/mcp/test_problem.py
::test_a_dimension_check_is_not_a_unit_check`` says "Any unit of the right
dimension is accepted; the core converts it… rejecting ``degC`` where the model
wrote ``kelvin`` would be the unit-string comparison this platform refuses" —
and exercises that claim with ``"2 minute"``, a ratio-scale unit, which is why
nothing here ever went red.

Found by ``benchmarks/blind/v1``: 72 of 444 blind cases, across two systems and
every boundary stratum, refused at the boundary for declaring a temperature in
degC against a frozen truth that expected a verdict.

What this file pins
-------------------

The fix is one branch in :meth:`Quantity.parse` — split the magnitude from the
unit and use the two-argument constructor, falling back to the string parser —
so the risk is not that degC stops working. The risk is that something ELSE
changed: that an unknown unit slipped through, that a bare number became
acceptable, or that one of the places which deliberately refuse an affine scale
stopped refusing. Most of what follows is about those.

Nothing here imports the blind challenge. The cases are written out.
"""

from __future__ import annotations

import math

import pytest

from src.engcore.mcp.errors import ProblemPayloadError
from src.engcore.mcp.problem import build_electrothermal_system
from src.engcore.scientific.errors import (
    InvalidScientificProblem,
    UnitCompatibilityError,
)

from src.engcore.scientific.units.quantity import Quantity as Q

#: Both are refusals, and the boundary scorer treats both as one. They differ
#: in who wraps them: `coupling.tolerance` is re-raised as the payload
#: boundary's own error, while an applicability sub-field surfaces the domain's
#: `InvalidScientificProblem` unwrapped. That inconsistency is worth knowing
#: about and is not what these tests are for, so they accept either.
REFUSED = (ProblemPayloadError, InvalidScientificProblem)

ABSOLUTE_ZERO_C = -273.15


# =====================================================================
# The finding: a declaration in degrees Celsius is readable
# =====================================================================

@pytest.mark.parametrize(
    "text, kelvin",
    [
        ("0 degC", 273.15),
        ("20 degC", 293.15),
        ("-12.3330494309767 degC", 260.81695056902327),
        ("-40 degC", 233.14999999999998),
        ("100 degC", 373.15),
        ("-273.15 degC", 0.0),
    ],
)
def test_a_celsius_declaration_parses_to_the_kelvin_it_means(text, kelvin):
    """The conversion is the offset, computed here rather than asked for."""
    parsed = Q.parse(text)
    assert parsed.magnitude_in("kelvin") == pytest.approx(kelvin, abs=1e-9)
    magnitude = float(text.split(" ")[0])
    assert parsed.magnitude_in("kelvin") == pytest.approx(
        magnitude - ABSOLUTE_ZERO_C, abs=1e-9
    )


def test_the_two_constructors_now_agree():
    """They did not, and that disagreement WAS the defect.

    One type, two ways in, and only one of them accepted an offset unit.
    """
    assert Q.parse("20 degC").magnitude_in("kelvin") == pytest.approx(
        Q(20.0, "degC").magnitude_in("kelvin")
    )


@pytest.mark.parametrize("unit", ["degC", "degF", "kelvin", "rankine"])
def test_every_temperature_scale_the_backend_knows_can_be_declared(unit):
    assert math.isfinite(Q.parse(f"20 {unit}").magnitude_in("kelvin"))


def test_fahrenheit_lands_where_the_definition_puts_it():
    """(F - 32) * 5/9 + 273.15, written out rather than delegated."""
    assert Q.parse("212 degF").magnitude_in("kelvin") == pytest.approx(
        (212.0 - 32.0) * 5.0 / 9.0 + 273.15, abs=1e-9
    )


def test_a_celsius_temperature_reaches_a_built_system():
    """End to end, through the boundary that could not express it.

    A conductor's reference temperature declared in degC now builds, and the
    system carries the kelvin it means.
    """
    payload = {
        "source_voltage": "12 volt",
        "stages": [{
            "component_id": "R1",
            "conductor": {
                "reference_resistance": "100 ohm",
                "temperature_coefficient": "0.00393 1/kelvin",
                "reference_temperature": "20 degC",
            },
            "body": {
                "heat_capacity": "2.5 joule/kelvin",
                "ambient_conductance": "0.05 watt/kelvin",
                "ambient_temperature": "25 degC",
                "initial_temperature": "25 degC",
                "duration": "60 second",
            },
        }],
        "coupling": {"tolerance": "1e-9 kelvin", "max_iterations": 50},
    }
    system = build_electrothermal_system(payload)
    conductor = system.stages[0].conductor
    assert conductor.reference_temperature.magnitude_in("kelvin") == (
        pytest.approx(293.15)
    )
    assert system.stages[0].body.ambient_temperature.magnitude_in(
        "kelvin") == pytest.approx(298.15)


def test_the_same_system_in_kelvin_is_the_same_system():
    """The unit a caller happened to write must not change the answer.

    The sharpest form of the claim: two payloads that differ only in the scale
    their temperatures are written on must produce the same state.
    """
    def payload(reference, ambient):
        return {
            "source_voltage": "12 volt",
            "stages": [{
                "component_id": "R1",
                "conductor": {
                    "reference_resistance": "100 ohm",
                    "temperature_coefficient": "0.00393 1/kelvin",
                    "reference_temperature": reference,
                },
                "body": {
                    "heat_capacity": "2.5 joule/kelvin",
                    "ambient_conductance": "0.05 watt/kelvin",
                    "ambient_temperature": ambient,
                    "initial_temperature": ambient,
                    "duration": "60 second",
                },
            }],
            "coupling": {"tolerance": "1e-9 kelvin", "max_iterations": 50},
        }

    celsius = build_electrothermal_system(payload("20 degC", "25 degC"))
    kelvin = build_electrothermal_system(payload("293.15 kelvin", "298.15 kelvin"))
    for left, right in ((celsius.stages[0], kelvin.stages[0]),):
        assert left.conductor.reference_temperature.magnitude_in("kelvin") == (
            pytest.approx(right.conductor.reference_temperature
                          .magnitude_in("kelvin")))
        assert left.body.ambient_temperature.magnitude_in("kelvin") == (
            pytest.approx(right.body.ambient_temperature
                          .magnitude_in("kelvin")))


# =====================================================================
# What must NOT have changed
# =====================================================================

@pytest.mark.parametrize(
    "text",
    ["1 kilohm", "1 nonsenseunit", "3 furfuraldehydes", "5 ohmm"],
)
def test_an_undefined_unit_is_still_refused(text):
    """The split path normalises through the same registry.

    ``kilohm`` is the spelling that produced 69 of the blind challenge's own
    failures, and refusing it is correct: the registry defines ``kiloohm``, and
    guessing which one a caller meant is the substitution this layer exists to
    refuse.
    """
    with pytest.raises(UnitCompatibilityError):
        Q.parse(text)


@pytest.mark.parametrize("text", ["12", "  12  ", "1e-9", "-4", "0"])
def test_a_bare_number_is_still_not_a_quantity(text):
    with pytest.raises(UnitCompatibilityError, match="carries no unit"):
        Q.parse(text)


@pytest.mark.parametrize(
    "text, unit",
    [
        ("5volt", "volt"),
        ("1e-6 meter**2/second", "meter ** 2 / second"),
        ("5000 millivolt", "millivolt"),
        ("2 minute", "minute"),
        ("0.03 dimensionless", "dimensionless"),
        ("-1.5 watt/meter/kelvin", "watt / kelvin / meter"),
    ],
)
def test_every_spelling_that_parsed_before_still_parses(text, unit):
    """Including the one with no separator, which only the fallback can read."""
    assert Q.parse(text).units == unit


@pytest.mark.parametrize("tolerance", ["0 degC", "20 degC", "-1 degC",
                                       "20 degF", "0 kelvin", "-1 kelvin"])
def test_an_affine_coupling_tolerance_is_still_refused(tolerance):
    """The deliberate refusal, and why the fix could not weaken it.

    A tolerance is a DIFFERENCE, and a difference cannot live on a scale whose
    zero is conventional. That refusal is made by ``_require_ratio_scale`` on
    the unit, AFTER any parse, so making the string readable never made it
    admissible. Before the fix ``"20 degC"`` was refused for the wrong reason —
    it could not be parsed at all — and this asserts it is still refused now
    that it can be.
    """
    payload = {
        "source_voltage": "12 volt",
        "stages": [{
            "component_id": "R1",
            "conductor": {
                "reference_resistance": "100 ohm",
                "temperature_coefficient": "0.00393 1/kelvin",
                "reference_temperature": "293.15 kelvin",
            },
            "body": {
                "heat_capacity": "2.5 joule/kelvin",
                "ambient_conductance": "0.05 watt/kelvin",
                "ambient_temperature": "298.15 kelvin",
                "initial_temperature": "298.15 kelvin",
                "duration": "60 second",
            },
        }],
        "coupling": {"tolerance": tolerance, "max_iterations": 50},
    }
    with pytest.raises(REFUSED):
        build_electrothermal_system(payload)


@pytest.mark.parametrize("bound", ["conductance_excursion_bound",
                                   "capacity_excursion_bound"])
def test_an_excursion_span_on_an_affine_scale_is_still_refused(bound):
    """The other deliberate refusal, for the same reason.

    An excursion bound is a span. Ten degrees of span written as ``10 degC`` is
    283.15 K, and every ratio built on it would be wrong by a factor of thirty
    with no dimension check able to notice.
    """
    payload = {
        "source_voltage": "12 volt",
        "stages": [{
            "component_id": "R1",
            "conductor": {
                "reference_resistance": "100 ohm",
                "temperature_coefficient": "0.00393 1/kelvin",
                "reference_temperature": "293.15 kelvin",
            },
            "body": {
                "heat_capacity": "2.5 joule/kelvin",
                "ambient_conductance": "0.05 watt/kelvin",
                "ambient_temperature": "298.15 kelvin",
                "initial_temperature": "298.15 kelvin",
                "duration": "60 second",
                "applicability": {bound: "10 degC"},
            },
        }],
        "coupling": {"tolerance": "1e-9 kelvin", "max_iterations": 50},
    }
    with pytest.raises(REFUSED):
        build_electrothermal_system(payload)


def test_a_wrong_dimension_is_still_a_wrong_dimension():
    """A resistance declared in volts is refused, degC fix or no degC fix."""
    payload = {
        "source_voltage": "12 volt",
        "stages": [{
            "component_id": "R1",
            "conductor": {
                "reference_resistance": "100 volt",
                "temperature_coefficient": "0.00393 1/kelvin",
                "reference_temperature": "293.15 kelvin",
            },
            "body": {
                "heat_capacity": "2.5 joule/kelvin",
                "ambient_conductance": "0.05 watt/kelvin",
                "ambient_temperature": "298.15 kelvin",
                "initial_temperature": "298.15 kelvin",
                "duration": "60 second",
            },
        }],
        "coupling": {"tolerance": "1e-9 kelvin", "max_iterations": 50},
    }
    with pytest.raises(REFUSED):
        build_electrothermal_system(payload)


def test_offset_arithmetic_is_untouched():
    """The behaviour `test_offset_unit_arithmetic.py` pins, re-asserted here.

    Parsing and arithmetic are different questions and the fix touched only the
    first, but the two meet on exactly one type — so the claim is worth one
    line here rather than a reader having to go and check.
    """
    difference = Q.parse("30 degC") - Q.parse("20 degC")
    assert difference.magnitude_in("kelvin") == pytest.approx(10.0)
    with pytest.raises(UnitCompatibilityError, match="offset|ambiguous"):
        Q.parse("30 degC") + Q.parse("20 degC")
