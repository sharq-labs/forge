"""Does a collapsed thin direction reach the frozen predictive UQ? Merged into PHASE6_REGRESSION.json.

    python -X utf8 benchmarks/core_gap_thin_ridge/audit/predictive_impact.py --k2 <scratch>/k2_grid.npz

The best-determined parameter combination is exactly what an in-range prediction depends on, so a
grid that collapses the thin direction under-reports EPISTEMIC predictive uncertainty there even when
every marginal is right. Measured with the frozen posterior_predictive_uq against:
  F5: the exact Gaussian;  TCR narrow: exact quadrature;  K2: the linearized local-Gaussian proxy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_thin_pred", HERE / "thin_ridge.py")
T = importlib.util.module_from_spec(spec)
sys.modules["_thin_pred"] = T
spec.loader.exec_module(T)

from engcore.inference import AdmittedForwardTable, GaussianObservation, ObservationSet, gaussian_grid_posterior  # noqa: E402
from engcore.scientific.ir.problem import ModelReference  # noqa: E402
from engcore.scientific.twins import TwinReference  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402
from engcore.uq import PredictiveObservableSpec, posterior_predictive_uq  # noqa: E402

TWIN = TwinReference(twin_id="review.thin_ridge", version="1")
MODEL = ModelReference("review.thin_ridge.synthetic", "1")


def frozen_epistemic_sd(posterior, predict_values, key="pred:y"):
    obs = ObservationSet((GaussianObservation(condition_id="pred", observable_name="y", value=Quantity(0.0, "dimensionless"),
                                              sigma=Quantity(1.0, "dimensionless"), source_ref="prediction"),), dataset_id="pred")
    table = AdmittedForwardTable(parameter_names=posterior.parameter_names, observation_keys=obs.keys, points=posterior.points,
                                 values=np.asarray(predict_values, float)[:, None], admissible_mask=posterior.admissible_mask,
                                 admission_refs=tuple((("prediction",) if ok else ()) for ok in posterior.admissible_mask),
                                 rejection_reasons=tuple("" if ok else "outside" for ok in posterior.admissible_mask))
    uq = posterior_predictive_uq(posterior, table, PredictiveObservableSpec(key, "dimensionless", None), twin=TWIN, model=MODEL, source_ref="prediction")
    return uq.epistemic_standard_uncertainty.magnitude


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k2", required=True)
    args = ap.parse_args()
    out = {}

    F = T.f5_problem()
    x_star = 10.025
    g = np.asarray([1.0, x_star])
    true_sd = float(math.sqrt(g @ F["cov"] @ g))
    for label, axes in (("declared_bounds_801", [np.linspace(F["lower"][i], F["upper"][i], 801) for i in range(2)]),
                        ("pm_6_marginal_sd_201", [np.linspace(F["mu"][i] - 6 * math.sqrt(F["cov"][i, i]), F["mu"][i] + 6 * math.sqrt(F["cov"][i, i]), 201) for i in range(2)])):
        post = T.frozen_posterior(f"pred.F5.{label}", F["predict"], F["y"], F["sigma"], axes)
        sd = frozen_epistemic_sd(post, post.points @ g)
        out[f"F5_{label}"] = {"prediction": "t1 + 10.025 t2 (y at the centre of the data)", "true_epistemic_sd": true_sd,
                              "frozen_grid_epistemic_sd": sd, "ratio": sd / true_sd}
        print(label, true_sd, sd, sd / true_sd, flush=True)

    reg = json.loads((T.ROUND / "PHASE6_REGRESSION.json").read_text(encoding="utf-8"))
    from engcore.studies import TcrTruth, ols_reference_estimate, synthesize_tcr_observations, tcr_forward_table
    OHM, KELVIN, PER_KELVIN = "ohm", "kelvin", "1/kelvin"
    t_ref = Quantity(293.15, KELVIN)
    truth = TcrTruth(reference_resistance=Quantity(1.2570, OHM), temperature_coefficient=Quantity(0.003930, PER_KELVIN), reference_temperature=t_ref)
    temps = [299.0, 299.5, 300.0, 300.5, 301.0, 301.5]
    obs = synthesize_tcr_observations(truth, temps, sigma=Quantity(0.002, OHM), dataset_id="tcr.cal", seed=20260912)
    by = {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(temps)}
    oracle = ols_reference_estimate(obs, by, t_ref)
    ra = np.linspace(oracle["reference_resistance"] - 6 * oracle["se_reference_resistance"], oracle["reference_resistance"] + 6 * oracle["se_reference_resistance"], 41)
    aa = np.linspace(oracle["temperature_coefficient"] - 6 * oracle["se_temperature_coefficient"], oracle["temperature_coefficient"] + 6 * oracle["se_temperature_coefficient"], 41)
    post = gaussian_grid_posterior(tcr_forward_table(obs, [(float(a), float(b)) for a in ra for b in aa], reference_temperature=t_ref, temperatures_by_condition=by), obs)
    dT = 300.25 - 293.15
    pred = post.points[:, 0] * (1 + post.points[:, 1] * dT)
    sd_grid = frozen_epistemic_sd(post, pred)
    truth_block = reg["tcr_thin_direction_truth"]["TCR_NARROW"]["truth_by_principal_axis_quadrature"]
    m, C = np.asarray(truth_block["mean"]), np.asarray(truth_block["covariance"])
    # exact quadrature of the prediction, same construction as tcr_truth.py
    lam, V = np.linalg.eigh(C)
    gg = np.linspace(-12, 12, 1201)
    A, B = np.meshgrid(gg * math.sqrt(lam[0]), gg * math.sqrt(lam[1]), indexing="ij")
    th = m + np.stack([A.ravel(), B.ravel()], axis=1) @ V.T
    y = np.asarray([o.value.magnitude_in(OHM) for o in obs.observations])
    d = np.asarray([by[o.condition_id].magnitude_in(KELVIN) for o in obs.observations]) - 293.15
    chi = np.sum(((th[:, [0]] * (1 + th[:, [1]] * d[None, :]) - y[None, :]) / 0.002) ** 2, axis=1)
    w = np.exp(-0.5 * (chi - chi.min())); w /= w.sum()
    p = th[:, 0] * (1 + th[:, 1] * dT)
    sd_true = float(math.sqrt(w @ (p - w @ p) ** 2))
    out["TCR_NARROW"] = {"prediction": "R at 300.25 K (centre of the data)", "true_epistemic_sd": sd_true, "frozen_grid_epistemic_sd": sd_grid, "ratio": sd_grid / sd_true}
    print("TCR narrow", sd_true, sd_grid, sd_grid / sd_true, flush=True)

    # K2: grid epistemic sd of each observable (from its own admitted values) vs linearized proxy
    from experiments.kinetics_k2 import k2_config as KC, k2_forward as KF
    from engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
    z = np.load(args.k2, allow_pickle=False)
    keys = tuple(json.loads(str(z["observation_keys"])))
    table = AdmittedForwardTable(parameter_names=KC.PARAMETER_NAMES, observation_keys=keys, points=z["points"], values=z["values"],
                                 admissible_mask=z["admissible_mask"], admission_refs=tuple(tuple(r) for r in json.loads(str(z["admission_refs"]))),
                                 rejection_reasons=tuple(json.loads(str(z["rejection_reasons"]))))
    primary = KF.observation_set_from_truth_means(KF.truth_means(), seed=KC.PRIMARY_SEED, condition_ids=KC.MULTI_CONDITION_IDS)
    post = gaussian_grid_posterior(table, primary)
    local = json.loads((T.ROOT / "benchmarks" / "core_gap_hd_uq" / "DOMAIN_KINETICS.json").read_text(encoding="utf-8"))["MULTI"]
    est = np.asarray(local["calibration"]["estimate"])
    cov = np.asarray(local["local_gaussian"]["posterior"]["covariance"])
    adapter = CSTRInferenceForwardAdapter()

    def f(theta):
        chem = KC.chemistry_from_coordinates(float(theta[0]), float(theta[1]))
        preds = {cid: adapter.evaluate(KC.CONDITION_BY_ID[cid].build(chem), observable_names=KC.OBSERVABLE_NAMES, run_id_prefix="thin-pred") for cid in KC.MULTI_CONDITION_IDS}
        return np.asarray([preds[k.split(":")[0]].value(k.split(":", 1)[1]).magnitude_in(o.value.units) for k, o in zip(keys, primary.observations)])
    h = np.asarray([1e-5 * (KC.LOG_K0_BOUNDS[1] - KC.LOG_K0_BOUNDS[0]), 1e-5 * (KC.E_OVER_R_BOUNDS_K[1] - KC.E_OVER_R_BOUNDS_K[0])])
    J = np.column_stack([(f(est + np.eye(2)[i] * h[i]) - f(est - np.eye(2)[i] * h[i])) / (2 * h[i]) for i in range(2)])
    proxy_sd = np.sqrt(np.einsum("ij,jk,ik->i", J, cov, J))
    rows = {}
    for j, key in enumerate(keys):
        sd_grid = frozen_epistemic_sd(post, table.values[:, j])
        sigma = primary.observations[j].sigma.magnitude
        rows[key] = {"proxy_epistemic_sd": float(proxy_sd[j]), "frozen_grid_epistemic_sd": sd_grid, "ratio": sd_grid / float(proxy_sd[j]),
                     "observation_sigma": sigma}
        print("K2", key, rows[key], flush=True)
    out["KINETICS_K2_MULTI"] = {"proxy": "linearized local Gaussian (HD-UQ review, importance ESS 0.997) -- a PROXY", "observables": rows}
    reg["predictive_impact_of_thin_direction"] = out
    (T.ROUND / "PHASE6_REGRESSION.json").write_bytes((json.dumps(T.jsonable(reg), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print("merged")


if __name__ == "__main__":
    main()
