"""Phase 8 regression matrix: every committed trusted and known-wrong grid, before and after the repair.

    python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/regression_matrix.py [--cache D:/rp_b3grids] [--workers 8]

BEFORE is the frozen rule alone (refuse iff ESS < 8 and max axis spacing >= marginal sd; predictive UQ
never refused). AFTER is what the repaired public functions do. Each row carries its truth where one
exists (exact Gaussian, dense quadrature of the closed-form law, or the committed local proxy for K2)
and the declared materiality, so a refusal can be read as a true or a false positive.

The B3 grids P1, P4, T3 and T5 are rebuilt with B3's own grid rule through the production adapter
(P2 and P3 come from the committed fixtures); built grids are cached under --cache so a re-run does not
repeat ~10 minutes of battery solves. Writes benchmarks/core_v1_thin_ridge_repair/REGRESSION_MATRIX.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "core_v1_thin_ridge_repair"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "inference"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "benchmarks" / "battery_flagship_b3" / "audit"))

import engcore.inference.calibration as cal  # noqa: E402
from engcore.inference import GridResolutionError, PosteriorGrid, assess_identifiability, gaussian_grid_posterior  # noqa: E402

import affected_tests as AT  # noqa: E402
import test_grid_resolution_repair as R  # noqa: E402


def material(post, mu, cov):
    sd_t = np.sqrt(np.diag(cov))
    mean_err = float(np.max(np.abs(post.mean - mu) / sd_t))
    ratio = np.sqrt(np.diag(post.covariance)) / sd_t
    lam, vec = np.linalg.eigh(cov)
    u = vec[:, 0]
    thin = math.sqrt(max(float(u @ post.covariance @ u), 0.0)) / math.sqrt(lam[0])
    thin_mean = abs(float(u @ (post.mean - mu))) / math.sqrt(lam[0])
    bad = bool(mean_err > 0.1 or ratio.min() < 0.9 or ratio.max() > 1.1 or not 0.9 <= thin <= 1.1 or thin_mean > 0.1)
    return bad, {"max_mean_error_sd": mean_err, "sd_ratio_min": float(ratio.min()), "sd_ratio_max": float(ratio.max()),
                 "thin_sd_ratio": thin, "thin_mean_error_sd": thin_mean}


def row(label, post, truth=None, truth_kind=None, expected=None):
    p = post.points.shape[1]
    diag = cal.posterior_grid_diagnostics(post)
    ess = float(diag["effective_sample_size"])
    before = bool(ess < 8.0 and max(diag["spacing_to_std"]) >= 1.0)
    try:
        status = assess_identifiability(post).status.value
        after = False
        reason = None
    except GridResolutionError as exc:
        status, after, reason = "GRID_TOO_COARSE_FOR_INFERENCE", True, str(exc).split(": ", 1)[1][:160]
    predictive_after = cal._grid_resolution_refusal(post, discrete_posterior_passes=True) is not None
    steps = cal._tensor_lattice_steps(post.points)
    aliasing = None
    if steps is not None and ess >= p + 1:
        S, _ = cal._fitted_lattice_covariance(post, steps)
        if S is not None:
            a = cal._minimum_aliasing_number(S, 1.0e6)
            aliasing = math.inf if a is None else float(a)
    out = {"label": label, "parameters": p, "grid_points": int(len(post.weights)), "effective_sample_size": ess,
           "aliasing_number": aliasing, "identifiability_refused_before": before, "identifiability_refused_after": after,
           "predictive_refused_before": False, "predictive_refused_after": predictive_after,
           "status_after": status, "refusal": reason, "expected": expected}
    if truth is not None:
        bad, m = material(post, *truth)
        out.update({"truth": truth_kind, "materially_wrong": bad, **m})
        out["outcome"] = ("TRUE_REFUSAL" if after and bad else "FALSE_REFUSAL" if after else
                          "MISSED" if bad else "CORRECTLY_KEPT")
    else:
        out.update({"truth": truth_kind, "materially_wrong": None, "outcome": "REFUSED_NO_TRUTH" if after else "KEPT_NO_TRUTH"})
    print(f"{label:34s} p={p} ESS={ess:9.2f} A={aliasing!s:>9.7} before={before!s:5} after={after!s:5} "
          f"pred_after={predictive_after!s:5} {out['outcome']}", flush=True)
    return out


def b3_grids(cache: pathlib.Path, workers: int):
    spec = importlib.util.spec_from_file_location("run_b3", ROOT / "benchmarks" / "battery_flagship_b3" / "audit" / "run_b3.py")
    H = importlib.util.module_from_spec(spec)
    sys.modules["run_b3"] = H
    spec.loader.exec_module(H)
    data = H.Data()
    cache.mkdir(parents=True, exist_ok=True)
    committed = json.loads((ROOT / "benchmarks" / "battery_flagship_b3" / "RESULTS.json").read_text(encoding="utf-8"))["models"]
    for model_id in ("P1", "P2", "P3", "P4", "T3", "T5"):
        param = H.parameterization(model_id)
        full = H.wls(param, data.split.calibration, data)
        g = H.MODELS[model_id]["grid"]
        path = cache / f"{model_id}.npz"
        if path.exists():
            z = np.load(path)
            post = PosteriorGrid(parameter_names=tuple(param.names), points=z["points"], weights=z["weights"],
                                 log_likelihood=z["log_likelihood"], admissible_mask=z["admissible_mask"], dataset_id=str(z["dataset_id"]))
        else:
            se = np.sqrt(np.diag(full["cov"]))
            axes = [np.linspace(t - g["span_marginal_standard_errors"] * e, t + g["span_marginal_standard_errors"] * e, g["per_axis"])
                    for t, e in zip(full["theta"], se)]
            grid = [tuple(map(float, r)) for r in np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T]
            post = gaussian_grid_posterior(H.forward_table(model_id, "calibration", grid, data, workers), data.split.calibration)
            np.savez(path, points=post.points, weights=post.weights, log_likelihood=post.log_likelihood,
                     admissible_mask=post.admissible_mask, dataset_id=post.dataset_id)
        if not np.allclose(post.mean, committed[model_id]["routes"]["CORE_GRID"]["posterior"]["mean_v"], rtol=1e-12):
            raise SystemExit(f"{model_id} does not reproduce the committed B3 grid posterior")
        yield model_id, post, (np.asarray(full["theta"]), np.asarray(full["cov"])), H, param


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="D:/rp_b3grids")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    rows = []

    mu, cov = R._f5_exact()
    for n in (201, 401, 801):
        post = R._f5_posterior([np.linspace(R.F5_LOWER[i], R.F5_UPPER[i], n) for i in range(2)], f"f5.bounds.{n}")
        rows.append(row(f"F5_bounds_{n}", post, (mu, cov), "exact linear Gaussian", "refuse"))

    wide = [300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0]
    for label, temps, n, expected in (("TCR_wide_41", wide, 41, "keep"), ("TCR_narrow_41", AT.NARROW, 41, "refuse"),
                                      ("TCR_narrow_81", AT.NARROW, 81, "keep"), ("TCR_narrow_161", AT.NARROW, 161, "keep")):
        post, m, c = R._tcr(temps, per_axis=n)
        rows.append(row(label, post, (m, c), "dense quadrature of the closed-form law", expected))

    for label, seed, n, subset, expected in (("TCR_heldout_caseC_21", 5, 21, None, "refuse"), ("TCR_heldout_caseC_81", 5, 81, None, "keep"),
                                             ("coverage_study_seed11_11", 11, 11, AT.CAL_T + AT.HELD_T, "refuse"),
                                             ("coverage_study_seed11_15", 11, 15, AT.CAL_T + AT.HELD_T, "keep")):
        temps = AT.NARROW if subset is None else AT.CAL_T
        post, (m, c) = tcr_posterior_and_truth(temps, seed, n, subset)
        rows.append(row(label, post, (m, c), "dense quadrature of the closed-form law", expected))

    proxy = R._k2_proxy_covariance()
    k2, _ = R._fixture_posterior("k2_multi", "K2-seed-20260809")
    rows.append(row("K2_MULTI", k2, (k2.mean, proxy), "committed local Gaussian proxy (DOMAIN_KINETICS.json), centred on the grid mean", "refuse"))
    weak, _ = R._fixture_posterior("k2_weak_c2", "K2-primary-weak-C2")
    rows.append(row("K2_WEAK_C2", weak, None, "none committed", "report"))

    for model_id, post, truth, H, param in b3_grids(pathlib.Path(args.cache), args.workers):
        rows.append(row(f"BATTERY_B3_{model_id}", post, truth, "exact linear Gaussian (affine model)", "keep"))
        _, T, names = H.reparameterize(model_id, param)
        mapped = PosteriorGrid(parameter_names=tuple(names), points=post.points @ T.T, weights=post.weights,
                               log_likelihood=post.log_likelihood, admissible_mask=post.admissible_mask, dataset_id=post.dataset_id)
        rows.append(row(f"BATTERY_B3_{model_id}_linearly_mapped", mapped, (T @ truth[0], T @ truth[1] @ T.T),
                        "exact linear Gaussian mapped by T", "report: not a tensor lattice"))

    for c in (1.0, 10.0, 100.0):
        rows.append(row(f"F5_rescaled_x{c:g}", R._scaled_f5(c), None, "see F5_bounds_801", "refuse"))

    out = {"schema": "thin_ridge_regression_matrix/1", "threshold": cal._ALIASING_NUMBER_MINIMUM,
           "before": "frozen rule only: refuse iff ESS < 8 and max axis spacing >= marginal sd; predictive UQ never refused",
           "after": "repaired assess_identifiability; predictive column is the refusal posterior_predictive_uq applies",
           "b1_b2": "benchmarks/battery_flagship_b1 and _b2 audit scripts re-run in a scratch worktree at the repair commit: "
                    "RESULTS.json identical to the committed files except wall-clock fields",
           "rows": rows}
    (ROUND / "REGRESSION_MATRIX.json").write_bytes((json.dumps(out, indent=1) + "\n").encode("utf-8"))


def tcr_posterior_and_truth(temps, seed, n, subset_of):
    from engcore.scientific.units.quantity import Quantity
    from engcore.studies import ols_reference_estimate, tcr_forward_table
    obs, all_temps = AT.observations(temps, seed, f"matrix.{seed}.{n}", subset_of)
    by = {f"T{i}": Quantity(t, "kelvin") for i, t in enumerate(all_temps)}
    oracle = ols_reference_estimate(obs, by, AT.T_REF)
    ra = np.linspace(oracle["reference_resistance"] - 6 * oracle["se_reference_resistance"], oracle["reference_resistance"] + 6 * oracle["se_reference_resistance"], n)
    aa = np.linspace(oracle["temperature_coefficient"] - 6 * oracle["se_temperature_coefficient"], oracle["temperature_coefficient"] + 6 * oracle["se_temperature_coefficient"], n)
    post = gaussian_grid_posterior(tcr_forward_table(obs, [(float(a), float(b)) for a in ra for b in aa], reference_temperature=AT.T_REF, temperatures_by_condition=by), obs)
    y = np.asarray([o.value.magnitude_in("ohm") for o in obs.observations])
    dT = np.asarray([by[o.condition_id].magnitude_in("kelvin") for o in obs.observations]) - 293.15
    mu0 = np.asarray([oracle["reference_resistance"], oracle["temperature_coefficient"]])
    J = np.column_stack([1 + mu0[1] * dT, mu0[0] * dT]) / AT.SIGMA
    lam, V = np.linalg.eigh(np.linalg.inv(J.T @ J))
    g = np.linspace(-12, 12, 1201)
    A, B = np.meshgrid(g * math.sqrt(lam[0]), g * math.sqrt(lam[1]), indexing="ij")
    th = mu0 + np.stack([A.ravel(), B.ravel()], axis=1) @ V.T
    chi = np.sum(((th[:, [0]] * (1 + th[:, [1]] * dT[None, :]) - y[None, :]) / AT.SIGMA) ** 2, axis=1)
    w = np.exp(-0.5 * (chi - chi.min()))
    w /= w.sum()
    m = w @ th
    return post, (m, (th - m).T @ ((th - m) * w[:, None]))


if __name__ == "__main__":
    main()
