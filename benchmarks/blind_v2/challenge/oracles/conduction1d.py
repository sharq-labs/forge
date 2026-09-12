"""Independent truth for 1-D linear diffusion on a slab.

``du/dt = alpha d2u/dx2`` on ``0 <= x <= L`` with ``u(0,t) = u(L,t) = 0`` and
the single-mode initial condition ``u(x,0) = sin(pi x / L)``.

* **analytic** -- separation of variables gives ``u(x,t) = sin(pi x / L)
  exp(-alpha pi^2 t / L^2)`` exactly, for all time. Carslaw & Jaeger,
  *Conduction of Heat in Solids*, 2nd ed. (1959), Ch. III.
* **numerical** -- this challenge's own Crank-Nicolson scheme on a uniform
  grid, solved with a Thomas tridiagonal sweep written here, refined in space
  and time until the midpoint stops moving. Second-order and unconditionally
  stable, so it is a genuinely different numerical statement from an explicit
  scheme and from the closed form.

The pair is the strongest available for this system: an exact solution and an
independent discretisation that must converge to it at the scheme's own order.
"""

from __future__ import annotations

import math

from .numeric import relative_gap


def analytic_decay(*, length: float, alpha: float, time: float) -> float:
    """exp(-alpha pi^2 t / L^2) -- the first-mode amplitude at time ``t``."""
    return math.exp(-alpha * math.pi**2 * time / (length * length))


def analytic_field(x: float, *, length: float, alpha: float, time: float) -> float:
    return math.sin(math.pi * x / length) * analytic_decay(
        length=length, alpha=alpha, time=time
    )


def _thomas(a: list[float], b: list[float], c: list[float], d: list[float]) -> list[float]:
    """Tridiagonal solve, written here so nothing external is in the loop."""
    n = len(d)
    cp = [0.0] * n
    dp = [0.0] * n
    cp[0] = c[0] / b[0]
    dp[0] = d[0] / b[0]
    for i in range(1, n):
        denom = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / denom if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / denom
    x = [0.0] * n
    x[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


def crank_nicolson_midpoint(
    *, length: float, alpha: float, time: float, cells: int, steps: int
) -> float:
    """Midpoint amplitude after ``time``, by an independent discretisation."""
    dx = length / cells
    dt = time / steps
    interior = cells - 1
    if interior <= 0:
        return float("nan")
    r = alpha * dt / (2.0 * dx * dx)
    u = [math.sin(math.pi * (i + 1) * dx / length) for i in range(interior)]
    a = [-r] * interior
    b = [1.0 + 2.0 * r] * interior
    c = [-r] * interior
    a[0] = 0.0
    c[-1] = 0.0
    for _ in range(steps):
        rhs = []
        for i in range(interior):
            left = u[i - 1] if i > 0 else 0.0
            right = u[i + 1] if i < interior - 1 else 0.0
            rhs.append(u[i] + r * (left - 2.0 * u[i] + right))
        u = _thomas(a, b, c, rhs)
    mid = length / 2.0
    index = mid / dx - 1.0
    lo = int(math.floor(index))
    if abs(index - round(index)) < 1e-12:
        return u[int(round(index))]
    frac = index - lo
    lo_value = u[lo] if 0 <= lo < interior else 0.0
    hi_value = u[lo + 1] if 0 <= lo + 1 < interior else 0.0
    return lo_value * (1.0 - frac) + hi_value * frac


def evaluate(decl: dict, *, with_routes: bool = True) -> dict:
    """Truth for one slab declaration."""
    alpha = decl.get("alpha")
    length = decl.get("length")
    end_time = decl.get("end_time")

    out = {"alpha": alpha}
    routes: dict[str, dict] = {}
    if with_routes and None not in (alpha, length, end_time) and alpha > 0.0 and length > 0.0:
        exact = analytic_decay(length=length, alpha=alpha, time=end_time)
        coarse = crank_nicolson_midpoint(
            length=length, alpha=alpha, time=end_time, cells=80, steps=200
        )
        fine = crank_nicolson_midpoint(
            length=length, alpha=alpha, time=end_time, cells=160, steps=400
        )
        routes["midpoint_amplitude"] = {
            "analytic": exact,
            "numerical": fine,
            "gap": relative_gap(exact, fine),
            "refinement_movement": relative_gap(coarse, fine),
            "fourier_number": alpha * end_time / (length * length),
        }
    return {"quantities": out, "routes": routes, "intermediate": {}}
