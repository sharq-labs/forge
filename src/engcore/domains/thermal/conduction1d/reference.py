"""The closed-form reference solution. Verification side only.

This module is what the solver is checked AGAINST, so it must not be reachable
from the solver: a verification that shares code with the thing it verifies
tests only that the shared code is self-consistent. It imports numpy and this
package's units, and nothing else — in particular it never imports
:mod:`solver`, and a test asserts that.

THE SOLUTION
------------
Separating variables on

    du/dt = alpha d2u/dx2,  u(0,t) = u(L,t) = 0,  u(x,0) = sin(pi x / L)

the initial condition is already the first eigenfunction of the Laplacian with
these boundaries, so the series collapses to a single term:

    u(x, t) = sin(pi x / L) * exp(-alpha pi^2 t / L^2)

That collapse is why this benchmark was chosen. A general initial condition
would need a truncated Fourier series, and the truncation error would sit
between the solver and the only independent thing measuring it — leaving any
disagreement ambiguous between "the discretization is inaccurate" and "the
reference is". Here the reference is exact to floating-point rounding, so a
disagreement can only be the solver's.
"""

from __future__ import annotations

import math

import numpy as np

from .errors import SlabConfigurationError

#: Carried into VerificationReport so a verification result names the reference
#: it was judged against. Both are used; there is no separate version constant,
#: because the reference is an exact closed form rather than an implementation
#: that could drift.
REFERENCE_ID = "thermal.conduction1d.single_mode_analytic"
REFERENCE_EXPRESSION = "u(x,t) = sin(pi*x/L) * exp(-alpha*pi^2*t/L^2)"


def _checked(length_m: float, alpha_m2_s: float, time_s: float) -> tuple[float, float, float]:
    length = float(length_m)
    alpha = float(alpha_m2_s)
    seconds = float(time_s)
    if not math.isfinite(length) or length <= 0.0:
        raise SlabConfigurationError(f"length must be finite and positive, got {length!r}")
    if not math.isfinite(alpha) or alpha <= 0.0:
        raise SlabConfigurationError(
            f"diffusivity must be finite and positive, got {alpha!r}"
        )
    if not math.isfinite(seconds) or seconds < 0.0:
        raise SlabConfigurationError(
            f"time must be finite and non-negative, got {seconds!r}"
        )
    return length, alpha, seconds


def decay_factor(*, length_m: float, alpha_m2_s: float, time_s: float) -> float:
    """exp(-alpha pi^2 t / L^2) — the whole time dependence."""
    length, alpha, seconds = _checked(length_m, alpha_m2_s, time_s)
    return float(math.exp(-alpha * math.pi**2 * seconds / (length**2)))


def exact_field(
    x_m, *, length_m: float, alpha_m2_s: float, time_s: float
) -> np.ndarray:
    """u(x, t) at the given positions."""
    length, alpha, seconds = _checked(length_m, alpha_m2_s, time_s)
    x = np.asarray(x_m, dtype=np.float64)
    if np.any(x < -1e-15) or np.any(x > length + 1e-15):
        raise SlabConfigurationError(
            f"positions must lie within [0, {length}]; the reference is only "
            f"defined on the slab"
        )
    return np.sin(np.pi * x / length) * decay_factor(
        length_m=length, alpha_m2_s=alpha, time_s=seconds
    )


def exact_midpoint(*, length_m: float, alpha_m2_s: float, time_s: float) -> float:
    """u(L/2, t). sin(pi/2) = 1, so this is exactly the decay factor."""
    return decay_factor(length_m=length_m, alpha_m2_s=alpha_m2_s, time_s=time_s)


# NOTE: max|u| over the slab is deliberately NOT a separate function. For this
# single mode the maximum is at the midpoint, so it would return exactly what
# exact_midpoint returns — two names for one number, which is how a reference
# implementation starts to disagree with itself.
