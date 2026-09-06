"""The lumped domain's computed validity context, function by function.

These are the *derivations*, tested away from any model record: does each
dimensionless group equal what its textbook definition says, is it unit-checked
rather than magnitude-checked, and does it return ``None`` — never a plausible
number — when the caller did not supply what it needs.

The conditions built on these groups are tested in
``test_lumped_applicability.py``. Splitting the two is deliberate: a wrong
Biot number and a wrong Biot *threshold* are different defects, and a test that
could not tell them apart would be evidence for neither.
"""

from __future__ import annotations

import math

import pytest

from src.engcore.domains.thermal_models import context as ctx
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.ir.problem import ScientificProblem
from src.engcore.scientific.ir.variables import ScientificParameter
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.units.quantity import Quantity

K = "kelvin"
DIMENSIONLESS = "dimensionless"


def dimensionless(quantity: Quantity) -> float:
    return quantity.magnitude_in(DIMENSIONLESS)


# =====================================================================
# Geometry: L_c = V / A_s
# =====================================================================

def test_characteristic_length_is_the_volume_to_surface_area_ratio():
    """Incropera 6th ed. Sec. 5.1: L_c = V / A_s."""
    length = ctx.characteristic_length(
        volume=Quantity(2.0e-5, "meter**3"),
        surface_area=Quantity(0.01, "meter**2"),
    )
    assert length.magnitude_in("meter") == pytest.approx(2.0e-3, rel=1e-12)


def test_a_declared_characteristic_length_overrides_the_volume_ratio():
    """A slab conducting from one face has L_c = its thickness, not V/A_s.

    The text says so, and only the caller knows the conduction path, so a
    declared value wins over the derived one rather than being averaged with it.
    """
    length = ctx.characteristic_length(
        declared=Quantity(0.05, "meter"),
        volume=Quantity(2.0e-5, "meter**3"),
        surface_area=Quantity(0.01, "meter**2"),
    )
    assert length.magnitude_in("meter") == pytest.approx(0.05, rel=1e-12)


def test_characteristic_length_is_none_without_a_volume_or_an_area():
    assert ctx.characteristic_length(surface_area=Quantity(0.01, "meter**2")) is None
    assert ctx.characteristic_length(volume=Quantity(2.0e-5, "meter**3")) is None
    assert ctx.characteristic_length() is None


def test_characteristic_length_converts_rather_than_comparing_magnitudes():
    """Millimetres and metres must give the same L_c, not a factor of 1000."""
    metric = ctx.characteristic_length(
        volume=Quantity(2.0e-5, "meter**3"),
        surface_area=Quantity(0.01, "meter**2"),
    )
    mixed = ctx.characteristic_length(
        volume=Quantity(20000.0, "millimeter**3"),
        surface_area=Quantity(100.0, "centimeter**2"),
    )
    assert mixed.magnitude_in("meter") == pytest.approx(
        metric.magnitude_in("meter"), rel=1e-12
    )


def test_a_zero_surface_area_is_refused_rather_than_dividing():
    """Zero area is not a small area: it is a body with no exchange surface."""
    with pytest.raises(InvalidScientificProblem):
        ctx.characteristic_length(
            volume=Quantity(1.0, "meter**3"),
            surface_area=Quantity(0.0, "meter**2"),
        )


def test_a_bare_number_is_refused_where_a_declaration_belongs():
    with pytest.raises(InvalidScientificProblem):
        ctx.characteristic_length(declared=0.05)


# =====================================================================
# h = hA / A_s
# =====================================================================

def test_the_surface_coefficient_splits_the_declared_conductance_by_area():
    coefficient = ctx.surface_coefficient(
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        surface_area=Quantity(0.01, "meter**2"),
    )
    assert coefficient.magnitude_in("watt/meter**2/kelvin") == pytest.approx(
        5.0, rel=1e-12
    )


def test_no_coefficient_exists_without_the_area_because_hA_is_a_product():
    """The balance declares hA, never h. Without A_s the split cannot be made."""
    assert (
        ctx.surface_coefficient(
            ambient_conductance=Quantity(0.05, "watt/kelvin"), surface_area=None
        )
        is None
    )


