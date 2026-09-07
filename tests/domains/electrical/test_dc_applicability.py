"""When the ideal linear DC model stops describing the device.

Two conditions across two companion model records, each with three tests —
IN_DOMAIN, OUTSIDE_VALIDATED_DOMAIN, and the missing declaration that must be
UNKNOWN rather than either. Each is the direct falsification of an assumption
the base record in ``dc/models.py`` already states in words: "zero internal
impedance", and a rating written against an element the lumped model does not
resolve.

A third condition, ``self_heating_resistance_drift_ratio``, was declared here
and is gone. Wiring it into the electro-thermal boundary measured it at 17.85
on this repository's own nominal example — violated eighteen times over, on a
correct design — because the coupled run solves the circuit at the converged
``R(T)`` and the drift it measured is the effect the composition *models*. The
module docstring carries the full argument. It is removed rather than
weakened, and ``test_the_falsified_condition_is_gone`` keeps it that way.

**Neither introduces a numeric constant.** Every bound is 1 and
definitional, being the fraction of a *declared* budget in use, so there is no
threshold in this file for a source to have printed and for anybody to have got
wrong. The tests below assert that: each bound is exactly ``Quantity(1.0,
dimensionless)``, and the condition crosses it at the declared budget rather
than at a number of this repository's choosing.

The rating conditions in ``test_dc_rating_applicability.py`` ask whether a part
survives its operating point. These ask whether the relation still describes it
while it comfortably does.
"""

from __future__ import annotations

import pytest

from src.engcore.domains.electrical import dc_applicability as app
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.ir.problem import ScientificProblem
from src.engcore.scientific.ir.variables import ScientificParameter
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.units.quantity import Quantity

OHM = "ohm"
VOLT = "volt"
AMPERE = "ampere"
WATT = "watt"
KELVIN = "kelvin"
K_PER_W = "kelvin/watt"
NONE = "dimensionless"


def _problem(**declared: Quantity) -> ScientificProblem:
    """A bare problem carrying exactly the declarations a test wants seen.

    The model records are bound to real circuit components elsewhere; what is
    under test here is the assessment, so the problem is the smallest thing
    that carries a declaration into it.
    """
    return ScientificProblem(
        problem_id="dc-applicability-test",
        name="declarations under test",
        parameters=tuple(
            ScientificParameter(name=name, value=value)
            for name, value in sorted(declared.items())
        ),
    )


# =====================================================================
# The bounds are definitional, and that is the point
# =====================================================================

def test_no_condition_here_introduces_a_numeric_constant():
    """Every bound is exactly 1, dimensionless, and is a declared budget.

    The alternative — a convention like 0.05, or a number read off a curve —
    is what three bounds in this repository were and what re-reading their
    sources cost. A fraction-of-a-declared-budget has nothing to re-read.
    """
    one = Quantity(1.0, NONE)
    assert app.REGULATION_BUDGET_LIMIT == one
    assert app.ELEMENT_TEMPERATURE_LIMIT == one

    for model in app.APPLICABILITY_MODELS:
        for condition in model.validity.conditions:
            assert condition.maximum == one, condition.name
            assert condition.minimum is None, condition.name


def test_every_derived_group_is_reserved_against_a_caller():
    """A declaration must never be able to decide a condition.

    Both quantities are computed from a solve and from declarations; a
    caller parameter of one of those names would satisfy the condition that
    reads it, which is a part nobody characterised reporting IN_DOMAIN over a
    number nobody derived. ``validity_context`` refuses it outright.
    """
    assert app.ASSEMBLER_NAMESPACE == {
        app.SOURCE_REGULATION_UTILIZATION,
        app.ELEMENT_HOT_SPOT_UTILIZATION,
    }
    for name in sorted(app.ASSEMBLER_NAMESPACE):
        forged = _problem(**{name: Quantity(0.0, NONE)})
        with pytest.raises(InvalidScientificProblem):
            forged.validity_context(reserved=app.ASSEMBLER_NAMESPACE)


def test_the_two_records_are_companions_and_not_replacements():
    """The frozen records keep their ids, versions and assumptions.

    These are new model ids beside the old ones, the shape
    ``rated_linear_tcr_resistance`` has beside ``linear_tcr_resistance``. A
    reader holding a result against ``electrical.dc.resistor_ohm`` is entitled
    to find that record unchanged.
    """
    from src.engcore.domains.electrical.dc.models import (
        IDEAL_VOLTAGE_SOURCE_MODEL,
        RESISTOR_OHM_MODEL,
    )

    assert "temperature-independent resistance" in RESISTOR_OHM_MODEL.assumptions
    assert "zero internal impedance" in IDEAL_VOLTAGE_SOURCE_MODEL.assumptions
    ids = {m.model_id for m in app.APPLICABILITY_MODELS}
    assert ids == {
        "electrical.dc.regulated_voltage_source",
        "electrical.dc.self_heated_resistor",
    }
    assert RESISTOR_OHM_MODEL.model_id not in ids
    assert IDEAL_VOLTAGE_SOURCE_MODEL.model_id not in ids


