"""Part 10: Battery B3 through the Core V2 route -- the T41 flagship and every scored model.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/battery.py

Every model is calibrated by the frozen ``calibrate`` with B3's own spec, then routed by
``engcore.hybrid_uq.route_uncertainty`` with the default multistart. No tensor grid is supplied, so the grid
route is skipped. Held-out predictions come from ``linearized_predictive_uq`` through the production battery
adapter.

Compared with B3's committed DOMAIN_LINEAR_GAUSSIAN route, which is exact: the model is affine in its voltages.
The tolerances were DECLARED HERE BEFORE THE RUN; they are those of the HD-UQ review (review_battery.py).
Where B3 also committed a CORE_GRID route (P1-P4, T3, T5), the V2 result is compared with it too.

Writes benchmarks/core_v2_hybrid_uq/BATTERY_T41.json.
"""

from __future__ import annotations

import time
import tracemalloc

import numpy as np
from scipy.stats import chi2

from common import b3_harness, dump

from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    assess_routed_identifiability,
    linearized_predictive_uq,
    route_uncertainty,
)
from engcore.inference import CalibrationSpec, NoiseModel, calibrate
from engcore.uq import PredictiveObservableSpec

#: Declared before the comparison ran (HD-UQ review values).
TOL_VS_B3_DOMAIN = {"mean_in_sd": 1e-3, "sd_relative": 1e-6, "predictive_sd_relative": 1e-6, "chi_square_relative": 1e-6}
TOL_VS_CORE_GRID = {"mean_in_sd": 0.1, "sd_ratio": (0.85, 1.15), "predictive_sd_relative": 0.05}
Z95 = 1.959963984540054


