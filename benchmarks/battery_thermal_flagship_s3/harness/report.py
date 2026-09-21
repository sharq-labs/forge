"""The flagship result artifact, machine-readable, and its human summary.

Reads the evidence files and assembles them. It computes nothing: every number
below was produced by the step that owns it, and this module's only job is to
put them in one place with the identity chain intact.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import prereg  # noqa: E402
from engcore.domains.battery import flagship as fl  # noqa: E402
from engcore.domains.battery.flagship_ocv import (  # noqa: E402
    FLAGSHIP_OCV_CURVE,
    OCV_LOWER,
    OCV_UPPER,
)


def read(name: str):
    with open(os.path.join(EVIDENCE, name), encoding="utf-8") as handle:
        return json.load(handle)


def digest_of(name: str) -> str:
    with open(os.path.join(EVIDENCE, name), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main() -> int:
    preregistration = read("PREREGISTRATION.json")
    selection = read("DATA_SELECTION.json")
    inventory = read("INVENTORY.json")
    ocv = read("OCV_AUTHORITY.json")
    calibration = read("CALIBRATION.json")
    validation = read("CAMPAIGN_VALIDATION.json")
    holdout = read("CAMPAIGN_HOLDOUT.json")
    gate = read("GATE_A.json")
    flagship = read("FLAGSHIP.json")

    superseded = None
    if os.path.exists(os.path.join(EVIDENCE, "GATE_A_v3_superseded.json")):
        superseded = read("GATE_A_v3_superseded.json")

    inside = [x for x in selection["selected"] if x["applicability"] == "inside"]
    by_split: dict[str, set[str]] = {}
    for item in selection["selected"]:
        by_split.setdefault(item["split"], set()).add(item["cell"])

    record: dict[str, Any] = {
        "schema": "battery_thermal_flagship_s3_result/1",
        "campaign_id": prereg.CAMPAIGN_ID,
        "campaign_version": prereg.CAMPAIGN_VERSION,
        "verdict": {
            "gate_a_passed": gate["gate_a_passed"],
            "sprint_3": (
                "PASS" if gate["gate_a_passed"] else "NOT YET PASSED"
            ),
            "what_passed": [
                v for v in gate["verdicts"] if v.endswith("PASS")
            ],
            "what_failed": [
                v for v in gate["verdicts"] if v.endswith("FAIL")
            ],
        },
        "dataset": {
            "dataset_id": preregistration["dataset"]["dataset_id"],
            "title": preregistration["dataset"]["title"],
            "version": preregistration["dataset"]["version"],
            "archive_sha256": inventory["archive_sha256"],
            "archive_bytes": inventory["archive_bytes"],
            "archive_url": inventory["archive_url"],
            "normalized_digest": holdout["dataset"]["normalized_digest"],
            "screened": inventory["counts"],
            "cells": sorted({x["cell"] for x in selection["selected"]}),
            "cells_by_split": {k: sorted(v) for k, v in sorted(by_split.items())},
            "trajectories_by_split": selection["counts"]["by_split"],
            "cases": holdout["dataset"]["cases"],
            "observations": holdout["dataset"]["observations"],
            "thermal_outliers": selection["thermal_outliers"],
            "not_full_at_start": selection["not_full_at_start"],
        },
        "experiments": {
            "calibration": sorted(
                x["trajectory_id"] for x in inside if x["split"] == "calibration"
            ),
            "validation": sorted(
                x["trajectory_id"] for x in inside if x["split"] == "validation"
            ),
            "locked_holdout": sorted(
                x["trajectory_id"]
                for x in inside
                if x["split"] == "locked_holdout"
            ),
            "guardrail_outside_applicability": sorted(
                x["trajectory_id"]
                for x in selection["selected"]
                if x["applicability"] == "outside"
            ),
        },
        "model": {
            "model_id": fl.MODEL_ID,
            "version": fl.MODEL_VERSION,
            "realization": (
                f"{fl.ELECTROTHERMAL_1RC_REALIZATION.realization_id}@"
                f"{fl.ELECTROTHERMAL_1RC_REALIZATION.version}"
            ),
            "solver": f"{fl.SOLVER_ID}@{fl.SOLVER_VERSION}",
            "composition_pack": flagship["run"]["composition_pack"],
            "execution_pack": flagship["run"]["execution_pack"],
            "blueprint": flagship["run"]["blueprint_id"],
            "assumptions": list(fl.ELECTROTHERMAL_1RC_MODEL.assumptions),
            "exclusions": list(fl.ELECTROTHERMAL_1RC_MODEL.exclusions),
        },
        "ocv_authority": {
            "digest": FLAGSHIP_OCV_CURVE.fingerprint,
            "method": ocv["method"],
            "interval": [OCV_LOWER, OCV_UPPER],
            "knots": len(ocv["knots"]),
            "derived_from_split": ocv["derived_from_split"],
            "calibration_cells": ocv["calibration_cells"],
            "interquartile_spread_v": ocv["interquartile_spread_v"],
            "extrapolation_policy": ocv["extrapolation_policy"],
            "what_it_is_not": ocv["what_it_is_not"],
        },
        "parameters": {
            "unit": calibration["parameter_unit"],
            "objective": calibration["objective"],
            "fixed": calibration["fixed"],
            "groups": [
                {
                    "group": item["group"],
                    "fitted_on": item["cells"],
                    "produces_a_claim": item["produces_a_claim"],
                    "fitted": item["fitted"],
                    "standard_errors": item["standard_errors"],
                    "identifiability": item["identifiability"],
                    "at_declared_bound": item["at_declared_bound"],
                    "objective_value": item["objective_value"],
                    "residuals": item["residuals"],
                }
                for item in calibration["groups"]
            ],
            "digest": digest_of("CALIBRATION.json"),
        },
        "input_profile": {
            "what_the_model_is_given": [
                "the measured load current at every sample instant, held "
                "between samples",
                "the ambient temperature of the experiment",
                "the measured cell temperature at the FIRST instant only",
                "the charge protocol's full-charge initial charge state",
                "zero initial polarization voltage",
            ],
            "what_it_is_never_given": [
                "any measured terminal voltage, at any instant",
                "any measured cell temperature after the first instant",
                "the cycle's own delivered capacity",
            ],
            "schedule_interpolation": "step (zero-order hold)",
            "rest_band_a": 0.05,
        },
        "quantities_of_interest": {
            "terminal_voltage": "validated against measurement",
            "cell_temperature": "validated against measurement",
            "state_of_charge": prereg.GATE_A["state_of_charge"],
        },
        "prediction_metrics": {
            metric: gate["splits_for_comparison"][metric]
            for metric in gate["splits_for_comparison"]
        },
        "gate_a": {
            "thresholds_frozen_at_commit": gate["thresholds_frozen_at_commit"],
            "metrics": {
                metric: {
                    "n": result["n"],
                    "checks": result["checks"],
                    "max_abs": result["max_abs"],
                    "passed": result["passed"],
                }
                for metric, result in gate["metrics"].items()
            },
            "passed": gate["gate_a_passed"],
            "per_cell": {
                metric: result["diagnosis"]["by_cell"]
                for metric, result in gate["metrics"].items()
            },
        },
        "residual_summary": {
            "failure_clusters": holdout["failure_clusters"],
            "model_form_diagnosis": holdout["model_form_diagnosis"],
            "guardrail_counts": holdout["guardrail_counts"],
            "refusal_accuracy": holdout["refusal_accuracy"],
            "counts": holdout["counts"],
        },
        "uncertainty_summary": flagship["uncertainty"],
        "validation_envelope": {
            "terminal_voltage": {
                "region": flagship["envelope"]["terminal_voltage"]["coverage"][
                    "region"
                ]["region_id"],
                "supported_cells": flagship["envelope"]["supported_cells"],
                "failed_cells": flagship["envelope"]["failed_cells"],
                "envelope_id": flagship["envelope"]["terminal_voltage"]["envelope_id"],
                "campaign_report_digest": flagship["envelope"]["terminal_voltage"]["campaign_report_digest"],
            },
            "cell_temperature": {
                "envelope_id": flagship["envelope"]["cell_temperature"]["envelope_id"],
            },
            "flagship_query_point": flagship["envelope"]["query_point"],
            "flagship_classification": flagship["envelope"]["classification"],
            "boundary_points": flagship["envelope"]["boundary_points"],
        },
        "applicability": {
            "inside": {
                "ambient_temperature_c": preregistration["selection"][
                    "inside_ambient_c"
                ],
                "load_current_a": preregistration["selection"]["inside_current_a"],
                "charge_state_at_or_above": preregistration["selection"][
                    "applicability_charge_state_floor"
                ],
                "direction": "discharge and rest only",
                "max_cycle_index": preregistration["selection"][
                    "inside_max_cycle_index"
                ],
            },
            "outside": {
                "ambient_temperature_c": preregistration["selection"][
                    "outside_ambient_c"
                ],
                "below_charge_state": preregistration["selection"][
                    "applicability_charge_state_floor"
                ],
                "charge_direction": "any current below the declared rest band",
            },
            "undeclared": (
                "any cell chemistry, format or fixture other than the 18650 "
                "cells of this archive's own experiment groups; no evidence "
                "here speaks to one"
            ),
        },
        "numerical_evidence": flagship["numerical"],
        "replay": flagship["replay"],
        "trust_gates": flagship["trust"],
        "certification": flagship["certification"],
        "holdout": {
            "evaluation": (
                f"{prereg.CAMPAIGN_ID}.holdout.v{prereg.CAMPAIGN_VERSION}"
            ),
            "opening_digest": holdout["holdout_opening_digest"],
            "report_digest": holdout["report_digest"],
            "opened_once": True,
            "superseded_evaluation": (
                None
                if superseded is None
                else {
                    "why": (
                        "the parameter set behind it was fitted against a load "
                        "profile that differed from the executed one at rest; "
                        "the defect was found by a consistency test, not by any "
                        "holdout result. See the preregistration amendment "
                        "from version 3 to version 4"
                    ),
                    "result": {
                        metric: {
                            "checks": result["checks"],
                            "passed": result["passed"],
                        }
                        for metric, result in superseded["metrics"].items()
                    },
                    "gate_a_passed": superseded["gate_a_passed"],
                }
            ),
            "no_post_hoc_tuning": (
                "no threshold was revised after either opening, and no "
                "parameter was chosen by looking at a holdout residual"
            ),
        },
        "evidence_digests": {
            name: digest_of(name)
            for name in sorted(
                item
                for item in os.listdir(EVIDENCE)
                if item.endswith(".json")
            )
        },
    }

    text = json.dumps(record, indent=1, allow_nan=False)
    path = os.path.join(BENCH, "RESULT.json")
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")
    print(f"wrote {path}")
    print(f"verdict: {record['verdict']['sprint_3']}")
    print(f"failed:  {record['verdict']['what_failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
