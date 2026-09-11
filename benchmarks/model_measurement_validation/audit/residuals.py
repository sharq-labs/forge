"""MV-17: what shape are the residuals, not merely how big.

A low summary error with a systematic trend in it is a different situation
from a low summary error with none, and the two are reported differently here.
Every case with more than two points gets a bias, a slope against its own
independent variable, a curvature, a count of sign changes and a comparison of
its low and high regimes.

The rule this file applies: a residual set whose signs never change and whose
magnitude varies monotonically with the independent variable is structural, and
saying so is more useful than any single number.
"""

from __future__ import annotations

import math


def _least_squares(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    return slope, mean_y - slope * mean_x


def _quadratic_coefficient(xs, ys):
    """The t^2 coefficient of a least-squares parabola. Zero means no curvature."""
    n = len(xs)
    if n < 3:
        return 0.0
    normal = [[0.0] * 3 for _ in range(3)]
    right = [0.0] * 3
    for x, y in zip(xs, ys):
        basis = [1.0, x, x * x]
        for i in range(3):
            right[i] += basis[i] * y
            for j in range(3):
                normal[i][j] += basis[i] * basis[j]
    for k in range(3):
        pivot = max(range(k, 3), key=lambda r: abs(normal[r][k]))
        if normal[pivot][k] == 0.0:
            return 0.0
        normal[k], normal[pivot] = normal[pivot], normal[k]
        right[k], right[pivot] = right[pivot], right[k]
        for r in range(k + 1, 3):
            factor = normal[r][k] / normal[k][k]
            for c in range(k, 3):
                normal[r][c] -= factor * normal[k][c]
            right[r] -= factor * right[k]
    coefficients = [0.0] * 3
    for k in range(2, -1, -1):
        total = right[k] - sum(normal[k][c] * coefficients[c] for c in range(k + 1, 3))
        coefficients[k] = total / normal[k][k]
    return coefficients[2]


def analyse(name, xs, residuals, uncertainties=None, independent="x", unit="V") -> dict:
    if len(xs) < 2:
        return {"case": name, "n": len(xs), "verdict": "TOO_FEW_POINTS_FOR_A_SHAPE"}
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    xs = [xs[i] for i in order]
    residuals = [residuals[i] for i in order]
    slope, intercept = _least_squares(xs, residuals)
    curvature = _quadratic_coefficient(xs, residuals)
    signs = [1 if r > 0 else (-1 if r < 0 else 0) for r in residuals if r != 0]
    sign_changes = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    half = max(1, len(residuals) // 2)
    low = residuals[:half]
    high = residuals[-half:]
    mean = sum(residuals) / len(residuals)
    median = sorted(residuals)[len(residuals) // 2]
    spread = math.sqrt(
        sum((r - mean) ** 2 for r in residuals) / max(1, len(residuals) - 1)
    )
    out = {
        "case": name,
        "n": len(residuals),
        "independent_variable": independent,
        "unit": unit,
        "mean_bias": mean,
        "median_bias": median,
        "standard_deviation": spread,
        "slope_per_unit_of_independent": slope,
        "curvature_coefficient": curvature,
        "sign_changes": sign_changes,
        "all_one_sign": sign_changes == 0,
        "low_regime_mean": sum(low) / len(low),
        "high_regime_mean": sum(high) / len(high),
        "low_to_high_drift": sum(high) / len(high) - sum(low) / len(low),
    }
    if uncertainties:
        scaled = [abs(r) / u for r, u in zip(residuals, uncertainties) if u > 0]
        out["worst_residual_in_units_of_uncertainty"] = max(scaled, default=0.0)
        out["median_residual_in_units_of_uncertainty"] = sorted(scaled)[len(scaled) // 2] if scaled else 0.0
    structural = (
        out["all_one_sign"] and abs(out["mean_bias"]) > 2.0 * out["standard_deviation"]
    ) or (out["all_one_sign"] and abs(out["low_to_high_drift"]) > out["standard_deviation"])
    out["verdict"] = (
        "SYSTEMATIC_STRUCTURE" if structural else "NO_SYSTEMATIC_STRUCTURE_DETECTED"
    )
    out["why"] = (
        "every residual carries the same sign and the trend across the range "
        "exceeds the scatter, so this is structure and not noise"
        if structural
        else "the residuals change sign or their trend is inside their own scatter"
    )
    return out


def run_all(results: dict) -> dict:
    out = {}

    for key in ("MV-A", "MV-A-replicate"):
        held = [r for r in results[key]["rows"] if r["split"] == "HELD_OUT"]
        out[key] = analyse(
            key,
            [r["inputs"]["state_of_charge"] for r in held],
            [r["residual_v"] for r in held],
            [r["expanded_uncertainty_k2_v"] for r in held],
            independent="state_of_charge",
            unit="V",
        )

    scored = [r for r in results["MV-C"]["rows"] if r["split"] == "VALIDATION"]
    out["MV-C"] = analyse(
        "MV-C",
        [r["inputs"]["temperature_degC"] for r in scored],
        [r["residual_ohm"] for r in scored],
        [r["expanded_uncertainty_k2_ohm"] for r in scored],
        independent="temperature_degC",
        unit="ohm",
    )
    out["MV-C"]["expected_shape"] = (
        "a positive, purely quadratic residual: the linear law drops exactly "
        "the -B t^2 term, so the residual SHOULD be systematic. A residual "
        "with no structure here would mean the omitted term was not what the "
        "algebra says it is."
    )

    departures = [r["rms_departure_v"] for r in results["MV-D"]["rows"]]
    durations = [r["inputs"]["duration_h"] for r in results["MV-D"]["rows"]]
    out["MV-D"] = analyse(
        "MV-D", durations, departures, None,
        independent="discharge_duration_h", unit="V",
    )
    out["MV-D"]["note"] = (
        "These are departures from a straight line, which are magnitudes and "
        "cannot change sign, so the sign test carries no information here and "
        "the verdict is read from the drift alone."
    )
    return out
