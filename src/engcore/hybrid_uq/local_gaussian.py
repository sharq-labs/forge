"""LOCAL_GAUSSIAN_APPROXIMATION: N(z_hat, (J_w^T J_w)^-1) at the calibrated estimate, and when not to believe it.

It is exact only for a model affine in the inference coordinates, with no bound near the estimate and a
single optimum. Every one of those assumptions has a diagnostic. When a diagnostic fails the route REFUSES
(and emits no covariance) or DOWNGRADES (and says why). It never reports precise uncertainty anyway.

* interior, stationary optimum -- the Gauss-Newton step from the estimate, in sd units;
* usable curvature -- rank and the column-equilibrated condition number of the weighted Jacobian;
* bounds not dominating -- distance to each bound in sd;
* locally affine within about +/-2 sd -- chi-square rise along every principal axis and every diagonal between
  two of them, against the 4 a Gaussian implies; fewer evaluated probes than parameters is no measurement;
* no heavier tail than the Gaussian out to 6 sd -- the chi-square rise at 3 and 6 sd along every principal axis,
  against r^2 (CORE-003). Only a shortfall is gated: it means mass the reported interval does not hold;
* residuals the declared noise can explain -- chi2_min against chi-square on n - p degrees of freedom (CORE-001). A
  covariance built from a declared sigma is the parameter uncertainty only if that sigma describes the residuals;
* parameterization conditioning -- raw versus equilibrated condition;
* a single mode -- a deterministic multistart through the frozen ``calibrate``, of at least a minimum search.
  Without one, or below that minimum, the claim is capped at DOWNGRADED: no SUPPORTED claim assumes a single
  mode nobody looked past. A converged refit below the estimate's objective refuses, near or far.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import chi2, norm

from ..inference.calibration import CalibrationResult, CalibrationSpec, CalibrationStatus, ForwardEvaluator, calibrate
from ..inference.grid import ObservationSet
from ..inference.parameters import CalibrationParameterSet
from ..inference.split import observation_set_content_digest
from ..scientific.errors import UnitCompatibilityError
from ..scientific.results.immutable import freeze
from ..scientific.units.quantity import Quantity, is_ratio_scale
from ._records import (
    decode_float, decode_matrix, decode_vector, digest_of, encode_float, encode_matrix, encode_vector, material,
    require_schema, require_valid_covariance,
)
from .sensitivity import (
    LocalSensitivity, _bind_supplied_sensitivity, _DerivativeNotConverged, evaluate, inference_bounds, reconstruct_local_sensitivity, to_inference,
    to_natural, transforms_of,
)
from .vocabulary import (
    ApproximationClass, HybridUQError, RouteClaim, RouteReason, RouteRefusedError, claim_for,
)

MULTISTART_POLICY_SCHEMA = "hybrid_uq.multistart_policy/1"
ROUTE_DIAGNOSTICS_SCHEMA = "hybrid_uq.route_diagnostics/3"
#: Written before the goodness-of-fit and tail diagnostics existed (CORE-001/-003). Read only to refuse it with the
#: reason: nothing it carries can show that a claim it makes survives those rules, and its threshold set is not the
#: canonical one.
ROUTE_DIAGNOSTICS_SCHEMA_V1 = "hybrid_uq.route_diagnostics/1"
#: I-14 (R-22(a)): the schema `observation_content_digest` was added under. A /2 payload carries no
#: digest, so its `observations` field is unbound and R-22(a) survives for such a payload -- which is
#: deliberate: refusing it would break records this core wrote, and the route now writes /3 for
#: everything, so every record this core PRODUCES is checkable.
ROUTE_DIAGNOSTICS_SCHEMA_V2 = "hybrid_uq.route_diagnostics/2"
PARAMETER_INTERVAL_SCHEMA = "hybrid_uq.parameter_interval/1"
LOCAL_GAUSSIAN_POSTERIOR_SCHEMA = "hybrid_uq.local_gaussian_posterior/1"

#: Declared validity thresholds, recorded in every RouteDiagnostics. Validated by the HD-UQ review
#: (benchmarks/core_gap_hd_uq) on Battery B3, TCR, K2 and failure cases F1-F6.
NONLINEARITY_DOWNGRADE = 0.10
NONLINEARITY_REFUSE = 0.50
BOUND_DOWNGRADE_SD = 3.0
STATIONARITY_SD = 0.05
AT_BOUND_RELATIVE = 1.0e-6
NUMERICAL_CONDITION_LIMIT = 1.0 / math.sqrt(float(np.finfo(float).eps))
PROBE_SD = 2.0
#: R-26 (re-audit 2026-09-16, I-08 part A): the COLUMN-EQUILIBRATED condition number at which double-precision
#: arithmetic alone moves the reported covariance by the nonlinearity tolerance this module already accepts.
#: The relative error of a linear solve at condition kappa is of order eps * kappa^2;
#: ``NUMERICAL_CONDITION_LIMIT`` is exactly where that reaches 1 -- where the covariance has no correct digits
#: -- and is already the REFUSAL. The DOWNGRADE is where the same quantity reaches ``NONLINEARITY_DOWNGRADE``,
#: so the limit is sqrt(0.10) / sqrt(eps): the two declared constants combined the only way the units allow,
#: and no number chosen. It replaces the RAW condition number, which any caller moves by any factor by
#: restating a parameter in a smaller unit -- a claim that moves under a unit change is not a claim about the
#: evidence. The raw number is still RECORDED in ``raw_jacobian_condition``; it just no longer lowers a claim.
#: Deliberately NOT in ``_thresholds()``: that map is serialized into every RouteDiagnostics and re-derived
#: exactly on read-back, so a new key would refuse every record ever written under
#: hybrid_uq.route_diagnostics/2. Stated as a residual in BATCH20_THRESHOLD_PROTOCOL.json.
POORLY_SCALED_CONDITION_LIMIT = math.sqrt(NONLINEARITY_DOWNGRADE) * NUMERICAL_CONDITION_LIMIT

#: CORE-001, preregistered in benchmarks/core_v4_false_confidence/BATCH1_THRESHOLD_PROTOCOL.json. The alpha is the
#: one HELD_OUT_CHI_SQUARE_ALPHA already declares (class B); the variance ratio is class C: above 4 the residual
#: scatter exceeds twice the declared sigma, so no rescaling of the covariance makes its sds right to a factor 2.
GOODNESS_OF_FIT_ALPHA = 0.01
MISFIT_REFUSE_VARIANCE_RATIO = 4.0
#: CORE-003: tail probe radii, and the rise ratio (chi2 rise / r^2, 1 for the reported Gaussian) below which the
#: route downgrades and refuses -- the existing nonlinearity thresholds, on the shortfall side only (class C).
TAIL_PROBE_SD = (3.0, 6.0)
TAIL_DOWNGRADE_RATIO = 1.0 - NONLINEARITY_DOWNGRADE
TAIL_REFUSE_RATIO = 1.0 - NONLINEARITY_REFUSE

_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107,
           109, 113, 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229)


def _prime(index: int) -> int:
    if index < len(_PRIMES):
        return _PRIMES[index]
    candidate, found = _PRIMES[-1], len(_PRIMES) - 1
    while found < index:
        candidate += 2
        if all(candidate % q for q in range(3, int(candidate ** 0.5) + 1, 2)):
            found += 1
    return candidate


def _radical_inverse(n: int, base: int) -> float:
    value, fraction = 0.0, 1.0 / base
    while n > 0:
        n, digit = divmod(n, base)
        value += digit * fraction
        fraction /= base
    return value


def _thresholds() -> dict[str, float]:
    return {
        "nonlinearity_downgrade": NONLINEARITY_DOWNGRADE, "nonlinearity_refuse": NONLINEARITY_REFUSE,
        "bound_downgrade_sd": BOUND_DOWNGRADE_SD, "stationarity_sd": STATIONARITY_SD,
        "at_bound_relative": AT_BOUND_RELATIVE, "numerical_condition_limit": NUMERICAL_CONDITION_LIMIT,
        "probe_sd": PROBE_SD, "goodness_of_fit_alpha": GOODNESS_OF_FIT_ALPHA,
        "misfit_refuse_variance_ratio": MISFIT_REFUSE_VARIANCE_RATIO, "tail_probe_sd_inner": TAIL_PROBE_SD[0],
        "tail_probe_sd_outer": TAIL_PROBE_SD[1], "tail_downgrade_ratio": TAIL_DOWNGRADE_RATIO,
        "tail_refuse_ratio": TAIL_REFUSE_RATIO,
    }


#: R-20 (re-audit 2026-09-16). With the variance-ratio refusal unconditional, a true variance ratio of
#: MISFIT_REFUSE_VARIANCE_RATIO is missed with probability P(chi2_dof <= min(dof, chi2.ppf(1 - alpha/2, dof) / 4)):
#: 0.683 at dof 1, 0.632 at dof 2, 0.608 at dof 3, 0.554 at dof 4, 0.477 at dof 5, 0.210 at dof 10. At or below this
#: many residual degrees of freedom the gate is more likely to miss a factor-4 misfit than to catch it, and the record
#: says so with GOODNESS_OF_FIT_UNDERPOWERED instead of reading "tested and adequate".
UNDERPOWERED_RESIDUAL_DOF = 2


def _leverage_weights(weighted_jacobian: "np.ndarray") -> tuple["np.ndarray", "np.ndarray"]:
    """``(hat_diagonal, orthonormal_basis)`` of a whitened Jacobian's column space (R-03).

    ``H = A (A^T A)^-1 A^T = U U^T`` for any orthonormal basis U of the column space of A, so observation i's
    leverage -- its share of the Fisher information that builds the reported covariance -- is
    ``H_ii = sum_j U[i, j]^2``. The weights lie in [0, 1] and sum to the rank. The basis is returned with them
    because the statistic's null cumulants are computed from it without forming the n x n matrix.
    """
    A = np.asarray(weighted_jacobian, dtype=np.float64)
    u, singular, _ = np.linalg.svd(A, full_matrices=False)
    if singular.size == 0 or not (singular[0] > 0.0):
        return np.zeros(A.shape[0]), np.zeros((A.shape[0], 0))
    keep = singular > singular[0] * max(A.shape) * np.finfo(float).eps
    basis = u[:, keep]
    return np.clip(np.einsum("ij,ij->i", basis, basis), 0.0, 1.0), basis


def _leverage_null_cumulants(weights: "np.ndarray", basis: "np.ndarray") -> tuple[float, float, float]:
    """``(c1, c2, c3)`` with ``c_k = trace(((I - H) D)^k)``, ``D = diag(weights)`` and ``H = basis basis^T``.

    Under the route's own premise -- the declared sigma is right, so the standardized errors are N(0, I) --
    the fitted residuals satisfy ``r = (I - H) e``, so ``T = sum_i weights_i r_i^2`` is the quadratic form
    ``e^T (I - H) D (I - H) e``. Its mean is exactly c1, its variance 2 c2 and its third central moment 8 c3.

    Written out in closed form, so nothing of size n x n is built: with ``h = diag(H)``, ``G = U^T D U`` and
    ``G2 = U^T D^2 U`` (both rank x rank),

        c1 = sum d     -     sum h d
        c2 = sum d^2   - 2   sum h d^2   +   tr(G^2)
        c3 = sum d^3   - 3   sum h d^3   + 3 tr(G G2) - tr(G^3)

    At ``d = 1`` for every observation all three are ``n - rank``, and the three-moment match below then
    reduces to the pooled chi-square test exactly. That identity is what makes this null checkable.
    """
    d = np.asarray(weights, dtype=np.float64)
    U = np.asarray(basis, dtype=np.float64)
    h = np.einsum("ij,ij->i", U, U) if U.size else np.zeros(d.shape)
    G = U.T @ (d[:, None] * U) if U.size else np.zeros((0, 0))
    G2 = U.T @ ((d ** 2)[:, None] * U) if U.size else np.zeros((0, 0))
    # NON-NEGATIVE BY ARITHMETIC, AND THE CLOSED FORM REACHES ZERO BY
    # CANCELLATION (I-14, landed in the batch that needed it).
    #
    # `c_k = trace(M^k)` with `M = (I - H) D (I - H)` positive semidefinite --
    # `D = diag(h)` has `h` in [0, 1] and `I - H` is an orthogonal projector --
    # so none of the three can be negative. `c2` is half the statistic's
    # variance and `c3` an eighth of its third central moment, and neither can
    # be negative for a quadratic form in N(0, I).
    #
    # The form above is written out precisely so that nothing of size n x n is
    # built, and the price of that trade is cancellation: for a problem where
    # one observation holds all the leverage the true cumulants are zero and
    # this arithmetic produced -2.22e-16, which is exactly -eps. The route's own
    # `_require_reasons_follow_measurements` refuses a record whose null carries
    # a negative cumulant, so such a problem could not be ROUTED at all -- it
    # raised before any verdict was reached.
    #
    # Clamped at the source rather than tolerated at the check, and only inside
    # a floor derived from the computation, so a genuinely negative value -- the
    # only other way one could arise being a coding error -- still raises.
    terms1 = float(np.sum(np.abs(d)) + np.sum(np.abs(h * d)))
    terms2 = float(np.sum(d ** 2) + 2.0 * np.sum(np.abs(h * d ** 2)) + abs(np.trace(G @ G)))
    terms3 = float(np.sum(np.abs(d) ** 3) + 3.0 * np.sum(np.abs(h * d ** 3))
                   + 3.0 * abs(np.trace(G @ G2)) + abs(np.trace(G @ G @ G)))
    count = max(int(d.size), 1)
    c1 = float(np.sum(d) - np.sum(h * d))
    c2 = float(np.sum(d ** 2) - 2.0 * np.sum(h * d ** 2) + np.trace(G @ G))
    c3 = float(np.sum(d ** 3) - 3.0 * np.sum(h * d ** 3) + 3.0 * np.trace(G @ G2) - np.trace(G @ G @ G))
    return (
        _clamp_leverage_cumulant(c1, scale=terms1, terms=count, name="c1"),
        _clamp_leverage_cumulant(c2, scale=terms2, terms=count, name="c2"),
        _clamp_leverage_cumulant(c3, scale=terms3, terms=count, name="c3"),
    )


def _clamp_leverage_cumulant(value: float, *, scale: float, terms: int, name: str) -> float:
    """A leverage null cumulant, with round-off at zero removed and nothing else.

    The floor is DERIVED and not chosen: ``terms * eps * scale``, with ``scale``
    the sum of the magnitudes of the summands that formed ``value``, is the
    standard first-order bound on the round-off of a sum of that many terms. A
    value inside it is indistinguishable from zero in float64; a value outside
    it is not round-off, and clamping it would turn this function into a way of
    accepting a coding error. (I-14.)
    """
    if value >= 0.0:
        return float(value)
    floor = float(terms) * float(np.finfo(float).eps) * abs(float(scale))
    if value >= -floor:
        return 0.0
    raise HybridUQError(
        f"the leverage null's {name} came out {value!r}, which is below the "
        f"round-off floor {-floor!r} of its own computation. It is the trace of "
        f"a power of a positive-semidefinite matrix and cannot be negative, so "
        f"this is not cancellation but an error in how it was formed"
    )


def _three_moment_p_value(statistic: float, c1: float, c2: float, c3: float) -> float:
    """Pearson's three-moment match of a quadratic form to a shifted, scaled chi-square; NaN when undefined.

    ``b = c3 / c2``, ``dof = c2^3 / c3^2`` and ``a = c1 - b dof`` reproduce the form's mean, variance and third
    central moment exactly, and the p-value is ``chi2.sf((T - a) / b, dof)``. At equal weights b = 1,
    dof = n - rank and a = 0, so this IS the pooled test.
    """
    if not (float(c2) > 0.0 and float(c3) > 0.0):
        return math.nan
    b = float(c3) / float(c2)
    dof = float(c2) ** 3 / float(c3) ** 2
    a = float(c1) - b * dof
    return float(chi2.sf((float(statistic) - a) / b, dof))


def _one_fit_test(statistic: float, null_mean: float, p_value: float) -> int:
    """How badly one CORE-001 test fails: 0 no reason, 1 a downgrade, 2 a refusal.

    The variance ratio refuses whatever the p-value says (R-20). Batch 1 declared the ratio of 4 because above
    it "the residual scatter exceeds twice the declared sigma, so no rescaling of the covariance makes its sds
    right to a factor 2" -- a statement about the SIZE of the error in the reported uncertainty, which does not
    become false when the sample is too small for the p-value to notice it.
    """
    if not (float(null_mean) > 0.0) or not (float(statistic) >= 0.0):
        return 0
    if float(statistic) / float(null_mean) > MISFIT_REFUSE_VARIANCE_RATIO:
        return 2
    if math.isnan(float(p_value)) or float(p_value) >= GOODNESS_OF_FIT_ALPHA / 2.0:
        return 0
    return 1


def _goodness_of_fit(chi_square_minimum: float, observations: int, parameters: int,
                     leverage_statistic: float = math.nan,
                     leverage_cumulants: Sequence[float] = ()) -> tuple[set, set]:
    """``(refusals, downgrades)`` the declared noise implies for a fit (CORE-001). One rule, four callers.

    Two tests, each run at half the declared alpha so the family-wise false-refusal rate stays the level batch
    1 declared, and the WORSE result stands:

    * the POOLED test, on chi2_min against chi-square on n - p degrees of freedom;
    * the LEVERAGE test (R-03), on ``T = sum_i H_ii r_i^2`` against the three-moment null of its cumulants.
      It weighs each residual by how much the reported covariance depends on it. An observation with a large
      declared sigma adds almost nothing to ``A^T A``, so it does not move the covariance, but it does add a
      degree of freedom to the pooled test: padding a dataset with such readings diluted the pooled gate and
      left the covariance where it was. A REFUSED misfit at chi2/dof 9 read SUPPORTED with 60 of them.

    A route that carries no leverage statistic -- a record written before this rule, or a caller with no
    Jacobian -- is held to the pooled test alone, at the same alpha / 2.

    At one or two residual degrees of freedom the gate is more likely to miss a factor-4 misfit than to catch
    it, so the claim is capped with GOODNESS_OF_FIT_UNDERPOWERED (R-20): the declared noise model was not
    tested and found adequate, it was essentially untestable.

    Under-dispersion is not gated: a declared sigma larger than the residuals makes the reported uncertainty
    conservative, and conservatism is not false confidence.
    """
    dof = int(observations) - int(parameters)
    chi = float(chi_square_minimum)
    verdict = 0
    if dof >= 1 and chi >= 0.0:
        verdict = _one_fit_test(chi, float(dof), float(chi2.sf(chi, dof)))
    cumulants = tuple(float(c) for c in leverage_cumulants)
    if len(cumulants) == 3:
        verdict = max(verdict, _one_fit_test(float(leverage_statistic), cumulants[0],
                                             _three_moment_p_value(leverage_statistic, *cumulants)))
    refusals = {RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE} if verdict == 2 else set()
    downgrades = {RouteReason.RESIDUALS_EXCEED_DECLARED_NOISE} if verdict == 1 else set()
    if 1 <= dof <= UNDERPOWERED_RESIDUAL_DOF:
        downgrades.add(RouteReason.GOODNESS_OF_FIT_UNDERPOWERED)
    return refusals, downgrades


def _tail_verdict(minimum_rise_ratio: float) -> tuple[set, set]:
    """``(refusals, downgrades)`` for the smallest tail rise ratio measured (CORE-003); NaN means none was evaluated."""
    ratio = float(minimum_rise_ratio)
    if math.isnan(ratio):
        return set(), set()
    if ratio < TAIL_REFUSE_RATIO:
        return {RouteReason.TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN}, set()
    if ratio < TAIL_DOWNGRADE_RATIO:
        return set(), {RouteReason.TAIL_HEAVIER_WITHIN_6_SD}
    return set(), set()


#: The goodness-of-fit reasons, which no grid route may be built past: a grid claim is SUPPORTED or absent.
MISFIT_REASONS = frozenset({RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE, RouteReason.RESIDUALS_EXCEED_DECLARED_NOISE})


#: The smallest multistart that may stand behind a claim of a single mode (audit HUQ-01). A caller may search more;
#: a search below ``max(MINIMUM_MULTISTART_STARTS, 2p + 2)`` starts, or over a narrower span or with looser mode
#: classification than the canonical policy, is recorded as MULTISTART_BELOW_MINIMUM_SEARCH and the claim is capped
#: at DOWNGRADED (MULTISTART_INCOMPLETE). Without this, ``MultistartPolicy(starts=1)`` switched the check off and still
#: read SUPPORTED.
MINIMUM_MULTISTART_STARTS = 6

#: The multistart policy a route actually used, recorded inside ``RouteDiagnostics.thresholds`` (so it is committed
#: to the diagnostics digest without a new field). Present exactly when a multistart was run.
_MULTISTART_POLICY_KEYS = (
    "multistart_comparable_fit_quantile", "multistart_interior_fraction", "multistart_max_evaluations",
    "multistart_maximum_retractions", "multistart_minimum_starts", "multistart_mode_separation_quantile",
    "multistart_starts",
)

#: A converged refit whose objective is below the estimate's by more than the route's own stationarity allowance is
#: a lower point the estimate did not find: the estimate is not the optimum of its basin (audit HUQ-08). The
#: allowance is twice the Gauss-Newton predicted decrease from the estimate, and never less than the objective
#: change of a STATIONARITY_SD step.
LOWER_OBJECTIVE_FLOOR = STATIONARITY_SD ** 2

#: A separated converged refit is a SECOND MODE when the posterior mass around it is not negligible, and only a worse
#: local optimum when it is (audit R-07). Negligible is this ratio of its mass to the estimate's: a mode with mass
#: ratio r holds r / (1 + r) of the total, so for a 95% interval around the estimate to still hold the 0.90 that the
#: V4 conformance floor requires, the mass elsewhere must stay under 0.05 -- r < 0.0526. This floor is a factor 50
#: inside that. Classifying by objective alone read a broad basin ten chi-square units up holding 0.79 of the
#: posterior as WORSE_LOCAL_OPTIMUM, which the verdict then ignored.
MULTISTART_MASS_FLOOR = 1.0e-3

#: The largest log mass ratio the route turns into a number. Above it the ratio overflows a float, and a mode that
#: dominates the estimate by e^700 is recorded as a second mode whose ratio could not be written rather than as a
#: fabricated finite one.
_MASS_RATIO_LOG_LIMIT = 700.0


def _minimum_starts(p: int) -> int:
    return max(MINIMUM_MULTISTART_STARTS, 2 * int(p) + 2)


def _policy_record(policy: "MultistartPolicy", p: int) -> dict[str, float]:
    return {
        "multistart_starts": float(int(policy.starts)), "multistart_interior_fraction": float(policy.interior_fraction),
        "multistart_max_evaluations": float(int(policy.max_evaluations)),
        "multistart_mode_separation_quantile": float(policy.mode_separation_quantile),
        "multistart_comparable_fit_quantile": float(policy.comparable_fit_quantile),
        "multistart_maximum_retractions": float(int(policy.maximum_retractions)),
        "multistart_minimum_starts": float(_minimum_starts(p)),
    }


def _search_shortfalls(record: Mapping[str, float], p: int) -> list[str]:
    """Why a recorded multistart policy is below the minimum search, or an empty list."""
    canonical = MultistartPolicy()
    shortfalls = []
    if float(record["multistart_starts"]) < _minimum_starts(p):
        shortfalls.append(f"{int(record['multistart_starts'])} start(s), below the minimum of {_minimum_starts(p)} for p = {p}")
    if float(record["multistart_interior_fraction"]) < canonical.interior_fraction:
        shortfalls.append(f"interior_fraction {record['multistart_interior_fraction']:g} spans less than {canonical.interior_fraction:g}")
    if float(record["multistart_mode_separation_quantile"]) > canonical.mode_separation_quantile:
        shortfalls.append("mode_separation_quantile above the canonical value merges separated modes")
    if float(record["multistart_comparable_fit_quantile"]) != canonical.comparable_fit_quantile:
        shortfalls.append("comparable_fit_quantile is not the canonical value")
    if float(record["multistart_max_evaluations"]) < float(int(canonical.max_evaluations)):
        # the start that travels to a distant mode is the slow one, so a small budget removes exactly that refit
        shortfalls.append(f"max_evaluations {int(record['multistart_max_evaluations'])} is below the canonical "
                          f"{int(canonical.max_evaluations)}, which drops the slowest refits")
    if float(record["multistart_maximum_retractions"]) < float(int(canonical.maximum_retractions)):
        shortfalls.append(f"maximum_retractions {int(record['multistart_maximum_retractions'])} replaces fewer refused "
                          f"starts than the canonical {int(canonical.maximum_retractions)}, so the search looks in fewer places")
    return shortfalls


def _multistart_verdict(entries: Sequence[Mapping[str, Any]], p: int,
                        thresholds: Mapping[str, float]) -> tuple[str, set[RouteReason], set[RouteReason]]:
    """``(uniqueness, refusals, downgrades)`` implied by recorded multistart entries and policy. One rule, two callers.

    The route builds its verdict with this, and a record read back is held to it, so the uniqueness a record states
    cannot disagree with the starts it lists.
    """
    if not entries:
        return "NOT_ASSESSED", set(), {RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED}
    classes = [entry.get("classification") for entry in entries]
    converged = sum(1 for entry in entries if entry.get("status") == CalibrationStatus.CONVERGED.value)
    # a start that did not converge looked nowhere, so the minimum search is a minimum number of CONVERGED refits
    # (audit R-08). The rule was `converged * 2 < len(entries)`, under which half the starts could fail silently.
    incomplete = converged < _minimum_starts(p)
    if all(key in thresholds for key in _MULTISTART_POLICY_KEYS):
        below = bool(_search_shortfalls(thresholds, p))
    else:
        # A record written before the policy was recorded: the starts it lists are the search it ran.
        below = len(entries) < _minimum_starts(p)
    refusals, downgrades = set(), set()
    if "BETTER_OPTIMUM" in classes:
        refusals.add(RouteReason.BETTER_OPTIMUM_FOUND)
    if "SECOND_MODE" in classes:
        refusals.add(RouteReason.SECOND_MODE_FOUND)
    if "LOWER_OBJECTIVE_SAME_BASIN" in classes:
        refusals.add(RouteReason.NOT_A_LOCAL_MINIMUM)
    if incomplete or below:
        downgrades.add(RouteReason.MULTISTART_INCOMPLETE)
    # a policy below the minimum search is named before a refit that failed: it is the more specific fact, and it is
    # the reason the converged count cannot reach the minimum in the first place. Both downgrade, above.
    uniqueness = ("BETTER_OPTIMUM_FOUND" if "BETTER_OPTIMUM" in classes else "SECOND_MODE_FOUND" if "SECOND_MODE" in classes
                  else "LOWER_OBJECTIVE_SAME_BASIN" if "LOWER_OBJECTIVE_SAME_BASIN" in classes
                  else "MULTISTART_BELOW_MINIMUM_SEARCH" if below else "MULTISTART_INCOMPLETE" if incomplete
                  else "MULTISTART_NO_SECOND_MODE")
    return uniqueness, refusals, downgrades


# ---------------------------------------------------------------------------
# multistart
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MultistartPolicy:
    """A deterministic multistart. Halton points in the central part of the inference-space bounds box.

    A start the forward model refuses (outside its admissible region, which a bounds box does not describe) is
    REPLACED by the next unused point of the same Halton sequence, at most ``maximum_retractions`` times, from
    one counter shared by every start so no two take the same replacement. The number of replacements is
    recorded per start; a start with no admissible replacement is recorded as such and does not count as
    converged.

    It was retracted toward the calibrated estimate instead, halving the distance each time, so a start
    retracted k times searched 2 ** -k of its intended span -- up to 1 / 4096 -- and still counted as a full
    start (audit R-18). ``maximum_retractions`` keeps its name and its value as the replacement budget.
    """

    starts: int = 6
    scheme: str = "halton_in_inference_bounds"
    interior_fraction: float = 0.8
    max_evaluations: int = 2000
    mode_separation_quantile: float = 0.999
    comparable_fit_quantile: float = 0.99
    maximum_retractions: int = 12

    def __post_init__(self) -> None:
        if int(self.starts) < 1:
            raise HybridUQError("a multistart needs at least one start")
        if self.scheme != "halton_in_inference_bounds":
            raise HybridUQError(f"unknown multistart scheme {self.scheme!r}")
        if not 0.0 < float(self.interior_fraction) <= 1.0:
            raise HybridUQError("interior_fraction must lie in (0, 1]")
        if int(self.max_evaluations) < 1:
            raise HybridUQError("max_evaluations must be positive")
        if int(self.maximum_retractions) < 0:
            raise HybridUQError("maximum_retractions must be non-negative")
        for label in ("mode_separation_quantile", "comparable_fit_quantile"):
            if not 0.0 < float(getattr(self, label)) < 1.0:
                raise HybridUQError(f"{label} must lie in (0, 1)")

    def _point(self, parameter_set: CalibrationParameterSet, index: int) -> tuple[float, ...]:
        """The ``index``-th point of this policy's Halton sequence, in natural units. ``index`` starts at 1.

        ``start_points`` is this for 1 .. ``starts``. A refused start is replaced by the next unused index, so a
        replacement is another point of the same sequence over the same span, not a point pulled toward the estimate.
        """
        transforms = transforms_of(parameter_set)
        lower, upper = inference_bounds(parameter_set)
        margin = 0.5 * (1.0 - float(self.interior_fraction))
        u = np.asarray([_radical_inverse(int(index), _prime(d)) for d in range(len(lower))])
        z = lower + (margin + float(self.interior_fraction) * u) * (upper - lower)
        return tuple(float(v) for v in to_natural(z, transforms))

    def start_points(self, parameter_set: CalibrationParameterSet) -> tuple[tuple[float, ...], ...]:
        """Starts in natural units. The same parameter set always gets the same starts."""
        return tuple(self._point(parameter_set, index) for index in range(1, int(self.starts) + 1))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MULTISTART_POLICY_SCHEMA, "starts": int(self.starts), "scheme": self.scheme,
                "interior_fraction": float(self.interior_fraction), "max_evaluations": int(self.max_evaluations),
                "mode_separation_quantile": float(self.mode_separation_quantile),
                "comparable_fit_quantile": float(self.comparable_fit_quantile),
                "maximum_retractions": int(self.maximum_retractions)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MultistartPolicy":
        require_schema(payload, MULTISTART_POLICY_SCHEMA)
        return cls(starts=int(payload["starts"]), scheme=payload["scheme"], interior_fraction=float(payload["interior_fraction"]),
                   max_evaluations=int(payload["max_evaluations"]),
                   mode_separation_quantile=float(payload["mode_separation_quantile"]),
                   comparable_fit_quantile=float(payload["comparable_fit_quantile"]),
                   maximum_retractions=int(payload["maximum_retractions"]))

    @property
    def digest(self) -> str:
        return digest_of(self.to_dict())


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RouteDiagnostics:
    """Whether the local route's assumptions hold, measured. Not whether the parameters are identifiable."""

    parameters: int
    observations: int
    jacobian_rank: int
    jacobian_condition: float
    raw_jacobian_condition: float
    newton_step_in_sd: tuple[float, ...]
    at_bound: tuple[str, ...]
    near_bound: tuple[str, ...]
    minimum_bound_distance_sd: float
    nonlinearity_index: float
    nonlinearity_probes_skipped: int
    minimum_chi_square_rise: float
    multistart: tuple[Mapping[str, Any], ...]
    uniqueness: str
    thresholds: Mapping[str, float]
    evaluation_count: int
    claim: RouteClaim
    refusals: tuple[RouteReason, ...]
    downgrades: tuple[RouteReason, ...]
    #: CORE-001: the chi-square at the estimate the goodness of fit is judged on. NaN only on an early refusal.
    chi_square_minimum: float = math.nan
    #: CORE-003: the smallest chi2 rise / r^2 over the evaluated tail probes; NaN when none was evaluated.
    minimum_tail_rise_ratio: float = math.nan
    #: CORE-003: tail probes inside the declared bounds that the forward evaluator refused.
    tail_probes_skipped: int = 0
    #: R-22(a) (re-audit 2026-09-16, I-14 part D): ``"<count>:<sha256>"`` over the observations this route
    #: was fitted to. `observations` above feeds the goodness of fit and NOTHING ELSE READ IT, so editing 10
    #: to 40 turned chi-square 30 from a DOWNGRADE on 10 degrees of freedom into a plausible fit on 38 and
    #: the record read back SUPPORTED. The count is repeated in the clear here so that the two can be
    #: compared without the observations; with them, `require_posterior_matches_observations` compares the
    #: digest. Empty only in a `route_diagnostics/2` payload. Appended, not inserted: the field order is
    #: frozen.
    observation_content_digest: str = ""
    #: CORE-001 / R-03: the leverage-weighted residual statistic sum_i H_ii r_i^2 the goodness of fit was also
    #: judged on. NaN when no leverage test ran (an early refusal, or a record written before the rule).
    leverage_weighted_chi_square: float = math.nan
    #: CORE-001 / R-03: (c1, c2, c3) of that statistic's exact null, which the p-value is derived from on read.
    #: Empty when no leverage test ran.
    leverage_null_cumulants: tuple[float, ...] = ()
    #: R-13 (re-audit 2026-09-16, I-08 part B): (lambda_min, lambda_max) of the whitened curvature matrix the
    #: nonlinearity index was judged on, or empty when fewer than two indices had a complete set of probes --
    #: and on every record written before the rule, which is why the derived checks are skipped when it is
    #: empty. `nonlinearity_index` must dominate max(|lambda_max - 1|, |1 - lambda_min|).
    curvature_eigenvalue_bounds: tuple[float, ...] = ()
    #: R-15: tail probes that reached a smaller radius than asked because the declared box stopped them, and
    #: were compared with the radius they DID reach.
    tail_probes_clipped: int = 0
    #: R-15: tail probes the declared box stopped inside PROBE_SD, where the +/-2 sd probes have already
    #: measured the rise against their own rule, so there is no tail left to measure. Downgrades.
    tail_probes_outside_bounds: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim", RouteClaim(self.claim))
        refusals = tuple(sorted({RouteReason(r) for r in self.refusals}, key=lambda r: r.value))
        downgrades = tuple(sorted({RouteReason(r) for r in self.downgrades}, key=lambda r: r.value))
        if any(r.severity is not RouteClaim.REFUSED for r in refusals):
            raise HybridUQError("a downgrade reason cannot be recorded as a refusal")
        if any(r.severity is not RouteClaim.DOWNGRADED for r in downgrades):
            raise HybridUQError("a refusal reason cannot be recorded as a downgrade")
        if self.claim is not claim_for(refusals + downgrades):
            raise HybridUQError(f"claim {self.claim.value} does not follow from its reasons")
        object.__setattr__(self, "refusals", refusals)
        object.__setattr__(self, "downgrades", downgrades)
        object.__setattr__(self, "newton_step_in_sd", tuple(float(v) for v in self.newton_step_in_sd))
        object.__setattr__(self, "at_bound", tuple(self.at_bound))
        object.__setattr__(self, "near_bound", tuple(self.near_bound))
        # Frozen at construction (audit HUQ-13): a validated record's nested mappings cannot be edited in place.
        object.__setattr__(self, "multistart", tuple(freeze(dict(m)) for m in self.multistart))
        object.__setattr__(self, "leverage_null_cumulants", tuple(float(c) for c in self.leverage_null_cumulants))
        if self.leverage_null_cumulants and len(self.leverage_null_cumulants) != 3:
            raise HybridUQError("a leverage null is (c1, c2, c3) or absent")
        object.__setattr__(self, "curvature_eigenvalue_bounds",
                           tuple(float(v) for v in self.curvature_eigenvalue_bounds))
        bounds = self.curvature_eigenvalue_bounds
        if bounds and (len(bounds) != 2 or not all(math.isfinite(v) for v in bounds) or bounds[0] > bounds[1]):
            raise HybridUQError(
                "the curvature extremes are (lambda_min, lambda_max), two finite numbers in order, or absent")
        object.__setattr__(self, "thresholds", freeze({str(k): float(v) for k, v in dict(self.thresholds).items()}))
        _require_reasons_follow_measurements(self)

    @property
    def reasons(self) -> tuple[RouteReason, ...]:
        return self.refusals + self.downgrades

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": ROUTE_DIAGNOSTICS_SCHEMA, "parameters": int(self.parameters), "observations": int(self.observations),
            "jacobian_rank": int(self.jacobian_rank), "jacobian_condition": encode_float(self.jacobian_condition),
            "raw_jacobian_condition": encode_float(self.raw_jacobian_condition),
            "newton_step_in_sd": encode_vector(self.newton_step_in_sd), "at_bound": list(self.at_bound),
            "near_bound": list(self.near_bound), "minimum_bound_distance_sd": encode_float(self.minimum_bound_distance_sd),
            "nonlinearity_index": encode_float(self.nonlinearity_index),
            "nonlinearity_probes_skipped": int(self.nonlinearity_probes_skipped),
            "minimum_chi_square_rise": encode_float(self.minimum_chi_square_rise),
            "multistart": [_encode_start(m) for m in self.multistart], "uniqueness": self.uniqueness,
            "thresholds": {k: encode_float(v) for k, v in sorted(self.thresholds.items())},
            "evaluation_count": int(self.evaluation_count), "claim": self.claim.value,
            "refusals": [r.value for r in self.refusals], "downgrades": [r.value for r in self.downgrades],
            "chi_square_minimum": encode_float(self.chi_square_minimum),
            "minimum_tail_rise_ratio": encode_float(self.minimum_tail_rise_ratio),
            "tail_probes_skipped": int(self.tail_probes_skipped),
            "observation_content_digest": str(self.observation_content_digest),
        }
        # R-13 / R-15: written only when they carry information. A record that carried an empty extremes list
        # or a zero count would say a rule was applied where nothing was measured, and would also change the
        # bytes of every record that predates the rule.
        if self.curvature_eigenvalue_bounds:
            payload["curvature_eigenvalue_bounds"] = encode_vector(self.curvature_eigenvalue_bounds)
        if self.tail_probes_clipped:
            payload["tail_probes_clipped"] = int(self.tail_probes_clipped)
        if self.tail_probes_outside_bounds:
            payload["tail_probes_outside_bounds"] = int(self.tail_probes_outside_bounds)
        if math.isfinite(self.leverage_weighted_chi_square) or self.leverage_null_cumulants:
            # written only when a leverage test ran: a record that carries the key and not the measurement
            # would say the rule was applied where it was not
            payload["leverage_weighted_chi_square"] = encode_float(self.leverage_weighted_chi_square)
            payload["leverage_null_cumulants"] = encode_vector(self.leverage_null_cumulants)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteDiagnostics":
        schema = payload.get("schema") if isinstance(payload, Mapping) else None
        legacy = schema == ROUTE_DIAGNOSTICS_SCHEMA_V1
        if not legacy and schema != ROUTE_DIAGNOSTICS_SCHEMA_V2:
            require_schema(payload, ROUTE_DIAGNOSTICS_SCHEMA)
            # Unconditional under this schema, which is what the bump is FOR: the field is written whether or
            # not it "carries information", so a reader never has to wonder whether its absence means an old
            # record or an edited one (I-14, R-22(a)).
            if not str(payload.get("observation_content_digest", "")):
                raise HybridUQError(
                    f"a {ROUTE_DIAGNOSTICS_SCHEMA} record carries the content digest of the observations it "
                    f"was fitted to; without it the observation count is bound to nothing")
        added = {} if legacy else {
            "chi_square_minimum": decode_float(payload["chi_square_minimum"]),
            "minimum_tail_rise_ratio": decode_float(payload["minimum_tail_rise_ratio"]),
            "tail_probes_skipped": int(payload["tail_probes_skipped"]),
            # Absent in a `/2` payload, which is readable and whose `observations` field is therefore
            # unbound -- see ROUTE_DIAGNOSTICS_SCHEMA_V2.
            "observation_content_digest": str(payload.get("observation_content_digest", "")),
        }
        # absent for any record written before the leverage test existed: such a record is held to the pooled
        # test alone, which is what its own numbers support
        if "leverage_weighted_chi_square" in payload:
            added["leverage_weighted_chi_square"] = decode_float(payload["leverage_weighted_chi_square"])
            added["leverage_null_cumulants"] = decode_vector(payload.get("leverage_null_cumulants", []))
        # absent on every record written before I-08 part B, which derives nothing from them
        if "curvature_eigenvalue_bounds" in payload:
            added["curvature_eigenvalue_bounds"] = decode_vector(payload["curvature_eigenvalue_bounds"])
        if "tail_probes_clipped" in payload:
            added["tail_probes_clipped"] = int(payload["tail_probes_clipped"])
        if "tail_probes_outside_bounds" in payload:
            added["tail_probes_outside_bounds"] = int(payload["tail_probes_outside_bounds"])
        return cls(**added,
            parameters=int(payload["parameters"]), observations=int(payload["observations"]),
            jacobian_rank=int(payload["jacobian_rank"]), jacobian_condition=decode_float(payload["jacobian_condition"]),
            raw_jacobian_condition=decode_float(payload["raw_jacobian_condition"]),
            newton_step_in_sd=decode_vector(payload["newton_step_in_sd"]), at_bound=tuple(payload["at_bound"]),
            near_bound=tuple(payload["near_bound"]), minimum_bound_distance_sd=decode_float(payload["minimum_bound_distance_sd"]),
            nonlinearity_index=decode_float(payload["nonlinearity_index"]),
            nonlinearity_probes_skipped=int(payload["nonlinearity_probes_skipped"]),
            minimum_chi_square_rise=decode_float(payload["minimum_chi_square_rise"]),
            multistart=tuple(_decode_start(m) for m in payload["multistart"]), uniqueness=payload["uniqueness"],
            thresholds={k: decode_float(v) for k, v in payload["thresholds"].items()},
            evaluation_count=int(payload["evaluation_count"]), claim=RouteClaim(payload["claim"]),
            refusals=tuple(RouteReason(r) for r in payload["refusals"]), downgrades=tuple(RouteReason(r) for r in payload["downgrades"]),
        )

    @property
    def digest(self) -> str:
        return digest_of(material(self.to_dict(), ("evaluation_count",)))


