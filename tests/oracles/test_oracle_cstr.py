"""Kinetics CSTR against balances and a root solver written here.

This domain was UNVERIFIED. Forge integrates the non-isothermal first-order
CSTR

    dC/dt = a (Cf - C) - k(T) C
    dT/dt = a (Tf - T) + beta k(T) C - gamma (T - Tc)
    k(T)  = k0 exp(-E / (R T))

with SciPy. Three oracles here, none of which import that integration:

* the STEADY STATE, obtained by eliminating C analytically and bisecting the
  single remaining energy residual -- a root find, not a march;
* the TRAJECTORY, obtained by classical RK4 written here;
* LIMITING CASES with derivations, where the answer is known in closed form.

The balances themselves are shared with Forge, so these verify the SOLUTION
rather than the choice of model, and the register says so.
"""

from __future__ import annotations

import math

import pytest

from src.engcore.domains.kinetics.cstr.problem import (
    ReactorChemistry,
    ReactorOperation,
    ReactorRun,
)
from src.engcore.domains.kinetics.cstr.solver import solve_reactor
from src.engcore.scientific.units.quantity import Quantity

from .oracle_ids import oracle

ORACLE_STEADY = "ORA-CSTR-STEADY"
ORACLE_RK4 = "ORA-CSTR-RK4"

#: CODATA 2018 molar gas constant, written here rather than imported.
R_GAS = 8.314462618  # J mol^-1 K^-1


def q(value, units):
    return Quantity(value, units)


class Reactor:
    """The declared reactor, reduced to the five numbers the balances need.

    Assembled here from the payload quantities so the oracle never reads a
    grouped coefficient Forge computed.
    """

    def __init__(self, *, k0, e_act, dh, rho, cp, volume, flow, caf, tf, tc, ua):
        self.k0 = k0
        self.e_over_r = e_act / R_GAS
        self.a = flow / volume                       # dilution rate, 1/s
        self.beta = -dh / (rho * cp)                 # m^3 K / mol
        self.gamma = ua / (rho * cp * volume)        # 1/s
        self.caf, self.tf, self.tc = caf, tf, tc

    def k(self, temperature):
        return self.k0 * math.exp(-self.e_over_r / temperature)

    def derivatives(self, concentration, temperature):
        reaction = self.k(temperature) * concentration
        return (
            self.a * (self.caf - concentration) - reaction,
            self.a * (self.tf - temperature)
            + self.beta * reaction
            - self.gamma * (temperature - self.tc),
        )

    def steady_concentration(self, temperature):
        """dC/dt = 0 solved exactly: C = a Cf / (a + k(T))."""
        return self.a * self.caf / (self.a + self.k(temperature))

    def energy_residual(self, temperature):
        """dT/dt with C eliminated. Its roots are the steady states."""
        concentration = self.steady_concentration(temperature)
        return (
            self.a * (self.tf - temperature)
            + self.beta * self.k(temperature) * concentration
            - self.gamma * (temperature - self.tc)
        )

    def steady_temperature(self, low, high, tolerance=1e-12):
        """Bisection -- bracketed, monotone in the bracket, no derivative."""
        f_low, f_high = self.energy_residual(low), self.energy_residual(high)
        assert f_low * f_high < 0.0, (
            f"no sign change on [{low}, {high}]: {f_low}, {f_high}"
        )
        for _ in range(400):
            middle = 0.5 * (low + high)
            if high - low < tolerance:
                return middle
            if self.energy_residual(middle) * f_low <= 0.0:
                high = middle
            else:
                low, f_low = middle, self.energy_residual(middle)
        return 0.5 * (low + high)

    def rk4(self, concentration, temperature, end_time, steps):
        step = end_time / steps
        for _ in range(steps):
            k1 = self.derivatives(concentration, temperature)
            k2 = self.derivatives(
                concentration + 0.5 * step * k1[0], temperature + 0.5 * step * k1[1]
            )
            k3 = self.derivatives(
                concentration + 0.5 * step * k2[0], temperature + 0.5 * step * k2[1]
            )
            k4 = self.derivatives(
                concentration + step * k3[0], temperature + step * k3[1]
            )
            concentration += (step / 6.0) * (
                k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]
            )
            temperature += (step / 6.0) * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        return concentration, temperature


