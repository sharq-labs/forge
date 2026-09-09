"""Thermal relationships, checked against derivations done here.

Every expected value in this module is computed from a textbook definition
written out in the test, from a finite-difference derivative, or from a second
published correlation. None is read from Forge, from the benchmark generator,
or from a constant either of them owns.

Tolerances are stated with their basis, and none of them was chosen by looking
at what Forge returned.
"""

from __future__ import annotations

import math

import pytest

from src.engcore.domains.thermal_models import context as thermal
from src.engcore.scientific.units.quantity import Quantity

from .oracle_ids import oracle

#: CODATA 2018. Written here rather than imported, so a change to Forge's
#: constant is something this file DISAGREES with rather than follows.
STEFAN_BOLTZMANN = 5.670374419e-8  # W m^-2 K^-4

#: Double precision carries ~1e-16 relative; a handful of arithmetic
#: operations on well-scaled inputs cannot lose more than a few ulps, so 1e-12
#: is four orders of margin over the floating-point floor and still far tighter
#: than any physical claim. It is a numerical bound, not a physical one.
FLOATING_POINT = 1e-12


def q(value, units):
    return Quantity(value, units)


# =====================================================================
# ORA-DIM-GROUPS -- the dimensionless groups, from their definitions
# =====================================================================

ORACLE_DIM = "ORA-DIM-GROUPS"


@pytest.mark.parametrize(
    "h,length,k",
    [
        (5.0, 0.01, 200.0),
        (25.0, 0.05, 15.0),
        (1.0e-3, 1.0, 0.026),
        (1000.0, 1e-4, 400.0),
    ],
)
def test_biot_number_equals_hL_over_k(h, length, k):
    """Bi = hL/k. Incropera 6th ed. Eq. 5.10."""
    assert oracle(ORACLE_DIM).independent
    expected = h * length / k          # the definition, written out
    got = thermal.biot_number(
        coefficient=q(h, "watt/meter**2/kelvin"),
        length=q(length, "meter"),
        conductivity=q(k, "watt/meter/kelvin"),
    )
    assert got.units == "dimensionless"
    assert got.magnitude == pytest.approx(expected, rel=FLOATING_POINT)


@pytest.mark.parametrize(
    "capacity,conductance",
    [(2.6, 0.019), (10.9, 0.243), (1.0, 1.0), (1e4, 1e-3)],
)
def test_thermal_time_constant_equals_C_over_hA(capacity, conductance):
    """tau = C / (hA). Incropera 6th ed. Eq. 5.7, thermal time constant."""
    expected = capacity / conductance
    got = thermal.thermal_time_constant(
        heat_capacity=q(capacity, "joule/kelvin"),
        ambient_conductance=q(conductance, "watt/kelvin"),
    )
    assert got.units == "second"
    assert got.magnitude == pytest.approx(expected, rel=FLOATING_POINT)


@pytest.mark.parametrize(
    "duration,tau,bi",
    [(600.0, 100.0, 0.05), (1.0, 1000.0, 0.001), (5.0, 5.0, 0.1)],
)
def test_internal_fourier_number_is_the_horizon_over_biot(duration, tau, bi):
    """Fo = alpha t / L^2, and alpha t / L^2 == (t/tau)/Bi identically.

    The identity is worth writing out because it is the whole reason a lumped
    model can report an INTERNAL diffusion time without ever being given a
    diffusivity:

        Fo = alpha t / L^2
           = (k/(rho c)) t / L^2
           = t (k/L) / (rho c L)
           = t / (tau Bi)      since tau = rho c V/(hA) and Bi = hL/k

    So this asserts an algebraic identity, not a coincidence.
    """
    expected = (duration / tau) / bi
    horizon = thermal.transient_horizon_ratio(
        duration=q(duration, "second"), time_constant=q(tau, "second")
    )
    assert horizon.magnitude == pytest.approx(duration / tau, rel=FLOATING_POINT)
    got = thermal.internal_fourier_number(
        horizon_ratio=horizon, biot=q(bi, "dimensionless")
    )
    assert got.units == "dimensionless"
    assert got.magnitude == pytest.approx(expected, rel=FLOATING_POINT)


