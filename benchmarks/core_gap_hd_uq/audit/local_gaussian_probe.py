"""Review probe: a CANDIDATE scalable uncertainty route, outside the Core.

This file is evidence for a compatibility review, not a backend. It lives under
``benchmarks/`` on purpose: nothing in ``src/engcore`` imports it, and the
review's verdict decides whether anything like it may ever enter the Core.

What it computes, for a bounded weighted least-squares calibration
``min sum(((f(theta) - y) / sigma)^2)``:

``LOCAL_GAUSSIAN_APPROXIMATION``
    N(theta_hat, (J_w^T J_w)^-1) with J_w the sigma-weighted Jacobian at the
    frozen ``calibrate`` estimate (Gauss-Newton / Fisher information, flat prior).
    Exact only for a model affine in theta with no active bound. Never called a
    posterior grid, never called exact.
``LINEARIZED_PREDICTIVE_UQ``
    mean g(theta_hat), variance diag(G Sigma G^T) + sigma_obs^2.

What it refuses or downgrades, and why each check exists:

* ``STRUCTURALLY_UNIDENTIFIABLE`` (refuse): rank(J_w) < p.
* ``NO_RESIDUAL_DEGREES_OF_FREEDOM`` (refuse): p >= n.
* ``NUMERICALLY_SINGULAR_JACOBIAN`` (refuse): cond(J_w) > 1/sqrt(eps).
* ``PARAMETER_AT_BOUND`` (refuse): the constrained optimum is not a stationary
  point, so J^T J is not the curvature of the posterior there.
* ``BOUND_WITHIN_3_SD`` (downgrade): the Gaussian puts material mass outside the
  physical range.
* ``NOT_A_LOCAL_MINIMUM`` (refuse): the objective falls along a probed direction.
* ``NONLINEAR_WITHIN_2_SD`` (downgrade) / ``NONLINEAR_BEYOND_LOCAL_GAUSSIAN``
  (refuse): along every principal axis of the covariance, at +/-2 sd, the true
  chi-square rise is compared with the rise of 4 the Gaussian implies.
* ``PREDICTIVE_NONLINEAR`` (downgrade): the same probe points, applied to the
  predicted quantities, compared with their linear extrapolation.
* ``SECOND_MODE_FOUND`` (refuse): a declared multistart reaches another optimum
  of comparable chi-square outside the local ellipsoid.
* ``GLOBAL_UNIQUENESS_NOT_ASSESSED`` (downgrade): no multistart was run and the
  model was not declared affine-and-verified.

Identifiability uses the FROZEN ``assess_identifiability`` thresholds, read from
its signature rather than copied, and applies the same classification rule to
the Gaussian covariance, with Gaussian marginal intervals in place of discrete
ones.
"""

from __future__ import annotations

import inspect
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np
from scipy.stats import chi2, norm

from engcore.inference import assess_identifiability

POSTERIOR_CLASS = "LOCAL_GAUSSIAN_APPROXIMATION"
PREDICTIVE_CLASS = "LINEARIZED_PREDICTIVE_UQ"
Z95 = float(norm.ppf(0.975))

_DEFAULTS = {k: v.default for k, v in inspect.signature(assess_identifiability).parameters.items()
             if v.default is not inspect.Parameter.empty}
THRESHOLDS = {
    "correlation": _DEFAULTS["correlation_threshold"],
    "condition_number": _DEFAULTS["condition_threshold"],
    "relative_width": _DEFAULTS["width_threshold"],
}

#: Declared diagnostic thresholds of the CANDIDATE route (review proposals).
NONLINEARITY_DOWNGRADE = 0.10
NONLINEARITY_REFUSE = 0.50
PREDICTIVE_NONLINEARITY_DOWNGRADE = 0.10
BOUND_DOWNGRADE_SD = 3.0
AFFINE_TOLERANCE = 1.0e-6
FD_RELATIVE_STEP = 1.0e-5
#: Above this weighted-Jacobian condition number the covariance's own condition number cond(J_w)^2
#: exceeds 1/eps: its smallest-variance direction is no longer representable in float64 relative
#: to its largest, whatever inversion method is used.
NUMERICAL_CONDITION_LIMIT = 1.0 / math.sqrt(np.finfo(float).eps)