#: An operating point where the reaction actually matters -- 93 % conversion,
#: a 7.8 K exotherm -- and which still has exactly ONE steady state in the
#: model's declared 250-1000 K range. Both halves are deliberate: a weakly
#: reacting point would let the balances agree for reasons that have nothing
#: to do with the kinetics, and a multiple-steady-state point would give a
#: bisection oracle more than one root to find.
#:
#: Uniqueness is not assumed -- `test_the_declared_range_holds_exactly_one
#: _steady_state` scans the range for sign changes and asserts there is one.
MILD = dict(
    k0=5.0e8, e_act=6.0e4, dh=-5.0e4, rho=1000.0, cp=4180.0,
    volume=0.1, flow=1.0e-3, caf=1000.0, tf=320.0, tc=300.0, ua=500.0,
)

#: Forge integrates with BDF at rtol = atol = 1e-8 (IntegrationSettings). The
#: comparison below is limited by THAT, not by the oracle's RK4, which at
#: 40 000 fixed steps on this smooth problem is exact to round-off. So the
#: budget is read off Forge's DECLARED tolerance rather than chosen, and a
#: run configured more loosely would widen it automatically.
FORGE_RTOL = 1.0e-8
FORGE_ATOL = 1.0e-8


def _integrator_budget(value):
    """The agreement Forge's own declared tolerance entitles it to."""
    return FORGE_RTOL * abs(value) + FORGE_ATOL


def _forge(params, *, initial_c, initial_t, end_time):
    run = ReactorRun(
        run_label="oracle",
        chemistry=ReactorChemistry(
            k0=q(params["k0"], "1/s"),
            activation_energy=q(params["e_act"], "J/mol"),
            heat_of_reaction=q(params["dh"], "J/mol"),
            density=q(params["rho"], "kg/m**3"),
            heat_capacity=q(params["cp"], "J/(kg*K)"),
        ),
        operation=ReactorOperation(
            volume=q(params["volume"], "m**3"),
            flow_rate=q(params["flow"], "m**3/s"),
            feed_concentration=q(params["caf"], "mol/m**3"),
            feed_temperature=q(params["tf"], "kelvin"),
            coolant_temperature=q(params["tc"], "kelvin"),
            ua=q(params["ua"], "W/K"),
            end_time=q(end_time, "second"),
        ),
        initial_concentration=q(initial_c, "mol/m**3"),
        initial_temperature=q(initial_t, "kelvin"),
    )
    return solve_reactor(run, run_id="oracle")


# =====================================================================
# ORA-CSTR-STEADY -- a root find against a march
# =====================================================================

def test_the_long_run_reaches_the_steady_state_a_root_finder_locates():
    """Forge marches; the oracle bisects. Different algorithms, same answer.

    The horizon is 200 residence times, so the march is at its fixed point to
    far more digits than the comparison asks for.
    """
    assert oracle(ORACLE_STEADY).independent
    reactor = Reactor(**MILD)
    residence = MILD["volume"] / MILD["flow"]

    result = _forge(
        MILD, initial_c=MILD["caf"], initial_t=MILD["tf"],
        end_time=200.0 * residence,
    )
    forge_t = result.value("T:final").magnitude_in("kelvin")
    forge_c = result.value("C_A:final").magnitude_in("mol/m**3")

    expected_t = reactor.steady_temperature(250.0, 1000.0)
    expected_c = reactor.steady_concentration(expected_t)

    assert forge_t == pytest.approx(expected_t, rel=1e-6), (
        f"steady temperature: forge {forge_t!r} vs bisection {expected_t!r}"
    )
    assert forge_c == pytest.approx(expected_c, rel=1e-6)


def test_the_located_steady_state_really_satisfies_both_balances():
    """The oracle must be right before it can judge anything.

    Both residuals are evaluated at the root and required to vanish to a
    bound set by the size of the terms that cancel, not by a round number.
    """
    reactor = Reactor(**MILD)
    temperature = reactor.steady_temperature(250.0, 1000.0)
    concentration = reactor.steady_concentration(temperature)
    d_c, d_t = reactor.derivatives(concentration, temperature)

    concentration_scale = reactor.a * reactor.caf
    temperature_scale = abs(reactor.a * reactor.tf) + abs(
        reactor.gamma * reactor.tc
    )
    assert abs(d_c) < 1e-10 * concentration_scale
    assert abs(d_t) < 1e-9 * temperature_scale


def test_conversion_is_the_fraction_the_feed_actually_lost():
    """X = (Cf - C)/Cf. A definitional identity, checked against the report."""
    residence = MILD["volume"] / MILD["flow"]
    result = _forge(
        MILD, initial_c=MILD["caf"], initial_t=MILD["tf"],
        end_time=200.0 * residence,
    )
    concentration = result.value("C_A:final").magnitude_in("mol/m**3")
    conversion = result.value("conversion:final").magnitude_in("dimensionless")
    assert conversion == pytest.approx(
        (MILD["caf"] - concentration) / MILD["caf"], rel=1e-12
    )


