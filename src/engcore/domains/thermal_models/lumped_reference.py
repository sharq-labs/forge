"""The independent reference solution for the lumped body. Verification only.

This module is what :class:`~.lumped.LumpedThermalSolver` is checked AGAINST,
so it must not be reachable from it: a verification that shares code with the
thing it verifies tests only that the shared code is self-consistent. It
imports :mod:`math` and :mod:`sys` and nothing else — in particular it never
imports :mod:`lumped`, and a test asserts that.

THE TWO ROUTES, AND WHY THEY ARE INDEPENDENT
--------------------------------------------
Both routes solve the same initial value problem::

    C dT/dt = Q - hA (T - T_amb),   T(0) = T0

**The solver's route** posits the exponential ansatz. To use it, it must first
*recognise* two derived quantities that do not appear in the equation:

    T_ss = T_amb + Q / hA          the steady state
    tau  = C / hA                  the time constant

and then evaluate ``T_ss + (T0 - T_ss) * exp(-t / tau)`` through ``math.exp``.

**This module's route** posits nothing. It writes the solution as an
undetermined power series about the start of the interval, substitutes it into
the equation, and matches powers of ``t``. That gives a recurrence in the
equation's own coefficients and nothing else::

    a_0 = T0
    C a_1       = Q - hA (a_0 - T_amb)
    C (n+1) a_{n+1} = -hA a_n                      for n >= 1

The exponential is never posited; it *emerges* from the recurrence. Nothing
here forms ``T_ss``, nothing forms ``tau`` as a decay constant in an exponent,
and nothing calls ``exp``.

**What the comparison can therefore detect.** Every derived quantity on the
solver's route is a place to make an error, and each one is visible here: a
steady state formed as ``Q * hA``, a time constant inverted, a sign flipped in
the exponent, or a mis-transcribed closed form all move the answer while
leaving this recurrence untouched.

**What it cannot detect, stated plainly.** Both routes take the governing
equation above as given. If the *equation* is the wrong model of the body, both
are wrong together and agree perfectly. This is a code-verification reference,
not a physical validation, and the level it supports says exactly that much —
the same limit the frozen ``conduction1d.reference`` has, where both the solver
and the closed form take the heat equation as given.

**They are the same mathematics.** Two correct derivations of one solution must
agree; that is what makes the comparison a check rather than a coincidence.
What makes it *evidence* is that the two share no code and no intermediate
quantity, so an error in either is a disagreement rather than a shared blind
spot.

ARGUMENT REDUCTION, AND WHY IT IS STILL EXACT
----------------------------------------------
The series for one step is alternating in ``y = hA h / C``, and for ``y`` much
above 1 it converges through enormous intermediate terms that cancel — the
answer would be lost to round-off, not to method. So the interval is split into
sub-steps short enough that ``y <= MAX_STEP_ARGUMENT``, and the series is
restarted from each sub-step's own initial value.

That composition is exact, not approximate. The equation is autonomous, so its
flow map is a semigroup: solving to ``h`` and re-solving from there to ``2h``
gives the same function as solving to ``2h`` directly. There is no
discretization error to extrapolate away — only the per-step truncation
remainder and the per-step rounding, both of which are *bounded a priori* below
and reported with the answer.

WHY NUMERICALLY_CONVERGED IS NOT EARNABLE HERE, BY EITHER SIDE
---------------------------------------------------------------
Stated explicitly rather than left unmentioned. ``NUMERICALLY_CONVERGED`` is a
claim about a *discretization* that stops moving as it is refined. The lumped
solver has no discretization: no mesh, no time step, no iteration. It evaluates
a closed form once and reports ``ConvergenceState.NOT_APPLICABLE``, and there
is no sequence of the solver's own results whose limit could be examined.

The sub-step count here is a refinable parameter, but it refines *this module*,
and a reference that converges says nothing about a model that never
discretized. Awarding ``NUMERICALLY_CONVERGED`` from it would certify the
solver for work the reference did — precisely the substitution the frozen
conduction gate refuses when it declines to read a linear residual as
convergence. So nothing here awards it, and nothing should.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

#: Carried into the validation check so a result names the reference it was
#: judged against.
REFERENCE_ID = "thermal_models.lumped.series_recurrence"
REFERENCE_EXPRESSION = (
    "T(t) = sum a_n t^n with a_0 = T0, C a_1 = Q - hA (a_0 - T_amb), "
    "C (n+1) a_{n+1} = -hA a_n"
)

#: Largest ``hA h / C`` permitted for one sub-step. At 0.5 the term ratio
#: ``y / (n+1)`` is below 0.25 from the first term on, so the terms decrease
#: monotonically, the alternating-series remainder bound applies from n = 1,
#: and the largest intermediate term is the first — there is no cancellation to
#: amplify round-off.
MAX_STEP_ARGUMENT = 0.5

#: Series terms per sub-step before the remainder is accepted as it stands.
#: With ``y <= 0.5`` the terms fall faster than ``2^-n / n!`` and the loop
#: reaches round-off in well under twenty, so this bound is a guard against a
#: caller-supplied ``max_step_argument``, not a working limit. Hitting it is
#: not silent: the remainder is still a valid bound and simply comes out
#: larger, which widens the declared tolerance rather than hiding an error.
MAX_TERMS_PER_STEP = 64

#: Sub-steps this reference will spend on one interval. The interval spans
#: ``hA t / C`` units of the equation's own decay argument, so this budget
#: covers intervals up to ``MAX_STEP_ARGUMENT * MAX_SUBSTEPS`` of them.
#: Beyond it the reference reports itself UNAVAILABLE rather than returning a
#: number it cannot bound — an unbounded reference is not a reference.
MAX_SUBSTEPS = 4096

_EPS = sys.float_info.epsilon


@dataclass(frozen=True)
class LumpedReferenceSolution:
    """The reference value, its error bound, and whether it exists at all.

    ``available`` is False when the reference could not be constructed inside
    its declared budget. That is deliberately not the same as a disagreement:
    a caller must be able to tell "the reference says otherwise" from "there is
    no reference", because the first is a finding and the second is a gap.
    """

    available: bool
    value_k: float | None
    error_bound_k: float | None
    substeps: int
    terms_used: int
    unavailable_reason: str = ""

    @property
    def detail(self) -> str:
        if not self.available:
            return f"reference unavailable: {self.unavailable_reason}"
        return (
            f"{REFERENCE_ID} gives {self.value_k:.12g} K over {self.substeps} "
            f"exact sub-step(s), {self.terms_used} series terms at the "
            f"deepest, with a total error bound of "
            f"{self.error_bound_k:.3e} K"
        )


def series_reference_temperature(
    *,
    capacity_j_per_k: float,
    conductance_w_per_k: float,
    heat_input_w: float,
    ambient_k: float,
    initial_k: float,
    duration_s: float,
    max_step_argument: float = MAX_STEP_ARGUMENT,
    max_substeps: int = MAX_SUBSTEPS,
    max_terms_per_step: int = MAX_TERMS_PER_STEP,
) -> LumpedReferenceSolution:
    """T at ``duration_s``, built from the equation's coefficients by recurrence.

    Every argument is a raw coefficient of the governing equation. Nothing
    derived from it — no steady state, no time constant — is accepted, because
    accepting one would be accepting the solver's own working.

    The returned :attr:`LumpedReferenceSolution.error_bound_k` is an upper
    bound, not an estimate. It is the sum over sub-steps of the first omitted
    series term (valid because the terms decrease monotonically at these
    arguments, so the alternating-series bound applies) plus a conservative
    accounting of the floating-point summation.
    """
    values = (
        capacity_j_per_k,
        conductance_w_per_k,
        heat_input_w,
        ambient_k,
        initial_k,
        duration_s,
    )
    if not all(math.isfinite(float(v)) for v in values):
        return LumpedReferenceSolution(
            False, None, None, 0, 0, "a coefficient is not finite"
        )
    capacity = float(capacity_j_per_k)
    conductance = float(conductance_w_per_k)
    duration = float(duration_s)
    if capacity <= 0.0 or conductance <= 0.0 or duration < 0.0:
        return LumpedReferenceSolution(
            False,
            None,
            None,
            0,
            0,
            f"the recurrence needs a positive capacity and conductance and a "
            f"non-negative interval, got C={capacity!r}, hA={conductance!r}, "
            f"t={duration!r}",
        )

    # The equation's own coefficient ratio. This is not the solver's `tau`:
    # it is never used as a decay constant, only as the recurrence multiplier
    # the equation itself supplies, and as the measure of how long the
    # interval is in the equation's own units.
    ratio_per_s = conductance / capacity
    span = ratio_per_s * duration
    substeps = 1 if span <= max_step_argument else math.ceil(span / max_step_argument)
    if substeps > max_substeps:
        return LumpedReferenceSolution(
            False,
            None,
            None,
            substeps,
            0,
            f"the interval spans {span:.6g} units of hA/C, which needs "
            f"{substeps} sub-steps at an argument of {max_step_argument}; the "
            f"declared budget is {max_substeps}",
        )

    step_s = duration / substeps
    step_argument = ratio_per_s * step_s

    temperature = float(initial_k)
    truncation_bound = 0.0
    largest_magnitude = abs(temperature)
    deepest_term = 0
    for _ in range(substeps):
        # a_1 * h. The first coefficient is the equation evaluated at the
        # step's own initial value — the only place the inputs enter.
        term = ((heat_input_w - conductance * (temperature - ambient_k)) / capacity) * step_s
        increment = 0.0
        index = 1
        # Truncate once the next term cannot move the accumulated temperature
        # at double precision; the omitted tail is then bounded by it.
        target = _EPS * max(abs(temperature), 1.0)
        while True:
            increment += term
            following = -term * step_argument / (index + 1)
            if abs(following) <= target or index >= max_terms_per_step:
                truncation_bound += abs(following)
                deepest_term = max(deepest_term, index)
                break
            term = following
            index += 1
        # The increment is accumulated separately from the absolute
        # temperature, so the series never has to cancel against a 300 K
        # offset that carries no information about the interval.
        temperature += increment
        largest_magnitude = max(largest_magnitude, abs(temperature))

    rounding_bound = substeps * (deepest_term + 2) * _EPS * largest_magnitude
    return LumpedReferenceSolution(
        available=True,
        value_k=temperature,
        error_bound_k=truncation_bound + rounding_bound,
        substeps=substeps,
        terms_used=deepest_term,
    )


__all__ = [
    "MAX_STEP_ARGUMENT",
    "MAX_SUBSTEPS",
    "MAX_TERMS_PER_STEP",
    "REFERENCE_EXPRESSION",
    "REFERENCE_ID",
    "LumpedReferenceSolution",
    "series_reference_temperature",
]