@pytest.mark.parametrize(
    "beta,dT,length,nu,pr",
    [
        (3.4e-3, 20.0, 0.05, 1.589e-5, 0.707),
        (2.7e-3, 100.0, 0.2, 1.6e-5, 0.71),
        (1.0e-3, 1.0, 0.01, 1.0e-6, 7.0),
    ],
)
def test_rayleigh_number_equals_its_definition(beta, dT, length, nu, pr):
    """Ra = g beta dT L^3 / (nu alpha_f), with alpha_f = nu/Pr.

    Written in the Pr form -- Ra = g beta dT L^3 Pr / nu^2 -- so the oracle
    reaches the same number by a different grouping than a nu*alpha product.
    Incropera 6th ed. Eq. 9.25. g from the SI standard, 9.80665 m/s^2.
    """
    expected = 9.80665 * beta * dT * length ** 3 * pr / nu ** 2
    got = thermal.rayleigh_number(
        expansion_coefficient=q(beta, "1/kelvin"),
        temperature_difference=q(dT, "kelvin"),
        length=q(length, "meter"),
        kinematic_viscosity=q(nu, "meter**2/second"),
        prandtl_number=q(pr, "dimensionless"),
    )
    assert got.units == "dimensionless"
    # 1e-9 rather than 1e-12: the two groupings differ in operation order, so
    # the comparison carries a few extra ulps of reassociation error.
    assert got.magnitude == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize(
    "velocity,length,nu",
    [(1.0, 0.1, 1.589e-5), (20.0, 2.0, 1.5e-5), (1e-3, 1e-3, 1e-6)],
)
def test_reynolds_number_equals_vL_over_nu(velocity, length, nu):
    """Re = vL/nu. Incropera 6th ed. Eq. 6.41."""
    expected = velocity * length / nu
    got = thermal.reynolds_number(
        velocity=q(velocity, "meter/second"),
        length=q(length, "meter"),
        kinematic_viscosity=q(nu, "meter**2/second"),
    )
    assert got.units == "dimensionless"
    assert got.magnitude == pytest.approx(expected, rel=FLOATING_POINT)


# =====================================================================
# ORA-RAD-LINEARIZATION -- against the derivative it claims to be
# =====================================================================

ORACLE_RAD = "ORA-RAD-LINEARIZATION"


def _exact_radiant_flux(emissivity, surface_k, surroundings_k):
    """q'' = eps sigma (Ts^4 - Tsur^4). Stefan-Boltzmann, grey diffuse body."""
    return emissivity * STEFAN_BOLTZMANN * (surface_k ** 4 - surroundings_k ** 4)


@pytest.mark.parametrize(
    "eps,ts,tsur",
    [
        (0.03, 350.0, 300.0),
        (0.9, 500.0, 300.0),
        (0.5, 301.0, 300.0),
        (0.8, 1200.0, 300.0),
    ],
)
def test_linearized_radiation_coefficient_reproduces_the_exact_flux(eps, ts, tsur):
    """h_r is EXACT, not approximate, and this is what that means.

    ``h_r (Ts - Tsur)`` must equal ``eps sigma (Ts^4 - Tsur^4)`` identically,
    because ``a^4 - b^4 = (a^2+b^2)(a+b)(a-b)``. So the check is not "close to"
    -- it is an algebraic identity, and a coefficient that merely approximated
    the flux would fail it at the wide temperature differences below.
    """
    assert oracle(ORACLE_RAD).independent
    got = thermal.linearized_radiation_coefficient(
        emissivity=q(eps, "dimensionless"),
        surface_temperature=q(ts, "kelvin"),
        surroundings_temperature=q(tsur, "kelvin"),
    )
    assert got.units == "watt / kelvin / meter ** 2"
    reconstructed = got.magnitude * (ts - tsur)
    assert reconstructed == pytest.approx(
        _exact_radiant_flux(eps, ts, tsur), rel=1e-12
    )


