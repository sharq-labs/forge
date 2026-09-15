"""Battery Flagship B3: existing SOC-dependent OCV representations on rich measured data.

    python -X utf8 benchmarks/battery_flagship_b3/audit/run_b3.py --controls   # synthetic controls only
    python -X utf8 benchmarks/battery_flagship_b3/audit/run_b3.py              # the measured round

Implements ``PREREGISTRATION.json`` and nothing else. Reads the frozen raw
evidence through ``b3_evidence.py``; writes, under benchmarks/battery_flagship_b3/:

    CONTROLS.json     synthetic controls (run before the measured round)
    RESULTS.json      every model: calibration, gate, identifiability, held-out,
                      regions, parameterization sensitivity, CV, ladder
    COMPARISON.json   complexity study, best honest model, B1/B2/B3 table, verdict
    SECONDARY.json    route cross-check, hysteresis, cross-cell, cutoff regression,
                      empirical adequacy, next-physics ranking

Two uncertainty routes, never confused:

``CORE_GRID``
    the frozen grid posterior, identifiability, predictive UQ and adequacy over
    an AdmittedForwardTable of production-solver predictions.
``DOMAIN_LINEAR_GAUSSIAN``
    the exact Gaussian posterior of a model that is affine in its parameters,
    with the frozen identifiability thresholds applied to it. Used where no
    feasible grid exists, and allowed to carry a claim only if it reproduces the
    Core grid on every model both can run.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import itertools
import json
import math
import pathlib
import sys
import time

import numpy as np
from scipy.stats import chi2, norm

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROUND = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


E = _load("_b3_evidence_run", HERE / "b3_evidence.py")
PREREG = json.loads((ROUND / "PREREGISTRATION.json").read_text(encoding="utf-8"))

from engcore.adequacy import assess_predictive_observation  # noqa: E402
from engcore.domains.battery import calibration as bc  # noqa: E402
from engcore.domains.battery import context as ctx  # noqa: E402
from engcore.domains.battery.cell import CellSpecification  # noqa: E402
from engcore.domains.battery.empirical import (  # noqa: E402
    ConditioningDirection,
    MeasuredOcvPoint,
    assess_ocv_empirical_adequacy,
)
from engcore.inference import (  # noqa: E402
    AdmittedForwardTable,
    CalibrationSpec,
    GaussianObservation,
    GridResolutionError,
    NoiseModel,
    ObservationSet,
    ObservationSplit,
    PosteriorGrid,
    assess_identifiability,
    calibrate,
    gaussian_grid_posterior,
    observation_content_digest,
    posterior_grid_diagnostics,
)
from engcore.scientific.twins import TwinReference  # noqa: E402
from engcore.scientific.units.quantity import Quantity as Q  # noqa: E402
from engcore.uq import PredictiveObservableSpec, posterior_predictive_uq  # noqa: E402

VOLT = ctx.VOLTAGE_UNIT
ALPHA = 0.01
CREDIBLE = 0.95
Z95 = float(norm.ppf(0.975))
SEED = PREREG["phase11_models"]["calibration"]["seed"]
BOUNDS = tuple(PREREG["phase11_models"]["calibration"]["bounds_v"])
MAX_EVALUATIONS = PREREG["phase11_models"]["calibration"]["max_evaluations"]
FD_STEP_V = 0.01
TWIN = TwinReference(twin_id="battery.lfp.a123_18650m1a.JAHN2024_A123_01", version="1")
_DECL = PREREG["fixed_declarations_for_the_battery_adapter"]
FIXED = bc.FixedCellDeclaration(
    cell_id=_DECL["cell_id"],
    nominal_capacity=Q(_DECL["nominal_capacity_ah"], ctx.CAPACITY_UNIT),
    internal_resistance=Q(_DECL["internal_resistance_ohm"], ctx.RESISTANCE_UNIT),
    coulombic_efficiency=Q(_DECL["coulombic_efficiency"], ctx.DIMENSIONLESS),
    chemistry=ctx.LITHIUM_ION,
)
CELL_TEMPERATURE = Q(_DECL["cell_temperature_k"], ctx.TEMPERATURE_UNIT)
CONDITIONING_CURRENT = Q(_DECL["conditioning_current_a"], ctx.CURRENT_UNIT)
MODELS = {m["id"]: m for m in PREREG["phase11_models"]["models"]}
SCORED_MODELS = [m for m in MODELS if MODELS[m]["route"] != "GATE_DEMONSTRATION_ONLY"]
REGION_NAMES = [name for name, _, _ in E.REGIONS]
DATASET_ID = "JAHN2024.A123_01.discharge"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None if math.isnan(value) else ("inf" if value > 0 else "-inf")
    return value


def dump(name: str, payload: dict) -> None:
    (ROUND / name).write_bytes((json.dumps(jsonable(payload), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def parameterization(model_id: str):
    model = MODELS[model_id]
    if model["form"].startswith("Tabulated"):
        return bc.TabulatedKnotParameterization(tuple(model["positions"]), source=f"B3-{model_id}")
    return bc.PolynomialNodeParameterization(tuple(model["positions"]), source=f"B3-{model_id}")


def rested_condition(observation_id: str, z: float) -> bc.RestedOcvCondition:
    return bc.RestedOcvCondition(
        condition_id=observation_id,
        target_state_of_charge=Q(z, ctx.DIMENSIONLESS),
        conditioning_current=CONDITIONING_CURRENT,
        cell_temperature=CELL_TEMPERATURE,
    )


# =====================================================================
# data: observations, sigmas, split
# =====================================================================

class Data:
    """One observation set at one relaxation allowance, split as preregistered."""

    def __init__(self, relaxation_allowance_v: float = E.PRIMARY_RELAXATION_ALLOWANCE_V,
                 observed_override: dict[str, float] | None = None, label: str = "measured"):
        self.label = label
        self.points = E.discharge_points()
        self.budget = E.uncertainty_budget(self.points, relaxation_allowance_v)
        self.allowance_v = relaxation_allowance_v
        self.by_id = {p["observation_id"]: p for p in self.points}
        self.z = {p["observation_id"]: p["state_of_charge"] for p in self.points}
        self.region = {p["observation_id"]: p["region"] for p in self.points}
        self.values = {p["observation_id"]: p["voltage_v"] for p in self.points}
        if observed_override is not None:
            self.values = dict(observed_override)
        observations = tuple(
            GaussianObservation(
                condition_id=p["observation_id"],
                observable_name=bc.OCV_OBSERVABLE,
                value=Q(self.values[p["observation_id"]], VOLT),
                sigma=Q(self.budget[p["observation_id"]]["combined_standard_uncertainty_v"], VOLT),
                source_ref=(f"zenodo:{E.DATASET_DOI}:{E.INCR_OCV}:row{p['row']:03d}" if observed_override is None
                            else f"synthetic:{label}:row{p['row']:03d}"),
            )
            for p in self.points
        )
        self.source = ObservationSet(observations, dataset_id=f"{DATASET_ID}.{label}")
        self.conditions = {p["observation_id"]: rested_condition(p["observation_id"], p["state_of_charge"]) for p in self.points}
        held = tuple(p["observation_id"] for p in self.points if p["partition"] == "held_out")
        self.split = ObservationSplit.partition(
            source=self.source, held_out_condition_ids=held, twin=TWIN,
            calibration_dataset_id=f"{DATASET_ID}.{label}.calibration",
            heldout_dataset_id=f"{DATASET_ID}.{label}.held_out",
        )

    def sigma(self, observation_id: str) -> float:
        return self.budget[observation_id]["combined_standard_uncertainty_v"]

    def leakage_proof(self) -> dict:
        cal = self.split.calibration.observations
        held = self.split.held_out.observations
        cal_ids, held_ids = {o.condition_id for o in cal}, {o.condition_id for o in held}
        cal_d, held_d = {observation_content_digest(o) for o in cal}, {observation_content_digest(o) for o in held}
        slope_sources = {oid: b["slope_taken_from"] for oid, b in self.budget.items()}
        held_in_sigma = sorted({s for used in slope_sources.values() for s in used} & held_ids)
        return {
            "calibration_n": len(cal), "held_out_n": len(held),
            "intersection_by_identity": sorted(cal_ids & held_ids),
            "intersection_by_content_digest": sorted(cal_d & held_d),
            "held_out_observations_used_in_any_sigma": held_in_sigma,
            "disjoint": not (cal_ids & held_ids) and not (cal_d & held_d) and not held_in_sigma,
        }


# =====================================================================
# forward map through the production adapter
# =====================================================================

def forward(param, voltages, observations: ObservationSet, data: Data) -> np.ndarray:
    return np.asarray([
        bc.curve_ocv_prediction(FIXED, data.conditions[o.condition_id], parameterization=param,
                                voltages=tuple(float(v) for v in voltages)).value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)
        for o in observations.observations
    ])


def initial_point(k: int) -> np.ndarray:
    return np.linspace(3.0, 3.4, k)


def affine_design(param, observations: ObservationSet, data: Data):
    """f(theta) = f0 + J (theta - base), exact for both forms (affine in voltages)."""
    k = len(param.names)
    base = initial_point(k)
    f0 = forward(param, base, observations, data)
    columns = []
    for index in range(k):
        bumped = base.copy()
        bumped[index] += FD_STEP_V
        columns.append((forward(param, bumped, observations, data) - f0) / FD_STEP_V)
    return base, f0, np.column_stack(columns)


def weighted(observations: ObservationSet):
    y = np.asarray([o.value.magnitude_in(VOLT) for o in observations.observations])
    s = np.asarray([o.sigma.magnitude_in(VOLT) for o in observations.observations])
    return y, s


def wls(param, observations: ObservationSet, data: Data) -> dict:
    base, f0, J = affine_design(param, observations, data)
    y, s = weighted(observations)
    A = J / s[:, None]
    singular = np.linalg.svd(A, compute_uv=False)
    rank = int(np.linalg.matrix_rank(A))
    k = J.shape[1]
    out = {"base": base, "f0": f0, "J": J, "rank": rank, "p": k, "n": len(y),
           "singular_values": singular, "jacobian_condition": float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf")}
    if rank == k:
        cov = np.linalg.inv(A.T @ A)
        theta = base + cov @ A.T @ ((y - f0) / s)
        out.update({"theta": theta, "cov": cov})
    return out


# =====================================================================
# calibration through the frozen Core
# =====================================================================

def core_calibrate(param, observations: ObservationSet, data: Data, heldout_dataset_id: str) -> dict:
    k = len(param.names)
    spec = CalibrationSpec(
        parameters=bc.build_curve_parameter_set(param, lower=Q(BOUNDS[0], VOLT), upper=Q(BOUNDS[1], VOLT)),
        fixed={
            ctx.NOMINAL_CAPACITY: FIXED.nominal_capacity,
            ctx.INTERNAL_RESISTANCE: FIXED.internal_resistance,
            ctx.COULOMBIC_EFFICIENCY: FIXED.coulombic_efficiency,
            ctx.CELL_TEMPERATURE: CELL_TEMPERATURE,
            ctx.DISCHARGE_CURRENT: CONDITIONING_CURRENT,
        },
        initial_point={n: Q(float(v), VOLT) for n, v in zip(param.names, initial_point(k))},
        noise_model=NoiseModel(),
    )
    counter: dict[str, int] = {}
    fit = calibrate(
        spec, observations,
        bc.curve_forward_evaluator(observations, fixed=FIXED, conditions=data.conditions, parameterization=param, counter=counter),
        heldout_dataset_id=heldout_dataset_id, max_evaluations=MAX_EVALUATIONS, seed=SEED,
    )
    estimates = np.asarray([e.value.magnitude_in(VOLT) for e in fit.estimates]) if fit.estimates else None
    return {
        "status": fit.status.value, "termination_reason": fit.termination_reason,
        "optimizer_evaluations": fit.evaluation_count, "admitted_forward_predictions": counter.get("n", 0),
        "objective_chi_square": fit.objective_value, "bounds_v": list(BOUNDS),
        "initial_point_v": initial_point(k).tolist(), "optimizer": "scipy.optimize.least_squares trf via engcore.inference.calibrate",
        "estimates_v": dict(zip(param.names, estimates.tolist())) if estimates is not None else {},
        "wall_seconds_informational": round(fit.provenance.wall_seconds, 3),
        "_estimates": estimates, "_residuals": list(fit.residuals) if fit.residuals else [],
    }


# =====================================================================
# identifiability on an exact Gaussian (frozen thresholds, same rule)
# =====================================================================

def gaussian_identifiability(mean: np.ndarray, cov: np.ndarray, names) -> dict:
    thresholds = {"correlation": 0.95, "condition_number": 1.0e6, "relative_width": 1.0}
    sd = np.sqrt(np.maximum(np.diag(cov), 0.0))
    denom = np.outer(sd, sd)
    corr = np.divide(cov, denom, out=np.zeros_like(cov), where=denom > 0)
    eig = np.linalg.eigvalsh(cov)
    condition = float(eig.max() / eig.min()) if eig.min() > 0 else float("inf")
    off = [abs(corr[i, j]) for i in range(len(sd)) for j in range(len(sd)) if i != j]
    max_corr = max(off) if off else 0.0
    widths = [(2 * Z95 * sd[i]) / abs(mean[i]) if abs(mean[i]) > 0 else float("inf") for i in range(len(sd))]
    reasons = []
    if not math.isfinite(condition) or condition > thresholds["condition_number"]:
        reasons.append("condition")
    if max_corr > thresholds["correlation"]:
        reasons.append("correlation")
    over = [names[i] for i, w in enumerate(widths) if not math.isfinite(w) or w > thresholds["relative_width"]]
    if over:
        status = "PARAMETERS_NOT_IDENTIFIABLE"
    elif not reasons:
        status = "PARAMETERS_IDENTIFIABLE"
    elif len(reasons) >= 2:
        status = "PARAMETERS_NOT_IDENTIFIABLE"
    else:
        status = "PARAMETERS_WEAKLY_IDENTIFIABLE"
    return {"status": status, "condition_number": condition, "max_abs_correlation": max_corr,
            "relative_widths": widths, "over_wide": over, "reasons": reasons, "thresholds": thresholds,
            "route": "DOMAIN_LINEAR_GAUSSIAN (frozen thresholds on the exact covariance; not Core-certified)"}


def reparameterize(model_id: str, param):
    """Linear map from the primary voltages to the secondary parameterization, and its names."""
    k = len(param.names)
    if isinstance(param, bc.PolynomialNodeParameterization):
        T = np.linalg.inv(np.vander(np.asarray(param.nodes, dtype=float), increasing=True))
        return "monomial_coefficients_about_0", T, [f"c{i}" for i in range(k)]
    T = np.eye(k) - np.eye(k, k=-1)
    return "anchor_plus_increments", T, ["v0"] + [f"d{i}" for i in range(1, k)]


# =====================================================================
# Core grid route, with optional worker processes
# =====================================================================

_WORKER: dict = {}


def _worker_init(allowance_v, override, label):
    _WORKER["data"] = Data(allowance_v, override, label)


def _worker_chunk(task):
    model_id, partition, points = task
    data = _WORKER["data"]
    observations = data.split.calibration if partition == "calibration" else data.split.held_out
    return bc.curve_forward_table(observations, points, fixed=FIXED, conditions=data.conditions,
                                  parameterization=parameterization(model_id))


def forward_table(model_id: str, partition: str, grid, data: Data, workers: int, override=None) -> AdmittedForwardTable:
    param = parameterization(model_id)
    observations = data.split.calibration if partition == "calibration" else data.split.held_out
    if workers <= 1:
        return bc.curve_forward_table(observations, grid, fixed=FIXED, conditions=data.conditions, parameterization=param)
    chunk = max(1, math.ceil(len(grid) / (workers * 6)))
    tasks = [(model_id, partition, grid[i:i + chunk]) for i in range(0, len(grid), chunk)]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                                                initargs=(data.allowance_v, override, data.label)) as pool:
        tables = list(pool.map(_worker_chunk, tasks))
    # Every chunk crossed admission row by row inside curve_forward_table; the
    # frozen constructor re-checks that each admitted row carries its refs.
    return AdmittedForwardTable(
        parameter_names=param.names, observation_keys=observations.keys,
        points=np.concatenate([t.points for t in tables]), values=np.concatenate([t.values for t in tables]),
        admissible_mask=np.concatenate([t.admissible_mask for t in tables]),
        admission_refs=tuple(itertools.chain.from_iterable(t.admission_refs for t in tables)),
        rejection_reasons=tuple(itertools.chain.from_iterable(t.rejection_reasons for t in tables)),
    )


def core_grid_route(model_id: str, data: Data, fit: dict, workers: int, override=None) -> dict:
    param = parameterization(model_id)
    spec = MODELS[model_id]["grid"]
    m, span = spec["per_axis"], spec["span_marginal_standard_errors"]
    theta, se = fit["theta"], np.sqrt(np.diag(fit["cov"]))
    axes = [np.linspace(t - span * e, t + span * e, m) for t, e in zip(theta, se)]
    grid = [tuple(float(v) for v in row) for row in np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(axes), -1).T]
    started = time.monotonic()
    table = forward_table(model_id, "calibration", grid, data, workers, override)
    posterior = gaussian_grid_posterior(table, data.split.calibration)
    rejected = int(np.sum(~table.admissible_mask))
    del table
    try:
        identifiability = assess_identifiability(posterior).to_dict()
    except GridResolutionError as exc:
        identifiability = {"status": "GRID_TOO_COARSE_FOR_INFERENCE", "refusal": str(exc)[:600]}
    diagnostics = posterior_grid_diagnostics(posterior)

    name2, T, names2 = reparameterize(model_id, param)
    mapped = PosteriorGrid(parameter_names=tuple(names2), points=posterior.points @ T.T, weights=posterior.weights,
                           log_likelihood=posterior.log_likelihood, admissible_mask=posterior.admissible_mask,
                           dataset_id=posterior.dataset_id)
    try:
        secondary = assess_identifiability(mapped).to_dict()
    except GridResolutionError as exc:
        secondary = {"status": "GRID_TOO_COARSE_FOR_INFERENCE", "refusal": str(exc)[:400]}
    secondary["note"] = ("same posterior mapped linearly; the mapped grid is not axis-aligned, so the frozen spacing "
                         "check sees many distinct coordinates per axis and is uninformative here")

    held_table = forward_table(model_id, "held_out", grid, data, workers, override)
    held = []
    for obs in data.split.held_out.observations:
        spec_obs = PredictiveObservableSpec(obs.key, VOLT, obs.sigma)
        uq = posterior_predictive_uq(posterior, held_table, spec_obs, twin=TWIN, model=bc.RINT_MODEL_REF,
                                     source_ref=obs.source_ref, credible_mass=CREDIBLE)
        assessment = assess_predictive_observation(
            posterior, held_table, spec_obs, obs.value, twin=TWIN, model=bc.RINT_MODEL_REF,
            source_ref=obs.source_ref, heldout_dataset_id=data.split.heldout_dataset_id, credible_mass=CREDIBLE,
        )
        observed = obs.value.magnitude_in(VOLT)
        mean = uq.mean.magnitude_in(VOLT)
        held.append({
            "observation_id": obs.condition_id, "state_of_charge": data.z[obs.condition_id], "region": data.region[obs.condition_id],
            "observed_v": observed, "predictive_mean_v": mean, "error_v": observed - mean,
            "parameter_sd_v": uq.epistemic_standard_uncertainty.magnitude_in(VOLT),
            "measurement_sd_v": obs.sigma.magnitude_in(VOLT),
            "total_sd_v": uq.total_standard_uncertainty.magnitude_in(VOLT),
            "total_interval_95_v": [uq.total_interval.lower.magnitude_in(VOLT), uq.total_interval.upper.magnitude_in(VOLT)],
            "standardized_residual": assessment.standardized_residual,
            "log_predictive_density": assessment.log_predictive_density,
            "covered_by_95_interval": bool(assessment.covered_by_central_interval),
            "evidence_digest": assessment.evidence.digest,
        })
    del held_table
    k = len(param.names)
    return {
        "route": "CORE_GRID",
        "grid": {"points": len(grid), "per_axis": m, "span_marginal_standard_errors": span, "rejected_rows": rejected,
                 "centre": "calibration-only WLS", "workers": workers, "wall_seconds_informational": round(time.monotonic() - started, 1)},
        "posterior": {"mean_v": posterior.mean.tolist(), "sd_v": np.sqrt(np.diag(posterior.covariance)).tolist(),
                      "correlation": posterior.correlation.tolist(),
                      "marginal_95_v": [list(posterior.marginal_interval(i, 0.95)) for i in range(k)],
                      "diagnostics": diagnostics},
        "identifiability": identifiability,
        "parameterization_sensitivity": {"primary": "node or knot voltages", "secondary": name2,
                                         "secondary_identifiability": secondary},
        "held_out": sorted(held, key=lambda h: h["state_of_charge"]),
    }


def domain_route(model_id: str, data: Data, fit: dict, center: np.ndarray | None = None) -> dict:
    """Exact linear-Gaussian posterior and predictive; centre defaults to the WLS estimate."""
    param = parameterization(model_id)
    theta = fit["theta"] if center is None else center
    cov = fit["cov"]
    base, f0h, Jh = affine_design(param, data.split.held_out, data)
    mean_h = f0h + Jh @ (theta - base)
    var_param = np.einsum("ij,jk,ik->i", Jh, cov, Jh)
    held = []
    for index, obs in enumerate(data.split.held_out.observations):
        observed = obs.value.magnitude_in(VOLT)
        s = obs.sigma.magnitude_in(VOLT)
        total = math.sqrt(var_param[index] + s * s)
        mean = float(mean_h[index])
        held.append({
            "observation_id": obs.condition_id, "state_of_charge": data.z[obs.condition_id], "region": data.region[obs.condition_id],
            "observed_v": observed, "predictive_mean_v": mean, "error_v": observed - mean,
            "parameter_sd_v": math.sqrt(max(var_param[index], 0.0)), "measurement_sd_v": s, "total_sd_v": total,
            "total_interval_95_v": [mean - Z95 * total, mean + Z95 * total],
            "standardized_residual": (observed - mean) / total,
            "log_predictive_density": float(norm.logpdf(observed, mean, total)),
            "covered_by_95_interval": abs(observed - mean) <= Z95 * total,
        })
    name2, T, names2 = reparameterize(model_id, param)
    return {
        "route": "DOMAIN_LINEAR_GAUSSIAN",
        "posterior": {"mean_v": theta.tolist(), "sd_v": np.sqrt(np.diag(cov)).tolist()},
        "identifiability": gaussian_identifiability(theta, cov, list(param.names)),
        "parameterization_sensitivity": {"primary": "node or knot voltages", "secondary": name2,
                                         "secondary_identifiability": gaussian_identifiability(T @ theta, T @ cov @ T.T, names2)},
        "held_out": sorted(held, key=lambda h: h["state_of_charge"]),
    }


# =====================================================================
# scoring
# =====================================================================

def metrics(held: list[dict]) -> dict:
    if not held:
        return {"n": 0}
    errors = np.asarray([h["error_v"] for h in held])
    z = np.asarray([h["standardized_residual"] for h in held])
    statistic = float(np.sum(z ** 2))
    p_value = float(chi2.sf(statistic, len(held)))
    covered = sum(1 for h in held if h["covered_by_95_interval"])
    worst = max(held, key=lambda h: abs(h["error_v"]))
    return {
        "n": len(held), "rmse_v": float(math.sqrt(np.mean(errors ** 2))), "mae_v": float(np.mean(np.abs(errors))),
        "max_abs_error_v": float(np.max(np.abs(errors))), "worst_at_state_of_charge": worst["state_of_charge"],
        "max_abs_standardized_residual": float(np.max(np.abs(z))),
        "mean_log_predictive_density": float(np.mean([h["log_predictive_density"] for h in held])),
        "coverage_95": f"{covered}/{len(held)}", "coverage_95_fraction": covered / len(held),
        "chi_square": statistic, "chi_square_df": len(held), "chi_square_p_value": p_value, "alpha": ALPHA,
        "adequacy": "MODEL_INADEQUATE" if p_value < ALPHA else "MODEL_ADEQUATE",
    }


def region_metrics(held: list[dict]) -> dict:
    return {name: metrics([h for h in held if h["region"] == name]) for name in REGION_NAMES}


def adequate_everywhere(scored: dict) -> bool:
    return scored["metrics"]["adequacy"] == "MODEL_ADEQUATE" and all(
        r["adequacy"] == "MODEL_ADEQUATE" for r in scored["regions"].values())


def empirical_adequacy(model_id: str, estimates: np.ndarray, data: Data) -> dict:
    param = parameterization(model_id)
    cell = CellSpecification(
        cell_id=FIXED.cell_id, nominal_capacity=FIXED.nominal_capacity, internal_resistance=FIXED.internal_resistance,
        coulombic_efficiency=FIXED.coulombic_efficiency, chemistry=FIXED.chemistry,
        open_circuit_voltage_curve=param.curve(tuple(estimates)),
    )
    points = [
        MeasuredOcvPoint(state_of_charge=Q(data.z[o.condition_id], ctx.DIMENSIONLESS), open_circuit_voltage=o.value,
                         standard_uncertainty=o.sigma, conditioning=ConditioningDirection.DISCHARGE, source_ref=o.source_ref)
        for o in data.split.held_out.observations
    ]
    result = assess_ocv_empirical_adequacy(cell, points).to_dict()
    result.pop("scored", None)
    return result


# =====================================================================
# one model, end to end
# =====================================================================

def run_model(model_id: str, data: Data, *, workers: int, core_grid: bool = True, override=None) -> dict:
    param = parameterization(model_id)
    cal = data.split.calibration
    full = wls(param, cal, data)
    k, n = full["p"], full["n"]
    record = {
        "model": MODELS[model_id], "names": list(param.names),
        "n_cal": n, "p": k, "residual_dof": n - k,
        "structural": {"rank": full["rank"], "p": k, "singular_values": full["singular_values"].tolist(),
                       "weighted_jacobian_condition_number": full["jacobian_condition"],
                       "p_less_than_n_cal": k < n, "rank_equals_p": full["rank"] == k},
    }
    if not (k < n and full["rank"] == k):
        record["gate"] = {"passed": False, "why": "p >= n_cal or rank < p: structurally unidentifiable; no scientific score"}
        return record
    fit = core_calibrate(param, cal, data, data.split.heldout_dataset_id)
    estimates = fit.pop("_estimates")
    fit.pop("_residuals")
    record["calibration"] = fit
    record["calibration"]["closed_form_wls_v"] = full["theta"].tolist()
    record["calibration"]["max_abs_disagreement_with_wls_v"] = float(np.max(np.abs(estimates - full["theta"])))
    pred_cal = full["f0"] + full["J"] @ (estimates - full["base"])
    y, s = weighted(cal)
    record["calibration"]["calibration_rmse_v"] = float(math.sqrt(np.mean((y - pred_cal) ** 2)))
    record["calibration"]["calibration_chi_square"] = float(np.sum(((y - pred_cal) / s) ** 2))

    routes = {"DOMAIN_LINEAR_GAUSSIAN": domain_route(model_id, data, full)}
    if core_grid and MODELS[model_id]["route"] == "CORE_GRID":
        routes["CORE_GRID"] = core_grid_route(model_id, data, full, workers, override)
    primary_route = MODELS[model_id]["route"] if MODELS[model_id]["route"] in routes else "DOMAIN_LINEAR_GAUSSIAN"
    for route in routes.values():
        route["metrics"] = metrics(route["held_out"])
        route["regions"] = region_metrics(route["held_out"])
    record["routes"] = routes
    record["primary_route"] = primary_route
    status = routes[primary_route]["identifiability"]["status"]
    record["gate"] = {"passed": status == "PARAMETERS_IDENTIFIABLE",
                      "identifiability_status": status, "route": primary_route,
                      "why": "p < n_cal, rank == p, and " + status}
    record["empirical_adequacy_measurement_u_only"] = empirical_adequacy(model_id, estimates, data)
    record["_estimates"] = estimates
    record["_wls"] = full
    return record


def route_cross_check(record: dict) -> dict | None:
    routes = record.get("routes", {})
    if "CORE_GRID" not in routes:
        return None
    g, d = routes["CORE_GRID"], routes["DOMAIN_LINEAR_GAUSSIAN"]
    gm, gs = np.asarray(g["posterior"]["mean_v"]), np.asarray(g["posterior"]["sd_v"])
    dm, ds = np.asarray(d["posterior"]["mean_v"]), np.asarray(d["posterior"]["sd_v"])
    mean_dev = float(np.max(np.abs(gm - dm) / gs))
    sd_ratio = (float(np.min(ds / gs)), float(np.max(ds / gs)))
    gt = np.asarray([h["total_sd_v"] for h in g["held_out"]])
    dt = np.asarray([h["total_sd_v"] for h in d["held_out"]])
    pred_dev = float(np.max(np.abs(dt / gt - 1.0)))
    passed = mean_dev <= 0.1 and 0.85 <= sd_ratio[0] and sd_ratio[1] <= 1.15 and pred_dev <= 0.05
    return {"max_mean_deviation_in_grid_sd": mean_dev, "sd_ratio_domain_over_grid_range": sd_ratio,
            "max_relative_total_predictive_sd_deviation": pred_dev, "passed": passed,
            "identifiability_core": g["identifiability"]["status"], "identifiability_domain": d["identifiability"]["status"],
            "held_out_chi_square_core": g["metrics"]["chi_square"], "held_out_chi_square_domain": d["metrics"]["chi_square"]}


# =====================================================================
# CV selection, ladder
# =====================================================================

def cross_validate(model_id: str, data: Data) -> dict:
    param = parameterization(model_id)
    cal = sorted(data.split.calibration.observations, key=lambda o: data.z[o.condition_id])
    folds = []
    for fold in range(5):
        test = tuple(o for r, o in enumerate(cal) if r % 5 == fold)
        train = tuple(o for r, o in enumerate(cal) if r % 5 != fold)
        train_set = ObservationSet(train, dataset_id=f"{data.source.dataset_id}.cv{fold}.train")
        test_set = ObservationSet(test, dataset_id=f"{data.source.dataset_id}.cv{fold}.test")
        design = wls(param, train_set, data)
        if not (design["p"] < design["n"] and design["rank"] == design["p"]):
            folds.append({"fold": fold, "eligible": False, "rank": design["rank"], "p": design["p"], "n_train": design["n"]})
            continue
        fit = core_calibrate(param, train_set, data, test_set.dataset_id)
        estimates = fit["_estimates"]
        predicted = forward(param, estimates, test_set, data)
        y, s = weighted(test_set)
        folds.append({"fold": fold, "eligible": True, "n_train": len(train), "n_test": len(test), "status": fit["status"],
                      "mean_squared_standardized_residual": float(np.mean(((y - predicted) / s) ** 2)),
                      "rmse_v": float(math.sqrt(np.mean((y - predicted) ** 2)))})
    eligible = all(f["eligible"] for f in folds)
    return {"folds": folds, "eligible": eligible,
            "cv_score": float(np.mean([f["mean_squared_standardized_residual"] for f in folds])) if eligible else None,
            "cv_rmse_v": float(math.sqrt(np.mean([f["rmse_v"] ** 2 for f in folds]))) if eligible else None}


def ladder(model_ids: list[str]) -> dict:
    out = {}
    for allowance in E.RELAXATION_LADDER_V:
        data = Data(allowance, label=f"ladder_{allowance * 1e3:g}mV")
        rung = {}
        for model_id in model_ids:
            param = parameterization(model_id)
            full = wls(param, data.split.calibration, data)
            fit = core_calibrate(param, data.split.calibration, data, data.split.heldout_dataset_id)
            scored = domain_route(model_id, data, full, center=fit["_estimates"])
            m = metrics(scored["held_out"])
            regions = region_metrics(scored["held_out"])
            rung[model_id] = {"calibration_status": fit["status"], "rmse_v": m["rmse_v"], "chi_square": m["chi_square"],
                              "p_value": m["chi_square_p_value"], "adequacy": m["adequacy"], "coverage_95": m["coverage_95"],
                              "regions": {r: {"chi_square": v["chi_square"], "p_value": v["chi_square_p_value"], "adequacy": v["adequacy"]} for r, v in regions.items()},
                              "adequate_everywhere": m["adequacy"] == "MODEL_ADEQUATE" and all(v["adequacy"] == "MODEL_ADEQUATE" for v in regions.values())}
        out[f"{allowance * 1e3:g}"] = rung
    thresholds = {}
    for model_id in model_ids:
        first = next((key for key, rung in out.items() if rung[model_id]["adequate_everywhere"]), None)
        first_global = next((key for key, rung in out.items() if rung[model_id]["adequacy"] == "MODEL_ADEQUATE"), None)
        thresholds[model_id] = {"smallest_allowance_mv_adequate_globally": first_global,
                                "smallest_allowance_mv_adequate_globally_and_in_every_region": first}
    return {"route": "DOMAIN_LINEAR_GAUSSIAN (re-calibrated through the frozen calibrate at every rung)",
            "rungs_mv": list(out), "results": out, "adequacy_thresholds": thresholds}


# =====================================================================
# synthetic controls
# =====================================================================

def synthetic_values(truth, seed: int) -> dict[str, float]:
    base = Data()
    rng = np.random.default_rng(seed)
    out = {}
    for p in base.points:
        out[p["observation_id"]] = float(truth(p["state_of_charge"]) + rng.normal(0.0, base.sigma(p["observation_id"])))
    return out


def run_controls(workers: int) -> dict:
    t5 = parameterization("T5")
    t5_voltages = (2.70, 3.20, 3.29, 3.31, 3.40)
    t5_truth = lambda z: bc.curve_ocv_prediction(FIXED, rested_condition("probe", z), parameterization=t5, voltages=t5_voltages).value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)
    knee_truth = lambda z: 3.30 - 0.62 * math.exp(-z / 0.018) + 0.06 * (z - 0.5)
    controls = {}

    override = synthetic_values(t5_truth, SEED)
    data = Data(observed_override=override, label="control_in_model")
    rec = run_model("T5", data, workers=workers, override=override)
    controls["in_model_T5"] = {
        "truth_voltages_v": t5_voltages, "gate": rec["gate"], "cross_check": route_cross_check(rec),
        "core_metrics": rec["routes"]["CORE_GRID"]["metrics"], "domain_metrics": rec["routes"]["DOMAIN_LINEAR_GAUSSIAN"]["metrics"],
        "core_identifiability": rec["routes"]["CORE_GRID"]["identifiability"]["status"],
        "estimates_v": rec["calibration"]["estimates_v"],
        "expected": "gate pass, MODEL_ADEQUATE, routes agree",
    }
    controls["in_model_T5"]["as_expected"] = bool(rec["gate"]["passed"] and controls["in_model_T5"]["core_metrics"]["adequacy"] == "MODEL_ADEQUATE"
                                                  and controls["in_model_T5"]["cross_check"]["passed"])

    override = synthetic_values(knee_truth, SEED + 1)
    data = Data(observed_override=override, label="control_knee_misfit")
    rec = run_model("P2", data, workers=workers, override=override)
    core = rec["routes"]["CORE_GRID"]
    worst = max(core["held_out"], key=lambda h: abs(h["error_v"]))
    controls["knee_misfit_P2"] = {
        "truth": "V(z) = 3.30 - 0.62 exp(-z/0.018) + 0.06 (z - 0.5) V", "gate": rec["gate"],
        "core_metrics": core["metrics"], "worst_region": worst["region"], "worst_error_v": worst["error_v"],
        "expected": "MODEL_INADEQUATE with the worst held-out error in KNEE",
        "as_expected": core["metrics"]["adequacy"] == "MODEL_INADEQUATE" and worst["region"] == "KNEE",
        "cross_check": route_cross_check(rec),
    }
    return {"schema": "battery_flagship_b3_controls/1", "run_before_the_measured_round": True, "seed": SEED,
            "noise": "Gaussian at each observation's preregistered primary sigma", "controls": controls,
            "all_as_expected": all(c["as_expected"] for c in controls.values())}


# =====================================================================
# secondary analyses
# =====================================================================

def hysteresis_vs_residuals(best_held: list[dict]) -> dict:
    quality = json.loads((ROUND / "DATA_QUALITY.json").read_text(encoding="utf-8"))
    deltas = quality["hysteresis_charge_minus_discharge_at_discharge_z_mv"]
    out = {}
    for name, low, high in E.REGIONS:
        d = [row["delta_mv"] for row in deltas if low <= row["state_of_charge"] < high]
        r = [abs(h["error_v"]) * 1e3 for h in best_held if h["region"] == name]
        rms = math.sqrt(sum(v * v for v in r) / len(r)) if r else None
        out[name] = {"n_discharge_points": len(d), "hysteresis_median_mv": float(np.median(d)), "hysteresis_min_mv": min(d),
                     "hysteresis_max_mv": max(d), "best_model_held_out_rms_error_mv": rms,
                     "hysteresis_median_over_rms_error": (float(np.median(d)) / rms) if rms else None}
    return {"method": "charge-conditioned branch linearly interpolated at each discharge z (DATA_QUALITY.json); data only, no model",
            "by_region": out}


def cross_cell(model_id: str, estimates: np.ndarray) -> dict:
    B1 = _load("_b1_harness_b3", ROOT / "benchmarks" / "battery_flagship_b1" / "audit" / "run_b1.py")
    discharge = B1.traces(B1.DISCHARGE_SHEET)
    _, budget = B1.build_source(discharge, tuple(discharge), (), "S-OCV.BATT_001.discharge.full_budget")
    param = parameterization(model_id)
    curve = param.curve(tuple(estimates))
    cell = CellSpecification(cell_id="BATT_001", nominal_capacity=B1.FIXED.nominal_capacity,
                             internal_resistance=B1.FIXED.internal_resistance, chemistry=B1.FIXED.chemistry,
                             open_circuit_voltage_curve=curve)
    points = [
        MeasuredOcvPoint(state_of_charge=Q(z, ctx.DIMENSIONLESS), open_circuit_voltage=Q(discharge[z]["relaxed_voltage_v"], VOLT),
                         standard_uncertainty=Q(budget[B1.condition_id(z)]["combined_standard_uncertainty_v"], VOLT),
                         conditioning=ConditioningDirection.DISCHARGE, source_ref=f"S-OCV:24h_Discharge_APR:{discharge[z]['label']}@24h")
        for z in sorted(discharge)
    ]
    assessment = assess_ocv_empirical_adequacy(cell, points).to_dict()
    k = len(param.names)
    return {
        "cell_A": "JAHN2024 A123_01 (fit)", "cell_B": "S-OCV BATT_001, Lithium Werks APR18650M1A, 24 h relaxed discharge OCV (no refit)",
        "model": model_id, "parameters_transfer": assessment,
        "verdict_parameters": "PARAMETERS_GENERALIZE" if assessment["status"] == "MODEL_EMPIRICALLY_ADEQUATE" else "PARAMETERS_DO_NOT_GENERALIZE",
        "representation_generalization": ("REPRESENTATION_GENERALIZATION_UNTESTABLE: BATT_001 has 6 discharge levels; refitting "
                                          f"{k} free parameters leaves {6 - k} for held-out, below the preregistered 3/3 split") if k > 3 else "testable (p <= 3)",
        "confounds": ["different laboratories and instruments", "24 h rest versus an undocumented rest",
                      "SOC definitions: nominal-capacity coulomb count (ACS724) versus Q / Q_top (BaSyTec)"],
    }


def cutoff_regression(model_id: str, estimates: np.ndarray) -> dict:
    param = parameterization(model_id)
    curve = param.curve(tuple(estimates))
    out = {"model": model_id}
    for label, cutoff, current in (("dataset_cutoff_2.0V_at_0.11A", 2.0, 0.11), ("inside_knee_3.0V_at_0.11A", 3.0, 0.11)):
        result = ctx.voltage_cutoff_state_of_charge_on_curve(cutoff_voltage=Q(cutoff, VOLT), current=Q(current, ctx.CURRENT_UNIT),
                                                             internal_resistance=FIXED.internal_resistance, curve=curve)
        out[label] = {"status": result.status.value, "state_of_charge": None if result.value is None else result.value.magnitude,
                      "reason": result.reason}
    return out


# =====================================================================
# main
# =====================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    started = time.monotonic()
    raw_before = E.verify_raw()
    for name in ("DATA_QUALITY.json", "OBSERVATIONS.json"):
        if sha(ROUND / name) != PREREG["pinned_inputs"][f"{name}_sha256"]:
            raise SystemExit(f"{name} differs from the preregistered digest")

    if args.controls:
        controls = run_controls(args.workers)
        controls["preregistration_sha256"] = sha(ROUND / "PREREGISTRATION.json")
        controls["run_wall_seconds_informational"] = round(time.monotonic() - started, 1)
        dump("CONTROLS.json", controls)
        print("controls all as expected:", controls["all_as_expected"])
        return 0

    controls = json.loads((ROUND / "CONTROLS.json").read_text(encoding="utf-8"))
    if not controls["all_as_expected"]:
        raise SystemExit("synthetic controls did not behave as preregistered; the measured round does not run")

    data = Data()
    leakage = data.leakage_proof()
    if not leakage["disjoint"]:
        raise SystemExit(f"leakage: {leakage}")

    records = {}
    for model_id in SCORED_MODELS:
        t0 = time.monotonic()
        records[model_id] = run_model(model_id, data, workers=args.workers)
        print(f"{model_id}: gate {records[model_id]['gate']['passed']} in {time.monotonic() - t0:.0f}s", flush=True)
    tcal_knots = [0.0] + sorted(p["state_of_charge"] for p in data.points if p["partition"] == "calibration") + [1.0]
    tcal = {"model": MODELS["T-CAL"], "p": len(tcal_knots), "n_cal": len(data.split.calibration.observations),
            "gate": {"passed": False, "why": f"p = {len(tcal_knots)} >= n_cal = {len(data.split.calibration.observations)}: every calibration point is a knot and two knots have no data; not calibrated, not scored"}}

    cross = {m: route_cross_check(r) for m, r in records.items() if route_cross_check(r) is not None}
    domain_route_valid = all(c["passed"] for c in cross.values())

    gate_passing = [m for m, r in records.items() if r["gate"]["passed"]]
    cv = {}
    for model_id in gate_passing:
        cv[model_id] = cross_validate(model_id, data)
        print(f"CV {model_id}: {cv[model_id]['cv_score']}", flush=True)
    eligible = {m: c["cv_score"] for m, c in cv.items() if c["eligible"]}

    best = None
    if eligible:
        lowest = min(eligible.values())
        near = [m for m, s in eligible.items() if s <= lowest * 1.01]
        best = min(near, key=lambda m: (records[m]["p"], eligible[m]))

    def scored(m):
        r = records[m]
        return r["routes"][r["primary_route"]]

    verdict_letter, verdict_notes = "D", []
    if best is not None:
        b = scored(best)
        if records[best]["primary_route"] == "DOMAIN_LINEAR_GAUSSIAN" and not domain_route_valid:
            verdict_letter = "D"
            verdict_notes.append("best honest model is on the domain route and the route cross-check failed")
        elif adequate_everywhere(b):
            verdict_letter = "A"
        else:
            family = "polynomial" if best.startswith("P") else "tabulated"
            simpler = [m for m in gate_passing if m in PREREG["phase17_complexity_and_selection"]["families"][family] and records[m]["p"] < records[best]["p"]]
            overfit = [m for m in simpler if b["metrics"]["rmse_v"] >= 1.2 * scored(m)["metrics"]["rmse_v"] or adequate_everywhere(scored(m))]
            if overfit:
                verdict_letter = "C"
                verdict_notes.append(f"less complex models doing better on held-out data: {overfit}")
            else:
                verdict_letter = "B"
                richer_adequate = [m for m in gate_passing if records[m]["p"] > records[best]["p"] and adequate_everywhere(scored(m))]
                if richer_adequate:
                    verdict_notes.append(f"ADEQUATE_ONLY_AT_A_COMPLEXITY_CV_DID_NOT_SELECT: {richer_adequate}")
    verdict = PREREG["phase23_verdict_mapping_fixed_now"]["final_verdict_strings"][verdict_letter]

    print("ladder ...", flush=True)
    ladder_result = ladder(gate_passing)

    complexity = []
    for model_id in SCORED_MODELS:
        r = records[model_id]
        row = {"model": model_id, "family": "polynomial" if model_id.startswith("P") else "tabulated", "p": r["p"],
               "residual_dof": r["residual_dof"], "rank": r["structural"]["rank"], "gate_passed": r["gate"]["passed"]}
        if "calibration" in r:
            s = scored(model_id)
            row.update({"route": r["primary_route"], "identifiability": r["gate"]["identifiability_status"],
                        "calibration_rmse_mv": r["calibration"]["calibration_rmse_v"] * 1e3,
                        "cv_score": cv.get(model_id, {}).get("cv_score"), "cv_rmse_mv": (cv.get(model_id, {}).get("cv_rmse_v") or float("nan")) * 1e3,
                        "held_out_rmse_mv": s["metrics"]["rmse_v"] * 1e3, "held_out_chi_square": s["metrics"]["chi_square"],
                        "held_out_adequacy": s["metrics"]["adequacy"], "adequate_everywhere": adequate_everywhere(s),
                        "knee_rmse_mv": s["regions"]["KNEE"]["rmse_v"] * 1e3, "plateau_rmse_mv": s["regions"]["PLATEAU"]["rmse_v"] * 1e3})
        complexity.append(row)
    held_best_post_hoc = min((m for m in gate_passing), key=lambda m: scored(m)["metrics"]["rmse_v"]) if gate_passing else None

    b1 = json.loads((ROOT / "benchmarks" / "battery_flagship_b1" / "RESULTS.json").read_text(encoding="utf-8"))
    b2 = json.loads((ROOT / "benchmarks" / "battery_flagship_b2" / "RESULTS.json").read_text(encoding="utf-8"))["primary"]
    comparison_rows = []
    if best is not None:
        bm, br = scored(best)["metrics"], records[best]
        comparison_rows = [
            {"metric": "dataset", "b1": "S-OCV BATT_001, 24 h relaxed", "b2": "S-OCV BATT_001, 24 h relaxed", "b3": "Jahn 2024 A123_01, interrupt-relaxed (rest undocumented)"},
            {"metric": "n_cal", "b1": 3, "b2": 3, "b3": br["n_cal"]},
            {"metric": "p", "b1": 2, "b2": 3, "b3": br["p"]},
            {"metric": "residual dof", "b1": 1, "b2": 0, "b3": br["residual_dof"]},
            {"metric": "held-out count", "b1": b1["metrics"]["n"], "b2": b2["metrics"]["n"], "b3": bm["n"]},
            {"metric": "identifiability", "b1": b1["identifiability"]["status"], "b2": b2["identifiability"]["status"], "b3": br["gate"]["identifiability_status"] + f" ({br['primary_route']})"},
            {"metric": "RMSE (mV)", "b1": b1["metrics"]["rmse_v"] * 1e3, "b2": b2["metrics"]["rmse_v"] * 1e3, "b3": bm["rmse_v"] * 1e3},
            {"metric": "MAE (mV)", "b1": b1["metrics"]["mae_v"] * 1e3, "b2": b2["metrics"]["mae_v"] * 1e3, "b3": bm["mae_v"] * 1e3},
            {"metric": "max |error| (mV)", "b1": b1["metrics"]["max_abs_error_v"] * 1e3, "b2": b2["metrics"]["max_abs_error_v"] * 1e3, "b3": bm["max_abs_error_v"] * 1e3},
            {"metric": "coverage 95 %", "b1": b1["metrics"]["coverage_95"], "b2": b2["metrics"]["coverage_95"], "b3": bm["coverage_95"]},
            {"metric": "chi-square (dof)", "b1": f"{b1['metrics']['chi_square']:.4g} ({b1['metrics']['chi_square_df']})", "b2": f"{b2['metrics']['chi_square']:.4g} ({b2['metrics']['chi_square_df']})", "b3": f"{bm['chi_square']:.4g} ({bm['chi_square_df']})"},
            {"metric": "adequacy", "b1": b1["adequacy_verdict"], "b2": b2["adequacy_verdict"], "b3": bm["adequacy"] + ("; every region adequate" if adequate_everywhere(scored(best)) else "; not adequate in every region")},
        ]

    secondary = {
        "route_cross_check": {"per_model": cross, "domain_route_may_carry_a_claim": domain_route_valid},
        "leakage_proof": leakage,
        "t_cal_gate_demonstration": tcal,
    }
    if best is not None:
        estimates = records[best]["_estimates"]
        secondary["hysteresis"] = hysteresis_vs_residuals(scored(best)["held_out"])
        secondary["cross_cell"] = cross_cell(best, estimates)
        secondary["cutoff_regression_on_best_curve"] = cutoff_regression(best, estimates)

    for r in records.values():
        r.pop("_estimates", None)
        r.pop("_wls", None)
    dump("RESULTS.json", {
        "schema": "battery_flagship_b3_results/1", "preregistration_sha256": sha(ROUND / "PREREGISTRATION.json"),
        "controls_sha256": sha(ROUND / "CONTROLS.json"), "raw_sha256_before": raw_before,
        "observations": {"calibration": data.split.calibration.dataset_id, "held_out": data.split.heldout_dataset_id},
        "models": records, "cross_validation": cv, "relaxation_ladder": ladder_result,
    })
    dump("COMPARISON.json", {
        "schema": "battery_flagship_b3_comparison/1",
        "complexity_study": complexity,
        "cv_eligible_scores": eligible,
        "best_honest_model": best,
        "held_out_best_post_hoc_not_used_for_selection": held_best_post_hoc,
        "b1_b2_b3": comparison_rows,
        "verdict_letter": verdict_letter, "verdict": verdict, "verdict_notes": verdict_notes,
        "verdict_scope": PREREG["phase23_verdict_mapping_fixed_now"]["scope_of_any_verdict"],
    })
    raw_after = E.verify_raw()
    secondary["raw_unchanged"] = raw_after == raw_before
    secondary["run_wall_seconds_informational"] = round(time.monotonic() - started, 1)
    dump("SECONDARY.json", secondary)
    print("best honest model:", best, "| verdict:", verdict, verdict_notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
