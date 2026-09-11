"""Oracle for the lumped first-order thermal body.

THE PHYSICS, derived here rather than read off the implementation.

A body of heat capacity C at uniform temperature T, receiving Q_in and losing
heat to an ambient at T_amb through a conductance hA, obeys the energy balance

    C dT/dt = Q_in - hA (T - T_amb)

The production code evaluates the closed form of this. An oracle that also
evaluated the closed form would be testing arithmetic, not physics, so this
module integrates the ODE NUMERICALLY instead, with a fixed-step classical
RK4 written out in full. The two routes share the differential equation --
which is the thing under test -- and share no algebra whatsoever: one
exponentiates, the other marches.

RK4 on dy/dt = f(t, y):

    k1 = f(t, y)
    k2 = f(t + h/2, y + h k1/2)
    k3 = f(t + h/2, y + h k2/2)
    k4 = f(t + h, y + h k3)
    y <- y + h (k1 + 2 k2 + 2 k3 + k4) / 6

Local truncation error O(h^5), global O(h^4). For a linear scalar ODE with a
well-resolved time constant this reaches machine precision quickly, which is
what makes it usable as an oracle for a closed form.
"""

from __future__ import annotations

import math


def rk4_final_temperature(
    *,
    capacity_j_per_k: float,
    conductance_w_per_k: float,
    ambient_k: float,
    initial_k: float,
    heat_input_w: float,
    duration_s: float,
    steps: int = 200_000,
) -> float:
    """March C dT/dt = Q - hA (T - T_amb) from t=0 to t=duration with RK4."""
    if capacity_j_per_k <= 0.0 or conductance_w_per_k <= 0.0:
        raise ValueError("capacity and conductance must be strictly positive")
    if duration_s < 0.0:
        raise ValueError("duration must be non-negative")
    if steps < 1:
        raise ValueError("steps must be at least 1")

    def slope(temperature: float) -> float:
        return (
            heat_input_w - conductance_w_per_k * (temperature - ambient_k)
        ) / capacity_j_per_k

    h = duration_s / steps
    temperature = initial_k
    for _ in range(steps):
        k1 = slope(temperature)
        k2 = slope(temperature + 0.5 * h * k1)
        k3 = slope(temperature + 0.5 * h * k2)
        k4 = slope(temperature + h * k3)
        temperature += h * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0
    return temperature


def energy_residual(
    *,
    capacity_j_per_k: float,
    conductance_w_per_k: float,
    ambient_k: float,
    initial_k: float,
    final_k: float,
    heat_input_w: float,
    duration_s: float,
    steps: int = 200_000,
) -> dict:
    """Is the first law satisfied over the interval?

    Integrating the balance over [0, t] gives

        C (T(t) - T(0)) = Q_in t - hA INTEGRAL_0^t (T - T_amb) dt'

    The left side is the change in stored internal energy; the right is heat
    in minus heat out. The integral is evaluated here by composite Simpson on
    the ANALYTIC trajectory of the same ODE -- which is legitimate because
    this function is testing the balance, not the trajectory, and the
    trajectory it uses is the one the balance itself implies.

    For the exponential trajectory T(t') = T_ss + (T0 - T_ss) e^{-t'/tau},

        INTEGRAL_0^t (T - T_amb) dt'
            = (T_ss - T_amb) t + (T0 - T_ss) tau (1 - e^{-t/tau})

    so the residual is computed in closed form and no quadrature error enters.
    """
    tau = capacity_j_per_k / conductance_w_per_k
    steady = ambient_k + heat_input_w / conductance_w_per_k
    if duration_s == 0.0:
        integral = 0.0
    else:
        integral = (steady - ambient_k) * duration_s + (initial_k - steady) * tau * (
            1.0 - math.exp(-duration_s / tau)
        )
    stored = capacity_j_per_k * (final_k - initial_k)
    supplied = heat_input_w * duration_s
    lost = conductance_w_per_k * integral
    residual = stored - (supplied - lost)
    scale = max(abs(stored), abs(supplied), abs(lost), 1e-30)
    return {
        "stored_j": stored,
        "supplied_j": supplied,
        "lost_j": lost,
        "residual_j": residual,
        "relative_residual": abs(residual) / scale,
    }
