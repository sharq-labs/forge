"""Independent truth for the non-isothermal first-order CSTR.

The balances, written out rather than imported::

    dC_A/dt = (C_Af - C_A)/tau - k(T) C_A
    dT/dt   = (T_f - T)/tau + beta k(T) C_A - gamma (T - T_c)
    k(T)    = k0 exp(-E / (R T)),  beta = -dH/(rho c_p),  gamma = UA/(rho V c_p)

Fogler, *Elements of Chemical Reaction Engineering*, 4th ed., Ch. 8-9, for the
non-isothermal CSTR; the Arrhenius form is standard.

**The ceiling.** ``Z = T + beta C_A`` satisfies ``dZ/dt = (Z_f - Z)/tau -
gamma (T - T_c)``, so with ``C_A >= 0`` the temperature is bounded above by
``max(T_0, T_f, T_c) + beta max(C_A0, C_Af)`` with or without cooling. That is
an inequality this challenge derives and then *checks numerically*: route two
integrates the balances with its own RK4 and asserts the trajectory never
crosses the analytic ceiling. A ceiling that the integration violated would be
an oracle defect, and the check is what makes that detectable.
"""

from __future__ import annotations

import math

from .numeric import GAS_CONSTANT, relative_gap, rk4_converged


def _rate_constant(k0: float, activation_energy: float, temperature: float) -> float:
    """Arrhenius, with the overflow the exponential can genuinely reach.

    A sampler exploring far outside the fitted region can ask for an exponent
    no float can hold. That is a fact about the declaration, not a fault in the
    oracle, so it returns an infinity the caller can see rather than raising
    through a generator that would then have to guess what happened.
    """
    try:
        return k0 * math.exp(-activation_energy / (GAS_CONSTANT * temperature))
    except OverflowError:
        return math.inf


def _ceiling(decl: dict) -> float | None:
    needed = (
        "heat_of_reaction",
        "density",
        "heat_capacity",
        "feed_concentration",
        "initial_concentration",
        "feed_temperature",
        "initial_temperature",
        "coolant_temperature",
    )
    if any(decl.get(name) is None for name in needed):
        return None
    rho = decl["density"]
    cp = decl["heat_capacity"]
    if rho == 0.0 or cp == 0.0:
        return None
    beta = -decl["heat_of_reaction"] / (rho * cp)
    hottest = max(
        decl["initial_temperature"], decl["feed_temperature"], decl["coolant_temperature"]
    )
    return hottest + beta * max(decl["initial_concentration"], decl["feed_concentration"])


def _trajectory(decl: dict) -> dict:
    """Route two: integrate. Returns the peak temperature actually reached."""
    needed = (
        "k0",
        "activation_energy",
        "heat_of_reaction",
        "density",
        "heat_capacity",
        "feed_concentration",
        "feed_temperature",
        "coolant_temperature",
        "ua",
        "residence_time",
        "end_time",
        "initial_concentration",
        "initial_temperature",
        "volume",
    )
    if any(decl.get(name) is None for name in needed):
        return {}
    rho, cp, volume = decl["density"], decl["heat_capacity"], decl["volume"]
    if rho <= 0.0 or cp <= 0.0 or volume <= 0.0 or decl["residence_time"] <= 0.0:
        return {}
    beta = -decl["heat_of_reaction"] / (rho * cp)
    gamma = decl["ua"] / (rho * volume * cp)
    tau = decl["residence_time"]
    k0, ea = decl["k0"], decl["activation_energy"]
    c_feed, t_feed, t_cool = (
        decl["feed_concentration"],
        decl["feed_temperature"],
        decl["coolant_temperature"],
    )

    peak = {"value": decl["initial_temperature"]}

    def rhs(_t, y):
        c, temp = y
        temp_safe = max(temp, 1.0)
        k = _rate_constant(k0, ea, temp_safe)
        if temp > peak["value"]:
            peak["value"] = temp
        return [
            (c_feed - c) / tau - k * c,
            (t_feed - temp) / tau + beta * k * c - gamma * (temp - t_cool),
        ]

    state, movement = rk4_converged(
        rhs,
        [decl["initial_concentration"], decl["initial_temperature"]],
        0.0,
        decl["end_time"],
        steps=2000,
        refinements=3,
        rtol=1e-8,
    )
    # An uncooled exotherm is stiff, and a fixed-step explicit scheme run into
    # one does not produce a large answer -- it produces a meaningless one. The
    # refinement already knows: when halving the step keeps moving the answer,
    # or the state leaves the reals, the route has not converged and must say
    # so. Reporting a peak from a divergent integration would have made a
    # second route look like evidence when it is noise, which is worse than
    # having one route.
    converged = (
        math.isfinite(state[0])
        and math.isfinite(state[1])
        and math.isfinite(movement)
        and movement < 1e-3
        and math.isfinite(peak["value"])
    )
    return {
        "final_concentration": state[0],
        "final_temperature": state[1],
        "peak_temperature": peak["value"],
        "refinement_movement": movement,
        "converged": converged,
    }


def evaluate(decl: dict, *, with_routes: bool = True) -> dict:
    """Every quantity the CSTR model's declared conditions are stated over.

    ``temperature`` and ``concentration`` are the model's own reserved derived
    names. This challenge never guesses which declared temperature they
    resolve to: every generated case keeps *all three* declared temperatures on
    the same side of the declared band, and both concentrations on the same
    side of zero, so the verdict is the same under any aggregation the domain
    might use. Where a case cannot be built that way it is not generated.
    """
    temperatures = [
        decl.get("initial_temperature"),
        decl.get("feed_temperature"),
        decl.get("coolant_temperature"),
    ]
    concentrations = [decl.get("initial_concentration"), decl.get("feed_concentration")]
    present_t = [t for t in temperatures if t is not None]
    present_c = [c for c in concentrations if c is not None]

    ceiling = _ceiling(decl)
    trajectory = _trajectory(decl) if with_routes else {}

    routes: dict[str, dict] = {}
    if ceiling is not None and trajectory and trajectory.get("converged"):
        peak = trajectory["peak_temperature"]
        routes["adiabatic_ceiling_temperature"] = {
            "analytic": ceiling,
            "numerical_peak_reached": peak,
            "ceiling_respected": bool(peak <= ceiling + 1e-6 * max(1.0, abs(ceiling))),
            "slack": ceiling - peak,
            "refinement_movement": trajectory["refinement_movement"],
        }
        routes["final_state"] = {
            "numerical_final_temperature": trajectory["final_temperature"],
            "numerical_final_concentration": trajectory["final_concentration"],
        }

    return {
        "numerical_route_converged": bool(trajectory.get("converged")) if trajectory else None,
        "quantities": {
            "temperature_min": min(present_t) if present_t else None,
            "temperature_max": max(present_t) if present_t else None,
            "concentration_min": min(present_c) if present_c else None,
            "k0": decl.get("k0"),
            "k_const": decl.get("k_const"),
            "activation_energy": decl.get("activation_energy"),
            "residence_time": decl.get("residence_time"),
            "adiabatic_ceiling_temperature": ceiling,
        },
        "routes": routes,
        "intermediate": trajectory,
    }


def ceiling_gap(decl: dict) -> float | None:
    """Convergence evidence for the ceiling, used by the oracle self-tests."""
    result = evaluate(decl)
    route = result["routes"].get("adiabatic_ceiling_temperature")
    if not route:
        return None
    return relative_gap(route["analytic"], route["numerical_peak_reached"])
