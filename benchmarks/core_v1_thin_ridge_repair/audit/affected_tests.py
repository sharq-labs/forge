"""Score every pre-existing test grid the repair now refuses, against its exact posterior.

    python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/affected_tests.py

A refusal is only a correct repair if the refused grid is materially wrong by the
declared materiality (THRESHOLD_PROTOCOL.json). For each grid named by a test that
went red, this rebuilds the SAME grid the test builds, computes its moments, the
private aliasing number, and the exact posterior moments of the closed-form TCR law
by dense quadrature along the local principal axes. It also scores the grid size
that each test is moved to, which must be classified and right.

Writes benchmarks/core_v1_thin_ridge_repair/AFFECTED_TESTS.json.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from engcore.inference import gaussian_grid_posterior  # noqa: E402
from engcore.inference.calibration import (  # noqa: E402
    _ALIASING_NUMBER_MINIMUM,
    _fitted_lattice_covariance,
    _grid_resolution_refusal,
    _minimum_aliasing_number,
    _tensor_lattice_steps,
)
from engcore.scientific.units.quantity import Quantity  # noqa: E402
from engcore.studies import TcrTruth, ols_reference_estimate, synthesize_tcr_observations, tcr_forward_table  # noqa: E402

T_REF = Quantity(293.15, "kelvin")
SIGMA = 0.002
TRUTH = TcrTruth(reference_resistance=Quantity(1.2570, "ohm"), temperature_coefficient=Quantity(0.003930, "1/kelvin"), reference_temperature=T_REF)
NARROW = [299.0, 299.5, 300.0, 300.5, 301.0, 301.5]
CAL_T = [300.0, 320.0, 340.0, 360.0, 380.0, 400.0]
HELD_T = [310.0, 350.0, 420.0]


def observations(temps, seed, dataset_id, subset_of=None):
    if subset_of is None:
        return synthesize_tcr_observations(TRUTH, temps, sigma=Quantity(SIGMA, "ohm"), dataset_id=dataset_id, seed=seed), temps
    source = synthesize_tcr_observations(TRUTH, subset_of, sigma=Quantity(SIGMA, "ohm"), dataset_id=f"cov.source.{seed}", seed=seed)
    ids = tuple(f"T{i}" for i in range(len(temps)))
    return source.subset(ids, dataset_id=dataset_id), subset_of


def score(label, temps, seed, per_axis, span=6.0, subset_of=None):
    obs, all_temps = observations(temps, seed, label, subset_of)
    by = {f"T{i}": Quantity(t, "kelvin") for i, t in enumerate(all_temps)}
    oracle = ols_reference_estimate(obs, by, T_REF)
    ra = np.linspace(oracle["reference_resistance"] - span * oracle["se_reference_resistance"], oracle["reference_resistance"] + span * oracle["se_reference_resistance"], per_axis)
    aa = np.linspace(oracle["temperature_coefficient"] - span * oracle["se_temperature_coefficient"], oracle["temperature_coefficient"] + span * oracle["se_temperature_coefficient"], per_axis)
    post = gaussian_grid_posterior(tcr_forward_table(obs, [(float(a), float(b)) for a in ra for b in aa], reference_temperature=T_REF, temperatures_by_condition=by), obs)

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
    mu = w @ th
    cov = (th - mu).T @ ((th - mu) * w[:, None])

    sd = np.sqrt(np.diag(cov))
    ratio = np.sqrt(np.diag(post.covariance)) / sd
    tl, tv = np.linalg.eigh(cov)
    u = tv[:, 0]
    thin = math.sqrt(max(float(u @ post.covariance @ u), 0.0)) / math.sqrt(tl[0])
    thin_mean = abs(float(u @ (post.mean - mu))) / math.sqrt(tl[0])
    mean_err = float(np.max(np.abs(post.mean - mu) / sd))
    material = bool(mean_err > 0.1 or ratio.min() < 0.9 or ratio.max() > 1.1 or not 0.9 <= thin <= 1.1 or thin_mean > 0.1)

    steps = _tensor_lattice_steps(post.points)
    S, fit = _fitted_lattice_covariance(post, steps)
    aliasing = None if S is None else _minimum_aliasing_number(S, 1e6)
    w_grid = np.asarray(post.weights)
    return {
        "label": label, "temperatures": list(temps), "seed": seed, "per_axis": per_axis, "sigma_span": span,
        "grid_correlation": float(post.covariance[0, 1] / math.sqrt(post.covariance[0, 0] * post.covariance[1, 1])),
        "exact_correlation": float(cov[0, 1] / (sd[0] * sd[1])),
        "effective_sample_size": float(1.0 / np.sum(w_grid ** 2)),
        "aliasing_number": None if aliasing is None else float(aliasing), "fit": fit,
        "max_marginal_mean_error_sd": mean_err, "marginal_sd_ratio": ratio.tolist(),
        "thin_direction_sd_ratio": thin, "thin_direction_mean_error_sd": thin_mean,
        "materially_wrong": material,
        "refused_by_repair": _grid_resolution_refusal(post) is not None,
    }


def main():
    cases = [
        # tests/inference/test_tcr_calibration.py posterior_over(NARROW_SPAN): 41x41, seed 20260912
        ("tcr_calibration.narrow.41", NARROW, 20260912, 41, None),
        ("tcr_calibration.narrow.81", NARROW, 20260912, 81, None),
        ("tcr_calibration.narrow.161", NARROW, 20260912, 161, None),
        # tests/inference/test_tcr_heldout_uq.py case C and B-vs-C: 21x21, seed 5
        ("tcr_heldout_uq.case_c.21", NARROW, 5, 21, None),
        ("tcr_heldout_uq.case_c.81", NARROW, 5, 81, None),
        ("tcr_heldout_uq.case_c.161", NARROW, 5, 161, None),
    ]
    for seed in (11, 12, 13):
        # tests/inference/test_reproducibility_and_evidence.py coverage study, grid_points_per_axis=11;
        # calibration half of a 9-temperature synthesis, as run_coverage_study builds it
        cases.append((f"coverage_study.seed{seed}.11", CAL_T, seed, 11, CAL_T + HELD_T))
        cases.append((f"coverage_study.seed{seed}.15", CAL_T, seed, 15, CAL_T + HELD_T))
        cases.append((f"coverage_study.seed{seed}.21", CAL_T, seed, 21, CAL_T + HELD_T))
    out = {"schema": "thin_ridge_affected_tests/1", "threshold": _ALIASING_NUMBER_MINIMUM,
           "materiality": "marginal mean error > 0.1 sd, marginal sd ratio outside [0.9, 1.1], thin-direction sd ratio outside [0.9, 1.1], or thin-direction mean error > 0.1 sd",
           "cases": []}
    for label, temps, seed, n, subset_of in cases:
        r = score(label, temps, seed, n, subset_of=subset_of)
        out["cases"].append(r)
        print(f"{label:34s} A={r['aliasing_number']!s:>10.8} ess={r['effective_sample_size']:8.2f} rho={r['grid_correlation']:+.5f} "
              f"mean_err={r['max_marginal_mean_error_sd']:.3f} sd={['%.3f' % v for v in r['marginal_sd_ratio']]} thin={r['thin_direction_sd_ratio']:.3f} "
              f"material={r['materially_wrong']} refused={r['refused_by_repair']}", flush=True)
    path = ROOT / "benchmarks" / "core_v1_thin_ridge_repair" / "AFFECTED_TESTS.json"
    path.write_bytes((json.dumps(out, indent=1) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
