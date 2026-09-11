"""Structural checks on the result set, independent of any number in it.

Three failure modes cannot be caught by looking at residuals, because they
leave every residual looking fine:

  * a point used both to set a parameter and to validate it;
  * a row the applicability screen excluded, counted in a validation summary;
  * a held-out point relabelled as calibration, which shrinks the held-out set
    until only the comfortable points remain.

Each is checked here against the preregistered split, which is read off disk
rather than recomputed, so that editing the code cannot quietly edit the rule.
"""

from __future__ import annotations

import json

from .evidence import ROOT


def _plan():
    return json.loads((ROOT / "VALIDATION_SPLIT.json").read_text(encoding="utf-8"))


def _rows(results):
    for bundle in results.values():
        for row in bundle["rows"]:
            yield row


def calibration_leakage(results) -> dict:
    """No input may appear as CALIBRATION and as HELD_OUT in the same case."""
    seen: dict[tuple, set] = {}
    for row in _rows(results):
        key = (row["case"], json.dumps(row["inputs"], sort_keys=True))
        seen.setdefault(key, set()).add(row["split"])
    offenders = [
        {"case": case, "inputs": json.loads(inputs), "splits": sorted(splits)}
        for (case, inputs), splits in seen.items()
        if len(splits) > 1
    ]
    return {
        "check": "calibration leakage",
        "points_examined": len(seen),
        "offenders": offenders,
        "passed": not offenders,
    }


def applicability_respected(results) -> dict:
    """Nothing screened OUT_OF_SCOPE may carry a validation verdict."""
    offenders = [
        {"case": row["case"], "inputs": row["inputs"], "applicability": row["applicability"]}
        for row in _rows(results)
        if row.get("applicability") == "OUT_OF_SCOPE"
        and row.get("split") in ("VALIDATION", "HELD_OUT")
    ]
    return {
        "check": "applicability respected",
        "offenders": offenders,
        "passed": not offenders,
    }


def split_matches_the_plan(results) -> dict:
    """The counts that ran must be the counts that were preregistered."""
    plan = {entry["case_id"]: entry for entry in _plan()["splits"]}
    report = []
    for case_id, bundle in results.items():
        base = case_id.replace("-replicate", "")
        if base not in plan or case_id.endswith("replicate"):
            continue
        counts = {"CALIBRATION": 0, "VALIDATION": 0, "HELD_OUT": 0}
        for row in bundle["rows"]:
            counts[row["split"]] = counts.get(row["split"], 0) + 1
        expected = plan[base]["counts"]
        report.append({
            "case": case_id,
            "expected": expected,
            "observed": {
                "calibration_rows": counts["CALIBRATION"],
                "validation_rows": counts["VALIDATION"],
                "held_out_rows": counts["HELD_OUT"],
            },
            "matches": (
                counts["CALIBRATION"] == expected["calibration_rows"]
                and counts["VALIDATION"] == expected["validation_rows"]
                and counts["HELD_OUT"] == expected["held_out_rows"]
            ),
        })
    return {
        "check": "split matches the preregistered plan",
        "cases": report,
        "passed": all(entry["matches"] for entry in report),
    }


def uncertainty_is_not_zero(results) -> dict:
    """No comparison may be scored against a zero measurement uncertainty."""
    offenders = []
    for row in _rows(results):
        for key in ("expanded_uncertainty_k2_v", "expanded_uncertainty_k2_ohm"):
            if key in row and not row[key] > 0.0:
                offenders.append({"case": row["case"], "inputs": row["inputs"], "field": key})
    return {
        "check": "measurement uncertainty is represented",
        "offenders": offenders,
        "passed": not offenders,
    }


def relaxation_read_at_the_declared_end(results) -> dict:
    """Every relaxed open-circuit voltage must come from the end of its trace.

    A 24-hour relaxation read at one hour is still a voltage, still plausible,
    and wrong by hundreds of millivolts on a cell that has just come off
    charge. Nothing in a residual reveals it, because every value moves
    together. So the read point is carried on the row and checked against the
    relaxation duration the dataset declares.
    """
    offenders = [
        {"case": row["case"], "inputs": row["inputs"],
         "read_at_hours": row["relaxed_at_hours"],
         "declared_hours": row["declared_relaxation_hours"]}
        for row in _rows(results)
        if "relaxed_at_hours" in row
        and abs(row["relaxed_at_hours"] - row["declared_relaxation_hours"]) > 1e-6
    ]
    return {
        "check": "relaxed values read at the declared end of the trace",
        "offenders": offenders,
        "passed": not offenders,
    }


def run_all(results) -> dict:
    checks = [
        relaxation_read_at_the_declared_end(results),
        calibration_leakage(results),
        applicability_respected(results),
        split_matches_the_plan(results),
        uncertainty_is_not_zero(results),
    ]
    offences = 0
    for check in checks:
        offences += len(check.get("offenders", []))
        offences += sum(1 for c in check.get("cases", []) if not c["matches"])
    return {
        "checks": checks,
        "offences": offences,
        "all_passed": all(check["passed"] for check in checks),
    }
