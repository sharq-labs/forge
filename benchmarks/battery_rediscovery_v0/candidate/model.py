"""The declared model family (Thevenin 1RC, and Rint as its R1 = 0 reduction): forward model, calibration, diagnostics.

Exact piecewise-constant update.  With the BACKWARD hold the current reported at sample k flowed over [t_(k-1), t_k];
the FORWARD hold (current of sample k-1) is used only as the switch-time sensitivity.  For sample k >= 1:

    z_k  = z_(k-1) - I_k dt / (3600 Q)
    a    = exp(-dt / (R1 C1))
    v1_k = a v1_(k-1) + R1 (1 - a) I_k
    V_k  = OCV(z_k) - I_k R0 - v1_k

z does not depend on the parameters, so the OCV enters linearly through fixed interpolation weights.  The residual
Jacobian is analytic: with s = d v1 / d ln(tau) (tau = R1 C1), d/d ln R1 = v1 + s and d/d ln C1 = s.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares

from .common import Trajectory

N_STARTS = 8
START_SEED = 0
CONVERGED_SSE_RATIO = 1.01


@dataclass
class Batch:
    """Trajectories padded to one array; ``mask`` marks scored samples (every real sample after the first)."""

    t: np.ndarray
    current: np.ndarray
    voltage: np.ndarray
    temperature: np.ndarray
    dt: np.ndarray
    i_used: np.ndarray
    z: np.ndarray
    mask: np.ndarray
    lengths: np.ndarray
    ids: tuple[str, ...]

    @classmethod
    def build(cls, trajs: Sequence[Trajectory], hold: str = "backward") -> "Batch":
        n, L = len(trajs), max(len(tr.t) for tr in trajs)
        t = np.zeros((n, L)); cur = np.zeros((n, L)); v = np.zeros((n, L)); temp = np.zeros((n, L))
        dt = np.zeros((n, L)); used = np.zeros((n, L)); z = np.zeros((n, L)); mask = np.zeros((n, L), bool)
        for i, tr in enumerate(trajs):
            m = len(tr.t)
            t[i, :m], cur[i, :m], v[i, :m], temp[i, :m] = tr.t, tr.current, tr.voltage, tr.temperature
            dt[i, 1:m] = np.diff(tr.t)
            if hold == "backward":
                used[i, 1:m] = tr.current[1:]
            elif hold == "forward":
                used[i, 1:m] = tr.current[:-1]
            else:
                raise ValueError(f"unknown hold convention {hold!r}")
            z[i, :m] = tr.z0 - np.concatenate([[0.0], np.cumsum(used[i, 1:m] * dt[i, 1:m])]) / (3600.0 * tr.capacity_Ah)
            z[i, m:] = z[i, m - 1]
            mask[i, 1:m] = True
        return cls(t, cur, v, temp, dt, used, z, mask, np.array([len(tr.t) for tr in trajs]), tuple(tr.traj_id for tr in trajs))


def interp_weights(z: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """Linear-interpolation weights of every z on the knot grid (constant beyond the end knots), shape z.shape + (K,)."""
    K = len(knots)
    zc = np.clip(z, knots[0], knots[-1])
    j = np.clip(np.searchsorted(knots, zc, side="right") - 1, 0, K - 2)
    w = (zc - knots[j]) / (knots[j + 1] - knots[j])
    out = np.zeros(z.shape + (K,))
    np.put_along_axis(out, j[..., None], (1 - w)[..., None], axis=-1)
    np.put_along_axis(out, (j + 1)[..., None], w[..., None], axis=-1)
    return out


def rc_branch(batch: Batch, R1: float, C1: float) -> tuple[np.ndarray, np.ndarray]:
    """v1 and s = d v1 / d ln(tau) along every trajectory (padding has dt = 0: the state is held)."""
    n, L = batch.t.shape
    tau = R1 * C1
    v = np.zeros(n); s = np.zeros(n)
    V1 = np.zeros((n, L)); S = np.zeros((n, L))
    for k in range(1, L):
        dt = batch.dt[:, k]
        a = np.exp(-dt / tau)
        da = a * dt / tau
        i = batch.i_used[:, k]
        s = a * s + da * (v - R1 * i)
        v = a * v + R1 * (1.0 - a) * i
        V1[:, k], S[:, k] = v, s
    return V1, S


@dataclass(frozen=True)
class ModelSpec:
    """What is fitted: ``rc`` (1RC) or not (Rint); the OCV is a fitted table (``knots_soc``) or fixed (``fixed_knots``)."""

    rc: bool
    bounds: Mapping[str, tuple[float, float]]
    knots_soc: np.ndarray | None = None
    ocv_bounds: tuple[float, float] | None = None
    fixed_knots: np.ndarray | None = None

    @classmethod
    def from_declared(cls, declared: Mapping[str, Any], *, rc: bool = True) -> "ModelSpec":
        b = declared["bounds"]
        bounds = {"R0": tuple(b["R0_ohm"]), "R1": tuple(b["R1_ohm"]), "C1": tuple(b["C1_F"])}
        ocv = declared["ocv"]
        if ocv["status"] == "MEASURED_FIXED":
            return cls(rc, bounds, fixed_knots=np.asarray(ocv["knots_z_V"], float))
        return cls(rc, bounds, knots_soc=np.asarray(ocv["knots_soc"], float), ocv_bounds=tuple(ocv["bounds_V"]))

    @property
    def names(self) -> list[str]:
        base = ["lnR0", "lnR1", "lnC1"] if self.rc else ["lnR0"]
        return base + ([f"ocv{j}" for j in range(len(self.knots_soc))] if self.knots_soc is not None else [])

    def bounds_vectors(self) -> tuple[np.ndarray, np.ndarray]:
        lo = [math.log(self.bounds["R0"][0])]; hi = [math.log(self.bounds["R0"][1])]
        if self.rc:
            lo += [math.log(self.bounds["R1"][0]), math.log(self.bounds["C1"][0])]
            hi += [math.log(self.bounds["R1"][1]), math.log(self.bounds["C1"][1])]
        if self.knots_soc is not None:
            lo += [self.ocv_bounds[0]] * len(self.knots_soc); hi += [self.ocv_bounds[1]] * len(self.knots_soc)
        return np.array(lo), np.array(hi)


class Evaluator:
    """Residuals and Jacobian of one model on one batch."""

    def __init__(self, spec: ModelSpec, batch: Batch) -> None:
        self.spec, self.batch = spec, batch
        if spec.fixed_knots is not None:
            k = spec.fixed_knots
            self.ocv_fixed = np.interp(batch.z, k[:, 0], k[:, 1])
            self.W = None
        else:
            self.ocv_fixed = None
            self.W = interp_weights(batch.z, spec.knots_soc)
        self.sel = batch.mask

    def predict(self, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Predicted voltage (n, L) and d V_pred / d theta (n, L, p)."""
        b, spec = self.batch, self.spec
        R0 = math.exp(theta[0])
        p = len(theta)
        J = np.zeros(b.t.shape + (p,))
        if spec.rc:
            R1, C1 = math.exp(theta[1]), math.exp(theta[2])
            V1, S = rc_branch(b, R1, C1)
            J[..., 1] = -(V1 + S)
            J[..., 2] = -S
            off = 3
        else:
            V1 = np.zeros(b.t.shape)
            off = 1
        J[..., 0] = -b.current * R0
        if self.W is not None:
            ocv = self.W @ theta[off:]
            J[..., off:] = self.W
        else:
            ocv = self.ocv_fixed
        return ocv - b.current * R0 - V1, J

    def residuals(self, theta: np.ndarray) -> np.ndarray:
        v, _ = self.predict(theta)
        return (self.batch.voltage - v)[self.sel]

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        _, J = self.predict(theta)
        return -J[self.sel]


