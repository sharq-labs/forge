"""The OutcomeModel boundary (M-4) and pre-result predictions (M-3).

Every number the Mind uses to rank an experiment or weigh a hypothesis comes from here, and every one of them cites
the admitted observations it was computed from (``basis``: their evidence digests).  Nothing here is a caller
assertion: a structure is fitted to ADMITTED EVIDENCE ONLY (observations the exposure authority released), with a
declared prior, and the predictive distribution is the closed-form posterior predictive of that fit.

Model (per structure S with p features): ln y = a + f_S(x)' b + e, e ~ N(0, s^2).

* MODEL COMPARISON uses Zellner's g-prior on b with the hyper-g/n prior on g (Liang, Paulo, Molina, Clyde & Berger
  2008, a = :data:`HYPER_G_A`), flat on a, Jeffreys on s^2: the marginal likelihood relative to the NULL structure is
  BF = (a - 2)/(2n) * integral_0^inf (1 + g/n)^(-a/2) (1 + g)^((n - 1 - p) / 2) (1 + g (1 - R^2))^(-(n - 1) / 2) dg,
  computed on a fixed log-g grid.  Two simpler choices failed on development worlds and are recorded: a FIXED g caps
  the Bayes factor at (1 + g)^((n - 1 - p) / 2) however overwhelming the evidence (the "information paradox": a structure
  leaving 3,600x more residual variance kept 8% of the posterior); the plain hyper-g prior has almost no Occam penalty
  at these sample sizes (no world without any dependence was ever concluded to have none).  Hyper-g/n is consistent,
  has no information paradox, and penalises like a unit-information prior.
* ESTIMATION AND PREDICTION, conditional on a structure, use the reference prior (flat on a and b, Jeffreys on s^2):
  the posterior predictive at a new setting is Student-t with n - 1 - p degrees of freedom around the least-squares
  fit.  (The g-prior's posterior mean shrinks every coefficient by g/(1+g); it is used for the Occam factor only.)

A structure that cannot be fitted (fewer observations than its features need, collinear features, no spread in the
observable) is UNFIT: it keeps its place in the competition and gets no number -- never a default.

A passive covariate is not set by an experiment, so its value at a planned query is unknown.  A structure that uses
one predicts through a covariate submodel fitted to the same evidence (ln u linear in the settable ln x), with the
submodel's residual variance carried into the prediction -- uncertainty is propagated, never dropped.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from .problem import ExperimentalProblem
from .structures import Structure

OUTCOME_MODEL_ID = "forge.mind.minimal.bayes_loglinear_gprior"
OUTCOME_MODEL_VERSION = "3"
HYPER_G_A = 3.0
_LOG_G = np.linspace(-12.0, 75.0, 1741)          # integration grid over t = ln g (step 0.05)
_DT = float(_LOG_G[1] - _LOG_G[0])
PREDICTION_SCHEMA = "forge.mind.minimal.outcome_prediction/1"


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class AdmittedObservation:
    """One observation the exposure authority released (``evidence_id``/``evidence_digest`` are its identity there)."""

    evidence_id: str
    evidence_digest: str
    query_ref: str
    settings: Mapping[str, float]
    covariates: Mapping[str, float]
    value: float

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "evidence_digest": self.evidence_digest, "query_ref": self.query_ref,
                "settings": dict(sorted(self.settings.items())), "covariates": dict(sorted(self.covariates.items())),
                "value": self.value}


class OutcomeModelRefused(ValueError):
    """The evidence cannot support this model at all (a non-positive observable for a log model)."""


@dataclass
class FittedStructure:
    structure: Structure
    key: str
    n: int
    p: int
    fit_ok: bool
    reason: str = ""
    log_bf_null: float | None = None
    r2: float | None = None
    ybar: float = 0.0
    coef: np.ndarray = field(default_factory=lambda: np.zeros(0))
    means: np.ndarray = field(default_factory=lambda: np.zeros(0))
    inv: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    shrink: float = 0.0
    s2: float = 0.0
    dof: int = 0
    basis_digest: str = ""

    def summary(self) -> dict[str, Any]:
        return {"key": self.key, "n": self.n, "p": self.p, "fit_ok": self.fit_ok, "reason": self.reason,
                "log_bf_null": None if self.log_bf_null is None else round(self.log_bf_null, 9),
                "r2": None if self.r2 is None else round(self.r2, 9), "s": round(math.sqrt(self.s2), 9) if self.fit_ok else None,
                "coef": [round(float(c), 9) for c in self.coef], "basis_digest": self.basis_digest}


@dataclass(frozen=True)
class CovariateModel:
    """ln u = c0 + c' ln x + r, fitted to the admitted evidence; a planned query predicts u through it."""

    name: str
    mean: float
    coef: tuple[float, ...]
    names: tuple[str, ...]
    resid_var: float
    r2: float


