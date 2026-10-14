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
    return {
        "schema": "forge.battery_1rc_identifiability.outcome/1",
        "calibration_sha256": val["calibration_sha256"],
        "validation_sha256": hashlib.sha256(raw).hexdigest(),
        "identifiability": cal["identifiability"]["decision"],
        "held_out_acceptance_1rc": acc,
        "held_out_acceptance_rint": {r: val["roles"][r]["rint"]["acceptance"] for r in HELD_OUT},
        "outcome": decide(cal["identifiability"]["decision"], acc),
        "mapping": PREREG["outcome_mapping"],
        "reading": {
            "supported": "R0, R1, C1 and tau are identifiable from 1C/6C HPPC pulses with a MEASURED OCV, and the frozen "
                         "1RC predicts held-out 2C/4C pulse windows of the same cell within 15 / 30 mV",
            "rejected": "the same parameter set fails the frozen constant-current acceptance on the one 1C capacity test "
                        f"(RMSE {cc['1rc']['rmse_mV']:.1f} mV, P95 {cc['1rc']['p95_abs_mV']:.1f} mV, bias "
                        f"{cc['1rc']['bias_mV']:.1f} mV): one RC branch fitted to 10 s pulses does not carry a "
                        "one-hour constant-current discharge of this cell within the declared limit",
            "not_tested": "cross-cell transfer (one cell), other temperatures, charge and regenerative drive cycles",
            "comparison_note": "the constant-current comparison has ONE unit; its interval is degenerate and is a point "
                               "difference, not a statistical result",
            "hypotheses_not_evidence": ["slower diffusion beyond one time constant", "rate-dependent OCV/hysteresis "
                                        "offset", "a capacity-basis offset between the HPPC day and the 1C test day",
                                        "cell self-heating (case 23.8-25.5 degC)"],
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
