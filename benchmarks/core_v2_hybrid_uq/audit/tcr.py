"""Part 11: TCR through the Core V2 route -- wide (identifiable) and narrow (weak) designs.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/tcr.py

Designs, truth, sigma and seed of tests/inference/test_tcr_calibration.py. Three answers per design:

* the V2 local route (``route_uncertainty`` with the calibration, default multistart, no grid);
* the repaired V1 grid, at a resolution the repaired V1 checks accept (41 nodes wide, 81 narrow);
* the exact posterior of the closed-form law by dense quadrature along the local principal axes.

The router is also given each design's 41-node grid. V1 accepts the wide one and refuses the narrow one, and the
router must follow V1.

Declared agreement tolerance (supported, locally Gaussian cases): |mean shift| <= 0.05 exact sd, sd ratio in
[0.95, 1.05], identifiability status equal to the resolved grid's.

Writes benchmarks/core_v2_hybrid_uq/TCR.json.
"""

from __future__ import annotations

import math
import time

import numpy as np

from common import dump

from engcore.hybrid_uq import MultistartPolicy, RouteDecision, assess_routed_identifiability, route_uncertainty
from engcore.inference import CalibrationSpec, NoiseModel, calibrate, gaussian_grid_posterior
from engcore.scientific.units.quantity import Quantity
from engcore.studies import (
    TcrTruth, build_tcr_parameter_set, ols_reference_estimate, synthesize_tcr_observations, tcr_forward_evaluator, tcr_forward_table,
)

TOLERANCE = {"mean_shift_exact_sd": 0.05, "sd_ratio": (0.95, 1.05)}
T_REF = Quantity(293.15, "kelvin")
SIGMA = 0.002
TRUTH = TcrTruth(reference_resistance=Quantity(1.2570, "ohm"), temperature_coefficient=Quantity(0.003930, "1/kelvin"), reference_temperature=T_REF)
DESIGNS = {"WIDE": ([300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0], 41),
           "NARROW": ([299.0, 299.5, 300.0, 300.5, 301.0, 301.5], 81)}


def exact(obs, by, oracle):
    y = np.asarray([o.value.magnitude_in("ohm") for o in obs.observations])
    dT = np.asarray([by[o.condition_id].magnitude_in("kelvin") for o in obs.observations]) - 293.15
    mu0 = np.asarray([oracle["reference_resistance"], oracle["temperature_coefficient"]])
    J = np.column_stack([1 + mu0[1] * dT, mu0[0] * dT]) / SIGMA
    lam, V = np.linalg.eigh(np.linalg.inv(J.T @ J))
    g = np.linspace(-12, 12, 1201)
    A, B = np.meshgrid(g * math.sqrt(lam[0]), g * math.sqrt(lam[1]), indexing="ij")
    th = mu0 + np.stack([A.ravel(), B.ravel()], axis=1) @ V.T
    chi = np.sum(((th[:, [0]] * (1 + th[:, [1]] * dT[None, :]) - y[None, :]) / SIGMA) ** 2, axis=1)
    w = np.exp(-0.5 * (chi - chi.min()))
    w /= w.sum()
    m = w @ th
    return m, (th - m).T @ ((th - m) * w[:, None])


def grid_for(obs, by, oracle, n):
    ra = np.linspace(oracle["reference_resistance"] - 6 * oracle["se_reference_resistance"], oracle["reference_resistance"] + 6 * oracle["se_reference_resistance"], n)
    aa = np.linspace(oracle["temperature_coefficient"] - 6 * oracle["se_temperature_coefficient"], oracle["temperature_coefficient"] + 6 * oracle["se_temperature_coefficient"], n)
    return gaussian_grid_posterior(tcr_forward_table(obs, [(float(a), float(b)) for a in ra for b in aa], reference_temperature=T_REF,
                                                     temperatures_by_condition=by), obs)


