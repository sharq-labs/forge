"""Gate A: score the locked holdout against the frozen acceptance policy.

Reads the campaign record and the preregistration and compares. It computes no
prediction and refits nothing: the numbers are the ones the campaign produced
and the thresholds are the ones committed before the holdout was opened.

The per-cell and per-region breakdowns below are diagnosis, not adjustment. A
threshold is not revised because a breakdown explains a failure.
"""

from __future__ import annotations

import collections
import json
import math
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import campaign as cmp  # noqa: E402
import prereg  # noqa: E402
from engcore.domains.battery import measurement as ms  # noqa: E402
from engcore.scientific.corpus import (  # noqa: E402
    Applicability,
    DatasetSplit,
    run_campaign,
    ValidationCampaign,
)

_GATE_KEYS = {
    ms.TERMINAL_VOLTAGE_METRIC: (
        ("mae", "mae_v", "mV", 1000.0),
        ("rmse", "rmse_v", "mV", 1000.0),
        ("p95", "p95_abs_v", "mV", 1000.0),
    ),
    ms.CELL_TEMPERATURE_METRIC: (
        ("mae", "mae_k", "K", 1.0),
        ("rmse", "rmse_k", "K", 1.0),
        ("p95", "p95_abs_k", "K", 1.0),
    ),
}


