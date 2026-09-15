"""Audit CAP-05 (c): the Bloch-Grueneisen/Debye floor is a statement about elemental metals.

``reduced_debye_temperature`` (T_coldest / theta_D >= 1/3) and its two
limit-versus-limit siblings rest on the Bloch-Grueneisen form of an elemental
metal's phonon-limited resistivity. They were evaluated for any conductor that
declared a Debye temperature -- including the flagship example, a thick-film
TO-220 part declared with copper's 343 K. A thick film on alumina, an alloy or
a semiconductor is not described by that argument, so the floor now answers
only for a conductor DECLARED as an elemental metal and is UNKNOWN otherwise,
including when no class is declared.
"""

from __future__ import annotations

import pytest

from engcore.domains.electrical import material as mat
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.units.quantity import Quantity as Q

DEBYE_CONDITIONS = (
    mat.REDUCED_DEBYE_TEMPERATURE,
    mat.REFERENCE_REDUCED_DEBYE_TEMPERATURE,
    mat.CEILING_REDUCED_DEBYE_TEMPERATURE,
)


def _problem(conductor_class):
    conductor = mat.TemperatureDependentConductor(
        component_id="R1",
        reference_resistance=Q(10.0, "ohm"),
        temperature_coefficient=Q(0.00393, "1/kelvin"),
        reference_temperature=Q(293.15, "kelvin"),
        limits=mat.MaterialLimits(
            linearization_band=Q(80.0, "kelvin"),
            maximum_operating_temperature=Q(400.0, "kelvin"),
            debye_temperature=Q(343.0, "kelvin"),
            conductor_class=conductor_class,
        ),
    )
    return mat.build_resistance_problem(conductor)


def _assess(conductor_class, temperature=320.0):
    t = Q(temperature, "kelvin")
    return mat.assess_rated_resistance_validity(_problem(conductor_class), t, t, t)


def test_a_declared_elemental_metal_gets_the_debye_floor_evaluated() -> None:
    assessment = _assess(mat.ELEMENTAL_METAL)
    assert set(DEBYE_CONDITIONS) <= set(assessment.satisfied)
    assert assessment.status is ValidityStatus.IN_DOMAIN


def test_the_floor_still_fires_for_an_elemental_metal_below_it() -> None:
    # 100 K / 343 K = 0.29 < 1/3.
    assessment = _assess(mat.ELEMENTAL_METAL, temperature=100.0)
    assert mat.REDUCED_DEBYE_TEMPERATURE in assessment.violated


@pytest.mark.parametrize("conductor_class", ["thick_film", "alloy", "metal_film", "semiconductor"])
def test_a_non_elemental_conductor_leaves_every_debye_condition_unknown(conductor_class) -> None:
    assessment = _assess(conductor_class)
    assert set(DEBYE_CONDITIONS) <= set(assessment.unknown)
    assert not (set(DEBYE_CONDITIONS) & set(assessment.satisfied))
    assert assessment.status is ValidityStatus.UNKNOWN


def test_an_undeclared_class_leaves_every_debye_condition_unknown() -> None:
    assessment = _assess(None)
    assert set(DEBYE_CONDITIONS) <= set(assessment.unknown)
    # Nor can a non-elemental conductor be refused on a floor that does not apply.
    assert not (set(DEBYE_CONDITIONS) & set(_assess(None, temperature=100.0).violated))


def test_an_unknown_class_is_refused_at_declaration() -> None:
    with pytest.raises(InvalidScientificProblem):
        mat.MaterialLimits(conductor_class="unobtainium")


def test_the_class_round_trips_and_is_absent_from_bytes_when_undeclared() -> None:
    declared = mat.MaterialLimits(
        debye_temperature=Q(343.0, "kelvin"), conductor_class=mat.ELEMENTAL_METAL
    )
    assert mat.MaterialLimits.from_dict(declared.to_dict()) == declared
    assert "conductor_class" not in mat.MaterialLimits(
        debye_temperature=Q(343.0, "kelvin")
    ).to_dict()