def _starts(spec: ModelSpec, batch: Batch) -> list[np.ndarray]:
    rng = np.random.RandomState(START_SEED)
    lo, hi = spec.bounds_vectors()
    starts = []
    for _ in range(N_STARTS):
        x = []
        x.append(rng.uniform(lo[0], hi[0]))
        if spec.rc:
            x += [rng.uniform(lo[1], hi[1]), rng.uniform(lo[2], hi[2])]
        if spec.knots_soc is not None:
            v_hi = float(np.max(batch.voltage[:, 0])); v_lo = float(np.min(batch.voltage[batch.mask]))
            x += list(np.interp(spec.knots_soc, [0.0, 1.0], [v_lo, v_hi]))
        starts.append(np.array(x))
    return starts


@dataclass
class Fit:
    spec: ModelSpec
    theta: np.ndarray
    sse: float
    n: int
    starts: list[dict[str, Any]]
    residuals: np.ndarray
    jac: np.ndarray

    @property
    def params(self) -> dict[str, float]:
        out = {"R0": math.exp(self.theta[0])}
        if self.spec.rc:
            out["R1"], out["C1"] = math.exp(self.theta[1]), math.exp(self.theta[2])
            out["tau"] = out["R1"] * out["C1"]
        return out


def fit(spec: ModelSpec, batch: Batch, *, x0: Sequence[np.ndarray] | None = None) -> Fit:
    ev = Evaluator(spec, batch)
    lo, hi = spec.bounds_vectors()
    starts, best = [], None
    for k, x in enumerate(x0 if x0 is not None else _starts(spec, batch)):
        x = np.clip(np.asarray(x, float), lo + 1e-9, hi - 1e-9)
        res = least_squares(ev.residuals, x, jac=ev.jacobian, bounds=(lo, hi), method="trf", x_scale="jac",
                            max_nfev=300, xtol=1e-10, ftol=1e-12, gtol=1e-10)
        sse = float(res.fun @ res.fun)
        starts.append({"start": k, "sse": sse, "theta": [float(v) for v in res.x], "status": int(res.status)})
        if best is None or sse < best[0]:
            best = (sse, res.x.copy())
    theta = best[1]
    return Fit(spec, theta, best[0], int(ev.sel.sum()), starts, ev.residuals(theta), ev.jacobian(theta))


