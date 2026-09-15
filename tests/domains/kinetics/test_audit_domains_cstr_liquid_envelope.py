"""Audit CAP-01: the CSTR's single-phase-liquid claim is tied to the declared fluid.

The model states "single liquid phase ... no boiling". Before this fix the only
temperature conditions were a fluid-independent 250-1000 K band, so a
water-like reactor fed at 700 K -- above water's critical point -- was reported
IN_DOMAIN, and a water-like reactor whose adiabatic ceiling is 503 K was
IN_DOMAIN at atmospheric pressure, where water boils at 373 K.

The liquid envelope now reads the fluid's own declared boiling temperature at
the operating pressure and its freezing temperature:

* undeclared -> the phase conditions are UNKNOWN, so no IN_DOMAIN without them;
* the declared state, or the adiabatic ceiling, at or above boiling -> OUTSIDE;
* the adiabatic floor at or below freezing -> OUTSIDE;
* both declared and the bounds clear -> IN_DOMAIN.
"""

from __future__ import annotations

import pytest

from engcore.domains.kinetics.cstr import (
    ADIABATIC_CEILING_TEMPERATURE,
    ASSEMBLER_NAMESPACE,
    CSTR_MODEL,
    ReactorChemistry,
    ReactorOperation,
    ReactorRun,
)
from engcore.domains.kinetics.cstr import context as ctx
from engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL
from engcore.domains.kinetics.cstr.errors import ReactorConfigurationError
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.units.quantity import Quantity as Q

PHASE_CONDITIONS = (
    ctx.DECLARED_TEMPERATURE_TO_BOILING_RATIO,
    ctx.CEILING_TO_BOILING_RATIO,
    ctx.FLOOR_TO_FREEZING_RATIO,
)


def water(*, boiling=None, freezing=None) -> ReactorChemistry:
    return ReactorChemistry(
        k0=Q(7.2e10 / 60.0, "1/s"),
        activation_energy=Q(8750.0 * 8.314462618, "J/mol"),
        heat_of_reaction=Q(-5.0e4, "J/mol"),
        density=Q(1000.0, "kg/m**3"),
        heat_capacity=Q(4184.0, "J/(kg*K)"),
        boiling_temperature=None if boiling is None else Q(boiling, "kelvin"),
        freezing_temperature=None if freezing is None else Q(freezing, "kelvin"),
    )


def run(chemistry, *, tf, tc, caf, t0, ca0=None) -> ReactorRun:
    return ReactorRun(
        run_label="cap01",
        chemistry=chemistry,
        operation=ReactorOperation(
            volume=Q(0.1, "m**3"),
            flow_rate=Q(0.1 / 60.0, "m**3/s"),
            feed_concentration=Q(caf, "mol/m**3"),
            feed_temperature=Q(tf, "kelvin"),
            coolant_temperature=Q(tc, "kelvin"),
            ua=Q(5.0e4 / 60.0, "W/K"),
            end_time=Q(1800.0, "second"),
        ),
        initial_concentration=Q(caf if ca0 is None else ca0, "mol/m**3"),
        initial_temperature=Q(t0, "kelvin"),
    )


def test_supercritical_water_like_reactor_is_not_in_domain_without_a_boiling_point() -> None:
    # s5_cstr.py: feed 700 K, ceiling 723.9 K, formerly IN_DOMAIN.
    assessment = run(water(), tf=700.0, tc=690.0, caf=2000.0, t0=700.0).validity_context().assess(CSTR_MODEL)
    assert assessment.status is not ValidityStatus.IN_DOMAIN
    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(PHASE_CONDITIONS) <= set(assessment.unknown)


def test_undeclared_fluid_is_unknown_on_every_phase_condition_even_when_cool() -> None:
    assessment = run(water(), tf=300.0, tc=295.0, caf=10.0, t0=300.0).validity_context().assess(CSTR_MODEL)
    assert assessment.status is ValidityStatus.UNKNOWN
    assert set(PHASE_CONDITIONS) <= set(assessment.unknown)


def test_water_at_one_atmosphere_whose_ceiling_passes_boiling_is_outside() -> None:
    # s5_cstr.py: feed 360 K, ceiling 503 K, formerly IN_DOMAIN.
    r = run(water(boiling=373.15, freezing=273.15), tf=360.0, tc=350.0, caf=12000.0, t0=360.0)
    assessment = r.validity_context().assess(CSTR_MODEL)
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert ctx.CEILING_TO_BOILING_RATIO in assessment.violated
    # The declared state itself is below boiling; only the reachable ceiling is not.
    assert ctx.DECLARED_TEMPERATURE_TO_BOILING_RATIO in assessment.satisfied