def statistics(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    count = len(values)
    index = min(count - 1, int(math.ceil(0.95 * count)) - 1)
    return {
        "n": count,
        "mae": sum(values) / count,
        "rmse": math.sqrt(sum(x * x for x in values) / count),
        "p95": values[max(index, 0)],
        "max": values[-1],
    }


def breakdown(report, dataset, *, split: str, metric: str):
    """Per-cell and per-region residuals, for diagnosis only."""
    cases = {case.case_id: case for case in dataset.cases}
    by_cell: dict[str, list[float]] = collections.defaultdict(list)
    by_rate: dict[str, list[float]] = collections.defaultdict(list)
    by_depth: dict[str, list[float]] = collections.defaultdict(list)
    by_phase: dict[str, list[float]] = collections.defaultdict(list)
    for item in report.comparisons:
        if item.split is not DatasetSplit(split) or item.metric != metric:
            continue
        if not item.verdict.is_scored or item.residual is None:
            continue
        case = cases[item.case_id]
        if case.applicability is not Applicability.INSIDE:
            continue
        residual = abs(float(item.residual))
        cell = next(
            (tag.split(":", 1)[1] for tag in case.tags if tag.startswith("cell:")),
            "unknown",
        )
        by_cell[cell].append(residual)
        rate = case.condition(ms.C_RATE).magnitude_in("1/hour")
        by_rate["2C" if rate >= 1.25 else "1C" if rate >= 0.25 else "rest"].append(
            residual
        )
        depth = case.condition(ms.DEPTH_OF_DISCHARGE).magnitude_in("dimensionless")
        by_depth[f"[{int(depth * 5) * 20}%,{int(depth * 5) * 20 + 20}%)"].append(
            residual
        )
        current = case.condition(ms.LOAD_CURRENT_MAGNITUDE).magnitude_in("ampere")
        by_phase["loaded" if current > 0.2 else "rest"].append(residual)
    return {
        "by_cell": {k: statistics(v) for k, v in sorted(by_cell.items())},
        "by_rate": {k: statistics(v) for k, v in sorted(by_rate.items())},
        "by_depth_of_discharge": {
            k: statistics(v) for k, v in sorted(by_depth.items())
        },
        "by_load_phase": {k: statistics(v) for k, v in sorted(by_phase.items())},
    }


def main() -> int:
    with open(os.path.join(EVIDENCE, "CAMPAIGN_HOLDOUT.json"), encoding="utf-8") as fh:
        campaign_record = json.load(fh)
    if not campaign_record["holdout_opened"]:
        raise SystemExit("Gate A scores the opened holdout; this record has none")

    # Rebuild the report so the breakdown can reach individual comparisons.
    selection, vendored, calibration, inventory = cmp.load_inputs()
    dataset = cmp.build_dataset(selection, vendored, inventory)
    if dataset.normalized_digest != campaign_record["dataset"]["normalized_digest"]:
        raise SystemExit(
            "the corpus has changed since the holdout was opened; the recorded "
            "result belongs to a dataset that no longer exists and scoring it "
            "against this one would be a different evaluation"
        )
    predictions, _runs, _keep = cmp.predict(
        dataset,
        selection,
        calibration,
        splits=["calibration", "validation", "locked_holdout"],
    )
    release = cmp.holdout_release(dataset)
    ledger = cmp.InMemoryHoldoutLedger(clock=lambda: "2026-09-21T00:00:00+00:00")
    campaign = ValidationCampaign(
        campaign_id=prereg.CAMPAIGN_ID,
        version=prereg.CAMPAIGN_VERSION,
        dataset=dataset,
        splits=(
            DatasetSplit.CALIBRATION,
            DatasetSplit.VALIDATION,
            DatasetSplit.LOCKED_HOLDOUT,
        ),
        holdout_release=release,
        description="Gate A rescoring of the opened locked holdout",
    )
    report = run_campaign(campaign.open_holdout(ledger), predictions)

    results: dict[str, Any] = {}
    verdicts: list[str] = []
    for metric, checks in _GATE_KEYS.items():
        gate = prereg.GATE_A[metric]
        measured = campaign_record["metrics"][metric]["locked_holdout"]
        rows = []
        for stat, key, unit, scale in checks:
            limit = gate[key]
            value = measured[stat]
            passed = value <= limit
            verdicts.append(f"{metric}.{stat}:{'PASS' if passed else 'FAIL'}")
            rows.append(
                {
                    "statistic": stat,
                    "value": value,
                    "value_display": f"{value * scale:.2f} {unit}",
                    "limit": limit,
                    "limit_display": f"{limit * scale:.2f} {unit}",
                    "passed": passed,
                }
            )
        results[metric] = {
            "n": measured["n"],
            "checks": rows,
            "max_abs": measured["max"],
            "max_abs_display": (
                f"{measured['max'] * checks[0][3]:.2f} {checks[0][2]}"
            ),
            "max_policy": prereg.GATE_A["max_error_policy"],
            "passed": all(row["passed"] for row in rows),
            "diagnosis": breakdown(
                report, dataset, split="locked_holdout", metric=metric
            ),
        }

    record = {
        "schema": "battery_thermal_flagship_s3_gate_a/1",
        "campaign_id": prereg.CAMPAIGN_ID,
        "campaign_version": prereg.CAMPAIGN_VERSION,
        "thresholds_frozen_at_commit": "1297648e",
        "thresholds_unchanged_since": (
            "the acceptance tolerances and every Gate A criterion were written "
            "in the first preregistration commit and no amendment touched one"
        ),
        "holdout_opening_digest": campaign_record["holdout_opening_digest"],
        "dataset_normalized_digest": campaign_record["dataset"]["normalized_digest"],
        "campaign_report_digest": campaign_record["report_digest"],
        "scope": prereg.GATE_A["scope"],
        "state_of_charge": prereg.GATE_A["state_of_charge"],
        "metrics": results,
        "splits_for_comparison": {
            metric: {
                split: campaign_record["metrics"][metric][split]
                for split in ("calibration", "validation", "locked_holdout")
            }
            for metric in _GATE_KEYS
        },
        "verdicts": verdicts,
        "gate_a_passed": all(item["passed"] for item in results.values()),
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    path = os.path.join(EVIDENCE, "GATE_A.json")
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")

    print("GATE A -- locked holdout, cases inside declared applicability")
    for metric, result in results.items():
        print(f"\n{metric}  n={result['n']}")
        for row in result["checks"]:
            print(
                f"  {row['statistic'].upper():5} {row['value_display']:>12} "
                f"limit {row['limit_display']:>12}   "
                f"{'PASS' if row['passed'] else 'FAIL'}"
            )
        print(f"  MAX   {result['max_abs_display']:>12}   reported, not gated")
        print("  by cell:")
        for cell, values in result["diagnosis"]["by_cell"].items():
            scale = 1000.0 if metric == ms.TERMINAL_VOLTAGE_METRIC else 1.0
            unit = "mV" if scale > 1 else "K"
            print(
                f"    {cell:7} n={values['n']:5d} MAE {values['mae'] * scale:8.2f} "
                f"RMSE {values['rmse'] * scale:8.2f} P95 {values['p95'] * scale:8.2f} {unit}"
            )
        print("  by rate:")
        for rate, values in result["diagnosis"]["by_rate"].items():
            scale = 1000.0 if metric == ms.TERMINAL_VOLTAGE_METRIC else 1.0
            unit = "mV" if scale > 1 else "K"
            print(
                f"    {rate:7} n={values['n']:5d} MAE {values['mae'] * scale:8.2f} "
                f"RMSE {values['rmse'] * scale:8.2f} P95 {values['p95'] * scale:8.2f} {unit}"
            )
    print(f"\nGATE A PASSED: {record['gate_a_passed']}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
