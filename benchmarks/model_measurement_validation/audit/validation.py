"""MV-16: the comparisons, exactly as METRIC_PLAN.json preregistered them.

Each case produces rows carrying the measurement, its uncertainty, the Core's
prediction, the residual, the preregistered tolerance and a verdict. Nothing in
this file chooses a tolerance; every threshold is read from the plan or derived
by the rule the plan states.
"""

from __future__ import annotations

import json
import math

from . import evidence as E
from . import production as P

APR = {"capacity_mah": 1100.0, "resistance_mohm": 12.6, "cell": "BATT_001 (APR, Lithium Werks, LiFePO4)"}
BSE = {"capacity_mah": 1500.0, "resistance_mohm": 35.0, "cell": "BATT_002 (BSE, LiFePO4)"}

LEVEL_2 = "LEVEL 2 published experimental dataset"
LEVEL_3 = "LEVEL 3 standards-body reference"


def _traces(sheet):
    return E.relaxation_traces(sheet)


def _uncertainty(soc, traces):
    return E.ocv_uncertainty(soc, traces, traces[soc]["final_hour_drift_v"])


# =====================================================================
# MV-A: the affine chord against measured open-circuit voltage
# =====================================================================


def case_a(charge_sheet="24h_Charge_APR", discharge_sheet="24h_Discharge_APR",
           metadata=APR, case_id="MV-A") -> dict:
    charge = _traces(charge_sheet)
    discharge = _traces(discharge_sheet)
    if 1.0 not in charge or 0.0 not in discharge:
        raise ValueError(f"{case_id}: this cell has no 100% or 0% conditioning level")

    full = charge[1.0]["relaxed_voltage_v"]
    empty = discharge[0.0]["relaxed_voltage_v"]
    cell = P.cell_with_chord(
        ocv_full_v=full, ocv_empty_v=empty,
        capacity_mah=metadata["capacity_mah"], resistance_mohm=metadata["resistance_mohm"],
    )

    rows = []
    for conditioning, traces, excluded in (
        ("charge", charge, 1.0),
        ("discharge", discharge, 0.0),
    ):
        for soc in sorted(traces):
            calibration = soc == excluded
            measured = traces[soc]["relaxed_voltage_v"]
            unc = _uncertainty(soc, traces)
            predicted = P.open_circuit_voltage(cell, soc)
            residual = predicted - measured
            rows.append({
                "case": case_id,
                "model": "battery.cell.rint_ocv",
                "configuration": "affine chord",
                "source_id": "S-OCV",
                "evidence_level": LEVEL_2,
                "cell": metadata["cell"],
                "split": "CALIBRATION" if calibration else "HELD_OUT",
                "inputs": {"state_of_charge": soc, "conditioning": conditioning},
                "measured_v": measured,
                "relaxed_at_hours": traces[soc]["relaxed_at_hours"],
                "declared_relaxation_hours": traces[soc]["declared_relaxation_hours"],
                "expanded_uncertainty_k2_v": unc["expanded_uncertainty_k2_v"],
                "uncertainty_budget": unc,
                "core_v": predicted,
                "residual_v": residual,
                "tolerance_v": unc["expanded_uncertainty_k2_v"],
                # A calibration point carries no verdict. Its residual is zero
                # by construction -- it IS the parameter -- and letting it read
                # as a pass would put two free wins into every summary.
                "within_tolerance": (
                    None if calibration
                    else abs(residual) <= unc["expanded_uncertainty_k2_v"]
                ),
                "applicability": "IN_SCOPE",
            })

    held = [r for r in rows if r["split"] == "HELD_OUT"]
    return {
        "case_id": case_id,
        "rows": rows,
        "declared_endpoints": {"ocv_at_empty_v": empty, "ocv_at_full_v": full},
        "summary": _summary(held),
        "hysteresis_v": _hysteresis(charge, discharge),
    }


def _hysteresis(charge, discharge) -> dict:
    """The measured size of an effect the model excludes.

    Reported rather than folded into the residual: a model that declares it
    does not represent hysteresis should be told how much hysteresis there was.
    """
    shared = sorted(set(charge) & set(discharge))
    gaps = {
        soc: charge[soc]["relaxed_voltage_v"] - discharge[soc]["relaxed_voltage_v"]
        for soc in shared
    }
    return {
        "states_of_charge_measured_both_ways": shared,
        "charge_minus_discharge_v": gaps,
        "max_abs_v": max((abs(v) for v in gaps.values()), default=0.0),
    }