# =====================================================================
# ORA-CSTR-RK4 -- trajectory against an integrator written here
# =====================================================================

@pytest.mark.parametrize("horizon", [0.5, 2.0, 10.0])
def test_the_trajectory_agrees_with_an_independent_rk4_march(horizon):
    """Tolerance from Richardson refinement, not chosen."""
    assert oracle(ORACLE_RK4).independent
    reactor = Reactor(**MILD)
    residence = MILD["volume"] / MILD["flow"]
    end_time = horizon * residence

    coarse = reactor.rk4(MILD["caf"], MILD["tf"], end_time, 20000)
    fine = reactor.rk4(MILD["caf"], MILD["tf"], end_time, 40000)
    # The oracle's own discretisation error, by Richardson. It must be well
    # below Forge's tolerance for the comparison to be about Forge at all.
    assert abs(fine[1] - coarse[1]) < 0.01 * _integrator_budget(fine[1])
    assert abs(fine[0] - coarse[0]) < 0.01 * _integrator_budget(fine[0])

    result = _forge(
        MILD, initial_c=MILD["caf"], initial_t=MILD["tf"], end_time=end_time
    )
    # A local-error tolerance is per step; over a march it accumulates, and a
    # factor of 10 on the declared bound is the smallest honest allowance.
    assert abs(
        result.value("T:final").magnitude_in("kelvin") - fine[1]
    ) <= 10.0 * _integrator_budget(fine[1])
    assert abs(
        result.value("C_A:final").magnitude_in("mol/m**3") - fine[0]
    ) <= 10.0 * _integrator_budget(fine[0])


def test_the_integrator_would_catch_a_wrong_trajectory():
    """The comparison above must be able to fail."""
    reactor = Reactor(**MILD)
    residence = MILD["volume"] / MILD["flow"]
    right = reactor.rk4(MILD["caf"], MILD["tf"], 2.0 * residence, 40000)
    # An exothermic reaction with the sign of the heat term flipped. At this
    # operating point the exotherm is 7.8 K, so the flip moves the answer by
    # far more than the 3e-6 K the comparison allows.
    flipped = Reactor(**{**MILD, "dh": -MILD["dh"]})
    wrong = flipped.rk4(MILD["caf"], MILD["tf"], 2.0 * residence, 40000)
    assert abs(right[1] - wrong[1]) > 1.0


# =====================================================================
# Limiting cases, each with its derivation
# =====================================================================

def test_no_reaction_leaves_the_feed_concentration_untouched():
    """k0 -> 0 removes the reaction term, so C -> Cf and the energy balance
    reduces to a (Tf - T) = gamma (T - Tc), whose root is the flow/coolant
    weighted mean  T = (a Tf + gamma Tc)/(a + gamma).
    """
    params = {**MILD, "k0": 1e-30}
    reactor = Reactor(**params)
    residence = params["volume"] / params["flow"]
    expected_t = (reactor.a * reactor.tf + reactor.gamma * reactor.tc) / (
        reactor.a + reactor.gamma
    )

    result = _forge(
        params, initial_c=params["caf"], initial_t=params["tf"],
        end_time=200.0 * residence,
    )
    assert result.value("C_A:final").magnitude_in("mol/m**3") == pytest.approx(
        params["caf"], rel=1e-9
    )
    assert result.value("T:final").magnitude_in("kelvin") == pytest.approx(
        expected_t, rel=1e-6
    )
    assert result.value(
        "conversion:final"
    ).magnitude_in("dimensionless") == pytest.approx(0.0, abs=1e-9)


def test_an_infinite_activation_energy_also_switches_the_reaction_off():
    """k = k0 exp(-E/RT) -> 0 as E grows: a second, independent route to the
    same no-reaction limit, reached by a different parameter."""
    params = {**MILD, "e_act": 1.0e7}
    reactor = Reactor(**params)
    residence = params["volume"] / params["flow"]
    expected_t = (reactor.a * reactor.tf + reactor.gamma * reactor.tc) / (
        reactor.a + reactor.gamma
    )
    result = _forge(
        params, initial_c=params["caf"], initial_t=params["tf"],
        end_time=200.0 * residence,
    )
    assert result.value("T:final").magnitude_in("kelvin") == pytest.approx(
        expected_t, rel=1e-6
    )


