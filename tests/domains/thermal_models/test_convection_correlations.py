"""The convection correlations, and the three conditions they support.

Before this file, ``ambient_conductance`` was a number the caller supplied and
nothing asked where it came from — while Biot, both excursion budgets and the
radiation ratio were all computed *from* it. An hA wrong by a factor of two
moved every one of them by a factor of two and none of them said anything.

What is tested here:

* the correlations reproduce hand-computed values, so a refactor cannot quietly
  change a constant;
* the ranges each source states are the bounds, on both sides, with no epsilon;
* the route is selected by the *declaration*, never by ``convection_regime``;
* declaring both routes is refused rather than silently resolved;
* every one of the six new fields is optional, and omitting any of them yields
  UNKNOWN and never IN_DOMAIN.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from src.engcore.domains.thermal_models import context as ctx
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.units.quantity import Quantity

Q = Quantity
K = "kelvin"

#: Air near 300 K. The viscosity and the Prandtl number are the fluid's; the
#: conductivity is the one that makes the correlation reproduce the declared
#: hA exactly, which is what a caller who did the sum would have.
NU = 1.589e-5
PR = 0.707

#: The body every applicability test in this package uses: hA = 0.05 W/K over
#: A_s = 0.01 m^2, so h = 5 W/(m^2 K).
DECLARED_H = 5.0

FORCED = ctx.LumpedApplicabilityDeclaration(
    characteristic_length=Q(0.002, "meter"),
    surface_area=Q(0.01, "meter**2"),
    body_conductivity=Q(200.0, "watt/meter/kelvin"),
    surface_emissivity=Q(0.05, "dimensionless"),
    convection_regime=ctx.FORCED_CONVECTION,
    conductance_excursion_bound=Q(60.0, K),
    capacity_excursion_bound=Q(100.0, K),
    melting_temperature=Q(900.0, K),
    fluid_conductivity=Q(0.0261, "watt/meter/kelvin"),
    fluid_kinematic_viscosity=Q(NU, "meter**2/second"),
    fluid_prandtl_number=Q(PR, "dimensionless"),
    fluid_velocity=Q(1.0, "meter/second"),
    convection_length=Q(0.6, "meter"),
)

#: The same body under free convection. beta = 2/(T_s + T_inf) for an ideal gas
#: at the film temperature, with T_ss = 320 K and T_amb = 300 K.
NATURAL = dataclasses.replace(
    FORCED,
    convection_regime=ctx.NATURAL_CONVECTION,
    fluid_velocity=None,
    fluid_expansion_coefficient=Q(2.0 / 620.0, "1/kelvin"),
    convection_length=Q(0.08, "meter"),
    fluid_conductivity=Q(0.02418015, "watt/meter/kelvin"),
)

AMBIENT = Q(300.0, K)
INITIAL = Q(300.0, K)
HEAT_INPUT = Q(1.0, "watt")


def body(declaration):
    return lump.ThermalBody(
        body_id="B1",
        heat_capacity=Q(2.5, "joule/kelvin"),
        ambient_conductance=Q(0.05, "watt/kelvin"),
        ambient_temperature=AMBIENT,
        initial_temperature=INITIAL,
        duration=Q(120.0, "second"),
        applicability=declaration,
    )


def assess(declaration, *, heat_input=HEAT_INPUT):
    return lump.assess_lumped_validity(
        lump.build_lumped_thermal_problem(body(declaration)),
        initial_temperature=INITIAL,
        ambient_temperature=AMBIENT,
        heat_input=heat_input,
    )


def status_of(declaration, condition, **kwargs):
    result = assess(declaration, **kwargs)
    for names, verdict in (
        (result.satisfied, ValidityStatus.IN_DOMAIN),
        (result.violated, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
        (result.unknown, ValidityStatus.UNKNOWN),
    ):
        if condition in names:
            return verdict
    raise AssertionError(f"{condition!r} was not assessed")


def group(declaration, name, **kwargs):
    context = lump.lumped_validity_context(
        lump.build_lumped_thermal_problem(body(declaration)),
        initial_temperature=INITIAL,
        ambient_temperature=AMBIENT,
        heat_input=kwargs.get("heat_input", HEAT_INPUT),
    )
    value = context.get(name)
    return None if value is None else value.magnitude_in("dimensionless")


# =====================================================================
# The correlations reproduce hand-computed numbers
# =====================================================================

def test_the_rayleigh_number_matches_its_definition() -> None:
    """Ra = g beta dT L^3 Pr / nu^2, computed here independently."""
    beta, length, dt = 2.0 / 620.0, 0.08, 20.0
    expected = 9.80665 * beta * dt * length ** 3 * PR / NU ** 2
    value = ctx.rayleigh_number(
        expansion_coefficient=Q(beta, "1/kelvin"),
        temperature_difference=Q(dt, K),
        length=Q(length, "meter"),
        kinematic_viscosity=Q(NU, "meter**2/second"),
        prandtl_number=Q(PR, "dimensionless"),
    )
    assert value.magnitude_in("dimensionless") == pytest.approx(
        expected, rel=1e-12
    )


def test_the_reynolds_number_matches_its_definition() -> None:
    value = ctx.reynolds_number(
        velocity=Q(1.0, "meter/second"),
        length=Q(0.6, "meter"),
        kinematic_viscosity=Q(NU, "meter**2/second"),
    )
    assert value.magnitude_in("dimensionless") == pytest.approx(
        0.6 / NU, rel=1e-12
    )


def test_churchill_chu_reproduces_its_printed_form() -> None:
    """Nu = 0.68 + 0.670 Ra^(1/4) / [1 + (0.492/Pr)^(9/16)]^(4/9).

    Churchill & Chu (1975); Incropera 6th ed. Eq. 9.27. Written out here
    independently so a changed constant in the domain fails rather than
    propagating.
    """
    for ra in (1.0e3, 1.0e6, 1.0e9):
        expected = 0.68 + 0.670 * ra ** 0.25 / (
            1.0 + (0.492 / PR) ** (9.0 / 16.0)
        ) ** (4.0 / 9.0)
        value = ctx.churchill_chu_nusselt(
            rayleigh=Q(ra, "dimensionless"),
            prandtl_number=Q(PR, "dimensionless"),
        )
        assert value.magnitude_in("dimensionless") == pytest.approx(
            expected, rel=1e-12
        )


def test_churchill_chu_approaches_its_conduction_limit() -> None:
    """Nu -> 0.68 as Ra -> 0, which is why there is no lower bound."""
    value = ctx.churchill_chu_nusselt(
        rayleigh=Q(0.0, "dimensionless"),
        prandtl_number=Q(PR, "dimensionless"),
    )
    assert value.magnitude_in("dimensionless") == pytest.approx(0.68)


def test_the_flat_plate_correlation_reproduces_its_printed_form() -> None:
    """Nu = 0.664 Re^(1/2) Pr^(1/3). Incropera 6th ed. Eq. 7.30."""
    for re in (1.0e2, 1.0e4, 5.0e5):
        expected = 0.664 * re ** 0.5 * PR ** (1.0 / 3.0)
        value = ctx.flat_plate_nusselt(
            reynolds=Q(re, "dimensionless"),
            prandtl_number=Q(PR, "dimensionless"),
        )
        assert value.magnitude_in("dimensionless") == pytest.approx(
            expected, rel=1e-12
        )


def test_the_fixtures_reproduce_the_declared_conductance() -> None:
    """Both routes predict h = 5 W/(m^2 K) to within a fraction of a percent.

    Not a tautology: it is the check that these fixtures are what they claim to
    be, and it is what makes the agreement-ratio tests below meaningful.
    """
    for declaration in (FORCED, NATURAL):
        ratio = group(declaration, ctx.CONVECTION_AGREEMENT_RATIO)
        assert ratio == pytest.approx(1.0, rel=0.01)


# =====================================================================
# The bounds are where the sources put them, on both sides
# =====================================================================

def test_the_rayleigh_ceiling_is_the_laminar_transition() -> None:
    assert ctx.CHURCHILL_CHU_LAMINAR_RAYLEIGH_CEILING.magnitude_in(
        "dimensionless"
    ) == 1.0e9


def test_the_reynolds_ceiling_is_the_flat_plate_transition() -> None:
    assert ctx.FLAT_PLATE_LAMINAR_REYNOLDS_CEILING.magnitude_in(
        "dimensionless"
    ) == 5.0e5


def test_leaving_the_laminar_range_is_the_finding() -> None:
    """1 % inside is accepted, 1 % outside refused, on both routes.

    This is the point of the task, more than the coefficient check: a
    coefficient taken from a correlation read past its own stated range has
    nothing behind it, and agreement between two unsupported numbers repairs
    nothing.

    The bound itself is exercised a line at a time rather than by aiming at it:
    placing a case *exactly* on 1e9 through a cube root is a test of floating
    point, not of the condition. Inclusivity is asserted directly from the
    record in :func:`test_the_range_bounds_are_inclusive`.
    """
    # Free convection: Ra goes as L^3, so scale the length by the cube root.
    base_ra = group(NATURAL, ctx.CONVECTION_FLOW_RANGE) * 1.0e9
    for factor, expected in (
        (0.99, ValidityStatus.IN_DOMAIN),
        (1.01, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
    ):
        scale = (1.0e9 * factor / base_ra) ** (1.0 / 3.0)
        stretched = dataclasses.replace(
            NATURAL,
            convection_length=Q(
                NATURAL.convection_length.magnitude_in("meter") * scale, "meter"
            ),
        )
        assert status_of(stretched, ctx.CONVECTION_FLOW_RANGE) is expected

    # Forced convection: Re is linear in the velocity.
    base_re = group(FORCED, ctx.CONVECTION_FLOW_RANGE) * 5.0e5
    for factor, expected in (
        (0.99, ValidityStatus.IN_DOMAIN),
        (1.01, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
    ):
        faster = dataclasses.replace(
            FORCED,
            fluid_velocity=Q(
                FORCED.fluid_velocity.magnitude_in("meter/second")
                * (5.0e5 * factor / base_re),
                "meter/second",
            ),
        )
        assert status_of(faster, ctx.CONVECTION_FLOW_RANGE) is expected


def test_the_range_bounds_are_inclusive() -> None:
    """Read off the record, not aimed at through a cube root.

    A utilization of exactly 1 is the edge the source printed, and the edge is
    inside. Every other RangeCondition in this domain is inclusive for the same
    reason and none of them applies an epsilon.
    """
    for name in (ctx.CONVECTION_FLOW_RANGE, ctx.CONVECTION_PROPERTY_RANGE):
        condition = next(
            c for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
            if c.name == name
        )
        assert condition.maximum_inclusive is True
        assert condition.evaluate(
            Q(1.0, "dimensionless")
        ) is ValidityStatus.IN_DOMAIN
        assert condition.evaluate(
            Q(1.0 + 1e-12, "dimensionless")
        ) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN

    agreement = next(
        c for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
        if c.name == ctx.CONVECTION_AGREEMENT_RATIO
    )
    assert agreement.minimum_inclusive and agreement.maximum_inclusive
    for edge in (0.5, 2.0):
        assert agreement.evaluate(
            Q(edge, "dimensionless")
        ) is ValidityStatus.IN_DOMAIN


def test_the_prandtl_floor_binds_only_the_forced_route() -> None:
    """Pr >= 0.6 is a restriction of Eq. 7.30 and of nothing else."""
    for prandtl, expected in (
        (0.6 / 0.99, ValidityStatus.IN_DOMAIN),
        (0.6, ValidityStatus.IN_DOMAIN),
        (0.6 / 1.01, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
    ):
        forced = dataclasses.replace(
            FORCED, fluid_prandtl_number=Q(prandtl, "dimensionless")
        )
        assert status_of(forced, ctx.CONVECTION_PROPERTY_RANGE) is expected

    # A liquid metal under FREE convection is in domain on this condition:
    # Churchill-Chu covers every Prandtl number, which is what its
    # (0.492/Pr)^(9/16) denominator is for.
    liquid_metal = dataclasses.replace(
        NATURAL, fluid_prandtl_number=Q(0.01, "dimensionless")
    )
    assert group(liquid_metal, ctx.CONVECTION_PROPERTY_RANGE) == 0.0
    assert (
        status_of(liquid_metal, ctx.CONVECTION_PROPERTY_RANGE)
        is ValidityStatus.IN_DOMAIN
    )


def test_a_coefficient_off_by_a_factor_is_a_finding() -> None:
    """The agreement bound, at its two edges, on both sides of each.

    The convention is a factor of two either way. A declared hA far *below* the
    correlation is the conservative error and far *above* is the dangerous one;
    both are bounded, so both are tested.
    """
    base_k = FORCED.fluid_conductivity.magnitude_in("watt/meter/kelvin")
    base_ratio = group(FORCED, ctx.CONVECTION_AGREEMENT_RATIO)
    for target, expected in (
        (1.99, ValidityStatus.IN_DOMAIN),
        (2.01, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
        (0.503, ValidityStatus.IN_DOMAIN),
        (0.497, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
    ):
        # h_correlated goes as k_f, so the ratio goes as 1/k_f.
        shifted = dataclasses.replace(
            FORCED,
            fluid_conductivity=Q(
                base_k * base_ratio / target, "watt/meter/kelvin"
            ),
        )
        assert group(shifted, ctx.CONVECTION_AGREEMENT_RATIO) == pytest.approx(
            target, rel=1e-9
        )
        assert status_of(shifted, ctx.CONVECTION_AGREEMENT_RATIO) is expected


def test_the_agreement_factor_is_recorded_as_a_convention() -> None:
    """Two of the three bounds are cited; this one is not, and says so."""
    condition = next(
        c for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
        if c.name == ctx.CONVECTION_AGREEMENT_RATIO
    )
    assert "CONVENTION" in condition.description.upper()

    # And the two range conditions say the opposite, because their numbers are
    # printed by their sources.
    for name in (ctx.CONVECTION_FLOW_RANGE, ctx.CONVECTION_PROPERTY_RANGE):
        text = next(
            c for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
            if c.name == name
        ).description
        assert "Incropera" in text
        assert "Sec." in text


def test_the_range_conditions_introduce_no_number_of_their_own() -> None:
    """Both are utilizations, so their bound is 1 by construction."""
    for name in (ctx.CONVECTION_FLOW_RANGE, ctx.CONVECTION_PROPERTY_RANGE):
        condition = next(
            c for c in lump.LUMPED_CAPACITY_MODEL.validity.conditions
            if c.name == name
        )
        assert condition.maximum == ctx.CORRELATION_RANGE_LIMIT
        assert condition.minimum is None


# =====================================================================
# The route is selected by evidence, never by a category
# =====================================================================

def test_the_declared_regime_still_decides_nothing() -> None:
    """Three declarations differing only in the regime string agree exactly."""
    verdicts = [
        assess(dataclasses.replace(FORCED, convection_regime=regime))
        for regime in (ctx.FORCED_CONVECTION, ctx.NATURAL_CONVECTION, None)
    ]
    assert {v.status for v in verdicts} == {ValidityStatus.IN_DOMAIN}
    groups = [
        group(dataclasses.replace(FORCED, convection_regime=regime),
              ctx.CONVECTION_FLOW_RANGE)
        for regime in (ctx.FORCED_CONVECTION, ctx.NATURAL_CONVECTION, None)
    ]
    assert len(set(groups)) == 1


def test_the_route_follows_the_declaration_not_the_label() -> None:
    """A body labelled 'natural' but declaring a velocity is judged as forced.

    The flow utilization is Re/5e5 either way, because a velocity is what the
    Reynolds number needs and the label is what nothing needs.
    """
    mislabelled = dataclasses.replace(
        FORCED, convection_regime=ctx.NATURAL_CONVECTION
    )
    assert group(mislabelled, ctx.CONVECTION_FLOW_RANGE) == pytest.approx(
        group(FORCED, ctx.CONVECTION_FLOW_RANGE)
    )


def test_declaring_both_routes_is_refused_rather_than_resolved() -> None:
    """Mixed convection, which neither correlation covers.

    Refused at the record rather than reported UNKNOWN: the caller stated
    something this domain cannot judge, which is a different thing from
    leaving something out, and the two must not collapse.
    """
    with pytest.raises(InvalidScientificProblem) as excinfo:
        dataclasses.replace(
            NATURAL, fluid_velocity=Q(1.0, "meter/second")
        )
    assert "mixed convection" in str(excinfo.value)


# =====================================================================
# Optional stays optional: every omission is UNKNOWN, never IN_DOMAIN
# =====================================================================

def test_a_caller_who_declares_only_a_conductance_is_no_worse_off() -> None:
    """The three conditions are UNKNOWN, exactly as before they existed."""
    bare = dataclasses.replace(
        FORCED,
        fluid_conductivity=None,
        fluid_kinematic_viscosity=None,
        fluid_prandtl_number=None,
        fluid_velocity=None,
        convection_length=None,
    )
    result = assess(bare)
    assert set(result.unknown) == {
        ctx.CONVECTION_FLOW_RANGE,
        ctx.CONVECTION_PROPERTY_RANGE,
        ctx.CONVECTION_AGREEMENT_RATIO,
    }
    # Every other condition still decidable and satisfied, so the six new
    # fields cost a caller who declines them nothing beyond honesty.
    assert not result.violated


@pytest.mark.parametrize(
    "dropped",
    [
        "fluid_conductivity",
        "fluid_kinematic_viscosity",
        "fluid_prandtl_number",
        "fluid_velocity",
        "convection_length",
        "surface_area",
    ],
)
def test_omitting_any_forced_route_field_never_yields_in_domain(dropped) -> None:
    crippled = dataclasses.replace(FORCED, **{dropped: None})
    result = assess(crippled)
    assert result.status is ValidityStatus.UNKNOWN
    assert ctx.CONVECTION_AGREEMENT_RATIO in result.unknown
    assert ctx.CONVECTION_AGREEMENT_RATIO not in result.satisfied
    assert ctx.CONVECTION_AGREEMENT_RATIO not in result.violated


@pytest.mark.parametrize(
    "dropped",
    [
        "fluid_conductivity",
        "fluid_kinematic_viscosity",
        "fluid_prandtl_number",
        "fluid_expansion_coefficient",
        "convection_length",
    ],
)
def test_omitting_any_natural_route_field_never_yields_in_domain(
    dropped,
) -> None:
    crippled = dataclasses.replace(NATURAL, **{dropped: None})
    result = assess(crippled)
    assert result.status is ValidityStatus.UNKNOWN
    assert ctx.CONVECTION_AGREEMENT_RATIO in result.unknown


def test_the_natural_route_needs_the_operating_point_and_the_forced_one_does_not(
) -> None:
    """A real asymmetry, not an oversight.

    Ra carries the driving temperature difference; Re does not. A flow-set
    coefficient genuinely does not depend on how hard the surface is driven, so
    a forced declaration stays decidable with no heat input while a free one
    does not.
    """
    forced = assess(FORCED, heat_input=None)
    assert ctx.CONVECTION_FLOW_RANGE in forced.satisfied

    natural = assess(NATURAL, heat_input=None)
    assert ctx.CONVECTION_FLOW_RANGE in natural.unknown
    assert ctx.CONVECTION_AGREEMENT_RATIO in natural.unknown


# =====================================================================
# Unit discipline and refusals
# =====================================================================

def test_the_fluid_conductivity_is_not_interchangeable_with_the_body_s() -> None:
    """Same dimension, opposite meaning, and no dimension check can help.

    The only protection is that they are separate fields, so this asserts they
    are — a body conductivity of 200 W/(m K) with the fluid's left out leaves
    the correlation unevaluable rather than silently using 200.
    """
    without_fluid = dataclasses.replace(FORCED, fluid_conductivity=None)
    assert without_fluid.body_conductivity is not None
    assert group(without_fluid, ctx.CONVECTION_AGREEMENT_RATIO) is None


def test_the_convection_length_is_not_the_biot_length() -> None:
    """Different fields, no fallback, and the difference is a factor of L^3."""
    assert FORCED.characteristic_length.magnitude_in("meter") == 0.002
    assert FORCED.convection_length.magnitude_in("meter") == 0.6
    without_length = dataclasses.replace(FORCED, convection_length=None)
    # The Biot number survives, because it uses the other length.
    assert group(without_length, ctx.BIOT_NUMBER) is not None
    assert group(without_length, ctx.CONVECTION_FLOW_RANGE) is None


@pytest.mark.parametrize(
    "field, value",
    [
        ("fluid_conductivity", Q(0.0, "watt/meter/kelvin")),
        ("fluid_kinematic_viscosity", Q(0.0, "meter**2/second")),
        ("fluid_prandtl_number", Q(0.0, "dimensionless")),
        ("fluid_velocity", Q(0.0, "meter/second")),
        ("convection_length", Q(0.0, "meter")),
        ("fluid_expansion_coefficient", Q(0.0, "1/kelvin")),
    ],
)
def test_a_non_positive_fluid_property_is_refused(field, value) -> None:
    with pytest.raises(InvalidScientificProblem):
        ctx.LumpedApplicabilityDeclaration(**{field: value})


@pytest.mark.parametrize(
    "field, value",
    [
        ("fluid_conductivity", Q(1.0, "meter")),
        ("fluid_kinematic_viscosity", Q(1.0, "meter")),
        ("fluid_velocity", Q(1.0, "meter")),
        ("convection_length", Q(1.0, "second")),
        ("fluid_expansion_coefficient", Q(1.0, "kelvin")),
    ],
)
def test_a_wrongly_dimensioned_fluid_property_is_refused(field, value) -> None:
    with pytest.raises(Exception):
        ctx.LumpedApplicabilityDeclaration(**{field: value})


def test_the_declaration_round_trips_with_its_convection_facts() -> None:
    restored = ctx.LumpedApplicabilityDeclaration.from_dict(FORCED.to_dict())
    assert restored == FORCED
    restored_natural = ctx.LumpedApplicabilityDeclaration.from_dict(
        NATURAL.to_dict()
    )
    assert restored_natural == NATURAL


def test_the_groups_are_reserved_so_a_caller_cannot_assert_them() -> None:
    assert {
        ctx.CONVECTION_FLOW_RANGE,
        ctx.CONVECTION_PROPERTY_RANGE,
        ctx.CONVECTION_AGREEMENT_RATIO,
    } <= ctx.ASSEMBLED_QUANTITIES


def test_every_derived_value_is_finite_at_the_range_edges() -> None:
    for ra in (0.0, 1.0e9):
        value = ctx.churchill_chu_nusselt(
            rayleigh=Q(ra, "dimensionless"),
            prandtl_number=Q(PR, "dimensionless"),
        )
        assert math.isfinite(value.magnitude_in("dimensionless"))
    for re in (0.0, 5.0e5):
        value = ctx.flat_plate_nusselt(
            reynolds=Q(re, "dimensionless"),
            prandtl_number=Q(PR, "dimensionless"),
        )
        assert math.isfinite(value.magnitude_in("dimensionless"))
