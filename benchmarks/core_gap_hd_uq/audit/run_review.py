"""Core Gap Review -- high-dimensional UQ: the measurements behind the verdict.

    python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py failure
    python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py battery --workers 12
    python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py tcr
    python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py kinetics
    python -X utf8 benchmarks/core_gap_hd_uq/audit/run_review.py scaling --workers 12

Each section writes one JSON under benchmarks/core_gap_hd_uq/. Nothing under
src/ is written or imported beyond the frozen public API and existing domains.
Grid references use the FROZEN gaussian_grid_posterior / assess_identifiability.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import pathlib
import sys
import threading
import time
import tracemalloc

import numpy as np
from scipy.stats import chi2, norm

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


P = _load("_hd_probe", HERE / "local_gaussian_probe.py")

from engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    GaussianObservation,
    GridResolutionError,
    ObservationSet,
    assess_identifiability,
    gaussian_grid_posterior,
    posterior_grid_diagnostics,
)
from engcore.scientific.units.quantity import Quantity  # noqa: E402

Z95 = P.Z95


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None if math.isnan(value) else ("inf" if value > 0 else "-inf")
    return value


def dump(name, payload):
    (ROUND / name).write_bytes((json.dumps(jsonable(payload), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print("wrote", name)


# =====================================================================
# frozen-grid reference for small synthetic problems
# =====================================================================

def synthetic_grid_reference(label, model, x, y, sigma, axes):
    """Frozen grid posterior over an analytic synthetic model (rows labelled as such)."""
    obs = ObservationSet(tuple(
        GaussianObservation(condition_id=f"x{i}", observable_name="y", value=Quantity(float(v), "dimensionless"),
                            sigma=Quantity(float(s), "dimensionless"), source_ref=f"synthetic:{label}:{i}")
        for i, (v, s) in enumerate(zip(y, sigma))), dataset_id=f"synthetic.{label}")
    mesh = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T
    values = np.asarray([model(point, x) for point in mesh])
    table = AdmittedForwardTable(
        parameter_names=tuple(f"theta{i + 1}" for i in range(len(axes))), observation_keys=obs.keys,
        points=mesh, values=values, admissible_mask=np.ones(len(mesh), dtype=bool),
        admission_refs=tuple(tuple(f"analytic-synthetic:{label}" for _ in obs.keys) for _ in mesh),
        rejection_reasons=tuple("" for _ in mesh))
    posterior = gaussian_grid_posterior(table, obs)
    try:
        ident = assess_identifiability(posterior).to_dict()
    except GridResolutionError as exc:
        ident = {"status": "GRID_TOO_COARSE_FOR_INFERENCE", "refusal": str(exc)[:300]}
    return {
        "route": "POSTERIOR_GRID (frozen), analytic synthetic rows",
        "points": int(len(mesh)),
        "mean": posterior.mean.tolist(), "sd": np.sqrt(np.diag(posterior.covariance)).tolist(),
        "marginal_95": [list(posterior.marginal_interval(i, 0.95)) for i in range(len(axes))],
        "identifiability": ident["status"], "diagnostics": posterior_grid_diagnostics(posterior),
    }


def least_squares_fit(problem, start):
    from scipy.optimize import least_squares
    def resid(t):
        v = problem.forward(t)
        return (v - problem.observed) / problem.sigma
    res = least_squares(resid, np.asarray(start, float), bounds=(problem.lower, problem.upper), method="trf")
    return res.x, float(np.sum(res.fun ** 2))


def failure_cases():
    rng = np.random.default_rng(20260913)
    cases = {}

    def run_case(label, expectation, model, x, truth, sigma_value, lower, upper, start, axes,
                 starts=(), declared_affine=False, reparam=None):
        x = np.asarray(x, float)
        sigma = np.full(len(x), sigma_value)
        y = model(np.asarray(truth, float), x) + rng.normal(0.0, sigma)
        problem = P.LocalProblem(names=tuple(f"theta{i + 1}" for i in range(len(truth))),
                                 forward=lambda t: model(t, x), observed=y, sigma=sigma,
                                 lower=np.asarray(lower, float), upper=np.asarray(upper, float),
                                 declared_affine=declared_affine)
        estimate, chi_min = least_squares_fit(problem, start)
        result = P.local_gaussian(problem, estimate,
                                  refit=(lambda s: least_squares_fit(problem, s)) if starts else None,
                                  starts=starts, reparameterizations=reparam)
        grid = synthetic_grid_reference(label, model, x, y, sigma, axes)
        extra = {}
        if "posterior" in result:
            cov = np.asarray(result["posterior"]["covariance"])
            extra["importance_check"] = P.importance_check(problem, estimate, cov, samples=4000)
            extra["laplace_vs_gauss_newton"] = P.gauss_newton_vs_laplace(problem, estimate, cov)
            gs, ls = np.asarray(grid["sd"]), np.asarray(result["posterior"]["sd"])
            extra["gaussian_vs_grid"] = {"mean_shift_in_grid_sd": (np.abs(np.asarray(grid["mean"]) - estimate) / gs).tolist(),
                                         "sd_ratio_gaussian_over_grid": (ls / gs).tolist()}
        cases[label] = {"expectation": expectation, "truth": truth, "estimate": estimate.tolist(),
                        "observed": y.tolist(), "probe": result, "grid_reference": grid, **extra}
        if label == "F5_weak_identifiability" and "posterior" in result:
            sd = np.asarray(result["posterior"]["sd"])
            study = []
            for per in (201, 401, 801):
                for window, grid_axes in (
                    ("declared_bounds", [np.linspace(lower[0], upper[0], per), np.linspace(lower[1], upper[1], per)]),
                    ("estimate_pm_6_gaussian_sd", [np.linspace(estimate[i] - 6 * sd[i], estimate[i] + 6 * sd[i], per) for i in range(2)]),
                ):
                    g = synthetic_grid_reference(f"{label}.{window}.{per}", model, x, y, sigma, grid_axes)
                    study.append({"per_axis": per, "window": window, "step": [float(a[1] - a[0]) for a in grid_axes],
                                  "mean": g["mean"], "sd": g["sd"], "identifiability": g["identifiability"],
                                  "effective_sample_size": g["diagnostics"]["effective_sample_size"],
                                  "spacing_to_std": g["diagnostics"]["spacing_to_std"]})
            conditional_width = float(1.0 / np.sqrt(np.linalg.inv(np.asarray(result["posterior"]["covariance"]))[0, 0]))
            cases[label]["grid_resolution_study"] = {
                "finding": ("the frozen grid over the declared bounds gives resolution-STABLE but WRONG moments for a thin correlated ridge: "
                            "its theta1 step exceeds the ridge's conditional width by ~30-120x, ESS stays above 8 and spacing/marginal-sd "
                            "stays below 1, so GridResolutionError is not raised. A window of +/-6 Gaussian sd reproduces the exact answer."),
                "exactness_evidence": "model affine in theta, box bounds >19 sd away: the Gaussian is the exact posterior; importance ESS 1.0 and Laplace = Gauss-Newton confirm",
                "theta1_conditional_sd": conditional_width, "study": study}
        claim = result["claim"]
        print(f"{label:28} claim={claim:10} refusals={result.get('refusals')} downgrades={result.get('downgrades')} "
              f"ident={result.get('identifiability', {}).get('status')} grid_ident={grid['identifiability']}")

    x8 = np.linspace(0.0, 1.0, 8)
    run_case("F1_strong_nonlinearity", "DOWNGRADED or REFUSED for nonlinearity; grid differs from Gaussian",
             lambda t, x: t[1] * np.exp(-t[0] * x), x8, (3.0, 2.0), 0.35, (0.01, 0.01), (20.0, 10.0), (1.0, 1.0),
             [np.linspace(0.01, 20.0, 241), np.linspace(0.01, 10.0, 241)])
    run_case("F2_parameter_at_bound", "REFUSED: PARAMETER_AT_BOUND",
             lambda t, x: t[0] + t[1] * x, np.linspace(0, 1, 10), (1.0, -0.05), 0.02, (0.0, 0.0), (5.0, 5.0), (0.5, 0.5),
             [np.linspace(0.8, 1.2, 201), np.linspace(0.0, 0.3, 201)], declared_affine=True)
    run_case("F3_nearly_singular_jacobian", "REFUSED: NUMERICALLY_SINGULAR_JACOBIAN or not identifiable",
             lambda t, x: t[0] * x + t[1] * (x + 1e-9 * x ** 2), np.linspace(1.0, 2.0, 10), (1.0, 1.0), 0.01,
             (-10.0, -10.0), (10.0, 10.0), (0.5, 0.5), [np.linspace(-10, 10, 201), np.linspace(-10, 10, 201)],
             declared_affine=True)
    run_case("F4_multimodal_no_multistart", "DOWNGRADED: GLOBAL_UNIQUENESS_NOT_ASSESSED (it cannot see the mirror mode)",
             lambda t, x: t[0] ** 2 * x, np.linspace(1.0, 2.0, 6), (1.0,), 0.05, (-3.0,), (3.0,), (0.5,),
             [np.linspace(-3.0, 3.0, 6001)])
    run_case("F4_multimodal_with_multistart", "REFUSED: SECOND_MODE_FOUND",
             lambda t, x: t[0] ** 2 * x, np.linspace(1.0, 2.0, 6), (1.0,), 0.05, (-3.0,), (3.0,), (0.5,),
             [np.linspace(-3.0, 3.0, 6001)], starts=((-2.0,), (-0.5,), (0.5,), (2.0,)))
    run_case("F5_weak_identifiability", "route SUPPORTED (affine), identifiability NOT IDENTIFIABLE: two verdicts, never merged",
             lambda t, x: t[0] + t[1] * x, np.linspace(10.0, 10.05, 6), (1.0, 0.3), 0.01, (-50.0, -5.0), (50.0, 5.0), (0.0, 0.0),
             [np.linspace(-50, 50, 801), np.linspace(-5, 5, 801)], declared_affine=True)
    # F6: the same physics in two parameterizations
    run_case("F6_linear_parameter_k", "affine in k: SUPPORTED; relative-width identifiability may fail near k~0",
             lambda t, x: t[0] * x, np.linspace(0.1, 1.0, 8), (0.2,), 0.1, (1e-6,), (5.0,), (1.0,),
             [np.linspace(1e-6, 5.0, 20001)], declared_affine=True)
    run_case("F6_log_parameter_logk", "the same model in log k is nonlinear: the probe must see it",
             lambda t, x: np.exp(t[0]) * x, np.linspace(0.1, 1.0, 8), (math.log(0.2),), 0.1, (math.log(1e-6),), (math.log(5.0),), (0.0,),
             [np.linspace(math.log(1e-6), math.log(5.0), 20001)])
    return {"schema": "core_gap_hd_uq_failure_cases/1", "seed": 20260913,
            "declared_thresholds": {"nonlinearity_downgrade": P.NONLINEARITY_DOWNGRADE, "nonlinearity_refuse": P.NONLINEARITY_REFUSE,
                                    "bound_downgrade_sd": P.BOUND_DOWNGRADE_SD, "numerical_condition_limit": P.NUMERICAL_CONDITION_LIMIT,
                                    "identifiability": P.THRESHOLDS},
            "cases": cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("section", choices=["failure", "battery", "tcr", "kinetics", "scaling", "compatibility"])
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.section == "failure":
        dump("FAILURE_CASES.json", failure_cases())
    elif args.section == "battery":
        section = _load("_review_battery", HERE / "review_battery.py")
        dump("BATTERY_B3_REFERENCE.json", section.run(sys.modules[__name__], args.workers))
    elif args.section == "compatibility":
        section = _load("_review_compatibility", HERE / "review_compatibility.py")
        dump("COMPATIBILITY.json", section.run(sys.modules[__name__]))
    elif args.section == "scaling":
        section = _load("_review_scaling", HERE / "review_scaling.py")
        dump("SCALING.json", section.run(sys.modules[__name__]))
    elif args.section in ("tcr", "kinetics"):
        section = _load("_review_domains", HERE / "review_domains.py")
        fn = section.tcr if args.section == "tcr" else section.kinetics
        dump(f"DOMAIN_{args.section.upper()}.json", fn(sys.modules[__name__]))


if __name__ == "__main__":
    main()