def test_with_no_cooling_the_rise_is_the_adiabatic_one():
    """UA = 0 removes the gamma term. At steady state the energy balance is
    a (Tf - T) + beta k C = 0 and the mass balance gives a (Cf - C) = k C, so

        T - Tf = beta (Cf - C)

    exactly -- the adiabatic temperature rise, independent of kinetics.
    """
    params = {**MILD, "ua": 0.0}
    reactor = Reactor(**params)
    residence = params["volume"] / params["flow"]
    result = _forge(
        params, initial_c=params["caf"], initial_t=params["tf"],
        end_time=400.0 * residence,
    )
    temperature = result.value("T:final").magnitude_in("kelvin")
    concentration = result.value("C_A:final").magnitude_in("mol/m**3")
    assert temperature - params["tf"] == pytest.approx(
        reactor.beta * (params["caf"] - concentration), rel=1e-5
    )


def test_a_zero_heat_of_reaction_decouples_temperature_from_conversion():
    """beta = 0 leaves the energy balance with no reaction term at all, so the
    steady temperature is the same weighted mean as the no-reaction case even
    though the reaction still consumes reagent."""
    params = {**MILD, "dh": 0.0}
    reactor = Reactor(**params)
    residence = params["volume"] / params["flow"]
    expected_t = (reactor.a * reactor.tf + reactor.gamma * reactor.tc) / (
        reactor.a + reactor.gamma
    )
    result = _forge(
        params, initial_c=params["caf"], initial_t=params["tf"],
        end_time=200.0 * residence,
    )
    assert result.value("T:final").magnitude_in("kelvin") == pytest.approx(
        expected_t, rel=1e-6
    )
    assert result.value(
        "conversion:final"
    ).magnitude_in("dimensionless") > 0.0


def test_arrhenius_doubles_the_rate_over_the_interval_it_should():
    """k(T2)/k(T1) = exp[(E/R)(1/T1 - 1/T2)], checked at a temperature pair
    chosen so the ratio is exactly 2 by construction. A wrong sign or a
    missing R would move it far off.
    """
    reactor = Reactor(**MILD)
    t1 = 320.0
    # Solve exp[(E/R)(1/t1 - 1/t2)] = 2 for t2.
    t2 = 1.0 / (1.0 / t1 - math.log(2.0) / reactor.e_over_r)
    assert reactor.k(t2) / reactor.k(t1) == pytest.approx(2.0, rel=1e-12)


# =====================================================================
# Dimensional verification, composed here
# =====================================================================

def test_the_grouped_coefficients_carry_the_dimensions_the_balances_need():
    """a is 1/s, gamma is 1/s, beta is m^3 K/mol -- so every term of both
    balances lands in mol/m^3/s and K/s respectively.
    """
    reactor = Reactor(**MILD)
    # a = q/V : (m^3/s)/(m^3) = 1/s
    assert reactor.a == pytest.approx(MILD["flow"] / MILD["volume"], rel=1e-15)
    # gamma = UA/(rho cp V) : (W/K)/((kg/m^3)(J/kg/K)(m^3)) = (J/s/K)/(J/K) = 1/s
    assert reactor.gamma == pytest.approx(
        MILD["ua"] / (MILD["rho"] * MILD["cp"] * MILD["volume"]), rel=1e-15
    )
    # beta = -dH/(rho cp) : (J/mol)/((kg/m^3)(J/kg/K)) = m^3 K/mol
    assert reactor.beta == pytest.approx(
        -MILD["dh"] / (MILD["rho"] * MILD["cp"]), rel=1e-15
    )
    # E/R has dimensions of temperature, so the exponent is dimensionless.
    assert reactor.e_over_r == pytest.approx(MILD["e_act"] / R_GAS, rel=1e-15)


def test_the_declared_range_holds_exactly_one_steady_state():
    """The bisection oracle is only valid where there is one root to find.

    The CSTR is the textbook multiple-steady-state system, so this is asserted
    rather than assumed: the energy residual is scanned across the model's own
    declared 250-1000 K range and required to change sign exactly once.
    """
    reactor = Reactor(**MILD)
    samples = [250.0 + 2.0 * i for i in range(376)]      # 250 K .. 1000 K
    residuals = [reactor.energy_residual(t) for t in samples]
    crossings = sum(
        1 for a, b in zip(residuals, residuals[1:]) if a * b < 0.0
    )
    assert crossings == 1, (
        f"{crossings} steady states in the declared range; a bracketed "
        f"bisection cannot be the oracle for this parameter set"
    )


def test_the_operating_point_actually_reacts():
    """A near-zero conversion would let the balances agree for the wrong
    reason -- the kinetics would barely enter either side."""
    residence = MILD["volume"] / MILD["flow"]
    result = _forge(
        MILD, initial_c=MILD["caf"], initial_t=MILD["tf"],
        end_time=200.0 * residence,
    )
    conversion = result.value("conversion:final").magnitude_in("dimensionless")
    assert conversion > 0.5, conversion
