"""Oracles for the Rint / coulomb-counting cell.

THE PHYSICS, derived here.

Coulomb counting. Charge is conserved, so the charge remaining after drawing a
constant current I for a time t from a cell of nominal capacity Q_nom at
coulombic efficiency eta is

    z(t) = z_0 - I t / (eta Q_nom)

with z the state of charge as a fraction of the usable charge eta Q_nom. Note
the placement of eta: this repository charges the caller the full stored charge
for the charge delivered, so a cell with eta < 1 depletes faster than an ideal
one. That convention is checked explicitly below rather than assumed, by
asking whether the runtime to a cutoff and the state of charge at that cutoff
are consistent with ONE definition of eta.

Rint terminal voltage. One ideal source at OCV(z) in series with one constant
resistance R:

    V = OCV(z) - I R,     OCV(z) = V_empty + (V_full - V_empty) z

Joule heating in the series resistance:  Q_gen = I^2 R  (>= 0 always).

Runtime to a cutoff. The state of charge falls linearly, so the time to walk
from z_0 to z_stop is the charge between them over the current:

    t = (z_0 - z_stop) eta Q_nom / I

Voltage cutoff inversion. Setting V = V_cut and solving OCV(z) = V_cut + I R:

    z_cut = (V_cut + I R - V_empty) / (V_full - V_empty)

INDEPENDENCE. Every expression above is written from charge conservation and
Kirchhoff's voltage law in this module. The unit conversion (ampere-hours to
hours) is done here with an explicit 3600, which the production code
deliberately does NOT do -- it converts through its unit system. A mismatch in
either direction is therefore visible.
"""

from __future__ import annotations

import math

SECONDS_PER_HOUR = 3600.0


def state_of_charge(
    *, z0: float, current_a: float, duration_s: float, efficiency: float,
    capacity_ah: float,
) -> float:
    amp_hours_drawn = current_a * (duration_s / SECONDS_PER_HOUR)
    return z0 - amp_hours_drawn / (efficiency * capacity_ah)


def open_circuit_voltage(*, z: float, v_empty: float, v_full: float) -> float:
    return v_empty + (v_full - v_empty) * z


def terminal_voltage(
    *, z: float, current_a: float, resistance_ohm: float, v_empty: float,
    v_full: float,
) -> float:
    return open_circuit_voltage(z=z, v_empty=v_empty, v_full=v_full) - current_a * resistance_ohm


def joule_heat_w(*, current_a: float, resistance_ohm: float) -> float:
    return current_a * current_a * resistance_ohm


def voltage_cutoff_soc(
    *, v_cut: float, current_a: float, resistance_ohm: float, v_empty: float,
    v_full: float,
) -> float:
    return (v_cut + current_a * resistance_ohm - v_empty) / (v_full - v_empty)


def runtime_to_cutoff_s(
    *, z0: float, z_stop: float, efficiency: float, capacity_ah: float,
    current_a: float,
) -> float:
    return (z0 - z_stop) * efficiency * capacity_ah / current_a * SECONDS_PER_HOUR


def charge_balance_residual(
    *, z0: float, z_end: float, current_a: float, duration_s: float,
    efficiency: float, capacity_ah: float,
) -> dict:
    """Coulombs accounted for against coulombs drawn. Must balance exactly.

        (z_0 - z_end) * eta * Q_nom * 3600  ==  I * t     [coulombs]

    This is charge conservation with no appeal to the trajectory: it asks only
    that the state of charge the model reports and the current it was given
    describe the same number of electrons.
    """
    accounted_c = (z0 - z_end) * efficiency * capacity_ah * SECONDS_PER_HOUR
    drawn_c = current_a * duration_s
    residual = accounted_c - drawn_c
    scale = max(abs(accounted_c), abs(drawn_c), 1e-30)

    # THE FLOOR IS NOT A FUDGE. (z0 - z_end) is a difference of two nearly
    # equal doubles whenever little charge moved, and that subtraction loses
    # absolute precision of about ulp(z0) however exact both numbers are. In
    # coulombs that is ulp(z0) * eta * Q_nom * 3600. A residual at or below it
    # is the subtraction's rounding and cannot be a conservation error; a
    # purely relative criterion here reports catastrophic cancellation as a
    # physics failure, which it did in a first pass of this audit.
    ulp_of_z = math.ulp(max(abs(z0), abs(z_end), 1.0))
    floor_c = 4.0 * ulp_of_z * efficiency * capacity_ah * SECONDS_PER_HOUR
    return {
        "accounted_coulombs": accounted_c,
        "drawn_coulombs": drawn_c,
        "residual_coulombs": residual,
        "relative_residual": abs(residual) / scale,
        "cancellation_floor_coulombs": floor_c,
        "within_cancellation_floor": abs(residual) <= floor_c,
    }


def peukert_effective_capacity_ah(
    *, capacity_ah: float, current_a: float, reference_current_a: float,
    exponent: float,
) -> float:
    """Q_eff = Q_nom (I_ref / I)^(k-1).

    Peukert's law is I^k t = constant. At the reference current the cell
    delivers Q_nom = I_ref t_ref, so the constant is I_ref^k t_ref =
    I_ref^(k-1) Q_nom. At another current, Q = I t = constant / I^(k-1), so
    Q = Q_nom (I_ref / I)^(k-1). Derived here, not copied.
    """
    return capacity_ah * (reference_current_a / current_a) ** (exponent - 1.0)
