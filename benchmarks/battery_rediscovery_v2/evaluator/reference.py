"""Reference truth table for the battery rediscovery v2 benchmark (independent implementation).

This module computes, from a problem specification alone (schema ``forge.mind.repsem.problem/1``), what a
correct answer on each of five axes is. It is written without reference to any candidate's code and it is
the oracle the candidates are scored against, so every rule it applies is stated here.

Forward model (first-order RC equivalent circuit, positive current = discharge)
-------------------------------------------------------------------------------
Exact piecewise-constant update with the BACKWARD hold: the current reported at sample k flowed over
``[t_(k-1), t_k]``. For k >= 1::

    z_k  = z_(k-1) - I_k (t_k - t_(k-1)) / Q
    a_k  = exp(-(t_k - t_(k-1)) / (R1 C1));   v1_k = a_k v1_(k-1) + R1 (1 - a_k) I_k
    V_k  = OCV(z_k) - I_k R0 - v1_k

with ``z_0 = initial_state.soc``, ``v1_0 = conditions.initial_polarization``, ``Q = conditions.capacity_As``
and ``V_0 = OCV(z_0) - I_0 R0 - v1_0``. ``OCV(z) = numpy.interp(z, knot_z, knot_V)`` (clamped at the ends)
over the measured knots (``rc1_measured_ocv/1``) or over ``ocv_knots_soc`` with fitted values ``ocv_k*``
(``rc1_fitted_ocv/1``). Residual ``r = V_pred - V_measured``; only samples k >= 1 of every trajectory are
scored. The linear recursion is evaluated blockwise in closed form (``exp(L_k - L_j)`` weights, never a
positive exponent), which is algebraically the recursion above.

Reference calibration (the oracle fit)
--------------------------------------
Least squares over the scored samples of all calibration trajectories, every parameter in ln-space inside its
declared bounds (``scipy.optimize.least_squares``, method "trf", xtol = ftol = gtol = 1e-12, max_nfev = 2000,
analytic Jacobian). Deterministic dense multistart:

* measured OCV: a 5x5x5 grid of starts over (R0, R1, C1) at ln-bound quantiles (0.1, 0.3, 0.5, 0.7, 0.9);
* fitted OCV: a 3x3x3 grid over (R0, R1, C1) at quantiles (0.2, 0.5, 0.8); for each, the K knot values are
  initialised by linear least squares given that R-part (OCV enters linearly through the interpolation
  weights of z, and z does not depend on the parameters), clipped to their bounds, then all parameters are
  refined jointly.

Every start's final cost (``0.5 * SSE``) and parameters are recorded. The optimum is the lowest cost (first
in start order on a tie).

Truth rules (margin M = 1.10)
-----------------------------
Each axis is ``{"truth": "SUPPORTED" | "NOT_SUPPORTED" | "NOT_ASSESSABLE" | None, "basis": str, ...}``.
``None`` is UNSCORED (marginal or rule-dependent); NOT_ASSESSABLE means the correct answer is a refusal.

1. MODEL_ADEQUACY. Calibration rmse and p95(|r|) at the optimum against ``adequacy_bar``: SUPPORTED if
   rmse <= rmse_max/M and p95 <= p95_abs_max/M; NOT_SUPPORTED if rmse > M*rmse_max or p95 > M*p95_abs_max;
   otherwise None.

2. IDENTIFIABILITY of the requested parameters (R0, R1, C1).

   * ``J = dr/d ln(theta)`` at the optimum over ALL parameters (analytic).
   * near-structural: every column of J normalised to unit norm; for each requested j, ``s_j`` is the norm of
     the component of column j orthogonal to the span of all other columns. ``min_j s_j < 1e-6`` ->
     NOT_SUPPORTED.
   * ambiguity: among the multistart results whose cost is within tol of the minimum (``delta cost <= 3.84
     sigma^2 / 2``, i.e. delta-SSE <= 3.84 sigma^2, when sigma is declared; relative cost difference <= 1e-6
     when sigma is None), a requested parameter differing from the optimum's by more than ln(1.5) in ln-space
     -> NOT_SUPPORTED.
   * sigma None: NOT_SUPPORTED if near-structural or ambiguous, else NOT_ASSESSABLE.
   * sigma declared: ``J_theta = J / theta`` per column; ``C_decl = inv(J_theta^T J_theta / sigma^2)`` over all
     parameters (no pseudo-inverse; a singular information matrix is NOT_SUPPORTED, basis "singular Fisher
     information"); ``sigma_infl = max(sigma, calibration rmse)`` and ``C_infl`` likewise. For each covariance
     the requested sub-block, mean = optimum, 95% interval mean +- 1.959963984540054 sd, and the frozen
     ``engcore.hybrid_uq.identifiability.classify`` under ``CANONICAL_IDENTIFIABILITY_THRESHOLDS``. on_bound: a
     requested parameter within 1e-6 (ln) of a bound.
     SUPPORTED iff status_decl == status_infl == IDENTIFIABLE and not on_bound, near-structural or ambiguous;
     NOT_SUPPORTED iff near-structural, ambiguous, singular, or status_decl == NOT_IDENTIFIABLE; else None.

3. WITHIN_CELL_GENERALIZATION (set ``within_unit_heldout``) and CROSS_CELL_TRANSFER (``cross_unit_heldout``).

   * absent or empty set -> NOT_ASSESSABLE ("no set supplied").
   * the domain is the calibration range: level_A and temperature_C min/max over all calibration samples, soc
     min/max of the reconstructed z over all calibration samples, each widened by ``applicability.widen[var]``
     (default 0); only the variables in ``applicability.variables`` are checked.
   * per subset, with the optimum parameters and no refit: pooled residuals over scored samples, rmse, p95.
     In-domain iff every listed variable's subset min >= lo - 1e-12 and max <= hi + 1e-12 (all samples) AND the
     unit relation holds (within: every unit_id is a calibration unit_id; cross: none is).
     In-domain label: SUPPORTED if rmse <= rmse_max/M and p95 <= p95_abs_max/M; NOT_SUPPORTED if
     rmse > M*rmse_max or p95 > M*p95_abs_max; else MARGINAL. Out-of-domain label: OOD_PASS if rmse <= rmse_max
     and p95 <= p95_abs_max; OOD_FAIL if rmse > M*rmse_max or p95 > M*p95_abs_max; else OOD_MARGINAL.
   * set truth: any in-domain NOT_SUPPORTED -> NOT_SUPPORTED; else any MARGINAL / OOD_FAIL / OOD_MARGINAL ->
     None; else any OOD_PASS -> NOT_ASSESSABLE; else SUPPORTED.

4. MODEL_DISCREPANCY.

   * sigma None -> NOT_ASSESSABLE (the measurement uncertainty is UNKNOWN; the plan defines no bound).
   * declared with half_width h: ``sd_pred = sqrt(mean over calibration scored samples of
     diag(J_theta C_infl J_theta^T))``; ``bound = h + 2 sd_pred``. NOT_SUPPORTED if rmse > M*bound;
     SUPPORTED if p95 <= bound/M; else None. Without a half_width, or with a singular covariance (so the
     parameter-induced spread is undefined), the axis is None: a missing number never becomes zero.

Output is JSON-serialisable: floats rounded to 12 significant digits, NaN/inf written as None. The same input
gives byte-identical ``json.dumps(..., sort_keys=True)`` output.
"""