# =====================================================================
# Bi = h L_c / k
# =====================================================================

def test_the_biot_number_is_the_coefficient_times_length_over_conductivity():
    """Incropera 6th ed. Sec. 5.1, Eq. 5.10."""
    biot = ctx.biot_number(
        coefficient=Quantity(5.0, "watt/meter**2/kelvin"),
        length=Quantity(0.05, "meter"),
        conductivity=Quantity(0.2, "watt/meter/kelvin"),
    )
    assert dimensionless(biot) == pytest.approx(1.25, rel=1e-12)


def test_the_biot_number_is_dimensionless_by_construction():
    biot = ctx.biot_number(
        coefficient=Quantity(5.0, "watt/meter**2/kelvin"),
        length=Quantity(0.002, "meter"),
        conductivity=Quantity(200.0, "watt/meter/kelvin"),
    )
    assert biot.dimensionality == Quantity(1.0, DIMENSIONLESS).dimensionality


def test_the_biot_number_is_none_when_any_of_its_three_inputs_is_absent():
    for missing in ("coefficient", "length", "conductivity"):
        supplied = {
            "coefficient": Quantity(5.0, "watt/meter**2/kelvin"),
            "length": Quantity(0.002, "meter"),
            "conductivity": Quantity(200.0, "watt/meter/kelvin"),
        }
        supplied[missing] = None
        assert ctx.biot_number(**supplied) is None, missing


def test_a_conductance_supplied_where_a_conductivity_belongs_is_refused():
    """W/K and W/(m K) differ by a length. A magnitude check would not notice."""
    with pytest.raises(Exception):
        ctx.biot_number(
            coefficient=Quantity(5.0, "watt/meter**2/kelvin"),
            length=Quantity(0.002, "meter"),
            conductivity=Quantity(200.0, "watt/kelvin"),
        )


# =====================================================================
# Time scales
# =====================================================================

def test_the_time_constant_is_capacity_over_conductance():
    """Incropera 6th ed. Sec. 5.1, Eq. 5.7: tau_t = R_t C_t."""
    tau = ctx.thermal_time_constant(
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
    )
    assert tau.magnitude_in("second") == pytest.approx(50.0, rel=1e-12)


def test_the_horizon_ratio_is_the_duration_in_time_constants():
    ratio = ctx.transient_horizon_ratio(
        duration=Quantity(120.0, "second"),
        time_constant=Quantity(50.0, "second"),
    )
    assert dimensionless(ratio) == pytest.approx(2.4, rel=1e-12)


def test_the_fourier_number_is_the_horizon_ratio_divided_by_the_biot_number():
    """Bi * Fo = t / tau — Incropera 6th ed. Sec. 5.2, Eq. 5.12.

    The identity is what makes Fo computable here without a density or a
    specific heat, so it is checked as an identity rather than assumed.
    """
    biot = Quantity(0.05, DIMENSIONLESS)
    horizon = Quantity(2.4, DIMENSIONLESS)
    fourier = ctx.internal_fourier_number(horizon_ratio=horizon, biot=biot)
    assert dimensionless(fourier) == pytest.approx(48.0, rel=1e-12)
    assert dimensionless(biot) * dimensionless(fourier) == pytest.approx(
        dimensionless(horizon), rel=1e-12
    )


def test_the_fourier_number_is_none_without_a_biot_number():
    assert (
        ctx.internal_fourier_number(
            horizon_ratio=Quantity(2.4, DIMENSIONLESS), biot=None
        )
        is None
    )


# =====================================================================
# Temperatures
# =====================================================================