def test_a_declared_state_already_boiling_is_outside_on_the_exact_condition() -> None:
    r = run(water(boiling=373.15, freezing=273.15), tf=380.0, tc=300.0, caf=0.0, t0=300.0)
    assessment = r.validity_context().assess(CSTR_MODEL)
    assert ctx.DECLARED_TEMPERATURE_TO_BOILING_RATIO in assessment.violated
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_exactly_at_boiling_is_not_liquid() -> None:
    r = run(water(boiling=373.15, freezing=273.15), tf=373.15, tc=300.0, caf=0.0, t0=300.0)
    assessment = r.validity_context().assess(CSTR_MODEL)
    assert ctx.DECLARED_TEMPERATURE_TO_BOILING_RATIO in assessment.violated


def test_pressurised_fluid_well_below_its_boiling_point_is_in_domain() -> None:
    r = run(water(boiling=600.0, freezing=273.15), tf=360.0, tc=350.0, caf=12000.0, t0=360.0)
    assessment = r.validity_context().assess(CSTR_MODEL)
    assert set(PHASE_CONDITIONS) <= set(assessment.satisfied)
    assert assessment.status is ValidityStatus.IN_DOMAIN


def test_below_the_declared_freezing_point_is_outside() -> None:
    # 260 K is inside the fluid-independent 250-1000 K band and below water's 273 K.
    r = run(water(boiling=373.15, freezing=273.15), tf=300.0, tc=260.0, caf=0.0, t0=300.0)
    assessment = r.validity_context().assess(CSTR_MODEL)
    assert ctx.FLOOR_TO_FREEZING_RATIO in assessment.violated
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_endothermic_floor_reaches_freezing_even_when_every_declared_temperature_is_liquid() -> None:
    chem = ReactorChemistry(
        k0=Q(1.0, "1/s"),
        activation_energy=Q(0.0, "J/mol"),
        heat_of_reaction=Q(+5.0e4, "J/mol"),       # endothermic: beta < 0
        density=Q(1000.0, "kg/m**3"),
        heat_capacity=Q(4184.0, "J/(kg*K)"),
        boiling_temperature=Q(373.15, "kelvin"),
        freezing_temperature=Q(273.15, "kelvin"),
    )
    # |beta| C_max = 5e4 / 4.184e6 * 3000 = 35.9 K; floor = 290 - 35.9 = 254 K.
    r = run(chem, tf=300.0, tc=290.0, caf=3000.0, t0=300.0)
    assessment = r.validity_context().assess(CSTR_MODEL)
    assert ctx.FLOOR_TO_FREEZING_RATIO in assessment.violated


def test_the_competitor_model_claims_the_same_liquid_and_checks_it() -> None:
    names = {c.name for c in CONSTANT_RATE_CSTR_MODEL.validity.conditions}
    assert set(PHASE_CONDITIONS) <= names
    assessment = run(water(), tf=700.0, tc=690.0, caf=2000.0, t0=700.0).validity_context().assess(
        CONSTANT_RATE_CSTR_MODEL
    )
    assert assessment.status is not ValidityStatus.IN_DOMAIN


@pytest.mark.parametrize("boiling, freezing", [(273.15, 273.15), (250.0, 300.0)])
def test_a_freezing_point_not_below_the_boiling_point_is_refused(boiling, freezing) -> None:
    with pytest.raises(ReactorConfigurationError):
        water(boiling=boiling, freezing=freezing)


def test_the_caller_cannot_assert_a_phase_ratio() -> None:
    r = run(water(), tf=300.0, tc=295.0, caf=10.0, t0=300.0)
    declared = dict(r.validity_context())
    declared[ctx.CEILING_TO_BOILING_RATIO] = Q(0.1, "dimensionless")
    declared[ctx.DECLARED_TEMPERATURE_TO_BOILING_RATIO] = Q(0.1, "dimensionless")
    declared[ctx.FLOOR_TO_FREEZING_RATIO] = Q(10.0, "dimensionless")
    assembled = ctx.cstr_validity_context(declared, reserved=ASSEMBLER_NAMESPACE)
    verdict = assembled.assess(CSTR_MODEL)
    assert set(PHASE_CONDITIONS) <= set(verdict.unknown)
    assert verdict.status is ValidityStatus.UNKNOWN


def test_the_ceiling_condition_no_longer_claims_to_establish_the_liquid_phase() -> None:
    by_name = {c.name: c for c in CSTR_MODEL.validity.conditions}
    for name in ("temperature", ADIABATIC_CEILING_TEMPERATURE):
        text = by_name[name].description.lower()
        assert "single-phase liquid with constant properties and no boiling" not in text
    # The liquid claim is carried by the conditions that read the fluid.
    assert "boiling" in by_name[ctx.CEILING_TO_BOILING_RATIO].description.lower()
