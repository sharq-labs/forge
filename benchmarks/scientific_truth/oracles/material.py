"""Oracle for the linear-TCR conductor, at 50 significant digits.

    R(T) = R_ref (1 + alpha (T - T_ref))

Trivial algebra, which is exactly why it is worth checking in a different
arithmetic. The expression has one cancellation hazard: when alpha (T - T_ref)
approaches -1 the bracket is a difference of nearly equal numbers and a double
loses significance in it. mpmath at 50 digits settles whether the double-
precision answer is the correctly rounded one or has lost digits to that
cancellation.

An alternative algebraic arrangement is also evaluated:

    R(T) = R_ref + R_ref alpha (T - T_ref)      (distributed)
    R(T) = R_ref (1 - alpha T_ref) + R_ref alpha T   (expanded in T)

All three are the same function mathematically and differ in floating point.
The expanded form is the one a careless optimiser would reach for, and it is
catastrophically worse when alpha T_ref is large -- which is the point of
checking.
"""

from __future__ import annotations

from mpmath import mp, mpf

mp.dps = 50


def resistance_high_precision(
    *, r_ref_ohm: float, alpha_per_k: float, t_ref_k: float, temperature_k: float
) -> float:
    r_ref = mpf(repr(r_ref_ohm))
    alpha = mpf(repr(alpha_per_k))
    t_ref = mpf(repr(t_ref_k))
    temperature = mpf(repr(temperature_k))
    return float(r_ref * (mpf(1) + alpha * (temperature - t_ref)))


def resistance_arrangements(
    *, r_ref_ohm: float, alpha_per_k: float, t_ref_k: float, temperature_k: float
) -> dict:
    """The same function three ways in double precision, plus the truth."""
    factored = r_ref_ohm * (1.0 + alpha_per_k * (temperature_k - t_ref_k))
    distributed = r_ref_ohm + r_ref_ohm * alpha_per_k * (temperature_k - t_ref_k)
    expanded = r_ref_ohm * (1.0 - alpha_per_k * t_ref_k) + r_ref_ohm * alpha_per_k * temperature_k
    exact = resistance_high_precision(
        r_ref_ohm=r_ref_ohm, alpha_per_k=alpha_per_k, t_ref_k=t_ref_k,
        temperature_k=temperature_k,
    )
    def rel(value: float) -> float:
        return abs(value - exact) / abs(exact) if exact != 0.0 else abs(value - exact)
    return {
        "exact_50_digit": exact,
        "factored": factored,
        "distributed": distributed,
        "expanded": expanded,
        "relative_error_factored": rel(factored),
        "relative_error_distributed": rel(distributed),
        "relative_error_expanded": rel(expanded),
    }