#: Refusals the route records before it measures anything else: the record holds no step, probe or multistart.
_EARLY_REFUSALS = frozenset({
    RouteReason.CALIBRATION_NOT_CONVERGED, RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE,
    RouteReason.NO_RESIDUAL_DEGREES_OF_FREEDOM, RouteReason.STRUCTURALLY_UNIDENTIFIABLE,
    RouteReason.NUMERICALLY_SINGULAR_JACOBIAN,
})
_CLASSIFICATIONS = frozenset({"SAME_OPTIMUM", "LOWER_OBJECTIVE_SAME_BASIN", "BETTER_OPTIMUM", "SECOND_MODE", "WORSE_LOCAL_OPTIMUM"})


def _same(a: float, b: float) -> bool:
    a, b = float(a), float(b)
    return (math.isnan(a) and math.isnan(b)) or a == b or math.isclose(a, b, rel_tol=1e-12, abs_tol=0.0)


def _require_reasons_follow_measurements(d: "RouteDiagnostics") -> None:
    """Re-derive every route reason from the measured diagnostics under the canonical thresholds (audit HUQ-09).

    ``claim`` following from the listed reasons is not enough: a record listing no reasons over a nonlinearity of 7.5,
    a rank-deficient Jacobian or an empty multistart said SUPPORTED and was read back. This applies the route's own
    rules to the numbers the record carries -- rank, conditioning, the Newton step, bound membership, the probes and
    the multistart entries and policy -- and refuses a record whose reasons are not exactly the ones they imply. The
    thresholds must be the canonical ones: they are declared constants, not a caller's choice. Digests over these
    records are integrity-only; this is what makes the claim authoritative. What the record does not carry (the
    Jacobian, the estimate's own chi-square) cannot be re-derived, and a refit's classification is checked against
    the separation radius only where the policy is recorded.
    """
    problems: list[str] = []
    p, n = int(d.parameters), int(d.observations)
    canonical = _thresholds()
    thresholds = dict(d.thresholds)
    for key, value in canonical.items():
        if key not in thresholds or not _same(thresholds[key], value):
            problems.append(f"threshold {key} is {thresholds.get(key)!r}, not the declared {value!r}")
    unknown = sorted(set(thresholds) - set(canonical) - set(_MULTISTART_POLICY_KEYS))
    if unknown:
        problems.append(f"unknown thresholds {unknown}")
    policy_keys = set(thresholds) & set(_MULTISTART_POLICY_KEYS)
    if policy_keys and policy_keys != set(_MULTISTART_POLICY_KEYS):
        problems.append("a partial multistart policy")
    # THE OBSERVATION COUNT IS BOUND TO SOMETHING (I-14, R-22(a)).
    #
    # `observations` feeds `_goodness_of_fit` and nothing else read it, so no other field disagreed with an
    # edit: raising 10 to 40 turned chi-square 30 from a DOWNGRADE on 10 degrees of freedom into a plausible
    # fit on 38, and the record read back SUPPORTED. The digest repeats the count in the clear precisely so
    # that this comparison is possible WITHOUT the observations; with them,
    # `require_posterior_matches_observations` compares the digest itself.
    carried = str(d.observation_content_digest)
    if carried:
        head, _, rest = carried.partition(":")
        if not (head.isdigit() and len(rest) == 64 and all(c in "0123456789abcdef" for c in rest)):
            problems.append(f"an observation content digest is '<count>:<sha256>'; this record carries {carried!r}")
        elif int(head) != n:
            problems.append(
                f"the record says {n} observation(s) and its observation content digest was taken over "
                f"{int(head)}; the count is what the goodness of fit is judged against")
    # An EMPTY digest is the `/2` shape and is indistinguishable from it here, so whether one is REQUIRED is
    # a question about the payload's schema and is answered in `from_dict`, where the schema is visible.
    refusals, downgrades, optional = set(), set(), set()
    early = set(d.refusals) & _EARLY_REFUSALS
    if p < 1:
        problems.append("no parameters")
    if early:
        reason = sorted(early, key=lambda r: r.value)[0]
        refusals.add(reason)
        if d.newton_step_in_sd or d.at_bound or d.near_bound or d.multistart or d.uniqueness != "NOT_ASSESSED" \
                or int(d.nonlinearity_probes_skipped) != 0 or policy_keys:
            problems.append(f"{reason.value} is recorded before any step, probe or multistart, yet the record carries them")
        if not all(math.isnan(float(v)) for v in (d.minimum_bound_distance_sd, d.nonlinearity_index, d.minimum_chi_square_rise,
                                                 d.chi_square_minimum, d.minimum_tail_rise_ratio,
                                                 d.leverage_weighted_chi_square)) \
                or int(d.tail_probes_skipped) != 0 or tuple(d.leverage_null_cumulants):
            problems.append(f"{reason.value} measures no bound distance, nonlinearity, chi-square rise, goodness of fit or tail")
        rank, condition = int(d.jacobian_rank), float(d.jacobian_condition)
        if reason is RouteReason.NO_RESIDUAL_DEGREES_OF_FREEDOM and not p >= n:
            problems.append(f"{p} parameter(s) and {n} observation(s) leave residual degrees of freedom")
        if reason is RouteReason.STRUCTURALLY_UNIDENTIFIABLE and not rank < p:
            problems.append(f"a Jacobian of rank {rank} for {p} parameter(s) is not structurally unidentifiable")
        if reason is RouteReason.NUMERICALLY_SINGULAR_JACOBIAN and not (n > p and rank == p and condition > NUMERICAL_CONDITION_LIMIT):
            problems.append(f"condition {condition:.3g} at rank {rank} is not a numerically singular Jacobian")
        if reason in (RouteReason.CALIBRATION_NOT_CONVERGED, RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE) and rank != 0:
            problems.append(f"{reason.value} has no Jacobian, yet a rank of {rank} is recorded")
    else:
        rank, condition, raw = int(d.jacobian_rank), float(d.jacobian_condition), float(d.raw_jacobian_condition)
        if not n > p:
            problems.append(f"{p} parameter(s) and {n} observation(s) would have refused NO_RESIDUAL_DEGREES_OF_FREEDOM")
        if rank != p:
            problems.append(f"a Jacobian of rank {rank} for {p} parameter(s) would have refused")
        if not condition <= NUMERICAL_CONDITION_LIMIT:
            problems.append(f"a Jacobian condition of {condition:.3g} would have refused")
        # R-26: was `raw > NUMERICAL_CONDITION_LIMIT or isnan(raw)`, which made a unit choice a claim and a
        # missing diagnostic a downgrade. The scaling downgrade now follows from the equilibrated condition, and
        # a non-refused record without its raw condition is refused as a record that does not carry a number it
        # claims to record -- the route computes it on every non-refused path.
        if condition > POORLY_SCALED_CONDITION_LIMIT:
            downgrades.add(RouteReason.POORLY_SCALED_PARAMETERIZATION)
        if math.isnan(raw):
            problems.append("the raw Jacobian condition is not recorded")
        step = np.asarray(d.newton_step_in_sd, dtype=np.float64)
        if step.shape != (p,) or not np.all(np.isfinite(step)):
            problems.append(f"a Newton step of {len(step)} finite entries is required for {p} parameter(s)")
        moved = bool(np.any(np.abs(step) > STATIONARITY_SD)) if step.size else False
        if d.at_bound:
            refusals.add(RouteReason.PARAMETER_AT_BOUND)
            if not moved:
                problems.append("a parameter is recorded at a bound the Newton step does not push against")
        elif moved:
            refusals.add(RouteReason.NOT_STATIONARY)
        distance = float(d.minimum_bound_distance_sd)
        if set(d.at_bound) & set(d.near_bound):
            problems.append("a parameter is recorded both at and near a bound")
        if d.near_bound:
            downgrades.add(RouteReason.BOUND_WITHIN_3_SD)
            if not distance < BOUND_DOWNGRADE_SD:
                problems.append(f"near_bound is recorded with a minimum bound distance of {distance:.3g} sd")
        elif not d.at_bound and not distance >= BOUND_DOWNGRADE_SD:
            problems.append(f"a minimum bound distance of {distance:.3g} sd names no parameter near a bound")
        skipped, index, rise = int(d.nonlinearity_probes_skipped), float(d.nonlinearity_index), float(d.minimum_chi_square_rise)
        total = 2 * p * p
        if not 0 <= skipped <= total:
            problems.append(f"{skipped} probes skipped of {total}")
        if skipped:
            downgrades.add(RouteReason.NONLINEARITY_PROBE_INCOMPLETE)
        if math.isnan(rise) or (math.isinf(rise) and rise < 0):
            problems.append("a measured route records a chi-square rise")
        if (math.isinf(rise) or total - skipped < p) and not math.isnan(index):
            problems.append(f"fewer probes than parameters were evaluated, so the nonlinearity {index!r} was not measured")
        if index < 0.0:
            problems.append("a negative nonlinearity index")
        if math.isfinite(index) and math.isfinite(rise) and index < abs(rise / PROBE_SD ** 2 - 1.0) - 1e-12:
            problems.append(f"a nonlinearity index of {index:.3g} is below the rise {rise:.3g} it was measured from")
        if math.isnan(index) or index > NONLINEARITY_REFUSE:
            refusals.add(RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN)
        elif index > NONLINEARITY_DOWNGRADE:
            downgrades.add(RouteReason.NONLINEAR_WITHIN_2_SD)
        if rise < -1e-9:
            # the route's roundoff allowance scales with a chi-square the record does not carry
            optional.add(RouteReason.NOT_A_LOCAL_MINIMUM)
        chi_minimum = float(d.chi_square_minimum)
        if not (math.isfinite(chi_minimum) and chi_minimum >= 0.0):
            problems.append("a measured route records the chi-square minimum its goodness of fit is judged on; this record "
                            f"carries {chi_minimum!r} (a {ROUTE_DIAGNOSTICS_SCHEMA_V1} record never assessed it)")
        else:
            statistic, cumulants = float(d.leverage_weighted_chi_square), tuple(d.leverage_null_cumulants)
            if bool(cumulants) != math.isfinite(statistic):
                problems.append("a leverage-weighted chi-square is recorded with the null it was judged against, or "
                                "neither is")
            elif cumulants and not (statistic >= 0.0 and all(math.isfinite(c) and c >= 0.0 for c in cumulants)):
                # a null whose cumulants are ZERO is legitimate and is recorded: it happens when one observation
                # holds all the leverage, so its fitted residual has variance 1 - h = 0 and there is no test to
                # run. `_goodness_of_fit` then uses the pooled test alone, which is what the numbers support.
                problems.append(f"a leverage test needs a non-negative statistic and a non-negative null; this "
                                f"record carries {statistic!r} against {cumulants!r}")
            elif cumulants and statistic > chi_minimum * (1.0 + 1.0e-9) + 1.0e-9:
                # every leverage weight is a hat-matrix diagonal, so 0 <= h_i <= 1 and T = sum h_i r_i^2 can never
                # exceed sum r_i^2. A record whose two statistics break that inequality is not one fit's numbers.
                problems.append(f"a leverage-weighted chi-square of {statistic:.6g} exceeds the chi-square minimum "
                                f"{chi_minimum:.6g} it weighs a subset of")
            elif cumulants and cumulants[0] > p * (1.0 + 1.0e-9) + 1.0e-9:
                # c1 = sum h - sum h^2 <= sum h = rank(A) <= p
                problems.append(f"a leverage null mean of {cumulants[0]:.6g} exceeds the {p} parameter(s) the "
                                f"leverage weights sum to")
            found_refusals, found_downgrades = _goodness_of_fit(chi_minimum, n, p, statistic, cumulants)
            refusals |= found_refusals
            downgrades |= found_downgrades
        tail_skipped, tail_ratio = int(d.tail_probes_skipped), float(d.minimum_tail_rise_ratio)
        # R-14 widened the tail direction set from p to p^2 + 2, so the bound on every tail count widens with
        # it. Widening an upper bound cannot refuse a record that satisfied the narrower one.
        tail_probe_budget = 2 * len(TAIL_PROBE_SD) * (p * p + 2)
        if not 0 <= tail_skipped <= tail_probe_budget:
            problems.append(f"{tail_skipped} tail probes skipped of {tail_probe_budget}")
        clipped, outside = int(d.tail_probes_clipped), int(d.tail_probes_outside_bounds)
        if not 0 <= clipped <= tail_probe_budget or not 0 <= outside <= tail_probe_budget:
            problems.append(f"{clipped} clipped and {outside} out-of-bounds tail probes of {tail_probe_budget}")
        if tail_skipped:
            downgrades.add(RouteReason.NONLINEARITY_PROBE_INCOMPLETE)
        if outside:
            downgrades.add(RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS)
        # R-13: the index must account for the matrix the record says it was judged on.
        bounds = tuple(d.curvature_eigenvalue_bounds)
        if bounds:
            index = float(d.nonlinearity_index)
            implied = max(abs(bounds[1] - 1.0), abs(1.0 - bounds[0]))
            if not (math.isnan(index) or index >= implied - 1.0e-9 * max(1.0, implied)):
                problems.append(
                    f"a nonlinearity index of {index:.6g} is below the {implied:.6g} its own curvature "
                    f"extremes {bounds} imply")
        if math.isinf(tail_ratio):
            problems.append("a tail rise ratio is finite, or NaN when no tail probe was evaluated")
        # AND NaN NEEDS THE REASON NO PROBE WAS EVALUATED (I-14, R-22(d)).
        #
        # The sentence above was already the rule; nothing enforced its second half. The route writes NaN in
        # exactly one situation -- no probe evaluated -- which it records by a non-zero skip count, and the
        # reasons a probe is not evaluated are a bound reached or approached. So NaN with zero skips and no
        # bound is a combination the route cannot produce, and it read back SUPPORTED with no reasons at all.
        if math.isnan(tail_ratio) and not (tail_skipped or d.near_bound or d.at_bound):
            problems.append(
                "a tail rise ratio of NaN says no tail probe was evaluated, and this record skipped none "
                "and reports no parameter at or near a bound; the route cannot produce that combination")
        found_refusals, found_downgrades = _tail_verdict(tail_ratio)
        refusals |= found_refusals
        downgrades |= found_downgrades
        entries = tuple(d.multistart)
        if not entries and policy_keys:
            problems.append("a multistart policy is recorded with no starts")
        # AND ITS CONVERSE (I-14, R-22(c)).
        #
        # With NO policy key at all the record counted as pre-policy, and two checks below stopped running:
        # the canonical-span check, and the separation-radius check on every classification. So removing the
        # seven `multistart_*` keys from a genuinely DOWNGRADED narrow search -- and editing the four fields
        # that are re-derived from them -- read back ACCEPTED, claim SUPPORTED, reasons []. A pre-policy
        # `route_diagnostics/2` record CANNOT EXIST: the schema and the policy record were introduced
        # together, so such a payload is not an old record but an edited one. A `/1` record is unaffected,
        # being already refused for carrying any multistart at all.
        if entries and policy_keys != set(_MULTISTART_POLICY_KEYS):
            problems.append(
                f"{len(entries)} multistart start(s) are recorded under an incomplete policy "
                f"({sorted(policy_keys)}); this schema postdates the policy record, so a record that lists "
                f"starts carries the policy they were drawn under -- without it the canonical-span and "
                f"separation-radius checks cannot run")
        if policy_keys == set(_MULTISTART_POLICY_KEYS):
            if int(thresholds["multistart_starts"]) != len(entries):
                problems.append(f"the policy asked for {int(thresholds['multistart_starts'])} start(s) and {len(entries)} are recorded")
            if int(thresholds["multistart_minimum_starts"]) != _minimum_starts(p):
                problems.append("the recorded minimum search is not the minimum for this dimension")
        separation = (float(chi2.ppf(thresholds["multistart_mode_separation_quantile"], p))
                      if policy_keys == set(_MULTISTART_POLICY_KEYS) else None)
        for entry in entries:
            status, classification = entry.get("status"), entry.get("classification")
            if status == CalibrationStatus.CONVERGED.value:
                m2, chi = entry.get("mahalanobis_sq"), entry.get("chi_square")
                if classification not in _CLASSIFICATIONS or not isinstance(m2, float) or not isinstance(chi, float) \
                        or not (math.isfinite(m2) and m2 >= 0.0 and math.isfinite(chi)):
                    problems.append("a converged start without a classification, a finite distance and a finite chi-square")
                elif separation is not None and (m2 > separation) != (classification in ("BETTER_OPTIMUM", "SECOND_MODE", "WORSE_LOCAL_OPTIMUM")):
                    problems.append(f"a start {m2:.3g} from the estimate is classified {classification}")
                elif separation is not None and classification in ("SECOND_MODE", "WORSE_LOCAL_OPTIMUM"):
                    # the classification is worth nothing if a record can carry the word without the mass it
                    # follows from. A record with no policy (separation is None) predates the rule and the ratio.
                    ratio, unavailable = entry.get("laplace_mass_ratio"), entry.get("laplace_mass_unavailable")
                    if ratio is None and isinstance(unavailable, str) and unavailable and classification == "SECOND_MODE":
                        pass
                    elif not isinstance(ratio, float) or not math.isfinite(ratio) or ratio < 0.0:
                        problems.append(f"a separated start classified {classification} carries no finite non-negative "
                                        f"laplace_mass_ratio ({ratio!r})")
                    elif (ratio > MULTISTART_MASS_FLOOR) != (classification == "SECOND_MODE"):
                        problems.append(f"a separated start whose laplace_mass_ratio is {ratio:.3g} against a floor of "
                                        f"{MULTISTART_MASS_FLOOR:g} is classified {classification}")
            elif classification is not None:
                problems.append(f"a start that did not converge ({status}) carries a classification")
        uniqueness, found_refusals, found_downgrades = _multistart_verdict(entries, p, thresholds)
        if uniqueness != d.uniqueness:
            problems.append(f"uniqueness {d.uniqueness!r} does not follow from the starts, which say {uniqueness!r}")
        refusals |= found_refusals
        downgrades |= found_downgrades
    recorded_refusals, recorded_downgrades = set(d.refusals), set(d.downgrades)
    if not refusals <= recorded_refusals <= refusals | optional:
        problems.append(f"refusals {sorted(r.value for r in recorded_refusals)} are not the ones the measurements imply "
                        f"({sorted(r.value for r in refusals | optional)})")
    if recorded_downgrades != downgrades:
        problems.append(f"downgrades {sorted(r.value for r in recorded_downgrades)} are not the ones the measurements imply "
                        f"({sorted(r.value for r in downgrades)})")
    if problems:
        raise HybridUQError(f"the route diagnostics contradict their own measurements: {problems}")


