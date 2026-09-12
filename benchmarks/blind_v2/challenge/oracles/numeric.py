"""Numerical machinery the oracles share, written for this challenge.

Deliberately small and deliberately not a wrapper around anything: a challenge
whose "independent numerical route" is a call into the same library the system
under test integrates with has one route, not two.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

STEFAN_BOLTZMANN = 5.670374419e-8  # W m^-2 K^-4, SI 2019 exact-constant value
STANDARD_GRAVITY = 9.80665  # m s^-2, CGPM 1901
GAS_CONSTANT = 8.31446261815324  # J mol^-1 K^-1, SI 2019 exact


def rk4(
    rhs: Callable[[float, Sequence[float]], Sequence[float]],
    y0: Sequence[float],
    t0: float,
    t1: float,
    steps: int,
) -> list[float]:
    """Classical fourth-order Runge-Kutta, fixed step. Returns the end state."""
    n = len(y0)
    y = [float(v) for v in y0]
    if steps <= 0 or t1 == t0:
        return y
    h = (t1 - t0) / steps
    t = t0
    for _ in range(steps):
        k1 = rhs(t, y)
        y2 = [y[i] + 0.5 * h * k1[i] for i in range(n)]
        k2 = rhs(t + 0.5 * h, y2)
        y3 = [y[i] + 0.5 * h * k2[i] for i in range(n)]
        k3 = rhs(t + 0.5 * h, y3)
        y4 = [y[i] + h * k3[i] for i in range(n)]
        k4 = rhs(t + h, y4)
        for i in range(n):
            y[i] += h * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]) / 6.0
        t += h
        if not all(math.isfinite(v) for v in y):
            # A diverging explicit step does not become informative by being
            # repeated. Stop and let the caller see the non-finite state.
            return y
    return y


def rk4_converged(
    rhs: Callable[[float, Sequence[float]], Sequence[float]],
    y0: Sequence[float],
    t0: float,
    t1: float,
    *,
    steps: int = 400,
    refinements: int = 3,
    rtol: float = 1e-9,
) -> tuple[list[float], float]:
    """Integrate, then halve the step until the answer stops moving.

    Returns ``(state, relative_movement)``. The movement is the oracle's own
    statement about its convergence and is recorded with the case: a numerical
    route that cannot say how well it converged is not evidence.
    """
    coarse = rk4(rhs, y0, t0, t1, steps)
    movement = math.inf
    for _ in range(refinements):
        steps *= 2
        fine = rk4(rhs, y0, t0, t1, steps)
        movement = max(
            abs(f - c) / max(1e-30, abs(f)) for f, c in zip(fine, coarse)
        )
        coarse = fine
        if movement < rtol:
            break
    return coarse, movement


def bisect(
    f: Callable[[float], float], lo: float, hi: float, *, tol: float = 1e-12,
    iterations: int = 200,
) -> float | None:
    """Independent root finder. ``None`` when the bracket does not straddle."""
    flo, fhi = f(lo), f(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if flo * fhi > 0.0:
        return None
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        fmid = f(mid)
        if fmid == 0.0 or (hi - lo) < tol * max(1.0, abs(mid)):
            return mid
        if flo * fmid < 0.0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return 0.5 * (lo + hi)


def relative_gap(a: float | None, b: float | None) -> float | None:
    """|a-b| / max(|a|,|b|, tiny) -- how far two routes are apart."""
    if a is None or b is None:
        return None
    if not (math.isfinite(a) and math.isfinite(b)):
        return math.inf
    scale = max(abs(a), abs(b), 1e-30)
    return abs(a - b) / scale
