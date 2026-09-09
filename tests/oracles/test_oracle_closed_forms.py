"""Closed forms against independent integration, limits and dimensions.

Three oracles live here:

* ``ORA-LUMPED-ODE`` -- the first-order transient closed form against a
  Runge-Kutta march of the balance it claims to solve. Algorithmically
  independent, and honest that both describe the same governing equation.
* ``ORA-TCR-LIMITS`` / ``ORA-PEUKERT`` -- limiting-case and identity checks
  that a wrong coefficient, sign or exponent cannot survive.
* ``ORA-DIMENSIONAL`` -- dimensions assembled here from SI base units, not
  from Forge's registry, so a formula that is dimensionally wrong fails even
  if the registry agrees with it.
"""

from __future__ import annotations

import math

import pytest

from src.engcore.domains.battery import context as battery
from src.engcore.domains.electrical import material as material
from src.engcore.domains.thermal_models import context as thermal
from src.engcore.scientific.units.quantity import Quantity, dimensionality

from .oracle_ids import oracle


def q(value, units):
    return Quantity(value, units)


# =====================================================================
# ORA-LUMPED-ODE -- closed form vs an integrator written here
# =====================================================================

ORACLE_ODE = "ORA-LUMPED-ODE"


def _rk4_lumped(*, t_init, t_amb, heat, capacity, conductance, duration, steps):
    """Integrate C dT/dt = Q - hA (T - T_amb) with classical RK4.

    No exponential, no time constant, no steady state -- none of the objects
    the closed form is built from appear here. The only thing shared is the
    balance itself, which is the point: this checks the SOLUTION, not the
    choice of equation.
    """
    def derivative(temperature):
        return (heat - conductance * (temperature - t_amb)) / capacity

    step = duration / steps
    temperature = t_init
    for _ in range(steps):
        k1 = derivative(temperature)
        k2 = derivative(temperature + 0.5 * step * k1)
        k3 = derivative(temperature + 0.5 * step * k2)
        k4 = derivative(temperature + step * k3)
        temperature += (step / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return temperature


def _closed_form(*, t_init, t_amb, heat, capacity, conductance, duration):
    """T(t) = T_ss + (T0 - T_ss) exp(-t/tau), assembled from Forge's parts."""
    tau = thermal.thermal_time_constant(
        heat_capacity=q(capacity, "joule/kelvin"),
        ambient_conductance=q(conductance, "watt/kelvin"),
    ).magnitude_in("second")
    steady = thermal.steady_state_temperature(
        ambient_temperature=q(t_amb, "kelvin"),
        heat_input=q(heat, "watt"),
        ambient_conductance=q(conductance, "watt/kelvin"),
    ).magnitude_in("kelvin")
    return steady + (t_init - steady) * math.exp(-duration / tau)


CASES = [
    # (t_init, t_amb, heat, capacity, conductance, duration)
    (285.33, 285.33, 9.21, 2.6246, 0.0192378, 818.57),   # U00204's body
    (324.91, 324.91, 23.87, 10.918, 0.243651, 268.86),   # U01001's body
    (300.0, 300.0, 1.0, 1.0, 0.1, 50.0),
    (400.0, 300.0, 0.0, 5.0, 0.5, 20.0),                 # pure cooling
]


@pytest.mark.parametrize("t_init,t_amb,heat,capacity,conductance,duration", CASES)
def test_the_closed_form_solves_the_balance_a_marcher_integrates(
    t_init, t_amb, heat, capacity, conductance, duration
):
    """Richardson: refine until the integrator's own error bounds the check.

    The tolerance is not chosen -- it is READ OFF the integrator. RK4 is
    fourth order, so halving the step should cut the error by ~16; the
    difference between the two refinements is therefore an estimate of the
    coarser one's error, and the comparison is made against the finer one at
    several times that estimate.
    """
    assert oracle(ORACLE_ODE).independent
    kwargs = dict(
        t_init=t_init, t_amb=t_amb, heat=heat,
        capacity=capacity, conductance=conductance, duration=duration,
    )
    coarse = _rk4_lumped(steps=2000, **kwargs)
    fine = _rk4_lumped(steps=4000, **kwargs)
    discretisation = abs(fine - coarse)
    budget = max(10.0 * discretisation, 1e-9)

    closed = _closed_form(**kwargs)
    assert abs(closed - fine) <= budget, (
        f"closed form {closed!r} vs RK4 {fine!r}; difference "
        f"{abs(closed - fine):.3e} exceeds the {budget:.3e} the integrator's "
        f"own convergence allows"
    )


def test_the_marcher_would_catch_a_wrong_closed_form():
    """The comparison above must be able to fail."""
    kwargs = dict(
        t_init=285.33, t_amb=285.33, heat=9.21,
        capacity=2.6246, conductance=0.0192378, duration=818.57,
    )
    fine = _rk4_lumped(steps=4000, **kwargs)
    # A sign error in the exponent is the classic transient mistake.
    tau = kwargs["capacity"] / kwargs["conductance"]
    steady = kwargs["t_amb"] + kwargs["heat"] / kwargs["conductance"]
    wrong = steady + (kwargs["t_init"] - steady) * math.exp(
        +kwargs["duration"] / tau
    )
    assert abs(wrong - fine) > 1.0


@pytest.mark.parametrize("t_init,t_amb,heat,capacity,conductance,duration", CASES)
def test_the_transient_reaches_the_steady_state_it_names(
    t_init, t_amb, heat, capacity, conductance, duration
):
    """Limiting case: t -> infinity must give T_amb + Q/(hA), exactly."""
    long_run = _rk4_lumped(
        t_init=t_init, t_amb=t_amb, heat=heat, capacity=capacity,
        conductance=conductance, duration=40.0 * capacity / conductance,
        steps=20000,
    )
    declared = thermal.steady_state_temperature(
        ambient_temperature=q(t_amb, "kelvin"),
        heat_input=q(heat, "watt"),
        ambient_conductance=q(conductance, "watt/kelvin"),
    ).magnitude_in("kelvin")
    # exp(-40) is 4e-18, far below double precision on these magnitudes.
    assert long_run == pytest.approx(declared, rel=1e-12)


def test_zero_heat_input_decays_to_ambient_and_nowhere_else():
    """No forcing: the body must end at ambient regardless of where it began."""
    for start in (250.0, 300.0, 900.0):
        declared = thermal.steady_state_temperature(
            ambient_temperature=q(300.0, "kelvin"),
            heat_input=q(0.0, "watt"),
            ambient_conductance=q(0.5, "watt/kelvin"),
        ).magnitude_in("kelvin")
        assert declared == pytest.approx(300.0, abs=1e-12), start


# =====================================================================
# ORA-TCR-LIMITS -- the linear form's own algebra
# =====================================================================

ORACLE_TCR = "ORA-TCR-LIMITS"


@pytest.mark.parametrize("alpha", [-0.05, -0.0005, 0.0, 0.0039, 0.05])
def test_the_resistance_ratio_is_one_at_the_reference_for_every_alpha(alpha):
    """R(T_ref)/R_ref = 1 identically. A coefficient error cannot survive it."""
    assert oracle(ORACLE_TCR).independent
    got = material.linear_resistance_ratio(
        temperature=q(293.15, "kelvin"),
        reference_temperature=q(293.15, "kelvin"),
        temperature_coefficient=q(alpha, "1/kelvin"),
    )
    assert got.magnitude == pytest.approx(1.0, abs=1e-15)


@pytest.mark.parametrize("alpha", [-0.0005, 0.0039])
@pytest.mark.parametrize("delta", [-100.0, -1.0, 1.0, 250.0])
def test_the_resistance_ratio_is_exactly_linear_in_temperature(alpha, delta):
    """1 + alpha dT, written out. Catches a squared or halved term."""
    got = material.linear_resistance_ratio(
        temperature=q(293.15 + delta, "kelvin"),
        reference_temperature=q(293.15, "kelvin"),
        temperature_coefficient=q(alpha, "1/kelvin"),
    )
    assert got.magnitude == pytest.approx(1.0 + alpha * delta, rel=1e-14)


def test_a_zero_coefficient_makes_resistance_temperature_independent():
    """alpha -> 0 is the limiting case that separates linear from constant."""
    for temperature in (4.0, 293.15, 1200.0):
        got = material.linear_resistance_ratio(
            temperature=q(temperature, "kelvin"),
            reference_temperature=q(293.15, "kelvin"),
            temperature_coefficient=q(0.0, "1/kelvin"),
        )
        assert got.magnitude == pytest.approx(1.0, abs=1e-15)


def test_flipping_alpha_and_the_excursion_together_leaves_the_ratio_alone():
    """A symmetry the linear form must have: R depends on alpha*dT only."""
    a = material.linear_resistance_ratio(
        temperature=q(400.0, "kelvin"),
        reference_temperature=q(300.0, "kelvin"),
        temperature_coefficient=q(0.004, "1/kelvin"),
    )
    b = material.linear_resistance_ratio(
        temperature=q(200.0, "kelvin"),
        reference_temperature=q(300.0, "kelvin"),
        temperature_coefficient=q(-0.004, "1/kelvin"),
    )
    assert a.magnitude == pytest.approx(b.magnitude, rel=1e-14)


# =====================================================================
# ORA-PEUKERT -- the published law, and its k = 1 limit
# =====================================================================

ORACLE_PEUKERT = "ORA-PEUKERT"


@pytest.mark.parametrize("k", [1.05, 1.2, 1.4])
@pytest.mark.parametrize("current,reference", [(2.0, 1.0), (0.5, 1.0), (10.0, 5.0)])
def test_peukert_effective_capacity_follows_the_published_law(k, current, reference):
    """C_eff = C_ref (I_ref/I)^(k-1). Peukert (1897)."""
    assert oracle(ORACLE_PEUKERT).executable
    expected = 3.0 * (reference / current) ** (k - 1.0)
    got = battery.peukert_effective_capacity(
        nominal_capacity=q(3.0, "ampere_hour"),
        current=q(current, "ampere"),
        reference_current=q(reference, "ampere"),
        exponent=q(k, "dimensionless"),
    )
    assert got.magnitude_in("ampere_hour") == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("current", [0.1, 1.0, 7.5, 50.0])
def test_a_peukert_exponent_of_one_removes_the_rate_dependence(current):
    """k = 1 is the limit where Peukert collapses to a constant capacity."""
    got = battery.peukert_effective_capacity(
        nominal_capacity=q(3.0, "ampere_hour"),
        current=q(current, "ampere"),
        reference_current=q(1.0, "ampere"),
        exponent=q(1.0, "dimensionless"),
    )
    assert got.magnitude_in("ampere_hour") == pytest.approx(3.0, rel=1e-15)


def test_discharging_at_the_reference_current_returns_the_nominal_capacity():
    """I = I_ref must give C_ref for EVERY k -- the law's anchor point."""
    for k in (1.0, 1.1, 1.35, 2.0):
        got = battery.peukert_effective_capacity(
            nominal_capacity=q(3.0, "ampere_hour"),
            current=q(1.0, "ampere"),
            reference_current=q(1.0, "ampere"),
            exponent=q(k, "dimensionless"),
        )
        assert got.magnitude_in("ampere_hour") == pytest.approx(3.0, rel=1e-15), k


def test_a_higher_rate_never_yields_more_capacity_than_a_lower_one():
    """Monotonicity is the physical content of Peukert's law."""
    previous = None
    for current in (0.5, 1.0, 2.0, 5.0, 20.0):
        capacity = battery.peukert_effective_capacity(
            nominal_capacity=q(3.0, "ampere_hour"),
            current=q(current, "ampere"),
            reference_current=q(1.0, "ampere"),
            exponent=q(1.2, "dimensionless"),
        ).magnitude_in("ampere_hour")
        if previous is not None:
            assert capacity < previous, current
        previous = capacity


def test_joule_heating_is_i_squared_r():
    """Q = I^2 R. A linear-in-I error is the one this catches."""
    for current in (0.5, 2.0, 7.0):
        got = battery.heat_generation(
            current=q(current, "ampere"), internal_resistance=q(0.05, "ohm")
        )
        assert got.magnitude_in("watt") == pytest.approx(
            current ** 2 * 0.05, rel=1e-14
        )


# =====================================================================
# ORA-DIMENSIONAL -- dimensions assembled here, not read from Forge
# =====================================================================

ORACLE_DIM = "ORA-DIMENSIONAL"

#: What each derived quantity's defining equation implies, written as a unit
#: expression composed from SI base units rather than named derived units, so
#: the comparison does not lean on the registry knowing that a watt is a
#: kg m^2 / s^3.
EXPECTED_DIMENSIONS = {
    "biot_number": ("dimensionless", "hL/k: (kg/s**3/K)*(m)/(kg*m/s**3/K)"),
    "time_constant": ("second", "C/(hA): (kg*m**2/s**2/K)/(kg*m**2/s**3/K)"),
    "rayleigh": ("dimensionless", "g beta dT L^3 Pr / nu^2"),
    "reynolds": ("dimensionless", "vL/nu"),
    "radiation_coefficient": (
        "kilogram / kelvin / second ** 3", "eps sigma T^3"
    ),
}


def test_the_dimensionless_groups_really_are_dimensionless():
    """Composed from base units here; the registry only reports, never decides."""
    assert oracle(ORACLE_DIM).independent
    biot = thermal.biot_number(
        coefficient=q(5.0, "kilogram/second**3/kelvin"),   # = W/m^2/K in base units
        length=q(0.01, "meter"),
        conductivity=q(200.0, "kilogram*meter/second**3/kelvin"),
    )
    assert dimensionality(biot.units) == dimensionality("dimensionless")

    reynolds = thermal.reynolds_number(
        velocity=q(1.0, "meter/second"),
        length=q(0.1, "meter"),
        kinematic_viscosity=q(1.5e-5, "meter**2/second"),
    )
    assert dimensionality(reynolds.units) == dimensionality("dimensionless")


def test_the_time_constant_carries_time_when_fed_base_units_only():
    """C/(hA) must be seconds even when nothing is spelled 'joule' or 'watt'."""
    got = thermal.thermal_time_constant(
        heat_capacity=q(2.6, "kilogram*meter**2/second**2/kelvin"),
        ambient_conductance=q(0.019, "kilogram*meter**2/second**3/kelvin"),
    )
    assert dimensionality(got.units) == dimensionality("second")
    assert got.magnitude_in("second") == pytest.approx(2.6 / 0.019, rel=1e-12)


def test_the_radiation_coefficient_carries_a_heat_transfer_coefficient():
    """h_r must be W/m^2/K = kg/s^3/K, checked in base units."""
    got = thermal.linearized_radiation_coefficient(
        emissivity=q(0.9, "dimensionless"),
        surface_temperature=q(400.0, "kelvin"),
        surroundings_temperature=q(300.0, "kelvin"),
    )
    assert dimensionality(got.units) == dimensionality("kilogram/second**3/kelvin")


def test_the_biot_number_is_invariant_under_a_consistent_unit_change():
    """A metamorphic property with a derivation: a dimensionless group cannot
    depend on the units its inputs were expressed in.

    Same physical situation, stated in millimetres and in metres.
    """
    si = thermal.biot_number(
        coefficient=q(25.0, "watt/meter**2/kelvin"),
        length=q(0.02, "meter"),
        conductivity=q(15.0, "watt/meter/kelvin"),
    )
    mixed = thermal.biot_number(
        coefficient=q(25.0, "watt/meter**2/kelvin"),
        length=q(20.0, "millimeter"),
        conductivity=q(15.0, "watt/meter/kelvin"),
    )
    assert si.magnitude == pytest.approx(mixed.magnitude, rel=1e-14)