def main():
    H = b3_harness()
    import json

    results = json.loads((H.ROOT / "benchmarks" / "battery_flagship_b3" / "RESULTS.json").read_text(encoding="utf-8"))
    data = H.Data()
    cal, held = data.split.calibration, data.split.held_out
    yh = np.asarray([o.value.magnitude_in(H.VOLT) for o in held.observations])
    specs = [PredictiveObservableSpec(o.key, H.VOLT, o.sigma) for o in held.observations]
    out = {"schema": "core_v2_hybrid_uq_battery/1", "declared_tolerances": {"vs_b3_domain_route": TOL_VS_B3_DOMAIN, "vs_core_grid": TOL_VS_CORE_GRID},
           "route_call": "route_uncertainty(calibration, observations, forward, multistart=MultistartPolicy()) with no grid", "models": {}}

    for model_id in H.SCORED_MODELS:
        param = H.parameterization(model_id)
        k = len(param.names)
        spec = CalibrationSpec(
            parameters=H.bc.build_curve_parameter_set(param, lower=H.Q(H.BOUNDS[0], H.VOLT), upper=H.Q(H.BOUNDS[1], H.VOLT)),
            fixed={H.ctx.NOMINAL_CAPACITY: H.FIXED.nominal_capacity, H.ctx.INTERNAL_RESISTANCE: H.FIXED.internal_resistance,
                   H.ctx.COULOMBIC_EFFICIENCY: H.FIXED.coulombic_efficiency, H.ctx.CELL_TEMPERATURE: H.CELL_TEMPERATURE,
                   H.ctx.DISCHARGE_CURRENT: H.CONDITIONING_CURRENT},
            initial_point={n: H.Q(float(v), H.VOLT) for n, v in zip(param.names, H.initial_point(k))}, noise_model=NoiseModel())
        counter = {"n": 0}
        predict_counter = {"n": 0}
        cal_evaluator = H.bc.curve_forward_evaluator(cal, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        held_evaluator = H.bc.curve_forward_evaluator(held, fixed=H.FIXED, conditions=data.conditions, parameterization=param)

        def forward(theta, ev=cal_evaluator, c=counter):
            c["n"] += 1  # forward EVALUATIONS (one call predicts every calibration observation)
            return ev(theta)

        def predict(theta, ev=held_evaluator, c=predict_counter):
            c["n"] += 1
            return ev(theta)

        t0 = time.perf_counter()
        fit = calibrate(spec, cal, forward, heldout_dataset_id=data.split.heldout_dataset_id, max_evaluations=H.MAX_EVALUATIONS, seed=H.SEED)
        calibration_seconds, calibration_calls = time.perf_counter() - t0, counter["n"]
        t0, c0 = time.perf_counter(), counter["n"]
        routed = route_uncertainty(calibration=fit, observations=cal, forward=forward, multistart=MultistartPolicy())
        route_seconds, route_calls = time.perf_counter() - t0, counter["n"] - c0
        post = routed.local_posterior
        row = {"p": k, "calibration": {"status": fit.status.value, "evaluations": calibration_calls, "wall_seconds": calibration_seconds},
               "decision": routed.decision.value, "claim": routed.claim.value, "considered": routed.considered,
               "refusals": [r.value for r in post.diagnostics.refusals], "downgrades": [r.value for r in post.diagnostics.downgrades],
               "uniqueness": post.diagnostics.uniqueness, "nonlinearity_index": post.diagnostics.nonlinearity_index,
               "jacobian_condition": post.diagnostics.jacobian_condition,
               "route": {"wall_seconds": route_seconds, "forward_evaluations_total": route_calls,
                         "forward_evaluations_diagnostic_and_jacobian": 4 * k + 1,
                         "forward_evaluations_multistart_including_start_checks": route_calls - (4 * k + 1),
                         "production_predictions": route_calls * len(cal.observations)},
               "multistart": [{"status": m["status"], "retractions": m.get("retractions"), "classification": m.get("classification")}
                              for m in post.diagnostics.multistart]}
        if routed.decision is RouteDecision.REFUSED:
            out["models"][model_id] = row
            print(model_id, "REFUSED", row["refusals"], flush=True)
            continue
        cov = np.asarray(routed.covariance)
        mean, sd = np.asarray(routed.mean), np.sqrt(np.diag(cov))
        t0, c0 = time.perf_counter(), predict_counter["n"]
        predictive = linearized_predictive_uq(post, predict, specs)
        predictive_seconds, predictive_calls = time.perf_counter() - t0, predict_counter["n"] - c0
        pm = np.asarray([r.mean for r in predictive])
        pt = np.asarray([r.total_standard_uncertainty for r in predictive])
        z = (yh - pm) / pt
        chi_square = float(np.sum(z ** 2))
        identity = assess_routed_identifiability(post)
        D = np.eye(k) - np.eye(k, k=-1)
        differences = assess_routed_identifiability(post.reparameterized(D, ["v0"] + [f"d{i}" for i in range(1, k)], [H.VOLT] * k,
                                                                         "successive_differences"))
        row.update({
            "posterior_mean_v": mean.tolist(), "posterior_sd_v": sd.tolist(),
            "covariance_digest": post.digest, "correlation_max_abs": float(np.max(np.abs(post.correlation - np.eye(k)))),
            "intervals_95_v": [[i.lower, i.upper] for i in post.intervals()],
            "predictive": {"wall_seconds": predictive_seconds, "forward_evaluations": predictive_calls,
                           "parameter_sd_v": [r.parameter_standard_uncertainty for r in predictive],
                           "measurement_sd_v": [r.measurement_standard_uncertainty for r in predictive],
                           "total_sd_v": pt.tolist(), "claim": predictive[0].route_claim.value,
                           "max_predictive_nonlinearity": max(r.predictive_nonlinearity for r in predictive),
                           "sources": list(predictive[0].sources)},
            "held_out": {"n": int(len(z)), "rmse_v": float(np.sqrt(np.mean((yh - pm) ** 2))), "chi_square": chi_square,
                         "p_value": float(chi2.sf(chi_square, len(z))), "coverage_95": int(np.sum(np.abs(z) <= Z95))},
            "identifiability": {"knot_or_node_voltages": identity.status.value, "successive_differences": differences.status.value,
                                "parameterization_digests_differ": identity.parameterization_digest != differences.parameterization_digest},
        })
        dom = results["models"][model_id]["routes"]["DOMAIN_LINEAR_GAUSSIAN"]
        dm, ds = np.asarray(dom["posterior"]["mean_v"]), np.asarray(dom["posterior"]["sd_v"])
        dt = np.asarray([h["total_sd_v"] for h in dom["held_out"]])
        order = np.argsort([data.z[o.condition_id] for o in held.observations], kind="stable")
        cmp_d = {"max_mean_diff_in_sd": float(np.max(np.abs(mean - dm) / ds)), "max_sd_relative": float(np.max(np.abs(sd / ds - 1))),
                 "max_predictive_sd_relative": float(np.max(np.abs(pt[order] / dt - 1))),
                 "chi_square_relative": abs(chi_square / dom["metrics"]["chi_square"] - 1),
                 "identifiability_equal": identity.status.value == dom["identifiability"]["status"],
                 "committed_identifiability": dom["identifiability"]["status"]}
        cmp_d["within_declared_tolerance"] = bool(cmp_d["max_mean_diff_in_sd"] <= TOL_VS_B3_DOMAIN["mean_in_sd"]
                                                  and cmp_d["max_sd_relative"] <= TOL_VS_B3_DOMAIN["sd_relative"]
                                                  and cmp_d["max_predictive_sd_relative"] <= TOL_VS_B3_DOMAIN["predictive_sd_relative"]
                                                  and cmp_d["chi_square_relative"] <= TOL_VS_B3_DOMAIN["chi_square_relative"]
                                                  and cmp_d["identifiability_equal"])
        row["vs_b3_domain_route"] = cmp_d
        if "CORE_GRID" in results["models"][model_id]["routes"]:
            g = results["models"][model_id]["routes"]["CORE_GRID"]
            gm, gs = np.asarray(g["posterior"]["mean_v"]), np.asarray(g["posterior"]["sd_v"])
            gt = np.asarray([h["total_sd_v"] for h in g["held_out"]])
            ratio = sd / gs
            cmp_g = {"max_mean_diff_in_grid_sd": float(np.max(np.abs(mean - gm) / gs)), "sd_ratio_range": [float(ratio.min()), float(ratio.max())],
                     "max_predictive_sd_relative": float(np.max(np.abs(pt[order] / gt - 1))),
                     "identifiability_grid": g["identifiability"]["status"], "grid_points": g["grid"]["points"]}
            cmp_g["within_declared_tolerance"] = bool(cmp_g["max_mean_diff_in_grid_sd"] <= TOL_VS_CORE_GRID["mean_in_sd"]
                                                      and TOL_VS_CORE_GRID["sd_ratio"][0] <= ratio.min() and ratio.max() <= TOL_VS_CORE_GRID["sd_ratio"][1]
                                                      and cmp_g["max_predictive_sd_relative"] <= TOL_VS_CORE_GRID["predictive_sd_relative"]
                                                      and cmp_g["identifiability_grid"] == identity.status.value)
            row["vs_committed_core_grid"] = cmp_g
        if model_id == "T41":
            tracemalloc.start()  # separate pass: tracemalloc never times anything
            route_uncertainty(calibration=fit, observations=cal, forward=forward, multistart=MultistartPolicy())
            linearized_predictive_uq(post, predict, specs)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            row["python_heap_peak_bytes_tracemalloc"] = peak
            row["covariance_v2"] = cov.tolist()
        out["models"][model_id] = row
        print(f"{model_id:4} p={k:2} {routed.decision.value} {routed.claim.value} dom_ok={cmp_d['within_declared_tolerance']} "
              f"grid_ok={row.get('vs_committed_core_grid', {}).get('within_declared_tolerance')} chi2={chi_square:.4f} "
              f"ident={identity.status.value}/{differences.status.value} route {route_seconds:.2f}s {route_calls} calls", flush=True)
    dump("BATTERY_T41.json", out)


if __name__ == "__main__":
    main()