def _encode_start(entry: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in entry.items():
        if isinstance(value, (list, tuple)):
            out[key] = encode_vector(value)
        elif isinstance(value, float):
            out[key] = encode_float(value)
        else:
            out[key] = value
    return out


def _decode_start(entry: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in entry.items():
        if isinstance(value, list):
            out[key] = decode_vector(value)
        elif key in ("chi_square", "mahalanobis_sq", "laplace_mass_ratio"):
            out[key] = decode_float(value)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# intervals and the posterior record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParameterInterval:
    """One marginal interval of an approximation, labelled with the approximation it came from."""

    name: str
    unit: str
    inference_transform: str
    estimate: float
    inference_standard_uncertainty: float
    lower: float
    upper: float
    confidence_level: float
    approximation_class: ApproximationClass

    def __post_init__(self) -> None:
        object.__setattr__(self, "approximation_class", ApproximationClass(self.approximation_class))
        if not 0.0 < float(self.confidence_level) < 1.0:
            raise HybridUQError("confidence_level must lie strictly between 0 and 1")
        if not (self.lower <= self.upper):
            raise HybridUQError("an interval's lower end exceeds its upper end")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": PARAMETER_INTERVAL_SCHEMA, "name": self.name, "unit": self.unit,
                "inference_transform": self.inference_transform, "estimate": encode_float(self.estimate),
                "inference_standard_uncertainty": encode_float(self.inference_standard_uncertainty),
                "lower": encode_float(self.lower), "upper": encode_float(self.upper),
                "confidence_level": float(self.confidence_level), "approximation_class": self.approximation_class.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParameterInterval":
        require_schema(payload, PARAMETER_INTERVAL_SCHEMA)
        return cls(name=payload["name"], unit=payload["unit"], inference_transform=payload["inference_transform"],
                   estimate=decode_float(payload["estimate"]),
                   inference_standard_uncertainty=decode_float(payload["inference_standard_uncertainty"]),
                   lower=decode_float(payload["lower"]), upper=decode_float(payload["upper"]),
                   confidence_level=float(payload["confidence_level"]),
                   approximation_class=ApproximationClass(payload["approximation_class"]))


def _magnitude(coefficient) -> float:
    if isinstance(coefficient, Quantity):
        return float(coefficient.magnitude)
    if isinstance(coefficient, bool) or not isinstance(coefficient, (int, float, np.integer, np.floating)):
        raise HybridUQError(f"a reparameterization coefficient is a number or a Quantity, not {type(coefficient).__name__}")
    return float(coefficient)


def _coefficient_in_output_unit(coefficient, source: str, output: str, row: str, column: str, terms: int) -> float:
    """The number that multiplies a ``source``-unit coordinate to give ``output`` units, or HybridUQError."""
    magnitude = _magnitude(coefficient)
    if not math.isfinite(magnitude):
        raise HybridUQError("a reparameterization matrix must be finite and of full row rank")
    if magnitude == 0.0:
        return 0.0
    unit = coefficient.units if isinstance(coefficient, Quantity) else "dimensionless"
    try:
        Quantity(1.0, output)
        ratio = is_ratio_scale(source) and is_ratio_scale(output) and is_ratio_scale(unit)
    except Exception as exc:  # an unknown unit string, reported in this package's terms
        raise HybridUQError(f"output {row!r}: {exc}") from None
    if not ratio:
        if terms == 1 and unit == "dimensionless" and magnitude == 1.0 and source == output:
            return 1.0
        raise HybridUQError(f"output {row!r} combines or scales {column!r} on an offset scale ({source} into {output}); "
                            f"only an unscaled copy of such a coordinate into its own unit has a meaning")
    term = Quantity(magnitude, unit) * Quantity(1.0, source)
    if not term.is_compatible_with(output):
        raise HybridUQError(f"output {row!r} in {output!r} is not compatible with its term in {column!r}: a coefficient in "
                            f"{unit!r} times a coordinate in {source!r} is {term.units!r}")
    return float(term.magnitude_in(output))


@dataclass(frozen=True)
class LocalGaussianPosterior:
    """A local Gaussian approximation of a posterior, with the diagnostics that decide whether to use it.

    ``covariance`` is in inference coordinates and is ``None`` when the route REFUSED: a refused route
    emits no numbers. It is never an exact posterior, and nothing on the record can say it is.
    """

    approximation_class: ApproximationClass
    parameter_names: tuple[str, ...]
    parameter_units: tuple[str, ...]
    inference_transforms: tuple[str, ...]
    parameterization: str
    parameterization_digest: str
    estimate: tuple[float, ...]
    inference_point: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...] | None
    lower_bounds: tuple[float, ...]
    upper_bounds: tuple[float, ...]
    diagnostics: RouteDiagnostics
    sensitivity_digest: str
    dataset_id: str
    #: R-12 (re-audit 2026-09-16, I-13 part A): the digest of the OBSERVATION CONTENT this posterior was
    #: calibrated on -- `digest_of(observations.to_dict())`, over the dataset id and every observation's
    #: condition id, observable, value, sigma, source ref and declared conditions with their units. A
    #: prediction that supplies `calibration_observations` is ASSERTING they are these, and
    #: `linearized_predictive_uq` refuses the assertion when it is false. Empty on a record written before the
    #: rule, and on a refused route, which emits no predictions anyway.
    calibration_content_digest: str = ""
    #: R-12 / R-31: the (name, unit) pairs of every condition EVERY calibration observation declares, sorted.
    #: The domain gate uses this design when the caller supplies no observations, so omitting them applies the
    #: check instead of silencing it.
    calibrated_conditions: tuple[tuple[str, str], ...] = ()
    #: R-31: one row of condition magnitudes per calibration observation, aligned with `calibrated_conditions`.
    #: The joint support the calibration covered, which is the convex hull of these rows -- not the box around
    #: them.
    calibrated_condition_points: tuple[tuple[float, ...], ...] = ()

    def __post_init__(self) -> None:
        cls = ApproximationClass(self.approximation_class)
        if cls is not ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION:
            raise HybridUQError(f"a LocalGaussianPosterior is a LOCAL_GAUSSIAN_APPROXIMATION, not {cls.value}")
        object.__setattr__(self, "approximation_class", cls)
        p = len(self.parameter_names)
        for label in ("parameter_names", "parameter_units", "inference_transforms"):
            object.__setattr__(self, label, tuple(str(v) for v in getattr(self, label)))
        for label in ("estimate", "inference_point", "lower_bounds", "upper_bounds"):
            object.__setattr__(self, label, tuple(float(v) for v in getattr(self, label)))
            if len(getattr(self, label)) != p:
                raise HybridUQError(f"{label} has {len(getattr(self, label))} entries for {p} parameter(s)")
        if len(self.parameter_units) != p or len(self.inference_transforms) != p:
            raise HybridUQError("names, units and transforms must agree in length")
        if not isinstance(self.diagnostics, RouteDiagnostics):
            raise HybridUQError("a LocalGaussianPosterior carries RouteDiagnostics")
        if self.diagnostics.claim is RouteClaim.REFUSED:
            if self.covariance is not None:
                raise HybridUQError("a REFUSED local route emits no covariance")
        else:
            if self.covariance is None:
                raise HybridUQError(f"a {self.diagnostics.claim.value} local route carries its covariance")
            cov = require_valid_covariance(self.covariance, p)
            object.__setattr__(self, "covariance", tuple(tuple(float(v) for v in row) for row in cov))
        if not str(self.parameterization).strip() or not str(self.parameterization_digest).strip():
            raise HybridUQError("a local posterior records its parameterization and its identity")
        # R-12 / R-31: the calibration design is frozen, and a design whose rows do not match its columns is
        # not a design. A record either carries the whole of it or none of it.
        object.__setattr__(self, "calibration_content_digest", str(self.calibration_content_digest))
        object.__setattr__(self, "calibrated_conditions",
                           tuple((str(name), str(unit)) for name, unit in self.calibrated_conditions))
        object.__setattr__(self, "calibrated_condition_points",
                           tuple(tuple(float(v) for v in row) for row in self.calibrated_condition_points))
        width = len(self.calibrated_conditions)
        if any(len(row) != width for row in self.calibrated_condition_points):
            raise HybridUQError("every calibrated condition row has one magnitude per declared condition")
        if bool(self.calibrated_condition_points) != bool(width):
            raise HybridUQError("a calibrated condition design is its names and its rows, or neither")
        if any(not math.isfinite(v) for row in self.calibrated_condition_points for v in row):
            raise HybridUQError("a calibrated condition magnitude must be finite")

    # -- reading ----------------------------------------------------------------
    @property
    def claim(self) -> RouteClaim:
        return self.diagnostics.claim

    @property
    def reasons(self) -> tuple[RouteReason, ...]:
        return self.diagnostics.reasons

    @property
    def exact_posterior(self) -> bool:
        return False

    def _require_numbers(self) -> np.ndarray:
        if self.covariance is None:
            raise RouteRefusedError(
                f"the local Gaussian route was REFUSED ({', '.join(r.value for r in self.diagnostics.refusals)}); "
                f"it has no covariance, intervals or identifiability to report")
        return np.asarray(self.covariance, dtype=np.float64)

    @property
    def standard_deviations(self) -> tuple[float, ...]:
        return tuple(float(v) for v in np.sqrt(np.diag(self._require_numbers())))

    @property
    def correlation(self) -> np.ndarray:
        cov = self._require_numbers()
        sd = np.sqrt(np.diag(cov))
        return cov / np.outer(sd, sd)

    def intervals(self, confidence_level: float = 0.95) -> tuple[ParameterInterval, ...]:
        cov = self._require_numbers()
        level = float(confidence_level)
        if not 0.0 < level < 1.0:
            raise HybridUQError("confidence_level must lie strictly between 0 and 1")
        q = float(norm.ppf(0.5 + level / 2.0))
        sd = np.sqrt(np.diag(cov))
        out = []
        for i, name in enumerate(self.parameter_names):
            z, t = self.inference_point[i], self.inference_transforms[i]
            if t == "linear_map":
                low, high = z - q * sd[i], z + q * sd[i]
            else:
                low, high = to_natural([z - q * sd[i]], [t])[0], to_natural([z + q * sd[i]], [t])[0]
            out.append(ParameterInterval(name=name, unit=self.parameter_units[i], inference_transform=t,
                                         estimate=self.estimate[i], inference_standard_uncertainty=float(sd[i]),
                                         lower=float(low), upper=float(high), confidence_level=level,
                                         approximation_class=self.approximation_class))
        return tuple(out)

    def reparameterized(self, matrix, names: Sequence[str], units: Sequence[str], label: str) -> "LocalGaussianPosterior":
        """The same Gaussian in linear combinations of the inference coordinates. A new parameterization identity.

        Units are part of the identity, so a linear combination must be dimensionally meaningful. Each inference
        coordinate has a unit: the declared unit for an ``identity`` parameter, ``dimensionless`` for a ``log``
        one (the coordinate is ln(value / declared unit), a pure number whose origin depends on that declared
        unit, which the parent identity records), and its own recorded unit for a ``linear_map`` one. A
        coefficient is a plain number, meaning dimensionless, or a :class:`Quantity` whose unit it carries. Every
        term of output row i, coefficient times coordinate, must be compatible with ``units[i]``, and is
        converted into it, so ``Quantity(1, "millivolt/volt")`` and ``1000`` against ``millivolt`` both scale a
        volt coordinate the same way. Offset units such as degrees Celsius are refused in any row except an
        unscaled copy of one coordinate into its own unit, because a sum on an interval scale has no meaning.
        """
        cov = self._require_numbers()
        rows = [list(row) for row in matrix]
        p = len(self.parameter_names)
        if not rows or any(len(row) != p for row in rows) or len(rows) != len(names) or len(units) != len(names):
            raise HybridUQError(f"a reparameterization of {p} coordinates needs a k x {p} matrix and k names and units")
        sources = [("dimensionless" if t == "log" else u) for t, u in zip(self.inference_transforms, self.parameter_units)]
        T = np.asarray([[_coefficient_in_output_unit(c, sources[j], str(units[i]), str(names[i]), self.parameter_names[j],
                                                     sum(1 for v in row if _magnitude(v) != 0.0))
                         for j, c in enumerate(row)] for i, row in enumerate(rows)], dtype=np.float64)
        if not np.all(np.isfinite(T)) or np.linalg.matrix_rank(T) != T.shape[0]:
            raise HybridUQError("a reparameterization matrix must be finite and of full row rank")
        text = str(label).strip()
        if not text:
            raise HybridUQError("a reparameterization needs a label")
        point = T @ np.asarray(self.inference_point)
        k = T.shape[0]
        identity = digest_of({"parent": self.parameterization_digest, "label": text, "matrix": encode_matrix(T.tolist()),
                              "names": list(map(str, names)), "units": list(map(str, units))})
        return LocalGaussianPosterior(
            approximation_class=self.approximation_class, parameter_names=tuple(map(str, names)),
            parameter_units=tuple(map(str, units)), inference_transforms=("linear_map",) * k,
            parameterization=f"linear_map:{text}", parameterization_digest=identity, estimate=tuple(point),
            inference_point=tuple(point), covariance=tuple(map(tuple, T @ cov @ T.T)),
            lower_bounds=(-math.inf,) * k, upper_bounds=(math.inf,) * k, diagnostics=self.diagnostics,
            sensitivity_digest=self.sensitivity_digest, dataset_id=self.dataset_id,
        )

    # -- records ----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LOCAL_GAUSSIAN_POSTERIOR_SCHEMA, "approximation_class": self.approximation_class.value,
            "exact_posterior": False, "parameter_names": list(self.parameter_names),
            "parameter_units": list(self.parameter_units), "inference_transforms": list(self.inference_transforms),
            "parameterization": self.parameterization, "parameterization_digest": self.parameterization_digest,
            "estimate": encode_vector(self.estimate), "inference_point": encode_vector(self.inference_point),
            "covariance": encode_matrix(self.covariance), "lower_bounds": encode_vector(self.lower_bounds),
            "upper_bounds": encode_vector(self.upper_bounds), "claim": self.claim.value,
            "diagnostics": self.diagnostics.to_dict(), "sensitivity_digest": self.sensitivity_digest,
            "dataset_id": self.dataset_id,
            # R-12 / R-31: written only when they carry information, so a record written before the rule keeps
            # its bytes and still reads back.
            **({"calibration_content_digest": self.calibration_content_digest}
               if self.calibration_content_digest else {}),
            **({"calibrated_conditions": [list(pair) for pair in self.calibrated_conditions],
                "calibrated_condition_points": [encode_vector(row) for row in self.calibrated_condition_points]}
               if self.calibrated_conditions else {}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LocalGaussianPosterior":
        require_schema(payload, LOCAL_GAUSSIAN_POSTERIOR_SCHEMA)
        if payload.get("exact_posterior") is not False:
            raise HybridUQError("a local Gaussian posterior record claiming to be exact is refused")
        diagnostics = RouteDiagnostics.from_dict(payload["diagnostics"])
        if payload.get("claim") != diagnostics.claim.value:
            raise HybridUQError("the record's claim disagrees with its diagnostics")
        posterior = cls(
            approximation_class=ApproximationClass(payload["approximation_class"]),
            parameter_names=tuple(payload["parameter_names"]), parameter_units=tuple(payload["parameter_units"]),
            inference_transforms=tuple(payload["inference_transforms"]), parameterization=payload["parameterization"],
            parameterization_digest=payload["parameterization_digest"], estimate=decode_vector(payload["estimate"]),
            inference_point=decode_vector(payload["inference_point"]), covariance=decode_matrix(payload["covariance"]),
            lower_bounds=decode_vector(payload["lower_bounds"]), upper_bounds=decode_vector(payload["upper_bounds"]),
            diagnostics=diagnostics, sensitivity_digest=payload["sensitivity_digest"], dataset_id=payload["dataset_id"],
            calibration_content_digest=payload.get("calibration_content_digest", ""),
            calibrated_conditions=tuple(tuple(pair) for pair in payload.get("calibrated_conditions", ())),
            calibrated_condition_points=tuple(
                tuple(decode_vector(row)) for row in payload.get("calibrated_condition_points", ())),
        )
        problems = _posterior_record_problems(posterior)
        if problems:
            raise HybridUQError(f"the local posterior record contradicts itself: {problems}")
        return posterior

    @property
    def digest(self) -> str:
        payload = self.to_dict()
        payload["diagnostics"] = self.diagnostics.digest
        return digest_of(payload)


def _posterior_record_problems(post: LocalGaussianPosterior) -> list[str]:
    """What a local posterior read back can be held to from its own fields (audits HUQ-09 and HUQ-12).

    Checked on read and wherever a routed result carries a posterior, not in the constructor, which tests and
    reparameterizations use to build deliberately partial posteriors. The estimate must be finite and map to the
    inference point exactly (a declared posterior's point is ``to_inference(estimate)``, a mapped one's is its
    estimate). For the declared parameterization, the carried covariance, point and bounds reproduce the minimum
    bound distance and the near-bound set the diagnostics recorded, and every at-bound parameter is at a bound: a
    covariance rescaled everywhere it appears keeps its digests but not those distances. The Jacobian is not carried,
    so a covariance with bounds infinitely far away cannot be re-derived: the sensitivity digest is integrity-only.
    """
    problems = []
    names, d = post.parameter_names, post.diagnostics
    if not all(math.isfinite(v) for v in post.estimate + post.inference_point):
        return ["the estimate and inference point must be finite"]
    if post.parameterization != "declared":
        if post.estimate != post.inference_point:
            problems.append("a linearly mapped posterior's point is its estimate")
        return problems
    if int(d.parameters) != len(names):
        problems.append(f"diagnostics for {d.parameters} parameter(s) on a posterior of {len(names)}")
        return problems
    try:
        expected = tuple(float(v) for v in to_inference(post.estimate, post.inference_transforms))
    except ValueError as exc:
        return [f"an inference transform is not a declared transform: {exc}"]
    if expected != post.inference_point:
        problems.append(f"the inference point {list(post.inference_point)} is not the estimate {list(post.estimate)} "
                        f"in its inference coordinates ({list(expected)})")
    z0 = np.asarray(post.inference_point)
    lower, upper = np.asarray(post.lower_bounds), np.asarray(post.upper_bounds)
    span = upper - lower
    for name in d.at_bound:
        if name not in names:
            problems.append(f"at_bound names {name!r}, which is not a parameter")
            continue
        i = names.index(name)
        if not ((z0[i] - lower[i]) <= AT_BOUND_RELATIVE * span[i] or (upper[i] - z0[i]) <= AT_BOUND_RELATIVE * span[i]):
            problems.append(f"{name!r} is recorded at a bound it is not at")
    if post.covariance is not None and d.newton_step_in_sd:
        sd = np.sqrt(np.diag(np.asarray(post.covariance, dtype=np.float64)))
        with np.errstate(divide="ignore", invalid="ignore"):
            distance = np.minimum(z0 - lower, upper - z0) / sd
        if not _same(float(np.min(distance)), d.minimum_bound_distance_sd):
            problems.append(f"the covariance and bounds put the nearest bound {float(np.min(distance)):.6g} sd away; the "
                            f"diagnostics measured {d.minimum_bound_distance_sd:.6g}")
        near = {names[i] for i in range(len(names)) if distance[i] < BOUND_DOWNGRADE_SD and names[i] not in d.at_bound}
        if near != set(d.near_bound):
            problems.append(f"the covariance and bounds put {sorted(near)} within {BOUND_DOWNGRADE_SD:g} sd of a bound; the "
                            f"diagnostics recorded {sorted(d.near_bound)}")
    return problems


# ---------------------------------------------------------------------------
# the route
# ---------------------------------------------------------------------------
def _invariant_basis(cov: "np.ndarray") -> tuple["np.ndarray", "np.ndarray"]:
    """The ``(lam, vec)`` pair whose scaled columns are the UNIT-INVARIANT unit-Mahalanobis probe axes (R-16).

    The route probed along ``sqrt(lam_k) * v_k`` from ``eigh(cov)`` in DECLARED units. Those directions have
    Mahalanobis length 1, but a covariance's eigenvectors ROTATE under a per-parameter unit change, so the
    tested directions moved with the units: the same model and data were SUPPORTED with a parameter in volts
    and REFUSED (TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN) in millivolts.

    The invariant basis is the CORRELATION eigenbasis scaled by the marginal standard deviations. With
    ``D = diag(sd)`` and ``R = D^-1 cov D^-1``, take ``mu_k, w_k = eigh(R)`` and return the pair whose scaled
    column is ``delta_k = sqrt(mu_k) * (sd * w_k)``. Two facts make it the right basis:

    * **It is the same points.** Under ``z -> S z`` for diagonal ``S`` -- a per-parameter unit change --
      ``cov -> S cov S`` and ``D -> S D``, so ``R`` is INVARIANT and ``w_k`` with it. Then
      ``delta_k -> S delta_k``: the direction set transforms covariantly, naming the same points in parameter
      space whatever unit each parameter is declared in.
    * **Its Mahalanobis length is exactly 1.** ``delta^T cov^-1 delta = mu_k * w_k^T (D cov^-1 D) w_k
      = mu_k * w_k^T R^-1 w_k = mu_k * (1 / mu_k) = 1``, so a Gaussian still predicts the same chi-square
      rise along every probe and ``PROBE_SD ** 2`` is still what it is compared with.

    For an UNCORRELATED posterior the two bases are identical -- ``R = I`` gives ``mu_k = 1`` and
    ``w_k = e_k``, so ``delta_k = sd_k e_k``, which is what ``sqrt(cov_kk) e_k`` already was. Only a
    correlated posterior's probes move, and they move to the invariant ones.

    Returned as a ``(lam, vec)`` pair rather than the directions themselves so ``_probe_directions`` keeps
    its signature and its meaning: it is handed the invariant basis instead of ``eigh(cov)``'s.
    """
    sd = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    safe = np.where(sd > 0.0, sd, 1.0)
    correlation = cov / np.outer(safe, safe)
    correlation = 0.5 * (correlation + correlation.T)
    mu, w = np.linalg.eigh(correlation)
    return mu, sd[:, None] * w


def _labelled_probe_directions(lam: np.ndarray, vec: np.ndarray) -> list[tuple[tuple, "np.ndarray"]]:
    """``(label, direction)`` for every probe, where the label says which entry of the curvature matrix it feeds.

    ``("axis", k)`` is the k-th unit-Mahalanobis axis; ``("plus", i, j)`` and ``("minus", i, j)`` are the two
    diagonals between axes i and j. R-13 rebuilds the whitened curvature matrix from exactly these, so the
    label is what ties a measured rise to the entry it determines -- without it the probe loop would have to
    re-derive which direction it was on from the numbers, which is how a matrix gets assembled out of the
    wrong probes.
    """
    # The direction list is built exactly as it always was -- the two diagonal lines below are pinned by the
    # mutation population (G33c) and are byte-identical -- and the labels are built beside it. Zipped rather
    # than appended in pairs so that removing the diagonals removes them from the RESULT too.
    scaled = [math.sqrt(max(float(lam[k]), 0.0)) * vec[:, k] for k in range(len(lam))]
    labels: list[tuple] = [("axis", k) for k in range(len(scaled))]
    directions = list(scaled)
    for i in range(len(scaled)):
        for j in range(i + 1, len(scaled)):
            labels.append(("plus", i, j))
            labels.append(("minus", i, j))
            directions.append((scaled[i] + scaled[j]) / math.sqrt(2.0))
            directions.append((scaled[i] - scaled[j]) / math.sqrt(2.0))
    return list(zip(labels, directions))


def _probe_directions(lam: np.ndarray, vec: np.ndarray) -> list[np.ndarray]:
    """Unit-Mahalanobis probe directions: every principal axis, then every diagonal between two of them.

    Each direction has Mahalanobis length 1, so a Gaussian predicts the same chi-square rise, PROBE_SD ** 2, along
    all of them. 2p + 2p(p - 1) probes in all: the diagonals are what see a cross term between two axes.
    """
    return [direction for _label, direction in _labelled_probe_directions(lam, vec)]


def _curvature_matrix(p: int, rises: Mapping[tuple, float]):
    """``(M, indices)``: the whitened curvature matrix rebuilt from the probes already paid for (R-13).

    THE PROBLEM. Each probed direction was bounded ALONE, against the Gaussian's ``PROBE_SD ** 2``. A
    curvature error spread over many pairs is small in every single direction and large in their sum: at
    p = 10 a residual curvature of -0.099 on every pair sat at index 0.0992 -- under the 0.10 downgrade --
    while along the equal-weight direction the true chi-square rise at 2, 3 and 6 reported sd was 0.5, 1.303
    and 9.068 against a Gaussian's 4, 9 and 36. The true standard deviation there was 2.24x the reported one.

    THE ARITHMETIC. For a local quadratic ``Q(u) = u^T M u`` in whitened coordinates, the axis probes give
    ``Q(+/-s e_k) = s^2 M_kk`` and the diagonals give
    ``Q(s (e_i +/- e_j)/sqrt(2)) = s^2 (M_ii + M_jj)/1 ... = s^2 ((M_ii + M_jj)/2 * 2 +/- 2 M_ij) / 1``, so
    with the two signs averaged over each direction::

        M_kk = mean_sign Q(+/- s e_k) / s^2
        M_ij = (Qbar_plus - Qbar_minus) / (2 s^2)

    where ``s = PROBE_SD``. No new forward evaluation: the axes and the diagonals between every pair already
    determine the form completely.

    AN INCOMPLETE MATRIX IS BUILT OVER WHAT IS COMPLETE. A probe beyond a declared bound or at an
    inadmissible point leaves an entry unmeasured, so the matrix is assembled over the largest index set
    whose axis probes AND all of whose pairwise diagonals were evaluated. A principal submatrix's extreme
    eigenvalues still bound the worst direction from below -- the supremum over unit directions supported on
    a subset is at most the supremum over all of them -- so the gate is never loosened by the restriction,
    only reduced in reach, and NONLINEARITY_PROBE_INCOMPLETE already says a probe was missed. Below two
    complete indices there is no matrix, and this returns ``None``.
    """
    square = PROBE_SD ** 2

    def averaged(label):
        values = [rises[(label, sign)] for sign in (1.0, -1.0) if (label, sign) in rises]
        return sum(values) / len(values) if len(values) == 2 else None

    diagonal = {k: averaged(("axis", k)) for k in range(p)}
    complete = [k for k in range(p) if diagonal[k] is not None]
    pairs: dict[tuple[int, int], float] = {}
    for i in complete:
        for j in complete:
            if j <= i:
                continue
            plus, minus = averaged(("plus", i, j)), averaged(("minus", i, j))
            if plus is None or minus is None:
                continue
            pairs[(i, j)] = (plus - minus) / (2.0 * square)
    # the largest index set every one of whose pairs is measured: drop an index at a time, worst first
    indices = list(complete)
    while len(indices) >= 2:
        missing = {k: sum(1 for i in indices for j in indices
                          if i < j and (i, j) not in pairs and k in (i, j)) for k in indices}
        worst = max(indices, key=lambda k: missing[k])
        if missing[worst] == 0:
            break
        indices.remove(worst)
    if len(indices) < 2:
        return None
    matrix = np.eye(len(indices))
    for a, i in enumerate(indices):
        matrix[a, a] = float(diagonal[i]) / square
        for b, j in enumerate(indices):
            if j > i:
                matrix[a, b] = matrix[b, a] = pairs[(i, j)]
    return 0.5 * (matrix + matrix.T), tuple(indices)


def _curvature_index(matrix: "np.ndarray") -> tuple[float, tuple[float, float]]:
    """``(index, (lambda_min, lambda_max))``: the SUPREMUM of the per-direction index, and the extremes it is.

    The per-direction index the route already thresholds is ``|Q(s d) / s^2 - 1| = |d^T M d - 1|`` for a unit
    whitened direction ``d``, and the supremum of a Rayleigh quotient's deviation from 1 over all unit
    directions is ``max(|lambda_max - 1|, |1 - lambda_min|)``. So this is the same quantity, maximized over
    every direction instead of evaluated at 2p^2 of them -- which is why it is compared with
    NONLINEARITY_DOWNGRADE and NONLINEARITY_REFUSE unchanged, and why it DOMINATES every per-direction index.
    """
    values = np.linalg.eigvalsh(np.asarray(matrix, dtype=float))
    low, high = float(values[0]), float(values[-1])
    return max(abs(high - 1.0), abs(1.0 - low)), (low, high)


def _tail_directions(lam: "np.ndarray", vec: "np.ndarray", matrix, indices) -> list["np.ndarray"]:
    """Every direction the +/-2 sd probes cover, plus the curvature matrix's two extreme eigenvectors (R-14).

    THE PROBLEM. The 3 and 6 sd tail probes ran along the p axes only. A posterior that is exactly Gaussian
    on both axes out to 6 sd and saturates along its diagonals beyond about 3 sd was SUPPORTED with no reason
    at all, and its 95% intervals held 76.8% of the marginal.

    WHY THESE DIRECTIONS. A tail probe asks whether the posterior is heavier than the reported Gaussian
    SOMEWHERE, and a heavy tail has to be looked for where the local quadratic is least trustworthy. The
    diagonals are where a cross term lives, which is why the +/-2 sd probes already cover them; the
    ``lambda_min`` direction is the one the curvature matrix says is flattest, which is where a saturating
    tail hides. A quasi-random sample of the sphere would be a different rule with a sample size to justify.

    The extreme eigenvectors are in whitened coordinates over ``indices``; they are mapped back by
    ``sum_k u_k delta_k``, which has Mahalanobis length 1 exactly because the ``delta_k`` are
    cov-orthonormal in that metric.
    """
    scaled = [math.sqrt(max(float(lam[k]), 0.0)) * vec[:, k] for k in range(len(lam))]
    directions = _probe_directions(lam, vec)
    if matrix is None or not indices:
        return directions
    values, vectors = np.linalg.eigh(np.asarray(matrix, dtype=float))
    for column in (0, len(values) - 1):
        u = vectors[:, column]
        directions.append(sum(float(u[a]) * scaled[k] for a, k in enumerate(indices)))
    return directions


def _clipped_radius(z0: "np.ndarray", direction: "np.ndarray", radius: float,
                    lower: "np.ndarray", upper: "np.ndarray") -> float:
    """The largest ``r <= radius`` with ``z0 + r * direction`` inside the declared box (R-15).

    A tail probe beyond a declared bound used to be dropped SILENTLY, which made the claim depend on where a
    bound was put: at 6.01 posterior sd the 6 sd probe ran and refused, at 5.99 it vanished and the claim
    rose. No posterior mass lies outside a declared bound, so a probe that would leave the box is indeed not
    measuring the posterior's tail -- the original reasoning is right and the silence was the defect. The
    probe is clipped to the radius the box allows, compared with that radius squared, and counted.
    """
    limit = float(radius)
    for i in range(len(z0)):
        step = float(direction[i])
        if step > 0.0:
            limit = min(limit, (float(upper[i]) - float(z0[i])) / step)
        elif step < 0.0:
            limit = min(limit, (float(lower[i]) - float(z0[i])) / step)
    return max(limit, 0.0)


def require_posterior_matches_calibration(posterior: "LocalGaussianPosterior", calibration) -> None:
    """Refuse a posterior whose declared parameterization is not the calibration's (I-14, R-25).

    Names, units, inference transforms, inference bounds and the declared parameterization digest.

    DECLARED BOUNDS ARE A PROPERTY OF THE REQUEST, and nothing inside a record is outside a forger's reach --
    which is why the audited forgery works: it moves the recorded bounds IN by sqrt(f) while dividing the
    covariance by f, so every bound distance in sd units survives and the re-derivation that catches a
    covariance-only shrink sees nothing. The only thing that can contradict edited bounds is the calibration
    they came from, so this function takes it, and the local route calls it on the record it has just built.
    Nothing here is checkable from the record ALONE, and that is not a gap this function can close.
    """
    if not isinstance(calibration, CalibrationResult):
        raise HybridUQError("a posterior is bound to a CalibrationResult")
    if posterior.parameterization != "declared":
        raise HybridUQError(
            f"only a declared posterior is bound to a calibration; this one is {posterior.parameterization!r}")
    parameters = calibration.spec.parameters
    lower, upper = inference_bounds(parameters)
    for label, found, expected in (
        ("parameter names", tuple(posterior.parameter_names), tuple(parameters.names)),
        ("parameter units", tuple(posterior.parameter_units), tuple(parameters.units)),
        ("inference transforms", tuple(posterior.inference_transforms), tuple(transforms_of(parameters))),
        ("lower bounds", tuple(float(v) for v in posterior.lower_bounds), tuple(float(v) for v in lower)),
        ("upper bounds", tuple(float(v) for v in posterior.upper_bounds), tuple(float(v) for v in upper)),
        ("parameterization digest", posterior.parameterization_digest,
         _declared_parameterization_digest(parameters)),
    ):
        if found != expected:
            raise HybridUQError(
                f"this posterior's {label} are {found!r} and the calibration declares {expected!r}; a "
                f"declared parameterization is the request's, and a record that moves it is not a record of "
                f"that request")


def require_posterior_matches_observations(posterior: "LocalGaussianPosterior", observations) -> None:
    """Refuse a posterior whose recorded observations are not the ones handed in (I-14, R-22(a)).

    Both halves: the COUNT, which the record states in the clear, and the DIGEST, which only these
    observations can produce. Without this the binding would be a read-back rule and a read-back rule is
    checked by whoever chooses to check -- so the local route calls it on the record it has just built, while
    both are in hand. A forger who edits the count and the digest to agree with each other produces a record
    that matches no observation set at all, and this is the check that says so.

    Distinct from `calibration_content_digest`, which is over `ObservationSet.to_dict()` and therefore binds
    the dataset id, the condition ids, the source refs and the row ORDER. The digest checked here binds the
    values and sigmas alone, order-independently, and carries the count: the weaker, more robust binding, and
    the only one the observation COUNT can be recovered from. Both are compared.
    """
    expected = observation_set_content_digest(observations)
    carried = str(posterior.diagnostics.observation_content_digest)
    if carried and carried != expected:
        raise HybridUQError(
            f"this posterior's diagnostics carry the observation content digest {carried!r} and the "
            f"observations handed in digest to {expected!r}; a record is evidence about the observations it "
            f"was fitted to and about no others")
    counted = len(getattr(observations, "observations", ()))
    if int(posterior.diagnostics.observations) != counted:
        raise HybridUQError(
            f"this posterior's diagnostics record {int(posterior.diagnostics.observations)} observation(s) "
            f"and {counted} were handed in; the count is what the goodness of fit is judged against")
    # `calibration_content_digest` is NOT re-checked here, deliberately. It is the posterior's own field and
    # is verified where it is used; adding it to this function made the digest check above unreachable --
    # mutation B36d removed that check and this one caught the same forgery, so the new binding was being
    # credited to an old one. One rule per function.


def _observation_content_digest(observations) -> str:
    """ONE canonical digest of the observation CONTENT a posterior was calibrated on (R-12).

    Over ``ObservationSet.to_dict()``, which is already the canonical serialization: the dataset id and, per
    observation, the condition id, the observable name, the value and sigma with their units, the source ref
    and the declared conditions with theirs. The CONTENT and not the dataset id, because two of R-12's three
    audited reproductions keep the id and change the content -- the conditions rescaled, or the values
    replaced by a predictor evaluated elsewhere. A dataset id is a label the caller writes.
    """
    return digest_of(observations.to_dict())


def _calibrated_conditions(observations) -> tuple[tuple[str, str], ...]:
    """The ``(name, unit)`` pairs of every condition EVERY calibration observation declares, sorted (R-31).

    The intersection, not the union: a condition one observation declares and another does not is not a range
    the calibration covered, and the domain gate already answered PREDICTION_DOMAIN_NOT_DECLARED for exactly
    that case. The unit is the first observation's, which every row is then converted into.
    """
    rows = getattr(observations, "observations", ())
    if not rows:
        return ()
    shared = set(rows[0].conditions)
    for row in rows[1:]:
        shared &= set(row.conditions)
    out = []
    for name in sorted(shared):
        unit = rows[0].conditions[name].units
        try:
            for row in rows:
                row.conditions[name].magnitude_in(unit)
        except UnitCompatibilityError:
            # A condition in another dimension is not ONE range, so it is not part of the design. Caught by
            # its own type and not as `Exception`: a broad catch here also swallowed the KeyError a name
            # missing from some observation raises, which made the INTERSECTION above unobservable -- a guard
            # mutation turning it into a union survived twice.
            continue
        out.append((str(name), str(unit)))
    return tuple(out)


def _calibrated_condition_points(observations) -> tuple[tuple[float, ...], ...]:
    """One row of condition magnitudes per calibration observation, aligned with ``_calibrated_conditions``."""
    pairs = _calibrated_conditions(observations)
    if not pairs:
        return ()
    return tuple(tuple(row.conditions[name].magnitude_in(unit) for name, unit in pairs)
                 for row in observations.observations)


def _declared_parameterization_digest(parameter_set: CalibrationParameterSet) -> str:
    return digest_of({"parameter_set_digest": parameter_set.digest, "label": "declared"})


def _refused(calibration: CalibrationResult, observations: ObservationSet, reason: RouteReason, *,
             sensitivity_digest: str = "", evaluations: int = 0, rank: int = 0,
             condition: float = math.nan, raw_condition: float = math.nan) -> LocalGaussianPosterior:
    parameters = calibration.spec.parameters
    transforms = transforms_of(parameters)
    lower, upper = inference_bounds(parameters)
    estimate = calibration.estimate_vector if calibration.status is CalibrationStatus.CONVERGED else calibration.spec.initial_vector
    p = len(parameters.names)
    diagnostics = RouteDiagnostics(
        parameters=p, observations=len(observations.observations), jacobian_rank=rank, jacobian_condition=condition,
        raw_jacobian_condition=raw_condition, newton_step_in_sd=(), at_bound=(), near_bound=(),
        minimum_bound_distance_sd=math.nan, nonlinearity_index=math.nan, nonlinearity_probes_skipped=0,
        minimum_chi_square_rise=math.nan, multistart=(), uniqueness="NOT_ASSESSED", thresholds=_thresholds(),
        evaluation_count=evaluations, claim=RouteClaim.REFUSED, refusals=(reason,), downgrades=(),
        # R-27 (I-14 part F): an early refusal is a `/3` record like any other, and `from_dict` requires
        # the digest of the observations a `/3` record was fitted to. Without it the router could return a
        # record that cannot be read back at all -- found while reproducing finding 22, whose structural
        # forgery needs a refused posterior that round-trips.
        observation_content_digest=observation_set_content_digest(observations),
    )
    return LocalGaussianPosterior(
        approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION, parameter_names=parameters.names,
        parameter_units=parameters.units, inference_transforms=transforms, parameterization="declared",
        parameterization_digest=_declared_parameterization_digest(parameters), estimate=tuple(estimate),
        inference_point=tuple(to_inference(estimate, transforms)), covariance=None, lower_bounds=tuple(lower),
        upper_bounds=tuple(upper), diagnostics=diagnostics, sensitivity_digest=sensitivity_digest or "none",
        dataset_id=observations.dataset_id,
    )


def _log_det_information(weighted_jacobian: "np.ndarray") -> float | None:
    """``log det(A.T @ A)`` for a whitened Jacobian, or None when that information is not positive definite.

    ``A.T @ A`` is the Gauss-Newton information and the local Gaussian covariance is its inverse, so
    ``log det(Sigma) = -log det(A.T @ A)``. Working in logs keeps a broad mode whose determinant underflows a
    float from turning into a zero or an infinity.
    """
    A = np.asarray(weighted_jacobian, dtype=np.float64)
    sign, logdet = np.linalg.slogdet(A.T @ A)
    if not (sign > 0.0 and math.isfinite(logdet)):
        return None
    return float(logdet)


def _separated_mass_ratio(refit: CalibrationResult, observations: ObservationSet, forward: ForwardEvaluator,
                          chi_minimum: float, log_det_at_minimum: float | None) -> tuple[float | None, int, str]:
    """``(ratio, evaluations, unavailable)`` -- the Laplace mass ratio of a separated converged refit.

    The ratio is ``exp(-(chi - chi_min) / 2) * sqrt(det(Sigma) / det(Sigma_min))``, the Laplace approximation to
    the ratio of the two modes' posterior mass, from a local sensitivity reconstructed at the refit. Posterior
    mass depends on a mode's VOLUME as well as its peak height, which is why the objective alone cannot say
    whether a separated optimum matters (audit R-07).

    ``ratio`` is None exactly when ``unavailable`` says why: the curvature at the refit could not be
    reconstructed, the information there is not positive definite, or the ratio overflows a float. A mode whose
    mass cannot be bounded is not a negligible mode, so the caller counts it.
    """
    if log_det_at_minimum is None:
        return None, 0, "the information at the estimate is not positive definite"
    try:
        local = reconstruct_local_sensitivity(refit, observations, forward)
    except (_DerivativeNotConverged, RouteRefusedError) as error:
        return None, 0, f"the curvature at the refit is not available ({type(error).__name__})"
    spent = int(local.evaluation_count)
    log_det = _log_det_information(local.weighted_jacobian)
    if log_det is None:
        return None, spent, "the information at the refit is not positive definite"
    exponent = -0.5 * (float(refit.objective_value) - float(chi_minimum)) + 0.5 * (float(log_det_at_minimum) - log_det)
    if exponent > _MASS_RATIO_LOG_LIMIT:
        return None, spent, f"the mass ratio exceeds exp({_MASS_RATIO_LOG_LIMIT:g})"
    return float(math.exp(exponent)), spent, ""


def local_gaussian_posterior(
    calibration: CalibrationResult,
    observations: ObservationSet,
    forward: ForwardEvaluator,
    *,
    multistart: MultistartPolicy | None,
    sensitivity: LocalSensitivity | None = None,
) -> LocalGaussianPosterior:
    """Build the local Gaussian approximation at a converged calibration, with every validity diagnostic.

    ``multistart`` is required: pass a :class:`MultistartPolicy`, or ``None`` to record that global
    uniqueness was not assessed (which caps the claim at DOWNGRADED).
    """
    if not isinstance(calibration, CalibrationResult):
        raise HybridUQError("local_gaussian_posterior takes a CalibrationResult")
    if not isinstance(observations, ObservationSet):
        raise HybridUQError("local_gaussian_posterior takes an ObservationSet")
    if multistart is not None and not isinstance(multistart, MultistartPolicy):
        raise HybridUQError("multistart must be a MultistartPolicy or None")
    if calibration.status is not CalibrationStatus.CONVERGED:
        return _refused(calibration, observations, RouteReason.CALIBRATION_NOT_CONVERGED)

    parameters = calibration.spec.parameters
    names = parameters.names
    transforms = transforms_of(parameters)
    lower, upper = inference_bounds(parameters)
    estimate = np.asarray(calibration.estimate_vector, dtype=np.float64)
    z0 = to_inference(estimate, transforms)
    keys = observations.keys
    units = tuple(o.value.units for o in observations.observations)
    references = tuple(o.value for o in observations.observations)
    observed, sigma = observations.numeric_vectors()
    evaluations = 0

    if sensitivity is None:
        try:
            sensitivity = reconstruct_local_sensitivity(calibration, observations, forward)
        except _DerivativeNotConverged:
            # Not an inadmissible point, and no route reason names it: the route has no curvature to report
            # and refuses by raising, so nothing downstream can build a covariance from an unstable Jacobian.
            raise
        except RouteRefusedError:
            return _refused(calibration, observations, RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE)
    else:
        try:
            evaluations += _bind_supplied_sensitivity(sensitivity, calibration, observations, forward)
        except _DerivativeNotConverged:
            raise
        except RouteRefusedError:
            return _refused(calibration, observations, RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE)
    evaluations += sensitivity.evaluation_count

    p, n = len(names), len(keys)
    A = sensitivity.weighted_jacobian
    refusals: list[RouteReason] = []
    downgrades: list[RouteReason] = []

    # usable curvature: rank and conditioning, scale-free through column equilibration
    norms = np.linalg.norm(A, axis=0)
    raw_s = np.linalg.svd(A, compute_uv=False)
    raw_condition = float(raw_s[0] / raw_s[-1]) if raw_s[-1] > 0 else math.inf
    if np.any(norms == 0.0):
        return _refused(calibration, observations, RouteReason.STRUCTURALLY_UNIDENTIFIABLE, sensitivity_digest=sensitivity.digest,
                        evaluations=evaluations, rank=int(np.linalg.matrix_rank(A)), condition=math.inf, raw_condition=raw_condition)
    scaled = A / norms
    U, S, Vt = np.linalg.svd(scaled, full_matrices=False)
    rank = int(np.sum(S > S[0] * max(n, p) * np.finfo(float).eps))
    condition = float(S[0] / S[-1]) if S[-1] > 0 else math.inf
    structural = None
    if p >= n:
        structural = RouteReason.NO_RESIDUAL_DEGREES_OF_FREEDOM
    elif rank < p:
        structural = RouteReason.STRUCTURALLY_UNIDENTIFIABLE
    elif condition > NUMERICAL_CONDITION_LIMIT:
        structural = RouteReason.NUMERICALLY_SINGULAR_JACOBIAN
    if structural is not None:
        return _refused(calibration, observations, structural, sensitivity_digest=sensitivity.digest, evaluations=evaluations,
                        rank=rank, condition=condition, raw_condition=raw_condition)
    # R-26: judged on the EQUILIBRATED condition, which is scale-free. The raw condition stays recorded below
    # and no longer lowers a claim: any caller moves it by any factor by restating a parameter in a smaller unit.
    if condition > POORLY_SCALED_CONDITION_LIMIT:
        downgrades.append(RouteReason.POORLY_SCALED_PARAMETERIZATION)
    scaled_cov = (Vt.T / S ** 2) @ Vt
    cov = scaled_cov / np.outer(norms, norms)
    cov = 0.5 * (cov + cov.T)
    sd = np.sqrt(np.diag(cov))
    chi_min = sensitivity.chi_square

    # residuals the declared noise can explain (CORE-001): the covariance above is the parameter uncertainty only if
    # the declared sigma describes the scatter about the fit
    # R-03: also where the information is. The hat diagonal costs nothing here -- it is the row norms of the
    # orthonormal basis of the same column space the rank and conditioning above came from.
    leverage, basis = _leverage_weights(A)
    leverage_cumulants = _leverage_null_cumulants(leverage, basis)
    leverage_statistic = float(np.sum(leverage * np.asarray(sensitivity.standardized_residuals) ** 2))
    fit_refusals, fit_downgrades = _goodness_of_fit(chi_min, n, p, leverage_statistic, leverage_cumulants)
    refusals.extend(sorted(fit_refusals, key=lambda r: r.value))
    downgrades.extend(sorted(fit_downgrades, key=lambda r: r.value))

    # interior, stationary optimum: the Gauss-Newton step from the estimate, in sd units
    residual = sensitivity.standardized_residuals
    step = -(cov @ (A.T @ residual))
    step_sd = step / sd
    span = upper - lower
    at_lower = (z0 - lower) <= AT_BOUND_RELATIVE * span
    at_upper = (upper - z0) <= AT_BOUND_RELATIVE * span
    at_bound = []
    for i in range(p):
        if abs(step_sd[i]) > STATIONARITY_SD:
            if (at_lower[i] and step[i] < 0) or (at_upper[i] and step[i] > 0):
                at_bound.append(names[i])
    if at_bound:
        refusals.append(RouteReason.PARAMETER_AT_BOUND)
    elif np.any(np.abs(step_sd) > STATIONARITY_SD):
        refusals.append(RouteReason.NOT_STATIONARY)

    # bounds not dominating
    distance = np.minimum(z0 - lower, upper - z0) / sd
    near = tuple(names[i] for i in range(p) if distance[i] < BOUND_DOWNGRADE_SD and names[i] not in at_bound)
    if near:
        downgrades.append(RouteReason.BOUND_WITHIN_3_SD)

    # locally affine within +/-2 sd: chi-square rise along every principal axis and every diagonal between two of
    # them, against the Gaussian's 4. Axis probes alone are blind to a cross term u_i u_j, which vanishes on both
    # axes, so a saddle whose descent lies between them passed as a minimum (audit HUQ-08).
    def chi_square_at(z):
        values = evaluate(forward, to_natural(z, transforms), keys, units, references)
        return None if values is None else float(np.sum(((values - observed) / sigma) ** 2))

    # R-16: the probe basis is the CORRELATION eigenbasis scaled by the marginal sds, not eigh(cov) in
    # declared units. Identical for an uncorrelated posterior; invariant under a unit change for any other.
    lam, vec = _invariant_basis(cov)
    worst, skipped, min_rise, not_minimum, evaluated = 0.0, 0, math.inf, False, 0
    expected = PROBE_SD ** 2
    measured_rises: dict[tuple, float] = {}
    for label, delta in _labelled_probe_directions(lam, vec):
        for sign in (1.0, -1.0):
            point = z0 + sign * PROBE_SD * delta
            if np.any(point < lower) or np.any(point > upper):
                skipped += 1
                continue
            value = chi_square_at(point)
            evaluations += 1
            if value is None:
                skipped += 1
                continue
            evaluated += 1
            rise = value - chi_min
            measured_rises[(label, sign)] = rise
            min_rise = min(min_rise, rise)
            if rise < -1e-9 * max(1.0, chi_min):
                not_minimum = True
            worst = max(worst, abs(rise / expected - 1.0))
    # R-13: the probes already paid for, read as a MATRIX. The per-direction index above bounds each
    # direction alone, and a curvature error spread over many pairs is small in every one of them and large
    # in their sum. The matrix index is the same quantity -- |d^T M d - 1| -- maximized over EVERY unit
    # direction, so it dominates the loop above and is compared with the same two declared thresholds.
    built = _curvature_matrix(p, measured_rises)
    curvature_bounds: tuple[float, ...] = ()
    curvature_indices: tuple[int, ...] = ()
    if built is not None:
        curvature, curvature_indices = built
        curvature_worst, extremes = _curvature_index(curvature)
        curvature_bounds = extremes
        worst = max(worst, curvature_worst)
    else:
        curvature = None
    if evaluated < p:
        # Fewer probes than parameters were compared with the model (audit HUQ-10). The nonlinearity was not
        # measured, and 0.0 is not its value: it is recorded as NaN, and a covariance nobody checked against the
        # model is not emitted.
        worst = math.nan
    if not_minimum:
        refusals.append(RouteReason.NOT_A_LOCAL_MINIMUM)
    if math.isnan(worst) or worst > NONLINEARITY_REFUSE:
        refusals.append(RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN)
    elif worst > NONLINEARITY_DOWNGRADE:
        downgrades.append(RouteReason.NONLINEAR_WITHIN_2_SD)
    if skipped:
        downgrades.append(RouteReason.NONLINEARITY_PROBE_INCOMPLETE)

    # no heavier tail than the reported Gaussian out to 6 sd (CORE-003). The +/-2 sd probes cannot see a posterior that
    # is Gaussian to just past 2 sd and nearly flat beyond, which puts most of its mass outside the reported interval.
    # A probe beyond a declared bound is not needed: no posterior mass lies there.
    tail_skipped, tail_ratio = 0, math.inf
    tail_clipped, tail_outside = 0, 0
    for axis in _tail_directions(lam, vec, curvature, curvature_indices):
        for radius in TAIL_PROBE_SD:
            for sign in (1.0, -1.0):
                # R-15: clipped to the radius the declared box allows, and compared with THAT radius squared.
                # Dropping the probe made the claim depend on where a bound was put -- 6.01 sd refused and
                # 5.99 sd was SUPPORTED. Below PROBE_SD there is no tail left to measure, because the +/-2 sd
                # probes already measured that radius against their own rule; such a probe is not used, and it
                # is counted rather than silent.
                reached = _clipped_radius(z0, sign * axis, radius, lower, upper)
                if reached < PROBE_SD:
                    tail_outside += 1
                    continue
                if reached < radius:
                    tail_clipped += 1
                point = z0 + sign * reached * axis
                value = chi_square_at(point)
                evaluations += 1
                if value is None:
                    tail_skipped += 1
                    continue
                tail_ratio = min(tail_ratio, (value - chi_min) / reached ** 2)
    tail_ratio = math.nan if math.isinf(tail_ratio) else float(tail_ratio)
    tail_refusals, tail_downgrades = _tail_verdict(tail_ratio)
    refusals.extend(sorted(tail_refusals, key=lambda r: r.value))
    downgrades.extend(sorted(tail_downgrades, key=lambda r: r.value))
    if tail_skipped:
        downgrades.append(RouteReason.NONLINEARITY_PROBE_INCOMPLETE)
    if tail_outside:
        downgrades.append(RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS)

    # a single mode: deterministic multistart through the frozen calibrate
    starts_record: list[dict[str, Any]] = []
    thresholds = _thresholds()
    if multistart is None:
        uniqueness = "NOT_ASSESSED"
        downgrades.append(RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED)
    else:
        thresholds.update(_policy_record(multistart, p))
        separation = float(chi2.ppf(multistart.mode_separation_quantile, p))
        comparable = float(chi2.ppf(multistart.comparable_fit_quantile, p))
        gradient = A.T @ residual
        lower_tolerance = max(2.0 * float(gradient @ cov @ gradient), LOWER_OBJECTIVE_FLOOR) + 1e-9 * max(1.0, chi_min)
        spec = calibration.spec
        canonical_budget = int(MultistartPolicy().max_evaluations)
        log_det_at_minimum = _log_det_information(A)
        # one counter for every start's replacements, so no two starts take the same Halton point
        halton_index = int(multistart.starts)
        for start in multistart.start_points(parameters):
            proposed = tuple(start)
            replacements = 0
            admissible = evaluate(forward, start, keys, units, references) is not None
            evaluations += 1
            while not admissible and replacements < int(multistart.maximum_retractions):
                replacements += 1
                halton_index += 1
                start = multistart._point(parameters, halton_index)
                admissible = evaluate(forward, start, keys, units, references) is not None
                evaluations += 1
            if not admissible:
                starts_record.append({"start": proposed, "status": "NO_ADMISSIBLE_START", "replacements": replacements})
                continue
            restart = CalibrationSpec(parameters=spec.parameters, fixed=spec.fixed,
                                      initial_point={nm: Quantity(v, u) for nm, v, u in zip(names, start, parameters.units)},
                                      noise_model=spec.noise_model, objective=spec.objective, method=spec.method)
            refit = calibrate(restart, observations, forward, heldout_dataset_id=calibration.provenance.heldout_dataset_id,
                              max_evaluations=int(multistart.max_evaluations), seed=calibration.provenance.seed)
            evaluations += int(refit.evaluation_count)
            retried = False
            if refit.status is not CalibrationStatus.CONVERGED and int(multistart.max_evaluations) < canonical_budget:
                # the caller's budget was too small, or this problem does not converge from here: one retry at the
                # canonical budget is the difference, and it is what the entry records (audit R-08)
                refit = calibrate(restart, observations, forward, heldout_dataset_id=calibration.provenance.heldout_dataset_id,
                                  max_evaluations=canonical_budget, seed=calibration.provenance.seed)
                evaluations += int(refit.evaluation_count)
                retried = True
            entry: dict[str, Any] = {"start": tuple(start), "proposed_start": proposed, "replacements": replacements,
                                     "status": refit.status.value}
            if retried:
                entry["retried_at_canonical_budget"] = True
            if refit.status is CalibrationStatus.CONVERGED:
                other = to_inference(refit.estimate_vector, transforms)
                m2 = float(np.sum((A @ (other - z0)) ** 2))
                entry.update({"estimate": tuple(refit.estimate_vector), "chi_square": float(refit.objective_value),
                              "mahalanobis_sq": m2})
                if m2 > separation:
                    if refit.objective_value < chi_min - comparable:
                        entry["classification"] = "BETTER_OPTIMUM"
                    else:
                        ratio, spent, unavailable = _separated_mass_ratio(refit, observations, forward, chi_min,
                                                                         log_det_at_minimum)
                        evaluations += spent
                        if ratio is None:
                            entry["laplace_mass_unavailable"] = unavailable
                        else:
                            entry["laplace_mass_ratio"] = ratio
                        # only a mass that is bounded AND negligible makes a separated optimum merely worse: a mode
                        # whose mass could not be bounded is not a negligible mode
                        entry["classification"] = ("WORSE_LOCAL_OPTIMUM"
                                                   if ratio is not None and ratio <= MULTISTART_MASS_FLOOR
                                                   else "SECOND_MODE")
                elif refit.objective_value < chi_min - lower_tolerance:
                    # inside the separation radius, but lower: not the estimate's optimum, whatever the distance
                    entry["classification"] = "LOWER_OBJECTIVE_SAME_BASIN"
                else:
                    entry["classification"] = "SAME_OPTIMUM"
            starts_record.append(entry)
        uniqueness, found_refusals, found_downgrades = _multistart_verdict(starts_record, p, thresholds)
        refusals.extend(sorted(found_refusals, key=lambda r: r.value))
        downgrades.extend(sorted(found_downgrades, key=lambda r: r.value))

    claim = claim_for(refusals + downgrades)
    diagnostics = RouteDiagnostics(
        parameters=p, observations=n, jacobian_rank=rank, jacobian_condition=condition, raw_jacobian_condition=raw_condition,
        newton_step_in_sd=tuple(step_sd), at_bound=tuple(at_bound), near_bound=near,
        minimum_bound_distance_sd=float(np.min(distance)), nonlinearity_index=float(worst),
        nonlinearity_probes_skipped=skipped, minimum_chi_square_rise=float(min_rise),
        multistart=tuple(starts_record), uniqueness=uniqueness, thresholds=thresholds, evaluation_count=evaluations,
        claim=claim, refusals=tuple(r for r in refusals if r.severity is RouteClaim.REFUSED),
        downgrades=tuple(d for d in downgrades if d.severity is RouteClaim.DOWNGRADED),
        chi_square_minimum=float(chi_min), minimum_tail_rise_ratio=tail_ratio, tail_probes_skipped=tail_skipped,
        observation_content_digest=observation_set_content_digest(observations),
        leverage_weighted_chi_square=leverage_statistic, leverage_null_cumulants=leverage_cumulants,
        curvature_eigenvalue_bounds=curvature_bounds, tail_probes_clipped=tail_clipped,
        tail_probes_outside_bounds=tail_outside,
    )
    posterior = LocalGaussianPosterior(
        approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION, parameter_names=names,
        parameter_units=parameters.units, inference_transforms=transforms, parameterization="declared",
        parameterization_digest=_declared_parameterization_digest(parameters), estimate=tuple(estimate),
        inference_point=tuple(z0), covariance=None if claim is RouteClaim.REFUSED else tuple(map(tuple, cov)),
        lower_bounds=tuple(lower), upper_bounds=tuple(upper), diagnostics=diagnostics,
        sensitivity_digest=sensitivity.digest, dataset_id=observations.dataset_id,
        # R-12 / R-31: what this posterior was calibrated on, so a prediction's domain statement can be bound
        # to it rather than to whatever a caller hands over later.
        calibration_content_digest=_observation_content_digest(observations),
        calibrated_conditions=_calibrated_conditions(observations),
        calibrated_condition_points=_calibrated_condition_points(observations),
    )
    # Held for the router's grid rebuild only: a covariance the route refused to report is still the best
    # available DESIGN for a grid that the frozen V1 checks will then verify or refuse. Never serialized.
    object.__setattr__(posterior, "_design_covariance", cov)
    object.__setattr__(posterior, "_modes", tuple(
        to_inference(m["estimate"], transforms) for m in starts_record
        if m.get("classification") in ("SECOND_MODE", "BETTER_OPTIMUM")))
    # The record is verified against the two things it was built from, while both are in hand: the
    # observations (I-14, R-22(a)) and the calibration (I-14, R-25). Without these calls both bindings would
    # be rules a reader may choose to apply, and R-25's forgery is one no reader can catch from the record
    # alone -- the bounds are the REQUEST's and every field is the forger's.
    require_posterior_matches_observations(posterior, observations)
    require_posterior_matches_calibration(posterior, calibration)
    return posterior
