"""F6 (hostile review, HIGH): a physically impossible coupled state is refused, not reported.

The reproduced defect: the coupled drone hover screening accepted a declared
power coefficient of 0.002, whose rotor absorbs about 1/14.55 of the ideal
induced power of momentum theory (figure of merit 14.55 > 1). The fixture values
are ILLUSTRATIVE (as in test_drone_coupled_hover.py), not product data, and an
admissible state is a necessary condition, never evidence.
"""

from __future__ import annotations

import math

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity as Q
from engcore.systems.admissibility import (
    AdmissibilityStatus, InvariantRelation, PhysicalInvariant, PhysicallyInadmissible, evaluate_invariant, require_admissible,
)
from engcore.systems.products import TemplateRefusal, coupled_hover_screening
from engcore.systems.products.drone_coupled import _declared, hover_power_floor
from tests.foundations.test_drone_coupled_hover import VALUES, template

CT = VALUES["prop_thrust_coefficient"].magnitude_in("dimensionless")
#: C_P at which the declared propeller is exactly an ideal actuator disk (FM = 1): C_T^(3/2) / sqrt(pi / 2)
CP_IDEAL = CT ** 1.5 / math.sqrt(math.pi / 2)


def _floor(**changes):
    return hover_power_floor(_declared(template(**changes)))


def test_the_normal_fixture_is_admissible_and_reports_the_check() -> None:
    result = coupled_hover_screening(template())
    (check,) = result["physical_admissibility"]
    assert check["status"] == "admissible" and check["invariant_id"] == "rotor.hover.momentum_theory_power_floor"
    figure_of_merit = 1 / check["ratio"]
    assert figure_of_merit == pytest.approx(CT ** 1.5 / (0.045 * math.sqrt(math.pi / 2)))
    assert 0 < figure_of_merit < 1


def test_the_exact_ideal_rotor_is_admissible() -> None:
    evaluation = _floor(prop_power_coefficient=Q(CP_IDEAL, "dimensionless"))
    assert evaluation.status is AdmissibilityStatus.ADMISSIBLE
    assert evaluation.ratio == pytest.approx(1.0, rel=1e-12)
    coupled_hover_screening(template(prop_power_coefficient=Q(CP_IDEAL, "dimensionless")))


def test_slightly_beyond_the_ideal_rotor_is_refused() -> None:
    beyond = Q(CP_IDEAL * (1 - 1e-6), "dimensionless")
    assert _floor(prop_power_coefficient=beyond).status is AdmissibilityStatus.INADMISSIBLE
    with pytest.raises(TemplateRefusal, match="physically inadmissible"):
        coupled_hover_screening(template(prop_power_coefficient=beyond))


def test_the_hostile_review_case_figure_of_merit_14_55_is_refused() -> None:
    hostile = Q(0.002, "dimensionless")
    evaluation = _floor(prop_power_coefficient=hostile)
    assert evaluation.status is AdmissibilityStatus.INADMISSIBLE
    assert 1 / evaluation.ratio == pytest.approx(14.554560428103372, rel=1e-9)
    with pytest.raises(TemplateRefusal, match="momentum_theory_power_floor"):
        coupled_hover_screening(template(prop_power_coefficient=hostile))


@pytest.mark.parametrize("cp, admissible", [(0.045, True), (CP_IDEAL, True), (0.002, False)])
def test_unit_converted_declarations_give_the_same_answer(cp, admissible) -> None:
    converted = dict(takeoff_mass=Q(1500, "g"), rotor_diameter=Q(10, "inch"), air_density=Q(1.225, "g/L"),
                     gravity=Q(980.665, "cm/s^2"), prop_power_coefficient=Q(cp, "dimensionless"))
    si = _floor(prop_power_coefficient=Q(cp, "dimensionless"))
    other = _floor(**converted)
    assert other.status is si.status
    assert (other.status is AdmissibilityStatus.ADMISSIBLE) is admissible
    assert other.ratio == pytest.approx(si.ratio, rel=1e-12)


# ---- the generic mechanism knows no physics --------------------------------------------------------------

LAW = PhysicalInvariant("test.efficiency_at_most_one", "an efficiency is at most one", "energy conservation",
                        InvariantRelation.AT_MOST)


def test_the_mechanism_compares_in_the_bounds_unit_and_refuses_incompatible_units() -> None:
    assert evaluate_invariant(LAW, Q(99, "percent"), Q(1, "dimensionless")).status is AdmissibilityStatus.ADMISSIBLE
    assert evaluate_invariant(LAW, Q(101, "percent"), Q(1, "dimensionless")).status is AdmissibilityStatus.INADMISSIBLE
    with pytest.raises(InvalidScientificProblem, match="incompatible units"):
        evaluate_invariant(LAW, Q(1, "W"), Q(1, "dimensionless"))


def test_round_off_at_the_boundary_is_not_a_violation_but_anything_more_is() -> None:
    assert evaluate_invariant(LAW, Q(1 + 1e-15, "dimensionless"), Q(1, "dimensionless")).status is AdmissibilityStatus.ADMISSIBLE
    assert evaluate_invariant(LAW, Q(1 + 1e-9, "dimensionless"), Q(1, "dimensionless")).status is AdmissibilityStatus.INADMISSIBLE


def test_unknown_never_admits() -> None:
    unknown = evaluate_invariant(LAW, None, Q(1, "dimensionless"))  # the system could not compute the value
    assert unknown.status is AdmissibilityStatus.UNKNOWN
    with pytest.raises(PhysicallyInadmissible, match="unknown"):
        require_admissible([unknown])
    with pytest.raises(PhysicallyInadmissible):
        require_admissible([evaluate_invariant(LAW, Q(2, "dimensionless"), Q(1, "dimensionless"))])
    assert require_admissible([evaluate_invariant(LAW, Q(0.5, "dimensionless"), Q(1, "dimensionless"))])


def test_an_invariant_must_say_what_law_it_is_and_where_it_comes_from() -> None:
    with pytest.raises(InvalidScientificProblem):
        PhysicalInvariant("x", "", "basis", InvariantRelation.AT_LEAST)
    with pytest.raises(InvalidScientificProblem):
        PhysicalInvariant("x", "law", " ", InvariantRelation.AT_LEAST)