# =====================================================================
# source_regulation_utilization
# =====================================================================
#
# A 12 V supply with 50 milliohms of output resistance, in a design that
# permits 1 % of droop. At 2 A the internal drop is 0.1 V, which is 0.833 % of
# 12 V and so 0.833 of the declared band.

REGULATED = {
    app.SOURCE_VOLTAGE: Quantity(12.0, VOLT),
    app.OUTPUT_RESISTANCE: Quantity(0.05, OHM),
    app.REGULATION_BAND: Quantity(0.01, NONE),
}


def test_regulation_in_domain():
    assessment = app.assess_regulated_source_validity(
        _problem(**REGULATED), source_current=Quantity(2.0, AMPERE)
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.satisfied == (app.SOURCE_REGULATION_UTILIZATION,)

    value = app.source_regulation_utilization(
        source_current=Quantity(2.0, AMPERE), **REGULATED
    )
    assert value.magnitude == pytest.approx(0.1 / 12.0 / 0.01)


def test_regulation_outside_validated_domain():
    """Three amps through the same supply, and the drop leaves the band.

    0.05 ohm at 3 A is 0.15 V, 1.25 % of 12 V, against a declared 1 %. The
    supply is nowhere near a current limit: this is the departure the rating
    conditions cannot see.
    """
    assessment = app.assess_regulated_source_validity(
        _problem(**REGULATED), source_current=Quantity(3.0, AMPERE)
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (app.SOURCE_REGULATION_UTILIZATION,)


@pytest.mark.parametrize(
    "withheld",
    [app.OUTPUT_RESISTANCE, app.REGULATION_BAND, app.SOURCE_VOLTAGE],
)
def test_regulation_unknown_when_a_declaration_is_missing(withheld):
    """An undeclared output resistance is not a zero output resistance."""
    partial = {k: v for k, v in REGULATED.items() if k != withheld}
    assessment = app.assess_regulated_source_validity(
        _problem(**partial), source_current=Quantity(2.0, AMPERE)
    )
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (app.SOURCE_REGULATION_UTILIZATION,)
    assert assessment.satisfied == ()


def test_regulation_unknown_when_the_solve_supplied_no_current():
    """Everything declared and nothing solved is still UNKNOWN.

    The current is a VARIABLE on the record: it is what the network produced,
    and a fully characterised supply with no operating point has still not been
    asked the question this condition answers.
    """
    assessment = app.assess_regulated_source_validity(_problem(**REGULATED))
    assert assessment.status is ValidityStatus.UNKNOWN


def test_regulation_reads_the_magnitude_of_a_reversed_current():
    """A source sinking 2 A departs exactly as far as one sourcing 2 A."""
    forward = app.source_regulation_utilization(
        source_current=Quantity(2.0, AMPERE), **REGULATED
    )
    reverse = app.source_regulation_utilization(
        source_current=Quantity(-2.0, AMPERE), **REGULATED
    )
    assert forward == reverse


def test_a_zero_regulation_band_is_refused_rather_than_read_as_unknown():
    """A band of zero is a specification error, not a very tight band."""
    with pytest.raises(InvalidScientificProblem):
        app.source_regulation_utilization(
            source_current=Quantity(2.0, AMPERE),
            source_voltage=Quantity(12.0, VOLT),
            output_resistance=Quantity(0.05, OHM),
            regulation_band=Quantity(0.0, NONE),
        )


# =====================================================================
# The element declarations the surviving condition reads
# =====================================================================
#
# A TO-220 power resistor: 6.5 K/W element-to-case, permissible element
# temperature 155 C = 428.15 K, both from the Bourns PWR220T-20 record in
# `benchmarks/ai_designs/components.json`.

HOT_SPOT_DECLARED = {
    app.ELEMENT_TO_BODY_THERMAL_RESISTANCE: Quantity(6.5, K_PER_W),
    app.PERMISSIBLE_ELEMENT_TEMPERATURE: Quantity(428.15, KELVIN),
}

SOLVED = {
    "body_temperature": Quantity(320.0, KELVIN),
    "dissipated_power": Quantity(2.0, WATT),
}


def test_the_falsified_condition_is_gone():
    """It was measured, it failed, and it is not coming back quietly.

    Wiring `self_heating_resistance_drift_ratio` into the electro-thermal
    boundary put it at 17.85 on the shipped example — a correct design — for
    the reason the module docstring sets out: the coupled run solves at the
    converged R(T), so the drift was a modelled effect reported as an
    unmodelled one. Nothing here declares it, reads it or reserves its name.
    """
    for model in app.APPLICABILITY_MODELS:
        for condition in model.validity.conditions:
            assert "drift" not in condition.name
        for spec in model.inputs:
            assert spec.name not in {"resistance_tolerance", "operating_resistance"}
    assert not hasattr(app, "self_heating_resistance_drift_ratio")
    assert not hasattr(app, "RESISTANCE_TOLERANCE")
    assert "self_heating_resistance_drift_ratio" not in app.ASSEMBLER_NAMESPACE


# =====================================================================
# element_hot_spot_utilization
# =====================================================================
#
# A TO-220 power resistor: 6.5 K/W element-to-case, permissible element
# temperature 155 C = 428.15 K. The body converged to 320 K, and 2 W across
# 6.5 K/W puts the element 13 K above it, at 333 K — 0.778 of the limit.


def test_element_hot_spot_in_domain():
    assessment = app.assess_self_heated_resistor_validity(
        _problem(**HOT_SPOT_DECLARED),
        **SOLVED,
    )
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert app.ELEMENT_HOT_SPOT_UTILIZATION in assessment.satisfied

    value = app.element_hot_spot_utilization(
        **SOLVED, **HOT_SPOT_DECLARED
    )
    assert value.magnitude == pytest.approx((320.0 + 13.0) / 428.15)


def test_element_hot_spot_outside_validated_domain():
    """The body is inside its limit and the element is not.

    This is the whole reason the condition exists. At a body temperature of
    420 K — still below the 428.15 K the element permits — 2 W across 6.5 K/W
    puts the film at 433 K, above it. A condition reading the body, or reading
    the declared ambient, cannot see that.
    """
    hot_body = dict(SOLVED, body_temperature=Quantity(420.0, KELVIN))
    assessment = app.assess_self_heated_resistor_validity(
        _problem(**HOT_SPOT_DECLARED),
        **hot_body,
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == (app.ELEMENT_HOT_SPOT_UTILIZATION,)
    assert app.element_hot_spot_utilization(
        **hot_body, **HOT_SPOT_DECLARED
    ).magnitude > 1.0


@pytest.mark.parametrize(
    "withheld",
    [
        app.ELEMENT_TO_BODY_THERMAL_RESISTANCE,
        app.PERMISSIBLE_ELEMENT_TEMPERATURE,
    ],
)
def test_element_hot_spot_unknown_when_a_declaration_is_missing(withheld):
    """Neither half of the pair can be inferred from the other."""
    partial = {k: v for k, v in HOT_SPOT_DECLARED.items() if k != withheld}
    assessment = app.assess_self_heated_resistor_validity(
        _problem(**partial),
        **SOLVED,
    )
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.unknown == (app.ELEMENT_HOT_SPOT_UTILIZATION,)


def test_element_hot_spot_unknown_when_the_run_supplied_no_temperature():
    """A declared thermal resistance with nothing to add it to."""
    assessment = app.assess_self_heated_resistor_validity(
        _problem(**HOT_SPOT_DECLARED),
        dissipated_power=Quantity(2.0, WATT),
    )
    assert assessment.unknown == (app.ELEMENT_HOT_SPOT_UTILIZATION,)


def test_a_bare_number_is_not_a_declaration():
    """The wrong type is a specification error, not a silent UNKNOWN."""
    with pytest.raises(InvalidScientificProblem):
        app.element_hot_spot_utilization(
            body_temperature=Quantity(320.0, KELVIN),
            dissipated_power=Quantity(2.0, WATT),
            element_to_body_thermal_resistance=6.5,
            permissible_element_temperature=Quantity(428.15, KELVIN),
        )


def test_a_wrong_dimension_is_refused():
    """An ambient-referenced thermal resistance is the wrong number here, and
    a thermal resistance in the wrong units is not even a number."""
    with pytest.raises(Exception):
        app.element_hot_spot_utilization(
            body_temperature=Quantity(320.0, KELVIN),
            dissipated_power=Quantity(2.0, WATT),
            element_to_body_thermal_resistance=Quantity(6.5, OHM),
            permissible_element_temperature=Quantity(428.15, KELVIN),
        )


# =====================================================================
# Nothing is satisfied by omission
# =====================================================================

def test_an_empty_declaration_leaves_every_condition_unknown():
    """The rule that holds across the whole platform, asserted here too.

    Supplying a declaration can move a condition off UNKNOWN. Omitting one can
    never move it onto IN_DOMAIN.
    """
    source = app.assess_regulated_source_validity(_problem())
    assert source.status is ValidityStatus.UNKNOWN
    assert source.satisfied == () and source.violated == ()

    resistor = app.assess_self_heated_resistor_validity(_problem())
    assert resistor.status is ValidityStatus.UNKNOWN
    assert resistor.satisfied == () and resistor.violated == ()
    assert set(resistor.unknown) == {app.ELEMENT_HOT_SPOT_UTILIZATION}