def main():
    out = {"schema": "core_v2_hybrid_uq_tcr/1", "declared_tolerance": TOLERANCE, "designs": {}}
    for name, (temps, resolved_nodes) in DESIGNS.items():
        obs = synthesize_tcr_observations(TRUTH, temps, sigma=Quantity(SIGMA, "ohm"), dataset_id=f"tcr.{name}", seed=20260912)
        by = {f"T{i}": Quantity(t, "kelvin") for i, t in enumerate(temps)}
        calls = {"n": 0}
        evaluator = tcr_forward_evaluator(obs, reference_temperature=T_REF, temperatures_by_condition=by)

        def forward(theta, ev=evaluator, c=calls):
            c["n"] += 1
            return ev(theta)

        spec = CalibrationSpec(parameters=build_tcr_parameter_set(), fixed={"reference_temperature": T_REF},
                               initial_point={"reference_resistance": Quantity(0.80, "ohm"), "temperature_coefficient": Quantity(0.0010, "1/kelvin")},
                               noise_model=NoiseModel())
        fit = calibrate(spec, obs, forward, heldout_dataset_id=f"tcr.{name}.heldout", seed=20260912)
        oracle = ols_reference_estimate(obs, by, T_REF)
        t0, c0 = time.perf_counter(), calls["n"]
        local = route_uncertainty(calibration=fit, observations=obs, forward=forward, multistart=MultistartPolicy())
        local_seconds, local_calls = time.perf_counter() - t0, calls["n"] - c0
        t0 = time.perf_counter()
        resolved = grid_for(obs, by, oracle, resolved_nodes)
        grid_seconds = time.perf_counter() - t0
        # CORE-005 (scientific core audit 2026-09-16): a supplied grid is routed only with the evidence it is checked
        # against. R-06 (re-audit 2026-09-16): a grid narrower than the declared bounds also needs a uniqueness basis,
        # which only a search over the calibration can give it, so the calibration and the canonical policy go in too.
        grid_route = route_uncertainty(grid=resolved, calibration=fit, observations=obs, forward=forward,
                                       multistart=MultistartPolicy())
        coarse = grid_for(obs, by, oracle, 41)
        with_coarse = route_uncertainty(grid=coarse, calibration=fit, observations=obs, forward=forward, multistart=MultistartPolicy())
        m, c = exact(obs, by, oracle)
        sd = np.sqrt(np.diag(c))
        lm, ls = np.asarray(local.mean), np.sqrt(np.diag(local.covariance))
        gm, gs = np.asarray(grid_route.mean), np.sqrt(np.diag(grid_route.covariance))
        li, gi = local.identifiability, grid_route.identifiability
        row = {
            "temperatures_k": temps, "calibration_status": fit.status.value,
            "v2_local": {"decision": local.decision.value, "claim": local.claim.value, "reasons": [r.value for r in local.local_posterior.reasons],
                         "uniqueness": local.local_posterior.diagnostics.uniqueness, "nonlinearity_index": local.local_posterior.diagnostics.nonlinearity_index,
                         "mean": lm.tolist(), "sd": ls.tolist(), "correlation": float(local.local_posterior.correlation[0, 1]),
                         "identifiability": li.status.value, "forward_evaluations": local_calls, "wall_seconds": local_seconds},
            "v1_resolved_grid": {"nodes_per_axis": resolved_nodes, "decision": grid_route.decision.value, "mean": gm.tolist(), "sd": gs.tolist(),
                                 "identifiability": gi.status.value, "forward_evaluations": resolved_nodes ** 2, "wall_seconds": grid_seconds},
            "exact_quadrature": {"mean": m.tolist(), "sd": sd.tolist(), "correlation": float(c[0, 1] / (sd[0] * sd[1]))},
            "router_given_the_41_node_grid": {"decision": with_coarse.decision.value, "considered": with_coarse.considered},
            "agreement": {
                "v2_mean_shift_exact_sd": (np.abs(lm - m) / sd).tolist(), "v2_sd_ratio_exact": (ls / sd).tolist(),
                "grid_mean_shift_exact_sd": (np.abs(gm - m) / sd).tolist(), "grid_sd_ratio_exact": (gs / sd).tolist(),
                "v2_sd_ratio_grid": (ls / gs).tolist(), "identifiability_equal": li.status is gi.status,
            },
        }
        a = row["agreement"]
        a["within_declared_tolerance"] = bool(max(a["v2_mean_shift_exact_sd"]) <= TOLERANCE["mean_shift_exact_sd"]
                                              and TOLERANCE["sd_ratio"][0] <= min(a["v2_sd_ratio_exact"]) and max(a["v2_sd_ratio_exact"]) <= TOLERANCE["sd_ratio"][1]
                                              and a["identifiability_equal"])
        out["designs"][name] = row
        print(name, local.decision.value, local.claim.value, li.status.value, gi.status.value, "coarse->", with_coarse.decision.value,
              "shift", np.round(a["v2_mean_shift_exact_sd"], 4), "ratio", np.round(a["v2_sd_ratio_exact"], 4), "ok", a["within_declared_tolerance"], flush=True)
    dump("TCR.json", out)


if __name__ == "__main__":
    main()