@pytest.mark.parametrize("eps,t", [(0.03, 300.0), (0.9, 800.0)])
def test_h_r_approaches_the_derivative_of_the_flux_as_the_gap_closes(eps, t):
    """As Ts -> Tsur, h_r must approach d/dT [eps sigma T^4] = 4 eps sigma T^3.

    A second, genuinely different route to the same coefficient: a central
    finite difference of the exact law rather than its factorisation.
    """
    step = 1e-4
    derivative = (
        _exact_radiant_flux(eps, t + step, t) - _exact_radiant_flux(eps, t - step, t)
    ) / (2 * step)
    analytic = 4.0 * eps * STEFAN_BOLTZMANN * t ** 3
    # The finite difference is second-order accurate; at this step it agrees
    # with the closed derivative to ~1e-9 relative, which bounds the comparison.
    assert derivative == pytest.approx(analytic, rel=1e-9)

    near = thermal.linearized_radiation_coefficient(
        emissivity=q(eps, "dimensionless"),
        surface_temperature=q(t + 1e-6, "kelvin"),
        surroundings_temperature=q(t, "kelvin"),
    )
    assert near.magnitude == pytest.approx(analytic, rel=1e-6)


def test_radiation_to_convection_ratio_is_the_share_it_claims_to_be():
    """The ratio must be h_r/h, so that h_r/(h_r+h) is the radiant share."""
    h_r = thermal.linearized_radiation_coefficient(
        emissivity=q(0.9, "dimensionless"),
        surface_temperature=q(400.0, "kelvin"),
        surroundings_temperature=q(300.0, "kelvin"),
    )
    ratio = thermal.radiation_to_convection_ratio(
        radiation_coefficient=h_r, coefficient=q(12.0, "watt/meter**2/kelvin")
    )
    assert ratio.magnitude == pytest.approx(h_r.magnitude / 12.0, rel=FLOATING_POINT)


# =====================================================================
# ORA-FREE-CONVECTION-CROSS -- two publications against each other
# =====================================================================

ORACLE_CONV = "ORA-FREE-CONVECTION-CROSS"


def _churchill_chu_1975(rayleigh, prandtl):
    """Transcribed from the citation, not from Forge.

    Nu = 0.68 + 0.670 Ra^(1/4) / [1 + (0.492/Pr)^(9/16)]^(4/9),  Ra <= 1e9.
    """
    return 0.68 + 0.670 * rayleigh ** 0.25 / (
        1.0 + (0.492 / prandtl) ** (9.0 / 16.0)
    ) ** (4.0 / 9.0)


def _mcadams_1954(rayleigh):
    """A DIFFERENT publication for the same configuration.

    Nu = 0.59 Ra^(1/4), vertical isothermal plate, 1e4 <= Ra <= 1e9.
    McAdams, Heat Transmission, 3rd ed. (1954).
    """
    return 0.59 * rayleigh ** 0.25


@pytest.mark.parametrize("ra", [1e4, 1e5, 1e6, 1e7, 1e8, 1e9])
def test_forge_reproduces_the_published_churchill_chu_equation(ra):
    """Transcription check: Forge against the equation as printed."""
    got = thermal.churchill_chu_nusselt(
        rayleigh=q(ra, "dimensionless"), prandtl_number=q(0.707, "dimensionless")
    )
    assert got.magnitude == pytest.approx(
        _churchill_chu_1975(ra, 0.707), rel=FLOATING_POINT
    )


#: The bound below is DERIVED, not chosen. For a fixed Pr the two published
#: forms are
#:
#:     Churchill-Chu   Nu = 0.68 + (0.670/D) Ra^(1/4),  D = [1+(0.492/Pr)^(9/16)]^(4/9)
#:     McAdams         Nu = 0.59 Ra^(1/4)
#:
#: so their ratio is  (0.68/0.59) Ra^(-1/4) + (0.670/D)/0.59 , which is
#: monotonically DECREASING in Ra and tends to (0.670/D)/0.59 as Ra grows. The
#: largest disagreement over any range is therefore at its top end, and it is
#: set entirely by the two leading coefficients.
#:
#: My first estimate of this had the sign of the trend backwards -- it is
#: recorded here because the tolerance was then re-derived from the
#: publications rather than adjusted until the test passed.
def _asymptotic_ratio(prandtl):
    denominator = (1.0 + (0.492 / prandtl) ** (9.0 / 16.0)) ** (4.0 / 9.0)
    return (0.670 / denominator) / 0.59


