"""Oracles for the non-isothermal CSTR.

THE PHYSICS, derived here.

A perfectly mixed constant-volume liquid CSTR of volume V fed at volumetric
rate q with concentration C_Af and temperature T_f, carrying one irreversible
first-order exothermic reaction A -> B of rate r = k(T) C_A, cooled by a
jacket at T_c through UA:

  species:  V dC_A/dt = q (C_Af - C_A) - V r
            => dC_A/dt = a (C_Af - C_A) - k C_A        with a = q/V

  energy:   V rho cp dT/dt = q rho cp (T_f - T) + (-dH) V r - UA (T - T_c)
            => dT/dt = a (T_f - T) + beta k C_A - gamma (T - T_c)
            with beta = (-dH)/(rho cp)   [m^3 K / mol]
                 gamma = UA/(V rho cp)   [1/s]

Arrhenius: k(T) = k0 exp(-E/(R T)).

THREE oracles, deliberately of different kinds:

1. ``rk4_trajectory`` -- a fixed-step classical RK4 written out here. The
   production solver is an implicit stiff method with an analytic Jacobian;
   RK4 is explicit and Jacobian-free, so the two share the right-hand side
   (the thing under test) and nothing else. Driven at a step small enough
   that its own error is far below the tolerance being checked.

2. ``steady_states`` -- the steady solution found by ROOT FINDING on a single
   scalar equation, with no time integration at all. At steady state the
   species balance gives C_A = a C_Af / (a + k(T)) exactly, and substituting
   into the energy balance leaves one equation in T:

       F(T) = a (T_f - T) + beta k(T) a C_Af / (a + k(T)) - gamma (T - T_c) = 0

   Solved by bisection on sign changes over a scan. This is an algebraic
   oracle for a differential problem: a long integration must land on a root
   of F, and which root it lands on is the multiplicity question the model
   exists to exhibit.

3. ``invariant_residual`` -- the exact invariant Z = T + beta C_A, whose
   balance dZ/dt = a (Z_f - Z) - gamma (T - T_c) contains NO reaction term:
   adding beta times the species balance to the energy balance cancels
   +beta k C_A against -beta k C_A identically. A trajectory that violates it
   has broken energy/species coupling regardless of what the rate law does.

GAS CONSTANT. R = 8.31446261815324 J/(mol K), the CODATA-2018 exact value
following the 2019 SI redefinition. Written here independently; if production
carries a different value that is itself a finding.
"""

from __future__ import annotations

import math

R_GAS = 8.31446261815324


def rate_constant(*, k0_per_s: float, e_j_per_mol: float, temperature_k: float) -> float:
    if temperature_k <= 0.0:
        return float("nan")
    return k0_per_s * math.exp(-e_j_per_mol / (R_GAS * temperature_k))


def _slopes(
    *, c_a: float, temperature: float, a: float, caf: float, tf: float,
    tc: float, beta: float, gamma: float, k0: float, energy: float,
) -> tuple[float, float]:
    k = rate_constant(k0_per_s=k0, e_j_per_mol=energy, temperature_k=temperature)
    reaction = k * c_a
    return (
        a * (caf - c_a) - reaction,
        a * (tf - temperature) + beta * reaction - gamma * (temperature - tc),
    )


def rk4_trajectory(
    *, a: float, caf: float, tf: float, tc: float, beta: float, gamma: float,
    k0: float, energy: float, c0: float, t0: float, end_time_s: float,
    steps: int = 400_000,
) -> dict:
    """Fixed-step RK4 on the two coupled balances. Explicit, Jacobian-free."""
    h = end_time_s / steps
    c_a, temperature = c0, t0
    worst_z = 0.0
    z_initial = temperature + beta * c_a
    peak_t = temperature
    for _ in range(steps):
        k1c, k1t = _slopes(c_a=c_a, temperature=temperature, a=a, caf=caf, tf=tf,
                           tc=tc, beta=beta, gamma=gamma, k0=k0, energy=energy)
        k2c, k2t = _slopes(c_a=c_a + 0.5 * h * k1c, temperature=temperature + 0.5 * h * k1t,
                           a=a, caf=caf, tf=tf, tc=tc, beta=beta, gamma=gamma, k0=k0, energy=energy)
        k3c, k3t = _slopes(c_a=c_a + 0.5 * h * k2c, temperature=temperature + 0.5 * h * k2t,
                           a=a, caf=caf, tf=tf, tc=tc, beta=beta, gamma=gamma, k0=k0, energy=energy)
        k4c, k4t = _slopes(c_a=c_a + h * k3c, temperature=temperature + h * k3t,
                           a=a, caf=caf, tf=tf, tc=tc, beta=beta, gamma=gamma, k0=k0, energy=energy)
        c_a += h * (k1c + 2 * k2c + 2 * k3c + k4c) / 6.0
        temperature += h * (k1t + 2 * k2t + 2 * k3t + k4t) / 6.0
        if not (math.isfinite(c_a) and math.isfinite(temperature)):
            return {"diverged": True, "c_a": c_a, "temperature": temperature}
        peak_t = max(peak_t, temperature)
        worst_z = max(worst_z, abs((temperature + beta * c_a) - z_initial))
    return {
        "diverged": False,
        "c_a": c_a,
        "temperature": temperature,
        "conversion": (caf - c_a) / caf if caf else float("nan"),
        "peak_temperature": peak_t,
        "z_drift_from_initial": worst_z,
        "steps": steps,
    }


def steady_states(
    *, a: float, caf: float, tf: float, tc: float, beta: float, gamma: float,
    k0: float, energy: float, t_low: float = 200.0, t_high: float = 1200.0,
    scan: int = 40_000,
) -> list[dict]:
    """Every steady state, by bisection on F(T) = 0. No time integration."""

    def residual(temperature: float) -> float:
        k = rate_constant(k0_per_s=k0, e_j_per_mol=energy, temperature_k=temperature)
        c_a = a * caf / (a + k)
        return a * (tf - temperature) + beta * k * c_a - gamma * (temperature - tc)

    roots: list[dict] = []
    previous_t = t_low
    previous_f = residual(previous_t)
    for i in range(1, scan + 1):
        current_t = t_low + (t_high - t_low) * i / scan
        current_f = residual(current_t)
        if previous_f == 0.0:
            roots.append(previous_t)
        elif previous_f * current_f < 0.0:
            lo, hi = previous_t, current_t
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                if residual(lo) * residual(mid) <= 0.0:
                    hi = mid
                else:
                    lo = mid
            roots.append(0.5 * (lo + hi))
        previous_t, previous_f = current_t, current_f

    out = []
    for temperature in roots:
        k = rate_constant(k0_per_s=k0, e_j_per_mol=energy, temperature_k=temperature)
        c_a = a * caf / (a + k)
        out.append(
            {
                "temperature": temperature,
                "c_a": c_a,
                "conversion": (caf - c_a) / caf if caf else float("nan"),
                "residual": residual(temperature),
            }
        )
    return out


def invariant_ceiling(
    *, beta: float, caf: float, c0: float, tf: float, tc: float, t0: float
) -> float:
    """T <= max(T_0, T_f, T_c) + beta max(C_A0, C_Af), with or without cooling.

    From dZ/dt = a (Z_f - Z) - gamma (T - T_c) for Z = T + beta C_A: Z is driven
    towards Z_f and pulled down whenever T > T_c, so Z never exceeds
    max(Z_0, Z_f, T_c + beta * max concentration), and T <= Z because C_A >= 0.
    """
    return max(t0, tf, tc) + beta * max(c0, caf)
