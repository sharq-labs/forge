"""Core Gap Review, Battery B3 reference (Phases 1, 6, 9). Imported by run_review.py."""

from __future__ import annotations

import json
import time

import numpy as np
from scipy.stats import chi2

#: Declared before the comparison was run.
TOL_VS_B3_DOMAIN = {"mean_in_sd": 1e-3, "sd_relative": 1e-6, "predictive_sd_relative": 1e-6, "chi_square_relative": 1e-6}
TOL_VS_CORE_GRID = {"mean_in_sd": 0.1, "sd_ratio": (0.85, 1.15), "predictive_sd_relative": 0.05}


def load_b3(R):
    H = R._load("_b3_harness_review", R.ROOT / "benchmarks" / "battery_flagship_b3" / "audit" / "run_b3.py")
    results = json.loads((R.ROOT / "benchmarks" / "battery_flagship_b3" / "RESULTS.json").read_text(encoding="utf-8"))
    return H, results


def parameterizations(param):
    k = len(param.names)
    D = np.eye(k) - np.eye(k, k=-1)
    maps = {"successive_differences": (D, ["v0"] + [f"d{i}" for i in range(1, k)])}
    if hasattr(param, "nodes"):
        maps["monomial_coefficients"] = (np.linalg.inv(np.vander(np.asarray(param.nodes, float), increasing=True)),
                                         [f"c{i}" for i in range(k)])
    return maps


def problem_for(R, H, data, model_id):
    P = R.P
    param = H.parameterization(model_id)
    cal, held = data.split.calibration, data.split.held_out
    y, s = H.weighted(cal)
    yh, sh = H.weighted(held)
    k = len(param.names)
    problem = P.LocalProblem(names=tuple(param.names), forward=lambda t: H.forward(param, t, cal, data),
                             observed=y, sigma=s, lower=np.full(k, H.BOUNDS[0]), upper=np.full(k, H.BOUNDS[1]),
                             predict=lambda t: H.forward(param, t, held, data), predict_sigma=sh, declared_affine=True)
    return param, problem, yh, sh


def held_metrics(yh, mean, total, z95):
    err = yh - mean
    z = err / total
    stat = float(np.sum(z ** 2))
    return {"rmse_v": float(np.sqrt(np.mean(err ** 2))), "chi_square": stat, "p_value": float(chi2.sf(stat, len(z))),
            "coverage_95": int(np.sum(np.abs(err) <= z95 * total)), "n": int(len(z))}


def estimates_of(results, model_id):
    return np.asarray(list(results["models"][model_id]["calibration"]["estimates_v"].values()))