def _summary(rows) -> dict:
    if not rows:
        return {"n": 0}
    residuals = [r["residual_v"] for r in rows]
    absolute = [abs(v) for v in residuals]
    return {
        "n": len(rows),
        "mean_absolute_error_v": sum(absolute) / len(absolute),
        "root_mean_square_error_v": math.sqrt(sum(v * v for v in residuals) / len(residuals)),
        "max_absolute_error_v": max(absolute),
        "mean_signed_residual_v": sum(residuals) / len(residuals),
        "fraction_within_uncertainty": sum(1 for r in rows if r["within_tolerance"]) / len(rows),
        "worst_residual_in_units_of_its_own_uncertainty": max(
            abs(r["residual_v"]) / r["expanded_uncertainty_k2_v"] for r in rows
        ),
    }


# =====================================================================
# MV-B: a declared measured curve, held-out states of charge
# =====================================================================

CURVE_CALIBRATION = (0.0, 0.2, 0.5, 0.8, 1.0)
CURVE_HELD_OUT = (0.4, 0.6)


def case_b() -> dict:
    charge = _traces("24h_Charge_APR")
    discharge = _traces("24h_Discharge_APR")

    samples = []
    for soc in CURVE_CALIBRATION:
        source = charge if soc in charge else discharge
        samples.append((soc, source[soc]["relaxed_voltage_v"]))

    cell = P.cell_with_curve(
        samples=samples,
        capacity_mah=APR["capacity_mah"],
        resistance_mohm=APR["resistance_mohm"],
        source="S-OCV, DOI 10.21227/651q-8v82, APR/BATT_001, relaxed values at 24 h",
    )

    curvature = _second_divided_differences(samples)
    # The calibration samples are emitted as rows too. They carry no verdict --
    # a point that set a parameter cannot also score it -- but leaving them out
    # would make the published counts disagree with the preregistered split,
    # and an accounting that does not reconcile is where leakage hides.
    rows = []
    for soc, voltage in samples:
        origin = charge if soc in charge else discharge
        rows.append({
            "case": "MV-B",
            "model": "battery.cell.rint_ocv",
            "configuration": "declared measured curve, TabulatedForm, linear interpolation",
            "source_id": "S-OCV",
            "evidence_level": LEVEL_2,
            "cell": APR["cell"],
            "split": "CALIBRATION",
            "inputs": {"state_of_charge": soc,
                       "conditioning": "charge" if soc in charge else "discharge"},
            "measured_v": voltage,
            "relaxed_at_hours": origin[soc]["relaxed_at_hours"],
            "declared_relaxation_hours": origin[soc]["declared_relaxation_hours"],
            "expanded_uncertainty_k2_v": _uncertainty(soc, origin)["expanded_uncertainty_k2_v"],
            "core_v": None,
            "residual_v": None,
            "tolerance_v": None,
            "within_tolerance": None,
            "applicability": "IN_SCOPE",
            "role": "one sample of the declared open-circuit-voltage curve",
        })
    for soc in CURVE_HELD_OUT:
        measured = charge[soc]["relaxed_voltage_v"]
        unc = _uncertainty(soc, charge)
        predicted = P.open_circuit_voltage(cell, soc)
        residual = predicted - measured
        lower, upper = _bracket(soc, [s for s, _ in samples])
        width = upper - lower
        local_curvature = _local_curvature(curvature, lower, upper)
        interpolation_bound = width * width * local_curvature / 8.0
        tolerance = unc["expanded_uncertainty_k2_v"] + interpolation_bound
        rows.append({
            "case": "MV-B",
            "model": "battery.cell.rint_ocv",
            "configuration": "declared measured curve, TabulatedForm, linear interpolation",
            "source_id": "S-OCV",
            "evidence_level": LEVEL_2,
            "cell": APR["cell"],
            "split": "HELD_OUT",
            "inputs": {"state_of_charge": soc, "conditioning": "charge"},
            "measured_v": measured,
            "relaxed_at_hours": charge[soc]["relaxed_at_hours"],
            "declared_relaxation_hours": charge[soc]["declared_relaxation_hours"],
            "expanded_uncertainty_k2_v": unc["expanded_uncertainty_k2_v"],
            "core_v": predicted,
            "residual_v": residual,
            "bracketing_interval": [lower, upper],
            "curvature_from_calibration_samples": local_curvature,
            "interpolation_bound_v": interpolation_bound,
            "tolerance_v": tolerance,
            "within_tolerance": abs(residual) <= tolerance,
            "applicability": "IN_SCOPE",
            "diagnostic_curvature_implied_by_the_residual": (
                8.0 * abs(residual) / (width * width) if width else None
            ),
        })
    return {
        "case_id": "MV-B",
        "rows": rows,
        "calibration_samples": samples,
        "summary": _summary([r for r in rows if r["split"] == "HELD_OUT"]),
    }


