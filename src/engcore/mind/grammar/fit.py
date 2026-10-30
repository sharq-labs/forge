"""Constant fitting for one grammar structure on ln-scale data (EXC-4, development).

The target is ``z = ln y - ln scale`` at each row; the residual is ``ln F(theta) - z``.  Deterministic throughout:

* ``power`` is linear in its parameters: ordinary least squares, exact;
* ``regime``: an exact change-point search -- every midpoint between consecutive distinct values of the switch group in
  the rows is a candidate threshold (no grid spacing to act as an undeclared prior), each side fitted by ordinary least
  squares; a side with fewer rows than its parameters plus one is not a candidate; the least total RSS is kept;
* ``sum``, ``exp``, ``sum_exp``: scipy ``least_squares`` (``trf``) from a fixed set of starts built from ordinary least
  squares fits -- the deterministic multi-start pattern of :func:`engcore.mind.repsem.assess._fit`, with a bounded number
  of starts.  The best residual sum of squares over the starts is kept.

A fit that is not finite, a structure with at least as many parameters as rows, or a fit whose exp argument reaches the
clip that only fitting applies (the emitted law is unclipped, so it would not be the law that was fitted) is reported
``ok=False``: it is never scored as if it fitted.  A finite fit stopped by :data:`MAX_NFEV` is kept with
``converged=False`` (a recall limit, recorded, never support).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from .grammar import EXP_CLIP, Structure, exp_argument, jacobian, log_f

MAX_NFEV = 60
TOL = 1e-8


@dataclass(frozen=True)
class Fit:
    structure: Structure
    theta: tuple[float, ...]
    rss: float
    n: int
    ok: bool
    reason: str = ""
    converged: bool = True          # False: a finite fit stopped by MAX_NFEV (reported, kept: a recall limit only)


def _ols(L: np.ndarray, z: np.ndarray, subset: tuple[int, ...]) -> tuple[np.ndarray, float]:
    X = np.column_stack([np.ones(len(z))] + [L[:, j] for j in subset])
    coef, *_ = np.linalg.lstsq(X, z, rcond=None)
    r = z - X @ coef
    return coef, float(r @ r)


def _rss(structure: Structure, theta: np.ndarray, L: np.ndarray, z: np.ndarray) -> float:
    r = log_f(structure, theta, L) - z
    return float(r @ r) if np.all(np.isfinite(r)) else math.inf


def _starts(structure: Structure, L: np.ndarray, z: np.ndarray) -> list[np.ndarray]:
    a = structure.atoms
    half = math.log(2.0)
    base = [_ols(L, z, s)[0] for s in a[:2]] if structure.shape in ("sum", "sum_exp") else [_ols(L, z, a[0])[0]]
    if structure.shape == "sum":
        lead = [np.concatenate([base[0] - np.r_[half, np.zeros(len(a[0]))], base[1] - np.r_[half, np.zeros(len(a[1]))]])]
        return lead + [np.concatenate([base[0] - np.r_[half, np.zeros(len(a[0]))],
                                       np.r_[base[1][0] - half + d, 0.5 * base[1][1:]]]) for d in (-1.0, 1.0)]
    c = a[-1]
    starts = []
    for sign_c in (1.0, -1.0):
        expo = np.full(len(c), sign_c)
        scale = float(np.median(np.exp(np.clip(L[:, list(c)] @ expo, -50, 50))))
        for sign_k in (1.0, -1.0):
            k = np.r_[sign_k * 0.5 / max(scale, 1e-12), expo]
            if structure.shape == "exp":
                starts.append(np.concatenate([base[0], k]))
            else:
                starts.append(np.concatenate([base[0] - np.r_[half, np.zeros(len(a[0]))],
                                              base[1] - np.r_[half, np.zeros(len(a[1]))], k]))
    return starts


def fit(structure: Structure, L: np.ndarray, z: np.ndarray) -> Fit:
    n = len(z)
    if structure.n_params >= n:
        return Fit(structure, (), math.inf, n, False, "at least as many parameters as rows")
    if structure.shape == "power":
        coef, rss = _ols(L, z, structure.atoms[0])
        return Fit(structure, tuple(map(float, coef)), rss, n, math.isfinite(rss))
    if structure.shape == "regime":
        s = structure.switch
        best: Fit | None = None
        values = np.unique(L[:, s])
        for lt in (values[:-1] + values[1:]) / 2.0:
            below = L[:, s] < lt
            pa, pb = 1 + len(structure.atoms[0]), 1 + len(structure.atoms[1])
            if below.sum() < pa + 1 or (~below).sum() < pb + 1:
                continue
            ca, ra = _ols(L[below], z[below], structure.atoms[0])
            cb, rb = _ols(L[~below], z[~below], structure.atoms[1])
            if best is None or ra + rb < best.rss:
                best = Fit(structure, tuple(map(float, np.concatenate([ca, cb, [lt]]))), ra + rb, n, True)
        return best or Fit(structure, (), math.inf, n, False, "no threshold leaves enough rows on both sides")
    best_theta, best_rss, best_status = None, math.inf, 0
    for x0 in _starts(structure, L, z):
        def resid(theta: np.ndarray) -> np.ndarray:
            r = log_f(structure, theta, L) - z
            return np.where(np.isfinite(r), r, 1e3)
        def jac(theta: np.ndarray) -> np.ndarray:
            J = jacobian(structure, theta, L)
            return np.where(np.isfinite(J), J, 0.0)
        try:
            sol = least_squares(resid, x0, jac=jac, method="trf", max_nfev=MAX_NFEV, ftol=TOL, xtol=TOL, gtol=TOL)
        except (ValueError, FloatingPointError):
            continue
        rss = _rss(structure, sol.x, L, z)
        if rss < best_rss:
            best_theta, best_rss, best_status = sol.x, rss, int(sol.status)
    if best_theta is None or not math.isfinite(best_rss):
        return Fit(structure, (), math.inf, n, False, "no start converged to a finite fit")
    u = exp_argument(structure, best_theta, L)
    if u is not None and float(np.max(np.abs(u))) >= EXP_CLIP:
        # the fit leaned on the clipped exp that only fitting uses; the emitted law is unclipped, so it is not this fit
        return Fit(structure, (), math.inf, n, False, "the fit relies on the clipped exp argument")
    return Fit(structure, tuple(map(float, best_theta)), best_rss, n, True,
               "" if best_status > 0 else "iteration cap reached (finite, not converged)", converged=best_status > 0)


__all__ = ["Fit", "MAX_NFEV", "TOL", "fit"]
