"""Cheap probes of what the SUPERSEDED Core V2 records would say under the audited route rules (stream hybrid).

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/superseded_probe.py battery|k2 <out.json>

BATTERY_T41.json and KINETICS_K2.json were produced before HUQ-01..14 and are too expensive to regenerate here (the
K2 MULTI multistart alone is ~76 min of CSTR solves). Their bytes are left untouched and marked superseded. This
script establishes, without any multistart refit, the part of their verdict that the new rules decide:

* every model / parameterization is calibrated exactly as its audit script calibrates it;
* the local route is built with ``multistart=None``, so the Jacobian, the 2p^2 diagonal chi-square probes, the
  bound and stationarity checks and identifiability are all measured under the new rules, and
  GLOBAL_UNIQUENESS_NOT_ASSESSED is the only reason that the missing multistart adds;
* predictions are made with the new predictive probes (axes, diagonals, Sigma grad g), scaled by parameter sd;
* the claim under the script's own multistart policy is PROJECTED: the measured reasons without
  GLOBAL_UNIQUENESS_NOT_ASSESSED, plus MULTISTART_INCOMPLETE where that policy is below the HUQ-01 minimum search.
  Whether the refits would find a second mode or a lower objective is not re-established (the committed refits
  found none), so the projection is labelled PROJECTED, never MEASURED.

The output is written to <out.json> (a scratch path); its content is quoted in the *.SUPERSEDED.json markers.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np

from common import ROOT, b3_harness, jsonable, load

from engcore.hybrid_uq import (
    MultistartPolicy, RouteClaim, RouteReason, assess_routed_identifiability, linearized_predictive_uq, local_gaussian_posterior,
)
from engcore.hybrid_uq.local_gaussian import _minimum_starts
from engcore.hybrid_uq.vocabulary import claim_for
from engcore.inference import CalibrationSpec, NoiseModel, calibrate
from engcore.uq import PredictiveObservableSpec


def projected(post, policy_starts: int, p: int, policy: MultistartPolicy) -> dict:
    measured = {r for r in post.reasons if r is not RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED}
    below = policy_starts < _minimum_starts(p) or policy.interior_fraction < 0.8 or policy.mode_separation_quantile > 0.999 \
        or policy.comparable_fit_quantile != 0.99
    reasons = set(measured) | ({RouteReason.MULTISTART_INCOMPLETE} if below else set())
    return {"label": "PROJECTED (multistart refits not re-run)", "policy_starts": policy_starts, "minimum_starts": _minimum_starts(p),
            "below_minimum_search": below, "claim": claim_for(reasons).value, "reasons": sorted(r.value for r in reasons)}


def local_summary(post) -> dict:
    d = post.diagnostics
    out = {"claim_without_multistart": post.claim.value, "reasons_without_multistart": [r.value for r in post.reasons],
           "nonlinearity_index": d.nonlinearity_index, "nonlinearity_probes_skipped": d.nonlinearity_probes_skipped,
           "minimum_chi_square_rise": d.minimum_chi_square_rise, "evaluation_count": d.evaluation_count}
    if post.covariance is not None:
        out.update({"mean": list(post.inference_point), "sd": list(post.standard_deviations),
                    "identifiability": assess_routed_identifiability(post).status.value})
    return out


def predictive_summary(records) -> dict:
    nonlinear = [r.predictive_nonlinearity for r in records if r.predictive_nonlinearity is not None]
    return {"claims": sorted({r.route_claim.value for r in records}),
            "reasons_other_than_the_missing_multistart": sorted({x.value for r in records for x in r.reasons
                                                                 if x is not RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED}),
            "max_predictive_nonlinearity_parameter_sd": max(nonlinear) if nonlinear else None,
            "parameter_sd": [r.parameter_standard_uncertainty for r in records]}


def battery() -> dict:
    H = b3_harness()
    data = H.Data()
    cal, held = data.split.calibration, data.split.held_out
    specs = [PredictiveObservableSpec(o.key, H.VOLT, o.sigma) for o in held.observations]
    committed = json.loads((ROOT / "benchmarks" / "core_v2_hybrid_uq" / "BATTERY_T41.json").read_bytes())["models"]
    policy = MultistartPolicy()
    out = {}
    for model_id in H.SCORED_MODELS:
        t0 = time.perf_counter()
        param = H.parameterization(model_id)
        k = len(param.names)
        spec = CalibrationSpec(
            parameters=H.bc.build_curve_parameter_set(param, lower=H.Q(H.BOUNDS[0], H.VOLT), upper=H.Q(H.BOUNDS[1], H.VOLT)),
            fixed={H.ctx.NOMINAL_CAPACITY: H.FIXED.nominal_capacity, H.ctx.INTERNAL_RESISTANCE: H.FIXED.internal_resistance,
                   H.ctx.COULOMBIC_EFFICIENCY: H.FIXED.coulombic_efficiency, H.ctx.CELL_TEMPERATURE: H.CELL_TEMPERATURE,
                   H.ctx.DISCHARGE_CURRENT: H.CONDITIONING_CURRENT},
            initial_point={n: H.Q(float(v), H.VOLT) for n, v in zip(param.names, H.initial_point(k))}, noise_model=NoiseModel())
        forward = H.bc.curve_forward_evaluator(cal, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        predict = H.bc.curve_forward_evaluator(held, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        fit = calibrate(spec, cal, forward, heldout_dataset_id=data.split.heldout_dataset_id, max_evaluations=H.MAX_EVALUATIONS, seed=H.SEED)
        post = local_gaussian_posterior(fit, cal, forward, multistart=None)
        row = {"p": k, **local_summary(post), "projected_with_default_multistart": projected(post, policy.starts, k, policy),
               "committed": {"claim": committed[model_id]["claim"], "uniqueness": committed[model_id]["uniqueness"],
                             "nonlinearity_index": committed[model_id]["nonlinearity_index"],
                             "predictive_claim": committed[model_id].get("predictive", {}).get("claim")}}
        if post.covariance is not None:
            row["predictive"] = predictive_summary(linearized_predictive_uq(post, predict, specs))
            sd_old = np.asarray(committed[model_id]["posterior_sd_v"])
            row["max_sd_relative_change_vs_committed"] = float(np.max(np.abs(np.asarray(row["sd"]) / sd_old - 1.0)))
        row["wall_seconds"] = time.perf_counter() - t0
        out[model_id] = row
        print(model_id, k, row["claim_without_multistart"], row["projected_with_default_multistart"]["claim"],
              row["projected_with_default_multistart"]["reasons"], f"{row['wall_seconds']:.1f}s", flush=True)
    return out


def k2() -> dict:
    K = load("k2_audit", ROOT / "benchmarks" / "core_v2_hybrid_uq" / "audit" / "kinetics.py")
    C, F, Adapter, model = K.setup()
    means = F.truth_means()
    primary = F.observation_set_from_truth_means(means, seed=C.PRIMARY_SEED, condition_ids=C.MULTI_CONDITION_IDS)
    weak = primary.subset(C.WEAK_CONDITION_IDS, dataset_id="K2-primary-weak-C2")
    params = K.parameter_set(C, model)
    start = (0.5 * sum(C.LOG_K0_BOUNDS), 0.5 * sum(C.E_OVER_R_BOUNDS_K))
    committed = json.loads((ROOT / "benchmarks" / "core_v2_hybrid_uq" / "KINETICS_K2.json").read_bytes())
    out = {}
    t0 = time.perf_counter()
    forward = K.evaluator_for(C, Adapter, primary)
    fit = calibrate(K.spec_for(C, params, start), primary, forward, heldout_dataset_id="K2.v2.multi.heldout", max_evaluations=400,
                    seed=C.PRIMARY_SEED)
    post = local_gaussian_posterior(fit, primary, forward, multistart=None)
    policy = MultistartPolicy(starts=6, max_evaluations=400)
    row = {"calibration_estimate": list(fit.estimate_vector), "committed_estimate": committed["MULTI_v2"]["calibration"]["estimate"],
           **local_summary(post), "projected_with_the_script_policy_starts_6": projected(post, 6, 2, policy),
           "committed": {"claim": committed["MULTI_v2"]["route"]["claim"], "nonlinearity_index": committed["MULTI_v2"]["route"]["nonlinearity_index"],
                         "identifiability": committed["MULTI_v2"]["identifiability"]}}
    if post.covariance is not None:
        cov = np.asarray(post.covariance)
        from engcore.scientific.units.quantity import Quantity

        T_star = float(cov[1, 1] / cov[0, 1])
        aligned = post.reparameterized([[1.0, Quantity(-1.0 / T_star, "1/kelvin")], [0.0, 1.0]], ("log_k_at_T_star", "e_over_r_k"),
                                       ("dimensionless", "kelvin"), f"ln_k_at_{T_star:.3f}K")
        row["identifiability_aligned"] = assess_routed_identifiability(aligned).status.value
        predict = K.evaluator_for(C, Adapter, weak)
        specs = [PredictiveObservableSpec(o.key, o.value.units, o.sigma) for o in weak.observations]
        row["C2_predictive"] = predictive_summary(linearized_predictive_uq(post, predict, specs))
        row["committed_C2_predictive"] = {key: {"claim": v["claim"], "nonlinearity_total_sd": v["nonlinearity"]}
                                          for key, v in committed["MULTI_v2"]["C2_predictive"].items()}
    row["wall_seconds"] = time.perf_counter() - t0
    out["MULTI"] = row
    print("MULTI", row["claim_without_multistart"], row["reasons_without_multistart"], row["nonlinearity_index"], flush=True)

    import math

    nforward = K.evaluator_for(C, Adapter, primary, natural_k0=True)
    est = committed["MULTI_v2"]["calibration"]["estimate"]
    for label, transform in (("natural_k0_identity", "identity"), ("k0_declared_log", "log")):
        t0 = time.perf_counter()
        nparams = K.parameter_set(C, model, natural_k0=True, transform=transform)
        nfit = calibrate(K.spec_for(C, nparams, (math.exp(est[0]), est[1])), primary, nforward, heldout_dataset_id=f"K2.v2.{label}.heldout",
                         max_evaluations=400, seed=C.PRIMARY_SEED)
        npost = local_gaussian_posterior(nfit, primary, nforward, multistart=None)
        out[label] = {**local_summary(npost), "committed": committed["parameterizations"][label], "wall_seconds": time.perf_counter() - t0}
        print(label, out[label]["claim_without_multistart"], out[label]["reasons_without_multistart"], flush=True)
    return out


def main():
    which, target = sys.argv[1], pathlib.Path(sys.argv[2])
    result = {"schema": "core_v2_hybrid_uq_superseded_probe/1", "probe": which,
              "multistart": "none run; claims under the audit script's policy are PROJECTED"}
    result["results"] = battery() if which == "battery" else k2()
    target.write_bytes((json.dumps(jsonable(result), indent=1, allow_nan=False) + "\n").encode("utf-8"))
    print("wrote", target, flush=True)


if __name__ == "__main__":
    main()