def _bracket(value, nodes):
    ordered = sorted(nodes)
    for lower, upper in zip(ordered, ordered[1:]):
        if lower <= value <= upper:
            return lower, upper
    raise ValueError(f"{value} is outside the declared samples")


def _second_divided_differences(samples):
    ordered = sorted(samples)
    out = {}
    for i in range(len(ordered) - 2):
        (x0, y0), (x1, y1), (x2, y2) = ordered[i:i + 3]
        first_a = (y1 - y0) / (x1 - x0)
        first_b = (y2 - y1) / (x2 - x1)
        out[(x0, x1, x2)] = 2.0 * abs((first_b - first_a) / (x2 - x0))
    return out


def _local_curvature(curvature, lower, upper):
    """The largest curvature any calibration triple spanning this gap reveals."""
    relevant = [
        value for triple, value in curvature.items()
        if lower in triple and upper in triple
    ]
    return max(relevant) if relevant else max(curvature.values(), default=0.0)


# =====================================================================
# MV-C: the linear law against the platinum reference table
# =====================================================================

R0_OHM = 100.0
COEFFICIENT_A = 3.9083e-3
COEFFICIENT_B = -5.775e-7
SCORED_LOW_C = 30
SCORED_HIGH_C = 400
TABLE_QUANTISATION_OHM = 0.005
RATIO_TOLERANCE = 0.05


def case_c() -> dict:
    table = E.platinum_table()
    corroboration = _corroborate_table(table)
    # R0 is the single calibration point: the standard's nominal 100 ohm, which
    # is also the table's own entry at the ice point. Emitted so the published
    # counts reconcile with the preregistered split.
    rows = [{
        "case": "MV-C",
        "model": "electrical.material.linear_tcr_resistance",
        "source_id": "S-PT100",
        "evidence_level": LEVEL_3,
        "split": "CALIBRATION",
        "inputs": {"temperature_degC": 0, "role": "R0"},
        "measured_ohm": table[0],
        "expanded_uncertainty_k2_ohm": TABLE_QUANTISATION_OHM,
        "core_ohm": None,
        "residual_ohm": None,
        "within_tolerance": None,
        "applicability": "PARTIALLY_IN_SCOPE",
    }]
    for celsius in sorted(table):
        if celsius == 0:
            continue  # emitted above as the calibration row
        reference = table[celsius]
        predicted = P.resistance_at(
            r0_ohm=R0_OHM, alpha_per_k=COEFFICIENT_A,
            reference_celsius=0.0, celsius=float(celsius),
        )
        residual = predicted - reference
        scored = SCORED_LOW_C <= celsius <= SCORED_HIGH_C
        row = {
            "case": "MV-C",
            "model": "electrical.material.linear_tcr_resistance",
            "source_id": "S-PT100",
            "evidence_level": LEVEL_3,
            "split": "VALIDATION" if scored else "HELD_OUT",
            "inputs": {"temperature_degC": celsius},
            "measured_ohm": reference,
            "expanded_uncertainty_k2_ohm": TABLE_QUANTISATION_OHM,
            "core_ohm": predicted,
            "residual_ohm": residual,
            "equivalent_temperature_error_degC": residual / (R0_OHM * COEFFICIENT_A),
            "applicability": "PARTIALLY_IN_SCOPE",
        }
        if scored:
            observed = residual / reference
            predicted_term = (
                abs(COEFFICIENT_B) * celsius * celsius
                / (1.0 + COEFFICIENT_A * celsius)
            )
            ratio = observed / predicted_term
            row |= {
                "observed_relative_deviation": observed,
                "predicted_omitted_term": predicted_term,
                "ratio": ratio,
                "metric": "|ratio - 1|",
                "value": abs(ratio - 1.0),
                "tolerance": RATIO_TOLERANCE,
                "within_tolerance": abs(ratio - 1.0) <= RATIO_TOLERANCE,
            }
        rows.append(row)

    scored_rows = [r for r in rows if r["split"] == "VALIDATION"]
    return {
        "case_id": "MV-C",
        "rows": rows,
        "table_corroboration": corroboration,
        "summary": {
            "n_scored": len(scored_rows),
            "n_reported_unscored": len(rows) - len(scored_rows),
            "max_metric": max(r["value"] for r in scored_rows),
            "mean_metric": sum(r["value"] for r in scored_rows) / len(scored_rows),
            "all_within_tolerance": all(r["within_tolerance"] for r in scored_rows),
            "max_absolute_residual_ohm_over_whole_table": max(
                abs(r["residual_ohm"]) for r in rows if r["residual_ohm"] is not None
            ),
        },
        "usable_interval": _usable_interval(rows),
        "secondary_analysis_after_the_audit_defect": _secondary(rows, corroboration),
    }