@dataclass(frozen=True)
class OutcomePrediction:
    """A hypothesis-conditioned prediction made BEFORE the result is exposed (M-3).

    ``mean``/``sd_mean`` describe ln(observable) under the hypothesis' posterior; ``sd_obs`` adds the observation
    noise; ``dof`` is the Student-t degrees of freedom.  ``available`` False means no prediction exists (UNFIT, or no
    evidence yet): the numbers are then None, never zero."""

    hypothesis_key: str
    query_ref: str
    available: bool
    mean: float | None
    sd_mean: float | None
    sd_obs: float | None
    dof: int | None
    basis_digest: str
    model: str = f"{OUTCOME_MODEL_ID}@{OUTCOME_MODEL_VERSION}"
    reason: str = ""

    def interval(self, mass: float = 0.9) -> tuple[float, float] | None:
        if not self.available:
            return None
        q = _t_quantile(0.5 + mass / 2, self.dof)
        return (self.mean - q * self.sd_obs * _t_scale(self.dof), self.mean + q * self.sd_obs * _t_scale(self.dof))

    def to_dict(self) -> dict[str, Any]:
        def r(x: float | None) -> float | None:
            return None if x is None else round(float(x), 9)
        return {"schema": PREDICTION_SCHEMA, "hypothesis_key": self.hypothesis_key, "query_ref": self.query_ref,
                "available": self.available, "mean_ln": r(self.mean), "sd_mean_ln": r(self.sd_mean),
                "sd_obs_ln": r(self.sd_obs), "dof": self.dof, "basis_digest": self.basis_digest, "model": self.model,
                "reason": self.reason}


def _t_scale(dof: int | None) -> float:
    """sd of a unit-scale Student-t is sqrt(dof/(dof-2)); the predictive sd is reported, so the scale is divided back."""
    return 1.0 if not dof or dof <= 2 else math.sqrt((dof - 2) / dof)


