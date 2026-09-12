"""Battery Flagship B1: the preregistered protocol, run on measured data.

    python -X utf8 benchmarks/battery_flagship_b1/audit/run_b1.py

Reads ``PREREGISTRATION.json`` and does exactly what it says, no more. Writes

    DATA_INTEGRITY.json   Phase 5 -- the raw traces, checked before anything is fitted
    RESULTS.json          Phases 6-13 -- split, calibration, identifiability, UQ,
                          held-out scores, the adequacy verdict
    SECONDARY.json        S1-S5 -- applicability boundary, residual structure,
                          relaxation time, hysteresis, current invariance

Nothing here is Core arithmetic. Calibration is ``engcore.inference.calibrate``,
the posterior ``gaussian_grid_posterior``, identifiability
``assess_identifiability``, predictive uncertainty
``engcore.uq.posterior_predictive_uq`` and per-observation adequacy
``engcore.adequacy.assess_predictive_observation`` -- all frozen, all
unmodified. Every forward value is an admitted prediction from the production
battery solver, through ``engcore.domains.battery.calibration``.

The raw measured file is opened read-only, and its SHA-256 is checked against
the preregistration before any value is read and again after the run.
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
ROUND = ROOT / "benchmarks" / "battery_flagship_b1"
PREREG = json.loads((ROUND / "PREREGISTRATION.json").read_text(encoding="utf-8"))

from engcore.adequacy import assess_predictive_observation  # noqa: E402
from engcore.domains.battery import calibration as bc  # noqa: E402
from engcore.domains.battery import cell as battery_cell  # noqa: E402
from engcore.domains.battery import context as ctx  # noqa: E402
from engcore.inference import (  # noqa: E402
    CalibrationSpec,
    GaussianObservation,
    GridResolutionError,
    NoiseModel,
    ObservationSet,
    ObservationSplit,
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
EVIDENCE_FILE = ROOT / PREREG["experiment"]["file"]
DOI = PREREG["experiment"]["dataset_doi"]
DISCHARGE_SHEET = "24h_Discharge_APR"
CHARGE_SHEET = "24h_Charge_APR"
TWIN = TwinReference(twin_id="battery.lfp.lithium_werks_apr18650.BATT_001", version="1")
ALPHA = 0.01
CREDIBLE = PREREG["uncertainty"]["credible_mass"]
GRID_N = 41
GRID_SPAN_SE = 6.0

FIXED = bc.FixedCellDeclaration(
    cell_id="BATT_001",
    nominal_capacity=Q(1.1, ctx.CAPACITY_UNIT),
    internal_resistance=Q(0.0126, ctx.RESISTANCE_UNIT),
    coulombic_efficiency=Q(1.0, ctx.DIMENSIONLESS),
    chemistry=ctx.LITHIUM_ION,
)
CELL_TEMPERATURE = Q(296.15, ctx.TEMPERATURE_UNIT)
CONDITIONING_CURRENT = Q(0.22, ctx.CURRENT_UNIT)


def _load_evidence_reader():
    """The previous round's reader, by path -- its package is also called ``audit``."""
    path = ROOT / "benchmarks" / "model_measurement_validation" / "audit" / "evidence.py"
    spec = importlib.util.spec_from_file_location("_mmv_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EV = _load_evidence_reader()


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def condition_id(z: float) -> str:
    return f"BATT_001.DCHG.SOC{int(round(z * 100)):03d}"


def rested_condition(z: float, current: Q = CONDITIONING_CURRENT) -> bc.RestedOcvCondition:
    return bc.RestedOcvCondition(
        condition_id=condition_id(z),
        target_state_of_charge=Q(z, ctx.DIMENSIONLESS),
        conditioning_current=current,
        cell_temperature=CELL_TEMPERATURE,
    )


# =====================================================================
# Phase 5 -- raw data integrity, before anything is fitted
# =====================================================================

LABEL = "BATT_001_OCV_V_{:02d}-SOC"
PUBLISHED_SOC = {
    DISCHARGE_SHEET: (0, 20, 40, 50, 60, 80),
    CHARGE_SHEET: (20, 40, 50, 60, 80, 100),
}
#: A single cell's terminal voltage outside this is not a LiFePO4 cell reading.
IMPOSSIBLE_V = (0.0, 5.0)
#: The cell's own published window: discharge cutoff and charge voltage.
PUBLISHED_WINDOW_V = (2.0, 3.6)


def integrity() -> dict:
    archive, strings, sheets = EV._open_workbook(EVIDENCE_FILE)
    report: dict = {"file": PREREG["experiment"]["file"], "sheets": {}}
    problems: list[str] = []
    for sheet in (DISCHARGE_SHEET, CHARGE_SHEET):
        rows = EV._sheet_rows(archive, strings, sheets, sheet)
        header = [rows[0].get(i) for i in range(len(rows[0]))]
        labels = header[1:]
        expected = [LABEL.format(s) if s < 100 else f"BATT_001_OCV_V_{s}-SOC"
                    for s in PUBLISHED_SOC[sheet]]
        body = rows[1:]
        times = [float(r[0]) for r in body if 0 in r]
        steps = np.diff(times)
        missing = sum(1 for r in body for c in range(1, len(header)) if c not in r)
        values = [float(r[c]) for r in body for c in range(1, len(header)) if c in r]
        finite = all(math.isfinite(v) for v in values) and all(math.isfinite(t) for t in times)
        impossible = [v for v in values if not IMPOSSIBLE_V[0] < v < IMPOSSIBLE_V[1]]
        outside_window = [v for v in values if not PUBLISHED_WINDOW_V[0] <= v <= PUBLISHED_WINDOW_V[1]]
        sheet_report = {
            "columns": labels,
            "labels_match_published_inventory": labels == expected,
            "duplicate_labels": sorted({l for l in labels if labels.count(l) > 1}),
            "rows": len(body),
            "timestamps_finite": all(math.isfinite(t) for t in times),
            "timestamps_strictly_increasing": bool(np.all(steps > 0)),
            "duplicate_timestamps": int(len(times) - len(set(times))),
            "first_timestamp_h": times[0],
            "last_timestamp_h": times[-1],
            "sampling_step_s_min_max": [float(steps.min() * 3600), float(steps.max() * 3600)],
            "missing_cells": missing,
            "all_values_finite": finite,
            "physically_impossible_values": len(impossible),
            "values_outside_published_window": len(outside_window),
            "voltage_range_v": [min(values), max(values)],
        }
        report["sheets"][sheet] = sheet_report
        if not sheet_report["labels_match_published_inventory"]:
            problems.append(f"{sheet}: column labels differ from the published inventory")
        if sheet_report["duplicate_labels"]:
            problems.append(f"{sheet}: repeated trace IDs")
        if not sheet_report["timestamps_strictly_increasing"] or sheet_report["duplicate_timestamps"]:
            problems.append(f"{sheet}: timestamps not strictly increasing")
        if missing:
            problems.append(f"{sheet}: {missing} missing samples")
        if not finite:
            problems.append(f"{sheet}: non-finite values")
        if impossible:
            problems.append(f"{sheet}: physically impossible voltages")
        if abs(times[-1] - 24.0) > 1e-9 or times[0] != 0.0:
            problems.append(f"{sheet}: the trace does not span 0-24 h")
    # metadata consistency, against the Header sheet
    header_rows = EV._sheet_rows(archive, strings, sheets, "Header")
    batt = next((r for r in header_rows if r.get(1) == "BATT_001"), {})
    metadata = {
        "chemistry": batt.get(2), "nominal_capacity_mAh": batt.get(6),
        "nominal_voltage_v": batt.get(7), "internal_resistance_mohm": batt.get(8),
        "relaxation_duration_h": batt.get(13),
    }
    consistent = (
        metadata["chemistry"] == "LiFePO4"
        and metadata["nominal_capacity_mAh"] == "1100"
        and metadata["internal_resistance_mohm"] == "12.6"
        and metadata["relaxation_duration_h"] == "24"
    )
    report["metadata"] = metadata
    report["metadata_consistent_with_fixed_declarations"] = consistent
    if not consistent:
        problems.append("Header metadata disagrees with the fixed declarations")
    report["transformations"] = [
        "none to the raw file; it is opened read-only",
        "the relaxed value of each trace is its sample at t = 24 h, as published",
    ]
    report["problems"] = problems
    report["passed"] = not problems
    return report


# =====================================================================
# observations, with the A2 rule for sigma
# =====================================================================

def traces(sheet: str) -> dict:
    return EV.relaxation_traces(sheet)


def observation(z: float, sheet_traces: dict, sigma_traces: dict) -> tuple[GaussianObservation, dict]:
    trace = sheet_traces[z]
    budget = EV.ocv_uncertainty(z, sigma_traces, trace["final_hour_drift_v"])
    return GaussianObservation(
        condition_id=condition_id(z),
        observable_name=bc.OCV_OBSERVABLE,
        value=Q(trace["relaxed_voltage_v"], VOLT),
        sigma=Q(budget["combined_standard_uncertainty_v"], VOLT),
        source_ref=f"S-OCV:doi:{DOI}:{DISCHARGE_SHEET}:{trace['label']}@24h",
    ), budget


def build_source(all_traces: dict, calibration_z, held_z, dataset_id: str):
    """Calibration sigma from calibration traces only; held-out sigma from the sheet (A2)."""
    calibration_traces = {z: all_traces[z] for z in calibration_z}
    items, budgets = [], {}
    for z in sorted(set(calibration_z) | set(held_z)):
        pool = calibration_traces if z in calibration_z else all_traces
        obs, budget = observation(z, all_traces, pool)
        items.append(obs)
        budgets[condition_id(z)] = {**budget, "sigma_computed_from": sorted(pool)}
    return ObservationSet(tuple(items), dataset_id=dataset_id), budgets


# =====================================================================
# one calibrate -> posterior -> predictive run
# =====================================================================

def wls_chord(observations: ObservationSet) -> dict:
    """Closed-form weighted least squares for the chord; the grid's independent centre."""
    z = np.asarray([float(o.condition_id[-3:]) / 100 for o in observations.observations])
    y = np.asarray([o.value.magnitude_in(VOLT) for o in observations.observations])
    s = np.asarray([o.sigma.magnitude_in(VOLT) for o in observations.observations])
    design = np.column_stack([1.0 - z, z]) / s[:, None]
    cov = np.linalg.inv(design.T @ design)
    beta = cov @ design.T @ (y / s)
    return {
        "open_circuit_voltage_at_empty": float(beta[0]),
        "open_circuit_voltage_at_full": float(beta[1]),
        "se": [float(math.sqrt(cov[0, 0])), float(math.sqrt(cov[1, 1]))],
        "correlation": float(cov[0, 1] / math.sqrt(cov[0, 0] * cov[1, 1])),
    }


def grid_for(centre: dict, span: float = GRID_SPAN_SE, n: int = GRID_N):
    axes = [
        np.linspace(centre[name] - span * se, centre[name] + span * se, n)
        for name, se in zip(bc.CHORD_PARAMETERS, centre["se"])
    ]
    return [(float(a), float(b)) for a in axes[0] for b in axes[1]], [
        [float(axes[0][0]), float(axes[0][-1])], [float(axes[1][0]), float(axes[1][-1])]
    ]


def run(source: ObservationSet, held_z, *, label: str, seed: int) -> dict:
    conditions = {condition_id(float(o.condition_id[-3:]) / 100): rested_condition(float(o.condition_id[-3:]) / 100)
                  for o in source.observations}
    split = ObservationSplit.partition(
        source=source,
        held_out_condition_ids=tuple(condition_id(z) for z in held_z),
        twin=TWIN,
        calibration_dataset_id=f"{source.dataset_id}.calibration",
        heldout_dataset_id=f"{source.dataset_id}.held_out",
    )
    cal_ids = {o.condition_id for o in split.calibration.observations}
    held_ids = {o.condition_id for o in split.held_out.observations}
    cal_digests = {observation_content_digest(o) for o in split.calibration.observations}
    held_digests = {observation_content_digest(o) for o in split.held_out.observations}
    split_record = {
        "calibration": sorted(cal_ids),
        "held_out": sorted(held_ids),
        "intersection_by_identity": sorted(cal_ids & held_ids),
        "intersection_by_material_content": sorted(cal_digests & held_digests),
        "calibration_dataset_id": split.calibration.dataset_id,
        "held_out_dataset_id": split.held_out.dataset_id,
    }

    params = bc.build_ocv_chord_parameter_set(
        lower=Q(PREREG["parameters"][0]["bounds"][0], VOLT),
        upper=Q(PREREG["parameters"][0]["bounds"][1], VOLT),
    )
    spec = CalibrationSpec(
        parameters=params,
        fixed={
            ctx.NOMINAL_CAPACITY: FIXED.nominal_capacity,
            ctx.INTERNAL_RESISTANCE: FIXED.internal_resistance,
            ctx.COULOMBIC_EFFICIENCY: FIXED.coulombic_efficiency,
            ctx.CELL_TEMPERATURE: CELL_TEMPERATURE,
            ctx.DISCHARGE_CURRENT: CONDITIONING_CURRENT,
        },
        initial_point={
            bc.CHORD_PARAMETERS[0]: Q(PREREG["parameters"][0]["initial_estimate"], VOLT),
            bc.CHORD_PARAMETERS[1]: Q(PREREG["parameters"][1]["initial_estimate"], VOLT),
        },
        noise_model=NoiseModel(),
    )
    counter: dict[str, int] = {}
    fit = calibrate(
        spec, split.calibration,
        bc.ocv_forward_evaluator(split.calibration, fixed=FIXED, conditions=conditions, counter=counter),
        heldout_dataset_id=split.heldout_dataset_id,
        max_evaluations=PREREG["calibration"]["max_evaluations"], seed=seed,
    )
    estimates = {e.identity.name: e.value.magnitude_in(VOLT) for e in fit.estimates}
    calibration_record = {
        "method": "engcore.inference.calibrate: bounded trust-region least squares on standardized residuals",
        "status": fit.status.value,
        "termination_reason": fit.termination_reason,
        "bounds_v": PREREG["parameters"][0]["bounds"],
        "initial_point_v": {n: spec.initial_point[n].magnitude_in(VOLT) for n in bc.CHORD_PARAMETERS},
        "optimizer_evaluations": fit.evaluation_count,
        "admitted_forward_predictions": counter.get("n", 0),
        "objective_chi_square": fit.objective_value,
        "calibration_degrees_of_freedom": len(split.calibration.observations) - 2,
        "wall_seconds_informational": round(fit.provenance.wall_seconds, 4),
        "estimates_v": estimates,
        "standardized_calibration_residuals": list(fit.residuals),
    }

    centre = wls_chord(split.calibration)
    posterior_record: dict = {"wls_oracle": centre}
    span = GRID_SPAN_SE
    for attempt in range(4):
        grid, ranges = grid_for(centre, span=span)
        table = bc.ocv_forward_table(split.calibration, grid, fixed=FIXED, conditions=conditions)
        posterior = gaussian_grid_posterior(table, split.calibration)
        diagnostics = posterior_grid_diagnostics(posterior)
        try:
            report = assess_identifiability(posterior)
            break
        except GridResolutionError as exc:
            posterior_record.setdefault("grid_refusals", []).append(
                {"span_se": span, "refusal": str(exc)[:300]})
            span /= 2.0
    posterior_record.update({
        "grid_points": len(grid),
        "grid_span_se": span,
        "grid_ranges_v": ranges,
        "rejected_rows": int(np.sum(~table.admissible_mask)),
        "posterior_mean_v": [float(v) for v in posterior.mean],
        "posterior_sd_v": [float(math.sqrt(posterior.covariance[i, i])) for i in range(2)],
        "posterior_correlation": float(posterior.correlation[0, 1]),
        "marginal_95_v": [list(map(float, posterior.marginal_interval(i, 0.95))) for i in range(2)],
        "diagnostics": {k: (v if not isinstance(v, (np.floating, float)) else float(v))
                        for k, v in diagnostics.items()},
    })
    identifiability = report.to_dict()

    predictive_table = bc.ocv_forward_table(split.held_out, grid, fixed=FIXED, conditions=conditions)
    held: list[dict] = []
    for obs in split.held_out.observations:
        spec_obs = PredictiveObservableSpec(obs.key, VOLT, obs.sigma)
        uq = posterior_predictive_uq(
            posterior, predictive_table, spec_obs, twin=TWIN, model=bc.RINT_MODEL_REF,
            source_ref=obs.source_ref, credible_mass=CREDIBLE,
        )
        assessment = assess_predictive_observation(
            posterior, predictive_table, spec_obs, obs.value, twin=TWIN, model=bc.RINT_MODEL_REF,
            source_ref=obs.source_ref, heldout_dataset_id=split.heldout_dataset_id,
            credible_mass=CREDIBLE,
        )
        observed = obs.value.magnitude_in(VOLT)
        mean = uq.mean.magnitude_in(VOLT)
        held.append({
            "condition_id": obs.condition_id,
            "state_of_charge": float(obs.condition_id[-3:]) / 100,
            "observed_v": observed,
            "predictive_mean_v": mean,
            "error_v": observed - mean,
            "parameter_standard_uncertainty_v": uq.epistemic_standard_uncertainty.magnitude_in(VOLT),
            "measurement_standard_uncertainty_v": obs.sigma.magnitude_in(VOLT),
            "total_standard_uncertainty_v": uq.total_standard_uncertainty.magnitude_in(VOLT),
            "parameter_interval_95_v": [uq.epistemic_interval.lower.magnitude_in(VOLT),
                                        uq.epistemic_interval.upper.magnitude_in(VOLT)],
            "total_interval_95_v": [uq.total_interval.lower.magnitude_in(VOLT),
                                    uq.total_interval.upper.magnitude_in(VOLT)],
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
    verdict = "inadequate_for_declared_study" if p_value < ALPHA else "adequate_for_declared_study"
    return {
        "label": label,
        "split": split_record,
        "calibration": calibration_record,
        "posterior": posterior_record,
        "identifiability": identifiability,
        "held_out": held,
        "metrics": {
            "n": len(held),
            "rmse_v": float(math.sqrt(np.mean(errors ** 2))),
            "mae_v": float(np.mean(np.abs(errors))),
            "max_abs_error_v": float(np.max(np.abs(errors))),
            "mean_log_predictive_density": float(np.mean([h["log_predictive_density"] for h in held])),
            "coverage_95": f"{covered}/{len(held)}",
            "chi_square": statistic,
            "chi_square_df": len(held),
            "chi_square_p_value": p_value,
            "alpha": ALPHA,
        },
        "uncertainty_sources": ["PARAMETER_UNCERTAINTY", "MEASUREMENT_UNCERTAINTY",
                                "MODEL_DISCREPANCY_NOT_MODELLED"],
        "model_discrepancy": "MODEL_DISCREPANCY_NOT_MODELLED",
        "adequacy_verdict": verdict,
        "_grid": grid,
        "_estimates": estimates,
        "_posterior_mean": [float(v) for v in posterior.mean],
    }


# =====================================================================
# secondary analyses
# =====================================================================

def relaxation(all_traces_raw: dict, budgets_full: dict) -> list[dict]:
    """S3: when does each rested trace stay inside its own expanded uncertainty of the 24 h value?"""
    archive, strings, sheets = EV._open_workbook(EVIDENCE_FILE)
    rows = EV._sheet_rows(archive, strings, sheets, DISCHARGE_SHEET)
    header = [rows[0].get(i) for i in range(len(rows[0]))]
    out = []
    for column, label in enumerate(header):
        if column == 0:
            continue
        z = int(label.split("_")[-1].split("-")[0]) / 100
        series = [(float(r[0]), float(r[column])) for r in rows[1:] if 0 in r and column in r]
        final = series[-1][1]
        u_expanded = budgets_full[condition_id(z)]["expanded_uncertainty_k2_v"]
        settled_from = None
        for index in range(len(series)):
            if all(abs(v - final) <= u_expanded for _, v in series[index:]):
                settled_from = series[index][0]
                break
        out.append({
            "state_of_charge": z,
            "voltage_at_0h_v": series[0][1],
            "voltage_at_24h_v": final,
            "recovery_over_24h_mv": (final - series[0][1]) * 1e3,
            "expanded_uncertainty_mv": u_expanded * 1e3,
            "within_expanded_uncertainty_of_24h_value_from_h": settled_from,
        })
    return sorted(out, key=lambda r: r["state_of_charge"])


def hysteresis(discharge: dict, charge: dict, budgets_full: dict) -> list[dict]:
    """S4: charge-branch minus discharge-branch relaxed OCV. An excluded effect, measured."""
    out = []
    for z in sorted(set(discharge) & set(charge)):
        delta = charge[z]["relaxed_voltage_v"] - discharge[z]["relaxed_voltage_v"]
        u = budgets_full[condition_id(z)]["expanded_uncertainty_k2_v"]
        out.append({"state_of_charge": z, "charge_minus_discharge_mv": delta * 1e3,
                    "discharge_expanded_uncertainty_mv": u * 1e3,
                    "exceeds_expanded_uncertainty": abs(delta) > u})
    return out


def applicability_assessment(estimates: dict, z: float) -> dict:
    """The model's OWN validity verdict on the calibrated cell, at one held-out point."""
    cell = FIXED.cell(ocv_at_empty=Q(estimates[bc.CHORD_PARAMETERS[0]], VOLT),
                      ocv_at_full=Q(estimates[bc.CHORD_PARAMETERS[1]], VOLT))
    load = rested_condition(z).load(FIXED)
    problem = battery_cell.build_battery_problem(cell, load)
    assessment = battery_cell.assess_rint_validity(
        problem, state_of_charge=Q(z, ctx.DIMENSIONLESS),
        discharge_current=CONDITIONING_CURRENT, cell_temperature=CELL_TEMPERATURE,
    )
    payload = assessment.to_dict()
    return {
        "state_of_charge": z,
        "status": payload.get("status"),
        "satisfied": payload.get("satisfied", []),
        "unknown": payload.get("unknown"),
        "violated": payload.get("violated", []),
    }


def main() -> int:
    before = sha(EVIDENCE_FILE)
    expected = PREREG["experiment"]["file_sha256"]
    if before != expected:
        raise SystemExit(f"evidence hash {before} is not the preregistered {expected}")

    started = time.monotonic()
    data = integrity()
    (ROUND / "DATA_INTEGRITY.json").write_bytes(json.dumps(data, indent=2).encode("utf-8") + b"\n")
    print("integrity:", "PASS" if data["passed"] else f"FAIL {data['problems']}")
    if not data["passed"]:
        return 2

    discharge = traces(DISCHARGE_SHEET)
    charge = traces(CHARGE_SHEET)
    cal_z = tuple(PREREG["split"]["calibration_state_of_charge"])
    held_z = tuple(PREREG["split"]["held_out_state_of_charge"])

    source, budgets = build_source(discharge, cal_z, held_z, "S-OCV.BATT_001.discharge")
    primary = run(source, held_z, label="PRIMARY", seed=PREREG["calibration"]["seed"])

    # S5: the held-out predictions, re-evaluated at 1C conditioning, must be identical.
    invariance = []
    for z in held_z:
        slow = bc.ocv_prediction(FIXED, rested_condition(z, Q(0.22, "ampere")),
                                 ocv_at_empty=Q(primary["_estimates"][bc.CHORD_PARAMETERS[0]], VOLT),
                                 ocv_at_full=Q(primary["_estimates"][bc.CHORD_PARAMETERS[1]], VOLT))
        fast = bc.ocv_prediction(FIXED, rested_condition(z, Q(1.1, "ampere")),
                                 ocv_at_empty=Q(primary["_estimates"][bc.CHORD_PARAMETERS[0]], VOLT),
                                 ocv_at_full=Q(primary["_estimates"][bc.CHORD_PARAMETERS[1]], VOLT))
        a = slow.value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)
        b = fast.value(bc.OCV_OBSERVABLE).magnitude_in(VOLT)
        invariance.append({"state_of_charge": z, "ocv_at_0.2C_v": a, "ocv_at_1C_v": b, "identical": a == b})

    # S1: plateau-core calibration, each outside point scored alone.
    s1_cal = (0.4, 0.5, 0.6)
    s1_rows = []
    for probe in (0.8, 0.2, 0.0):
        s1_source, _ = build_source(discharge, s1_cal, (probe,), f"S-OCV.BATT_001.discharge.S1.{int(probe*100):03d}")
        s1 = run(s1_source, (probe,), label=f"S1.{probe}", seed=PREREG["calibration"]["seed"])
        h = s1["held_out"][0]
        s1_rows.append({
            "calibrated_on": list(s1_cal), "scored_state_of_charge": probe,
            "identifiability": s1["identifiability"]["status"],
            "error_mv": h["error_v"] * 1e3, "total_standard_uncertainty_mv": h["total_standard_uncertainty_v"] * 1e3,
            "standardized_residual": h["standardized_residual"],
            "two_sided_tail_probability": h["two_sided_tail_probability"],
            "consistent_at_alpha_0.01": h["two_sided_tail_probability"] >= ALPHA,
            "covered_by_95_interval": h["covered_by_95_interval"],
        })

    # S2: residual structure against state of charge, all six, from the primary posterior mean.
    empty, full = primary["_posterior_mean"]
    structure = []
    for z in sorted(discharge):
        observed = discharge[z]["relaxed_voltage_v"]
        chord = empty + (full - empty) * z
        sigma_used = next(o.sigma.magnitude_in(VOLT) for o in source.observations if o.condition_id == condition_id(z))
        structure.append({"state_of_charge": z, "partition": "calibration" if z in cal_z else "held_out",
                          "observed_minus_chord_mv": (observed - chord) * 1e3,
                          "in_sigma": (observed - chord) / sigma_used})

    _, budgets_full = build_source(discharge, tuple(discharge), (), "S-OCV.BATT_001.discharge.full_budget")
    secondary = {
        "S1_applicability_boundary": s1_rows,
        "S2_residual_structure_vs_soc": structure,
        "S3_relaxation_time": relaxation(discharge, budgets_full),
        "S4_hysteresis_charge_minus_discharge": hysteresis(discharge, charge, budgets_full),
        "S5_conditioning_current_invariance": invariance,
        "applicability_assessment_of_calibrated_cell": [
            applicability_assessment(primary["_estimates"], z) for z in held_z
        ],
    }

    for key in ("_grid", "_estimates", "_posterior_mean"):
        primary.pop(key)
    primary["observation_budgets"] = budgets
    primary["preregistration_sha256"] = sha(ROUND / "PREREGISTRATION.json")
    primary["evidence_sha256_before"] = before
    after = sha(EVIDENCE_FILE)
    primary["evidence_sha256_after"] = after
    primary["evidence_unchanged"] = before == after
    primary["run_wall_seconds_informational"] = round(time.monotonic() - started, 1)

    (ROUND / "RESULTS.json").write_bytes(json.dumps(primary, indent=2).encode("utf-8") + b"\n")
    (ROUND / "SECONDARY.json").write_bytes(json.dumps(secondary, indent=2).encode("utf-8") + b"\n")

    m = primary["metrics"]
    print("calibration:", primary["calibration"]["status"], primary["calibration"]["estimates_v"])
    print("identifiability:", primary["identifiability"]["status"])
    print(f"held-out RMSE {m['rmse_v']*1e3:.2f} mV  MAE {m['mae_v']*1e3:.2f} mV  "
          f"max {m['max_abs_error_v']*1e3:.2f} mV  coverage {m['coverage_95']}  "
          f"chi2 {m['chi_square']:.4g} (df {m['chi_square_df']}) p {m['chi_square_p_value']:.3g}")
    print("VERDICT:", primary["adequacy_verdict"])
    print("evidence unchanged:", primary["evidence_unchanged"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
