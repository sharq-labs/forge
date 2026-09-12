"""Time integration and root finding written here.

``scipy.integrate.solve_ivp`` and ``scipy.optimize.brentq`` are both used by the
Core's reactor solver and are therefore unavailable to the reference branch.
What is here instead is a fixed-step classical Runge-Kutta of order four and a
plain bisection, both short enough to read.

Every use of ``rk4`` in this round is accompanied by a refinement ladder, so
the oracle's own resolution is evidence rather than an assumption. A tolerance
justified by "RK4 is accurate" and not by a measured ladder would be a
tolerance with no provenance.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence


def rk4(
    rhs: Callable[[float, Sequence[float]], Sequence[float]],
    y0: Sequence[float],
    *,
    t0: float,
    t1: float,
    n_steps: int,
) -> list[float]:
    """Classical RK4, fixed step. Returns the state at t1."""
    if n_steps < 1:
        raise ValueError("n_steps must be at least 1")
    h = (t1 - t0) / n_steps
    y = list(y0)
    t = t0
    for step in range(n_steps):
        k1 = rhs(t, y)
        k2 = rhs(t + 0.5 * h, [yi + 0.5 * h * ki for yi, ki in zip(y, k1)])
        k3 = rhs(t + 0.5 * h, [yi + 0.5 * h * ki for yi, ki in zip(y, k2)])
        k4 = rhs(t + h, [yi + h * ki for yi, ki in zip(y, k3)])
        y = [
            yi + h * (a + 2.0 * b + 2.0 * c + d) / 6.0
            for yi, a, b, c, d in zip(y, k1, k2, k3, k4)
        ]
        t = t0 + (step + 1) * h
    return y


def refinement_ladder(
    rhs: Callable[[float, Sequence[float]], Sequence[float]],
    y0: Sequence[float],
    *,
    t0: float,
    t1: float,
    step_counts: Sequence[int],
) -> dict:
    """Run rk4 at each step count and report how the answer settles.

    The last entry's distance from the one before it is the oracle's own
    resolution, and no comparison in this round is allowed a tolerance tighter
    than that number.
    """
    results = [
        {"n_steps": n, "state": rk4(rhs, y0, t0=t0, t1=t1, n_steps=n)}
        for n in step_counts
    ]
    for previous, current in zip(results, results[1:]):
        current["change_from_previous"] = [
            abs(a - b) for a, b in zip(current["state"], previous["state"])
        ]
        current["relative_change"] = [
            abs(a - b) / abs(a) if a != 0.0 else abs(a - b)
            for a, b in zip(current["state"], previous["state"])
        ]
    finest = results[-1]
    return {
        "ladder": results,
        "state": finest["state"],
        "self_resolution": max(finest.get("relative_change", [0.0])),
    }


def bisect(
    function: Callable[[float], float],
    low: float,
    high: float,
    *,
    tolerance: float = 1e-12,
    max_iterations: int = 400,
) -> float:
    """Bisection on a sign change. No Brent, no scipy, no interpolation.

    Slower than the Core's root finder and deliberately so: an algorithm that
    converges differently is a stronger check than the same algorithm run twice.
    """
    f_low = function(low)
    f_high = function(high)
    if f_low == 0.0:
        return low
    if f_high == 0.0:
        return high
    if f_low * f_high > 0.0:
        raise ValueError("no sign change on the bracket")
    for _ in range(max_iterations):
        middle = 0.5 * (low + high)
        f_middle = function(middle)
        if f_middle == 0.0 or (high - low) < tolerance * max(1.0, abs(middle)):
            return middle
        if f_low * f_middle < 0.0:
            high, f_high = middle, f_middle
        else:
            low, f_low = middle, f_middle
    return 0.5 * (low + high)