@pytest.mark.parametrize("ra", [1e4, 1e5, 1e6, 1e7, 1e8, 1e9])
def test_two_independently_published_correlations_agree_within_their_scatter(ra):
    """The cross-check that is not a transcription check.

    Churchill-Chu (1975) and McAdams (1954) were fitted two decades apart by
    different authors to overlapping experimental corpora. For air over the
    laminar range they must agree to within the scatter such correlations
    carry -- free-convection correlations are conventionally quoted at
    +/-10-20 %, and Churchill & Chu discuss the spread of the data they fit.

    The bound is the asymptotic ratio computed above from the two published
    coefficient sets, plus nothing. A wrong exponent or a misplaced constant
    in Forge's transcription would leave this band immediately.
    """
    assert oracle(ORACLE_CONV).independent
    forge = thermal.churchill_chu_nusselt(
        rayleigh=q(ra, "dimensionless"), prandtl_number=q(0.707, "dimensionless")
    ).magnitude
    mcadams = _mcadams_1954(ra)
    disagreement = abs(forge - mcadams) / mcadams
    bound = 1.0 - _asymptotic_ratio(0.707)
    assert disagreement <= bound + 1e-12, (
        f"Ra={ra:g}: Churchill-Chu via Forge gives {forge:.4f}, McAdams gives "
        f"{mcadams:.4f}, a {disagreement:.2%} disagreement -- past the "
        f"{bound:.2%} the two published coefficient sets can explain"
    )


def test_the_disagreement_between_the_two_correlations_is_fully_explained():
    """Not just bounded -- accounted for, term by term.

    If the whole difference between the two publications is the algebra above,
    then the measured ratio must equal the predicted ratio at every Ra. That is
    a far stronger statement than "within 13 %": it says there is no unexplained
    residue anywhere in the range, which is what would show up if Forge had
    transcribed one coefficient wrongly.
    """
    predicted_asymptote = _asymptotic_ratio(0.707)
    previous = None
    for ra in (1e4, 1e5, 1e6, 1e7, 1e8, 1e9):
        forge = thermal.churchill_chu_nusselt(
            rayleigh=q(ra, "dimensionless"),
            prandtl_number=q(0.707, "dimensionless"),
        ).magnitude
        ratio = forge / _mcadams_1954(ra)
        predicted = (0.68 / 0.59) * ra ** -0.25 + predicted_asymptote
        assert ratio == pytest.approx(predicted, rel=1e-12), ra
        # ...and the trend really is monotone decreasing, as the algebra says.
        if previous is not None:
            assert ratio < previous, ra
        previous = ratio

    # The two are not the same correlation, so the agreement test is not
    # comparing something with itself.
    assert 0.85 < predicted_asymptote < 0.90
    assert _churchill_chu_1975(1e4, 0.707) != _mcadams_1954(1e4)


def test_correlated_surface_coefficient_inverts_the_nusselt_definition():
    """Nu = hL/k, so h = Nu k / L. Same definition, solved the other way."""
    got = thermal.correlated_surface_coefficient(
        nusselt=q(42.0, "dimensionless"),
        fluid_conductivity=q(0.026, "watt/meter/kelvin"),
        length=q(0.05, "meter"),
    )
    assert got.magnitude == pytest.approx(42.0 * 0.026 / 0.05, rel=FLOATING_POINT)
    # ...and the round trip closes, which is the identity worth asserting.
    back = thermal.biot_number(
        coefficient=got, length=q(0.05, "meter"), conductivity=q(0.026, "watt/meter/kelvin")
    )
    assert back.magnitude == pytest.approx(42.0, rel=1e-9)
