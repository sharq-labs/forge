"""Core Gap Review 2 -- thin-ridge posterior resolution (read-only; no Core change).

    python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py phase1
    python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py family
    python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py parameterization
    python -X utf8 benchmarks/core_gap_thin_ridge/audit/thin_ridge.py regression --k2 <scratch>/k2_grid.npz

Every grid result below comes from the FROZEN gaussian_grid_posterior and the
FROZEN assess_identifiability / posterior_grid_diagnostics. Synthetic posteriors
are embedded as admitted linear observations, y = A theta with A = L^-1
(Sigma = L L^T) and unit sigma, so the frozen likelihood IS the target Gaussian.

Candidate diagnostics (Phase 5) read only what a PosteriorGrid already holds:
points, weights, log_likelihood, admissible_mask. Declared thresholds:

A  grid-covariance thin axis: projected lattice spacing / sqrt(lambda_min(grid cov)) > 1
B  grid-covariance condition number > 1e4
C  same as A, with Sigma_H from a quadratic fit to the grid's own log-likelihood values
D  lattice aliasing number: min over non-zero integer n of (2 pi)^2 (n/h)^T Sigma_H (n/h) < 2 ln(1e4)
   (Poisson summation: a lattice sum of a Gaussian differs from its integral by terms
   exp(-k^T Sigma k / 2) at reciprocal-lattice vectors k = 2 pi n / h)
E  ESS / ESS expected for a resolved Gaussian with Sigma_H outside [0.5, 2]
F  a second grid offset by half a step disagrees (mean > 0.1 grid sd or sd ratio outside [0.9, 1.1])
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import pathlib
import sys
import time

import numpy as np
from scipy.stats import chi2, multivariate_normal

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    GaussianObservation,
    GridResolutionError,
    ObservationSet,
    PosteriorGrid,
    assess_identifiability,
    gaussian_grid_posterior,
    posterior_grid_diagnostics,
)
from engcore.scientific.units.quantity import Quantity  # noqa: E402

#: Declared before any case was run.
MATERIAL = {"mean_error_in_true_sd": 0.1, "sd_ratio": (0.9, 1.1)}
THRESHOLDS = {"A_projected_spacing_over_thin_sd": 1.0, "B_condition": 1.0e4, "C_projected_spacing_over_thin_sd": 1.0,
              "D_aliasing_number_min": 2 * math.log(1.0e4), "E_ess_ratio": (0.5, 2.0), "F_mean_in_sd": 0.1, "F_sd_ratio": (0.9, 1.1)}


def jsonable(v):
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, np.ndarray):
        return jsonable(v.tolist())
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None if math.isnan(v) else ("inf" if v > 0 else "-inf")
    return v


def dump(name, payload):
    (ROUND / name).write_bytes((json.dumps(jsonable(payload), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print("wrote", name, flush=True)


# =====================================================================
# frozen grid over a synthetic model
# =====================================================================

def frozen_posterior(label, predict, y, sigma, axes, inside=None):
    """Frozen table + posterior. predict(points (N,p)) -> (N,n). inside(points) masks a prior box."""
    obs = ObservationSet(tuple(
        GaussianObservation(condition_id=f"o{i}", observable_name="y", value=Quantity(float(v), "dimensionless"),
                            sigma=Quantity(float(s), "dimensionless"), source_ref=f"synthetic:{label}:{i}")
        for i, (v, s) in enumerate(zip(y, sigma))), dataset_id=f"thin_ridge.{label}")
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T
    values = np.asarray(predict(mesh), dtype=float)
    mask = np.ones(len(mesh), dtype=bool) if inside is None else np.asarray(inside(mesh), dtype=bool)
    ref = f"analytic-synthetic:{label}"
    table = AdmittedForwardTable(
        parameter_names=tuple(f"t{i + 1}" for i in range(len(axes))), observation_keys=obs.keys, points=mesh,
        values=np.where(mask[:, None], values, 0.0), admissible_mask=mask,
        admission_refs=tuple((tuple(ref for _ in obs.keys) if ok else ()) for ok in mask),
        rejection_reasons=tuple("" if ok else "outside declared prior box" for ok in mask))
    return gaussian_grid_posterior(table, obs)


def guard(posterior):
    diag = posterior_grid_diagnostics(posterior)
    try:
        report = assess_identifiability(posterior)
        verdict, status = "ACCEPT", report.status.value
    except GridResolutionError:
        verdict, status = "REFUSE", "GRID_TOO_COARSE_FOR_INFERENCE"
    return {"verdict": verdict, "status": status, "effective_sample_size": diag["effective_sample_size"],
            "spacing_to_std": list(diag["spacing_to_std"]), "grid_points": diag["grid_points"]}


def moments(posterior):
    cov = posterior.covariance
    return posterior.mean, cov


def compare(mean_g, cov_g, mu, sigma):
    sd_t, sd_g = np.sqrt(np.diag(sigma)), np.sqrt(np.maximum(np.diag(cov_g), 0))
    mean_err = np.abs(mean_g - mu) / sd_t
    ratio = sd_g / sd_t
    material = bool(np.max(mean_err) > MATERIAL["mean_error_in_true_sd"] or np.min(ratio) < MATERIAL["sd_ratio"][0]
                    or np.max(ratio) > MATERIAL["sd_ratio"][1])
    corr = lambda c: float(c[0, 1] / math.sqrt(c[0, 0] * c[1, 1])) if c.shape[0] == 2 and c[0, 0] > 0 and c[1, 1] > 0 else None
    # POST HOC (added after Phase 4 was seen): the sd of the TRUE thin principal direction. A grid can get
    # every marginal right and still collapse the best-determined combination onto one node.
    lam, vec = np.linalg.eigh(sigma)
    u = vec[:, 0]
    thin_ratio = float(math.sqrt(max(float(u @ cov_g @ u), 0.0)) / math.sqrt(lam[0]))
    thin_mean_err = float(abs(float(u @ (mean_g - mu))) / math.sqrt(lam[0]))
    material_thin = bool(material or thin_ratio < MATERIAL["sd_ratio"][0] or thin_ratio > MATERIAL["sd_ratio"][1] or thin_mean_err > MATERIAL["mean_error_in_true_sd"])
    return {"max_mean_error_in_true_sd": float(np.max(mean_err)), "sd_ratio_grid_over_true": ratio.tolist(),
            "false_precision": bool(np.min(ratio) < MATERIAL["sd_ratio"][0]), "material": material,
            "correlation_true": corr(sigma), "correlation_grid": corr(cov_g),
            "post_hoc_thin_direction": {"sd_ratio_grid_over_true": thin_ratio, "mean_error_in_thin_sd": thin_mean_err,
                                        "material_including_thin_direction": material_thin}}


def classify(guard_verdict, material):
    if guard_verdict == "ACCEPT":
        return "C_FALSE_ACCEPT" if material else "A_CORRECT_ACCEPT"
    return "B_CORRECT_REFUSE" if material else "D_FALSE_REFUSE"


# =====================================================================
# candidate diagnostics (Phase 5), from PosteriorGrid contents only
# =====================================================================

def steps_of(posterior):
    return np.asarray([float(np.min(np.diff(np.unique(posterior.points[:, i])))) for i in range(posterior.points.shape[1])])


def quadratic_fit(posterior, min_points=None):
    """Sigma_H from a least-squares quadratic fit to the grid's own log-likelihood values.

    Progressive window: nodes within delta log-units of the maximum, delta in (50, 500, 5000, inf),
    the first whose quadratic design has full numerical rank. On a thin ridge every nearby node lies
    on the ridge line, so a small window cannot fix the cross-ridge curvature; the delta that was
    needed is returned, because a large delta makes the fit less local on a non-Gaussian posterior.
    """
    pts, ll = posterior.points, posterior.log_likelihood
    ok = np.isfinite(ll)
    p = pts.shape[1]
    need = (p + 1) * (p + 2) // 2
    if int(ok.sum()) < need:
        return None, "too few finite log-likelihood values"
    top = int(np.argmax(np.where(ok, ll, -np.inf)))
    x0 = pts[top]
    scale = steps_of(posterior)
    for delta in (50.0, 500.0, 5000.0, math.inf):
        idx = np.flatnonzero(ok & (ll >= ll[top] - delta))
        if len(idx) < 4 * need:
            continue
        X = (pts[idx] - x0) / scale
        cols = [np.ones(len(idx))] + [X[:, i] for i in range(p)] + [X[:, i] * X[:, j] for i in range(p) for j in range(i, p)]
        M = np.column_stack(cols)
        norms = np.linalg.norm(M, axis=0)
        if not np.all(np.isfinite(M)) or np.any(norms == 0):
            continue  # every nearby node shares a coordinate: this window cannot fix a quadratic
        try:
            sv = np.linalg.svd(M / norms, compute_uv=False)
        except np.linalg.LinAlgError:
            continue
        if sv[-1] / sv[0] < 1e-8:
            continue
        coef, *_ = np.linalg.lstsq(M, ll[idx], rcond=None)
        H = np.zeros((p, p))
        c = 1 + p
        for i in range(p):
            for j in range(i, p):
                if i == j:
                    H[i, i] = 2 * coef[c]
                else:
                    H[i, j] = H[j, i] = coef[c]
                c += 1
        D = np.diag(1 / scale)
        H = D @ H @ D
        if np.linalg.eigvalsh(H).max() >= 0:
            return None, f"fitted log-likelihood is not locally concave (delta {delta})"
        return np.linalg.inv(-H), f"ok (delta {delta}, {len(idx)} nodes)"
    return None, "quadratic design rank-deficient at every window (nodes collinear)"


def aliasing_number(sigma, h, n_max=None):
    p = len(h)
    n_max = n_max or (60 if p <= 2 else (12 if p == 3 else 6))
    rng = np.arange(-n_max, n_max + 1)
    best = math.inf
    # half-space enumeration (n and -n give the same value)
    for n in itertools.product(rng, repeat=p):
        if all(v == 0 for v in n):
            continue
        k = 2 * math.pi * np.asarray(n) / h
        best = min(best, float(k @ sigma @ k))
    return best


def projected_spacing(sigma, h):
    lam, vec = np.linalg.eigh(sigma)
    u = vec[:, 0]
    return float(math.sqrt(np.sum((u * h) ** 2)) / math.sqrt(max(lam[0], 1e-300))), float(lam[-1] / lam[0]) if lam[0] > 0 else math.inf


def candidates(posterior, *, offset_posterior=None):
    h = steps_of(posterior)
    cov_g = posterior.covariance
    out = {}
    a_ratio, cond_g = projected_spacing(cov_g, h) if np.linalg.eigvalsh(cov_g)[0] > 0 else (math.inf, math.inf)
    out["A"] = {"value": a_ratio, "flag": bool(a_ratio > THRESHOLDS["A_projected_spacing_over_thin_sd"])}
    out["B"] = {"value": cond_g, "flag": bool(cond_g > THRESHOLDS["B_condition"])}
    sigma_h, why = quadratic_fit(posterior)
    out["fit"] = why
    if sigma_h is None:
        for key in ("C", "D", "E"):
            out[key] = {"value": None, "flag": True, "why": why}
    else:
        c_ratio, _ = projected_spacing(sigma_h, h)
        out["C"] = {"value": c_ratio, "flag": bool(c_ratio > THRESHOLDS["C_projected_spacing_over_thin_sd"])}
        A = aliasing_number(sigma_h, h)
        out["D"] = {"value": A, "flag": bool(A < THRESHOLDS["D_aliasing_number_min"]),
                    "aliasing_amplitude": math.exp(-A / 2) if A < 1400 else 0.0}
        p = len(h)
        ess = posterior_grid_diagnostics(posterior)["effective_sample_size"]
        expected = (4 * math.pi) ** (p / 2) * math.sqrt(max(np.linalg.det(sigma_h), 0)) / float(np.prod(h))
        ratio = ess / expected if expected > 0 else math.inf
        out["E"] = {"value": ratio, "flag": bool(not (THRESHOLDS["E_ess_ratio"][0] <= ratio <= THRESHOLDS["E_ess_ratio"][1])),
                    "ess": ess, "ess_expected": expected}
        out["sigma_H"] = sigma_h.tolist()
    if offset_posterior is not None:
        sd = np.sqrt(np.maximum(np.diag(cov_g), 1e-300))
        m1, c1 = moments(posterior)
        m2, c2 = moments(offset_posterior)
        r = np.sqrt(np.maximum(np.diag(c2), 1e-300)) / np.sqrt(np.maximum(np.diag(c1), 1e-300))
        d = float(np.max(np.abs(m1 - m2) / sd))
        out["F"] = {"value": {"mean_shift_in_sd_H": d, "sd_ratio_offset_over_base": r.tolist()},
                    "flag": bool(d > THRESHOLDS["F_mean_in_sd"] or r.min() < THRESHOLDS["F_sd_ratio"][0] or r.max() > THRESHOLDS["F_sd_ratio"][1])}
    return out


# =====================================================================
# Phase 1: the exact F5 case
# =====================================================================

def f5_problem():
    committed = json.loads((ROOT / "benchmarks" / "core_gap_hd_uq" / "FAILURE_CASES.json").read_text(encoding="utf-8"))["cases"]["F5_weak_identifiability"]
    x = np.linspace(10.0, 10.05, 6)
    y = np.asarray(committed["observed"])
    sigma = np.full(6, 0.01)
    lower, upper = np.asarray([-50.0, -5.0]), np.asarray([50.0, 5.0])
    X = np.column_stack([np.ones(6), x]) / sigma[:, None]
    cov = np.linalg.inv(X.T @ X)
    mu = cov @ X.T @ (y / sigma)
    predict = lambda pts: pts[:, [0]] + pts[:, [1]] * x[None, :]
    return {"committed": committed, "x": x, "y": y, "sigma": sigma, "lower": lower, "upper": upper, "mu": mu, "cov": cov, "predict": predict}


def exact_box_moments(mu, cov, lower, upper, n=2001, span=12.0):
    """Independent reference: dense quadrature in PRINCIPAL-AXIS coordinates, truncated to the box."""
    lam, vec = np.linalg.eigh(cov)
    s = np.sqrt(lam)
    g = [np.linspace(-span * s[i], span * s[i], n) for i in range(2)]
    a, b = np.meshgrid(g[0], g[1], indexing="ij")
    Z = np.stack([a.ravel(), b.ravel()], axis=1)
    theta = mu + Z @ vec.T
    w = np.exp(-0.5 * (a.ravel() ** 2 / lam[0] + b.ravel() ** 2 / lam[1]))
    w[np.any(theta < lower, axis=1) | np.any(theta > upper, axis=1)] = 0.0
    w /= w.sum()
    m = w @ theta
    c = (theta - m).T @ ((theta - m) * w[:, None])
    return m, c


def phase1():
    F = f5_problem()
    mu, cov = F["mu"], F["cov"]
    lam, vec = np.linalg.eigh(cov)
    ref_m, ref_c = exact_box_moments(mu, cov, F["lower"], F["upper"])
    box_mass = float(multivariate_normal(mu, cov).cdf(F["upper"]) - multivariate_normal(mu, cov).cdf([F["lower"][0], F["upper"][1]])
                     - multivariate_normal(mu, cov).cdf([F["upper"][0], F["lower"][1]]) + multivariate_normal(mu, cov).cdf(F["lower"]))
    out = {"case": "F5_weak_identifiability from benchmarks/core_gap_hd_uq/FAILURE_CASES.json (committed observations reused byte-for-byte)",
           "model": "y = t1 + t2 x, x = linspace(10, 10.05, 6), sigma 0.01, flat prior on [-50,50] x [-5,5]",
           "parameter_count": 2,
           "trusted_reference": {
               "analytic_gaussian": {"mean": mu.tolist(), "covariance": cov.tolist(), "sd": np.sqrt(np.diag(cov)).tolist(),
                                     "correlation": float(cov[0, 1] / math.sqrt(cov[0, 0] * cov[1, 1]))},
               "principal_axes": {"eigenvalues": lam.tolist(), "widths_sd": np.sqrt(lam).tolist(), "thin_direction": vec[:, 0].tolist(),
                                  "condition_number": float(lam[1] / lam[0])},
               "conditional_sd_t1_given_t2": float(1 / math.sqrt(np.linalg.inv(cov)[0, 0])),
               "box_probability_mass": box_mass,
               "independent_quadrature_in_principal_coordinates_truncated_to_box": {"mean": ref_m.tolist(), "sd": np.sqrt(np.diag(ref_c)).tolist()},
           },
           "grids": []}
    for per in (201, 401, 801):
        for window in ("declared_bounds", "estimate_pm_6_marginal_sd", "declared_bounds_offset_half_step"):
            sd = np.sqrt(np.diag(cov))
            if window == "declared_bounds":
                axes = [np.linspace(F["lower"][i], F["upper"][i], per) for i in range(2)]
            elif window == "declared_bounds_offset_half_step":
                axes = [np.linspace(F["lower"][i], F["upper"][i], per) for i in range(2)]
                axes = [a[:-1] + 0.5 * (a[1] - a[0]) for a in axes]
            else:
                axes = [np.linspace(mu[i] - 6 * sd[i], mu[i] + 6 * sd[i], per) for i in range(2)]
            t0 = time.perf_counter()
            post = frozen_posterior(f"F5.{window}.{per}", F["predict"], F["y"], F["sigma"], axes)
            g = guard(post)
            m_g, c_g = moments(post)
            cmp = compare(m_g, c_g, mu, cov)
            row = {"per_axis": per, "window": window, "step": [float(a[1] - a[0]) for a in axes], "guard": g,
                   "grid_mean": m_g.tolist(), "grid_sd": np.sqrt(np.diag(c_g)).tolist(), "comparison": cmp,
                   "classification": classify(g["verdict"], cmp["material"]), "wall_seconds": time.perf_counter() - t0}
            out["grids"].append(row)
            print(per, window, g["verdict"], g["status"], "ESS %.1f" % g["effective_sample_size"], "spacing", np.round(g["spacing_to_std"], 3),
                  "mean", np.round(m_g, 3), "sd", np.round(row["grid_sd"], 3), row["classification"], flush=True)
    bounds_rows = [r for r in out["grids"] if r["window"] == "declared_bounds"]
    stable = all(np.allclose(r["grid_mean"], bounds_rows[0]["grid_mean"], rtol=1e-6, atol=1e-9) and
                 np.allclose(r["grid_sd"], bounds_rows[0]["grid_sd"], rtol=1e-6) for r in bounds_rows)
    out["GRID_STABLE_BUT_WRONG"] = {"stable_under_refinement": bool(stable), "all_accepted_by_guard": all(r["guard"]["verdict"] == "ACCEPT" for r in bounds_rows),
                                    "all_materially_wrong": all(r["comparison"]["material"] for r in bounds_rows),
                                    "occurs": bool(stable and all(r["guard"]["verdict"] == "ACCEPT" and r["comparison"]["material"] for r in bounds_rows))}
    # why stable: the ridge's slope maps one t2 step onto almost exactly one t1 step at every nested refinement
    h0 = [bounds_rows[0]["step"][0], bounds_rows[0]["step"][1]]
    slope = float(-np.linalg.inv(cov)[0, 1] / np.linalg.inv(cov)[0, 0])  # d t1 / d t2 along the ridge
    out["mechanism"] = {"ridge_slope_dt1_dt2": slope, "t1_shift_per_t2_step_over_t1_step": abs(slope) * h0[1] / h0[0],
                        "note": "the same ratio holds at every nested refinement (both steps halve), so the sampled phase pattern of the ridge through the lattice repeats: resolution-stable aliasing"}
    post = frozen_posterior("F5.declared_bounds.801.cand", F["predict"], F["y"], F["sigma"], [np.linspace(F["lower"][i], F["upper"][i], 801) for i in range(2)])
    off = frozen_posterior("F5.declared_bounds.801.offset", F["predict"], F["y"], F["sigma"],
                           [(lambda a: a[:-1] + 0.5 * (a[1] - a[0]))(np.linspace(F["lower"][i], F["upper"][i], 801)) for i in range(2)])
    out["candidates_on_declared_bounds_801"] = candidates(post, offset_posterior=off)
    out["aliasing_number_with_true_sigma"] = aliasing_number(cov, steps_of(post))
    return out


# =====================================================================
# Phase 3: adversarial family (exact Gaussian targets)
# =====================================================================

def gaussian_embedding(mu, sigma):
    L = np.linalg.cholesky(sigma)
    A = np.linalg.inv(L)
    y = A @ mu
    return (lambda pts: pts @ A.T), y, np.ones(len(mu))


def run_case(tag, mu, sigma, axes, offset=True):
    predict, y, s = gaussian_embedding(mu, sigma)
    post = frozen_posterior(tag, predict, y, s, axes)
    off = None
    if offset:
        off_axes = [a + 0.5 * (a[1] - a[0]) for a in axes]
        off = frozen_posterior(tag + ".off", predict, y, s, off_axes)
    g = guard(post)
    m_g, c_g = moments(post)
    cmp = compare(m_g, c_g, mu, sigma)
    cand = candidates(post, offset_posterior=off)
    h = steps_of(post)
    return {"tag": tag, "guard": g, "comparison": cmp, "classification": classify(g["verdict"], cmp["material"]),
            "classification_post_hoc_thin": classify(g["verdict"], cmp["post_hoc_thin_direction"]["material_including_thin_direction"]),
            "candidates": {k: v for k, v in cand.items() if k != "sigma_H"},
            "aliasing_number_true_sigma": aliasing_number(sigma, h), "steps": h.tolist(),
            "principal_widths_true": np.sqrt(np.linalg.eigvalsh(sigma)).tolist(),
            "marginal_sd_true": np.sqrt(np.diag(sigma)).tolist()}


def family():
    rng = np.random.default_rng(20260913)
    rows = []

    def sigma_from(rho, s1=1.0, s2=1.0):
        return np.asarray([[s1 * s1, rho * s1 * s2], [rho * s1 * s2, s2 * s2]])

    # F1: correlation x window x density x lattice phase (equal marginals)
    for rho in (0.0, 0.5, 0.9, 0.99, 0.999, 0.9999):
        for window in (6.0, 20.0):
            for m in (11, 21, 41, 81, 161):
                for seed in range(4):
                    sig = sigma_from(rho)
                    sd = np.sqrt(np.diag(sig))
                    h = 2 * window * sd / (m - 1)
                    mu = rng.uniform(-0.5, 0.5, 2) * h  # lattice phase
                    axes = [np.linspace(-window * sd[i], window * sd[i], m) for i in range(2)]
                    r = run_case(f"rho{rho}.W{window}.m{m}.s{seed}", mu, sig, axes)
                    r.update({"family": "correlation", "rho": rho, "window_marginal_sd": window, "per_axis": m, "seed": seed})
                    rows.append(r)
        print("rho", rho, "done", flush=True)
    # F2: ridge rotation x thin width (principal widths 1 and w, angle phi)
    for w in (1.0, 0.1, 0.01, 0.001):
        for phi in (0.0, 10.0, 30.0, 45.0, 80.0, 90.0):
            for m in (21, 81):
                for seed in range(3):
                    c, s_ = math.cos(math.radians(phi)), math.sin(math.radians(phi))
                    V = np.asarray([[c, -s_], [s_, c]])
                    sig = V @ np.diag([1.0, w * w]) @ V.T
                    sd = np.sqrt(np.diag(sig))
                    h = 12 * sd / (m - 1)
                    mu = rng.uniform(-0.5, 0.5, 2) * h
                    axes = [np.linspace(-6 * sd[i], 6 * sd[i], m) for i in range(2)]
                    r = run_case(f"w{w}.phi{phi}.m{m}.s{seed}", mu, sig, axes)
                    r.update({"family": "rotation", "thin_width": w, "angle_deg": phi, "per_axis": m, "seed": seed})
                    rows.append(r)
        print("width", w, "done", flush=True)
    # F3: parameter scaling with a FIXED common physical window (not marginal-sd scaled)
    for c_scale in (1.0, 10.0, 1000.0):
        for m in (41, 161):
            for seed in range(3):
                sig = np.diag([1.0, c_scale]) @ sigma_from(0.999) @ np.diag([1.0, c_scale])
                half = 6 * math.sqrt(sig[1, 1])  # window set by the larger axis, applied to both
                h = 2 * half / (m - 1)
                mu = rng.uniform(-0.5, 0.5, 2) * h
                axes = [np.linspace(-half, half, m) for _ in range(2)]
                r = run_case(f"scale{c_scale}.m{m}.s{seed}", mu, sig, axes)
                r.update({"family": "scaling_fixed_window", "scale_t2": c_scale, "per_axis": m, "seed": seed})
                rows.append(r)
    # summary tables
    def summarize(sel):
        counts = {k: 0 for k in ("A_CORRECT_ACCEPT", "B_CORRECT_REFUSE", "C_FALSE_ACCEPT", "D_FALSE_REFUSE")}
        for r in sel:
            counts[r["classification"]] += 1
        return counts
    summary = {"overall": summarize(rows),
               "overall_post_hoc_thin": {k: sum(1 for r in rows if r["classification_post_hoc_thin"] == k) for k in ("A_CORRECT_ACCEPT", "B_CORRECT_REFUSE", "C_FALSE_ACCEPT", "D_FALSE_REFUSE")}}
    for rho in (0.0, 0.5, 0.9, 0.99, 0.999, 0.9999):
        summary[f"rho={rho}"] = summarize([r for r in rows if r.get("rho") == rho])
    for w in (1.0, 0.1, 0.01, 0.001):
        summary[f"thin_width={w}"] = summarize([r for r in rows if r.get("thin_width") == w])
    for c_scale in (1.0, 10.0, 1000.0):
        summary[f"scale={c_scale}"] = summarize([r for r in rows if r.get("scale_t2") == c_scale])
    cand = {}
    for rule in ("declared", "post_hoc_thin"):
        for key in ("A", "B", "C", "D", "E", "F", "GUARD", "GUARD_OR_D"):
            tp = fp = fn = tn = 0
            for r in rows:
                if key == "GUARD":
                    flag = r["guard"]["verdict"] == "REFUSE"
                elif key == "GUARD_OR_D":
                    flag = r["guard"]["verdict"] == "REFUSE" or r["candidates"]["D"]["flag"]
                else:
                    flag = r["candidates"].get(key, {}).get("flag")
                    if flag is None:
                        continue
                bad = r["comparison"]["material"] if rule == "declared" else r["comparison"]["post_hoc_thin_direction"]["material_including_thin_direction"]
                tp += flag and bad; fp += flag and not bad; fn += (not flag) and bad; tn += (not flag) and not bad
            cand[f"{rule}:{key}"] = {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn}
    for key in ():
        tp = fp = fn = tn = 0
        for r in rows:
            flag = r["candidates"].get(key, {}).get("flag")
            if flag is None:
                continue
            bad = r["comparison"]["material"]
            tp += flag and bad
            fp += flag and not bad
            fn += (not flag) and bad
            tn += (not flag) and not bad
        cand[key] = {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn}
    # current guard as a detector, same accounting
    cand["current_guard"] = {"true_positive": summary["overall"]["B_CORRECT_REFUSE"], "false_positive": summary["overall"]["D_FALSE_REFUSE"],
                             "false_negative": summary["overall"]["C_FALSE_ACCEPT"], "true_negative": summary["overall"]["A_CORRECT_ACCEPT"]}
    # combined: current guard OR D
    tp = fp = fn = tn = 0
    for r in rows:
        flag = r["guard"]["verdict"] == "REFUSE" or r["candidates"]["D"]["flag"]
        bad = r["comparison"]["material"]
        tp += flag and bad; fp += flag and not bad; fn += (not flag) and bad; tn += (not flag) and not bad
    cand["current_guard_OR_D"] = {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn}
    return {"schema": "thin_ridge_family/1", "material_rule": MATERIAL, "thresholds": THRESHOLDS, "cases": len(rows),
            "summary": summary, "candidate_confusion": cand, "rows": rows}


# =====================================================================
# Phase 4: the same physical posterior in other coordinates
# =====================================================================

def parameterization():
    F = f5_problem()
    mu, cov = F["mu"], F["cov"]
    lam, V = np.linalg.eigh(cov)
    lower, upper = F["lower"], F["upper"]
    corners = np.asarray(list(itertools.product(*zip(lower, upper))))
    inside_theta = lambda th: np.all(th >= lower, axis=1) & np.all(th <= upper, axis=1)
    out = {}
    per = 801
    systems = {
        "original": (np.eye(2), np.zeros(2)),
        "principal_axes_rotated": (V.T, V.T @ mu),              # psi = V^T theta
        "whitened": (np.diag(1 / np.sqrt(lam)) @ V.T, np.diag(1 / np.sqrt(lam)) @ V.T @ mu),
        "scaled_t2_x100": (np.diag([1.0, 100.0]), np.diag([1.0, 100.0]) @ mu),
    }
    for name, (T, _) in systems.items():
        Tinv = np.linalg.inv(T)
        box = corners @ T.T
        lo, hi = box.min(axis=0), box.max(axis=0)
        axes = [np.linspace(lo[i], hi[i], per) for i in range(2)]
        predict = lambda psi, Tinv=Tinv: F["predict"](psi @ Tinv.T)
        inside = lambda psi, Tinv=Tinv: inside_theta(psi @ Tinv.T)
        post = frozen_posterior(f"param.{name}", predict, F["y"], F["sigma"], axes, inside=inside)
        g = guard(post)
        m_psi, c_psi = moments(post)
        m_theta, c_theta = Tinv @ m_psi, Tinv @ c_psi @ Tinv.T  # back to physical coordinates
        cmp = compare(m_theta, c_theta, mu, cov)
        cand = candidates(post)
        out[name] = {"guard": g, "comparison_in_physical_coordinates": cmp, "classification": classify(g["verdict"], cmp["material"]),
                     "classification_post_hoc_thin": classify(g["verdict"], cmp["post_hoc_thin_direction"]["material_including_thin_direction"]),
                     "steps_in_this_coordinate_system": steps_of(post).tolist(),
                     "candidates": {k: v for k, v in cand.items() if k != "sigma_H"}}
        print(name, g["verdict"], g["status"], "ESS %.1f" % g["effective_sample_size"], np.round(g["spacing_to_std"], 3), out[name]["classification"],
              {k: v["flag"] for k, v in cand.items() if k in "ABCDE"}, flush=True)
    return {"schema": "thin_ridge_parameterization/1", "posterior": "F5 physical posterior, flat prior on the declared box, 801 points per axis over the box's bounding window in each coordinate system", "systems": out}


# =====================================================================
# Phase 6: low-dimensional regression on existing trusted cases
# =====================================================================

def regression(k2_path, only_k2=False):
    out = {}
    if only_k2:
        return {"cases": _regression_k2(k2_path)}
    # TCR wide / narrow, exactly as tests/inference/test_tcr_calibration.py posterior_over()
    from engcore.studies import TcrTruth, ols_reference_estimate, synthesize_tcr_observations, tcr_forward_table
    OHM, KELVIN, PER_KELVIN = "ohm", "kelvin", "1/kelvin"
    t_ref = Quantity(293.15, KELVIN)
    truth = TcrTruth(reference_resistance=Quantity(1.2570, OHM), temperature_coefficient=Quantity(0.003930, PER_KELVIN), reference_temperature=t_ref)
    for name, temps in (("TCR_WIDE", [300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0]), ("TCR_NARROW", [299.0, 299.5, 300.0, 300.5, 301.0, 301.5])):
        obs = synthesize_tcr_observations(truth, temps, sigma=Quantity(0.002, OHM), dataset_id="tcr.cal", seed=20260912)
        by = {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(temps)}
        oracle = ols_reference_estimate(obs, by, t_ref)

        def grid_for(shift):
            ra = np.linspace(oracle["reference_resistance"] - 6 * oracle["se_reference_resistance"], oracle["reference_resistance"] + 6 * oracle["se_reference_resistance"], 41)
            aa = np.linspace(oracle["temperature_coefficient"] - 6 * oracle["se_temperature_coefficient"], oracle["temperature_coefficient"] + 6 * oracle["se_temperature_coefficient"], 41)
            if shift:
                ra, aa = ra + 0.5 * (ra[1] - ra[0]), aa + 0.5 * (aa[1] - aa[0])
            pts = [(float(a), float(b)) for a in ra for b in aa]
            return gaussian_grid_posterior(tcr_forward_table(obs, pts, reference_temperature=t_ref, temperatures_by_condition=by), obs)
        post, off = grid_for(False), grid_for(True)
        out[name] = {"guard": guard(post), "candidates": candidates(post, offset_posterior=off), "expected": "healthy (grid agrees with the exact linear-Gaussian route, HD-UQ review)"}
        print(name, out[name]["guard"]["verdict"], {k: v["flag"] for k, v in out[name]["candidates"].items() if k in "ABCDEF"}, flush=True)

    # Battery B3 P2 and P3: the committed B3 grid rule, rebuilt serially through the production adapter
    spec = __import__("importlib.util").util.spec_from_file_location("_b3_thin", ROOT / "benchmarks" / "battery_flagship_b3" / "audit" / "run_b3.py")
    H = __import__("importlib.util").util.module_from_spec(spec)
    sys.modules["_b3_thin"] = H
    spec.loader.exec_module(H)
    data = H.Data()
    for model_id in ("P2", "P3"):
        param = H.parameterization(model_id)
        full = H.wls(param, data.split.calibration, data)
        g = H.MODELS[model_id]["grid"]
        se = np.sqrt(np.diag(full["cov"]))
        axes = [np.linspace(t - g["span_marginal_standard_errors"] * e, t + g["span_marginal_standard_errors"] * e, g["per_axis"]) for t, e in zip(full["theta"], se)]
        grid = [tuple(map(float, r)) for r in np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T]
        t0 = time.perf_counter()
        post = gaussian_grid_posterior(H.forward_table(model_id, "calibration", grid, data, 1), data.split.calibration)
        out[f"BATTERY_{model_id}"] = {"guard": guard(post), "candidates": candidates(post),
                                      "F": "not run: one more full production grid", "grid_wall_seconds": time.perf_counter() - t0,
                                      "expected": "healthy (Core grid = exact linear-Gaussian route to 1e-4 sd, HD-UQ review)"}
        print(model_id, out[f"BATTERY_{model_id}"]["guard"]["verdict"], {k: v["flag"] for k, v in out[f"BATTERY_{model_id}"]["candidates"].items() if k in "ABCDE"}, flush=True)

    # deliberately weak synthetic case: F5, with a correctly windowed grid (healthy) and the bounds grid (broken)
    P1 = f5_problem()
    for label, axes in (("WEAK_F5_WINDOWED_HEALTHY", [np.linspace(P1["mu"][i] - 6 * math.sqrt(P1["cov"][i, i]), P1["mu"][i] + 6 * math.sqrt(P1["cov"][i, i]), 201) for i in range(2)]),
                        ("WEAK_F5_BOUNDS_BROKEN", [np.linspace(P1["lower"][i], P1["upper"][i], 201) for i in range(2)])):
        post = frozen_posterior(label, P1["predict"], P1["y"], P1["sigma"], axes)
        off = frozen_posterior(label + ".off", P1["predict"], P1["y"], P1["sigma"], [a + 0.5 * (a[1] - a[0]) for a in axes])
        out[label] = {"guard": guard(post), "candidates": candidates(post, offset_posterior=off),
                      "comparison": compare(*moments(post), P1["mu"], P1["cov"])}
        print(label, out[label]["guard"]["verdict"], {k: v["flag"] for k, v in out[label]["candidates"].items() if k in "ABCDEF"}, flush=True)
    return {"schema": "thin_ridge_regression/1", "cases": out}


def _regression_k2(k2_path):
    out = {}
    # Kinetics K2: the regenerated frozen 61x61 grid; MULTI must reproduce k2_report.md first
    if True:
        from experiments.kinetics_k2 import k2_config as C, k2_forward as F
        z = np.load(k2_path, allow_pickle=False)
        keys = tuple(json.loads(str(z["observation_keys"])))
        refs = tuple(tuple(r) for r in json.loads(str(z["admission_refs"])))
        reasons = tuple(json.loads(str(z["rejection_reasons"])))
        table = AdmittedForwardTable(parameter_names=C.PARAMETER_NAMES, observation_keys=keys, points=z["points"], values=z["values"],
                                     admissible_mask=z["admissible_mask"], admission_refs=refs, rejection_reasons=reasons)
        means = F.truth_means()
        report = {"MULTI": ([20.979314794931746, 8775.076414950117], [0.15202805349527396, 49.51789691706498]),
                  "WEAK_C2": ([21.07347982427268, 8806.143839722085], [1.1959411184598971, 388.8372838352901])}
        primary = F.observation_set_from_truth_means(means, seed=C.PRIMARY_SEED, condition_ids=C.MULTI_CONDITION_IDS)
        for label, cids in (("MULTI", C.MULTI_CONDITION_IDS), ("WEAK_C2", C.WEAK_CONDITION_IDS)):
            # exactly as experiments/kinetics_k2/k2_run.py: the weak control is a SUBSET of the primary draw
            obs = primary if label == "MULTI" else primary.subset(C.WEAK_CONDITION_IDS, dataset_id="K2-primary-weak-C2")
            post = gaussian_grid_posterior(table, obs)
            ref_m, ref_s = report[label]
            reproduced = bool(np.allclose(post.mean, ref_m, rtol=1e-9) and np.allclose(np.sqrt(np.diag(post.covariance)), ref_s, rtol=1e-9))
            out[f"KINETICS_K2_{label}"] = {"reproduces_k2_report": reproduced, "grid_mean": post.mean.tolist(), "grid_sd": np.sqrt(np.diag(post.covariance)).tolist(),
                                           "guard": guard(post), "candidates": candidates(post), "F": "not run: one more K2 grid is 11,163 CSTR solves",
                                           "stats": json.loads(str(z["stats"])),
                                           "expected": "MULTI healthy (local Gaussian + importance tier agree to ~2 %); WEAK_C2 bounded, prior-dominated"}
            if label == "MULTI":
                local = json.loads((ROOT / "benchmarks" / "core_gap_hd_uq" / "DOMAIN_KINETICS.json").read_text(encoding="utf-8"))["MULTI"]
                proxy = np.asarray(local["local_gaussian"]["posterior"]["covariance"])
                lam, vec = np.linalg.eigh(proxy)
                u = vec[:, 0]
                cov_g = post.covariance
                out[f"KINETICS_K2_{label}"]["thin_direction_vs_local_gaussian_proxy"] = {
                    "proxy": "HD-UQ review local Gaussian at the calibrate estimate (importance tier ESS 0.997, 100 samples); a PROXY, not exact truth",
                    "proxy_thin_sd": float(math.sqrt(lam[0])), "grid_sd_along_proxy_thin_direction": float(math.sqrt(max(float(u @ cov_g @ u), 0.0))),
                    "ratio_grid_over_proxy": float(math.sqrt(max(float(u @ cov_g @ u), 0.0)) / math.sqrt(lam[0])),
                    "aliasing_number_with_proxy_sigma": aliasing_number(proxy, steps_of(post)),
                    "proxy_marginal_sd": np.sqrt(np.diag(proxy)).tolist(), "grid_marginal_sd": np.sqrt(np.diag(cov_g)).tolist()}
            print("K2", label, reproduced, out[f"KINETICS_K2_{label}"]["guard"]["verdict"], {k: v["flag"] for k, v in out[f"KINETICS_K2_{label}"]["candidates"].items() if k in "ABCDE"}, flush=True)

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("section", choices=["phase1", "family", "parameterization", "regression", "regression_k2"])
    ap.add_argument("--k2", default=None)
    a = ap.parse_args()
    if a.section == "phase1":
        dump("PHASE1_REPRODUCTION.json", phase1())
    elif a.section == "family":
        dump("PHASE3_FAMILY.json", family())
    elif a.section == "parameterization":
        dump("PHASE4_PARAMETERIZATION.json", parameterization())
    elif a.section == "regression":
        dump("PHASE6_REGRESSION.json", regression(None))
    else:
        existing = json.loads((ROUND / "PHASE6_REGRESSION.json").read_text(encoding="utf-8"))
        existing["cases"].update(regression(a.k2, only_k2=True)["cases"])
        dump("PHASE6_REGRESSION.json", existing)


if __name__ == "__main__":
    main()
