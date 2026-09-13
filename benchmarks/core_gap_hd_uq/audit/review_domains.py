"""Core Gap Review, cross-domain justification (Phase 7): TCR and CSTR kinetics.

TCR: the frozen experimental TCR study (engcore.studies), the designs its own
tests use, frozen grid vs the candidate route.

Kinetics: the frozen K2 experiment's forward model, conditions, truth and
observation seed, reused read-only. The K2 grid posterior is NOT recomputed
(22 min on 24 workers); its committed numbers in k2_report.md are the reference.
"""

from __future__ import annotations

import math
import time

import numpy as np

from engcore.inference import (
    CalibrationParameterSet,
    CalibrationSpec,
    GridResolutionError,
    InferenceAdmissibilityError,
    NoiseModel,
    ParameterBounds,
    ParameterIdentity,
    assess_identifiability,
    calibrate,
    gaussian_grid_posterior,
    posterior_grid_diagnostics,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units.quantity import Quantity


def _vector_forward(evaluator, observations):
    def forward(theta):
        out = evaluator(tuple(float(v) for v in theta))
        if out is None:
            return None
        return np.asarray([q.magnitude_in(o.value.units) for q, o in zip(out, observations.observations)])
    return forward


def _magnitudes(observations):
    return (np.asarray([o.value.magnitude for o in observations.observations]),
            np.asarray([o.sigma.magnitude_in(o.value.units) for o in observations.observations]))


# =====================================================================
# TCR
# =====================================================================

def tcr(R):
    P = R.P
    from engcore.studies import (
        TcrTruth, build_tcr_parameter_set, ols_reference_estimate, synthesize_tcr_observations,
        tcr_forward_evaluator, tcr_forward_table)
    OHM, KELVIN, PER_KELVIN = "ohm", "kelvin", "1/kelvin"
    t_ref = Quantity(293.15, KELVIN)
    sigma = Quantity(0.002, OHM)
    truth = TcrTruth(reference_resistance=Quantity(1.2570, OHM), temperature_coefficient=Quantity(0.003930, PER_KELVIN),
                     reference_temperature=t_ref)
    designs = {"WIDE_SPAN": [300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0],
               "NARROW_SPAN": [299.0, 299.5, 300.0, 300.5, 301.0, 301.5]}
    out = {"source": "engcore.studies TCR (EXPERIMENTAL study scaffolding) with the designs, truth, sigma and seed of tests/inference/test_tcr_calibration.py"}
    lower, upper = np.asarray([0.0, -0.02]), np.asarray([10.0, 0.02])
    for name, temps in designs.items():
        obs = synthesize_tcr_observations(truth, temps, sigma=sigma, dataset_id=f"tcr.{name}", seed=20260912)
        by = {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(temps)}
        evaluator = tcr_forward_evaluator(obs, reference_temperature=t_ref, temperatures_by_condition=by)
        spec = CalibrationSpec(parameters=build_tcr_parameter_set(), fixed={"reference_temperature": t_ref},
                               initial_point={"reference_resistance": Quantity(0.80, OHM), "temperature_coefficient": Quantity(0.0010, PER_KELVIN)},
                               noise_model=NoiseModel())
        fit = calibrate(spec, obs, evaluator, heldout_dataset_id=f"tcr.{name}.heldout", seed=20260912)
        estimate = np.asarray([e.value.magnitude for e in fit.estimates])

        def refit(start, spec=spec, obs=obs, evaluator=evaluator):
            s2 = CalibrationSpec(parameters=spec.parameters, fixed=spec.fixed,
                                 initial_point={"reference_resistance": Quantity(float(start[0]), OHM),
                                                "temperature_coefficient": Quantity(float(start[1]), PER_KELVIN)},
                                 noise_model=NoiseModel())
            f2 = calibrate(s2, obs, evaluator, heldout_dataset_id="tcr.multistart", seed=20260912)
            if not f2.estimates:
                return None
            return np.asarray([e.value.magnitude for e in f2.estimates]), float(f2.objective_value)

        y, s = _magnitudes(obs)
        problem = P.LocalProblem(names=("reference_resistance", "temperature_coefficient"), forward=_vector_forward(evaluator, obs),
                                 observed=y, sigma=s, lower=lower, upper=upper)
        # (R_ref, alpha) -> (R_ref, R_ref*alpha) is NONLINEAR, so it is a separate problem, not a matrix
        slope_problem = P.LocalProblem(
            names=("reference_resistance", "slope_r_ref_times_alpha"),
            forward=lambda t, ev=evaluator, ob=obs: _vector_forward(ev, ob)(np.asarray([t[0], t[1] / t[0] if t[0] > 0 else 0.0])),
            observed=y, sigma=s, lower=np.asarray([1e-6, -0.2]), upper=np.asarray([10.0, 0.2]), declared_affine=True)
        t0 = time.perf_counter()
        probe = P.local_gaussian(problem, estimate, refit=refit, starts=((0.5, -0.01), (5.0, 0.015), (2.0, 0.0)))
        wall = time.perf_counter() - t0
        slope_probe = P.local_gaussian(slope_problem, np.asarray([estimate[0], estimate[0] * estimate[1]]))

        oracle = ols_reference_estimate(obs, by, t_ref)
        axes = [np.linspace(oracle["reference_resistance"] - 6 * oracle["se_reference_resistance"], oracle["reference_resistance"] + 6 * oracle["se_reference_resistance"], 41),
                np.linspace(oracle["temperature_coefficient"] - 6 * oracle["se_temperature_coefficient"], oracle["temperature_coefficient"] + 6 * oracle["se_temperature_coefficient"], 41)]
        points = [(float(a), float(b)) for a in axes[0] for b in axes[1]]
        t0 = time.perf_counter()
        table = tcr_forward_table(obs, points, reference_temperature=t_ref, temperatures_by_condition=by)
        posterior = gaussian_grid_posterior(table, obs)
        grid_wall = time.perf_counter() - t0
        try:
            ident = assess_identifiability(posterior).to_dict()
        except GridResolutionError as exc:
            ident = {"status": "GRID_TOO_COARSE_FOR_INFERENCE", "refusal": str(exc)[:200]}
        gm, gs = posterior.mean, np.sqrt(np.diag(posterior.covariance))
        entry = {"n": len(temps), "calibration_status": fit.status.value, "estimate": estimate.tolist(),
                 "core_grid": {"points": len(points), "mean": gm.tolist(), "sd": gs.tolist(), "identifiability": ident["status"],
                               "max_abs_correlation": ident.get("max_abs_correlation"), "wall_seconds": grid_wall,
                               "marginal_95": [list(posterior.marginal_interval(i, 0.95)) for i in range(2)],
                               "diagnostics": posterior_grid_diagnostics(posterior)},
                 "local_gaussian": probe, "local_wall_seconds": wall,
                 "slope_parameterization": {"claim": slope_probe["claim"], "identifiability": slope_probe.get("identifiability", {}).get("status"),
                                            "nonlinearity": slope_probe.get("nonlinearity", {}).get("max_relative_deviation"),
                                            "refusals": slope_probe.get("refusals"), "downgrades": slope_probe.get("downgrades")}}
        if "posterior" in probe:
            ls = np.asarray(probe["posterior"]["sd"])
            entry["agreement"] = {"mean_shift_in_grid_sd": (np.abs(gm - estimate) / gs).tolist(), "sd_ratio_local_over_grid": (ls / gs).tolist(),
                                  "identifiability_equal": probe["identifiability"]["status"] == ident["status"]}
        out[name] = entry
        print(f"TCR {name}: claim={probe['claim']} {probe.get('refusals')} {probe.get('downgrades')} ident local={probe.get('identifiability', {}).get('status')} grid={ident['status']} "
              f"agreement={entry.get('agreement')} slope={entry['slope_parameterization']}", flush=True)
    return out


# =====================================================================
# Kinetics / CSTR (K2)
# =====================================================================

def kinetics(R, *, importance_samples=100):
    P = R.P
    from experiments.kinetics_k2 import k2_config as C, k2_forward as F
    from engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
    from engcore.domains.kinetics.cstr.problem import CSTR_MODEL

    model = ModelReference(CSTR_MODEL.model_id, CSTR_MODEL.version)
    means = F.truth_means()
    reference = {
        "source": "experiments/kinetics_k2/k2_report.md (frozen K2 scored run, 61x61 grid, 3,721 points, 11,163 condition solves, 1357 s on 24 workers)",
        "MULTI": {"mean": [20.979314794931746, 8775.076414950117], "sd": [0.15202805349527396, 49.51789691706498],
                  "covariance": [[0.02311252904956188, 7.527989120383729], [7.527989120383729, 2452.022115089074]],
                  "correlation": 0.9999840117764515, "grid_step": [(C.LOG_K0_BOUNDS[1] - C.LOG_K0_BOUNDS[0]) / 60, (C.E_OVER_R_BOUNDS_K[1] - C.E_OVER_R_BOUNDS_K[0]) / 60]},
        "WEAK_C2": {"mean": [21.07347982427268, 8806.143839722085], "sd": [1.1959411184598971, 388.8372838352901]},
    }
    bounds_log = np.asarray([C.LOG_K0_BOUNDS[0], C.E_OVER_R_BOUNDS_K[0]])
    bounds_up = np.asarray([C.LOG_K0_BOUNDS[1], C.E_OVER_R_BOUNDS_K[1]])
    out = {"reference_grid": reference}

    def evaluator_for(observations, natural_k0=False):
        adapter = CSTRInferenceForwardAdapter()
        conditions = []
        for o in observations.observations:
            if o.condition_id not in conditions:
                conditions.append(o.condition_id)

        def evaluate(vector):
            a, e = float(vector[0]), float(vector[1])
            log_k0 = math.log(a) if natural_k0 else a
            try:
                chemistry = C.chemistry_from_coordinates(log_k0, e)
                preds = {cid: adapter.evaluate(C.CONDITION_BY_ID[cid].build(chemistry), observable_names=C.OBSERVABLE_NAMES,
                                               run_id_prefix=f"review-{cid}") for cid in conditions}
            except (ValueError, InferenceAdmissibilityError):
                return None
            return [preds[o.condition_id].value(o.observable_name) for o in observations.observations]
        return evaluate

    def spec_for(start):
        params = CalibrationParameterSet((
            ParameterIdentity(name="log_k0", unit="dimensionless", model=model,
                              bounds=ParameterBounds(Quantity(bounds_log[0], "dimensionless"), Quantity(bounds_up[0], "dimensionless"))),
            ParameterIdentity(name="e_over_r_k", unit="kelvin", model=model,
                              bounds=ParameterBounds(Quantity(bounds_log[1], "kelvin"), Quantity(bounds_up[1], "kelvin"))),
        ))
        return CalibrationSpec(parameters=params, fixed={},
                               initial_point={"log_k0": Quantity(float(start[0]), "dimensionless"), "e_over_r_k": Quantity(float(start[1]), "kelvin")},
                               noise_model=NoiseModel())

    for label, condition_ids in (("MULTI", C.MULTI_CONDITION_IDS), ("WEAK_C2", C.WEAK_CONDITION_IDS)):
        obs = F.observation_set_from_truth_means(means, seed=C.PRIMARY_SEED, condition_ids=condition_ids)
        evaluator = evaluator_for(obs)
        calls = {"n": 0}

        def counted(v, ev=evaluator, calls=calls):
            calls["n"] += 1
            return ev(v)

        start = (0.5 * (bounds_log[0] + bounds_up[0]), 0.5 * (bounds_log[1] + bounds_up[1]))
        t0 = time.perf_counter()
        fit = calibrate(spec_for(start), obs, counted, heldout_dataset_id=f"K2.review.{label}.heldout", max_evaluations=400, seed=C.PRIMARY_SEED)
        cal_wall, cal_calls = time.perf_counter() - t0, calls["n"]
        estimate = np.asarray([e.value.magnitude for e in fit.estimates]) if fit.estimates else None
        entry = {"n_observations": len(obs.observations), "calibration": {"status": fit.status.value, "evaluations": cal_calls,
                 "condition_solves": cal_calls * len(condition_ids), "wall_seconds": cal_wall, "estimate": None if estimate is None else estimate.tolist(),
                 "termination": fit.termination_reason}}
        if estimate is None:
            out[label] = entry
            continue
        y, s = _magnitudes(obs)
        problem = P.LocalProblem(names=("log_k0", "e_over_r_k"), forward=_vector_forward(evaluator, obs), observed=y, sigma=s,
                                 lower=bounds_log, upper=bounds_up)

        def refit(st, obs=obs, evaluator=evaluator):
            f2 = calibrate(spec_for(st), obs, evaluator, heldout_dataset_id="K2.review.multistart", max_evaluations=400, seed=C.PRIMARY_SEED)
            if not f2.estimates:
                return None
            return np.asarray([e.value.magnitude for e in f2.estimates]), float(f2.objective_value)

        t_ref = 350.0
        reparam = {"log_k_at_350K_and_e_over_r": (np.asarray([[1.0, -1.0 / t_ref], [0.0, 1.0]]), ["log_k_350K", "e_over_r_k"])}
        t0 = time.perf_counter()
        starts = ((19.5, 8000.0), (22.5, 9600.0)) if label == "MULTI" else ()
        probe = P.local_gaussian(problem, estimate, refit=refit if starts else None, starts=starts, reparameterizations=reparam)
        entry["local_gaussian"] = probe
        entry["local_wall_seconds"] = time.perf_counter() - t0
        entry["local_condition_solves"] = probe["forward_calls"]["forward"] * len(condition_ids)
        if "posterior" in probe:
            ref = reference[label]
            ls, lm = np.asarray(probe["posterior"]["sd"]), estimate
            entry["vs_committed_k2_grid"] = {"mean_shift_in_grid_sd": (np.abs(lm - np.asarray(ref["mean"])) / np.asarray(ref["sd"])).tolist(),
                                             "sd_ratio_local_over_grid": (ls / np.asarray(ref["sd"])).tolist()}
            if label == "MULTI":
                cov = np.asarray(probe["posterior"]["covariance"])
                entry["vs_committed_k2_grid"]["correlation_local"] = float(cov[0, 1] / math.sqrt(cov[0, 0] * cov[1, 1]))
                t1 = time.perf_counter()
                entry["importance_check"] = P.importance_check(problem, estimate, cov, samples=importance_samples)
                entry["importance_check"]["wall_seconds"] = time.perf_counter() - t1
                natural = P.LocalProblem(names=("k0_per_s", "e_over_r_k"), forward=_vector_forward(evaluator_for(obs, natural_k0=True), obs),
                                         observed=y, sigma=s, lower=np.asarray([math.exp(bounds_log[0]), bounds_log[1]]),
                                         upper=np.asarray([math.exp(bounds_up[0]), bounds_up[1]]))
                nat = P.local_gaussian(natural, np.asarray([math.exp(estimate[0]), estimate[1]]))
                entry["natural_k0_parameterization"] = {"claim": nat["claim"], "refusals": nat.get("refusals"), "downgrades": nat.get("downgrades"),
                                                        "identifiability": nat.get("identifiability", {}).get("status"),
                                                        "nonlinearity": nat.get("nonlinearity", {}).get("max_relative_deviation")}
        out[label] = entry
        print(f"K2 {label}: cal {fit.status.value} {cal_calls} evals {cal_wall:.0f}s est {entry['calibration']['estimate']} claim={probe['claim']} "
              f"{probe.get('refusals')} {probe.get('downgrades')} ident={probe.get('identifiability', {}).get('status')} "
              f"reparam={ {k: v['status'] for k, v in probe.get('reparameterizations', {}).items()} } vs_grid={entry.get('vs_committed_k2_grid')}", flush=True)
    return out
