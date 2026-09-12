"""Independent truth for the lumped first-order thermal body.

Two routes over the same declaration:

* **analytic** -- the closed form of ``C dT/dt = Q - hA (T - T_amb)``, which is
  ``T(t) = T_ss + (T_0 - T_ss) exp(-t/tau)`` with ``tau = C/hA`` and
  ``T_ss = T_amb + Q/hA``; and the dimensionless groups of Incropera, DeWitt,
  Bergman & Lavine, *Fundamentals of Heat and Mass Transfer*, 6th ed. (2007) --
  Bi (Sec. 5.1), Fo (Sec. 5.2), the linearized radiation coefficient
  (Sec. 1.2.3, Eq. 1.9), Churchill-Chu (Sec. 9.6.1) and the laminar flat plate
  (Sec. 7.2, Eq. 7.30).
* **numerical** -- the same balance integrated with this challenge's own RK4,
  refined until the answer stops moving, with the steady state found by
  bisection on the residual rather than by the formula. It never evaluates the
  closed form.

The two agree on every temperature-trajectory quantity and disagree nowhere;
where a quantity has only one credible route (a dimensionless group is a
definition, not an integration) the case records that and is not counted as
dual-oracle.
"""

from __future__ import annotations

import math

from .numeric import (
    STANDARD_GRAVITY,
    STEFAN_BOLTZMANN,
    bisect,
    relative_gap,
    rk4_converged,
)

#: The two correlation ranges, each as its source prints it.
CHURCHILL_CHU_RA_MAX = 1e9  # Churchill & Chu (1975), laminar vertical plate
FLAT_PLATE_RE_MAX = 5e5  # Incropera 6th ed. Sec. 7.1, transition Re
FLAT_PLATE_PR_MIN = 0.6  # Incropera 6th ed. Sec. 7.2, printed with Eq. 7.30


def _steady_state_analytic(t_amb: float, q: float, ha: float) -> float:
    return t_amb + q / ha


def _steady_state_numeric(t_amb: float, q: float, ha: float) -> float | None:
    """T_ss as the root of the balance's right-hand side, found by bisection."""
    def residual(t: float) -> float:
        return q - ha * (t - t_amb)

    guess = abs(q / ha) if ha else 1.0
    lo, hi = t_amb - 10.0 * guess - 1.0, t_amb + 10.0 * guess + 1.0
    return bisect(residual, lo, hi)


def _final_temperature_numeric(
    t0: float, t_amb: float, q: float, ha: float, capacity: float, duration: float
) -> tuple[float, float]:
    def rhs(_t: float, y):
        return [(q - ha * (y[0] - t_amb)) / capacity]

    state, movement = rk4_converged(rhs, [t0], 0.0, duration)
    return state[0], movement


