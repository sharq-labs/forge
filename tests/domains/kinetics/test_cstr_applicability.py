"""The CSTR's two dimensionless applicability conditions.

Before this file the domain declared five conditions and all five were
positivity or a single-value envelope. These two are groups: they combine
several declarations into a number that says something no individual value
does, and both are decidable from the declaration alone.

What is tested here, in order:

* the derived numbers agree with the domain's own float properties;
* each bound fires in the direction its physics argues for and *not* in the
  other, which for the Damkohler number is the whole claim;
* an absent input yields UNKNOWN, never IN_DOMAIN;
* a caller cannot assert either group;
* the convention is labelled as one, in the constant and in the condition.
"""

from __future__ import annotations

import math

import pytest

from src.engcore.domains.kinetics.cstr import (
    ADIABATIC_CEILING_TEMPERATURE,
    ASSEMBLED_QUANTITIES,
    ASSEMBLER_NAMESPACE,
    CSTR_MODEL,
    DAMKOHLER_NUMBER,
    MAX_VALID_TEMPERATURE_K,
    MAX_WELL_MIXED_DAMKOHLER,
    IntegrationSettings,
    ReactorChemistry,
    ReactorOperation,
    ReactorRun,
    adiabatic_ceiling_temperature,
    cstr_validity_context,
    damkohler_number,
    derived_cstr_quantities,
    solve_reactor,
)
from src.engcore.domains.kinetics.cstr import context as ctx
from src.engcore.scientific.errors import (
    InvalidScientificProblem,
    UnitCompatibilityError,
)
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.units.quantity import Quantity

Q = Quantity

#: The Seborg parameterization, which is also what ``test_cstr_domain`` uses.
#: At the nominal feed temperature it sits at Da = 1.000 to four figures, which
#: is the textbook design point and is why the bound has to be above it.
CHEMISTRY = ReactorChemistry(
    k0=Q(7.2e10 / 60.0, "1/s"),
    activation_energy=Q(8750.0 * 8.314462618, "J/mol"),
    heat_of_reaction=Q(-5.0e4, "J/mol"),
    density=Q(1000.0, "kg/m**3"),
    heat_capacity=Q(239.0, "J/(kg*K)"),
)


def operation(*, tf=350.0, tc=290.0, caf=1000.0, ua=5.0e4 / 60.0, end=1800.0):
    return ReactorOperation(
        volume=Q(0.1, "m**3"),
        flow_rate=Q(0.1 / 60.0, "m**3/s"),
        feed_concentration=Q(caf, "mol/m**3"),
        feed_temperature=Q(tf, "kelvin"),
        coolant_temperature=Q(tc, "kelvin"),
        ua=Q(ua, "W/K"),
        end_time=Q(end, "second"),
    )


def reactor(*, chemistry=None, op=None, ca0=1000.0, t0=300.0) -> ReactorRun:
    return ReactorRun(
        run_label="applicability",
        chemistry=chemistry if chemistry is not None else CHEMISTRY,
        operation=op if op is not None else operation(),
        initial_concentration=Q(ca0, "mol/m**3"),
        initial_temperature=Q(t0, "kelvin"),
    )


def assess(run: ReactorRun):
    return run.validity_context().assess(CSTR_MODEL)