from __future__ import annotations

import itertools
import math
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares

from engcore.hybrid_uq.identifiability import CANONICAL_IDENTIFIABILITY_THRESHOLDS, classify
from engcore.inference.calibration import IdentifiabilityStatus

SCHEMA = "forge.battery_rediscovery_v2.reference_truth/1"

MARGIN = 1.10
CHI2_95_1DOF = 3.84
Z95 = 1.959963984540054
AMBIGUITY_LN = math.log(1.5)
AMBIGUITY_REL_COST = 1e-6
NEAR_STRUCTURAL_TOL = 1e-6
ON_BOUND_LN = 1e-6
DOMAIN_EPS = 1e-12

MEASURED_FAMILY = "rc1_measured_ocv/1"
FITTED_FAMILY = "rc1_fitted_ocv/1"
R_NAMES = ("R0", "R1", "C1")
MEASURED_QUANTILES = (0.1, 0.3, 0.5, 0.7, 0.9)
FITTED_QUANTILES = (0.2, 0.5, 0.8)
LSQ_OPTIONS = {"method": "trf", "xtol": 1e-12, "ftol": 1e-12, "gtol": 1e-12, "max_nfev": 2000}

AXES = ("MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER",
        "MODEL_DISCREPANCY")
HELDOUT_SETS = (("WITHIN_CELL_GENERALIZATION", "within_unit_heldout", "within"),
                ("CROSS_CELL_TRANSFER", "cross_unit_heldout", "cross"))

SUPPORTED = "SUPPORTED"
NOT_SUPPORTED = "NOT_SUPPORTED"
NOT_ASSESSABLE = "NOT_ASSESSABLE"

_BLOCK = 16
_TRIL = np.tril(np.ones((_BLOCK, _BLOCK), dtype=bool))
_LNA_FLOOR = -700.0  # exp(-700) ~ 1e-304: below it a decay factor is zero to double precision


# --------------------------------------------------------------------------------------------- numerics