def run(R, workers):
    P = R.P
    H, results = load_b3(R)
    data = H.Data()
    out = {"schema": "core_gap_hd_uq_battery_b3_reference/1", "models": {},
           "tolerances": {"vs_b3_domain_route": TOL_VS_B3_DOMAIN, "vs_core_grid": TOL_VS_CORE_GRID}}
    for model_id in H.SCORED_MODELS:
        committed = results["models"][model_id]
        param, problem, yh, sh = problem_for(R, H, data, model_id)
        estimate = estimates_of(results, model_id)
        t0 = time.perf_counter()
        probe = P.local_gaussian(problem, estimate, reparameterizations=parameterizations(param))
        wall = time.perf_counter() - t0
        mean_p, sd_p = np.asarray(probe["posterior"]["mean"]), np.asarray(probe["posterior"]["sd"])
        pm, pt = np.asarray(probe["predictive"]["mean"]), np.asarray(probe["predictive"]["total_sd"])
        hm = held_metrics(yh, pm, pt, P.Z95)
        row = {"p": len(estimate), "probe_claim": probe["claim"], "probe_downgrades": probe["downgrades"],
               "probe_refusals": probe["refusals"], "probe_identifiability": probe["identifiability"]["status"],
               "global_uniqueness": probe["global_uniqueness"],
               "nonlinearity_max_relative_deviation": probe["nonlinearity"]["max_relative_deviation"],
               "predictive_nonlinearity_max_in_total_sd": probe["nonlinearity"]["predictive_max_deviation_in_total_sd"],
               "forward_calls": probe["forward_calls"], "wall_seconds": wall, "held_out": hm,
               "reparameterizations": {k: v["status"] for k, v in probe["reparameterizations"].items()},
               "posterior_mean_v": mean_p.tolist(), "posterior_sd_v": sd_p.tolist(), "interval_95_v": probe["posterior"]["interval_95"]}
        dom = committed["routes"]["DOMAIN_LINEAR_GAUSSIAN"]
        dm, ds = np.asarray(dom["posterior"]["mean_v"]), np.asarray(dom["posterior"]["sd_v"])
        dt = np.asarray([h["total_sd_v"] for h in dom["held_out"]])
        cmp_d = {"max_mean_diff_in_sd": float(np.max(np.abs(mean_p - dm) / ds)),
                 "max_sd_relative": float(np.max(np.abs(sd_p / ds - 1))),
                 "max_predictive_sd_relative": float(np.max(np.abs(pt / dt - 1))),
                 "chi_square_relative": abs(hm["chi_square"] / dom["metrics"]["chi_square"] - 1),
                 "identifiability_equal": probe["identifiability"]["status"] == dom["identifiability"]["status"],
                 "committed_secondary_reparam_status": dom["parameterization_sensitivity"]["secondary_identifiability"]["status"]}
        cmp_d["within_tolerance"] = bool(
            cmp_d["max_mean_diff_in_sd"] <= TOL_VS_B3_DOMAIN["mean_in_sd"]
            and cmp_d["max_sd_relative"] <= TOL_VS_B3_DOMAIN["sd_relative"]
            and cmp_d["max_predictive_sd_relative"] <= TOL_VS_B3_DOMAIN["predictive_sd_relative"]
            and cmp_d["chi_square_relative"] <= TOL_VS_B3_DOMAIN["chi_square_relative"]
            and cmp_d["identifiability_equal"])
        row["vs_b3_domain_route"] = cmp_d
        if "CORE_GRID" in committed["routes"]:
            g = committed["routes"]["CORE_GRID"]
            gm, gs = np.asarray(g["posterior"]["mean_v"]), np.asarray(g["posterior"]["sd_v"])
            gt = np.asarray([h["total_sd_v"] for h in g["held_out"]])
            ratio = sd_p / gs
            cmp_g = {"max_mean_diff_in_grid_sd": float(np.max(np.abs(mean_p - gm) / gs)),
                     "sd_ratio_range": [float(ratio.min()), float(ratio.max())],
                     "max_predictive_sd_relative": float(np.max(np.abs(pt / gt - 1))),
                     "grid_marginal_95_v": g["posterior"]["marginal_95_v"],
                     "identifiability_core": g["identifiability"]["status"], "identifiability_probe": probe["identifiability"]["status"],
                     "chi_square_core": g["metrics"]["chi_square"], "chi_square_probe": hm["chi_square"],
                     "coverage_core": g["metrics"]["coverage_95"], "coverage_probe": f"{hm['coverage_95']}/{hm['n']}",
                     "adequacy_core": g["metrics"]["adequacy"],
                     "adequacy_probe": "MODEL_INADEQUATE" if hm["p_value"] < 0.01 else "MODEL_ADEQUATE",
                     "grid_points": g["grid"]["points"], "grid_forward_predictions": g["grid"]["points"] * 100,
                     "grid_wall_seconds_12_workers": g["grid"]["wall_seconds_informational"]}
            cmp_g["within_tolerance"] = bool(
                cmp_g["max_mean_diff_in_grid_sd"] <= TOL_VS_CORE_GRID["mean_in_sd"]
                and TOL_VS_CORE_GRID["sd_ratio"][0] <= ratio.min() and ratio.max() <= TOL_VS_CORE_GRID["sd_ratio"][1]
                and cmp_g["max_predictive_sd_relative"] <= TOL_VS_CORE_GRID["predictive_sd_relative"]
                and cmp_g["identifiability_core"] == cmp_g["identifiability_probe"]
                and cmp_g["adequacy_core"] == cmp_g["adequacy_probe"])
            row["vs_core_grid"] = cmp_g
        out["models"][model_id] = row
        print(f"{model_id:4} p={len(estimate):2} claim={probe['claim']:10} dom_ok={cmp_d['within_tolerance']} "
              f"grid_ok={row.get('vs_core_grid', {}).get('within_tolerance')} chi2={hm['chi_square']:.3f} wall={wall:.2f}s", flush=True)

    # T41 flagship: verification tiers (options A and C) through the real adapter
    param, problem, yh, sh = problem_for(R, H, data, "T41")
    estimate = estimates_of(results, "T41")
    cov = np.asarray(P.local_gaussian(problem, estimate)["posterior"]["covariance"])
    t0, c0 = time.perf_counter(), problem.calls["forward"]
    is_check = P.importance_check(problem, estimate, cov, samples=2000)
    is_check.update({"wall_seconds": time.perf_counter() - t0, "forward_calls": problem.calls["forward"] - c0})
    t0, c0 = time.perf_counter(), problem.calls["forward"]
    lap = P.gauss_newton_vs_laplace(problem, estimate, cov)
    ratios = lap.pop("sd_ratio_laplace_over_gauss_newton")
    lap.pop("sd_laplace")
    lap.update({"wall_seconds": time.perf_counter() - t0, "forward_calls": problem.calls["forward"] - c0,
                "sd_ratio_range": [min(ratios), max(ratios)]})
    out["t41_verification_tiers"] = {"importance_sampling_option_C": is_check, "full_hessian_laplace_option_A": lap}
    print("T41 IS ess", is_check["ess_fraction"], "laplace sd ratio", lap["sd_ratio_range"], flush=True)

    # Phase 6 on the frozen grid: three parameterizations of one posterior
    from engcore.inference import GridResolutionError, PosteriorGrid, assess_identifiability, gaussian_grid_posterior
    grid_param = {}
    for model_id in ("P2", "T3", "P3"):
        param = H.parameterization(model_id)
        full = H.wls(param, data.split.calibration, data)
        spec = H.MODELS[model_id]["grid"]
        m, span = spec["per_axis"], spec["span_marginal_standard_errors"]
        se = np.sqrt(np.diag(full["cov"]))
        axes = [np.linspace(t - span * e, t + span * e, m) for t, e in zip(full["theta"], se)]
        grid = [tuple(map(float, r)) for r in np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T]
        table = H.forward_table(model_id, "calibration", grid, data, workers)
        posterior = gaussian_grid_posterior(table, data.split.calibration)
        del table
        estimate = estimates_of(results, model_id)
        cov = np.asarray(P.local_gaussian(problem_for(R, H, data, model_id)[1], estimate)["posterior"]["covariance"])
        maps = {"node_or_knot_voltages": (np.eye(len(axes)), list(param.names)), **parameterizations(param)}
        statuses = {}
        for name, (T, labels) in maps.items():
            mapped = PosteriorGrid(parameter_names=tuple(labels), points=posterior.points @ T.T, weights=posterior.weights,
                                   log_likelihood=posterior.log_likelihood, admissible_mask=posterior.admissible_mask,
                                   dataset_id=posterior.dataset_id)
            try:
                rep = assess_identifiability(mapped)
                entry = {"core_grid": rep.status.value, "widest_relative_width": max(rep.relative_widths),
                         "max_abs_correlation": rep.max_abs_correlation}
            except GridResolutionError:
                entry = {"core_grid": "GRID_TOO_COARSE_FOR_INFERENCE"}
            local = P.classify_identifiability(T @ estimate, T @ cov @ T.T, labels)
            entry.update({"local_gaussian": local["status"], "local_widest_relative_width": max(local["relative_widths"])})
            statuses[name] = entry
        grid_param[model_id] = statuses
        print(model_id, {k: (v["core_grid"], v["local_gaussian"]) for k, v in statuses.items()}, flush=True)
    out["parameterization_on_core_grid"] = grid_param
    return out