def lag1(batch: Batch, resid_full: np.ndarray) -> float:
    """Mean over trajectories of the lag-1 autocorrelation of the scored residuals."""
    vals = []
    for i in range(batch.t.shape[0]):
        r = resid_full[i, 1:batch.lengths[i]]
        if len(r) > 2 and np.std(r) > 0:
            r = r - r.mean()
            vals.append(float(r[:-1] @ r[1:] / (r @ r)))
    return float(np.mean(vals)) if vals else float("nan")


def error_stats(batch: Batch, v_pred: np.ndarray) -> dict[str, float]:
    full = batch.voltage - v_pred
    r = full[batch.mask]
    a = np.abs(r) * 1e3
    return {"rmse_mV": float(np.sqrt(np.mean(r ** 2)) * 1e3), "p95_abs_mV": float(np.percentile(a, 95)),
            "mae_mV": float(np.mean(a)), "bias_mV": float(np.mean(r) * 1e3), "max_abs_mV": float(np.max(a)),
            "lag1": lag1(batch, full), "samples": int(r.size)}


NULL_SINGULAR_RATIO = 1e-10
NULL_LOADING = 1e-6


def covariance(f: Fit, *, rho: float) -> np.ndarray:
    """Gauss-Newton covariance, inflated by (1 + rho) / (1 - rho) for lag-1 autocorrelated residuals.

    Computed from the SVD of the Jacobian.  A direction whose singular value is below NULL_SINGULAR_RATIO of the largest
    carries no information: every parameter loading on it gets an infinite variance (a pseudo-inverse would instead
    report zero variance there and manufacture identifiability).
    """
    p = len(f.theta)
    s2 = f.sse / max(f.n - p, 1)
    infl = (1 + rho) / (1 - rho)
    _, sv, vt = np.linalg.svd(f.jac, full_matrices=False)
    null = sv < NULL_SINGULAR_RATIO * sv.max()
    inv = np.where(null, 0.0, 1.0 / np.where(null, 1.0, sv) ** 2)
    cov = (vt.T * inv) @ vt * s2 * infl
    if null.any():
        loaded = np.any(np.abs(vt[null]) > NULL_LOADING, axis=0)
        cov[loaded, :] = np.nan
        cov[:, loaded] = np.nan
        cov[loaded, loaded] = np.inf
    return cov


__all__ = ["Batch", "CONVERGED_SSE_RATIO", "Evaluator", "Fit", "ModelSpec", "N_STARTS", "covariance", "error_stats",
           "fit", "interp_weights", "lag1", "rc_branch"]