def evaluate(decl: dict, *, with_routes: bool = True) -> dict:
    """Every quantity the lumped model's declared conditions are stated over.

    ``decl`` carries SI magnitudes only; the caller has already converted, and
    the conversion is this challenge's own. A key that is absent is *not
    declared*, which is a different thing from zero and produces ``None``.
    """
    capacity = decl.get("heat_capacity")
    ha = decl.get("ambient_conductance")
    duration = decl.get("duration")
    t0 = decl.get("initial_temperature")
    t_amb = decl.get("ambient_temperature")
    q = decl.get("heat_input")

    out: dict[str, float | None] = {
        "heat_capacity": capacity,
        "ambient_conductance": ha,
    }
    routes: dict[str, dict] = {}

    # ---- trajectory, by two routes ---------------------------------------
    t_ss = t_ss_num = None
    t_final = None
    movement = None
    if None not in (t_amb, q, ha) and ha > 0.0:
        t_ss = _steady_state_analytic(t_amb, q, ha)
        t_ss_num = _steady_state_numeric(t_amb, q, ha) if with_routes else None
    if with_routes and None not in (t0, t_amb, q, ha, capacity, duration) and ha > 0.0 and capacity > 0.0:
        t_final, movement = _final_temperature_numeric(
            t0, t_amb, q, ha, capacity, duration
        )
    if t_ss is not None and with_routes:
        routes["steady_state_temperature"] = {
            "analytic": t_ss,
            "numerical": t_ss_num,
            "gap": relative_gap(t_ss, t_ss_num),
        }
    if t_final is not None and t_ss is not None and capacity and ha:
        tau = capacity / ha
        closed = t_ss + (t0 - t_ss) * math.exp(-duration / tau) if tau > 0 else None
        routes["final_temperature"] = {
            "analytic": closed,
            "numerical": t_final,
            "gap": relative_gap(closed, t_final),
            "refinement_movement": movement,
        }

    peak = None if (t0 is None or t_ss is None) else max(t0, t_ss)
    excursion = (
        None
        if (t0 is None or t_amb is None or t_ss is None)
        else max(abs(t0 - t_amb), abs(t_ss - t_amb))
    )

    # ---- geometry --------------------------------------------------------
    length_declared = decl.get("characteristic_length")
    volume = decl.get("body_volume")
    area = decl.get("surface_area")
    implied = None
    if volume is not None and area is not None and area > 0.0:
        implied = volume / area
    length = length_declared if length_declared is not None else implied
    if length_declared is not None and implied not in (None, 0.0):
        out["geometry_route_ratio"] = length_declared / implied
    else:
        out["geometry_route_ratio"] = None

    coefficient = None
    if ha is not None and area not in (None, 0.0):
        coefficient = ha / area

    # ---- Biot and Fourier ------------------------------------------------
    conductivity = decl.get("body_conductivity")
    biot = None
    if None not in (coefficient, length, conductivity) and conductivity > 0.0:
        biot = coefficient * length / conductivity
    out["biot_number"] = biot

    fourier = None
    if biot not in (None, 0.0) and None not in (capacity, ha, duration) and capacity > 0:
        horizon_ratio = duration / (capacity / ha)
        fourier = horizon_ratio / biot
    out["internal_fourier_number"] = fourier

    # ---- declared property budgets --------------------------------------
    bound_h = decl.get("conductance_excursion_bound")
    out["conductance_excursion_ratio"] = (
        None if (excursion is None or bound_h in (None, 0.0)) else excursion / bound_h
    )
    bound_c = decl.get("capacity_excursion_bound")
    out["capacity_excursion_ratio"] = (
        None
        if (t_ss is None or t0 is None or bound_c in (None, 0.0))
        else abs(t_ss - t0) / bound_c
    )

    # ---- radiation -------------------------------------------------------
    emissivity = decl.get("surface_emissivity")
    radiation = None
    if None not in (emissivity, peak, t_amb, coefficient) and coefficient > 0.0:
        h_r = (
            emissivity
            * STEFAN_BOLTZMANN
            * (peak + t_amb)
            * (peak * peak + t_amb * t_amb)
        )
        radiation = h_r / coefficient
    out["radiation_to_convection_ratio"] = radiation

    # ---- melting ---------------------------------------------------------
    melt = decl.get("melting_temperature")
    out["melting_temperature_utilization"] = (
        None if (peak is None or melt in (None, 0.0)) else peak / melt
    )

    # ---- convection route ------------------------------------------------
    beta = decl.get("fluid_expansion_coefficient")
    velocity = decl.get("fluid_velocity")
    nu = decl.get("fluid_kinematic_viscosity")
    prandtl = decl.get("fluid_prandtl_number")
    k_fluid = decl.get("fluid_conductivity")
    conv_length = decl.get("convection_length")

    natural = beta is not None
    forced = velocity is not None
    route = "ambiguous" if (natural and forced) else ("natural" if natural else ("forced" if forced else None))

    rayleigh = reynolds = nusselt = None
    if route == "natural" and None not in (beta, excursion, conv_length, nu, prandtl) and nu:
        rayleigh = (
            STANDARD_GRAVITY
            * beta
            * excursion
            * conv_length**3
            * prandtl
            / (nu * nu)
        )
        if prandtl > 0.0:
            nusselt = 0.68 + 0.670 * rayleigh**0.25 / (
                1.0 + (0.492 / prandtl) ** (9.0 / 16.0)
            ) ** (4.0 / 9.0)
    elif route == "forced" and None not in (velocity, conv_length, nu, prandtl) and nu:
        reynolds = velocity * conv_length / nu
        nusselt = 0.664 * reynolds**0.5 * prandtl ** (1.0 / 3.0)

    if route == "natural" and rayleigh is not None:
        out["convection_flow_range_utilization"] = rayleigh / CHURCHILL_CHU_RA_MAX
        out["convection_property_range_utilization"] = 0.0
    elif route == "forced" and reynolds is not None:
        out["convection_flow_range_utilization"] = reynolds / FLAT_PLATE_RE_MAX
        out["convection_property_range_utilization"] = (
            None if not prandtl else FLAT_PLATE_PR_MIN / prandtl
        )
    else:
        out["convection_flow_range_utilization"] = None
        out["convection_property_range_utilization"] = None

    agreement = None
    if (
        nusselt is not None
        and None not in (k_fluid, conv_length, coefficient)
        and conv_length > 0.0
    ):
        h_correlated = nusselt * k_fluid / conv_length
        if h_correlated:
            agreement = coefficient / h_correlated
    out["convection_conductance_agreement_ratio"] = agreement

    return {
        "quantities": out,
        "routes": routes,
        "route_selection": route,
        "intermediate": {
            "steady_state_temperature": t_ss,
            "peak_temperature": peak,
            "surface_excursion": excursion,
            "surface_coefficient": coefficient,
            "characteristic_length": length,
            "rayleigh": rayleigh,
            "reynolds": reynolds,
            "nusselt": nusselt,
        },
    }