def _secondary(rows, corroboration) -> dict:
    """The same rule, on the interval the reference data can actually support.

    The preregistered rule and its result stand above, unedited. This is a
    separate, labelled analysis, and it exists because the scored interval's
    lower bound was derived from the table's STATED quantisation of +/-0.005
    ohm before the table had been parsed. Its measured scatter is about three
    times that, so the ratio metric cannot discriminate at 5 percent until the
    predicted term is correspondingly larger. The lower bound is recomputed
    here from the measured scatter by the same rule the plan used.
    """
    scatter = corroboration["measured_scatter_against_the_best_fit_quadratic_ohm"]
    supported = {}
    for low in (30, 40, 50, 60, 75, 100):
        selected = [
            r for r in rows
            if r["split"] == "VALIDATION" and r["inputs"]["temperature_degC"] >= low
        ]
        if not selected:
            continue
        supported[str(low)] = {
            "n": len(selected),
            "max_metric": max(r["value"] for r in selected),
            "passes_at_5_percent": max(r["value"] for r in selected) <= RATIO_TOLERANCE,
        }
    return {
        "why_this_exists": (
            "AUDIT_DEFECT MVA-2. The preregistered lower bound of 30 degC was "
            "set from the table's stated quantisation. Its measured scatter is "
            f"{scatter:.4f} ohm, and at 30 degC that is 29 percent of the "
            "predicted omitted term, so a 5 percent rule there is measuring "
            "the reference data rather than the model."
        ),
        "measured_scatter_ohm": scatter,
        "by_lower_bound": supported,
        "the_rule_is_unchanged": "the 5 percent tolerance is the preregistered one; only the interval the reference data can support is recomputed",
    }


def _fit_quadratic(table, low=0, high=850):
    """Least squares for R = 100 (1 + a t + b t^2) over the positive branch.

    A diagnostic, not evidence. It answers one question: which coefficients is
    this transcription actually built from? If the answer is the pair the
    previous round recited from an unrelated source, the recitation is
    corroborated by a document it never saw.
    """
    normal = [[0.0, 0.0], [0.0, 0.0]]
    right = [0.0, 0.0]
    for celsius in range(low, high + 1):
        y = table[celsius] - 100.0
        basis = [celsius, celsius * celsius]
        for i in range(2):
            right[i] += basis[i] * y
            for j in range(2):
                normal[i][j] += basis[i] * basis[j]
    determinant = normal[0][0] * normal[1][1] - normal[0][1] * normal[1][0]
    a = (right[0] * normal[1][1] - normal[0][1] * right[1]) / determinant
    b = (normal[0][0] * right[1] - right[0] * normal[1][0]) / determinant
    return a / 100.0, b / 100.0


