"""Independent truth for the linear-TCR conductor resistance.

``R(T) = R_ref (1 + alpha (T - T_ref))``.

* **analytic** -- the closed form above, evaluated in exact rational
  arithmetic where the inputs are exactly representable, so the boundary
  ``1 + alpha (T - T_ref) > 0`` is decided without a float rounding it across.
* **numerical** -- ``R(T) = R_ref + integral of alpha R_ref dT`` from ``T_ref``
  to ``T``, integrated with this challenge's own RK4 on ``dR/dT = alpha
  R_ref``. A different statement of the same physics: the closed form is the
  solution, this is the differential equation it solves.

The Debye floors are the physics: above roughly ``theta_D / 3`` a metal's
resistivity is linear in ``T``; well below it Bloch-Grueneisen gives
``rho ~ T^5``. Ashcroft & Mermin, *Solid State Physics* (1976), Ch. 26,
Eq. 26.55; Kittel, *Introduction to Solid State Physics*, 8th ed., Ch. 6.
"""

from __future__ import annotations

from fractions import Fraction

from .numeric import relative_gap, rk4_converged


def _exact_linear_ratio(alpha: float, temperature: float, reference: float) -> float:
    """1 + alpha (T - T_ref), formed in exact rationals then returned as float.

    Floats are dyadic rationals, so ``Fraction(x)`` is exact and the whole
    expression is evaluated without a single rounding. Only the final cast
    rounds, and it rounds a number whose sign is already decided.
    """
    value = 1 + Fraction(alpha) * (Fraction(temperature) - Fraction(reference))
    return float(value)


def _numeric_resistance(
    reference_resistance: float, alpha: float, temperature: float, reference: float
) -> tuple[float, float]:
    def rhs(_t, _y):
        return [alpha * reference_resistance]

    state, movement = rk4_converged(
        rhs, [reference_resistance], reference, temperature, steps=64, refinements=2
    )
    return state[0], movement


def evaluate(decl: dict, *, with_routes: bool = True) -> dict:
    """Every quantity the two TCR models' declared conditions are stated over.

    ``temperature`` is evaluated at the state the run occupies. The Debye floor
    is evaluated at the *coldest* state and the linearization band at the state
    *furthest* from the reference, both as the declared conditions say; where a
    case declares a single operating temperature all three coincide.
    """
    temperature = decl.get("temperature")
    coldest = decl.get("coldest_temperature", temperature)
    furthest = decl.get("furthest_temperature", temperature)
    reference = decl.get("reference_temperature")
    alpha = decl.get("temperature_coefficient")
    r_ref = decl.get("reference_resistance")
    band = decl.get("linearization_band")
    t_max = decl.get("maximum_operating_temperature")
    theta = decl.get("debye_temperature")

    out: dict[str, float | None] = {
        "temperature": temperature,
        "reference_resistance": r_ref,
        "reference_temperature": reference,
        "maximum_operating_temperature": t_max,
        "debye_temperature": theta,
    }

    out["linearization_excursion_ratio"] = (
        None
        if (furthest is None or reference is None or band in (None, 0.0))
        else abs(furthest - reference) / band
    )
    out["operating_temperature_utilization"] = (
        None if (temperature is None or t_max in (None, 0.0)) else temperature / t_max
    )
    out["reduced_debye_temperature"] = (
        None if (coldest is None or theta in (None, 0.0)) else coldest / theta
    )
    out["reference_temperature_utilization"] = (
        None if (reference is None or t_max in (None, 0.0)) else reference / t_max
    )
    out["reference_reduced_debye_temperature"] = (
        None if (reference is None or theta in (None, 0.0)) else reference / theta
    )
    out["ceiling_reduced_debye_temperature"] = (
        None if (t_max is None or theta in (None, 0.0)) else t_max / theta
    )

    ratio = None
    routes: dict[str, dict] = {}
    if None not in (alpha, temperature, reference):
        ratio = _exact_linear_ratio(alpha, temperature, reference)
        if r_ref is not None and with_routes:
            closed = r_ref * ratio
            numeric, movement = _numeric_resistance(r_ref, alpha, temperature, reference)
            routes["resistance"] = {
                "analytic": closed,
                "numerical": numeric,
                "gap": relative_gap(closed, numeric),
                "refinement_movement": movement,
            }
    out["linear_resistance_ratio"] = ratio

    return {"quantities": out, "routes": routes, "intermediate": {}}