@dataclass
class LocalProblem:
    """Everything the route needs; nothing domain-specific.

    ``forward(theta)`` returns model means at the calibration observations (in
    the observations' units) or ``None`` when the point is inadmissible.
    ``predict(theta)`` optionally returns the predicted quantities.
    """

    names: tuple[str, ...]
    forward: Callable[[np.ndarray], np.ndarray | None]
    observed: np.ndarray
    sigma: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    predict: Callable[[np.ndarray], np.ndarray | None] | None = None
    predict_sigma: np.ndarray | None = None
    declared_affine: bool = False
    calls: dict = field(default_factory=lambda: {"forward": 0, "predict": 0})

    def f(self, theta):
        self.calls["forward"] += 1
        out = self.forward(np.asarray(theta, dtype=float))
        return None if out is None else np.asarray(out, dtype=float)

    def g(self, theta):
        self.calls["predict"] += 1
        out = self.predict(np.asarray(theta, dtype=float))
        return None if out is None else np.asarray(out, dtype=float)

    def chi_square(self, theta):
        values = self.f(theta)
        if values is None:
            return None
        return float(np.sum(((values - self.observed) / self.sigma) ** 2))


def jacobian(fun, theta, lower, upper, count):
    """Central differences, step = FD_RELATIVE_STEP x declared bound range; one-sided at a bound."""
    theta = np.asarray(theta, dtype=float)
    base = fun(theta)
    if base is None:
        return None, None
    cols = []
    for i in range(len(theta)):
        h = FD_RELATIVE_STEP * (upper[i] - lower[i])
        up, dn = theta.copy(), theta.copy()
        up[i] += h
        dn[i] -= h
        if up[i] > upper[i]:
            up = theta.copy()
            fu, fd = base, fun(dn)
            denom = h
        elif dn[i] < lower[i]:
            dn = theta.copy()
            fu, fd = fun(up), base
            denom = h
        else:
            fu, fd = fun(up), fun(dn)
            denom = 2 * h
        if fu is None or fd is None:
            return base, None
        cols.append((fu - fd) / denom)
    count["jacobian_columns"] = count.get("jacobian_columns", 0) + len(theta)
    return base, np.column_stack(cols)


def classify_identifiability(mean, cov, names):
    sd = np.sqrt(np.maximum(np.diag(cov), 0.0))
    denom = np.outer(sd, sd)
    corr = np.divide(cov, denom, out=np.zeros_like(cov), where=denom > 0)
    eig = np.linalg.eigvalsh(cov)
    condition = float(eig.max() / eig.min()) if eig.min() > 0 else float("inf")
    off = [abs(float(corr[i, j])) for i in range(len(sd)) for j in range(len(sd)) if i != j]
    max_corr = max(off) if off else 0.0
    widths = [(2 * Z95 * sd[i]) / abs(mean[i]) if abs(mean[i]) > 0 else float("inf") for i in range(len(sd))]
    reasons = []
    if not math.isfinite(condition) or condition > THRESHOLDS["condition_number"]:
        reasons.append("condition")
    if max_corr > THRESHOLDS["correlation"]:
        reasons.append("correlation")
    over = [names[i] for i, w in enumerate(widths) if not math.isfinite(w) or w > THRESHOLDS["relative_width"]]
    if over:
        status = "PARAMETERS_NOT_IDENTIFIABLE"
    elif not reasons:
        status = "PARAMETERS_IDENTIFIABLE"
    elif len(reasons) >= 2:
        status = "PARAMETERS_NOT_IDENTIFIABLE"
    else:
        status = "PARAMETERS_WEAKLY_IDENTIFIABLE"
    return {"status": status, "condition_number": condition, "max_abs_correlation": max_corr,
            "relative_widths": widths, "over_wide": over, "reasons": reasons, "thresholds": THRESHOLDS,
            "rule": "frozen assess_identifiability thresholds and classification, Gaussian marginals"}