def _corroborate_table(table) -> dict:
    """Is the transcription what it says it is, before anything is built on it?

    Three checks that do not depend on one another.

    The first is the three anchor values the file's own comments document.

    The second fits the Callendar-Van Dusen coefficients to the table and
    compares them against the pair the previous round recited from a different
    source. This is the check that matters: two artifacts that never saw each
    other agreeing on A and B is corroboration of both.

    The third measures how far the table departs from ANY quadratic. That
    number is the reference data's real noise floor, and it turns out to be
    about three times the +/-0.005 ohm its own 0.01 ohm resolution implies -
    which is a defect in the reference data, discovered here, and the reason
    the preregistered scored interval was set too low.
    """
    anchors = {-200: 18.52, 0: 100.00, 100: 138.51}
    anchor_ok = {c: table[c] == v for c, v in anchors.items()}

    fitted_a, fitted_b = _fit_quadratic(table)
    coefficient_agreement = {
        "fitted_A_per_degC": fitted_a,
        "recited_A_per_degC": COEFFICIENT_A,
        "relative_difference_A": abs(fitted_a - COEFFICIENT_A) / abs(COEFFICIENT_A),
        "fitted_B_per_degC2": fitted_b,
        "recited_B_per_degC2": COEFFICIENT_B,
        "relative_difference_B": abs(fitted_b - COEFFICIENT_B) / abs(COEFFICIENT_B),
    }

    worst_against_recited = 0.0
    worst_recited_at = None
    worst_against_fitted = 0.0
    worst_fitted_at = None
    for celsius in range(0, 851):
        recited = R0_OHM * (
            1.0 + COEFFICIENT_A * celsius + COEFFICIENT_B * celsius * celsius
        )
        fitted = R0_OHM * (1.0 + fitted_a * celsius + fitted_b * celsius * celsius)
        d_recited = abs(table[celsius] - recited)
        d_fitted = abs(table[celsius] - fitted)
        if d_recited > worst_against_recited:
            worst_against_recited, worst_recited_at = d_recited, celsius
        if d_fitted > worst_against_fitted:
            worst_against_fitted, worst_fitted_at = d_fitted, celsius

    # The pre-1995 DIN 43760 pair, ruled out so that "some other edition"
    # is not left as an unexamined explanation for the scatter.
    old_a, old_b = 3.90802e-3, -5.802e-7
    worst_old = max(
        abs(table[c] - R0_OHM * (1.0 + old_a * c + old_b * c * c))
        for c in range(0, 851)
    )

    coefficients_agree = (
        coefficient_agreement["relative_difference_A"] < 1e-4
        and coefficient_agreement["relative_difference_B"] < 1e-4
    )
    return {
        "anchor_values_present": anchor_ok,
        "all_anchors_match": all(anchor_ok.values()),
        "coefficient_agreement": coefficient_agreement,
        "coefficients_agree_with_the_previous_round_recitation": coefficients_agree,
        "pre_1995_din_43760_pair_ruled_out": {
            "A": old_a, "B": old_b, "worst_departure_ohm": worst_old,
        },
        "worst_departure_from_the_recited_relation_ohm": worst_against_recited,
        "worst_departure_from_the_recited_relation_at_degC": worst_recited_at,
        "measured_scatter_against_the_best_fit_quadratic_ohm": worst_against_fitted,
        "measured_scatter_at_degC": worst_fitted_at,
        "nominal_quantisation_ohm": TABLE_QUANTISATION_OHM,
        "scatter_in_units_of_the_nominal_quantisation": (
            worst_against_fitted / TABLE_QUANTISATION_OHM
        ),
        "verdict": (
            "TRANSCRIPTION_CORROBORATES_THE_RECITED_COEFFICIENTS"
            if all(anchor_ok.values()) and coefficients_agree
            else "TRANSCRIPTION_DISAGREES_WITH_THE_RECITED_COEFFICIENTS"
        ),
        "reference_data_defect": (
            "The table departs from the best quadratic through it by up to "
            f"{worst_against_fitted:.4f} ohm, about "
            f"{worst_against_fitted / TABLE_QUANTISATION_OHM:.1f} times the "
            "+/-0.005 ohm its own 0.01 ohm resolution implies. No pair of "
            "Callendar-Van Dusen coefficients reproduces it to its stated "
            "resolution, the pre-1995 edition included. This is a defect in "
            "the reference data, and it is what sets the real noise floor of "
            "every comparison against it."
        ),
        "what_this_does_not_establish": (
            "that either source is the current edition of the standard. Two "
            "artifacts agreeing is corroboration; it is not the document, "
            "which this environment cannot reach."
        ),
    }


