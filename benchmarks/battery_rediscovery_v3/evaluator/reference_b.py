"""Reference B: the second, independent truth implementation of battery_rediscovery_v3 (frozen before any run).

Reference A is battery_rediscovery_v2's reference protocol (``benchmarks.battery_rediscovery_v2.evaluator.reference``),
imported unchanged.  A shares two critical numerical components with the GEN1 candidate (``engcore.mind.repsem``):
``scipy.optimize.least_squares`` (method "trf") and ``engcore.hybrid_uq.identifiability.classify``.  So an A-only truth
is IMPLEMENTATION_CORRELATED.  Reference B answers the same five questions, under the same declared semantics, with
none of the candidate's numerics except, where a declared noise forces it, the canonical classifier (flagged):

* **Forward model.**  A sequential recursion of its own, vectorised over a grid of time constants.  With
  ``a_k = exp(-dt_k / tau)``, ``g_k = a_k g_(k-1) + (1 - a_k) I_k`` (``g_0 = 0``) and ``A_k = a_k A_(k-1)`` (``A_0 = 1``),
  the declared branch is ``v1_k = p0 A_k + R1 g_k``, so ``V_k = OCV(z_k) - I_k R0 - p0 A_k - R1 g_k`` with
  ``z_k = z_0 - sum_(j<=k) I_j dt_j / Q`` (backward hold) and OCV linear interpolation, clamped at the end knots.
* **Optimizer (variable projection).**  For a fixed ``tau`` the model is LINEAR in (R0, R1) and, for a fitted OCV, in
  the knot values.  Each ``tau`` is solved exactly by bounded-variable least squares (``scipy.optimize.lsq_linear``,
  method "bvls": a convex problem, so its optimum is global) with R1 bounded by ``[max(R1_lo, tau/C1_hi),
  min(R1_hi, tau/C1_lo)]`` so that ``C1 = tau / R1`` stays inside its declared bounds.  The profile ``S(tau)`` is
  evaluated on ``N_TAU`` log-spaced points over ``[R1_lo C1_lo, R1_hi C1_hi]`` and every grid local minimum within
  ``REFINE_REL`` of the best is refined by bounded Brent search in ``ln tau`` (``scipy.optimize.minimize_scalar``,
  "bounded") between its neighbours.  The optimum is the lowest refined cost.  No nonlinear least-squares solver is used.
* **Jacobian.**  Central finite differences of B's own forward model in ln-parameters (step ``FD_STEP``).

Truth rules: the same declared semantics as v2's reference (margin M = 1.10; ``None`` = unscored; NOT_ASSESSABLE = the
correct answer is a refusal), implemented here independently:

1. MODEL_ADEQUACY: calibration rmse and p95(|r|) at B's optimum against the adequacy bar.
2. IDENTIFIABILITY: near-structural if a requested parameter's normalised Jacobian column has an orthogonal
   component < 1e-6; ambiguous if another refined profile minimum has a relative cost within 1e-6 (sigma None) or a
   delta-SSE <= 3.84 sigma^2 (sigma declared) and a requested parameter differing by > ln(1.5).  sigma None:
   NOT_SUPPORTED if near-structural or ambiguous, else NOT_ASSESSABLE.  sigma declared: Fisher ``J^T J / sigma^2``
   (singular -> NOT_SUPPORTED), declared and residual-inflated covariances classified by the canonical classifier
   (``classifier_shared = True`` is recorded); SUPPORTED iff both IDENTIFIABLE and nothing is on a bound.
3. WITHIN / CROSS: the domain is the calibration range of each applicability variable (B's own charge-state
   reconstruction), widened by the declared margins; in-domain iff every sample of the subset lies inside and the unit
   relation holds; per-subset labels and the set rule as declared in the pack's ``questions.set_rule``.
4. MODEL_DISCREPANCY: sigma None -> NOT_ASSESSABLE; with a declared half-width h, ``bound = h + 2 sd_pred`` from B's
   inflated covariance; NOT_SUPPORTED if rmse > M bound, SUPPORTED if p95 <= bound / M, else None.

The module also returns the profile, the finite-difference Jacobian's sigma-free correlation structure and the
horizon/sampling scales that ``diagnostics.py`` needs.  Output is JSON-safe and deterministic.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import lsq_linear, minimize_scalar

from engcore.hybrid_uq.identifiability import CANONICAL_IDENTIFIABILITY_THRESHOLDS, classify
from engcore.inference.calibration import IdentifiabilityStatus

SCHEMA = "forge.battery_rediscovery_v3.reference_b/1"
MARGIN = 1.10
CHI2_95_1DOF = 3.84
Z95 = 1.959963984540054
AMBIGUITY_LN = math.log(1.5)
AMBIGUITY_REL_COST = 1e-6
NEAR_STRUCTURAL_TOL = 1e-6
ON_BOUND_LN = 1e-6
DOMAIN_EPS = 1e-12
N_TAU = 241
REFINE_REL = 1e-3
BRENT_XATOL = 1e-7
FD_STEP = 1e-5
BVLS_TOL = 1e-12

MEASURED = "rc1_measured_ocv/1"
FITTED = "rc1_fitted_ocv/1"
SUPPORTED, NOT_SUPPORTED, NOT_ASSESSABLE = "SUPPORTED", "NOT_SUPPORTED", "NOT_ASSESSABLE"
AXES = ("MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY")
HELDOUT = (("WITHIN_CELL_GENERALIZATION", "within_unit_heldout", "within"),
           ("CROSS_CELL_TRANSFER", "cross_unit_heldout", "cross"))


# ------------------------------------------------------------------------------------------------ data and model
class Traj:
    def __init__(self, payload: Mapping[str, Any], extra: Sequence[str]):
        c = payload["columns"]
        self.id, self.unit = str(payload["id"]), str(payload["unit_id"])
        self.t = np.asarray(c["t_s"], float)
        self.i = np.asarray(c["current_A"], float)
        self.v = np.asarray(c["voltage_V"], float)
        self.cols = {k: np.asarray(c[k], float) for k in extra}
        self.dt = np.diff(self.t)
        if self.t.size < 2 or np.any(self.dt <= 0.0):
            raise ValueError(f"{self.id}: needs >= 2 samples with increasing time")
        self.q = float(payload["conditions"]["capacity_As"])
        self.p0 = float(payload["conditions"]["initial_polarization"])
        z0 = float(payload["initial_state"]["soc"])
        self.z = np.concatenate([[z0], z0 - np.cumsum(self.i[1:] * self.dt) / self.q])

    def var(self, name: str) -> np.ndarray:
        return self.z if name == "soc" else self.cols[name]


def _weights(z: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """Linear interpolation weights on the knots, clamped at both ends (rows sum to 1)."""
    w = np.zeros((z.size, knots.size))
    zc = np.clip(z, knots[0], knots[-1])
    j = np.clip(np.searchsorted(knots, zc, side="right") - 1, 0, knots.size - 2)
    f = (zc - knots[j]) / (knots[j + 1] - knots[j])
    rows = np.arange(z.size)
    w[rows, j] += 1.0 - f
    w[rows, j + 1] += f
    return w


class Model:
    def __init__(self, family: Mapping[str, Any]):
        self.family_id = family["family_id"]
        b = family["parameter_bounds"]
        k = family["constants"]
        if self.family_id == MEASURED:
            kn = np.asarray(k["ocv_knots"], float)
            self.knot_z, self.knot_v, self.fitted = kn[:, 0], kn[:, 1], False
            self.names = ("R0", "R1", "C1")
        elif self.family_id == FITTED:
            self.knot_z, self.knot_v, self.fitted = np.asarray(k["ocv_knots_soc"], float), None, True
            self.names = ("R0", "R1", "C1") + tuple(f"ocv_k{j}" for j in range(self.knot_z.size))
        else:
            raise ValueError(f"unknown family {self.family_id!r}")
        if np.any(np.diff(self.knot_z) <= 0.0):
            raise ValueError("OCV knots must be strictly increasing")
        self.lo = {n: float(b[n][0]) for n in self.names}
        self.hi = {n: float(b[n][1]) for n in self.names}
        self.tau_lo = self.lo["R1"] * self.lo["C1"]
        self.tau_hi = self.hi["R1"] * self.hi["C1"]

    def ocv(self, z: np.ndarray, knots_v: np.ndarray | None = None) -> np.ndarray:
        return _weights(z, self.knot_z) @ (self.knot_v if knots_v is None else knots_v)


def _branch(tr: Traj, taus: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """g and A for every sample (rows) and every tau (columns)."""
    n = tr.t.size
    g = np.zeros((n, taus.size))
    a_cum = np.ones((n, taus.size))
    gk = np.zeros(taus.size)
    ak = np.ones(taus.size)
    for k in range(1, n):
        a = np.exp(-tr.dt[k - 1] / taus)
        gk = a * gk + (1.0 - a) * tr.i[k]
        ak = a * ak
        g[k] = gk
        a_cum[k] = ak
    return g, a_cum


def _predict(model: Model, tr: Traj, theta: Mapping[str, float]) -> np.ndarray:
    tau = theta["R1"] * theta["C1"]
    g, a_cum = _branch(tr, np.array([tau]))
    knots_v = np.array([theta[f"ocv_k{j}"] for j in range(model.knot_z.size)]) if model.fitted else None
    return model.ocv(tr.z, knots_v) - tr.i * theta["R0"] - tr.p0 * a_cum[:, 0] - theta["R1"] * g[:, 0]


def _residuals(model: Model, trs: Sequence[Traj], theta: Mapping[str, float]) -> np.ndarray:
    return np.concatenate([(_predict(model, tr, theta) - tr.v)[1:] for tr in trs])


# ------------------------------------------------------------------------------------------------ the fit
class _Design:
    """Per-calibration-set constant parts of the variable-projection problem."""

    def __init__(self, model: Model, trs: Sequence[Traj]):
        self.model, self.trs = model, trs
        self.i = np.concatenate([tr.i[1:] for tr in trs])
        self.v = np.concatenate([tr.v[1:] for tr in trs])
        self.w = np.concatenate([_weights(tr.z[1:], model.knot_z) for tr in trs]) if model.fitted else None
        self.ocv = None if model.fitted else np.concatenate([model.ocv(tr.z[1:]) for tr in trs])

    def solve(self, tau: float, g: np.ndarray | None = None, a_cum: np.ndarray | None = None) -> dict[str, Any] | None:
        m = self.model
        r1_lo, r1_hi = max(m.lo["R1"], tau / m.hi["C1"]), min(m.hi["R1"], tau / m.lo["C1"])
        if r1_lo > r1_hi:
            return None
        if g is None:
            parts = [_branch(tr, np.array([tau])) for tr in self.trs]
            g = np.concatenate([p[0][1:, 0] for p in parts])
            a_cum = np.concatenate([p[1][1:, 0] for p in parts])
        p0 = np.concatenate([np.full(tr.t.size - 1, tr.p0) for tr in self.trs])
        y = self.v + p0 * a_cum - (0.0 if m.fitted else self.ocv)
        cols = [-self.i, -g]
        lo, hi = [m.lo["R0"], r1_lo], [m.hi["R0"], r1_hi]
        if m.fitted:
            cols += [self.w[:, j] for j in range(self.w.shape[1])]
            lo += [m.lo[f"ocv_k{j}"] for j in range(self.w.shape[1])]
            hi += [m.hi[f"ocv_k{j}"] for j in range(self.w.shape[1])]
        x_mat = np.column_stack(cols)
        sol = lsq_linear(x_mat, y, bounds=(np.array(lo), np.array(hi)), method="bvls", tol=BVLS_TOL)
        x = np.clip(sol.x, lo, hi)
        r = x_mat @ x - y
        theta = {"R0": float(x[0]), "R1": float(x[1]), "C1": float(tau / x[1])}
        if m.fitted:
            theta.update({f"ocv_k{j}": float(x[2 + j]) for j in range(self.w.shape[1])})
        return {"tau": float(tau), "theta": theta, "sse": float(r @ r), "status": int(sol.status)}


def fit(model: Model, trs: Sequence[Traj]) -> dict[str, Any]:
    design = _Design(model, trs)
    taus = np.exp(np.linspace(math.log(model.tau_lo), math.log(model.tau_hi), N_TAU))
    parts = [_branch(tr, taus) for tr in trs]
    g_all = np.concatenate([p[0][1:] for p in parts])
    a_all = np.concatenate([p[1][1:] for p in parts])
    grid = []
    for j, tau in enumerate(taus):
        s = design.solve(float(tau), g_all[:, j], a_all[:, j])
        grid.append(math.inf if s is None else s["sse"])
    grid = np.array(grid)
    finite = np.isfinite(grid)
    if not finite.any():
        raise ValueError("no feasible time constant")
    best_grid = float(np.min(grid[finite]))
    u = np.log(taus)
    minima = [j for j in range(N_TAU) if finite[j] and (j == 0 or grid[j] <= grid[j - 1]) and
              (j == N_TAU - 1 or grid[j] <= grid[j + 1]) and grid[j] <= best_grid * (1.0 + REFINE_REL)]
    refined = []
    for j in minima:
        a_, b_ = u[max(j - 1, 0)], u[min(j + 1, N_TAU - 1)]

        def f(x: float) -> float:
            s = design.solve(math.exp(x))
            return math.inf if s is None else s["sse"]

        res = minimize_scalar(f, bounds=(a_, b_), method="bounded", options={"xatol": BRENT_XATOL})
        cand = [design.solve(math.exp(float(res.x))), design.solve(float(taus[j]))]
        cand = [c for c in cand if c is not None]
        refined.append(min(cand, key=lambda c: c["sse"]))
    refined.sort(key=lambda c: c["sse"])
    return {"best": refined[0], "refined": refined, "grid_ln_tau": u, "grid_sse": grid}


# ------------------------------------------------------------------------------------------------ analysis
def _stats(r: np.ndarray) -> dict[str, float]:
    a = np.abs(r)
    return {"n": int(r.size), "rmse": float(np.sqrt(np.mean(r * r))), "p95_abs": float(np.percentile(a, 95.0)),
            "bias": float(np.mean(r)), "max_abs": float(np.max(a))}


def _graded(rmse: float, p95: float, bar: Mapping[str, float]) -> str | None:
    if rmse > MARGIN * bar["rmse_max"] or p95 > MARGIN * bar["p95_abs_max"]:
        return NOT_SUPPORTED
    if rmse <= bar["rmse_max"] / MARGIN and p95 <= bar["p95_abs_max"] / MARGIN:
        return SUPPORTED
    return None


def jacobian_ln(model: Model, trs: Sequence[Traj], theta: Mapping[str, float]) -> np.ndarray:
    cols = []
    for n in model.names:
        up, dn = dict(theta), dict(theta)
        up[n] = theta[n] * math.exp(FD_STEP)
        dn[n] = theta[n] * math.exp(-FD_STEP)
        cols.append((_residuals(model, trs, up) - _residuals(model, trs, dn)) / (2.0 * FD_STEP))
    return np.column_stack(cols)


def _orthogonal(jac: np.ndarray, idx: Sequence[int]) -> list[float]:
    norms = np.linalg.norm(jac, axis=0)
    unit = np.divide(jac, norms, out=np.zeros_like(jac), where=norms > 0)
    out = []
    for j in idx:
        if norms[j] == 0.0:
            out.append(0.0)
            continue
        others = np.delete(unit, j, axis=1)
        q, _ = np.linalg.qr(others)
        resid = unit[:, j] - q @ (q.T @ unit[:, j])
        out.append(float(np.linalg.norm(resid)))
    return out


UNCONSTRAINED_REL = 1e-9


def information(jac: np.ndarray, names: Sequence[str] = ()) -> dict[str, Any]:
    """Sigma-free structure of ``inv(J^T J)`` (its correlation matrix does not depend on a noise scale).

    A parameter whose Jacobian column norm is below ``UNCONSTRAINED_REL`` times the largest is EFFECTIVELY
    UNCONSTRAINED (no scored sample depends on it, e.g. an OCV knot outside the data's charge-state range); it is
    reported and left out of ``unit_cov_ln_reduced``.  ``singular`` refers to the full parameter set, as the truth
    rules require; ``reduced_singular`` to the constrained set.
    """
    norms = np.linalg.norm(jac, axis=0)
    p = int(jac.shape[1])
    keep = [j for j in range(p) if norms[j] > UNCONSTRAINED_REL * max(float(norms.max()), 1e-300)]
    unit = np.divide(jac, norms, out=np.zeros_like(jac), where=norms > 0)
    rank = int(np.linalg.matrix_rank(unit))
    out: dict[str, Any] = {"rank": rank, "p": p, "singular": rank < p,
                           "unconstrained": [names[j] if names else j for j in range(p) if j not in keep],
                           "kept_index": keep}
    red = jac[:, keep]
    red_rank = int(np.linalg.matrix_rank(unit[:, keep]))
    out["reduced_singular"] = red_rank < len(keep)
    if not out["reduced_singular"]:
        try:
            out["unit_cov_ln_reduced"] = np.linalg.inv(red.T @ red)
        except np.linalg.LinAlgError:
            out["reduced_singular"] = True
    if not out["singular"]:
        try:
            out["unit_cov_ln"] = np.linalg.inv(jac.T @ jac)
        except np.linalg.LinAlgError:
            out["singular"] = True
    return out


def _correlation_structure(cov: np.ndarray, idx: Sequence[int]) -> dict[str, float]:
    sub = cov[np.ix_(idx, idx)]
    sd = np.sqrt(np.abs(np.diag(sub)))
    corr = sub / np.outer(sd, sd)
    ev = np.linalg.eigvalsh(corr)
    cond = math.inf if ev.min() <= 0 else float(ev.max() / ev.min())
    off = [abs(float(corr[a, b])) for a in range(len(idx)) for b in range(len(idx)) if a != b]
    return {"condition_number": cond, "max_abs_correlation": max(off) if off else 0.0}


def _noise(spec: Mapping[str, Any]) -> tuple[float | None, float | None]:
    n = spec.get("measurement_noise") or {}
    s, h = n.get("sigma"), n.get("half_width")
    return (None if s is None else float(s)), (None if h is None else float(h))


def _identifiability(spec, model, f, theta, jac, cal, sigma) -> dict[str, Any]:
    req = list(spec.get("requested_parameters", ["R0", "R1", "C1"]))
    idx = [model.names.index(n) for n in req]
    s = _orthogonal(jac, idx)
    near = min(s) < NEAR_STRUCTURAL_TOL
    best = f["best"]["sse"]
    tol_abs = CHI2_95_1DOF * sigma * sigma if sigma is not None else None
    tied = [c for c in f["refined"][1:] if (c["sse"] - best <= tol_abs if tol_abs is not None
                                           else c["sse"] - best <= AMBIGUITY_REL_COST * best)]
    dev = {n: max([abs(math.log(c["theta"][n]) - math.log(theta[n])) for c in tied] or [0.0]) for n in req}
    ambiguous = any(v > AMBIGUITY_LN for v in dev.values())
    on_bound = [n for n in req if math.log(theta[n]) - math.log(model.lo[n]) <= ON_BOUND_LN
                or math.log(model.hi[n]) - math.log(theta[n]) <= ON_BOUND_LN]
    e: dict[str, Any] = {"orthogonal_norms": dict(zip(req, s)), "near_structural": near, "ambiguous": ambiguous,
                         "minima_within_tolerance": len(tied), "max_ln_deviation": dev, "on_bound": on_bound,
                         "sigma": sigma, "classifier_shared": False}
    structural = (["near-structural"] if near else []) + (["ambiguous profile minima"] if ambiguous else [])
    if sigma is None:
        e.update(truth=NOT_SUPPORTED if structural else NOT_ASSESSABLE,
                 basis="; ".join(structural) if structural else "sigma UNKNOWN; neither near-structural nor ambiguous")
        return e
    info = information(jac)
    if info["singular"]:
        e.update(truth=NOT_SUPPORTED, basis="; ".join(structural + ["singular Fisher information"]))
        return e
    e["classifier_shared"] = True
    sig_infl = max(sigma, cal["rmse"])
    th = np.array([theta[n] for n in model.names])
    statuses = {}
    for label, sg in (("declared", sigma), ("inflated", sig_infl)):
        cov_theta = info["unit_cov_ln"] * sg * sg * np.outer(th, th)
        sub = cov_theta[np.ix_(idx, idx)]
        sd = np.sqrt(np.diag(sub))
        mean = th[idx]
        st, cond, corr, widths, why = classify(list(mean), sub, list(mean - Z95 * sd), list(mean + Z95 * sd), req,
                                               **CANONICAL_IDENTIFIABILITY_THRESHOLDS)
        statuses[label] = st
        e[label] = {"status": st.value, "condition_number": cond, "max_abs_correlation": corr,
                    "relative_widths": dict(zip(req, widths)), "why": why}
    d, i_ = statuses["declared"], statuses["inflated"]
    if structural:
        e.update(truth=NOT_SUPPORTED, basis="; ".join(structural))
    elif d is IdentifiabilityStatus.NOT_IDENTIFIABLE:
        e.update(truth=NOT_SUPPORTED, basis="declared-sigma classification NOT_IDENTIFIABLE")
    elif d is IdentifiabilityStatus.IDENTIFIABLE and i_ is IdentifiabilityStatus.IDENTIFIABLE and not on_bound:
        e.update(truth=SUPPORTED, basis="declared and inflated classifications IDENTIFIABLE, nothing on a bound")
    else:
        e.update(truth=None, basis=f"unscored: declared {d.value}, inflated {i_.value}, on bound {on_bound}")
    return e


def _discrepancy(cal, sigma, half, jac) -> dict[str, Any]:
    e: dict[str, Any] = {"rmse": cal["rmse"], "p95_abs": cal["p95_abs"], "sigma": sigma, "half_width": half}
    if sigma is None:
        e.update(truth=NOT_ASSESSABLE, basis="measurement uncertainty UNKNOWN; no discrepancy bound is defined")
        return e
    if half is None:
        e.update(truth=None, basis="unscored: no half-width, so no bound")
        return e
    info = information(jac)
    if info["singular"]:
        e.update(truth=None, basis="unscored: singular information, parameter-induced spread undefined")
        return e
    sig_infl = max(sigma, cal["rmse"])
    var = np.einsum("ij,jk,ik->i", jac, info["unit_cov_ln"] * sig_infl * sig_infl, jac)
    sd_pred = math.sqrt(max(float(np.mean(var)), 0.0))
    bound = half + 2.0 * sd_pred
    e.update(sd_pred=sd_pred, bound=bound)
    if cal["rmse"] > MARGIN * bound:
        e.update(truth=NOT_SUPPORTED, basis="rmse > M * bound")
    elif cal["p95_abs"] <= bound / MARGIN:
        e.update(truth=SUPPORTED, basis="p95 <= bound / M")
    else:
        e.update(truth=None, basis="unscored: between the margins")
    return e


def _domain(spec, cal: Sequence[Traj]) -> dict[str, dict[str, float]]:
    app = spec.get("applicability") or {}
    widen = app.get("widen") or {}
    out = {}
    for var in app.get("variables", []):
        vals = np.concatenate([tr.var(var) for tr in cal])
        w = float(widen.get(var, 0.0))
        out[var] = {"lo": float(vals.min()) - w, "hi": float(vals.max()) + w}
    return out


def _heldout(spec, model, theta, cal_units, domain, key, relation, extra) -> dict[str, Any]:
    subsets = {k: v for k, v in ((spec.get("sets") or {}).get(key) or {}).items() if v}
    if not subsets:
        return {"truth": NOT_ASSESSABLE, "basis": "no set supplied", "subsets": {}}
    per = {}
    for name in sorted(subsets):
        bar = spec["acceptance"][f"{key}/{name}"]
        trs = [Traj(t, extra) for t in subsets[name]]
        st = _stats(np.concatenate([(_predict(model, tr, theta) - tr.v)[1:] for tr in trs]))
        units = sorted({tr.unit for tr in trs})
        unit_ok = all(u in cal_units for u in units) if relation == "within" else not any(u in cal_units for u in units)
        outside = []
        for var, rng in domain.items():
            vals = np.concatenate([tr.var(var) for tr in trs])
            if vals.min() < rng["lo"] - DOMAIN_EPS or vals.max() > rng["hi"] + DOMAIN_EPS:
                outside.append(var)
        if unit_ok and not outside:
            g = _graded(st["rmse"], st["p95_abs"], bar)
            label = {SUPPORTED: "SUPPORTED", NOT_SUPPORTED: "NOT_SUPPORTED", None: "MARGINAL"}[g]
        elif st["rmse"] <= bar["rmse_max"] and st["p95_abs"] <= bar["p95_abs_max"]:
            label = "OOD_PASS"
        elif st["rmse"] > MARGIN * bar["rmse_max"] or st["p95_abs"] > MARGIN * bar["p95_abs_max"]:
            label = "OOD_FAIL"
        else:
            label = "OOD_MARGINAL"
        per[name] = {"label": label, "in_domain": bool(unit_ok and not outside), "outside": outside,
                     "unit_relation_holds": bool(unit_ok), **st}
    labels = [p["label"] for p in per.values()]
    if "NOT_SUPPORTED" in labels:
        truth, basis = NOT_SUPPORTED, "an in-domain subset fails its bar beyond the margin"
    elif any(lab in ("MARGINAL", "OOD_FAIL", "OOD_MARGINAL") for lab in labels):
        truth, basis = None, "unscored: marginal or out of domain without a clean pass"
    elif "OOD_PASS" in labels:
        truth, basis = NOT_ASSESSABLE, "in-domain subsets pass but a subset lies outside the calibration domain"
    else:
        truth, basis = SUPPORTED, "every subset in domain and passing with margin"
    return {"truth": truth, "basis": basis, "subsets": per}


def truth_table(spec: Mapping[str, Any]) -> dict[str, Any]:
    model = Model(spec["declared_family"])
    extra = [v for v in (spec.get("applicability") or {}).get("variables", []) if v != "soc"]
    cal = [Traj(t, extra) for t in spec["sets"]["calibration"]]
    f = fit(model, cal)
    theta = f["best"]["theta"]
    r = _residuals(model, cal, theta)
    cal_stats = _stats(r)
    jac = jacobian_ln(model, cal, theta)
    sigma, half = _noise(spec)
    table: dict[str, Any] = {"MODEL_ADEQUACY": {"truth": _graded(cal_stats["rmse"], cal_stats["p95_abs"], spec["adequacy_bar"]),
                                                **cal_stats}}
    table["IDENTIFIABILITY"] = _identifiability(spec, model, f, theta, jac, cal_stats, sigma)
    domain = _domain(spec, cal)
    units = {tr.unit for tr in cal}
    for axis, key, rel in HELDOUT:
        table[axis] = _heldout(spec, model, theta, units, domain, key, rel, extra)
    table["MODEL_DISCREPANCY"] = _discrepancy(cal_stats, sigma, half, jac)
    info = information(jac, model.names)
    req = [model.names.index(n) for n in spec.get("requested_parameters", ["R0", "R1", "C1"])]
    req_red = [info["kept_index"].index(j) for j in req if j in info["kept_index"]]
    gs = f["grid_sse"]
    best = f["best"]["sse"]
    flat = f["grid_ln_tau"][np.isfinite(gs) & (gs <= best * 1.01)]
    table["diagnostics"] = {
        "schema": SCHEMA, "family_id": model.family_id, "parameters": theta, "tau": f["best"]["tau"], "sse": best,
        "calibration": cal_stats, "domain": domain,
        "bounds": {n: [model.lo[n], model.hi[n]] for n in model.names},
        "profile": {"n_tau": N_TAU, "ln_tau_min": float(f["grid_ln_tau"][0]), "ln_tau_max": float(f["grid_ln_tau"][-1]),
                    "refined_minima": [{"tau": c["tau"], "sse": c["sse"], "theta": c["theta"]} for c in f["refined"]],
                    "ln_tau_span_within_1pct": float(flat.max() - flat.min()) if flat.size else 0.0},
        "information": {"rank": info["rank"], "p": info["p"], "singular": info["singular"],
                        "unconstrained": info["unconstrained"], "reduced_singular": info["reduced_singular"],
                        "requested_unconstrained": [n for n, j in zip(spec.get("requested_parameters", ["R0", "R1", "C1"]), req)
                                                    if j not in info["kept_index"]],
                        **({} if info["reduced_singular"] or len(req_red) < len(req)
                           else _correlation_structure(info["unit_cov_ln_reduced"], req_red))},
        "horizon_s": float(max(tr.t[-1] - tr.t[0] for tr in cal)),
        "median_dt_s": float(np.median(np.concatenate([tr.dt for tr in cal]))),
    }
    return _clean(table)


def _clean(v: Any) -> Any:
    if isinstance(v, Mapping):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, np.ndarray):
        return _clean(v.tolist())
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        x = float(v)
        if not math.isfinite(x):
            return None
        x = float(f"{x:.12g}")
        return 0.0 if x == 0.0 else x
    return v


__all__ = ["AXES", "MARGIN", "Model", "SCHEMA", "Traj", "fit", "information", "jacobian_ln", "truth_table"]