def local_gaussian(problem: LocalProblem, estimate: Sequence[float], *,
                   refit: Callable[[np.ndarray], tuple[np.ndarray, float] | None] | None = None,
                   starts: Sequence[Sequence[float]] = (),
                   reparameterizations: dict[str, tuple[np.ndarray, list[str]]] | None = None) -> dict:
    started = time.perf_counter()
    theta = np.asarray(estimate, dtype=float)
    p, n = len(theta), len(problem.observed)
    count: dict = {}
    reasons_refuse: list[str] = []
    reasons_down: list[str] = []
    out: dict = {"posterior_class": POSTERIOR_CLASS, "predictive_class": PREDICTIVE_CLASS,
                 "p": p, "n": n, "exact_posterior_claimed": False}

    base, J = jacobian(problem.f, theta, problem.lower, problem.upper, count)
    if base is None or J is None:
        out.update({"claim": "REFUSED", "refusals": ["FORWARD_INADMISSIBLE_AT_OR_NEAR_ESTIMATE"]})
        return out
    A = J / problem.sigma[:, None]
    s = np.linalg.svd(A, compute_uv=False)
    rank = int(np.linalg.matrix_rank(A))
    out["structural"] = {"rank": rank, "singular_values": s.tolist(),
                         "jacobian_condition": float(s[0] / s[-1]) if s[-1] > 0 else float("inf")}
    structural = []
    if p >= n:
        structural.append("NO_RESIDUAL_DEGREES_OF_FREEDOM")
    if rank < p:
        structural.append("STRUCTURALLY_UNIDENTIFIABLE")
    elif s[-1] <= 0 or s[0] / s[-1] > NUMERICAL_CONDITION_LIMIT:
        structural.append("NUMERICALLY_SINGULAR_JACOBIAN")
    if structural:
        out.update({"claim": "REFUSED", "refusals": structural,
                    "wall_seconds": time.perf_counter() - started, "forward_calls": dict(problem.calls)})
        return out
    U, S, Vt = np.linalg.svd(A, full_matrices=False)
    cov = (Vt.T / S ** 2) @ Vt
    sd = np.sqrt(np.diag(cov))
    chi_min = float(np.sum(((base - problem.observed) / problem.sigma) ** 2))
    out["posterior"] = {"mean": theta.tolist(), "sd": sd.tolist(), "covariance": cov.tolist(),
                        "interval_95": [[float(t - Z95 * e), float(t + Z95 * e)] for t, e in zip(theta, sd)],
                        "chi_square_at_estimate": chi_min}
    out["identifiability"] = classify_identifiability(theta, cov, list(problem.names))
    if reparameterizations:
        out["reparameterizations"] = {
            name: classify_identifiability(T @ theta, T @ cov @ T.T, labels)
            for name, (T, labels) in reparameterizations.items()}

    # bounds
    distance = np.minimum(theta - problem.lower, problem.upper - theta) / sd
    at_bound = [problem.names[i] for i in range(p)
                if min(theta[i] - problem.lower[i], problem.upper[i] - theta[i]) <= 1e-9 * (problem.upper[i] - problem.lower[i])]
    near = [problem.names[i] for i in range(p) if distance[i] < BOUND_DOWNGRADE_SD and problem.names[i] not in at_bound]
    out["bounds"] = {"min_distance_in_sd": float(distance.min()), "at_bound": at_bound, "within_3_sd": near}
    if at_bound:
        reasons_refuse.append("PARAMETER_AT_BOUND")
    if near:
        reasons_down.append("BOUND_WITHIN_3_SD")

    # nonlinearity along principal axes at +/- 2 sd
    lam, vec = np.linalg.eigh(cov)
    worst, rises, outside, not_min = 0.0, [], 0, False
    pred_worst = 0.0
    g0 = G = None
    if problem.predict is not None:
        g0, G = jacobian(problem.g, theta, problem.lower, problem.upper, count)
    for k in range(p):
        delta = 2.0 * math.sqrt(max(lam[k], 0.0)) * vec[:, k]
        for sign in (1.0, -1.0):
            point = theta + sign * delta
            if np.any(point < problem.lower) or np.any(point > problem.upper):
                outside += 1
                continue
            c = problem.chi_square(point)
            if c is None:
                outside += 1
                continue
            rise = c - chi_min
            rises.append(rise)
            if rise < -1e-9 * max(1.0, chi_min):
                not_min = True
            worst = max(worst, abs(rise / 4.0 - 1.0))
            if G is not None:
                gp = problem.g(point)
                if gp is not None:
                    total = np.sqrt(np.einsum("ij,jk,ik->i", G, cov, G) + (problem.predict_sigma ** 2 if problem.predict_sigma is not None else 0.0))
                    pred_worst = max(pred_worst, float(np.max(np.abs(gp - (g0 + sign * G @ delta)) / total)))
    out["nonlinearity"] = {"probe": "principal axes of the covariance at +/-2 sd; expected chi-square rise 4",
                           "max_relative_deviation": worst, "probes_outside_bounds_or_inadmissible": outside,
                           "min_rise": min(rises) if rises else None, "max_rise": max(rises) if rises else None,
                           "predictive_max_deviation_in_total_sd": pred_worst if G is not None else None}
    if not_min:
        reasons_refuse.append("NOT_A_LOCAL_MINIMUM")
    if worst > NONLINEARITY_REFUSE:
        reasons_refuse.append("NONLINEAR_BEYOND_LOCAL_GAUSSIAN")
    elif worst > NONLINEARITY_DOWNGRADE:
        reasons_down.append("NONLINEAR_WITHIN_2_SD")
    if outside:
        reasons_down.append("NONLINEARITY_PROBE_INCOMPLETE")
    if G is not None and pred_worst > PREDICTIVE_NONLINEARITY_DOWNGRADE:
        reasons_down.append("PREDICTIVE_NONLINEAR")

    # global uniqueness
    uniqueness = "NOT_ASSESSED"
    if starts and refit is not None:
        modes = []
        cut = chi2.ppf(0.999, p)
        precision = np.linalg.inv(cov)
        for start in starts:
            result = refit(np.asarray(start, dtype=float))
            if result is None:
                continue
            other, other_chi = result
            d = other - theta
            m2 = float(d @ precision @ d)
            modes.append({"start": list(map(float, start)), "estimate": other.tolist(), "chi_square": other_chi, "mahalanobis_sq": m2})
            if m2 > cut and other_chi <= chi_min + chi2.ppf(0.99, p):
                reasons_refuse.append("SECOND_MODE_FOUND")
        uniqueness = "MULTISTART_NO_SECOND_MODE" if "SECOND_MODE_FOUND" not in reasons_refuse else "SECOND_MODE_FOUND"
        out["multistart"] = modes
    elif problem.declared_affine and worst <= AFFINE_TOLERANCE and outside == 0:
        uniqueness = "DECLARED_AFFINE_AND_VERIFIED_ALONG_PRINCIPAL_AXES"
    if uniqueness == "NOT_ASSESSED":
        reasons_down.append("GLOBAL_UNIQUENESS_NOT_ASSESSED")
    out["global_uniqueness"] = uniqueness

    if G is not None:
        var = np.einsum("ij,jk,ik->i", G, cov, G)
        total = np.sqrt(var + (problem.predict_sigma ** 2 if problem.predict_sigma is not None else 0.0))
        out["predictive"] = {"mean": g0.tolist(), "parameter_sd": np.sqrt(np.maximum(var, 0)).tolist(), "total_sd": total.tolist()}

    claim = "REFUSED" if reasons_refuse else ("DOWNGRADED" if reasons_down else "SUPPORTED")
    out.update({"claim": claim, "refusals": sorted(set(reasons_refuse)), "downgrades": sorted(set(reasons_down)),
                "forward_calls": dict(problem.calls), "wall_seconds": time.perf_counter() - started})
    return out