def test_the_steady_state_temperature_is_the_ambient_plus_the_driven_rise():
    steady = ctx.steady_state_temperature(
        ambient_temperature=Quantity(300.0, K),
        heat_input=Quantity(1.0, "watt"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
    )
    assert steady.magnitude_in(K) == pytest.approx(320.0, rel=1e-12)


def test_the_steady_state_temperature_is_none_without_a_heat_input():
    assert (
        ctx.steady_state_temperature(
            ambient_temperature=Quantity(300.0, K),
            heat_input=None,
            ambient_conductance=Quantity(0.05, "watt/kelvin"),
        )
        is None
    )


def test_the_peak_temperature_is_an_endpoint_because_the_response_is_monotone():
    """No overshoot: one real pole, so the extremes are the endpoints."""
    assert ctx.peak_body_temperature(
        initial_temperature=Quantity(300.0, K),
        steady_temperature=Quantity(320.0, K),
    ).magnitude_in(K) == pytest.approx(320.0, rel=1e-12)
    # Cooling: the initial state is the peak.
    assert ctx.peak_body_temperature(
        initial_temperature=Quantity(400.0, K),
        steady_temperature=Quantity(320.0, K),
    ).magnitude_in(K) == pytest.approx(400.0, rel=1e-12)


def test_the_surface_excursion_is_the_larger_of_the_two_endpoint_differences():
    excursion = ctx.surface_temperature_excursion(
        initial_temperature=Quantity(400.0, K),
        ambient_temperature=Quantity(300.0, K),
        steady_temperature=Quantity(320.0, K),
    )
    assert excursion.magnitude_in(K) == pytest.approx(100.0, rel=1e-12)


# =====================================================================
# Excursion budgets
# =====================================================================

def test_the_conductance_budget_is_the_excursion_over_the_declared_bound():
    ratio = ctx.conductance_excursion_ratio(
        excursion=Quantity(20.0, K), bound=Quantity(50.0, K)
    )
    assert dimensionless(ratio) == pytest.approx(0.4, rel=1e-12)


def test_the_conductance_budget_takes_no_regime_and_has_no_bypass():
    """The declaration cannot reach this computation, by signature.

    An earlier version accepted ``regime=`` and returned 0.0 for a declared
    forced regime before reading either argument. The parameter is gone: there
    is no third argument through which a caller can assert their way past the
    two that carry evidence.
    """
    import inspect

    assert set(
        inspect.signature(ctx.conductance_excursion_ratio).parameters
    ) == {"excursion", "bound"}


def test_the_conductance_budget_needs_a_bound_whatever_the_caller_declares():
    """No bound, no ratio — the regime is not consulted and cannot help."""
    assert (
        ctx.conductance_excursion_ratio(excursion=Quantity(500.0, K), bound=None)
        is None
    )
    assert (
        ctx.conductance_excursion_ratio(excursion=None, bound=Quantity(50.0, K))
        is None
    )


def test_the_capacity_budget_is_the_body_temperature_span_over_the_bound():
    ratio = ctx.capacity_excursion_ratio(
        initial_temperature=Quantity(300.0, K),
        steady_temperature=Quantity(320.0, K),
        bound=Quantity(100.0, K),
    )
    assert dimensionless(ratio) == pytest.approx(0.2, rel=1e-12)


def test_the_capacity_budget_is_none_without_a_declared_bound():
    assert (
        ctx.capacity_excursion_ratio(
            initial_temperature=Quantity(300.0, K),
            steady_temperature=Quantity(320.0, K),
            bound=None,
        )
        is None
    )


# =====================================================================
# Radiation
# =====================================================================

def test_the_linearized_radiation_coefficient_matches_equation_1_9():
    """h_r = eps sigma (T_s + T_sur)(T_s^2 + T_sur^2) — Incropera Eq. 1.9."""
    emissivity, surface, surroundings = 0.8, 400.0, 300.0
    expected = (
        emissivity
        * ctx.STEFAN_BOLTZMANN.magnitude_in("watt/meter**2/kelvin**4")
        * (surface + surroundings)
        * (surface**2 + surroundings**2)
    )
    computed = ctx.linearized_radiation_coefficient(
        emissivity=Quantity(emissivity, DIMENSIONLESS),
        surface_temperature=Quantity(surface, K),
        surroundings_temperature=Quantity(surroundings, K),
    )
    assert computed.magnitude_in("watt/meter**2/kelvin") == pytest.approx(
        expected, rel=1e-12
    )


def test_the_radiation_coefficient_recovers_the_fourth_power_exchange():
    """h_r (T_s - T_sur) must equal eps sigma (T_s^4 - T_sur^4) exactly.

    The factorisation is algebra, not an approximation, and this is the check
    that says so rather than the docstring saying so.
    """
    sigma = ctx.STEFAN_BOLTZMANN.magnitude_in("watt/meter**2/kelvin**4")
    emissivity, surface, surroundings = 0.65, 380.0, 295.0
    h_r = ctx.linearized_radiation_coefficient(
        emissivity=Quantity(emissivity, DIMENSIONLESS),
        surface_temperature=Quantity(surface, K),
        surroundings_temperature=Quantity(surroundings, K),
    ).magnitude_in("watt/meter**2/kelvin")
    assert h_r * (surface - surroundings) == pytest.approx(
        emissivity * sigma * (surface**4 - surroundings**4), rel=1e-12
    )


def test_the_radiation_coefficient_uses_absolute_temperature_not_celsius():
    """A Celsius declaration must not become a fourth power of the wrong number."""
    kelvin = ctx.linearized_radiation_coefficient(
        emissivity=Quantity(0.8, DIMENSIONLESS),
        surface_temperature=Quantity(400.0, K),
        surroundings_temperature=Quantity(300.0, K),
    )
    celsius = ctx.linearized_radiation_coefficient(
        emissivity=Quantity(0.8, DIMENSIONLESS),
        surface_temperature=Quantity(400.0 - 273.15, "degC"),
        surroundings_temperature=Quantity(300.0 - 273.15, "degC"),
    )
    assert celsius.magnitude_in("watt/meter**2/kelvin") == pytest.approx(
        kelvin.magnitude_in("watt/meter**2/kelvin"), rel=1e-9
    )


def test_the_radiation_coefficient_is_none_without_a_declared_emissivity():
    assert (
        ctx.linearized_radiation_coefficient(
            emissivity=None,
            surface_temperature=Quantity(400.0, K),
            surroundings_temperature=Quantity(300.0, K),
        )
        is None
    )


def test_an_emissivity_outside_zero_to_one_is_not_an_emissivity():
    for bad in (-0.1, 1.5):
        with pytest.raises(InvalidScientificProblem):
            ctx.LumpedApplicabilityDeclaration(
                surface_emissivity=Quantity(bad, DIMENSIONLESS)
            )


def test_the_radiation_share_is_the_ratio_of_the_two_coefficients():
    ratio = ctx.radiation_to_convection_ratio(
        radiation_coefficient=Quantity(0.5, "watt/meter**2/kelvin"),
        coefficient=Quantity(5.0, "watt/meter**2/kelvin"),
    )
    assert dimensionless(ratio) == pytest.approx(0.1, rel=1e-12)


# =====================================================================
# Phase change
# =====================================================================

def test_the_melting_utilization_is_the_ratio_of_two_absolute_temperatures():
    ratio = ctx.melting_temperature_utilization(
        peak_temperature=Quantity(320.0, K),
        melting_temperature=Quantity(900.0, K),
    )
    assert dimensionless(ratio) == pytest.approx(320.0 / 900.0, rel=1e-12)


def test_the_melting_utilization_is_none_without_a_declared_melting_point():
    assert (
        ctx.melting_temperature_utilization(
            peak_temperature=Quantity(320.0, K), melting_temperature=None
        )
        is None
    )


# =====================================================================
# The declaration record
# =====================================================================

def test_an_empty_declaration_declares_nothing_and_says_so():
    assert ctx.LumpedApplicabilityDeclaration().is_empty
    assert not ctx.LumpedApplicabilityDeclaration(
        surface_area=Quantity(0.01, "meter**2")
    ).is_empty


def test_the_declaration_round_trips_through_its_serialized_form():
    declaration = ctx.LumpedApplicabilityDeclaration(
        characteristic_length=Quantity(0.002, "meter"),
        volume=Quantity(2.0e-5, "meter**3"),
        surface_area=Quantity(0.01, "meter**2"),
        body_conductivity=Quantity(200.0, "watt/meter/kelvin"),
        surface_emissivity=Quantity(0.05, DIMENSIONLESS),
        convection_regime=ctx.FORCED_CONVECTION,
        conductance_excursion_bound=Quantity(40.0, K),
        capacity_excursion_bound=Quantity(100.0, K),
        melting_temperature=Quantity(900.0, K),
    )
    restored = ctx.LumpedApplicabilityDeclaration.from_dict(declaration.to_dict())
    assert restored == declaration
    assert restored.to_dict() == declaration.to_dict()


def test_an_empty_declaration_round_trips_as_nine_absent_facts():
    empty = ctx.LumpedApplicabilityDeclaration()
    restored = ctx.LumpedApplicabilityDeclaration.from_dict(empty.to_dict())
    assert restored == empty and restored.is_empty


def test_an_unknown_convection_regime_is_refused_rather_than_ignored():
    with pytest.raises(InvalidScientificProblem):
        ctx.LumpedApplicabilityDeclaration(convection_regime="mixed")


def test_a_declaration_refuses_a_non_positive_size_or_property():
    for field, value in (
        ("characteristic_length", Quantity(0.0, "meter")),
        ("volume", Quantity(-1.0, "meter**3")),
        ("surface_area", Quantity(0.0, "meter**2")),
        ("body_conductivity", Quantity(0.0, "watt/meter/kelvin")),
        ("melting_temperature", Quantity(0.0, K)),
    ):
        with pytest.raises(InvalidScientificProblem):
            ctx.LumpedApplicabilityDeclaration(**{field: value})


def test_a_declaration_refuses_a_dimensionally_wrong_quantity():
    with pytest.raises(Exception):
        ctx.LumpedApplicabilityDeclaration(surface_area=Quantity(1.0, "meter"))


def test_a_span_declared_on_an_affine_scale_is_refused_not_silently_converted():
    """A 10 degC *band* is not 283.15 K, and no dimension check would notice.

    The two excursion bounds are differences carried in a type that means an
    absolute value. Celsius and Fahrenheit have conventional zeros, so a span
    written in them does not survive conversion; kelvin and the delta scales do.
    """
    for field in ("conductance_excursion_bound", "capacity_excursion_bound"):
        with pytest.raises(InvalidScientificProblem):
            ctx.LumpedApplicabilityDeclaration(**{field: Quantity(10.0, "degC")})
        # kelvin and an explicit delta scale are both accepted, and agree
        in_kelvin = ctx.LumpedApplicabilityDeclaration(
            **{field: Quantity(10.0, "kelvin")}
        )
        in_delta = ctx.LumpedApplicabilityDeclaration(
            **{field: Quantity(10.0, "delta_degC")}
        )
        assert getattr(in_kelvin, field).magnitude_in("kelvin") == pytest.approx(
            getattr(in_delta, field).magnitude_in("kelvin"), rel=1e-12
        )


def test_an_absolute_temperature_may_still_be_declared_in_celsius():
    """The guard applies to spans, not to states: a melting point has a zero."""
    declaration = ctx.LumpedApplicabilityDeclaration(
        melting_temperature=Quantity(626.85, "degC")
    )
    assert declaration.melting_temperature.magnitude_in(K) == pytest.approx(
        900.0, rel=1e-9
    )


# =====================================================================
# Assembly
# =====================================================================

def test_the_assembler_omits_every_key_it_could_not_derive():
    """The whole contract in one assertion: nothing is invented."""
    assert ctx.derived_lumped_quantities({}) == {}


def test_the_assembler_derives_only_what_the_supplied_facts_reach():
    """Geometry without a state gives the geometric groups and nothing else."""
    base = {
        "heat_capacity": Quantity(2.5, "joule/kelvin"),
        "ambient_conductance": Quantity(0.05, "watt/kelvin"),
        "duration": Quantity(120.0, "second"),
        ctx.CHARACTERISTIC_LENGTH: Quantity(0.002, "meter"),
        ctx.SURFACE_AREA: Quantity(0.01, "meter**2"),
        ctx.BODY_CONDUCTIVITY: Quantity(200.0, "watt/meter/kelvin"),
    }
    derived = ctx.derived_lumped_quantities(base)
    assert set(derived) == {
        ctx.BIOT_NUMBER,
        ctx.TRANSIENT_HORIZON_RATIO,
        ctx.INTERNAL_FOURIER_NUMBER,
        # One route to a characteristic length was supplied, so whether the
        # two routes agree is answerable and they trivially do: there is no
        # second declaration for the length to contradict.
        ctx.GEOMETRY_ROUTE_RATIO,
    }
    assert dimensionless(derived[ctx.BIOT_NUMBER]) == pytest.approx(
        5.0e-5, rel=1e-12
    )
    assert math.isfinite(dimensionless(derived[ctx.INTERNAL_FOURIER_NUMBER]))


# =====================================================================
# F03 — a caller parameter cannot be read as a derived quantity
# =====================================================================

def _incomplete_body():
    """Fully declared except ``body_conductivity``, which the Biot number needs."""
    return lump.ThermalBody(
        body_id="R1",
        heat_capacity=Quantity(2.5, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, K),
        initial_temperature=Quantity(300.0, K),
        duration=Quantity(120.0, "second"),
        applicability=ctx.LumpedApplicabilityDeclaration(
            characteristic_length=Quantity(0.002, "meter"),
            surface_area=Quantity(0.01, "meter**2"),
            # body_conductivity DELIBERATELY ABSENT
            conductance_excursion_bound=Quantity(60.0, K),
            capacity_excursion_bound=Quantity(100.0, K),
            melting_temperature=Quantity(900.0, K),
            surface_emissivity=Quantity(0.05, "dimensionless"),
            convection_regime=ctx.FORCED_CONVECTION,
            fluid_conductivity=Quantity(0.0261, "watt/meter/kelvin"),
            fluid_kinematic_viscosity=Quantity(1.589e-5, "meter**2/second"),
            fluid_prandtl_number=Quantity(0.707, "dimensionless"),
            fluid_velocity=Quantity(1.0, "meter/second"),
            convection_length=Quantity(0.6, "meter"),
        ),
    )


def _with_parameters(problem, values):
    """The same problem with extra caller parameters, through public APIs only.

    Built by round-tripping the record's own ``to_dict``/``from_dict``, which is
    how the review reproduced this: no private attribute is touched and nothing
    is monkeypatched. A caller assembling a problem by hand reaches the same
    place more directly.
    """
    payload = problem.to_dict()
    payload["parameters"].extend(
        ScientificParameter(name=name, value=value).to_dict()
        for name, value in values.items()
    )
    return ScientificProblem.from_dict(payload)


def _assess(problem):
    return lump.assess_lumped_validity(
        problem,
        initial_temperature=Quantity(300.0, K),
        ambient_temperature=Quantity(300.0, K),
        heat_input=Quantity(1.0, "watt"),
    )


def test_f03_a_caller_parameter_cannot_stand_in_for_a_failed_derivation():
    """The reproduction: two UNKNOWN conditions bought with two parameters.

    Without ``body_conductivity`` the Biot number cannot be formed, so
    ``biot_number`` and ``internal_fourier_number`` are UNKNOWN and the model's
    verdict is UNKNOWN. Context assembly started from every caller parameter and
    overwrote only what it managed to derive, so a caller parameter of the same
    name survived and was read as derived evidence — turning the honest UNKNOWN
    into a verdict about numbers nobody computed, with ``body_conductivity``
    still absent.
    """
    problem = lump.build_lumped_thermal_problem(_incomplete_body())

    honest = _assess(problem)
    assert honest.status is ValidityStatus.UNKNOWN
    assert honest.unknown == (ctx.BIOT_NUMBER, ctx.INTERNAL_FOURIER_NUMBER)

    forged = _assess(
        _with_parameters(
            problem,
            {
                ctx.BIOT_NUMBER: Quantity(0.05, "dimensionless"),
                ctx.INTERNAL_FOURIER_NUMBER: Quantity(5.0, "dimensionless"),
            },
        )
    )
    assert forged.status is ValidityStatus.UNKNOWN
    assert forged.unknown == honest.unknown
    assert ctx.BIOT_NUMBER not in forged.satisfied
    assert ctx.BIOT_NUMBER not in forged.violated


@pytest.mark.parametrize("declared", [True, False])
def test_f03_colliding_with_every_derived_name_changes_no_verdict(declared):
    """Not one name and not the two that were noticed: all of them.

    Run against a body that declares everything and one that declares no
    ``body_conductivity``. The second case is the one that matters — where a
    derivation *fails*, and where the old assembly therefore left the caller's
    value in place. The first is the regression guard: reserving a name must
    not stop the domain from filling it.
    """
    body = (
        lump.ThermalBody(
            body_id="R1",
            heat_capacity=Quantity(2.5, "joule/kelvin"),
            ambient_conductance=Quantity(0.05, "watt/kelvin"),
            ambient_temperature=Quantity(300.0, K),
            initial_temperature=Quantity(300.0, K),
            duration=Quantity(120.0, "second"),
            applicability=ctx.LumpedApplicabilityDeclaration(
                characteristic_length=Quantity(0.002, "meter"),
                surface_area=Quantity(0.01, "meter**2"),
                body_conductivity=Quantity(200.0, "watt/meter/kelvin"),
                conductance_excursion_bound=Quantity(60.0, K),
                capacity_excursion_bound=Quantity(100.0, K),
                melting_temperature=Quantity(900.0, K),
                surface_emissivity=Quantity(0.05, "dimensionless"),
                convection_regime=ctx.FORCED_CONVECTION,
                fluid_conductivity=Quantity(0.0261, "watt/meter/kelvin"),
                fluid_kinematic_viscosity=Quantity(1.589e-5, "meter**2/second"),
                fluid_prandtl_number=Quantity(0.707, "dimensionless"),
                fluid_velocity=Quantity(1.0, "meter/second"),
                convection_length=Quantity(0.6, "meter"),
            ),
        )
        if declared
        else _incomplete_body()
    )
    problem = lump.build_lumped_thermal_problem(body)
    honest = _assess(problem)

    collisions = {
        name: Quantity(0.05, "dimensionless")
        for name in ctx.ASSEMBLED_QUANTITIES
    }
    assert collisions  # the reserved set is not empty
    assert _assess(_with_parameters(problem, collisions)) == honest


def test_f03_every_derivable_name_is_reserved():
    """The registry cannot fall behind the assembler.

    A derived quantity added without being reserved would be impersonable again
    on the day it landed, and nothing would say so. The assembler refuses to
    emit a name the registry does not know, and this is that refusal exercised
    against everything the assembler can actually produce.
    """
    derivable = set(
        ctx.derived_lumped_quantities(
            {
                "ambient_conductance": Quantity(0.05, "watt/kelvin"),
                "heat_capacity": Quantity(2.5, "joule/kelvin"),
                "duration": Quantity(120.0, "second"),
                ctx.SURFACE_AREA: Quantity(0.01, "meter**2"),
                ctx.CHARACTERISTIC_LENGTH: Quantity(0.002, "meter"),
                ctx.BODY_CONDUCTIVITY: Quantity(200.0, "watt/meter/kelvin"),
                ctx.SURFACE_EMISSIVITY: Quantity(0.05, "dimensionless"),
                ctx.CONDUCTANCE_EXCURSION_BOUND: Quantity(60.0, K),
                ctx.CAPACITY_EXCURSION_BOUND: Quantity(100.0, K),
                ctx.MELTING_TEMPERATURE: Quantity(900.0, K),
            },
            initial_temperature=Quantity(300.0, K),
            ambient_temperature=Quantity(300.0, K),
            heat_input=Quantity(1.0, "watt"),
        )
    )
    assert derivable
    assert derivable <= ctx.ASSEMBLED_QUANTITIES


def test_f03_the_omission_tests_still_describe_the_same_behaviour():
    """A missing declaration is still UNKNOWN, and still not IN_DOMAIN."""
    assessment = _assess(lump.build_lumped_thermal_problem(_incomplete_body()))
    assert assessment.status is ValidityStatus.UNKNOWN
    assert ctx.BIOT_NUMBER in assessment.unknown
    assert ctx.BIOT_NUMBER not in assessment.satisfied
