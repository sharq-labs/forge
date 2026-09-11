"""Oracle for 1-D linear transient diffusion.

THE PHYSICS.

    du/dt = alpha d2u/dx2   on 0 < x < L,   u(0,t) = u(L,t) = 0

Separating variables, u = X(x) T(t) with X'' = -lambda^2 X and Dirichlet ends
gives X_n = sin(n pi x / L) and T_n = exp(-alpha (n pi / L)^2 t), so the
general solution is

    u(x,t) = SUM_n b_n sin(n pi x / L) exp(-alpha (n pi / L)^2 t)

with b_n the Fourier sine coefficients of the initial condition. For the
single-mode initial condition u(x,0) = sin(pi x / L) the series collapses to
its first term exactly.

TWO independent oracles are provided, because the repository already ships a
closed form and an audit that used only that would be re-running the
repository's own reference:

  * ``analytic_midpoint`` -- the series above, derived and written here.
  * ``ftcs_midpoint``     -- an explicit forward-time centred-space march,
    written here, which shares no algebra with a backward-Euler solve and no
    algebra at all with the closed form. It is conditionally stable, so it is
    driven at r = alpha dt/dx^2 <= 1/4, comfortably inside the von Neumann
    limit of 1/2.

Agreement between a closed form and an explicit march is real evidence: one is
exact and the other converges to the PDE from a different discretization than
the production solver uses.
"""

from __future__ import annotations

import math


def analytic_midpoint(*, length_m: float, alpha_m2_s: float, time_s: float) -> float:
    """u(L/2, t) for the single-mode initial condition. Exact."""
    if length_m <= 0.0 or alpha_m2_s <= 0.0 or time_s < 0.0:
        raise ValueError("length and alpha must be positive, time non-negative")
    # sin(pi * (L/2) / L) = sin(pi/2) = 1, so the spatial factor is exactly 1.
    return math.exp(-alpha_m2_s * (math.pi / length_m) ** 2 * time_s)


def analytic_field(
    *, length_m: float, alpha_m2_s: float, time_s: float, x_m: float
) -> float:
    return math.sin(math.pi * x_m / length_m) * math.exp(
        -alpha_m2_s * (math.pi / length_m) ** 2 * time_s
    )


def ftcs_midpoint(
    *,
    length_m: float,
    alpha_m2_s: float,
    time_s: float,
    n_cells: int = 400,
    target_r: float = 0.25,
) -> dict:
    """Explicit FTCS march to u(L/2, t). Independent discretization.

        u_i^{n+1} = u_i^n + r (u_{i+1}^n - 2 u_i^n + u_{i-1}^n),  r = alpha dt/dx^2

    Stable for r <= 1/2 (von Neumann: the amplification factor of mode k is
    1 - 4r sin^2(k dx / 2), whose magnitude stays below 1 exactly when
    r <= 1/2). Driven at r = 1/4 here, so stability is not in question and the
    remaining error is discretization only.
    """
    if n_cells % 2 != 0:
        raise ValueError("n_cells must be even so that L/2 is a node")
    dx = length_m / n_cells
    dt_max = target_r * dx * dx / alpha_m2_s
    n_steps = max(1, int(math.ceil(time_s / dt_max)))
    dt = time_s / n_steps
    r = alpha_m2_s * dt / (dx * dx)

    # Interior nodes only; the boundaries are held at zero and never stored.
    u = [math.sin(math.pi * i * dx / length_m) for i in range(1, n_cells)]
    for _ in range(n_steps):
        left = 0.0
        nxt = []
        for i, centre in enumerate(u):
            right = u[i + 1] if i + 1 < len(u) else 0.0
            nxt.append(centre + r * (right - 2.0 * centre + left))
            left = centre
        u = nxt
    return {
        "midpoint": u[n_cells // 2 - 1],
        "r": r,
        "dx": dx,
        "dt": dt,
        "n_steps": n_steps,
    }