def importance_check(problem: LocalProblem, estimate, cov, *, samples=2000, seed=20260913) -> dict:
    """Option C as a VERIFICATION tier: reweight Gaussian draws by the true likelihood."""
    rng = np.random.default_rng(seed)
    theta = np.asarray(estimate, dtype=float)
    L = np.linalg.cholesky(cov)
    precision = np.linalg.inv(cov)
    draws = theta + (L @ rng.standard_normal((len(theta), samples))).T
    chi_min = problem.chi_square(theta)
    logw = np.full(samples, -np.inf)
    for i, point in enumerate(draws):
        if np.any(point < problem.lower) or np.any(point > problem.upper):
            continue
        c = problem.chi_square(point)
        if c is None:
            continue
        d = point - theta
        logw[i] = -0.5 * (c - chi_min) + 0.5 * float(d @ precision @ d)
    finite = np.isfinite(logw)
    if not finite.any():
        return {"ess_fraction": 0.0}
    w = np.exp(logw[finite] - logw[finite].max())
    w /= w.sum()
    ess = 1.0 / float(np.sum(w ** 2))
    mean = w @ draws[finite]
    centred = draws[finite] - mean
    cov_is = centred.T @ (centred * w[:, None])
    return {"samples": samples, "ess_fraction": ess / samples, "outside_bounds_or_inadmissible": int((~finite).sum()),
            "mean": mean.tolist(), "sd": np.sqrt(np.diag(cov_is)).tolist(),
            "max_mean_shift_in_gaussian_sd": float(np.max(np.abs(mean - theta) / np.sqrt(np.diag(cov))))}