def _t_quantile(p: float, dof: int | None) -> float:
    """Student-t quantile (Hill 1970 expansion; exact enough for intervals and never used as a test statistic)."""
    z = _norm_quantile(p)
    if not dof or dof > 1e6:
        return z
    g1 = (z ** 3 + z) / 4
    g2 = (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96
    g3 = (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384
    return z + g1 / dof + g2 / dof ** 2 + g3 / dof ** 3


def _norm_quantile(p: float) -> float:
    # Acklam's rational approximation
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        return -_norm_quantile(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def t_logpdf(x: float, loc: float, scale_sd: float, dof: int) -> float:
    """Log density of a Student-t given its SD (not its scale)."""
    scale = scale_sd * _t_scale(dof)
    zz = (x - loc) / scale
    return (math.lgamma((dof + 1) / 2) - math.lgamma(dof / 2) - 0.5 * math.log(dof * math.pi) - math.log(scale)
            - (dof + 1) / 2 * math.log1p(zz * zz / dof))


def t_cdf(x: float, loc: float, scale_sd: float, dof: int) -> float:
    """Student-t CDF via the regularised incomplete beta function (continued fraction)."""
    scale = scale_sd * _t_scale(dof)
    t = (x - loc) / scale
    xb = dof / (dof + t * t)
    ib = _betainc(dof / 2, 0.5, xb)
    return 1 - 0.5 * ib if t > 0 else 0.5 * ib


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1 - math.exp(lbeta) * _betacf(b, a, 1 - x) / b


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(1 + aa / c) > 1e-300 else 1e-300
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return h


def hyper_g_log_bf(n: int, p: int, r2: float, a: float = HYPER_G_A) -> float:
    """ln BF(S : null) under the hyper-g/n prior (trapezoid rule in ln g on a fixed grid; log-sum-exp for stability)."""
    if p == 0:
        return 0.0
    t = _LOG_G
    g = np.exp(t)
    log_f = (math.log((a - 2) / (2 * n)) + t - 0.5 * a * np.log1p(g / n) + 0.5 * (n - 1 - p) * np.log1p(g)
             - 0.5 * (n - 1) * np.log1p(g * (1.0 - r2)))
    top = float(np.max(log_f))
    w = np.exp(log_f - top)
    return top + math.log(float(np.sum(w) - 0.5 * (w[0] + w[-1])) * _DT)


class OutcomeModel:
    """Fits structures to admitted evidence and predicts outcomes; identity = (id, version, prior)."""

    identity = {"model": OUTCOME_MODEL_ID, "version": OUTCOME_MODEL_VERSION, "g": f"hyper-g/n, a={HYPER_G_A}",
                "sigma_prior": "jeffreys", "intercept_prior": "flat", "estimation": "reference prior (least squares)"}

    def __init__(self, problem: ExperimentalProblem) -> None:
        self.problem = problem
        self.settable = [x.name for x in problem.canonical_inputs()]

    # ---- evidence -> arrays ---------------------------------------------------------------------------------------
    def _logs(self, rows: Sequence[AdmittedObservation]) -> tuple[dict[str, np.ndarray], np.ndarray]:
        cols: dict[str, np.ndarray] = {}
        for name in self.settable:
            cols[name] = np.log(np.array([r.settings[name] for r in rows], dtype=float))
        for name in self.problem.covariates:
            vals = np.array([r.covariates.get(name, float("nan")) for r in rows], dtype=float)
            if np.any(~np.isfinite(vals)) or np.any(vals <= 0):
                raise OutcomeModelRefused(f"passive covariate {name!r} is missing or non-positive in an admitted observation; "
                                          "a log model of it is inapplicable")
            cols[name] = np.log(vals)
        y = np.array([r.value for r in rows], dtype=float)
        if np.any(~np.isfinite(y)) or np.any(y <= 0):
            raise OutcomeModelRefused("the observable is non-positive or non-finite in an admitted observation: a model of "
                                      "ln(observable) is inapplicable")
        return cols, np.log(y)

    @staticmethod
    def _features(structure: Structure, cols: Mapping[str, np.ndarray]) -> np.ndarray:
        parts = [cols[n] for n in structure.linear] + [cols[n] ** 2 for n in structure.quadratic]
        n = len(next(iter(cols.values()))) if cols else 0
        return np.column_stack(parts) if parts else np.zeros((n, 0))

    @staticmethod
    def basis_digest(rows: Sequence[AdmittedObservation]) -> str:
        return _digest(sorted(r.evidence_digest for r in rows))

    def fit(self, structure: Structure, rows: Sequence[AdmittedObservation], key: str) -> FittedStructure:
        n, p = len(rows), structure.n_features
        basis = self.basis_digest(rows)
        if n < p + 4:
            return FittedStructure(structure, key, n, p, False, f"UNFIT: {n} observations, {p} features need >= {p + 4}",
                                   basis_digest=basis)
        cols, t = self._logs(rows)
        X = self._features(structure, cols)
        ybar = float(np.mean(t))
        yc = t - ybar
        sst = float(yc @ yc)
        if not sst > 1e-300:
            return FittedStructure(structure, key, n, p, False, "UNFIT: the observable has no spread", basis_digest=basis)
        if p == 0:
            s2 = sst / (n - 1)
            return FittedStructure(structure, key, n, 0, True, log_bf_null=0.0, r2=0.0, ybar=ybar, coef=np.zeros(0),
                                   means=np.zeros(0), inv=np.zeros((0, 0)), shrink=0.0, s2=s2, dof=n - 1, basis_digest=basis)
        means = X.mean(axis=0)
        Xc = X - means
        xtx = Xc.T @ Xc
        try:
            cond = np.linalg.cond(xtx)
        except np.linalg.LinAlgError:
            cond = math.inf
        if not math.isfinite(cond) or cond > 1e12:
            return FittedStructure(structure, key, n, p, False, "UNFIT: collinear features in this design (not identifiable)",
                                   basis_digest=basis)
        inv = np.linalg.inv(xtx)
        beta = inv @ (Xc.T @ yc)
        ssr = float(beta @ (xtx @ beta))
        r2 = min(max(ssr / sst, 0.0), 1.0 - 1e-15)
        log_bf = hyper_g_log_bf(n, p, r2)
        # estimation conditional on the structure uses the reference (flat) prior: the g-prior's shrinkage by g/(1+g)
        # serves model comparison only; applied to the coefficients it would bias every exponent toward zero
        sse = max(sst - ssr, 0.0)
        return FittedStructure(structure, key, n, p, True, log_bf_null=log_bf, r2=r2, ybar=ybar, coef=beta,
                               means=means, inv=inv, shrink=1.0, s2=sse / (n - 1 - p), dof=n - 1 - p, basis_digest=basis)

    # ---- covariate submodels ----------------------------------------------------------------------------------------
    def covariate_models(self, rows: Sequence[AdmittedObservation]) -> dict[str, CovariateModel]:
        out = {}
        if not rows or not self.problem.covariates:
            return out
        cols, _ = self._logs(rows)
        Z = np.column_stack([cols[n] for n in self.settable])
        for name in self.problem.covariates:
            w = cols[name]
            n, k = Z.shape
            if n >= k + 3:
                zm = Z.mean(axis=0)
                Zc = Z - zm
                coef, *_ = np.linalg.lstsq(Zc, w - w.mean(), rcond=None)
                resid = (w - w.mean()) - Zc @ coef
                rv = float(resid @ resid) / (n - k - 1)
                sst = float((w - w.mean()) @ (w - w.mean()))
                r2 = 1 - float(resid @ resid) / sst if sst > 0 else 0.0
                out[name] = CovariateModel(name, float(w.mean() - zm @ coef), tuple(float(c) for c in coef),
                                           tuple(self.settable), rv, r2)
            else:
                rv = float(np.var(w, ddof=1)) if n > 1 else float("inf")
                out[name] = CovariateModel(name, float(w.mean()), tuple(0.0 for _ in self.settable), tuple(self.settable), rv, 0.0)
        return out

    # ---- prediction --------------------------------------------------------------------------------------------------
    def predict_many(self, fitted: FittedStructure, points: Sequence[Mapping[str, float]],
                     covmodels: Mapping[str, CovariateModel]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(mean ln y, sd of the mean, sd of a new observation) at planned settings; covariates through their submodels."""
        m = len(points)
        if not fitted.fit_ok:
            nan = np.full(m, np.nan)
            return nan, nan, nan
        z = {n: np.log(np.array([pt[n] for pt in points], dtype=float)) for n in self.settable}
        extra_var = np.zeros(m)
        cols: dict[str, np.ndarray] = dict(z)
        for name in self.problem.covariates:
            if name in fitted.structure.linear:
                cm = covmodels[name]
                cols[name] = cm.mean + sum(c * z[nm] for c, nm in zip(cm.coef, cm.names))
                j = list(fitted.structure.linear).index(name)
                extra_var += float(fitted.coef[j]) ** 2 * cm.resid_var
        F = self._features(fitted.structure, cols) if fitted.p else np.zeros((m, 0))
        fc = F - fitted.means if fitted.p else F
        loc = fitted.ybar + (fc @ fitted.coef if fitted.p else 0.0)
        lev = fitted.shrink * np.einsum("ij,jk,ik->i", fc, fitted.inv, fc) if fitted.p else np.zeros(m)
        infl = fitted.dof / (fitted.dof - 2) if fitted.dof > 2 else math.inf
        var_mean = fitted.s2 * (1.0 / fitted.n + lev) * infl
        var_obs = var_mean + fitted.s2 * infl + extra_var
        return np.asarray(loc, dtype=float) * np.ones(m), np.sqrt(var_mean), np.sqrt(var_obs)

    def prediction(self, fitted: FittedStructure, point: Mapping[str, float], covmodels: Mapping[str, CovariateModel],
                   query_ref: str) -> OutcomePrediction:
        if not fitted.fit_ok:
            return OutcomePrediction(fitted.key, query_ref, False, None, None, None, None, fitted.basis_digest, reason=fitted.reason)
        loc, sdm, sdo = self.predict_many(fitted, [point], covmodels)
        return OutcomePrediction(fitted.key, query_ref, True, float(loc[0]), float(sdm[0]), float(sdo[0]), fitted.dof,
                                 fitted.basis_digest)

    def design_matrix(self, fitted: FittedStructure, points: Sequence[Mapping[str, float]],
                      covmodels: Mapping[str, CovariateModel]) -> np.ndarray:
        """Centred feature rows (for the expected-precision computation of a planned design)."""
        z = {n: np.log(np.array([pt[n] for pt in points], dtype=float)) for n in self.settable}
        cols: dict[str, np.ndarray] = dict(z)
        for name in self.problem.covariates:
            if name in fitted.structure.linear:
                cm = covmodels[name]
                cols[name] = cm.mean + sum(c * z[nm] for c, nm in zip(cm.coef, cm.names))
        F = self._features(fitted.structure, cols)
        return F - fitted.means if fitted.p else F


__all__ = ["HYPER_G_A", "hyper_g_log_bf", "AdmittedObservation", "CovariateModel", "FittedStructure", "OUTCOME_MODEL_ID", "OUTCOME_MODEL_VERSION",
           "OutcomeModel", "OutcomeModelRefused", "OutcomePrediction", "t_cdf", "t_logpdf"]
