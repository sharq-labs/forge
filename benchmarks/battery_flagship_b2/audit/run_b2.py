"""Battery Flagship B2: the existing OCV curve, on B1's exact evidence and protocol.

    python -X utf8 benchmarks/battery_flagship_b2/audit/run_b2.py

Reads ``PREREGISTRATION.json`` (B2) and reuses B1's harness helpers BY PATH and
read-only -- the evidence reader, the integrity checks, the A2 sigma rule, the
condition identities -- so the data handling cannot drift from B1's. B1's
artifacts are read, never written.

Writes, all under benchmarks/battery_flagship_b2/:

    RESULTS.json      the primary B2-POLY2 run and the secondary B2-TAB3 run
    COMPARISON.json   B1 chord vs B2 curve, and the preregistered verdict
    SECONDARY.json    flexibility guard, coefficient sensitivity, residual
                      structure, hysteresis, generalization to BATT_002,
                      empirical adequacy (Phase 12), cutoff on the curve (13)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import pathlib
import sys
import time

import numpy as np
from scipy.stats import chi2

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "battery_flagship_b2"
B1_ROUND = ROOT / "benchmarks" / "battery_flagship_b1"
PREREG = json.loads((ROUND / "PREREGISTRATION.json").read_text(encoding="utf-8"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B1 = _load("_b1_harness", B1_ROUND / "audit" / "run_b1.py")

from engcore.adequacy import assess_predictive_observation  # noqa: E402
from engcore.domains.battery import calibration as bc  # noqa: E402
from engcore.domains.battery import cell as battery_cell  # noqa: E402
from engcore.domains.battery import context as ctx  # noqa: E402
from engcore.domains.battery.empirical import (  # noqa: E402
    ConditioningDirection,
    MeasuredOcvPoint,
    assess_ocv_empirical_adequacy,
)
from engcore.inference import (  # noqa: E402
    CalibrationSpec,
    GridResolutionError,
    NoiseModel,
    ObservationSplit,
    assess_identifiability,
    calibrate,
    gaussian_grid_posterior,
    observation_content_digest,
    posterior_grid_diagnostics,
)
from engcore.scientific.units.quantity import Quantity as Q  # noqa: E402
from engcore.uq import PredictiveObservableSpec, posterior_predictive_uq  # noqa: E402

VOLT = ctx.VOLTAGE_UNIT
ALPHA = 0.01
CREDIBLE = 0.95
PER_AXIS = 25
SPAN_SE = 6.0
SEED = 20260912
BOUNDS = (2.0, 3.6)
MATERIAL_RMSE_REDUCTION = 0.20

POLY2 = bc.PolynomialNodeParameterization((0.0, 0.5, 1.0), source="B2-POLY2")
TAB3 = bc.TabulatedKnotParameterization((0.0, 0.5, 1.0), source="B2-TAB3")
TAB5 = bc.TabulatedKnotParameterization((0.0, 0.25, 0.5, 0.75, 1.0), source="B2-TAB5")


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def z_of(condition_id: str) -> float:
    return float(condition_id[-3:]) / 100


def predict(parameterization, voltages, z) -> float:
    return bc.curve_ocv_prediction(
        B1.FIXED, B1.rested_condition(z), parameterization=parameterization, voltages=voltages
    ).value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)


def jacobian(parameterization, zs) -> np.ndarray:
    """The linear map from node or knot voltages to predictions, through the adapter."""
    k = len(parameterization.names)
    base = 3.3 + np.linspace(-0.1, 0.1, k)
    f0 = np.asarray([predict(parameterization, tuple(base), z) for z in zs])
    columns = []
    for index in range(k):
        bumped = base.copy()
        bumped[index] += 0.01
        columns.append((np.asarray([predict(parameterization, tuple(bumped), z) for z in zs]) - f0) / 0.01)
    return np.column_stack(columns)


def closed_form(parameterization, observations):
    zs = [z_of(o.condition_id) for o in observations.observations]
    y = np.asarray([o.value.magnitude_in(VOLT) for o in observations.observations])
    s = np.asarray([o.sigma.magnitude_in(VOLT) for o in observations.observations])
    weighted = jacobian(parameterization, zs) / s[:, None]
    cov = np.linalg.inv(weighted.T @ weighted)
    theta = cov @ weighted.T @ (y / s)
    return theta, cov


# =====================================================================
# one curve run: calibrate -> posterior -> identifiability -> held-out
# =====================================================================

def run_curve(parameterization, source, held_z, *, label):
    conditions = {o.condition_id: B1.rested_condition(z_of(o.condition_id)) for o in source.observations}
    split = ObservationSplit.partition(
        source=source, held_out_condition_ids=tuple(B1.condition_id(z) for z in held_z),
        twin=B1.TWIN, calibration_dataset_id=f"{source.dataset_id}.calibration",
        heldout_dataset_id=f"{source.dataset_id}.held_out",
    )
    cal_digests = {observation_content_digest(o) for o in split.calibration.observations}
    held_digests = {observation_content_digest(o) for o in split.held_out.observations}
    cal_ids = {o.condition_id for o in split.calibration.observations}
    held_ids = {o.condition_id for o in split.held_out.observations}

    k = len(parameterization.names)
    n_cal = len(split.calibration.observations)
    spec = CalibrationSpec(
        parameters=bc.build_curve_parameter_set(parameterization, lower=Q(BOUNDS[0], VOLT), upper=Q(BOUNDS[1], VOLT)),
        fixed={
            ctx.NOMINAL_CAPACITY: B1.FIXED.nominal_capacity,
            ctx.INTERNAL_RESISTANCE: B1.FIXED.internal_resistance,
            ctx.COULOMBIC_EFFICIENCY: B1.FIXED.coulombic_efficiency,
            ctx.CELL_TEMPERATURE: B1.CELL_TEMPERATURE,
            ctx.DISCHARGE_CURRENT: B1.CONDITIONING_CURRENT,
        },
        initial_point={n: Q(v, VOLT) for n, v in zip(parameterization.names, np.linspace(3.2, 3.4, k))},
        noise_model=NoiseModel(),
    )
    counter: dict[str, int] = {}
    fit = calibrate(
        spec, split.calibration,
        bc.curve_forward_evaluator(split.calibration, fixed=B1.FIXED, conditions=conditions,
                                   parameterization=parameterization, counter=counter),
        heldout_dataset_id=split.heldout_dataset_id, max_evaluations=2000, seed=SEED,
    )
    estimates = [e.value.magnitude_in(VOLT) for e in fit.estimates]
    theta, cov = closed_form(parameterization, split.calibration)
    se = np.sqrt(np.diag(cov))

    axes = [np.linspace(t - SPAN_SE * e, t + SPAN_SE * e, PER_AXIS) for t, e in zip(theta, se)]
    grid = [tuple(float(v) for v in point) for point in np.array(np.meshgrid(*axes, indexing="ij")).reshape(k, -1).T]
    record: dict = {}
    table = bc.curve_forward_table(split.calibration, grid, fixed=B1.FIXED, conditions=conditions,
                                   parameterization=parameterization)
    posterior = gaussian_grid_posterior(table, split.calibration)
    try:
        identifiability = assess_identifiability(posterior).to_dict()
    except GridResolutionError as exc:
        identifiability = {"status": "GRID_TOO_COARSE_FOR_INFERENCE", "refusal": str(exc)[:400]}
    diagnostics = posterior_grid_diagnostics(posterior)

    predictive = bc.curve_forward_table(split.held_out, grid, fixed=B1.FIXED, conditions=conditions,
                                        parameterization=parameterization)
    held = []
    for obs in split.held_out.observations:
        spec_obs = PredictiveObservableSpec(obs.key, VOLT, obs.sigma)
        uq = posterior_predictive_uq(posterior, predictive, spec_obs, twin=B1.TWIN, model=bc.RINT_MODEL_REF,
                                     source_ref=obs.source_ref, credible_mass=CREDIBLE)
        assessment = assess_predictive_observation(
            posterior, predictive, spec_obs, obs.value, twin=B1.TWIN, model=bc.RINT_MODEL_REF,
            source_ref=obs.source_ref, heldout_dataset_id=split.heldout_dataset_id, credible_mass=CREDIBLE,
        )
        observed = obs.value.magnitude_in(VOLT)
        mean = uq.mean.magnitude_in(VOLT)
        held.append({
            "condition_id": obs.condition_id, "state_of_charge": z_of(obs.condition_id),
            "observed_v": observed, "predictive_mean_v": mean, "error_v": observed - mean,
            "parameter_standard_uncertainty_v": uq.epistemic_standard_uncertainty.magnitude_in(VOLT),
            "measurement_standard_uncertainty_v": obs.sigma.magnitude_in(VOLT),
            "total_standard_uncertainty_v": uq.total_standard_uncertainty.magnitude_in(VOLT),
            "parameter_interval_95_v": [uq.epistemic_interval.lower.magnitude_in(VOLT), uq.epistemic_interval.upper.magnitude_in(VOLT)],
            "total_interval_95_v": [uq.total_interval.lower.magnitude_in(VOLT), uq.total_interval.upper.magnitude_in(VOLT)],
            "standardized_residual": assessment.standardized_residual,
            "two_sided_tail_probability": assessment.two_sided_tail_probability,
            "log_predictive_density": assessment.log_predictive_density,
            "covered_by_95_interval": assessment.covered_by_central_interval,
            "evidence_digest": assessment.evidence.digest,
        })
    held.sort(key=lambda h: h["state_of_charge"])
    errors = np.asarray([h["error_v"] for h in held])
    residuals = np.asarray([h["standardized_residual"] for h in held])
    statistic = float(np.sum(residuals ** 2))
    p_value = float(chi2.sf(statistic, len(held)))
    covered = sum(1 for h in held if h["covered_by_95_interval"])
    record.update({
        "label": label,
        "parameterization": {"form": type(parameterization).__name__, "positions": list(getattr(parameterization, "nodes", getattr(parameterization, "knots", ()))), "names": list(parameterization.names)},
        "free_parameters": k, "calibration_observations": n_cal, "parameter_to_data_ratio": k / n_cal,
        "residual_degrees_of_freedom": n_cal - k,
        "split": {"calibration": sorted(cal_ids), "held_out": sorted(held_ids),
                  "intersection_by_identity": sorted(cal_ids & held_ids),
                  "intersection_by_material_content": sorted(cal_digests & held_digests)},
        "calibration": {
            "status": fit.status.value, "termination_reason": fit.termination_reason,
            "optimizer_evaluations": fit.evaluation_count, "admitted_forward_predictions": counter.get("n", 0),
            "objective_chi_square": fit.objective_value, "bounds_v": list(BOUNDS),
            "initial_point_v": [float(v) for v in np.linspace(3.2, 3.4, k)],
            "estimates_v": dict(zip(parameterization.names, estimates)),
            "standardized_calibration_residuals": list(fit.residuals),
            "wall_seconds_informational": round(fit.provenance.wall_seconds, 4),
            "closed_form_estimate_v": [float(v) for v in theta],
            "max_abs_disagreement_with_closed_form_v": float(np.max(np.abs(np.asarray(estimates) - theta))) if estimates else None,
            "zero_residual_dof_note": (
                "the fit has as many free parameters as calibration observations, so its "
                "calibration residuals are zero by construction: NO internal check, never "
                "read as validity" if n_cal == k else ""
            ),
        },
        "posterior": {
            "grid_points": len(grid), "per_axis": PER_AXIS, "span_se": SPAN_SE,
            "rejected_rows": int(np.sum(~table.admissible_mask)),
            "posterior_mean_v": [float(v) for v in posterior.mean],
            "posterior_sd_v": [float(math.sqrt(posterior.covariance[i, i])) for i in range(k)],
            "correlation": [[float(v) for v in row] for row in posterior.correlation],
            "marginal_95_v": [list(map(float, posterior.marginal_interval(i, 0.95))) for i in range(k)],
            "diagnostics": {kk: (float(v) if isinstance(v, (float, np.floating)) else v) for kk, v in diagnostics.items()},
        },
        "identifiability": identifiability,
        "held_out": held,
        "metrics": {
            "n": len(held), "rmse_v": float(math.sqrt(np.mean(errors ** 2))), "mae_v": float(np.mean(np.abs(errors))),
            "max_abs_error_v": float(np.max(np.abs(errors))),
            "mean_log_predictive_density": float(np.mean([h["log_predictive_density"] for h in held])),
            "coverage_95": f"{covered}/{len(held)}", "chi_square": statistic, "chi_square_df": len(held),
            "chi_square_p_value": p_value, "alpha": ALPHA,
        },
        "model_discrepancy": "MODEL_DISCREPANCY_NOT_MODELLED",
        "adequacy_verdict": "inadequate_for_declared_study" if p_value < ALPHA else "adequate_for_declared_study",
        "_posterior_mean": [float(v) for v in posterior.mean],
        "_cov": cov,
    })
    return record


# =====================================================================
# main
# =====================================================================

def main() -> int:
    started = time.monotonic()
    evidence_file = ROOT / PREREG["phase3_same_measured_data"]["file"]
    before = sha(evidence_file)
    if before != PREREG["phase3_same_measured_data"]["file_sha256"]:
        raise SystemExit(f"evidence hash {before} is not the preregistered one")
    integrity = B1.integrity()
    if not integrity["passed"]:
        raise SystemExit(f"integrity failed: {integrity['problems']}")
    b1_results = json.loads((B1_ROUND / "RESULTS.json").read_text(encoding="utf-8"))

    discharge = B1.traces(B1.DISCHARGE_SHEET)
    charge = B1.traces(B1.CHARGE_SHEET)
    cal_z, held_z = (0.2, 0.5, 0.8), (0.0, 0.4, 0.6)
    source, budgets = B1.build_source(discharge, cal_z, held_z, "S-OCV.BATT_001.discharge")

    primary = run_curve(POLY2, source, held_z, label="B2-POLY2")
    secondary_run = run_curve(TAB3, source, held_z, label="B2-TAB3")

    # same evidence as B1: identical evidence-identity digests at every held-out point
    b1_digests = {h["condition_id"]: h["evidence_digest"] for h in b1_results["held_out"]}
    same_evidence = {h["condition_id"]: h["evidence_digest"] == b1_digests[h["condition_id"]] for h in primary["held_out"]}

    # ---- flexibility guard: 5 knots from 3 calibration levels -----------------
    zs = [z_of(o.condition_id) for o in source.observations if z_of(o.condition_id) in cal_z]
    J5 = jacobian(TAB5, zs)
    _, singular, vh = np.linalg.svd(J5)
    rank5 = int(np.linalg.matrix_rank(J5, tol=1e-9))
    guard_calibration = None
    try:
        split5 = ObservationSplit.partition(source=source, held_out_condition_ids=tuple(B1.condition_id(z) for z in held_z),
                                            twin=B1.TWIN, calibration_dataset_id="S-OCV.BATT_001.discharge.calibration",
                                            heldout_dataset_id="S-OCV.BATT_001.discharge.held_out")
        conditions = {o.condition_id: B1.rested_condition(z_of(o.condition_id)) for o in source.observations}
        spec5 = CalibrationSpec(
            parameters=bc.build_curve_parameter_set(TAB5, lower=Q(BOUNDS[0], VOLT), upper=Q(BOUNDS[1], VOLT)),
            fixed={}, initial_point={n: Q(v, VOLT) for n, v in zip(TAB5.names, np.linspace(3.2, 3.4, 5))},
            noise_model=NoiseModel(),
        )
        fit5 = calibrate(spec5, split5.calibration,
                         bc.curve_forward_evaluator(split5.calibration, fixed=B1.FIXED, conditions=conditions, parameterization=TAB5),
                         heldout_dataset_id=split5.heldout_dataset_id, seed=SEED)
        guard_calibration = {"status": fit5.status.value, "termination_reason": fit5.termination_reason,
                             "estimates_v": [e.value.magnitude_in(VOLT) for e in fit5.estimates],
                             "objective_chi_square": fit5.objective_value}
    except Exception as exc:  # noqa: BLE001 - reported
        guard_calibration = {"error": f"{type(exc).__name__}: {exc}"}
    flexibility = {
        "B2-TAB5_free_parameters": 5, "calibration_observations": 3,
        "jacobian_rank": rank5, "singular_values": [float(v) for v in singular],
        "null_space_dimension": 5 - rank5,
        "null_space_basis": [[float(x) for x in row] for row in vh[rank5:]],
        "structurally_identifiable": rank5 == 5,
        "frozen_calibrate_outcome": guard_calibration,
        "reading": "rank 3 < 5: two directions in knot-voltage space leave every calibration prediction unchanged, so no amount of this data can determine them. Not scored on held-out data.",
    }

    # ---- coefficient-parameterization sensitivity (preregistered secondary) ---
    vander = np.vander(np.asarray(POLY2.nodes), increasing=True)
    inverse = np.linalg.inv(vander)
    coefficients = inverse @ np.asarray(primary["_posterior_mean"])
    cov_c = inverse @ primary["_cov"] @ inverse.T
    widths = [2 * 1.959963985 * math.sqrt(cov_c[i, i]) / abs(coefficients[i]) for i in range(3)]
    sensitivity = {
        "coefficients_ascending_v": [float(c) for c in coefficients],
        "coefficient_sd_v": [float(math.sqrt(cov_c[i, i])) for i in range(3)],
        "relative_95_widths": [float(w) for w in widths],
        "frozen_width_threshold": 1.0,
        "would_be_classified": "NOT_IDENTIFIABLE" if max(widths) > 1.0 else "IDENTIFIABLE",
        "reading": "the same fitted function, expressed through coefficients: the curvature coefficient is small, so its interval is wide relative to itself. This is why the preregistered primary parameterizes by voltages. Linear transform of the node posterior, not a second grid.",
    }

    # ---- residual structure, all six SOC, from each posterior-mean curve --------
    poly_curve = POLY2.curve(primary["_posterior_mean"])
    chord = b1_results["calibration"]["estimates_v"]
    structure = []
    for z in sorted(discharge):
        observed = discharge[z]["relaxed_voltage_v"]
        curve_v = poly_curve.evaluate(Q(z, "dimensionless")).value.magnitude_in(VOLT)
        chord_v = chord["open_circuit_voltage_at_empty"] + (chord["open_circuit_voltage_at_full"] - chord["open_circuit_voltage_at_empty"]) * z
        structure.append({"state_of_charge": z, "partition": "calibration" if z in cal_z else "held_out",
                          "observed_v": observed, "b2_curve_v": curve_v, "b1_chord_v": chord_v,
                          "b2_residual_mv": (observed - curve_v) * 1e3, "b1_residual_mv": (observed - chord_v) * 1e3})

    # ---- hysteresis vs B2 residuals ----------------------------------------------
    hysteresis = []
    b2_residual = {row["state_of_charge"]: row["b2_residual_mv"] for row in structure}
    for z in sorted(set(discharge) & set(charge)):
        delta = (charge[z]["relaxed_voltage_v"] - discharge[z]["relaxed_voltage_v"]) * 1e3
        hysteresis.append({"state_of_charge": z, "charge_minus_discharge_mv": delta,
                           "b2_residual_mv": b2_residual[z],
                           "partition": "calibration" if z in cal_z else "held_out",
                           "ratio_to_b2_residual": (abs(delta) / abs(b2_residual[z])) if abs(b2_residual[z]) > 1e-9 else None})

    # ---- Phase 12: empirical adequacy on BATT_001 held-out, beside applicability ---
    _, full_budget = B1.build_source(discharge, tuple(discharge), (), "S-OCV.BATT_001.discharge.full_budget")

    def held_points(sheet_traces, budget, zs_, batt, sheet):
        points = []
        for z in zs_:
            points.append(MeasuredOcvPoint(
                state_of_charge=Q(z, "dimensionless"),
                open_circuit_voltage=Q(sheet_traces[z]["relaxed_voltage_v"], VOLT),
                standard_uncertainty=Q(budget[z], VOLT),
                conditioning=ConditioningDirection.DISCHARGE,
                source_ref=f"S-OCV:{sheet}:{sheet_traces[z]['label']}@24h",
            ))
        return points

    batt1_budget = {z: full_budget[B1.condition_id(z)]["combined_standard_uncertainty_v"] for z in discharge}
    curve_cell = battery_cell.CellSpecification(
        cell_id="BATT_001", nominal_capacity=B1.FIXED.nominal_capacity, internal_resistance=B1.FIXED.internal_resistance,
        chemistry=B1.FIXED.chemistry, open_circuit_voltage_curve=poly_curve,
    )
    chord_cell = B1.FIXED.cell(ocv_at_empty=Q(chord["open_circuit_voltage_at_empty"], VOLT),
                               ocv_at_full=Q(chord["open_circuit_voltage_at_full"], VOLT))

    def applicability(cell):
        load = B1.rested_condition(0.4).load(B1.FIXED)
        problem = battery_cell.build_battery_problem(cell, load)
        verdict = battery_cell.assess_rint_validity(
            problem, state_of_charge=Q(0.4, "dimensionless"), discharge_current=B1.CONDITIONING_CURRENT,
            cell_temperature=B1.CELL_TEMPERATURE,
            open_circuit_voltage_curve=cell.open_circuit_voltage_curve,
        )
        return verdict

    empirical = {}
    for name, cell in (("B1_chord", chord_cell), ("B2_curve", curve_cell)):
        verdict = applicability(cell)
        assessment = assess_ocv_empirical_adequacy(
            cell, held_points(discharge, batt1_budget, held_z, "BATT_001", B1.DISCHARGE_SHEET),
            applicability_status=verdict,
        )
        empirical[name] = {**assessment.to_dict(), "applicability_violated": list(verdict.violated)}

    # ---- Phase 15: generalization to BATT_002, no recalibration --------------------
    bse = B1.traces("24h_Discharge_BSE")
    bse_u = {}
    for z in bse:
        drift = bse[z]["final_hour_drift_v"]
        bse_u[z] = B1.EV.ocv_uncertainty(z, bse, drift)["combined_standard_uncertainty_v"]
    generalization = {}
    for name, cell in (("B1_chord", chord_cell), ("B2_curve", curve_cell)):
        assessment = assess_ocv_empirical_adequacy(
            cell, held_points(bse, bse_u, sorted(bse), "BATT_002", "24h_Discharge_BSE"))
        generalization[name] = assessment.to_dict()
    generalization["cell"] = "BATT_002, BSE 18650 LiFePO4, 1500 mAh; discharge-branch SOC " + str(sorted(bse))
    generalization["other_chemistries"] = "DATA_LIMIT: BATT_003..BATT_008 carry only 0 % and 100 % OCV, and a LiFePO4 curve is no claim about them"

    # ---- Phase 13 applied: the dataset's own 2.0 V discharge cutoff ----------------
    cutoff = {
        "cutoff_voltage_v": 2.0, "current_a": B1.CONDITIONING_CURRENT.magnitude_in("ampere"),
        "b1_chord_state_of_charge": ctx.voltage_cutoff_state_of_charge(
            cutoff_voltage=Q(2.0, VOLT), current=B1.CONDITIONING_CURRENT, internal_resistance=B1.FIXED.internal_resistance,
            ocv_at_empty=chord_cell.open_circuit_voltage_at_empty, ocv_at_full=chord_cell.open_circuit_voltage_at_full,
        ).magnitude,
    }
    on_curve = ctx.voltage_cutoff_state_of_charge_on_curve(
        cutoff_voltage=Q(2.0, VOLT), current=B1.CONDITIONING_CURRENT, internal_resistance=B1.FIXED.internal_resistance,
        curve=poly_curve,
    )
    cutoff["b2_curve_status"] = on_curve.status.value
    cutoff["b2_curve_state_of_charge"] = None if on_curve.value is None else on_curve.value.magnitude
    cutoff["b2_curve_reason"] = on_curve.reason

    # ---- comparison and the preregistered verdict ----------------------------------
    b1m, b2m = b1_results["metrics"], primary["metrics"]
    reduction = 1.0 - b2m["rmse_v"] / b1m["rmse_v"]
    comparison = {
        "rows": [
            {"metric": "RMSE (mV)", "b1_chord": b1m["rmse_v"] * 1e3, "b2_curve": b2m["rmse_v"] * 1e3, "improvement_pct": 100 * reduction},
            {"metric": "MAE (mV)", "b1_chord": b1m["mae_v"] * 1e3, "b2_curve": b2m["mae_v"] * 1e3, "improvement_pct": 100 * (1 - b2m["mae_v"] / b1m["mae_v"])},
            {"metric": "max |error| (mV)", "b1_chord": b1m["max_abs_error_v"] * 1e3, "b2_curve": b2m["max_abs_error_v"] * 1e3, "improvement_pct": 100 * (1 - b2m["max_abs_error_v"] / b1m["max_abs_error_v"])},
            {"metric": "coverage 95 %", "b1_chord": b1m["coverage_95"], "b2_curve": b2m["coverage_95"], "improvement_pct": None},
            {"metric": "chi-square (3 df)", "b1_chord": b1m["chi_square"], "b2_curve": b2m["chi_square"], "improvement_pct": 100 * (1 - b2m["chi_square"] / b1m["chi_square"])},
            {"metric": "free parameters", "b1_chord": 2, "b2_curve": primary["free_parameters"], "improvement_pct": None},
            {"metric": "residual dof", "b1_chord": 1, "b2_curve": primary["residual_degrees_of_freedom"], "improvement_pct": None},
            {"metric": "identifiability", "b1_chord": b1_results["identifiability"]["status"], "b2_curve": primary["identifiability"]["status"], "improvement_pct": None},
            {"metric": "adequacy", "b1_chord": b1_results["adequacy_verdict"], "b2_curve": primary["adequacy_verdict"], "improvement_pct": None},
        ],
        "same_evidence_as_b1": same_evidence,
        "rmse_reduction_fraction": reduction,
        "material_threshold_fraction": MATERIAL_RMSE_REDUCTION,
    }
    p = b2m["chi_square_p_value"]
    if p >= ALPHA:
        verdict = "BATTERY B2 COMPLETE -- SOC CURVE ADEQUATE ON HELD-OUT DATA"
    elif reduction >= MATERIAL_RMSE_REDUCTION:
        verdict = "BATTERY B2 COMPLETE -- SOC CURVE IMPROVES BUT REMAINS INADEQUATE"
    elif not flexibility["structurally_identifiable"]:
        verdict = "BATTERY B2 BLOCKED -- DATA LIMIT UNDER THE BINDING SPLIT"
    else:
        verdict = "UNMAPPED -- the flexibility guard did not confirm the data limit; see SECONDARY.json"
    comparison["verdict"] = verdict
    comparison["verdict_rule"] = PREREG["verdict_mapping_fixed_now"]

    after = sha(evidence_file)
    for run in (primary, secondary_run):
        run.pop("_posterior_mean"); run.pop("_cov")
    results = {"primary": primary, "secondary": secondary_run, "observation_budgets": budgets,
               "preregistration_sha256": sha(ROUND / "PREREGISTRATION.json"),
               "b1_results_sha256": sha(B1_ROUND / "RESULTS.json"),
               "evidence_sha256_before": before, "evidence_sha256_after": after,
               "evidence_unchanged": before == after, "integrity_passed": integrity["passed"],
               "run_wall_seconds_informational": round(time.monotonic() - started, 1)}
    secondary = {"flexibility_guard": flexibility, "coefficient_sensitivity": sensitivity,
                 "residual_structure": structure, "hysteresis": hysteresis,
                 "empirical_adequacy_batt_001_held_out": empirical, "generalization_batt_002": generalization,
                 "cutoff_on_curve": cutoff}
    for name, payload in (("RESULTS.json", results), ("COMPARISON.json", comparison), ("SECONDARY.json", secondary)):
        (ROUND / name).write_bytes(json.dumps(payload, indent=2).encode("utf-8") + b"\n")

    print("same evidence as B1:", same_evidence)
    for run in (primary, secondary_run):
        m = run["metrics"]
        print(f"{run['label']}: {run['calibration']['status']} | {run['identifiability']['status']} | "
              f"RMSE {m['rmse_v']*1e3:.2f} MAE {m['mae_v']*1e3:.2f} max {m['max_abs_error_v']*1e3:.2f} mV | "
              f"coverage {m['coverage_95']} | chi2 {m['chi_square']:.4g} p {m['chi_square_p_value']:.3g}")
    print(f"RMSE reduction vs B1: {100*reduction:.2f} %")
    print("flexibility guard rank:", rank5, "of 5")
    print("VERDICT:", verdict)
    print("evidence unchanged:", before == after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
