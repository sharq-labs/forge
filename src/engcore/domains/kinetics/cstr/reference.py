"""Independent references. Verification side only.

This module is what the integrator is checked AGAINST, so it must not be
reachable from the integrator. It imports ``math``/``numpy``/``scipy.optimize``
and this package's errors, and nothing else — in particular it never imports
:mod:`solver`, and a test asserts that.

Independence is claimed at the level of NUMERICAL MACHINERY, not of the model.
Both sides necessarily use the same k0, E, dH and operating conditions — those
*are* the model, and a reference that used different ones would be checking a
different reactor. What differs is everything else: the equations solved
(algebraic rather than differential), the algorithm (Brent bracketing rather
than adaptive implicit time stepping), and the implementation. The Arrhenius
exponent is recomputed here from the raw activation energy rather than reusing
the declaration's derived ``e_over_r_k`` accessor, so the two sides do not even
share that division.

What that buys, stated precisely: agreement establishes that the time
integration converges to the stationary point of the equations it claims to be
integrating. It says nothing whatever about whether those equations describe a
real reactor. No physical measurement appears anywhere in this milestone.

=====================================================================
REFERENCE 1 — the steady states, by algebraic elimination
=====================================================================
Setting both derivatives to zero, the species balance is linear in C_A and can
be eliminated in closed form:

    0 = a (C_Af - C_A) - k(T) C_A       =>   C_A*(T) = a C_Af / (a + k(T))

with ``a = q/V``. Substituting into the energy balance leaves one scalar
equation in one unknown:

    g(T) = a (T_f - T) + beta k(T) C_A*(T) - gamma (T - T_c) = 0

``g`` is continuous on the model's temperature envelope, so a root at which it
*changes sign* can be bracketed by scanning and then refined by Brent's method.
For an exothermic reaction ``g`` crosses zero three times over part of the
coolant-temperature range — the ignition/extinction multiplicity — and this
function returns all such crossings rather than the first, because "the steady
state" is not well defined when there are three.

WHAT THIS SEARCH DOES AND DOES NOT PROMISE — READ BEFORE QUOTING A COUNT
--------------------------------------------------------------------------
It finds every **transversal** root: every temperature at which ``g`` changes
sign, to the resolution of the scan. That is a strictly weaker claim than "every
stationary point", and the difference is not academic here.

At a **fold** (a saddle-node bifurcation, exactly where the multiplicity window
opens and closes) two roots merge into one double root at which ``g`` touches
zero without crossing it. A sign-change scan cannot see a tangential root, and
refining the scan does not fix it: no finite grid makes a non-crossing touch
into a crossing. Arbitrarily close to a fold the two roots are still transversal
but separated by less than the scan spacing, so they are missed as a pair —
which at least fails safely, by reporting one root rather than a spurious one.

The claim is therefore narrowed rather than the algorithm extended: this
function reports transversal roots, may report fewer than the true count within
a scan spacing of a fold, and never reports a root that is not one. Detecting
tangential roots honestly needs a bifurcation/continuation method, which is a
great deal of machinery for a case this milestone does not exercise and does not
need — K1's regimes sit well away from the folds.

Consumers must therefore not read the returned count as "the number of steady
states this reactor has". :func:`steady_states` returns the roots it can
bracket; :data:`SEARCH_SEMANTICS` states this in one line for anything that
serializes the result.

=====================================================================
REFERENCE 2 — an exact invariant of the nonlinear system
=====================================================================
Let ``Z = T + beta C_A``. Then

    dZ/dt = a (T_f - T) + beta k C_A - gamma (T - T_c)
            + beta [ a (C_Af - C_A) - k C_A ]
          = a (Z_f - Z) - gamma (T - T_c),      Z_f = T_f + beta C_Af

The reaction term cancels EXACTLY. The rate constant — the entire nonlinearity
and the entire source of stiffness — does not appear in the evolution of Z.

Under adiabatic operation (UA = 0, hence gamma = 0) this collapses to a linear
scalar ODE with the closed-form solution

    Z(t) = Z_f + (Z_0 - Z_f) exp(-a t)

which is an *exact solution of a component of a genuinely nonlinear stiff
system*, available in elementary functions and containing no truncated series.
That is what makes it a real analytic reference rather than a second
approximation: any disagreement is the integrator's.

It is also a demanding check rather than a trivial one, and for a specific
reason. C_A and T individually undergo the full ignition transient; only the
combination is smooth. Reproducing Z(t) therefore requires the integrator to
keep the two states consistently coupled through the stiff region, and a scheme
that mis-tracks the fast mode breaks the cancellation immediately.

When gamma > 0 the invariant still eliminates the reaction, but its evolution
is driven by T(s) over the whole history, so evaluating it would require the
integrator's own trajectory. That is a conservation check, not an independent
solution, and this module does not offer it as one: the verification path
reports NOT_RUN for the analytic check on a cooled reactor rather than quietly
substituting a weaker claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from scipy.optimize import brentq

from .errors import ReactorConfigurationError

#: Carried into verification records so a result names what it was judged
#: against. Two distinct references, versioned together with this module.
STEADY_STATE_REFERENCE_ID = "kinetics.cstr.algebraic_steady_state_brentq"
STEADY_STATE_EXPRESSION = (
    "g(T) = a(T_f - T) + beta k(T) a C_Af/(a + k(T)) - gamma(T - T_c) = 0"
)

#: The exact scope of what the steady-state search returns. Carried into
#: serialized verification records so a reader of a stored result cannot
#: mistake the count for "the number of steady states this reactor has".
SEARCH_SEMANTICS = (
    "transversal roots only: every sign change of g on the scanned interval, "
    "refined by Brent. A tangential (double) root at a fold does not change "
    "sign and is not detected, and two roots closer together than the scan "
    "spacing are reported as none rather than as one spurious root. Never "
    "reports a root that is not one"
)
INVARIANT_REFERENCE_ID = "kinetics.cstr.adiabatic_reaction_free_invariant"
INVARIANT_EXPRESSION = (
    "Z = T + beta C_A;  Z(t) = Z_f + (Z_0 - Z_f) exp(-a t)  [exact when UA = 0]"
)

#: Same value as the model's constant. Restated rather than imported so this
#: module shares no arithmetic with the solve path.
_R_J_PER_MOL_K = 8.314462618


def _check_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ReactorConfigurationError(
            f"{label} must be finite and strictly positive, got {number!r}"
        )
    return number


def _check_non_negative(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ReactorConfigurationError(
            f"{label} must be finite and non-negative, got {number!r}"
        )
    return number


def arrhenius_rate_constant(
    temperature_k: float, *, k0_per_s: float, activation_energy_j_per_mol: float
) -> float:
    """k(T) = k0 exp(-E/(R T)), computed from E and R independently.

    Deliberately does NOT take the pre-divided E/R group: recomputing the
    division here is what keeps the reference free of the solve path's derived
    quantities.
    """
    temperature = _check_positive(temperature_k, "temperature")
    k0 = _check_positive(k0_per_s, "k0_per_s")
    energy = _check_non_negative(
        activation_energy_j_per_mol, "activation_energy_j_per_mol"
    )
    return float(k0 * math.exp(-energy / (_R_J_PER_MOL_K * temperature)))


# =====================================================================
# Reference 1 — steady states
# =====================================================================

@dataclass(frozen=True)
class SteadyState:
    """One stationary point of the reactor equations."""

    temperature_k: float
    concentration_mol_per_m3: float
    conversion: float
    #: Trace of the Jacobian at this point, used only to label the branch.
    #: A positive trace guarantees instability; a negative one does not by
    #: itself guarantee stability, so the label is deliberately three-valued.
    jacobian_trace: float
    jacobian_determinant: float

    @property
    def stability(self) -> str:
        """UNSTABLE / STABLE / INDETERMINATE from the 2x2 linearization.

        For a two-state system a stationary point is asymptotically stable iff
        trace < 0 and determinant > 0. Anything else with determinant > 0 and
        trace >= 0 is unstable; determinant < 0 is a saddle, also unstable.
        Exact zeros are reported as indeterminate rather than guessed.
        """
        if self.jacobian_determinant < 0.0:
            return "unstable"
        if self.jacobian_determinant == 0.0 or self.jacobian_trace == 0.0:
            return "indeterminate"
        return "stable" if self.jacobian_trace < 0.0 else "unstable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature_k": self.temperature_k,
            "concentration_mol_per_m3": self.concentration_mol_per_m3,
            "conversion": self.conversion,
            "jacobian_trace": self.jacobian_trace,
            "jacobian_determinant": self.jacobian_determinant,
            "stability": self.stability,
        }


def steady_state_residual(
    temperature_k: float,
    *,
    dilution_rate_per_s: float,
    feed_concentration_mol_per_m3: float,
    feed_temperature_k: float,
    coolant_temperature_k: float,
    beta_m3_k_per_mol: float,
    gamma_per_s: float,
    k0_per_s: float,
    activation_energy_j_per_mol: float,
) -> float:
    """``g(T)`` — the scalar steady-state energy residual, in K/s."""
    a = _check_positive(dilution_rate_per_s, "dilution_rate_per_s")
    k = arrhenius_rate_constant(
        temperature_k,
        k0_per_s=k0_per_s,
        activation_energy_j_per_mol=activation_energy_j_per_mol,
    )
    ca_star = a * feed_concentration_mol_per_m3 / (a + k)
    return float(
        a * (feed_temperature_k - temperature_k)
        + beta_m3_k_per_mol * k * ca_star
        - gamma_per_s * (temperature_k - coolant_temperature_k)
    )


def steady_states(
    *,
    dilution_rate_per_s: float,
    feed_concentration_mol_per_m3: float,
    feed_temperature_k: float,
    coolant_temperature_k: float,
    beta_m3_k_per_mol: float,
    gamma_per_s: float,
    k0_per_s: float,
    activation_energy_j_per_mol: float,
    search_min_k: float,
    search_max_k: float,
    scan_points: int = 20001,
    xtol: float = 1.0e-12,
) -> tuple[SteadyState, ...]:
    """Every **transversal** root in ``[search_min_k, search_max_k]``.

    A dense uniform scan brackets the sign changes; Brent's method refines each
    bracket. The scan is dense on purpose: an ignition branch can be narrow,
    and a coarse scan that stepped over a bracketed pair would silently report
    one steady state where there are three — the failure mode that would make
    this reference agree with a wrong answer.

    This is NOT a promise to return every stationary point. A tangential root
    at a fold does not change sign and is not found, and a pair separated by
    less than the scan spacing is missed as a pair. See :data:`SEARCH_SEMANTICS`
    and the module docstring; the shortfall is always in the safe direction
    (fewer roots, never a spurious one).
    """
    a = _check_positive(dilution_rate_per_s, "dilution_rate_per_s")
    low = _check_positive(search_min_k, "search_min_k")
    high = _check_positive(search_max_k, "search_max_k")
    if high <= low:
        raise ReactorConfigurationError(
            f"search_max_k ({high}) must exceed search_min_k ({low})"
        )
    if int(scan_points) < 3:
        raise ReactorConfigurationError("scan_points must be at least 3")

    def residual(temperature: float) -> float:
        return steady_state_residual(
            temperature,
            dilution_rate_per_s=a,
            feed_concentration_mol_per_m3=feed_concentration_mol_per_m3,
            feed_temperature_k=feed_temperature_k,
            coolant_temperature_k=coolant_temperature_k,
            beta_m3_k_per_mol=beta_m3_k_per_mol,
            gamma_per_s=gamma_per_s,
            k0_per_s=k0_per_s,
            activation_energy_j_per_mol=activation_energy_j_per_mol,
        )

    # The scalar residual validated the rate parameters on every one of its
    # ``scan_points`` calls, by way of ``arrhenius_rate_constant``. The array
    # scan below evaluates the Arrhenius factor directly, so the same refusals
    # are made here, once, and up front. Dropping them would turn an invalid
    # declaration from an error into a silently fabricated residual curve.
    k0 = _check_positive(k0_per_s, "k0_per_s")
    energy = _check_non_negative(
        activation_energy_j_per_mol, "activation_energy_j_per_mol"
    )

    grid = np.linspace(low, high, int(scan_points))

    # The BRACKETING scan is evaluated as array arithmetic rather than as
    # ``scan_points`` separate Python calls. This is the same expression in the
    # same order on the same float64 values — g(T) is a composition of exp,
    # multiply, divide, add and subtract, each of which IEEE-754 defines
    # elementwise — so the sampled residuals, the sign changes they bracket and
    # therefore the roots are bit-identical to the scalar scan. That equality is
    # asserted over every preregistered regime in
    # tests/domains/kinetics/test_cstr_reference_scan.py, because a scan that
    # merely *nearly* agreed could bracket a different pair and move a root.
    #
    # REFINEMENT IS DELIBERATELY NOT VECTORIZED: ``brentq`` below is still
    # handed the scalar ``residual``, so the root-finding algorithm, its
    # tolerance and the reference's independence from the solve path are all
    # untouched. Only the scan that *locates* the brackets changed.
    with np.errstate(over="ignore"):
        rate = k0 * np.exp(-energy / (_R_J_PER_MOL_K * grid))
    ca_star = a * feed_concentration_mol_per_m3 / (a + rate)
    values = (
        a * (feed_temperature_k - grid)
        + beta_m3_k_per_mol * rate * ca_star
        - gamma_per_s * (grid - coolant_temperature_k)
    )

    roots: list[float] = []
    for index in range(len(grid) - 1):
        left, right = float(grid[index]), float(grid[index + 1])
        f_left, f_right = float(values[index]), float(values[index + 1])
        if f_left == 0.0:
            roots.append(left)
        elif f_left * f_right < 0.0:
            roots.append(float(brentq(residual, left, right, xtol=xtol)))
    if float(values[-1]) == 0.0:
        roots.append(float(grid[-1]))

    resolved: list[SteadyState] = []
    for temperature in sorted(roots):
        if resolved and abs(temperature - resolved[-1].temperature_k) < 1e-9:
            continue
        k = arrhenius_rate_constant(
            temperature,
            k0_per_s=k0_per_s,
            activation_energy_j_per_mol=activation_energy_j_per_mol,
        )
        concentration = a * feed_concentration_mol_per_m3 / (a + k)
        conversion = (
            (feed_concentration_mol_per_m3 - concentration)
            / feed_concentration_mol_per_m3
            if feed_concentration_mol_per_m3 > 0.0
            else 0.0
        )
        # Analytic Jacobian of the two-state system at this point.
        dk_dt = k * activation_energy_j_per_mol / (
            _R_J_PER_MOL_K * temperature * temperature
        )
        j11 = -(a + k)
        j12 = -concentration * dk_dt
        j21 = beta_m3_k_per_mol * k
        j22 = -(a + gamma_per_s) + beta_m3_k_per_mol * concentration * dk_dt
        resolved.append(
            SteadyState(
                temperature_k=float(temperature),
                concentration_mol_per_m3=float(concentration),
                conversion=float(conversion),
                jacobian_trace=float(j11 + j22),
                jacobian_determinant=float(j11 * j22 - j12 * j21),
            )
        )
    return tuple(resolved)


# =====================================================================
# Reference 2 — the exact adiabatic invariant
# =====================================================================

def invariant_value(
    concentration_mol_per_m3,
    temperature_k,
    *,
    beta_m3_k_per_mol: float,
):
    """``Z = T + beta C_A``, the reaction-free combination.

    Accepts scalars or arrays; a scalar in gives a float out, so the verifier
    can use one expression for a single state and for a whole trajectory
    without restating the formula in two places.
    """
    concentration = np.asarray(concentration_mol_per_m3, dtype=np.float64)
    temperature = np.asarray(temperature_k, dtype=np.float64)
    combined = temperature + float(beta_m3_k_per_mol) * concentration
    if combined.ndim == 0:
        return float(combined)
    return combined


def adiabatic_invariant_exact(
    time_s,
    *,
    dilution_rate_per_s: float,
    beta_m3_k_per_mol: float,
    feed_concentration_mol_per_m3: float,
    feed_temperature_k: float,
    initial_concentration_mol_per_m3: float,
    initial_temperature_k: float,
) -> np.ndarray:
    """``Z(t) = Z_f + (Z_0 - Z_f) exp(-a t)``. Exact; adiabatic only.

    The caller is responsible for having established that the reactor is
    adiabatic. This function cannot check it — gamma does not appear in the
    formula, which is precisely why passing a cooled reactor here would produce
    a confident wrong answer instead of an error. The verification path guards
    it with :func:`invariant_is_exact` and a test pins that guard.
    """
    a = _check_positive(dilution_rate_per_s, "dilution_rate_per_s")
    z_feed = invariant_value(
        feed_concentration_mol_per_m3,
        feed_temperature_k,
        beta_m3_k_per_mol=beta_m3_k_per_mol,
    )
    z_initial = invariant_value(
        initial_concentration_mol_per_m3,
        initial_temperature_k,
        beta_m3_k_per_mol=beta_m3_k_per_mol,
    )
    t = np.asarray(time_s, dtype=np.float64)
    if np.any(t < 0.0):
        raise ReactorConfigurationError(
            "the invariant reference is defined for non-negative times only"
        )
    return z_feed + (z_initial - z_feed) * np.exp(-a * t)


def invariant_is_exact(gamma_per_s: float) -> bool:
    """True only for a strictly adiabatic reactor.

    Exact equality with zero, not a tolerance. A reactor with a small but
    non-zero UA has an invariant driven by its whole temperature history, and
    calling that "approximately exact" is how an unearned ANALYTICALLY_VERIFIED
    would get awarded.
    """
    return float(gamma_per_s) == 0.0


__all__ = [
    "STEADY_STATE_REFERENCE_ID",
    "STEADY_STATE_EXPRESSION",
    "INVARIANT_REFERENCE_ID",
    "INVARIANT_EXPRESSION",
    "SteadyState",
    "arrhenius_rate_constant",
    "steady_state_residual",
    "steady_states",
    "invariant_value",
    "adiabatic_invariant_exact",
    "invariant_is_exact",
]
