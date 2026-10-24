"""Historical truth, read only after the seal is verified.

The mapping from each historical record to a pilot disposition is frozen here before any run:

* acceptance strings: PASS -> SUPPORTED, FAIL -> NOT_SUPPORTED, NOT_ASSESSABLE -> NOT_ASSESSABLE (first token);
  anything else stops the evaluation (no guessing).
* identifiability decisions: IDENTIFIABLE -> SUPPORTED; NOT_IDENTIFIABLE or WEAKLY_IDENTIFIABLE -> NOT_SUPPORTED
  (the question asks whether EVERY requested parameter is identifiable).
* MODEL_DISCREPANCY (derived): NOT_SUPPORTED if any historical 1RC held-out residual lag-1 autocorrelation exceeds the
  plan's structure threshold (0.5), else NOT_ASSESSABLE (no historical measurement-compatibility decision exists).
* P1 MODEL_ADEQUACY (derived): NOT_SUPPORTED if any historical held-out 1RC acceptance FAILS; SUPPORTED only if all
  PASS and the derived discrepancy is SUPPORTED; else NOT_ASSESSABLE.
* P2 MODEL_ADEQUACY: the preregistered outcome: MODEL_REJECTED -> NOT_SUPPORTED, MODEL_VALIDATION_SUPPORTED ->
  SUPPORTED, IDENTIFIABILITY_SUPPORTED / INSUFFICIENT_MEASUREMENT_EVIDENCE -> NOT_ASSESSABLE.
* P2 CROSS_CELL_TRANSFER: no second cell exists, so the truth is structural (NOT_ASSESSABLE) and the history class is
  HISTORY_NOT_ASSESSABLE.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parents[1]
STRUCTURED_LAG1 = 0.5

RECORDS = {
    "P1": {"calibration": "benchmarks/battery_1rc_closure/results/CALIBRATION.json",
           "validation": "benchmarks/battery_1rc_closure/results/VALIDATION.json",
           "uncertainty": "benchmarks/battery_1rc_closure/results/UNCERTAINTY_REPORT.json"},
    "P2": {"calibration": "benchmarks/battery_1rc_identifiability/results/CALIBRATION.json",
           "validation": "benchmarks/battery_1rc_identifiability/results/VALIDATION.json",
           "outcome": "benchmarks/battery_1rc_identifiability/results/OUTCOME.json"},
}


class SealNotVerified(RuntimeError):
    pass


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def verify_seal(results: pathlib.Path) -> dict[str, Any]:
    """The seal exists, is PASS, is committed in HEAD's history with these bytes, and every bound file matches."""
    seal_path = results / "SEAL.json"
    if not seal_path.exists():
        raise SealNotVerified("no SEAL.json: the candidate outputs are not sealed")
    raw = seal_path.read_bytes()
    rel = str(seal_path.resolve().relative_to(ROOT)).replace("\\", "/")
    commits = _git("log", "--format=%H", "--", rel).split()
    if not commits:
        raise SealNotVerified("SEAL.json is not committed")
    committed = subprocess.run(["git", "show", f"{commits[-1]}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout
    if committed != raw:
        raise SealNotVerified("SEAL.json differs from the bytes first committed")
    seal = json.loads(raw)
    if seal["status"] != "PASS":
        raise SealNotVerified(f"the seal status is {seal['status']}")
    bound = dict(seal["outputs"]); bound.update(seal["access_log"]); bound.update(seal["leakage_pre_seal"])
    for path, sha in bound.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sha:
            raise SealNotVerified(f"{path} changed after the seal")
    return {"seal_sha256": hashlib.sha256(raw).hexdigest(), "seal_commit": commits[-1], "files_bound": len(bound)}


def _acceptance(s: str) -> str:
    tok = s.strip().split()[0].upper().rstrip(":,;.")
    if tok.startswith("PASS"):
        return "SUPPORTED"
    if tok.startswith("FAIL"):
        return "NOT_SUPPORTED"
    if tok.startswith("NOT_ASSESSABLE"):
        return "NOT_ASSESSABLE"
    raise ValueError(f"unmapped historical acceptance {s!r}")


def _identifiability(s: str) -> str:
    if s == "IDENTIFIABLE":
        return "SUPPORTED"
    if s in ("NOT_IDENTIFIABLE", "WEAKLY_IDENTIFIABLE"):
        return "NOT_SUPPORTED"
    raise ValueError(f"unmapped historical identifiability decision {s!r}")


def _load(rel: str) -> tuple[dict, str]:
    raw = (ROOT / rel).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _entry(truth: str | None, history: str, sources: list[str], basis: str, derived: bool = False,
           sub: dict | None = None) -> dict[str, Any]:
    out = {"truth": truth, "history_class": history, "sources": sources, "basis": basis, "derived": derived}
    if sub:
        out["sub"] = sub
    return out


def extract(results: pathlib.Path) -> dict[str, Any]:
    seal = verify_seal(results)
    digests: dict[str, str] = {}
    table: dict[str, dict[str, Any]] = {}

    # P1
    cal, d = _load(RECORDS["P1"]["calibration"]); digests[RECORDS["P1"]["calibration"]] = d
    val, d = _load(RECORDS["P1"]["validation"]); digests[RECORDS["P1"]["validation"]] = d
    unc, d = _load(RECORDS["P1"]["uncertainty"]); digests[RECORDS["P1"]["uncertainty"]] = d
    roles = val["roles"]
    w = _acceptance(roles["within_cell_holdout"]["1rc"]["acceptance"])
    x = _acceptance(roles["cross_cell_validation"]["1rc"]["acceptance"])
    lag = {r: roles[r]["1rc"]["lag1_autocorrelation_mean"] for r in ("within_cell_holdout", "cross_cell_validation")}
    disc = "NOT_SUPPORTED" if max(lag.values()) > STRUCTURED_LAG1 else "NOT_ASSESSABLE"
    adeq = "NOT_SUPPORTED" if "NOT_SUPPORTED" in (w, x) else (
        "SUPPORTED" if (w, x, disc) == ("SUPPORTED", "SUPPORTED", "SUPPORTED") else "NOT_ASSESSABLE")
    p1v = RECORDS["P1"]["validation"]
    table["P1"] = {
        "IDENTIFIABILITY": _entry(_identifiability(cal["identifiability"]["decision"]), "DECIDED",
                                  [RECORDS["P1"]["calibration"] + "#identifiability.decision"],
                                  f"historical decision {cal['identifiability']['decision']}"),
        "WITHIN_CELL_GENERALIZATION": _entry(w, "DECIDED", [p1v + "#roles.within_cell_holdout.1rc.acceptance"],
                                             roles["within_cell_holdout"]["1rc"]["acceptance"][:160]),
        "CROSS_CELL_TRANSFER": _entry(x, "DECIDED", [p1v + "#roles.cross_cell_validation.1rc.acceptance"],
                                      roles["cross_cell_validation"]["1rc"]["acceptance"][:160]),
        "MODEL_DISCREPANCY": _entry(disc, "DECIDED", [p1v + "#roles.*.1rc.lag1_autocorrelation_mean",
                                                      RECORDS["P1"]["uncertainty"] + "#components.model_form.status"],
                                    f"held-out 1RC lag-1 {lag}; model_form status {unc['components']['model_form']['status']}",
                                    derived=True),
        "MODEL_ADEQUACY": _entry(adeq, "DECIDED", [p1v + "#roles.*.1rc.acceptance"],
                                 f"held-out acceptance within={w} cross={x}; derived discrepancy {disc}", derived=True),
    }

    # P2
    cal2, d = _load(RECORDS["P2"]["calibration"]); digests[RECORDS["P2"]["calibration"]] = d
    val2, d = _load(RECORDS["P2"]["validation"]); digests[RECORDS["P2"]["validation"]] = d
    out2, d = _load(RECORDS["P2"]["outcome"]); digests[RECORDS["P2"]["outcome"]] = d
    acc = out2["held_out_acceptance_1rc"]
    sub = {"within_cell_heldout/pulses": _acceptance(acc["heldout_pulses"]), "within_cell_heldout/cc": _acceptance(acc["heldout_cc"])}
    within2 = "NOT_SUPPORTED" if "NOT_SUPPORTED" in sub.values() else (
        "NOT_ASSESSABLE" if "NOT_ASSESSABLE" in sub.values() else "SUPPORTED")
    outcome_map = {"MODEL_REJECTED": "NOT_SUPPORTED", "MODEL_VALIDATION_SUPPORTED": "SUPPORTED",
                   "IDENTIFIABILITY_SUPPORTED": "NOT_ASSESSABLE", "INSUFFICIENT_MEASUREMENT_EVIDENCE": "NOT_ASSESSABLE"}
    lag2 = {r: val2["roles"][r]["1rc"]["lag1_autocorrelation_mean"] for r in ("heldout_pulses", "heldout_cc")}
    disc2 = "NOT_SUPPORTED" if max(lag2.values()) > STRUCTURED_LAG1 else "NOT_ASSESSABLE"
    p2o = RECORDS["P2"]["outcome"]
    table["P2"] = {
        "IDENTIFIABILITY": _entry(_identifiability(out2["identifiability"]), "DECIDED", [p2o + "#identifiability"],
                                  f"historical decision {out2['identifiability']}"),
        "WITHIN_CELL_GENERALIZATION": _entry(within2, "DECIDED", [p2o + "#held_out_acceptance_1rc"],
                                             f"pulses {acc['heldout_pulses']}; cc {acc['heldout_cc']}", sub=sub),
        "CROSS_CELL_TRANSFER": _entry("NOT_ASSESSABLE", "HISTORY_NOT_ASSESSABLE", [],
                                      "one cell only: no cross-cell set exists (structural truth)"),
        "MODEL_DISCREPANCY": _entry(disc2, "HISTORY_NOT_ASSESSABLE", [RECORDS["P2"]["validation"] +
                                    "#roles.heldout_*.1rc.lag1_autocorrelation_mean"],
                                    f"no historical model-form decision; derived from held-out 1RC lag-1 {lag2}",
                                    derived=True),
        "MODEL_ADEQUACY": _entry(outcome_map[out2["outcome"]], "DECIDED", [p2o + "#outcome"],
                                 f"preregistered outcome {out2['outcome']}"),
    }
    params = {"P1": {"1rc": cal["models"]["1rc"]["parameters"], "tau_s": cal["models"]["1rc"]["tau_s"],
                     "rmse_mV": cal["models"]["1rc"]["rmse_mV"]},
              "P2": {"1rc": cal2["models"]["1rc"]["parameters"], "tau_s": cal2["models"]["1rc"]["tau_s"],
                     "rmse_mV": cal2["models"]["1rc"]["rmse_mV"]}}
    heldout_rmse = {"P1": {r: roles[r]["1rc"]["rmse_mV"] for r in ("within_cell_holdout", "cross_cell_validation")},
                    "P2": {r: val2["roles"][r]["1rc"]["rmse_mV"] for r in ("heldout_pulses", "heldout_cc")}}
    return {"schema": "forge.battery_rediscovery.truth/1", "seal": seal, "record_sha256": digests, "table": table,
            "historical_parameters": params, "historical_heldout_rmse_mV": heldout_rmse}


__all__ = ["SealNotVerified", "extract", "verify_seal"]