def _usable_interval(rows) -> dict:
    """Where the linear law stays inside a stated resistance band.

    Reported at three bands rather than one, because there is no single
    externally justified number and inventing one would be exactly the kind of
    threshold this round forbids. Each band is stated with what it means.
    """
    out = {}
    rows = [r for r in rows if r["residual_ohm"] is not None]
    for band, meaning in (
        (0.005, "the table's own quantisation"),
        (0.1, "0.26 degC equivalent"),
        (1.0, "2.6 degC equivalent"),
    ):
        inside = [r["inputs"]["temperature_degC"] for r in rows if abs(r["residual_ohm"]) <= band]
        out[str(band)] = {
            "band_ohm": band,
            "means": meaning,
            "interval_degC": [min(inside), max(inside)] if inside else None,
            "n_entries": len(inside),
        }
    return out


# =====================================================================
# MV-D: what any affine chord must do to a constant-current discharge
# =====================================================================


def case_d() -> dict:
    data = E.discharge_curves()
    rows = []
    for sheet, payload in sorted(data["sheets"].items()):
        for label, curve in sorted(payload["curves"].items()):
            times = curve["t_h"]
            volts = curve["v_v"]
            if len(times) < 10:
                continue
            slope, intercept = _least_squares(times, volts)
            residuals = [v - (slope * t + intercept) for t, v in zip(times, volts)]
            rms = math.sqrt(sum(r * r for r in residuals) / len(residuals))
            rows.append({
                "case": "MV-D",
                "model": "battery.cell.rint_ocv",
                "configuration": "affine chord, structural consequence",
                "source_id": "S-DCHG",
                "evidence_level": LEVEL_2,
                "split": "HELD_OUT",
                "sheet": sheet,
                "curve": label,
                "inputs": {"samples": curve["n_kept"], "original_samples": curve["n_original"],
                           "duration_h": times[-1]},
                "best_case_straight_line": {"slope_v_per_h": slope, "intercept_v": intercept},
                "rms_departure_v": rms,
                "max_departure_v": max(abs(r) for r in residuals),
                "measurement_uncertainty_v": E.VOLTAGE_ACQUISITION_U_V,
                "finding_exceeds_measurement_uncertainty": rms > E.VOLTAGE_ACQUISITION_U_V,
                "applicability": "PARTIALLY_IN_SCOPE",
            })
    return {
        "case_id": "MV-D",
        "rows": rows,
        "summary": {
            "n_curves": len(rows),
            "min_rms_departure_v": min(r["rms_departure_v"] for r in rows),
            "median_rms_departure_v": sorted(r["rms_departure_v"] for r in rows)[len(rows) // 2],
            "max_rms_departure_v": max(r["rms_departure_v"] for r in rows),
            "max_of_max_departure_v": max(r["max_departure_v"] for r in rows),
            "all_exceed_measurement_uncertainty": all(
                r["finding_exceeds_measurement_uncertainty"] for r in rows
            ),
        },
        "what_this_bounds": (
            "The least-squares line is the best any affine-chord configuration "
            "could achieve on this curve, for ANY declared endpoints, capacity, "
            "efficiency or resistance, because the model forces the terminal "
            "voltage to be affine in time under a constant current. The RMS "
            "departure is therefore a parameter-free lower bound on that "
            "configuration's error, and it needs no knowledge of the discharge "
            "current, which this dataset does not record."
        ),
    }


def _least_squares(xs, ys):
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    return slope, mean_y - slope * mean_x


def run_all() -> dict:
    return {
        "MV-A": case_a(),
        "MV-A-replicate": case_a(
            "24h_Charge_BSE", "24h_Discharge_BSE", BSE, "MV-A-replicate"
        ),
        "MV-B": case_b(),
        "MV-C": case_c(),
        "MV-D": case_d(),
    }