def _linrec(lna: np.ndarray, b: np.ndarray, x0: float) -> np.ndarray:
    """``x_k = exp(lna_k) x_(k-1) + b_k`` for k = 0..n-1 with ``x_(-1) = x0``.

    Blockwise closed form: inside a block of ``_BLOCK`` samples ``x_k = sum_(j<=k) exp(L_k - L_j) b_j +
    exp(L_k) x_in`` with ``L`` the in-block cumulative sum of ``lna``; only non-positive exponents are ever
    evaluated. The carry between blocks is the same recursion one level up.
    """
    lna = np.maximum(np.asarray(lna, dtype=np.float64), _LNA_FLOOR)
    b = np.asarray(b, dtype=np.float64)
    n = b.size
    if n == 0:
        return np.empty(0, dtype=np.float64)
    m = -(-n // _BLOCK)
    pad = m * _BLOCK - n
    if pad:
        lna = np.concatenate([lna, np.zeros(pad)])
        b = np.concatenate([b, np.zeros(pad)])
    L = np.cumsum(lna.reshape(m, _BLOCK), axis=1)
    D = np.where(_TRIL, L[:, :, None] - L[:, None, :], -np.inf)
    y = np.einsum("ikj,ij->ik", np.exp(D), b.reshape(m, _BLOCK))
    if m == 1:
        carry = np.array([x0], dtype=np.float64)
    else:
        ends = _linrec(L[:, -1], y[:, -1], x0)
        carry = np.concatenate([[float(x0)], ends[:-1]])
    x = y + np.exp(L) * carry[:, None]
    return x.ravel()[:n]


def _interp_weights(z: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """Rows ``w(z)`` with ``w(z) @ values == numpy.interp(z, knots, values)`` (clamped ends)."""
    n, k = z.size, knots.size
    w = np.zeros((n, k), dtype=np.float64)
    below = z <= knots[0]
    above = z >= knots[-1]
    mid = ~(below | above)
    rows = np.nonzero(mid)[0]
    idx = np.clip(np.searchsorted(knots, z[mid], side="right") - 1, 0, k - 2)
    frac = (z[mid] - knots[idx]) / (knots[idx + 1] - knots[idx])
    w[rows, idx] = 1.0 - frac
    w[rows, idx + 1] = frac
    w[below, 0] = 1.0
    w[above, -1] = 1.0
    return w


def _stats(r: np.ndarray) -> dict[str, Any]:
    if r.size == 0:
        raise ValueError("no scored samples")
    a = np.abs(r)
    return {"n": int(r.size), "rmse": float(np.sqrt(np.mean(r * r))), "p95_abs": float(np.percentile(a, 95.0)),
            "bias": float(np.mean(r)), "max_abs": float(np.max(a))}


# ----------------------------------------------------------------------------------------- the problem


class _Trajectory:
    """One trajectory's columns, its reconstructed SOC and the boundary conditions the model needs."""

    def __init__(self, payload: Mapping[str, Any], *, extra_columns: Sequence[str] = ()):
        self.id = str(payload["id"])
        self.unit_id = str(payload["unit_id"])
        columns = payload["columns"]
        self.t = np.asarray(columns["t_s"], dtype=np.float64)
        self.current = np.asarray(columns["current_A"], dtype=np.float64)
        self.voltage = np.asarray(columns["voltage_V"], dtype=np.float64)
        n = self.t.size
        if n < 2:
            raise ValueError(f"trajectory {self.id!r} has fewer than two samples, so nothing of it is scored")
        self.columns: dict[str, np.ndarray] = {}
        for name in ("t_s", "current_A", "voltage_V", *extra_columns):
            if name not in columns:
                raise ValueError(f"trajectory {self.id!r} has no column {name!r}")
            values = np.asarray(columns[name], dtype=np.float64)
            if values.shape != (n,) or not np.all(np.isfinite(values)):
                raise ValueError(f"trajectory {self.id!r}: column {name!r} is not {n} finite numbers")
            self.columns[name] = values
        self.dt = np.diff(self.t)
        if np.any(self.dt < 0.0):
            raise ValueError(f"trajectory {self.id!r}: time runs backwards")
        conditions = payload["conditions"]
        if "initial_polarization" not in conditions or "capacity_As" not in conditions:
            raise ValueError(f"trajectory {self.id!r}: initial_polarization and capacity_As are both required")
        self.p0 = float(conditions["initial_polarization"])
        self.capacity = float(conditions["capacity_As"])
        if not (self.capacity > 0.0 and math.isfinite(self.capacity) and math.isfinite(self.p0)):
            raise ValueError(f"trajectory {self.id!r}: capacity_As must be positive and finite")
        z0 = float(payload["initial_state"]["soc"])
        self.soc = np.empty(n, dtype=np.float64)
        self.soc[0] = z0
        self.soc[1:] = z0 - np.cumsum(self.current[1:] * self.dt) / self.capacity

    def variable(self, name: str) -> np.ndarray:
        return self.soc if name == "soc" else self.columns[name]


class _Model:
    """The declared family: parameter names, ln-bounds and the forward model with its ln-Jacobian."""

    def __init__(self, family: Mapping[str, Any]):
        self.family_id = family["family_id"]
        bounds = family["parameter_bounds"]
        constants = family.get("constants", {})
        if self.family_id == MEASURED_FAMILY:
            knots = np.asarray(constants["ocv_knots"], dtype=np.float64)
            if knots.ndim != 2 or knots.shape[1] != 2:
                raise ValueError("ocv_knots must be [[z, V], ...]")
            self.knot_z, self.knot_v = knots[:, 0].copy(), knots[:, 1].copy()
            self.fitted = False
            self.names = R_NAMES
        elif self.family_id == FITTED_FAMILY:
            self.knot_z = np.asarray(constants["ocv_knots_soc"], dtype=np.float64)
            self.knot_v = None
            self.fitted = True
            self.names = R_NAMES + tuple(f"ocv_k{j}" for j in range(self.knot_z.size))
        else:
            raise ValueError(f"unknown family {self.family_id!r}")
        if self.knot_z.size < 2 or np.any(np.diff(self.knot_z) <= 0.0):
            raise ValueError("OCV knots must be at least two strictly increasing SOC values")
        lo, hi = [], []
        for name in self.names:
            if name not in bounds:
                raise ValueError(f"no declared bounds for parameter {name!r}")
            a, b = (float(v) for v in bounds[name])
            if not (0.0 < a < b and math.isfinite(b)):
                raise ValueError(f"bounds for {name!r} must satisfy 0 < lo < hi < inf, got {[a, b]}")
            lo.append(math.log(a))
            hi.append(math.log(b))
        self.ln_lo = np.asarray(lo)
        self.ln_hi = np.asarray(hi)
        self.p = len(self.names)

    def ocv_values(self, theta: np.ndarray) -> np.ndarray:
        return theta[3:] if self.fitted else self.knot_v

    def simulate(self, tr: _Trajectory, theta: np.ndarray, want_jac: bool):
        """Predicted voltage at every sample and, optionally, ``dV/d ln(theta)`` at every sample."""
        r0, r1, c1 = float(theta[0]), float(theta[1]), float(theta[2])
        tau = r1 * c1
        values = self.ocv_values(theta)
        current = tr.current
        lna = -tr.dt / tau
        one_minus_a = -np.expm1(lna)
        i_next = current[1:]
        n = current.size
        v1 = np.empty(n, dtype=np.float64)
        v1[0] = tr.p0
        v1[1:] = _linrec(lna, r1 * one_minus_a * i_next, tr.p0)
        prediction = np.interp(tr.soc, self.knot_z, values) - current * r0 - v1
        if not want_jac:
            return prediction, None
        jac = np.zeros((n, self.p), dtype=np.float64)
        jac[:, 0] = -current * r0
        # s = dv1/dR1 at fixed tau; tq = tau * dv1/dtau, with tau da/dtau = a * (-lna)
        s = _linrec(lna, one_minus_a * i_next, 0.0)
        g = np.exp(lna) * (-lna)
        tq = _linrec(lna, g * (v1[:-1] - r1 * i_next), 0.0)
        jac[1:, 1] = -(r1 * s + tq)  # d/dlnR1 = R1 d/dR1|tau + tau d/dtau
        jac[1:, 2] = -tq  # d/dlnC1 = tau d/dtau
        if self.fitted:
            jac[:, 3:] = _interp_weights(tr.soc, self.knot_z) * values[None, :]
        return prediction, jac


def _residuals(model: _Model, trajectories: Sequence[_Trajectory], theta: np.ndarray, want_jac: bool):
    rs, js = [], []
    for tr in trajectories:
        prediction, jac = model.simulate(tr, theta, want_jac)
        rs.append(prediction[1:] - tr.voltage[1:])
        if want_jac:
            js.append(jac[1:])
    r = np.concatenate(rs)
    return r, (np.concatenate(js, axis=0) if want_jac else None)


# ------------------------------------------------------------------------------------------ the fit


def _starts(model: _Model, calibration: Sequence[_Trajectory]) -> list[np.ndarray]:
    quantiles = FITTED_QUANTILES if model.fitted else MEASURED_QUANTILES
    span = model.ln_hi[:3] - model.ln_lo[:3]
    starts = []
    for q in itertools.product(quantiles, repeat=3):
        x_r = model.ln_lo[:3] + np.asarray(q) * span
        if not model.fitted:
            starts.append(x_r)
            continue
        theta_r = np.exp(x_r)
        r0, r1, c1 = theta_r
        tau = r1 * c1
        rows, targets = [], []
        for tr in calibration:
            lna = -tr.dt / tau
            v1 = _linrec(lna, r1 * (-np.expm1(lna)) * tr.current[1:], tr.p0)
            # V_meas = W y - I R0 - v1  ->  W y = V_meas + I R0 + v1 on the scored samples
            targets.append(tr.voltage[1:] + tr.current[1:] * r0 + v1)
            rows.append(_interp_weights(tr.soc[1:], model.knot_z))
        y, *_ = np.linalg.lstsq(np.concatenate(rows, axis=0), np.concatenate(targets), rcond=None)
        y = np.clip(y, np.exp(model.ln_lo[3:]), np.exp(model.ln_hi[3:]))
        starts.append(np.concatenate([x_r, np.clip(np.log(y), model.ln_lo[3:], model.ln_hi[3:])]))
    return starts


def _fit(model: _Model, calibration: Sequence[_Trajectory]) -> dict[str, Any]:
    def fun(x):
        return _residuals(model, calibration, np.exp(x), False)[0]

    def jac(x):
        return _residuals(model, calibration, np.exp(x), True)[1]

    records = []
    for index, x0 in enumerate(_starts(model, calibration)):
        result = least_squares(fun, x0, jac=jac, bounds=(model.ln_lo, model.ln_hi), **LSQ_OPTIONS)
        x = np.clip(result.x, model.ln_lo, model.ln_hi)
        r = fun(x)
        records.append({"index": index, "x0": np.asarray(x0, dtype=np.float64), "x": x,
                        "cost": float(0.5 * np.dot(r, r)), "nfev": int(result.nfev), "status": int(result.status)})
    costs = np.asarray([rec["cost"] for rec in records])
    best = int(np.argmin(costs))
    return {"starts": records, "best": best}


# ------------------------------------------------------------------------------------- the analysis


def _noise(spec: Mapping[str, Any]) -> tuple[float | None, float | None, str]:
    noise = spec.get("measurement_noise") or {}
    sigma = noise.get("sigma")
    sigma = None if sigma is None else float(sigma)
    if sigma is not None and not (sigma > 0.0 and math.isfinite(sigma)):
        raise ValueError(f"a declared sigma must be positive and finite, got {sigma!r}")
    half = noise.get("half_width")
    half = None if half is None else float(half)
    return sigma, half, str(noise.get("status"))


def _bar(entry: Mapping[str, Any]) -> tuple[float, float]:
    return float(entry["rmse_max"]), float(entry["p95_abs_max"])


def _graded(rmse: float, p95: float, rmse_max: float, p95_max: float) -> str | None:
    """SUPPORTED / NOT_SUPPORTED / None under margin M."""
    if rmse > MARGIN * rmse_max or p95 > MARGIN * p95_max:
        return NOT_SUPPORTED
    if rmse <= rmse_max / MARGIN and p95 <= p95_max / MARGIN:
        return SUPPORTED
    return None


def _covariance_ln(jac: np.ndarray, sigma: float) -> np.ndarray | None:
    """``inv(J^T J / sigma^2)`` in ln-coordinates, or None when the information matrix is singular.

    ``C_theta = diag(theta) C_ln diag(theta)`` is algebraically ``inv(J_theta^T J_theta / sigma^2)``; the
    ln-space form is inverted because its columns share a scale (theta spans ~1e-3 to ~1e4 here).
    """
    p = jac.shape[1]
    norms = np.linalg.norm(jac, axis=0)
    if np.any(norms == 0.0) or not np.all(np.isfinite(norms)):
        return None
    if np.linalg.matrix_rank(jac / norms) < p:
        return None
    fisher = jac.T @ jac / (sigma * sigma)
    try:
        np.linalg.cholesky(fisher)
        cov = np.linalg.inv(fisher)
    except np.linalg.LinAlgError:
        return None
    cov = 0.5 * (cov + cov.T)
    if not np.all(np.isfinite(cov)) or np.any(np.diag(cov) <= 0.0):
        return None
    return cov


def _orthogonal_norms(jac: np.ndarray, requested: Sequence[int]) -> list[float]:
    norms = np.linalg.norm(jac, axis=0)
    unit = np.divide(jac, norms, out=np.zeros_like(jac), where=norms > 0.0)
    out = []
    for j in requested:
        if norms[j] == 0.0:
            out.append(0.0)
            continue
        others = np.delete(unit, j, axis=1)
        if others.shape[1] == 0:
            out.append(1.0)
            continue
        coef, *_ = np.linalg.lstsq(others, unit[:, j], rcond=None)
        out.append(float(np.linalg.norm(unit[:, j] - others @ coef)))
    return out


def _identifiability(spec, model, fit, x_opt, jac, cal_stats, sigma) -> tuple[dict, dict]:
    names = list(spec.get("requested_parameters", list(R_NAMES)))
    requested = [model.names.index(name) for name in names]
    theta = np.exp(x_opt)

    s = _orthogonal_norms(jac, requested)
    near = min(s) < NEAR_STRUCTURAL_TOL

    best_cost = fit["starts"][fit["best"]]["cost"]
    if sigma is not None:
        tol = CHI2_95_1DOF * sigma * sigma / 2.0
        tied = [rec for rec in fit["starts"] if rec["cost"] - best_cost <= tol]
        tie_rule = f"delta cost <= 3.84 sigma^2 / 2 = {tol:.6g}"
    else:
        tied = [rec for rec in fit["starts"] if rec["cost"] - best_cost <= AMBIGUITY_REL_COST * best_cost]
        tie_rule = "relative cost difference <= 1e-06"
    deviation = {name: max(abs(float(rec["x"][j] - x_opt[j])) for rec in tied) for name, j in zip(names, requested)}
    ambiguous = any(v > AMBIGUITY_LN for v in deviation.values())

    on_bound = [name for name, j in zip(names, requested)
                if x_opt[j] - model.ln_lo[j] <= ON_BOUND_LN or model.ln_hi[j] - x_opt[j] <= ON_BOUND_LN]

    entry: dict[str, Any] = {
        "requested_parameters": names, "orthogonal_norms": dict(zip(names, s)), "near_structural": near,
        "ambiguity_rule": tie_rule, "starts_within_tolerance": len(tied), "max_ln_deviation_within_tolerance": deviation,
        "ambiguous": ambiguous, "on_bound": on_bound, "sigma": sigma,
    }
    structural = []
    if near:
        structural.append(f"near-structural: min orthogonal norm {min(s):.3g} < {NEAR_STRUCTURAL_TOL:g}")
    if ambiguous:
        worst = max(deviation, key=lambda k: deviation[k])
        structural.append(f"ambiguous: {len(tied)} start(s) within tolerance and {worst} differs by "
                          f"{deviation[worst]:.3g} > ln(1.5) in ln-space")

    covariances: dict[str, Any] = {"declared_ln": None, "inflated_ln": None, "sigma_inflated": None}
    if sigma is None:
        if structural:
            entry.update(truth=NOT_SUPPORTED, basis="; ".join(structural))
        else:
            entry.update(truth=NOT_ASSESSABLE, basis="measurement sigma is UNKNOWN, so no interval can be stated; "
                                                    "neither near-structural nor ambiguous")
        return entry, covariances

    sigma_infl = max(sigma, cal_stats["rmse"])
    covariances["sigma_inflated"] = sigma_infl
    entry["sigma_inflated"] = sigma_infl
    cov_decl = _covariance_ln(jac, sigma)
    if cov_decl is None:
        entry.update(singular=True, truth=NOT_SUPPORTED,
                     basis="; ".join(structural + ["singular Fisher information"]))
        return entry, covariances
    cov_infl = cov_decl * (sigma_infl / sigma) ** 2
    covariances["declared_ln"] = cov_decl
    covariances["inflated_ln"] = cov_infl
    entry["singular"] = False

    mean = theta[requested]
    statuses = {}
    for label, cov_ln in (("declared", cov_decl), ("inflated", cov_infl)):
        cov_theta = cov_ln * np.outer(theta, theta)
        sub = cov_theta[np.ix_(requested, requested)]
        sd = np.sqrt(np.diag(sub))
        lows, highs = mean - Z95 * sd, mean + Z95 * sd
        status, condition, max_corr, widths, why = classify(
            list(mean), sub, list(lows), list(highs), names, **CANONICAL_IDENTIFIABILITY_THRESHOLDS)
        statuses[label] = status
        entry[label] = {"status": status.value, "condition_number": condition, "max_abs_correlation": max_corr,
                        "relative_widths": dict(zip(names, widths)), "sd": dict(zip(names, sd)),
                        "interval_95": {n: [lo, hi] for n, lo, hi in zip(names, lows, highs)}, "why": why}
    decl, infl = statuses["declared"], statuses["inflated"]
    if structural:
        entry.update(truth=NOT_SUPPORTED, basis="; ".join(structural))
    elif decl is IdentifiabilityStatus.NOT_IDENTIFIABLE:
        entry.update(truth=NOT_SUPPORTED, basis=f"declared-sigma classification is {decl.value}")
    elif decl is IdentifiabilityStatus.IDENTIFIABLE and infl is IdentifiabilityStatus.IDENTIFIABLE and not on_bound:
        entry.update(truth=SUPPORTED, basis="declared and inflated classifications are both IDENTIFIABLE, no "
                                            "parameter on a bound, not near-structural, not ambiguous")
    else:
        reasons = [f"declared {decl.value}", f"inflated {infl.value}"]
        if on_bound:
            reasons.append(f"on bound: {on_bound}")
        entry.update(truth=None, basis="unscored: " + ", ".join(reasons))
    return entry, covariances


def _discrepancy(cal_stats, sigma, half, jac, theta, cov_infl_ln) -> dict:
    entry: dict[str, Any] = {"rmse": cal_stats["rmse"], "p95_abs": cal_stats["p95_abs"], "sigma": sigma,
                             "half_width": half}
    if sigma is None:
        entry.update(truth=NOT_ASSESSABLE, basis="the measurement uncertainty is UNKNOWN; the plan defines no "
                                                 "discrepancy bound")
        return entry
    if half is None:
        entry.update(truth=None, basis="unscored: sigma is declared but no half_width is, so no bound is defined")
        return entry
    if cov_infl_ln is None:
        entry.update(truth=None, basis="unscored: the parameter covariance is singular, so the parameter-induced "
                                       "predictive spread is undefined")
        return entry
    # diag(J_theta C_theta J_theta^T) == diag(J C_ln J^T)
    variance = np.einsum("ij,jk,ik->i", jac, cov_infl_ln, jac)
    sd_pred = float(math.sqrt(max(float(np.mean(variance)), 0.0)))
    bound = half + 2.0 * sd_pred
    entry.update(sd_pred=sd_pred, bound=bound)
    if cal_stats["rmse"] > MARGIN * bound:
        entry.update(truth=NOT_SUPPORTED, basis=f"rmse {cal_stats['rmse']:.6g} > M * bound {MARGIN * bound:.6g}")
    elif cal_stats["p95_abs"] <= bound / MARGIN:
        entry.update(truth=SUPPORTED, basis=f"p95 {cal_stats['p95_abs']:.6g} <= bound / M {bound / MARGIN:.6g}")
    else:
        entry.update(truth=None, basis="unscored: between the margins")
    return entry


def _domain(spec, calibration: Sequence[_Trajectory]) -> dict[str, dict[str, float]]:
    applicability = spec.get("applicability") or {}
    widen = applicability.get("widen") or {}
    domain = {}
    for var in applicability.get("variables", []):
        values = np.concatenate([tr.variable(var) for tr in calibration])
        w = float(widen.get(var, 0.0))
        domain[var] = {"min": float(values.min()), "max": float(values.max()), "widen": w,
                       "lo": float(values.min()) - w, "hi": float(values.max()) + w}
    return domain


def _heldout(spec, model, theta, calibration_units, domain, set_key, relation, extra) -> tuple[dict, dict]:
    subsets = (spec.get("sets") or {}).get(set_key) or {}
    subsets = {name: trajs for name, trajs in subsets.items() if trajs}
    if not subsets:
        return {"truth": NOT_ASSESSABLE, "basis": "no set supplied", "subsets": {}}, {}
    acceptance = spec.get("acceptance") or {}
    per_subset = {}
    for name in sorted(subsets):
        key = f"{set_key}/{name}"
        if key not in acceptance:
            raise ValueError(f"no acceptance bar for {key!r}")
        rmse_max, p95_max = _bar(acceptance[key])
        trajectories = [_Trajectory(t, extra_columns=extra) for t in subsets[name]]
        residuals = np.concatenate([model.simulate(tr, theta, False)[0][1:] - tr.voltage[1:] for tr in trajectories])
        stats = _stats(residuals)
        units = sorted({tr.unit_id for tr in trajectories})
        if relation == "within":
            unit_ok = all(u in calibration_units for u in units)
        else:
            unit_ok = not any(u in calibration_units for u in units)
        outside = {}
        for var, rng in domain.items():
            values = np.concatenate([tr.variable(var) for tr in trajectories])
            vmin, vmax = float(values.min()), float(values.max())
            if vmin < rng["lo"] - DOMAIN_EPS or vmax > rng["hi"] + DOMAIN_EPS:
                outside[var] = {"min": vmin, "max": vmax, "lo": rng["lo"], "hi": rng["hi"],
                                "below_by": max(rng["lo"] - vmin, 0.0), "above_by": max(vmax - rng["hi"], 0.0)}
        in_domain = unit_ok and not outside
        if in_domain:
            graded = _graded(stats["rmse"], stats["p95_abs"], rmse_max, p95_max)
            label = {SUPPORTED: "SUPPORTED", NOT_SUPPORTED: "NOT_SUPPORTED", None: "MARGINAL"}[graded]
        elif stats["rmse"] <= rmse_max and stats["p95_abs"] <= p95_max:
            label = "OOD_PASS"
        elif stats["rmse"] > MARGIN * rmse_max or stats["p95_abs"] > MARGIN * p95_max:
            label = "OOD_FAIL"
        else:
            label = "OOD_MARGINAL"
        per_subset[name] = {"units": units, "trajectories": [tr.id for tr in trajectories],
                            "unit_relation": relation, "unit_relation_holds": unit_ok, "in_domain": in_domain,
                            "outside": outside, "rmse": stats["rmse"], "p95_abs": stats["p95_abs"],
                            "bias": stats["bias"], "max_abs": stats["max_abs"], "n_scored": stats["n"],
                            "rmse_max": rmse_max, "p95_abs_max": p95_max, "label": label}
    labels = [s["label"] for s in per_subset.values()]
    if "NOT_SUPPORTED" in labels:
        truth, basis = NOT_SUPPORTED, "an in-domain subset fails its acceptance bar beyond the margin"
    elif any(lab in ("MARGINAL", "OOD_FAIL", "OOD_MARGINAL") for lab in labels):
        truth, basis = None, "unscored: a subset is marginal or out of domain without a clean pass"
    elif "OOD_PASS" in labels:
        truth, basis = NOT_ASSESSABLE, "every in-domain subset passes but a subset lies outside the calibration domain"
    else:
        truth, basis = SUPPORTED, "every subset is in domain and passes its acceptance bar with margin"
    entry = {"truth": truth, "basis": basis, "subsets": {k: {"label": v["label"], "in_domain": v["in_domain"]}
                                                         for k, v in per_subset.items()}}
    return entry, per_subset


def _analyse(spec: Mapping[str, Any]) -> dict[str, Any]:
    model = _Model(spec["declared_family"])
    extra = [v for v in (spec.get("applicability") or {}).get("variables", []) if v != "soc"]
    calibration = [_Trajectory(t, extra_columns=extra) for t in spec["sets"]["calibration"]]
    if not calibration:
        raise ValueError("no calibration trajectories")
    fit = _fit(model, calibration)
    x_opt = fit["starts"][fit["best"]]["x"]
    theta = np.exp(x_opt)
    residuals, jac = _residuals(model, calibration, theta, True)
    cal_stats = _stats(residuals)
    sigma, half, noise_status = _noise(spec)
    ident, covariances = _identifiability(spec, model, fit, x_opt, jac, cal_stats, sigma)
    return {"model": model, "calibration": calibration, "fit": fit, "x_opt": x_opt, "theta": theta,
            "residuals": residuals, "jac": jac, "cal_stats": cal_stats, "sigma": sigma, "half": half,
            "noise_status": noise_status, "identifiability": ident, "covariances": covariances, "extra": extra}


# ------------------------------------------------------------------------------------------- output


def _clean(value: Any) -> Any:
    """JSON-safe: floats to 12 significant digits, NaN/inf to None, numpy and enums unwrapped."""
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        x = float(value)
        if not math.isfinite(x):
            return None
        x = float(f"{x:.12g}")
        return 0.0 if x == 0.0 else x
    if isinstance(value, Enum):
        return value.value
    return value


def _starts_record(model: _Model, fit: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"index": rec["index"], "start": dict(zip(model.names, np.exp(rec["x0"]))),
             "final": dict(zip(model.names, np.exp(rec["x"]))), "cost": rec["cost"], "nfev": rec["nfev"],
             "status": rec["status"]} for rec in fit["starts"]]


def _theta_cov(cov_ln, theta):
    return None if cov_ln is None else cov_ln * np.outer(theta, theta)


def reference_fit(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The oracle fit: optimum, every start, calibration residual statistics, ln-Jacobian and covariances."""
    a = _analyse(spec)
    model, theta, cov = a["model"], a["theta"], a["covariances"]
    best = a["fit"]["starts"][a["fit"]["best"]]
    return _clean({
        "schema": SCHEMA + "#fit", "family_id": model.family_id, "parameter_names": list(model.names),
        "optimum": dict(zip(model.names, theta)), "optimum_ln": a["x_opt"], "best_start": a["fit"]["best"],
        "cost": best["cost"], "starts": _starts_record(model, a["fit"]), "residuals": a["cal_stats"],
        "jacobian_ln": a["jac"], "sigma": a["sigma"], "sigma_inflated": cov["sigma_inflated"],
        "covariance_declared": _theta_cov(cov["declared_ln"], theta),
        "covariance_inflated": _theta_cov(cov["inflated_ln"], theta),
    })


def truth_table(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The correct answer on each of the five axes, plus a diagnostics block."""
    a = _analyse(spec)
    model, theta, cal_stats = a["model"], a["theta"], a["cal_stats"]
    table: dict[str, Any] = {}

    rmse_max, p95_max = _bar(spec["adequacy_bar"])
    graded = _graded(cal_stats["rmse"], cal_stats["p95_abs"], rmse_max, p95_max)
    table["MODEL_ADEQUACY"] = {
        "truth": graded, "rmse": cal_stats["rmse"], "p95_abs": cal_stats["p95_abs"], "rmse_max": rmse_max,
        "p95_abs_max": p95_max,
        "basis": {SUPPORTED: "calibration rmse and p95 within the adequacy bar divided by the margin",
                  NOT_SUPPORTED: "calibration rmse or p95 exceeds the adequacy bar times the margin",
                  None: "unscored: within the margin band of the adequacy bar"}[graded],
    }
    table["IDENTIFIABILITY"] = a["identifiability"]

    domain = _domain(spec, a["calibration"])
    calibration_units = {tr.unit_id for tr in a["calibration"]}
    subsets_diag = {}
    for axis, set_key, relation in HELDOUT_SETS:
        entry, per = _heldout(spec, model, theta, calibration_units, domain, set_key, relation, a["extra"])
        table[axis] = entry
        subsets_diag[set_key] = per

    table["MODEL_DISCREPANCY"] = _discrepancy(cal_stats, a["sigma"], a["half"], a["jac"], theta,
                                              a["covariances"]["inflated_ln"])

    fit = a["fit"]
    costs = [rec["cost"] for rec in fit["starts"]]
    table["diagnostics"] = {
        "schema": SCHEMA, "family_id": model.family_id, "margin": MARGIN,
        "parameters": dict(zip(model.names, theta)), "cost": costs[fit["best"]],
        "calibration": cal_stats, "noise_status": a["noise_status"],
        "starts": {"count": len(costs), "best": fit["best"], "cost_min": min(costs), "cost_max": max(costs),
                   "hit_max_nfev": sum(1 for rec in fit["starts"] if rec["status"] == 0)},
        "calibration_units": sorted(calibration_units), "domain": domain, "subsets": subsets_diag,
    }
    return _clean(table)
