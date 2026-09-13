"""Part 12: K2 kinetics through the Core V2 route, and the V1-errata quantities restated with measured values.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/kinetics.py [--workers 12]

The frozen K2 forward model, conditions, truth, observation seed, prior bounds and noise are reused read-only
(experiments/kinetics_k2). Nothing under experiments/ is edited, and the committed K2 report is not rewritten:
its errata are in benchmarks/core_v1_thin_ridge_repair/ERRATA.md, and the corrected values are here.

1. MULTI (C1, C2, C3; 6 observations, p = 2): frozen ``calibrate``, then ``route_uncertainty`` with a 6-start
   multistart. Identifiability is assessed in the declared (log k0, E/R) and in the decorrelated (ln k(T*), E/R).
2. C2 predictive uncertainty from the MULTI posterior: ``linearized_predictive_uq`` through the production
   adapter at C2.
3. REFERENCE posteriors that the repaired V1 checks accept -- the committed 61 x 61 grid does not pass them.
   Each is a tensor grid in decorrelated coordinates (u = ln k0 - E/R / T*, v = E/R). The map has unit
   determinant, so determinants are invariant and a flat prior stays flat. The prior box, a parallelogram in
   (u, v), is imposed by marking nodes outside it inadmissible.
   * MULTI: T* from the V2 covariance; +/-8 sd box, containment checked, nested refinement until moments move
     < 0.05 sd.
   * WEAK_C2: the V2 route REFUSES it (2 observations, 2 parameters). T* is chosen from the local Jacobian at the
     weak calibration; the box is the prior's full E/R range and +/-10 local sd in u; refined the same way.
4. Corrected values:
   * the MULTI covariance, its determinant and correlation (V2 route and reference grid);
   * the C2 predictive sd (V2 linearized and reference-grid predictive);
   * the A5 determinant ratio and gain.
5. The natural-k0 parameterization (IDENTITY in k0 = exp(ln k0)), calibrated and routed without multistart,
   records how route validity depends on parameterization.

Writes benchmarks/core_v2_hybrid_uq/KINETICS_K2.json.
"""

from __future__ import annotations

import argparse
import math
import time

import numpy as np

from common import dump

