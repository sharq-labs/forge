"""Apply the preregistered outcome mapping to the pinned records. Writes results/OUTCOME.json (deterministic)."""

from __future__ import annotations

import hashlib
import json

from .data import PREREG
from .evaluate import RESULTS, load_calibration

HELD_OUT = ("heldout_gitt25", "heldout_gitt5")


def decide(identifiability: str, held_out_1rc: dict[str, str]) -> str:
    """The frozen mapping (PREREGISTRATION outcome_mapping), in its stated order."""
    if identifiability != "IDENTIFIABLE":
        return "INSUFFICIENT_MEASUREMENT_EVIDENCE"
    if any(v == "FAIL" for v in held_out_1rc.values()):
        return "MODEL_REJECTED"
    if any(v.startswith("NOT_ASSESSABLE") for v in held_out_1rc.values()):
        return "IDENTIFIABILITY_SUPPORTED"
    return "MODEL_VALIDATION_SUPPORTED"


def ledger_independent_validation(outcome: str, measurement_uncertainty_admitted: bool) -> str:
    """The preregistered ledger rule: a report, not a promotion."""
    return "PASS" if outcome == "MODEL_VALIDATION_SUPPORTED" and measurement_uncertainty_admitted else "MISSING"


def build() -> dict:
    cal = load_calibration()
    raw = (RESULTS / "VALIDATION.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (RESULTS / "VALIDATION.sha256").read_bytes().split()[0].decode():
        raise ValueError("VALIDATION.json does not match its pinned digest")
    val = json.loads(raw)
    acc = {r: val["roles"][r]["1rc"]["acceptance"] for r in HELD_OUT}
    outcome = decide(cal["identifiability"]["decision"], acc)
    lim = PREREG["validation"]["acceptance"]
    summary = {}
    for r, key in zip(HELD_OUT, ("primary", "secondary")):
        m = val["roles"][r]["1rc"]
        summary[r] = {"acceptance": acc[r], "limits": lim[key], "rmse_mV": m["rmse_mV"], "p95_abs_mV": m["p95_abs_mV"],
                      "load_only_rmse_mV": m["load_only"]["rmse_mV"], "load_only_p95_abs_mV": m["load_only"]["p95_abs_mV"],
                      "bias_mV": m["bias_mV"], "cells": val["roles"][r]["cells"],
                      "windows": val["roles"][r]["units_windows"], "route_validity": val["roles"][r]["route_validity"],
                      "comparison_vs_rint": val["roles"][r]["comparison"]["verdict"],
                      "out_of_domain_attribution": val["roles"][r]["out_of_domain_attribution"],
                      "current_A": val["roles"][r]["current_A"]}
    g25, g5 = val["roles"]["heldout_gitt25"], val["roles"]["heldout_gitt5"]
    ps = cal["parameter_set"]
    ident = cal["identifiability"]
    sub25, sub5 = g25.get("in_domain_windows_only"), g5.get("in_domain_windows_only")
    reading = {
        "supported": f"R0, R1, C1 and tau are {ident['decision']} from the 25-pulse GITT windows of "
                     f"{len(cal['cells'])} calibration cells in three experiments (cell-block bootstrap CV "
                     f"{100 * max(v['bootstrap_cv'] for v in ident['per_parameter'].values()):.1f} % at most), with the "
                     "calibration-mean measured OCV fixed",
        "not_assessable": f"neither held-out set can support or contradict the model: {sum(v for k, v in summary['heldout_gitt25']['out_of_domain_attribution'].items() if k != 'in_domain')} "
                          f"of {g25['units_windows']} primary and "
                          f"{sum(v for k, v in summary['heldout_gitt5']['out_of_domain_attribution'].items() if k != 'in_domain')} "
                          f"of {g5['units_windows']} secondary windows leave the unwidened calibration domain "
                          f"({ps['temperature_range_C'][0]:.2f}-{ps['temperature_range_C'][1]:.2f} degC, "
                          f"<= {ps['max_current_A']:.4f} A): held-out cells ran as cold as "
                          f"{min(g25['temperature_C']['min'], g5['temperature_C']['min']):.2f} degC, and the held-out pulse "
                          f"current exceeds the calibration maximum by up to "
                          f"{max(g25['current_A']['excess_mA'], g5['current_A']['excess_mA']):.2f} mA in some windows. "
                          "The preregistration keeps the range unwidened because the BioLogic accuracy is not admitted; "
                          "it is not widened after the fact",
        "what_an_admitted_accuracy_would_and_would_not_change": "an owner-admitted cycler current accuracy could cover "
                          "the sub-mA current excess, but NOT the temperature gap (several degC, and the thermocouple is "
                          f"not the cycler's current channel): {summary['heldout_gitt25']['out_of_domain_attribution'].get('temperature_below_calibration_min', 0) + summary['heldout_gitt25']['out_of_domain_attribution'].get('temperature_below_calibration_min+current_above_calibration_max', 0)} "
                          "primary windows are outside on temperature, so the primary set would stay NOT_ASSESSABLE. "
                          "Closing the temperature gap needs calibration data that spans the held-out temperatures, or "
                          "held-out cells inside the calibrated range, under a new preregistration",
        "descriptive_only": None if not (sub25 and sub5) else (
            f"NOT preregistered, NO verdict: on the in-domain windows only, the 1RC errors are "
            f"{sub25['1rc']['rmse_mV']:.1f} / {sub25['1rc']['p95_abs_mV']:.1f} mV (primary, "
            f"{sub25['windows']} windows; load-only {sub25['1rc']['load_only']['rmse_mV']:.1f} / "
            f"{sub25['1rc']['load_only']['p95_abs_mV']:.1f}) and {sub5['1rc']['rmse_mV']:.1f} / "
            f"{sub5['1rc']['p95_abs_mV']:.1f} mV (secondary, {sub5['windows']} windows from "
            f"{len(sub5['cells'])} cells). The subset is not neutral: the excluded windows carry larger errors (full "
            f"primary set {g25['1rc']['rmse_mV']:.1f} mV). A post-hoc subset selected after the held-out cells were "
            "opened cannot replace the preregistered set"),
        "blindness_spent": "the held-out cells were partly unblinded while building the roles (raw step edges of the "
                           "Expt 2,2 cells were read; on-load drops seen before the calibration fit, which had no free "
                           "choice left) and fully opened by the evaluation; a later evaluation on them (for example after "
                           "an owner-admitted measurement uncertainty widens the domain) would not be blind and must say "
                           "so. A blind cross-cell verdict needs cells not yet opened",
        "not_tested": "other temperatures, ageing, charge, drive cycles, currents other than 2.5 A, SOC below the scope; "
                      "the pulse current equals the calibration current, so this is cross-cell transfer, not current "
                      "extrapolation",
        "hypotheses_not_evidence": ["the held-out rigs (experiments 1 and 2,2) ran colder at times than the "
                                    "calibration rigs", "Expt 2,2/D's larger strict-transfer error tracks its lower own "
                                    "capacity (Q_own below Q_cal)"],
        "applicability_not_enforced_by_the_route": "the SOC scope is enforced by the role builder only; the route's "
                                                   "validity domain does not carry it",
    }
    return {
        "schema": "forge.battery_1rc_crosscell.outcome/1",
        "calibration_sha256": val["calibration_sha256"],
        "validation_sha256": hashlib.sha256(raw).hexdigest(),
        "identifiability": cal["identifiability"]["decision"],
        "parameters": cal["models"]["1rc"]["parameters"] | {"tau_s": cal["models"]["1rc"]["tau_s"]},
        "held_out_acceptance_1rc": acc,
        "held_out_acceptance_rint": {r: val["roles"][r]["rint"]["acceptance"] for r in HELD_OUT},
        "held_out_summary": summary,
        "outcome": outcome,
        "mapping": PREREG["outcome_mapping"],
        "ledger_independent_validation": ledger_independent_validation(outcome, False),
        "ledger_reason": "Kirkaldy measurement uncertainty is UNKNOWN (not admitted); the preregistered rule keeps the "
                         "gate MISSING whatever the outcome",
        "scope": val["scope"],
        "reading": reading,
    }


def main() -> int:
    doc = build()
    data = json.dumps(doc, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "OUTCOME.json").write_bytes(data)
    (RESULTS / "OUTCOME.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    print(doc["outcome"], doc["held_out_acceptance_1rc"], doc["ledger_independent_validation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
