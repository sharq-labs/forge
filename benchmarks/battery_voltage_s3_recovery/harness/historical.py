"""R17: re-run Sprint 3's opened holdout, labelled for what it is.

Sprint 3's locked holdout -- B0007, B0036, B0044 -- was opened and read. Running
the recovery model on it says something worth knowing: whether the mechanism
that failed there was addressed. It says nothing about whether the recovery model
is independently validated, because those cells' residuals were read before this
model existed and every decision in the recovery was made by somebody who knew
them.

So this runs **outside the campaign machinery on purpose.** ``DatasetSplit`` has
three values and none of them means "observed holdout"; placing these cells in a
VALIDATION split would make Core call the result validation, which is exactly
the confusion R17 exists to prevent. The record below carries
``evidence_class: historical_diagnostic`` and ``satisfies_gate_a: false``, and a
regression asserts that a reader cannot mistake one for the other.

    python benchmarks/battery_voltage_s3_recovery/harness/historical.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import statistics
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
REPO = os.path.dirname(os.path.dirname(BENCH))
sys.path.insert(0, HERE)

import candidates as cd  # noqa: E402
import corpus as cp  # noqa: E402
import predict as pr  # noqa: E402
from engcore.domains.battery import flagship_ocv_v2 as ocv_v2  # noqa: E402
from engcore.domains.battery import flagship_v2 as model_v2  # noqa: E402

HISTORICAL_SCHEMA = "battery_voltage_s3_recovery_historical_diagnostic/1"

#: The label this record carries everywhere. R17's words.
EVIDENCE_CLASS = "historical_diagnostic"

S3_EVIDENCE = os.path.join(
    REPO, "benchmarks", "battery_thermal_flagship_s3", "evidence"
)


def load(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def statistics_of(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    count = len(ordered)
    index = min(count - 1, int(math.ceil(0.95 * count)) - 1)
    return {
        "n": count,
        "mae": sum(ordered) / count,
        "rmse": math.sqrt(sum(x * x for x in ordered) / count),
        "p95": ordered[max(index, 0)],
        "max": ordered[-1],
    }


def main() -> int:
    prereg = load(os.path.join(EVIDENCE, "NEW_GATE_A_PREREGISTRATION.json"))
    state = load(os.path.join(EVIDENCE, "BATTERY_STATE_AUTHORITY.json"))
    selection = load(os.path.join(EVIDENCE, "SELECTION.json"))
    s3_gate = load(os.path.join(S3_EVIDENCE, "GATE_A.json"))

    states = {row["trajectory_id"]: row for row in state["trajectories"]}
    parameters = prereg["frozen_parameters"]
    rows = [
        row
        for row in selection["selected"]
        if row["split"] == "observed_holdout" and row.get("applicability") == "inside"
    ]
    channels = {
        item["trajectory_id"]: item
        for item in cp.normalized_trajectories()
        if item["trajectory_id"] in {row["trajectory_id"] for row in rows}
    }

    absolute: dict[str, list[float]] = collections.defaultdict(list)
    signed: dict[str, list[float]] = collections.defaultdict(list)
    temperature_abs: dict[str, list[float]] = collections.defaultdict(list)
    refused: list[dict[str, Any]] = []
    scored_trajectories = 0

    for row in sorted(rows, key=lambda r: r["trajectory_id"]):
        tid = row["trajectory_id"]
        record = states.get(tid)
        trajectory = channels.get(tid)
        if record is None or trajectory is None:
            continue
        if record["capacity"]["basis"] == "unknown":
            refused.append({"trajectory_id": tid, "why": "capacity UNKNOWN"})
            continue
        if record["initial_state"]["basis"] == "unknown":
            refused.append({"trajectory_id": tid, "why": "initial state UNKNOWN"})
            continue
        band = ocv_v2.band_for(
            float(row["ambient_temperature_c"]), float(row["load_current_a"])
        )
        unit = (
            f"{row['group']}|{row['corner']}|"
            f"{round(abs(float(row['load_current_a'])) * 2.0) / 2.0:g}A"
        )
        fitted = parameters.get(unit, {}).get("fitted")
        if fitted is None:
            refused.append(
                {"trajectory_id": tid, "why": f"no parameter set for block {unit}"}
            )
            continue

        ch = trajectory["channels"]
        currents = [-x for x in ch["current_a"]]
        voltages = ch["voltage_v"]
        temperatures = [x + 273.15 for x in ch["temperature_c"]]
        admissible = [
            cd.channel_consistent(currents, voltages, index)
            for index in range(len(voltages))
        ]
        instants, voltage, temperature, charge, refusal = pr.march(
            cell_id=row["cell"],
            band=band,
            times_s=ch["time_s"],
            currents_a=currents,
            ambient_k=float(row["ambient_temperature_c"]) + 273.15,
            initial_temperature_k=temperatures[0],
            parameters=fitted,
            available_charge_ah=float(
                record["capacity"]["initial_available_charge_ah"]
            ),
            initial_state_of_charge=float(
                record["initial_state"]["initial_state_of_charge"]
            ),
        )
        floor = ocv_v2.OCV_V2_CURVES[band].lower
        scored_trajectories += 1
        for offset in range(len(voltage)):
            index = offset + 1
            if charge[offset] < floor or not admissible[index]:
                continue
            delta = voltage[offset] - voltages[index]
            absolute[row["cell"]].append(abs(delta))
            signed[row["cell"]].append(delta)
            if row.get("admit_cell_temperature", True):
                temperature_abs[row["cell"]].append(
                    abs(temperature[offset] - temperatures[index])
                )

    pooled = [v for values in absolute.values() for v in values]
    pooled_signed = [v for values in signed.values() for v in values]
    pooled_temperature = [v for values in temperature_abs.values() for v in values]

    aggregate = statistics_of(pooled)
    aggregate["bias"] = (
        sum(pooled_signed) / len(pooled_signed) if pooled_signed else None
    )
    per_cell = {}
    for cell, values in sorted(absolute.items()):
        entry = statistics_of(values)
        entry["bias"] = sum(signed[cell]) / len(signed[cell])
        per_cell[cell] = entry

    sprint3 = {
        cell: {
            "mae": values["mae"],
            "rmse": values["rmse"],
            "p95": values["p95"],
        }
        for cell, values in s3_gate["metrics"]["terminal_voltage"]["diagnosis"][
            "by_cell"
        ].items()
    }
    comparison = {}
    for cell, now in per_cell.items():
        then = sprint3.get(cell)
        if then is None:
            continue
        comparison[cell] = {
            "sprint3_rmse_v": then["rmse"],
            "recovery_rmse_v": now["rmse"],
            "change_v": now["rmse"] - then["rmse"],
            "change_percent": round(
                (now["rmse"] - then["rmse"]) / then["rmse"] * 100.0, 1
            ),
        }

    record = {
        "schema": HISTORICAL_SCHEMA,
        "evidence_class": EVIDENCE_CLASS,
        "satisfies_gate_a": False,
        "what_this_is": (
            "the recovery model run on the cells Sprint 3 opened as its locked "
            "holdout. It says whether the mechanism that failed there was "
            "addressed"
        ),
        "what_this_is_not": (
            "independent validation, and it cannot satisfy any Gate A. These "
            "cells' residuals were read before this model existed and every "
            "decision in this recovery was taken by somebody who knew them. "
            "Sprint 3's own round report names B0044's capacity gap as the "
            "failure, so B0044 in particular shaped the direction of this work"
        ),
        "why_outside_the_campaign_machinery": (
            "DatasetSplit has three values and none means observed holdout. "
            "Placing these cells in a VALIDATION split would make Core call this "
            "result validation, which is the confusion R17 exists to prevent"
        ),
        "model": prereg["model"],
        "cells": sorted(absolute),
        "trajectories_scored": scored_trajectories,
        "refused": refused,
        "aggregate_voltage": aggregate,
        "per_cell_voltage": per_cell,
        "aggregate_temperature": statistics_of(pooled_temperature),
        "sprint3_comparison": comparison,
        "reading": (
            "the comparison is per cell and against Sprint 3's own recorded "
            "per-cell numbers. It is a statement about a mechanism, not a "
            "verdict about a model"
        ),
    }

    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    path = os.path.join(EVIDENCE, "HISTORICAL_DIAGNOSTIC.json")
    with open(path, "wb") as handle:
        handle.write(payload)

    print(f"wrote {path}")
    print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    print(f"evidence class: {EVIDENCE_CLASS}   satisfies Gate A: False")
    print()
    print("HISTORICAL DIAGNOSTIC -- Sprint 3's opened holdout, recovery model")
    print(
        f"  aggregate voltage n={aggregate.get('n', 0)} "
        f"MAE {aggregate.get('mae', 0)*1000:.2f} RMSE {aggregate.get('rmse', 0)*1000:.2f} "
        f"P95 {aggregate.get('p95', 0)*1000:.2f} mV "
        f"bias {(aggregate.get('bias') or 0)*1000:+.2f} mV"
    )
    print(f"{'cell':8} {'S3 RMSE':>10} {'now RMSE':>10} {'change':>10} {'now bias':>10}")
    for cell, values in comparison.items():
        print(
            f"{cell:8} {values['sprint3_rmse_v']*1000:>10.2f} "
            f"{values['recovery_rmse_v']*1000:>10.2f} "
            f"{values['change_percent']:>9.1f}% "
            f"{per_cell[cell]['bias']*1000:>10.2f}"
        )
    for row in refused:
        print(f"  refused {row['trajectory_id']}: {row['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
