"""R1: reproduce the final Sprint 3 result and freeze it as a baseline record.

This script does not re-open the locked holdout and does not refit anything.
It re-derives what the committed tree can re-derive, verifies every digest the
Sprint 3 provenance chain pins, and records what it could **not** reproduce.

Run, in order, before this script (each was run in the recovery session and
each result is recorded in the output):

    prereg.py            DATA_SELECTION.json, PREREGISTRATION.json
    vendor.py            selected_trajectories.json
    calibrate.py         CALIBRATION.json
    campaign.py          CAMPAIGN_VALIDATION.json
    gate_a.py            GATE_A.json
    flagship.py          FLAGSHIP.json

The stage outcomes below are supplied by ``--stage`` so that this record states
what was actually executed rather than what the script assumes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
REPO = os.path.dirname(os.path.dirname(BENCH))
S3 = os.path.join(REPO, "benchmarks", "battery_thermal_flagship_s3")
S3_EVIDENCE = os.path.join(S3, "evidence")

#: The Sprint 3 artifacts whose bytes this baseline pins.
PINNED = (
    "PREREGISTRATION.json",
    "DATA_SELECTION.json",
    "selected_trajectories.json",
    "OCV_AUTHORITY.json",
    "CALIBRATION.json",
    "CAMPAIGN_VALIDATION.json",
    "CAMPAIGN_HOLDOUT.json",
    "GATE_A.json",
    "FLAGSHIP.json",
)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def load(name: str):
    with open(os.path.join(S3_EVIDENCE, name), encoding="utf-8") as handle:
        return json.load(handle)


def ocv_provenance_check() -> dict:
    """Is the committed OCV authority derivable from the committed selection?

    The authority names the (cell, discharge cycle) pairs it was built from.
    The selection names the calibration cycles the authority is allowed to
    read. If the first is not a subset of the second, the shipped curve rests
    on a trajectory this campaign does not admit.
    """
    ocv = load("OCV_AUTHORITY.json")
    selection = load("DATA_SELECTION.json")
    allowed: dict[str, set[int]] = {}
    for item in selection["selected"]:
        if item["split"] == "calibration":
            allowed.setdefault(item["cell"], set()).add(int(item["cycle_index"]))
    used = [(p["cell"], int(p["discharge_cycle"])) for p in ocv["pairs"]]
    strangers = sorted(
        f"{cell}.d{cycle:04d}"
        for cell, cycle in used
        if cycle not in allowed.get(cell, set())
    )
    rejected = {
        item["trajectory_id"]: item["why"]
        for item in selection.get("not_full_at_start", [])
    }
    return {
        "reproducible_from_committed_selection": not strangers,
        "pairs_in_authority": len(used),
        "pairs_not_admitted_by_the_selection": strangers,
        "why_each_is_not_admitted": {
            name: rejected.get(name, "not a selected calibration trajectory")
            for name in strangers
        },
        "consequence": (
            "the open-circuit voltage curve the flagship ran with cannot be "
            "regenerated from the committed selection; re-running ocv.py on "
            "this tree produces a different curve"
        ) if strangers else "",
    }


def fingerprint_stability_check() -> dict:
    """Is a composition pack's authority digest stable across processes?

    ``implementation_fingerprint`` hashes ``repr(code.co_consts)``. When an
    implementation contains a comprehension or a lambda, ``co_consts`` holds a
    nested code object whose ``repr`` embeds its memory address, so the digest
    is a property of the process rather than of the code.
    """
    from engcore.compositionpacks import builtin_battery_electrothermal as pack
    from engcore.domainpacks.frozen import implementation_fingerprint

    rows = []
    for name in sorted(dir(pack)):
        value = getattr(pack, name, None)
        if not callable(value):
            continue
        if getattr(value, "__module__", "") != pack.__name__:
            continue
        code = getattr(value, "__code__", None)
        try:
            digest, _basis = implementation_fingerprint(value)
        except Exception:
            continue
        nested = (
            [c for c in code.co_consts if isinstance(c, types.CodeType)]
            if code is not None
            else []
        )
        rows.append(
            {
                "implementation": name,
                "digest_this_process": digest,
                "nested_code_objects": len(nested),
                "address_bearing_repr": bool(nested),
            }
        )
    unstable = [r["implementation"] for r in rows if r["address_bearing_repr"]]
    return {
        "mechanism": (
            "engcore.domainpacks.frozen.implementation_fingerprint hashes "
            "repr(code.co_consts); a nested code object's repr contains its "
            "memory address, e.g. '<code object <genexpr> at 0x...>'"
        ),
        "implementations": rows,
        "process_dependent_implementations": unstable,
        "stable": not unstable,
        "consequence": (
            "composition_authority_digest, and every certification digest "
            "derived from it, differ between two runs of the same bytes; the "
            "scientific result is unaffected and the within-run verification "
            "still holds, but the recorded digest cannot be re-derived later"
        ) if unstable else "",
    }


def gate_a_arithmetic_check() -> dict:
    """Does GATE_A.json's verdict follow from CAMPAIGN_HOLDOUT.json's metrics?"""
    campaign = load("CAMPAIGN_HOLDOUT.json")
    gate = load("GATE_A.json")
    rows = []
    for metric, result in gate["metrics"].items():
        recorded = campaign["metrics"][metric]["locked_holdout"]
        for check in result["checks"]:
            measured = recorded[check["statistic"]]
            rows.append(
                {
                    "metric": metric,
                    "statistic": check["statistic"],
                    "gate_a_value": check["value"],
                    "campaign_value": measured,
                    "agrees": abs(check["value"] - measured) <= 1e-12,
                    "limit": check["limit"],
                    "passed": check["passed"],
                    "verdict_follows": (check["value"] <= check["limit"])
                    == check["passed"],
                }
            )
    return {
        "checks": rows,
        "every_gate_value_came_from_the_campaign_record": all(
            r["agrees"] for r in rows
        ),
        "every_verdict_follows_from_its_threshold": all(
            r["verdict_follows"] for r in rows
        ),
        "gate_a_passed": gate["gate_a_passed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        action="append",
        default=[],
        metavar="NAME=OUTCOME[:NOTE]",
        help="outcome of a reproduction stage actually executed this session",
    )
    args = parser.parse_args()

    stages = []
    for raw in args.stage:
        name, _, rest = raw.partition("=")
        outcome, _, note = rest.partition(":")
        stages.append(
            {"stage": name, "outcome": outcome, "note": note or ""}
        )

    gate = load("GATE_A.json")
    campaign = load("CAMPAIGN_HOLDOUT.json")
    validation = load("CAMPAIGN_VALIDATION.json")
    calibration = load("CALIBRATION.json")
    prereg = load("PREREGISTRATION.json")

    per_cell = {
        metric: {
            cell: {k: v for k, v in values.items()}
            for cell, values in result["diagnosis"]["by_cell"].items()
        }
        for metric, result in gate["metrics"].items()
    }

    record = {
        "schema": "battery_voltage_s3_recovery_baseline/1",
        "what_this_is": (
            "the frozen record of the Sprint 3 result as this tree reproduces "
            "it. It is historical evidence. No number in it may be used to "
            "choose a model, a parameter or a threshold in the recovery."
        ),
        "base": {
            "branch": "claude/battery-thermal-flagship-sprint-3",
            "commit": git("rev-parse", "7aff1449"),
            "commit_subject": git("log", "-1", "--format=%s", "7aff1449"),
            "recovery_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "tree_clean_at_baseline": git("status", "--porcelain") == "",
        },
        "dataset": {
            "archive_sha256": campaign["dataset"].get("snapshot_sha256")
            or prereg.get("archive_sha256"),
            "normalized_digest": campaign["dataset"]["normalized_digest"],
            "campaign_id": campaign["campaign_id"],
            "campaign_version": campaign["campaign_version"],
            "holdout_opening_digest": campaign["holdout_opening_digest"],
            "report_digest": campaign["report_digest"],
        },
        "artifact_digests": {
            name: sha256_file(os.path.join(S3_EVIDENCE, name)) for name in PINNED
        },
        "reproduction_stages": stages,
        "reproduced_result": {
            "gate_a_passed": gate["gate_a_passed"],
            "locked_holdout": {
                metric: campaign["metrics"][metric]["locked_holdout"]
                for metric in gate["metrics"]
            },
            "validation_split": {
                metric: validation["metrics"][metric]["validation"]
                for metric in gate["metrics"]
            },
            "calibration_split": {
                metric: validation["metrics"][metric]["calibration"]
                for metric in gate["metrics"]
            },
            "per_cell": per_cell,
            "counts": campaign["counts"],
            "refusal_accuracy": campaign["refusal_accuracy"],
            "pass_fraction": campaign["pass_fraction"],
        },
        "fitted_parameters": {
            group["group"]: {
                "cells": group["cells"],
                "fitted": group["fitted"],
                "identifiability": group["identifiability"],
                "produces_a_claim": group["produces_a_claim"],
            }
            for group in calibration["groups"]
        },
        "gate_a_thresholds_frozen": {
            metric: {
                check["statistic"]: check["limit"]
                for check in result["checks"]
            }
            for metric, result in gate["metrics"].items()
        },
        "checks": {
            "gate_a_arithmetic": gate_a_arithmetic_check(),
            "ocv_provenance": ocv_provenance_check(),
            "pack_fingerprint_stability": fingerprint_stability_check(),
        },
    }

    problems = []
    if not record["checks"]["ocv_provenance"]["reproducible_from_committed_selection"]:
        problems.append("ocv_authority_not_reproducible_from_committed_selection")
    if not record["checks"]["pack_fingerprint_stability"]["stable"]:
        problems.append("pack_authority_digest_is_process_dependent")
    record["defects_found_while_reproducing"] = problems
    record["scientific_result_reproduces"] = all(
        s["outcome"] in ("identical", "identical_modulo_wall_clock")
        for s in stages
        if s["stage"] in ("prereg", "vendor", "calibrate", "campaign_validation", "gate_a")
    )

    text = json.dumps(record, indent=1, allow_nan=False, sort_keys=False)
    out = os.path.join(EVIDENCE, "S3_RECOVERY_BASELINE.json")
    os.makedirs(EVIDENCE, exist_ok=True)
    with open(out, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")
    print(f"wrote {out}")
    print(f"  gate A passed          : {record['reproduced_result']['gate_a_passed']}")
    print(f"  scientific reproduction: {record['scientific_result_reproduces']}")
    print(f"  defects found          : {problems or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