from engcore.hybrid_uq import (
    MultistartPolicy, RouteDecision, assess_routed_identifiability, grid_predictive_uncertainty, linearized_predictive_uq,
    local_gaussian_posterior, reconstruct_local_sensitivity, route_uncertainty,
)
from engcore.inference import (
    AdmittedForwardTable, CalibrationParameterSet, CalibrationSpec, GridResolutionError, InferenceAdmissibilityError, NoiseModel,
    ParameterBounds, ParameterIdentity, ParameterTransform, assess_identifiability, calibrate, gaussian_grid_posterior,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

COMMITTED = {  # experiments/kinetics_k2/k2_report.md (the committed, aliased grid)
    "MULTI": {"mean": [20.979314794931746, 8775.076414950117], "sd": [0.15202805349527396, 49.51789691706498],
              "covariance": [[0.02311252904956188, 7.527989120383729], [7.527989120383729, 2452.022115089074]],
              "determinant": 0.001812168548599421, "correlation": 0.9999840117764515},
    "WEAK_C2": {"mean": [21.07347982427268, 8806.143839722085], "sd": [1.1959411184598971, 388.8372838352901],
                "covariance": [[1.4302751588231097, 465.0223121929614], [465.02231219296146, 151194.43330040597]],
                "determinant": 3.891264620109364, "correlation": 0.9999910028010043},
    "A5_det_ratio_multi_over_weak": 4.66e-4, "A5_gain_weak_over_multi": 2147.3, "A5_threshold_ratio": 0.5,
}
CONVERGENCE_SD = 0.05
EDGE_DROP = math.log(1.0e6)


def setup():
    from experiments.kinetics_k2 import k2_config as C, k2_forward as F
    from engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
    from engcore.domains.kinetics.cstr.problem import CSTR_MODEL
    return C, F, CSTRInferenceForwardAdapter, ModelReference(CSTR_MODEL.model_id, CSTR_MODEL.version)


def evaluator_for(C, Adapter, observations, *, natural_k0=False, counter=None):
    adapter = Adapter()
    conditions = list(dict.fromkeys(o.condition_id for o in observations.observations))

    def evaluate(vector):
        if counter is not None:
            counter["n"] += 1
        a, e = float(vector[0]), float(vector[1])
        try:
            chemistry = C.chemistry_from_coordinates(math.log(a) if natural_k0 else a, e)
        except ValueError:
            return None
        preds = {cid: adapter.evaluate(C.CONDITION_BY_ID[cid].build(chemistry), observable_names=C.OBSERVABLE_NAMES,
                                       run_id_prefix=f"v2-{cid}") for cid in conditions}
        return [preds[o.condition_id].value(o.observable_name) for o in observations.observations]
    return evaluate


def parameter_set(C, model, *, natural_k0=False, transform="identity"):
    if natural_k0:
        first = ParameterIdentity(name="k0", unit="1/s", model=model, transform=ParameterTransform(transform),
                                  bounds=ParameterBounds(Quantity(math.exp(C.LOG_K0_BOUNDS[0]), "1/s"), Quantity(math.exp(C.LOG_K0_BOUNDS[1]), "1/s")))
    else:
        first = ParameterIdentity(name="log_k0", unit="dimensionless", model=model,
                                  bounds=ParameterBounds(Quantity(C.LOG_K0_BOUNDS[0], "dimensionless"), Quantity(C.LOG_K0_BOUNDS[1], "dimensionless")))
    second = ParameterIdentity(name="e_over_r_k", unit="kelvin", model=model,
                               bounds=ParameterBounds(Quantity(C.E_OVER_R_BOUNDS_K[0], "kelvin"), Quantity(C.E_OVER_R_BOUNDS_K[1], "kelvin")))
    return CalibrationParameterSet((first, second))


def spec_for(C, params, start):
    return CalibrationSpec(parameters=params, fixed={}, noise_model=NoiseModel(),
                           initial_point={p.name: Quantity(float(v), p.unit) for p, v in zip(params.parameters, start)})


def build_uv_posterior(C, F, observations, T_star, u_axis, v_axis, workers, c2_keys):
    uv = np.array(np.meshgrid(u_axis, v_axis, indexing="ij")).reshape(2, -1).T
    lv = np.column_stack([uv[:, 0] + uv[:, 1] / T_star, uv[:, 1]])
    inside = ((lv[:, 0] >= C.LOG_K0_BOUNDS[0]) & (lv[:, 0] <= C.LOG_K0_BOUNDS[1])
              & (lv[:, 1] >= C.E_OVER_R_BOUNDS_K[0]) & (lv[:, 1] <= C.E_OVER_R_BOUNDS_K[1]))
    condition_ids = tuple(dict.fromkeys(o.condition_id for o in observations.observations))
    t0 = time.perf_counter()
    built = F.build_forward_table_with_stats(lv[inside], observations, condition_ids=condition_ids, workers=workers)
    seconds = time.perf_counter() - t0
    keys = observations.keys
    n = len(uv)
    values = np.zeros((n, len(keys)))
    mask = np.zeros(n, dtype=bool)
    refs: list[tuple] = [()] * n
    reasons = ["outside the frozen K2 prior box"] * n
    t = built.table
    for j, i in enumerate(np.flatnonzero(inside)):
        values[i] = t.values[j]
        mask[i] = bool(t.admissible_mask[j])
        refs[i] = t.admission_refs[j]
        reasons[i] = t.rejection_reasons[j]
    names = (f"log_k_at_{T_star:.3f}K", "e_over_r_k")
    table = AdmittedForwardTable(parameter_names=names, observation_keys=keys, points=uv, values=values, admissible_mask=mask,
                                 admission_refs=tuple(refs), rejection_reasons=tuple(reasons))
    posterior = gaussian_grid_posterior(table, observations)
    c2 = None
    if c2_keys:
        cols = [keys.index(k) for k in c2_keys]
        c2 = AdmittedForwardTable(parameter_names=names, observation_keys=tuple(c2_keys), points=uv, values=values[:, cols], admissible_mask=mask,
                                  admission_refs=tuple(tuple(r[c] for c in cols) if m else () for r, m in zip(refs, mask)),
                                  rejection_reasons=tuple(reasons))
    stats = {"nodes": [len(u_axis), len(v_axis)], "inside_prior_box": int(inside.sum()), "admitted": int(mask.sum()),
             "condition_solves": int(built.stats.condition_attempts), "wall_seconds": seconds, "workers": built.stats.workers}
    return posterior, c2, stats


def moments_lv(posterior, T_star):
    Tinv = np.asarray([[1.0, 1.0 / T_star], [0.0, 1.0]])  # (u, v) -> (ln k0, E/R), unit determinant
    m = Tinv @ np.asarray(posterior.mean)
    c = Tinv @ np.asarray(posterior.covariance) @ Tinv.T
    return m, c


def edge_drops(posterior, shape):
    ll = np.where(posterior.admissible_mask & np.isfinite(posterior.log_likelihood), posterior.log_likelihood, -np.inf).reshape(shape)
    peak = float(np.max(ll))
    return {"u_low": peak - float(np.max(ll[0, :])), "u_high": peak - float(np.max(ll[-1, :])),
            "v_low": peak - float(np.max(ll[:, 0])), "v_high": peak - float(np.max(ll[:, -1]))}


def converged_reference(C, F, observations, T_star, u_range, v_range, nu, nv, workers, c2_keys, label, max_attempts=4):
    """Contain, V1-accept and converge (moments move < 0.05 sd between nested refinements)."""
    u_lo, u_hi = u_range
    v_lo, v_hi = max(v_range[0], C.E_OVER_R_BOUNDS_K[0]), min(v_range[1], C.E_OVER_R_BOUNDS_K[1])
    history = []
    previous = None
    for attempt in range(max_attempts):
        u_axis, v_axis = np.linspace(u_lo, u_hi, nu), np.linspace(v_lo, v_hi, nv)
        posterior, c2, stats = build_uv_posterior(C, F, observations, T_star, u_axis, v_axis, workers, c2_keys)
        drops = edge_drops(posterior, (nu, nv))
        try:
            report = assess_identifiability(posterior)
            v1 = {"accepted": True, "status": report.status.value}
        except GridResolutionError as exc:
            v1 = {"accepted": False, "refusal": str(exc)[:300]}
        m, c = moments_lv(posterior, T_star)
        entry = {"attempt": attempt, "u_range": [u_lo, u_hi], "v_range": [v_lo, v_hi], **stats, "edge_log_likelihood_drop": drops, "v1": v1,
                 "mean_lv": m.tolist(), "sd_lv": np.sqrt(np.diag(c)).tolist(), "determinant": float(np.linalg.det(c))}
        history.append(entry)
        print(f"  {label} attempt {attempt}: nodes {nu}x{nv} admitted {stats['admitted']} v1 {v1.get('accepted')} drops "
              f"{ {k: round(v, 1) for k, v in drops.items()} } mean {np.round(m, 4)} sd {np.round(np.sqrt(np.diag(c)), 4)} "
              f"det {entry['determinant']:.5g} ({stats['wall_seconds']:.0f}s)", flush=True)
        grew = False
        for side in ("u_low", "u_high", "v_low", "v_high"):
            at_prior = (side == "v_low" and v_lo <= C.E_OVER_R_BOUNDS_K[0]) or (side == "v_high" and v_hi >= C.E_OVER_R_BOUNDS_K[1])
            if drops[side] < EDGE_DROP and not at_prior:
                grew = True
                if side == "u_low":
                    u_lo -= 0.5 * (u_hi - u_lo)
                elif side == "u_high":
                    u_hi += 0.5 * (u_hi - u_lo)
                elif side == "v_low":
                    v_lo = max(v_lo - 0.5 * (v_hi - v_lo), C.E_OVER_R_BOUNDS_K[0])
                else:
                    v_hi = min(v_hi + 0.5 * (v_hi - v_lo), C.E_OVER_R_BOUNDS_K[1])
        if grew:
            previous = None
            continue
        if v1["accepted"] and previous is not None:
            sd = np.asarray(entry["sd_lv"])
            moved = max(float(np.max(np.abs(np.asarray(entry["mean_lv"]) - np.asarray(previous["mean_lv"])) / sd)),
                        float(np.max(np.abs(sd - np.asarray(previous["sd_lv"])) / sd)))
            entry["moved_since_previous_sd"] = moved
            if moved < CONVERGENCE_SD:
                return posterior, c2, history, True
        previous = entry if v1["accepted"] else None
        nu, nv = 2 * (nu - 1) + 1, 2 * (nv - 1) + 1
    return posterior, c2, history, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--starts", type=int, default=6)
    args = ap.parse_args()
    C, F, Adapter, model = setup()
    means = F.truth_means()
    primary = F.observation_set_from_truth_means(means, seed=C.PRIMARY_SEED, condition_ids=C.MULTI_CONDITION_IDS)
    weak = primary.subset(C.WEAK_CONDITION_IDS, dataset_id="K2-primary-weak-C2")
    out = {"schema": "core_v2_hybrid_uq_kinetics/1", "committed_k2_report_values": COMMITTED, "convergence_sd": CONVERGENCE_SD}
    params = parameter_set(C, model)
    twin = TwinReference("k2-v2-reference", "1")

    # 1. MULTI through V2
    counter = {"n": 0}
    forward = evaluator_for(C, Adapter, primary, counter=counter)
    start = (0.5 * sum(C.LOG_K0_BOUNDS), 0.5 * sum(C.E_OVER_R_BOUNDS_K))
    t0 = time.perf_counter()
    fit = calibrate(spec_for(C, params, start), primary, forward, heldout_dataset_id="K2.v2.multi.heldout", max_evaluations=400, seed=C.PRIMARY_SEED)
    cal = {"status": fit.status.value, "evaluations": counter["n"], "condition_solves": 3 * counter["n"], "wall_seconds": time.perf_counter() - t0,
           "estimate": list(fit.estimate_vector), "chi_square": fit.objective_value}
    print("MULTI calibration", cal, flush=True)
    t0, c0 = time.perf_counter(), counter["n"]
    routed = route_uncertainty(calibration=fit, observations=primary, forward=forward, multistart=MultistartPolicy(starts=args.starts, max_evaluations=400))
    route = {"decision": routed.decision.value, "claim": routed.claim.value, "considered": routed.considered,
             "evaluations": counter["n"] - c0, "condition_solves": 3 * (counter["n"] - c0), "wall_seconds": time.perf_counter() - t0}
    post = routed.local_posterior
    route.update({"reasons": [r.value for r in post.reasons], "uniqueness": post.diagnostics.uniqueness,
                  "multistart": [{k: v for k, v in m.items() if k in ("status", "classification", "retractions", "estimate", "chi_square", "mahalanobis_sq")}
                                 for m in post.diagnostics.multistart],
                  "nonlinearity_index": post.diagnostics.nonlinearity_index, "jacobian_condition": post.diagnostics.jacobian_condition})
    print("MULTI route", route["decision"], route["claim"], route["reasons"], route["uniqueness"], f"{route['wall_seconds']:.0f}s", flush=True)
    out["MULTI_v2"] = {"calibration": cal, "route": route}
    if routed.decision is RouteDecision.REFUSED:
        dump("KINETICS_K2.json", out)
        raise SystemExit("MULTI refused by the V2 route")
    cov = np.asarray(post.covariance)
    T_star = float(cov[1, 1] / cov[0, 1])  # decorrelates ln k0 - E/R / T* from E/R
    T = np.asarray([[1.0, -1.0 / T_star], [0.0, 1.0]])
    aligned = post.reparameterized(T, ("log_k_at_T_star", "e_over_r_k"), ("dimensionless", "kelvin"), f"ln_k_at_{T_star:.3f}K")
    ident_declared = assess_routed_identifiability(post)
    ident_aligned = assess_routed_identifiability(aligned)
    sd = np.sqrt(np.diag(cov))
    out["MULTI_v2"].update({
        "mean": list(post.inference_point), "sd": sd.tolist(), "covariance": cov.tolist(), "determinant": float(np.linalg.det(cov)),
        "correlation": float(cov[0, 1] / (sd[0] * sd[1])), "intervals_95": [[i.lower, i.upper] for i in post.intervals()],
        "T_star_k": T_star, "identifiability": {"declared_ln_k0_e_over_r": ident_declared.status.value,
                                               f"ln_k_at_T_star_e_over_r": ident_aligned.status.value},
        "aligned_covariance": np.asarray(aligned.covariance).tolist(),
    })

    # 2. C2 predictive from the MULTI posterior
    c2_obs = [o for o in primary.observations if o.condition_id == "C2"]
    c2_keys = tuple(o.key for o in c2_obs)
    predict = evaluator_for(C, Adapter, weak)
    specs = [PredictiveObservableSpec(o.key, o.value.units, o.sigma) for o in weak.observations]
    predictive = linearized_predictive_uq(post, predict, specs)
    out["MULTI_v2"]["C2_predictive"] = {r.observation_key: {"mean": r.mean, "parameter_sd": r.parameter_standard_uncertainty,
                                                           "measurement_sd": r.measurement_standard_uncertainty, "total_sd": r.total_standard_uncertainty,
                                                           "unit": r.unit, "claim": r.route_claim.value, "nonlinearity": r.predictive_nonlinearity}
                                        for r in predictive}
    print("C2 predictive", out["MULTI_v2"]["C2_predictive"], flush=True)

    # 3a. MULTI reference grid, decorrelated
    aligned_sd = np.sqrt(np.diag(np.asarray(aligned.covariance)))
    u0 = float(aligned.inference_point[0])
    v0 = float(aligned.inference_point[1])
    ref_post, ref_c2, history, converged = converged_reference(
        C, F, primary, T_star, (u0 - 8 * aligned_sd[0], u0 + 8 * aligned_sd[0]), (v0 - 8 * aligned_sd[1], v0 + 8 * aligned_sd[1]),
        33, 33, args.workers, c2_keys, "MULTI reference")
    m, c = moments_lv(ref_post, T_star)
    rs = np.sqrt(np.diag(c))
    ref = {"T_star_k": T_star, "converged": converged, "history": history, "mean": m.tolist(), "sd": rs.tolist(), "covariance": c.tolist(),
           "determinant": float(np.linalg.det(c)), "correlation": float(c[0, 1] / (rs[0] * rs[1]))}
    try:
        ref["identifiability_in_grid_coordinates"] = assess_identifiability(ref_post).status.value
        ref["C2_predictive"] = {}
        for o in c2_obs:
            r = grid_predictive_uncertainty(ref_post, ref_c2, PredictiveObservableSpec(o.key, o.value.units, o.sigma), twin=twin, model=model,
                                            source_ref="k2-v2-reference")
            ref["C2_predictive"][o.key] = {"mean": r.mean, "parameter_sd": r.parameter_standard_uncertainty, "total_sd": r.total_standard_uncertainty}
    except GridResolutionError as exc:
        ref["refusal"] = str(exc)[:300]
    out["MULTI_reference_grid"] = ref
    out["MULTI_v2"]["vs_reference"] = {"mean_shift_reference_sd": (np.abs(np.asarray(post.inference_point) - m) / rs).tolist(),
                                       "sd_ratio": (sd / rs).tolist(), "determinant_ratio": float(np.linalg.det(cov) / np.linalg.det(c))}
    print("MULTI reference", ref["mean"], ref["sd"], ref["determinant"], ref["correlation"], out["MULTI_v2"]["vs_reference"], flush=True)

    # 3b. WEAK_C2 through V2 (expected refusal) and its reference grid
    wcounter = {"n": 0}
    wforward = evaluator_for(C, Adapter, weak, counter=wcounter)
    wfit = calibrate(spec_for(C, params, fit.estimate_vector), weak, wforward, heldout_dataset_id="K2.v2.weak.heldout", max_evaluations=400, seed=C.PRIMARY_SEED)
    wrouted = route_uncertainty(calibration=wfit, observations=weak, forward=wforward, multistart=None)
    out["WEAK_C2_v2"] = {"calibration": {"status": wfit.status.value, "estimate": list(wfit.estimate_vector) if wfit.estimates else None},
                         "decision": wrouted.decision.value, "claim": wrouted.claim.value,
                         "reasons": [r.value for r in wrouted.local_posterior.reasons] if wrouted.local_posterior else []}
    print("WEAK route", out["WEAK_C2_v2"], flush=True)
    sens = reconstruct_local_sensitivity(wfit, weak, wforward)
    Aw = sens.weighted_jacobian
    wcov = np.linalg.inv(Aw.T @ Aw)
    T_weak = float(wcov[1, 1] / wcov[0, 1])
    u_w = float(wfit.estimate_vector[0] - wfit.estimate_vector[1] / T_weak)
    Tw = np.asarray([[1.0, -1.0 / T_weak], [0.0, 1.0]])
    su = float(math.sqrt((Tw @ wcov @ Tw.T)[0, 0]))
    wpost, _, whistory, wconverged = converged_reference(C, F, weak, T_weak, (u_w - 10 * su, u_w + 10 * su), C.E_OVER_R_BOUNDS_K,
                                                         33, 129, args.workers, (), "WEAK reference")
    wm, wc = moments_lv(wpost, T_weak)
    ws = np.sqrt(np.diag(wc))
    out["WEAK_C2_reference_grid"] = {"T_star_k": T_weak, "local_jacobian_design_covariance": wcov.tolist(), "converged": wconverged, "history": whistory,
                                     "mean": wm.tolist(), "sd": ws.tolist(), "covariance": wc.tolist(), "determinant": float(np.linalg.det(wc)),
                                     "correlation": float(wc[0, 1] / (ws[0] * ws[1]))}

    # 4. corrected values
    det_multi_v2 = float(np.linalg.det(cov))
    det_multi_ref = float(np.linalg.det(c))
    det_weak_ref = float(np.linalg.det(wc))
    out["CORRECTED"] = {
        "MULTI_covariance_v2": cov.tolist(), "MULTI_covariance_reference": c.tolist(),
        "MULTI_determinant_v2": det_multi_v2, "MULTI_determinant_reference": det_multi_ref, "MULTI_determinant_committed": COMMITTED["MULTI"]["determinant"],
        "MULTI_correlation_v2": out["MULTI_v2"]["correlation"], "MULTI_correlation_reference": ref["correlation"],
        "MULTI_correlation_committed": COMMITTED["MULTI"]["correlation"],
        "C2_predictive_v2": out["MULTI_v2"]["C2_predictive"], "C2_predictive_reference": ref.get("C2_predictive"),
        "WEAK_determinant_reference": det_weak_ref, "WEAK_determinant_committed": COMMITTED["WEAK_C2"]["determinant"],
        "A5_det_ratio_multi_over_weak_v2_multi_reference_weak": det_multi_v2 / det_weak_ref,
        "A5_det_ratio_multi_over_weak_reference": det_multi_ref / det_weak_ref,
        "A5_gain_weak_over_multi_reference": det_weak_ref / det_multi_ref,
        "A5_passes_reference": det_multi_ref / det_weak_ref <= COMMITTED["A5_threshold_ratio"],
        "A5_committed_ratio": COMMITTED["A5_det_ratio_multi_over_weak"], "A5_committed_gain": COMMITTED["A5_gain_weak_over_multi"],
        "reference_grids_converged": bool(converged and wconverged),
    }
    print("CORRECTED", out["CORRECTED"], flush=True)

    # 5. natural k0 parameterization, no multistart (cost)
    nparams = parameter_set(C, model, natural_k0=True)
    ncounter = {"n": 0}
    nforward = evaluator_for(C, Adapter, primary, natural_k0=True, counter=ncounter)
    nfit = calibrate(spec_for(C, nparams, (math.exp(fit.estimate_vector[0]), fit.estimate_vector[1])), primary, nforward,
                     heldout_dataset_id="K2.v2.natural.heldout", max_evaluations=400, seed=C.PRIMARY_SEED)
    npost = local_gaussian_posterior(nfit, primary, nforward, multistart=None)
    out["natural_k0_parameterization"] = {"calibration": nfit.status.value, "claim": npost.claim.value, "reasons": [r.value for r in npost.reasons],
                                          "raw_jacobian_condition": npost.diagnostics.raw_jacobian_condition,
                                          "jacobian_condition": npost.diagnostics.jacobian_condition, "nonlinearity_index": npost.diagnostics.nonlinearity_index,
                                          "identifiability": None if npost.covariance is None else assess_routed_identifiability(npost).status.value}
    lparams = parameter_set(C, model, natural_k0=True, transform="log")
    lpost = local_gaussian_posterior(calibrate(spec_for(C, lparams, (math.exp(fit.estimate_vector[0]), fit.estimate_vector[1])), primary, nforward,
                                               heldout_dataset_id="K2.v2.logdeclared.heldout", max_evaluations=400, seed=C.PRIMARY_SEED),
                                     primary, nforward, multistart=None)
    out["k0_declared_LOG_parameterization"] = {"claim": lpost.claim.value, "reasons": [r.value for r in lpost.reasons],
                                               "sd_inference": list(lpost.standard_deviations) if lpost.covariance is not None else None,
                                               "identifiability": None if lpost.covariance is None else assess_routed_identifiability(lpost).status.value}
    print("natural k0", out["natural_k0_parameterization"], "LOG-declared k0", out["k0_declared_LOG_parameterization"], flush=True)
    dump("KINETICS_K2.json", out)


if __name__ == "__main__":
    main()