def gauss_newton_vs_laplace(problem: LocalProblem, estimate, cov_gn) -> dict:
    """Option A: full finite-difference Hessian of chi-square/2 versus J^T J. O(p^2) calls."""
    theta = np.asarray(estimate, dtype=float)
    p = len(theta)
    h = np.sqrt(np.diag(cov_gn)) * 0.05
    c0 = problem.chi_square(theta)
    H = np.zeros((p, p))
    for i in range(p):
        for j in range(i, p):
            ei, ej = np.zeros(p), np.zeros(p)
            ei[i], ej[j] = h[i], h[j]
            fpp = problem.chi_square(theta + ei + ej)
            fpm = problem.chi_square(theta + ei - ej)
            fmp = problem.chi_square(theta - ei + ej)
            fmm = problem.chi_square(theta - ei - ej)
            if None in (fpp, fpm, fmp, fmm):
                return {"hessian": None, "reason": "inadmissible probe"}
            H[i, j] = H[j, i] = 0.5 * (fpp - fpm - fmp + fmm) / (4 * h[i] * h[j])
    try:
        cov_laplace = np.linalg.inv(H)
        eig = np.linalg.eigvalsh(H)
    except np.linalg.LinAlgError:
        return {"hessian": "singular"}
    return {"hessian_positive_definite": bool(eig.min() > 0), "sd_laplace": np.sqrt(np.abs(np.diag(cov_laplace))).tolist(),
            "sd_ratio_laplace_over_gauss_newton": (np.sqrt(np.abs(np.diag(cov_laplace))) / np.sqrt(np.diag(cov_gn))).tolist(),
            "chi_square_calls": 4 * p * (p + 1) // 2, "chi_square_at_estimate": c0}
