"""Apply the preregistered outcome mapping to the pinned records. Writes results/OUTCOME.json (deterministic)."""

from __future__ import annotations

import hashlib
import json

from .evaluate import RESULTS, load_calibration
from .prereg import PREREG

HELD_OUT = ("heldout_pulses", "heldout_cc")


def decide(identifiability: str, held_out_1rc: dict[str, str]) -> str:
    """The frozen mapping (PREREGISTRATION outcome_mapping), in its stated order."""
    if identifiability != "IDENTIFIABLE":
        return "INSUFFICIENT_MEASUREMENT_EVIDENCE"
    if any(v == "FAIL" for v in held_out_1rc.values()):
        return "MODEL_REJECTED"
    if any(v.startswith("NOT_ASSESSABLE") for v in held_out_1rc.values()):
        return "IDENTIFIABILITY_SUPPORTED"
    return "MODEL_VALIDATION_SUPPORTED"


def build() -> dict:
    cal = load_calibration()
    raw = (RESULTS / "VALIDATION.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (RESULTS / "VALIDATION.sha256").read_bytes().split()[0].decode():
        raise ValueError("VALIDATION.json does not match its pinned digest")
    val = json.loads(raw)
    acc = {r: val["roles"][r]["1rc"]["acceptance"] for r in HELD_OUT}
    cc = val["roles"]["heldout_cc"]
    hp = val["roles"]["heldout_pulses"]
    lim = PREREG["validation"]["acceptance"]
    stricter = dict(acc)
    for r in HELD_OUT:
        if val["roles"][r]["temperature_C"]["in_domain_only_because_of_the_preregistered_1C_widening"]:
            stricter[r] = "NOT_ASSESSABLE (outside the unwidened calibration temperature range)"
    return {
        "schema": "forge.battery_1rc_identifiability.outcome/1",
        "calibration_sha256": val["calibration_sha256"],
        "validation_sha256": hashlib.sha256(raw).hexdigest(),
        "identifiability": cal["identifiability"]["decision"],
        "held_out_acceptance_1rc": acc,
        "held_out_acceptance_rint": {r: val["roles"][r]["rint"]["acceptance"] for r in HELD_OUT},
        "outcome": decide(cal["identifiability"]["decision"], acc),
        "outcome_without_the_preregistered_temperature_widening": decide(cal["identifiability"]["decision"], stricter),
        "mapping": PREREG["outcome_mapping"],
        "reading": {
            "supported": "R0, R1, C1 and tau are identifiable from 1C/6C HPPC pulses GIVEN the measured OCV (one cell, "
                         "25 degC, SOC >= 0.10). The held-out 2C/4C pulse windows pass the preregistered pooled limits "
                         f"(RMSE {hp['1rc']['rmse_mV']:.1f} / P95 {hp['1rc']['p95_abs_mV']:.1f} mV), but this tests current "
                         "interpolation only, shares the OCV knots logged minutes earlier in the same record, is "
                         f"{100 * hp['1rc']['rest_samples'] / hp['1rc']['samples']:.0f} % rest samples, and under load alone "
                         f"the RMSE is {hp['1rc']['load_only_against_the_same_limits']['rmse_mV']:.1f} mV (above "
                         f"{lim['heldout_pulses']['RMSE_mV_max']:.0f})",
            "rejected": "the BUNDLE (this parameter set, the measured OCV, the Q_HPPC charge basis, z0 = 1 and v_p0 = 0) "
                        "fails the frozen constant-current acceptance on the one 1C capacity test (RMSE "
                        f"{cc['1rc']['rmse_mV']:.1f} mV, P95 {cc['1rc']['p95_abs_mV']:.1f} mV, bias "
                        f"{cc['1rc']['bias_mV']:.1f} mV). The failure is marginal: "
                        f"{cc['1rc']['rmse_mV'] - lim['heldout_cc']['RMSE_mV_max']:.2f} mV and "
                        f"{cc['1rc']['p95_abs_mV'] - lim['heldout_cc']['P95_abs_mV_max']:.2f} mV over, both below the "
                        "+/-5 mV voltage accuracy (which is not admitted). The test is in domain only because of the "
                        "preregistered +/-1 degC widening (case "
                        f"{cc['temperature_C']['min']:.2f}-{cc['temperature_C']['max']:.2f} degC against an unwidened "
                        f"{cc['temperature_C']['calibration_range_unwidened'][0]:.2f}-"
                        f"{cc['temperature_C']['calibration_range_unwidened'][1]:.2f} degC); without it the outcome would "
                        "be IDENTIFIABILITY_SUPPORTED. Its initial state (z0 = 1, v_p0 = 0) rests on a 10 s visible rest, "
                        "a weaker basis than the pulse windows' 590 s",
            "not_tested": "cross-cell transfer (one cell), other temperatures, charge and regenerative drive cycles",
            "comparison_note": "the constant-current comparison has ONE unit; its interval is degenerate and is a point "
                               "difference, not a statistical result",
            "hypotheses_not_evidence": ["slower diffusion beyond one time constant", "rate-dependent OCV/hysteresis "
                                        "offset", "a capacity-basis offset between the HPPC day and the 1C test day",
                                        "cell self-heating"],
            "applicability_not_enforced_by_the_route": "SOC >= 0.10 is enforced by the role builder only; the route's "
                                                       "validity domain does not carry it, so its in_domain does not "
                                                       "certify SOC",
        },
    }


def main() -> int:
    doc = build()
    data = json.dumps(doc, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "OUTCOME.json").write_bytes(data)
    (RESULTS / "OUTCOME.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    print(doc["outcome"], doc["held_out_acceptance_1rc"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
