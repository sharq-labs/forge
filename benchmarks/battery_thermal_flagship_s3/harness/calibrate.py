"""Fit the seven flagship parameters. CALIBRATION trajectories only.

The split is enforced here, not assumed: the fitter reads
``DATA_SELECTION.json``, keeps the calibration rows and refuses to start if any
validation or locked-holdout trajectory reached it.

The objective
-------------
Weighted least squares on the two measured channels, each residual divided by
the reviewed acceptance tolerance for its metric, so a millivolt of voltage and
a millikelvin of temperature enter on the scale the campaign says agreement is
measured on. That is a declared weighting and not an uncertainty claim: this
source states no instrument accuracy, so no residual here is normalized by one.

What comes out
--------------
A :class:`~engcore.scientific.corpus.calibration.CalibratedParameterSet`: the
values, their bounds, the objective, the dataset digest the fit saw, and a
standard error and identifiability verdict per parameter derived from the
Jacobian the optimizer ended on. It is inert. Nothing is promoted by running
this.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import march as mm  # noqa: E402
import prereg  # noqa: E402
from simulate import PARAMETER_ORDER, REFERENCE_TEMPERATURE_K  # noqa: E402

#: Residual weights: one over the reviewed acceptance tolerance of each metric.
VOLTAGE_SCALE_V = prereg.ACCEPTANCE["terminal_voltage"]["per_sample_tolerance_v"]
TEMPERATURE_SCALE_K = prereg.ACCEPTANCE["cell_temperature"]["per_sample_tolerance_k"]

#: A trajectory the march stops early on contributes the residuals it produced
#: and a penalty for the samples it could not reach, so a parameter set that
#: buys a low objective by refusing most of the data does not win. The penalty
#: is one acceptance tolerance per unreached sample -- the same scale as a
#: residual exactly at the edge of agreement.
UNREACHED_PENALTY = 1.0


def load_calibration() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with open(os.path.join(EVIDENCE, "DATA_SELECTION.json"), encoding="utf-8") as fh:
        selection = json.load(fh)
    with open(
        os.path.join(EVIDENCE, "selected_trajectories.json"), encoding="utf-8"
    ) as fh:
        vendored = json.load(fh)
    by_id = {item["trajectory_id"]: item for item in vendored["trajectories"]}

    rows: list[dict[str, Any]] = []
    for item in selection["selected"]:
        if item["split"] != "calibration":
            continue
        if item["applicability"] != "inside":
            raise SystemExit(
                "a calibration trajectory is declared outside applicability; "
                "fitting on a case the model is not claimed for would make the "
                "declaration decorative"
            )
        trajectory = by_id[item["trajectory_id"]]
        channels = trajectory["channels"]
        rows.append(
            {
                "trajectory_id": item["trajectory_id"],
                "cell": item["cell"],
                "group": item["group"],
                "times_s": channels["time_s"],
                "currents_a": [-x for x in channels["current_a"]],
                "voltage_v": channels["voltage_v"],
                "temperature_k": [x + 273.15 for x in channels["temperature_c"]],
                "ambient_k": item["ambient_temperature_c"] + 273.15,
                "admit_temperature": bool(item["admit_cell_temperature"]),
            }
        )
    if not rows:
        raise SystemExit("no calibration trajectory was selected")
    splits = {item["split"] for item in selection["selected"]}
    if not {"validation", "locked_holdout"} <= splits:
        raise SystemExit(
            "the selection has no independent splits; a fit with nothing held "
            "back is not a fit this campaign can report"
        )
    return rows, selection


def residuals(vector, rows) -> np.ndarray:
    """Weighted residuals over the samples the model is claimed at.

    A sample below the declared charge-state floor contributes nothing: the
    flagship does not claim that region, and fitting to residuals there would
    tune the model on evidence about a place it says it does not go.
    """
    r0, ea0, r1, ea1, c1, c_th, ha = (float(x) for x in vector)
    floor = prereg.APPLICABILITY_CHARGE_STATE_FLOOR
    out: list[float] = []
    for row in rows:
        try:
            _instants, voltage, temperature, charge, stopped = mm.march(
                times_s=row["times_s"],
                currents_a=row["currents_a"],
                ambient_k=row["ambient_k"],
                initial_temperature_k=row["temperature_k"][0],
                r0_ref=r0,
                ea0=ea0,
                r1_ref=r1,
                ea1=ea1,
                c1=c1,
                c_th=c_th,
                ha=ha,
                reference_temperature_k=REFERENCE_TEMPERATURE_K,
            )
        except (ValueError, OverflowError):
            # A parameter set the march cannot evaluate at all is not scored as
            # a very bad fit with made-up residuals; every claimed sample takes
            # the unreached penalty, which is finite, ordered and says why.
            count = row["claimed_samples"]
            out.extend([UNREACHED_PENALTY] * count)
            if row["admit_temperature"]:
                out.extend([UNREACHED_PENALTY] * count)
            continue
        reached = len(voltage)
        measured_v = row["voltage_v"][1 : reached + 1]
        measured_t = row["temperature_k"][1 : reached + 1]
        claimed = 0
        for index in range(reached):
            if charge[index] < floor:
                continue
            claimed += 1
            out.append((voltage[index] - measured_v[index]) / VOLTAGE_SCALE_V)
            if row["admit_temperature"]:
                out.append(
                    (temperature[index] - measured_t[index]) / TEMPERATURE_SCALE_K
                )
        missing = row["claimed_samples"] - claimed
        if missing > 0:
            out.extend([UNREACHED_PENALTY] * missing)
            if row["admit_temperature"]:
                out.extend([UNREACHED_PENALTY] * missing)
    return np.asarray(out, dtype=float)


def claimed_sample_count(row) -> int:
    """How many of a trajectory's instants sit at or above the declared floor.

    Computed from the measured current alone -- the charge state is the
    integrated measurement, so this is a property of the trajectory and not of
    any parameter value. It fixes the residual vector's length, which a
    least-squares call requires to be constant.
    """
    floor = prereg.APPLICABILITY_CHARGE_STATE_FLOOR
    basis = mm.CHARGE_STATE_BASIS_AH
    times = row["times_s"]
    currents = row["currents_a"]
    charge = 0.0
    count = 0
    for index in range(1, len(times)):
        dt_h = (float(times[index]) - float(times[index - 1])) / 3600.0
        charge += float(currents[index - 1]) * dt_h
        if 1.0 - charge / basis >= floor:
            count += 1
    return count


def identifiability(jacobian: np.ndarray, residual: np.ndarray, names, values):
    """Standard errors and a verdict per parameter, from the fit's own Jacobian.

    ``UNKNOWN`` where the normal matrix is singular: a parameter the data did
    not constrain gets no error bar and no claim, which is the honest outcome
    and the one the corpus record enforces by refusing an identifiability claim
    with no diagnostic behind it.
    """
    n, p = jacobian.shape
    dof = max(n - p, 1)
    sigma_squared = float(residual @ residual) / dof
    normal = jacobian.T @ jacobian
    singular = np.linalg.svd(normal, compute_uv=False)
    condition = (
        float(singular[0] / singular[-1]) if singular[-1] > 0 else math.inf
    )
    try:
        covariance = np.linalg.inv(normal) * sigma_squared
    except np.linalg.LinAlgError:
        return (
            {name: None for name in names},
            {name: "unknown" for name in names},
            condition,
            sigma_squared,
        )
    errors: dict[str, float | None] = {}
    verdicts: dict[str, str] = {}
    for index, name in enumerate(names):
        variance = float(covariance[index, index])
        if not math.isfinite(variance) or variance < 0.0:
            errors[name] = None
            verdicts[name] = "unknown"
            continue
        error = math.sqrt(variance)
        errors[name] = error
        value = abs(float(values[index]))
        relative = error / value if value > 0 else math.inf
        # The thresholds are a declared reading of the diagnostic, not a
        # measurement: a parameter whose standard error is under a tenth of its
        # own value is called identified, one over half is called unidentified,
        # and the band between them is weak.
        if relative <= 0.1:
            verdicts[name] = "identified"
        elif relative <= 0.5:
            verdicts[name] = "weak"
        else:
            verdicts[name] = "unidentified"
    return errors, verdicts, condition, sigma_squared


def fit_group(group: str, rows, specs, names) -> dict[str, Any]:
    for row in rows:
        row["claimed_samples"] = claimed_sample_count(row)
    x0 = np.array([specs[name]["initial"] for name in names], dtype=float)
    lower = np.array([specs[name]["lower"] for name in names], dtype=float)
    upper = np.array([specs[name]["upper"] for name in names], dtype=float)

    started = time.perf_counter()
    result = least_squares(
        residuals,
        x0,
        bounds=(lower, upper),
        args=(rows,),
        method="trf",
        x_scale="jac",
        ftol=1e-12,
        xtol=1e-12,
        gtol=1e-12,
        max_nfev=6000,
    )
    elapsed = time.perf_counter() - started
    errors, verdicts, condition, sigma_squared = identifiability(
        result.jac, result.fun, names, result.x
    )
    fitted = {name: float(value) for name, value in zip(names, result.x)}
    residual_count = int(result.fun.size)
    objective = float(0.5 * float(result.fun @ result.fun))
    at_bound = sorted(
        name
        for index, name in enumerate(names)
        if abs(result.x[index] - lower[index]) <= 1e-9 * max(1.0, abs(lower[index]))
        or abs(result.x[index] - upper[index]) <= 1e-9 * max(1.0, abs(upper[index]))
    )
    return {
        "group": group,
        "trajectories": [row["trajectory_id"] for row in rows],
        "cells": sorted({row["cell"] for row in rows}),
        "temperature_admitted_for": sorted(
            {row["cell"] for row in rows if row["admit_temperature"]}
        ),
        "claimed_samples": sum(row["claimed_samples"] for row in rows),
        "fitted": fitted,
        "standard_errors": errors,
        "identifiability": verdicts,
        "at_declared_bound": at_bound,
        "objective_value": objective,
        "residuals": residual_count,
        "reduced_objective": objective / max(residual_count - len(names), 1),
        "optimizer": {
            "method": "trf",
            "status": int(result.status),
            "message": str(result.message),
            "function_evaluations": int(result.nfev),
            "wall_seconds": elapsed,
            "initial_point": {name: float(v) for name, v in zip(names, x0)},
        },
        "normal_matrix_condition_number": condition,
        "residual_variance": sigma_squared,
    }


def main() -> int:
    rows, selection = load_calibration()
    specs = {item["parameter_id"]: item for item in prereg.FITTED_PARAMETERS}
    names = list(PARAMETER_ORDER)
    missing = sorted(set(names) - set(specs))
    if missing:
        raise SystemExit(f"parameters with no preregistered spec: {missing}")

    claimable = set(selection["groups_without_independent_cells"])
    by_group: dict[str, list] = {}
    for row in rows:
        by_group.setdefault(row["group"], []).append(row)

    fits: list[dict[str, Any]] = []
    for group in sorted(by_group):
        record = fit_group(group, by_group[group], specs, names)
        record["produces_a_claim"] = group not in claimable
        record["why_no_claim"] = (
            ""
            if record["produces_a_claim"]
            else (
                "this experiment group has no validation or locked-holdout cell, "
                "so its parameter set is never applied to independent evidence "
                "and supports no flagship claim"
            )
        )
        fits.append(record)
        print(
            f"{group:14} cells={','.join(record['cells']):20} "
            f"objective {record['objective_value']:12.4g} over "
            f"{record['residuals']:6d} residuals  "
            f"{'CLAIM' if record['produces_a_claim'] else 'calibration only'}",
            file=sys.stderr,
        )
        for name in names:
            error = record["standard_errors"][name]
            print(
                f"    {name:38} {record['fitted'][name]:14.6g}  "
                f"+/- {('%.3g' % error) if error is not None else 'n/a':>10}  "
                f"{record['identifiability'][name]}",
                file=sys.stderr,
            )

    record = {
        "schema": "battery_thermal_flagship_s3_calibration/2",
        "campaign_id": prereg.CAMPAIGN_ID,
        "campaign_version": prereg.CAMPAIGN_VERSION,
        "split": "calibration",
        "parameter_unit": "one experiment group",
        "applicability_charge_state_floor": (
            prereg.APPLICABILITY_CHARGE_STATE_FLOOR
        ),
        "objective": {
            "objective_id": "battery_electrothermal.weighted_least_squares",
            "version": "2",
            "description": (
                "sum of squared residuals on measured terminal voltage and "
                "measured cell temperature at every instant at or above the "
                "declared charge-state floor, each divided by the reviewed "
                "acceptance tolerance for its metric; an instant the march "
                f"could not reach takes a penalty of {UNREACHED_PENALTY} on the "
                "same scale"
            ),
            "voltage_scale_v": VOLTAGE_SCALE_V,
            "temperature_scale_k": TEMPERATURE_SCALE_K,
        },
        "groups": fits,
        "identifiability_rule": (
            "standard error under a tenth of the value is identified, under a "
            "half is weak, above is unidentified; no diagnostic at all is "
            "unknown"
        ),
        "fixed": prereg.FIXED_PARAMETERS,
        "what_this_is_not": (
            "not a promotion. This record changes no production authority; the "
            "flagship run is given these values as external inputs and says so "
            "in its own provenance"
        ),
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    out = os.path.join(EVIDENCE, "CALIBRATION.json")
    with open(out, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")
    print(f"\nwrote {out}: {len(fits)} group parameter sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
