"""Uncertainty, model-discrepancy and applicability report, derived only from the pinned result records.

``python -m benchmarks.battery_1rc_closure.uq`` writes results/UNCERTAINTY_REPORT.json. Nothing is fitted or
re-evaluated. UNKNOWN stays UNKNOWN; no component is combined with another under an independence assumption.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from .evaluate import RESULTS, load_calibration


def _pinned(name: str) -> dict:
    raw = (RESULTS / f"{name}.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (RESULTS / f"{name}.sha256").read_bytes().split()[0].decode():
        raise ValueError(f"results/{name}.json does not match its pinned digest")
    return json.loads(raw)


def build() -> dict:
    cal = load_calibration()
    val = _pinned("VALIDATION")
    ident = cal["identifiability"]
    roles = val["roles"]
    held = {r: roles[r] for r in ("within_cell_holdout", "cross_cell_validation")}
    sens = _pinned("SENSITIVITY")
    return {
        "schema": "forge.battery_1rc_closure.uncertainty/1",
        "calibration_sha256": val["calibration_sha256"],
        "validation_sha256": (RESULTS / "VALIDATION.sha256").read_bytes().split()[0].decode(),
        "sensitivity_sha256": (RESULTS / "SENSITIVITY.sha256").read_bytes().split()[0].decode(),
        "components": {
            "measurement": {
                "status": "UNKNOWN",
                "reason": "NASA describes the voltmeter / ammeter / thermocouple suite but states no calibrated "
                          "per-sample uncertainty or traceability for these records; a sensor description is not a "
                          "calibrated uncertainty",
                "evidence_required": "a calibration certificate (or manufacturer accuracy specification bound to the "
                                     "actual instruments and ranges used) for voltage, current, temperature and time, "
                                     "or an independent co-located reference measurement of the same records",
            },
            "parameter": {
                "status": "NOT_ADMISSIBLE",
                "computed": {"bootstrap_sets": len(ident["bootstrap_draws_1rc"]), "bootstrap": ident["bootstrap"],
                             "held_out_band_median_half_width_mV": {r: held[r]["parameter_uncertainty_1rc"]
                                                                    ["median_half_width_mV"] for r in held},
                             "held_out_band_coverage": {r: held[r]["parameter_uncertainty_1rc"]
                                                        ["coverage_of_measurements"] for r in held}},
                "reason": "the parameters are " + ident["decision"] + ": the cycle bootstrap varies near-replicate "
                          "cycles and cannot see the OCV-resistance confounding (flat profiles) or the switch-time "
                          "dependence (forward hold moves R1 by "
                          f"{100 * (ident['sensitivity']['forward_hold']['R1'] / cal['models']['1rc']['parameters']['R1'] - 1):+.0f} %). "
                          "Propagated jointly (no independence assumption), the band covers only a small fraction of "
                          "the held-out measurements, so it must not be presented as the prediction uncertainty",
            },
            "numerical": {
                "status": "NOT_APPLICABLE",
                "reason": "the update is exact for piecewise-constant current; agreement with an independent adaptive "
                          "ODE integration is below 1e-9 V and the fitting transcription equals the route below 1e-12 V "
                          "(tests); float rounding only",
            },
            "initial_state": {
                "status": "PARTIALLY_QUANTIFIED",
                "vp0_plus_20mA_x_R1": ident["sensitivity"]["vp0_20mA_x_R1"],
                "vp0_minus_20mA_x_R1": sens["cases"]["vp0_minus_20mA_x_R1"],
                "reason": "after a CV charge v_p0 carries the charge direction (negative under the positive-discharge "
                          "convention); either sign of a 20 mA x R1 polarization is immaterial (objective ratios "
                          f"{ident['sensitivity']['vp0_20mA_x_R1']['sse_ratio']:.4f} and "
                          f"{sens['cases']['vp0_minus_20mA_x_R1']['sse_ratio']:.4f})",
            },
            "input_reconstruction": {
                "status": "NOT_REDUCED",
                "hold_convention_forward_vs_backward": ident["sensitivity"]["forward_hold"],
                "forward_hold_with_negative_vp0": sens["cases"]["forward_hold_and_vp0_minus_20mA_x_R1"],
                "reason": "turning ~19 s current samples into a piecewise-constant input leaves the load switch "
                          "time unknown within one sample: the forward hold changes the objective by a factor "
                          f"{ident['sensitivity']['forward_hold']['sse_ratio']:.3f} and moves R1 by "
                          f"{100 * (ident['sensitivity']['forward_hold']['R1'] / cal['models']['1rc']['parameters']['R1'] - 1):+.0f} %. "
                          "This is an input (measurement-sampling) uncertainty, not numerical discretization, and it "
                          "is never NOT_APPLICABLE for measured profiles",
            },
            "model_form": {
                "status": "NOT_QUANTIFIED_AS_ADMISSIBLE_UQ",
                "empirical_held_out_residuals": {r: {m: {k: held[r][m][k] for k in ("rmse_mV", "bias_mV", "p95_abs_mV",
                                                                                      "max_abs_mV", "tail_rmse_mV",
                                                                                      "lag1_autocorrelation_mean")}
                                                     for m in ("1rc", "rint")} for r in held},
                "residual_rmse_over_band_half_width": {r: held[r]["1rc"]["rmse_mV"] / held[r]["parameter_uncertainty_1rc"]
                                                       ["median_half_width_mV"] for r in held},
                "reason": "held-out 1RC residual RMSE is "
                          + " and ".join(f"{held[r]['1rc']['rmse_mV'] / held[r]['parameter_uncertainty_1rc']['median_half_width_mV']:.0f}x"
                                         for r in sorted(held))
                          + " the propagated parameter band half-width, and the residuals are strongly autocorrelated "
                          "(lag-1 " + ", ".join(f"{held[r]['1rc']['lag1_autocorrelation_mean']:.2f}" for r in sorted(held))
                          + "): the error is structured model-form and state error (OCV/resistance "
                          "confounding, end-of-discharge knee, rest tail beyond one time constant), not noise. With "
                          "measurement uncertainty UNKNOWN the discrepancy cannot be separated from it, so no "
                          "discrepancy term is admitted; it is never zero",
            },
            "applicability": {
                "supported_regime": "2 A constant-current discharge plus rest, ~24 C ambient, cells of the NASA FY08Q4 "
                                    "batch within their first 30 discharges, SOC on the causal integrated-charge basis",
                "transfer": "cross-cell transfer (B0006) FAILED the preregistered acceptance for both models",
                "extrapolation_flags": {r: held[r]["1rc"]["route_validity_status_counts"] for r in held},
                "acceptance_after_applicability": {r: {m: held[r][m]["acceptance"] for m in ("1rc", "rint")}
                                                   for r in held},
                "unsupported": ["any other current, including pulses and charge", "other temperatures",
                                "aged cells beyond ordinal 30", "other cell types", "parameter values as physical "
                                "constants of the cell"],
            },
        },
        "combination": "none: the components are reported separately; UNKNOWN measurement uncertainty prevents any "
                       "total, and no independence assumption is made",
    }


def main() -> int:
    doc = build()
    data = json.dumps(doc, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "UNCERTAINTY_REPORT.json").write_bytes(data)
    (RESULTS / "UNCERTAINTY_REPORT.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    print(json.dumps({k: v["status"] for k, v in doc["components"].items() if "status" in v}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