def status_of(run: ReactorRun, condition: str) -> ValidityStatus:
    """The verdict on ONE condition, read out of the whole assessment."""
    result = assess(run)
    for names, verdict in (
        (result.satisfied, ValidityStatus.IN_DOMAIN),
        (result.violated, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
        (result.unknown, ValidityStatus.UNKNOWN),
    ):
        if condition in names:
            return verdict
    raise AssertionError(f"{condition!r} was not assessed at all")


# =====================================================================
# Both conditions exist, and neither replaces what was there
# =====================================================================

def test_the_model_now_declares_two_dimensionless_conditions() -> None:
    names = {c.name for c in CSTR_MODEL.validity.conditions}
    assert {DAMKOHLER_NUMBER, ADIABATIC_CEILING_TEMPERATURE} <= names
    # The five positivity and envelope conditions are still there.
    assert {
        "temperature", "concentration", "k0", "activation_energy",
        "residence_time",
    } <= names


def test_the_nominal_reactor_is_in_domain_on_both() -> None:
    run = reactor()
    assert status_of(run, DAMKOHLER_NUMBER) is ValidityStatus.IN_DOMAIN
    assert (
        status_of(run, ADIABATIC_CEILING_TEMPERATURE)
        is ValidityStatus.IN_DOMAIN
    )


# =====================================================================
# The Damkohler number
# =====================================================================

def test_the_derived_group_equals_the_domain_s_own_float_property() -> None:
    """Two routes to Da: the float kernel, and the unit-checked Quantity.

    ``ReactorRun.damkohler_at_feed_temperature`` goes through
    ``ReactorChemistry.rate_constant_per_s`` in plain floats because it is the
    solver's own arithmetic; ``damkohler_number`` rebuilds the exponent as a
    Quantity so an activation energy in the wrong dimension is caught. They
    must not be allowed to drift apart.
    """
    for tf in (300.0, 340.0, 350.0, 360.0, 380.0):
        run = reactor(op=operation(tf=tf))
        derived = run.validity_context()[DAMKOHLER_NUMBER]
        assert derived.magnitude_in("dimensionless") == pytest.approx(
            run.damkohler_at_feed_temperature, rel=1e-12
        )


def test_the_damkohler_number_is_unit_checked_not_magnitude_read() -> None:
    """The same activation energy in kJ/mol gives the same number."""
    joules = damkohler_number(
        k0=Q(1.0, "1/s"),
        activation_energy=Q(20_000.0, "J/mol"),
        feed_temperature=Q(350.0, "kelvin"),
        residence_time=Q(1.0, "second"),
    )
    kilojoules = damkohler_number(
        k0=Q(1.0, "1/s"),
        activation_energy=Q(20.0, "kJ/mol"),
        feed_temperature=Q(350.0, "kelvin"),
        residence_time=Q(1.0, "second"),
    )
    assert joules.magnitude_in("dimensionless") == pytest.approx(
        kilojoules.magnitude_in("dimensionless"), rel=1e-12
    )
    # And a residence time offered where a rate constant belongs is refused
    # rather than silently producing a number. The refusal comes from
    # Quantity.require_compatible, so it is a UnitCompatibilityError; what
    # matters is that nothing is computed.
    with pytest.raises(UnitCompatibilityError):
        damkohler_number(
            k0=Q(1.0, "second"),
            activation_energy=Q(20_000.0, "J/mol"),
            feed_temperature=Q(350.0, "kelvin"),
            residence_time=Q(1.0, "second"),
        )


def test_a_reaction_faster_than_the_tank_mixes_is_outside_the_domain() -> None:
    """The bound fires above, which is the direction the physics argues for."""
    # A feed hot enough to put Da past the ceiling. Every other declaration is
    # nominal, so this isolates the one condition.
    hot = reactor(op=operation(tf=400.0))
    assert hot.damkohler_at_feed_temperature > 10.0
    assert (
        status_of(hot, DAMKOHLER_NUMBER)
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )


def test_the_damkohler_bound_is_inclusive_and_sits_where_it_says() -> None:
    """1 % inside is accepted; 1 % outside is refused. No epsilon either way."""
    ceiling = MAX_WELL_MIXED_DAMKOHLER.magnitude_in("dimensionless")
    assert ceiling == 10.0

    # Solve for the feed temperature that puts Da exactly on the bound, then
    # step off it by 1 % in Da on each side by moving the residence time — the
    # one input Da is exactly linear in, so the distance is exact.
    base = reactor(op=operation(tf=380.0))
    da_base = base.damkohler_at_feed_temperature
    for factor, expected in (
        (0.99 * ceiling / da_base, ValidityStatus.IN_DOMAIN),
        (1.00 * ceiling / da_base, ValidityStatus.IN_DOMAIN),
        (1.01 * ceiling / da_base, ValidityStatus.OUTSIDE_VALIDATED_DOMAIN),
    ):
        run = ReactorRun(
            run_label="ladder",
            chemistry=CHEMISTRY,
            operation=ReactorOperation(
                volume=Q(0.1 * factor, "m**3"),
                flow_rate=Q(0.1 / 60.0, "m**3/s"),
                feed_concentration=Q(1000.0, "mol/m**3"),
                feed_temperature=Q(380.0, "kelvin"),
                coolant_temperature=Q(290.0, "kelvin"),
                ua=Q(5.0e4 / 60.0, "W/K"),
                end_time=Q(1800.0, "second"),
            ),
            initial_concentration=Q(1000.0, "mol/m**3"),
            initial_temperature=Q(300.0, "kelvin"),
        )
        assert status_of(run, DAMKOHLER_NUMBER) is expected


def test_a_reactor_that_barely_reacts_is_still_in_domain() -> None:
    """There is NO lower bound, and this is the case that says why.

    ``test_a_reactor_that_cannot_react_still_solves_and_conserves`` in the
    domain suite runs this chemistry and checks the trajectory against an
    elementary exponential. A low-Da floor would call the one case where the
    model is easiest to verify inapplicable.
    """
    inert = ReactorChemistry(
        k0=Q(1e-30, "1/s"),
        activation_energy=CHEMISTRY.activation_energy,
        heat_of_reaction=CHEMISTRY.heat_of_reaction,
        density=CHEMISTRY.density,
        heat_capacity=CHEMISTRY.heat_capacity,
    )
    run = reactor(chemistry=inert, op=operation(ua=0.0, end=600.0), ca0=0.0)
    assert run.damkohler_at_feed_temperature < 1e-30
    assert status_of(run, DAMKOHLER_NUMBER) is ValidityStatus.IN_DOMAIN
    assert assess(run).status is ValidityStatus.IN_DOMAIN


def test_the_interesting_band_is_not_excluded() -> None:
    """Da of order unity is what this model is for, and stays in domain."""
    for tf in (340.0, 350.0, 360.0):
        run = reactor(op=operation(tf=tf))
        assert 0.1 < run.damkohler_at_feed_temperature < 10.0
        assert status_of(run, DAMKOHLER_NUMBER) is ValidityStatus.IN_DOMAIN


# =====================================================================
# The adiabatic ceiling
# =====================================================================

def test_the_ceiling_reuses_the_envelope_bound_and_introduces_no_threshold(
) -> None:
    condition = next(
        c for c in CSTR_MODEL.validity.conditions
        if c.name == ADIABATIC_CEILING_TEMPERATURE
    )
    assert condition.minimum is None
    assert condition.maximum.magnitude_in("kelvin") == MAX_VALID_TEMPERATURE_K


def test_the_ceiling_is_the_hottest_declared_state_plus_the_adiabatic_rise(
) -> None:
    run = reactor()
    ceiling = run.validity_context()[ADIABATIC_CEILING_TEMPERATURE]
    hottest = max(
        run.t0_k, run.operation.tf_k, run.operation.tc_k
    )
    expected = hottest + run.adiabatic_rise_k
    assert ceiling.magnitude_in("kelvin") == pytest.approx(expected, rel=1e-12)


def test_the_ceiling_really_does_bound_the_trajectory() -> None:
    """Not a definition test: solve, and check the peak against the bound.

    An adiabatic run is the case where the invariant is exact and the bound is
    therefore tightest, so it is the one that would expose an error in the
    derivation.
    """
    run = ReactorRun(
        run_label="ceiling",
        chemistry=CHEMISTRY,
        operation=operation(ua=0.0, tf=350.0, caf=1000.0, end=3600.0),
        initial_concentration=Q(1000.0, "mol/m**3"),
        initial_temperature=Q(340.0, "kelvin"),
        integration=IntegrationSettings(
            method="BDF", rtol=1e-10, atol_concentration=1e-10,
            atol_temperature=1e-10,
        ),
    )
    ceiling = run.validity_context()[
        ADIABATIC_CEILING_TEMPERATURE
    ].magnitude_in("kelvin")
    result = solve_reactor(run, run_id="ceiling-1")
    peak = result.values["T:max"].magnitude_in("kelvin")
    assert peak <= ceiling
    # And the bound is not vacuous: an adiabatic run from a rich feed gets
    # within a few kelvin of it, so it is a real ceiling rather than infinity.
    assert peak > ceiling - 20.0


def test_a_declaration_that_can_leave_the_envelope_is_outside_the_domain(
) -> None:
    """A feed rich enough that full conversion carries the tank past 1000 K.

    Every declared temperature is inside the 250-1000 K envelope, so the
    ``temperature`` condition is satisfied and this is caught by the ceiling
    alone — which is the point of having it.
    """
    run = reactor(op=operation(tf=900.0, tc=900.0, caf=4000.0), t0=900.0)
    assert status_of(run, "temperature") is ValidityStatus.IN_DOMAIN
    assert (
        status_of(run, ADIABATIC_CEILING_TEMPERATURE)
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )


def test_an_endothermic_reaction_does_not_lower_its_own_ceiling() -> None:
    """beta <= 0, so the rise term is clamped at zero rather than subtracted."""
    endothermic = ReactorChemistry(
        k0=CHEMISTRY.k0,
        activation_energy=CHEMISTRY.activation_energy,
        heat_of_reaction=Q(+5.0e4, "J/mol"),
        density=CHEMISTRY.density,
        heat_capacity=CHEMISTRY.heat_capacity,
    )
    run = reactor(chemistry=endothermic)
    ceiling = run.validity_context()[
        ADIABATIC_CEILING_TEMPERATURE
    ].magnitude_in("kelvin")
    hottest = max(run.t0_k, run.operation.tf_k, run.operation.tc_k)
    assert ceiling == pytest.approx(hottest, rel=1e-12)


# =====================================================================
# Missing input yields UNKNOWN, and a caller cannot assert either group
# =====================================================================

@pytest.mark.parametrize(
    "dropped, condition",
    [
        ("k0", DAMKOHLER_NUMBER),
        ("activation_energy", DAMKOHLER_NUMBER),
        ("feed_temperature", DAMKOHLER_NUMBER),
        ("residence_time", DAMKOHLER_NUMBER),
        ("heat_of_reaction", ADIABATIC_CEILING_TEMPERATURE),
        ("density", ADIABATIC_CEILING_TEMPERATURE),
        ("heat_capacity", ADIABATIC_CEILING_TEMPERATURE),
        ("feed_concentration", ADIABATIC_CEILING_TEMPERATURE),
        ("concentration", ADIABATIC_CEILING_TEMPERATURE),
        ("temperature", ADIABATIC_CEILING_TEMPERATURE),
        ("coolant_temperature", ADIABATIC_CEILING_TEMPERATURE),
    ],
)
def test_a_missing_declaration_makes_its_group_unknown(
    dropped: str, condition: str
) -> None:
    declared = dict(reactor().validity_context())
    # Only the derived groups. `temperature` and `concentration` are
    # reserved too, but they are the reactor's own state and are what the
    # assembler derives *from*; stripping them here would remove an input
    # rather than a forgery.
    for name in ASSEMBLED_QUANTITIES:
        declared.pop(name, None)
    declared.pop(dropped)
    assembled = cstr_validity_context(declared, reserved=ASSEMBLER_NAMESPACE)
    assert condition not in assembled

    verdict = assembled.assess(CSTR_MODEL)
    assert condition in verdict.unknown
    assert condition not in verdict.satisfied


def test_a_caller_cannot_assert_either_group() -> None:
    """The forged value is stripped before anything is derived.

    With the inputs present the assembler's own number wins; with an input
    missing the key is absent rather than caller-supplied, so the condition
    reads UNKNOWN instead of the caller's IN_DOMAIN.
    """
    declared = dict(reactor().validity_context())
    # Only the derived groups. `temperature` and `concentration` are
    # reserved too, but they are the reactor's own state and are what the
    # assembler derives *from*; stripping them here would remove an input
    # rather than a forgery.
    for name in ASSEMBLED_QUANTITIES:
        declared.pop(name, None)

    forged = dict(declared)
    forged[DAMKOHLER_NUMBER] = Q(1.0, "dimensionless")
    forged[ADIABATIC_CEILING_TEMPERATURE] = Q(300.0, "kelvin")
    assembled = cstr_validity_context(forged, reserved=ASSEMBLER_NAMESPACE)
    assert assembled[ADIABATIC_CEILING_TEMPERATURE].magnitude_in(
        "kelvin"
    ) == pytest.approx(559.2050209205021)

    # Now remove an input the ceiling needs and forge it anyway.
    crippled = dict(declared)
    crippled.pop("density")
    crippled[ADIABATIC_CEILING_TEMPERATURE] = Q(300.0, "kelvin")
    assembled = cstr_validity_context(crippled, reserved=ASSEMBLER_NAMESPACE)
    assert ADIABATIC_CEILING_TEMPERATURE not in assembled
    verdict = assembled.assess(CSTR_MODEL)
    assert ADIABATIC_CEILING_TEMPERATURE in verdict.unknown


def test_the_assembler_refuses_a_group_it_did_not_reserve() -> None:
    assert ASSEMBLED_QUANTITIES == frozenset(
        {DAMKOHLER_NUMBER, ADIABATIC_CEILING_TEMPERATURE}
    )
    assert set(
        derived_cstr_quantities(reactor().validity_context())
    ) <= ASSEMBLED_QUANTITIES


def test_nothing_is_derived_from_an_empty_declaration() -> None:
    assert derived_cstr_quantities({}) == {}
    verdict = cstr_validity_context(
        {}, reserved=ASSEMBLER_NAMESPACE
    ).assess(CSTR_MODEL)
    assert verdict.status is ValidityStatus.UNKNOWN
    assert DAMKOHLER_NUMBER in verdict.unknown
    assert ADIABATIC_CEILING_TEMPERATURE in verdict.unknown


# =====================================================================
# The convention is labelled a convention
# =====================================================================

def test_the_damkohler_ceiling_is_recorded_as_a_convention() -> None:
    """Rule: a number the source does not establish must say so.

    The Fo = 0.2 episode is the precedent. Here the *direction* is
    Levenspiel's and the *number* is a reading of "well stirred", so the
    constant, the condition description and the docs row all have to say
    convention out loud, or the citation is doing work it cannot do.
    """
    condition = next(
        c for c in CSTR_MODEL.validity.conditions if c.name == DAMKOHLER_NUMBER
    )
    assert "CONVENTION" in condition.description.upper()
    assert "Levenspiel" in condition.description
    # And the constant itself, where a reader meets the number first.
    source = ctx.__doc__ or ""
    assert "Levenspiel" in source
    import inspect
    module_text = inspect.getsource(ctx)
    marker = module_text.split("MAX_WELL_MIXED_DAMKOHLER = ")[0]
    assert "convention" in marker.rsplit("#: Da <= 10", 1)[-1].lower()


def test_the_ceiling_condition_names_no_new_number() -> None:
    """It reuses the envelope bound, so it needs no convention of its own."""
    condition = next(
        c for c in CSTR_MODEL.validity.conditions
        if c.name == ADIABATIC_CEILING_TEMPERATURE
    )
    assert "1000 K" in condition.description
    assert "invariant" in condition.description


# =====================================================================
# Purity
# =====================================================================

def test_the_derivations_do_not_mutate_what_they_are_given() -> None:
    declared = dict(reactor().validity_context())
    # Only the derived groups. `temperature` and `concentration` are
    # reserved too, but they are the reactor's own state and are what the
    # assembler derives *from*; stripping them here would remove an input
    # rather than a forgery.
    for name in ASSEMBLED_QUANTITIES:
        declared.pop(name, None)
    snapshot = dict(declared)
    derived_cstr_quantities(declared)
    cstr_validity_context(declared, reserved=ASSEMBLER_NAMESPACE)
    assert declared == snapshot


def test_a_zero_residence_time_is_refused_rather_than_dividing() -> None:
    with pytest.raises(InvalidScientificProblem):
        damkohler_number(
            k0=Q(1.0, "1/s"),
            activation_energy=Q(0.0, "J/mol"),
            feed_temperature=Q(350.0, "kelvin"),
            residence_time=Q(0.0, "second"),
        )


def test_a_zero_density_is_refused_rather_than_dividing() -> None:
    with pytest.raises(InvalidScientificProblem):
        adiabatic_ceiling_temperature(
            heat_of_reaction=Q(-5.0e4, "J/mol"),
            density=Q(0.0, "kg/m**3"),
            heat_capacity=Q(239.0, "J/(kg*K)"),
            feed_concentration=Q(1000.0, "mol/m**3"),
            initial_concentration=Q(1000.0, "mol/m**3"),
            feed_temperature=Q(350.0, "kelvin"),
            initial_temperature=Q(300.0, "kelvin"),
            coolant_temperature=Q(290.0, "kelvin"),
        )


def test_the_exponent_is_finite_at_the_envelope_extremes() -> None:
    """Da must be a number, not an overflow, anywhere the model is allowed."""
    for tf in (250.0, 1000.0):
        value = damkohler_number(
            k0=Q(7.2e10 / 60.0, "1/s"),
            activation_energy=Q(8750.0 * 8.314462618, "J/mol"),
            feed_temperature=Q(tf, "kelvin"),
            residence_time=Q(60.0, "second"),
        )
        assert math.isfinite(value.magnitude_in("dimensionless"))
