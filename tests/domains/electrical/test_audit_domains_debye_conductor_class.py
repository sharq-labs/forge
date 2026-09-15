"""Audit CAP-05 (c): the Bloch-Grueneisen/Debye floor is a statement about elemental metals.

``reduced_debye_temperature`` (T_coldest / theta_D >= 1/3) and its two
limit-versus-limit siblings rest on the Bloch-Grueneisen form of an elemental
metal's phonon-limited resistivity. They were evaluated for any conductor that
declared a Debye temperature -- including the flagship example, a thick-film
TO-220 part declared with copper's 343 K. A thick film on alumina, an alloy or
a semiconductor is not described by that argument.

Lead decision (declaring is asserting): ``conductor_class`` is optional. A
declared class other than ``elemental_metal`` makes the three Debye conditions
UNKNOWN and the Debye temperature unused. With no class declared, declaring a
Debye temperature is the caller's explicit assertion of an elemental metal: the
conditions answer, and the assertion is recorded in the report as
``asserted_conductor_class = elemental_metal`` asserted by the
``debye_temperature`` declaration.
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


def test_an_undeclared_class_answers_on_the_asserted_elemental_metal() -> None:
    assessment = _assess(None)
    assert set(DEBYE_CONDITIONS) <= set(assessment.satisfied)
    assert mat.REDUCED_DEBYE_TEMPERATURE in _assess(None, temperature=100.0).violated


def test_a_declared_non_elemental_class_is_not_refused_on_a_floor_that_does_not_apply() -> None:
    assert not (set(DEBYE_CONDITIONS) & set(_assess("thick_film", temperature=100.0).violated))


def test_the_assertion_is_recorded_and_says_what_made_it() -> None:
    asserted = mat.conductor_class_assertion(
        mat.MaterialLimits(debye_temperature=Q(343.0, "kelvin"))
    )
    assert asserted["asserted_conductor_class"] == mat.ELEMENTAL_METAL
    assert asserted["asserted_by"] == "debye_temperature declaration"
    declared = mat.conductor_class_assertion(mat.MaterialLimits(conductor_class="thick_film"))
    assert declared["conductor_class"] == "thick_film" and declared["basis"] == "declared"
    assert mat.conductor_class_assertion(mat.MaterialLimits()) is None
    text = " ".join(
        c.description for c in mat.RATED_LINEAR_TCR_MODEL.validity.conditions
        if c.name == mat.REDUCED_DEBYE_TEMPERATURE
    )
    assert "asserted by debye_temperature declaration" in text


def test_the_report_carries_the_assertion() -> None:
    import copy

    from engcore.mcp.problem import example_electrothermal_payload, run_electrothermal_case

    payload = copy.deepcopy(example_electrothermal_payload())
    payload["stages"][0]["conductor"]["limits"] = {"debye_temperature": "343 kelvin"}
    report = run_electrothermal_case(payload, run_id="asserted").reports[0]
    records = [d for d in report.declarations if d.source.startswith("MaterialLimits.conductor_class")]
    assert len(records) == 1
    assert records[0].payload["asserted_conductor_class"] == "elemental_metal"
    assert records[0].consumed_by_verdict is True
    # The flagship thick-film example declares no Debye limits and asserts nothing.
    shipped = run_electrothermal_case(example_electrothermal_payload(), run_id="shipped").reports[0]
    assert not [d for d in shipped.declarations if d.source.startswith("MaterialLimits.conductor_class")]


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


def test_the_public_derivation_withholds_the_floor_for_a_declared_non_elemental_class() -> None:
    """Not only the rated context: ``derived_material_quantities`` is public and
    is called directly (the Contract Integrity nominals do), so it gates too."""
    base = {
        mat.REFERENCE_TEMPERATURE: Q(293.15, "kelvin"),
        mat.TEMPERATURE_COEFFICIENT: Q(0.00393, "1/kelvin"),
        mat.DEBYE_TEMPERATURE: Q(343.0, "kelvin"),
    }
    t = Q(320.0, "kelvin")
    assert mat.REDUCED_DEBYE_TEMPERATURE in mat.derived_material_quantities(base, temperature=t)
    assert mat.REDUCED_DEBYE_TEMPERATURE not in mat.derived_material_quantities(
        {**base, mat.CONDUCTOR_CLASS: "thick_film"}, temperature=t
    )
    assert mat.REDUCED_DEBYE_TEMPERATURE in mat.derived_material_quantities(
        {**base, mat.CONDUCTOR_CLASS: mat.ELEMENTAL_METAL}, temperature=t
    )
