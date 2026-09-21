"""R2 + R3: establish a capacity and an initial state for every trajectory.

    python benchmarks/battery_voltage_s3_recovery/harness/state.py

Three things happen, in this order, and the order matters:

1. **The estimator's own spread is measured, on calibration cells only.** For
   every screened discharge of every calibration cell, the like-for-like prior
   capacity is compared with what that discharge actually delivered. The
   resulting relative spread is what every capacity record then carries as its
   standard uncertainty. It is measured, not assumed, and it is measured
   nowhere near a validation or holdout cell.

2. **The selection is built**, Sprint 3's in-band rows verbatim plus the
   low-ambient corner.

3. **A capacity and an initial state are established per trajectory**, from
   cycles that completed before it. A trajectory the authorities cannot answer
   for is recorded as UNKNOWN and carried as such; it is not dropped, because
   a corpus that silently loses the cases the model cannot start is a corpus
   that flatters it.

The locked holdout's rows are written with their identity and their state, but
this script reads the holdout's *first sample voltage and current* only -- the
two channels the initial-state authority needs -- and no other sample. It never
computes a residual, and the model does not exist yet when it runs.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import corpus as cp  # noqa: E402
from engcore.domains.battery.capacity import (  # noqa: E402
    CapacityBasis,
    establish_capacity,
)
from engcore.domains.battery.initial_state import InitialStateBasis  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402

STATE_AUTHORITY_SCHEMA = "battery_voltage_s3_recovery_state_authority/1"

#: Carried from the Sprint 3 preregistration, which froze both before any fit.
FULL_CHARGE_ANCHOR_V = 4.188513
FULL_CHARGE_BAND_V = 0.050


def calibration_cells(selection: dict[str, Any]) -> set[str]:
    return {
        row["cell"] for row in selection["selected"] if row["split"] == "calibration"
    }


def measure_estimator_spread(
    selection: dict[str, Any], inventory: dict[str, Any], trajectories
) -> dict[str, Any]:
    """The like-for-like estimator's error, measured on calibration cells.

    Every screened discharge of a calibration cell contributes one comparison
    between the capacity prior evidence predicts and the capacity that
    discharge delivered. No validation or holdout cell is read.
    """
    cells = calibration_cells(selection)
    errors: list[float] = []
    unknown = 0
    for item in trajectories:
        if item["cell"] not in cells:
            continue
        sequence = cp.sequence_of(inventory, item["cell"], item["cycle_index"])
        if sequence is None:
            continue
        state = establish_capacity(
            cell_id=item["cell"],
            experiment_id=item["group"],
            sequence=sequence,
            load_current=Quantity(abs(float(item["load_current_a"])), "ampere"),
            ambient_temperature=Quantity(
                float(item["ambient_temperature_c"]) + 273.15, "kelvin"
            ),
            prior_cycles=cp.prior_cycles_for(inventory, item["cell"], sequence),
        )
        if not state.is_known:
            unknown += 1
            continue
        predicted = state.initial_available_charge.magnitude_in("ampere_hour")
        delivered = float(item["delivered_ah"])
        errors.append((predicted - delivered) / delivered)

    absolute = sorted(abs(x) for x in errors)
    count = len(absolute)
    # A robust scale: the 68th percentile of |relative error|, which is the
    # one-sigma width of a distribution without assuming it is Gaussian and
    # without letting one anomalous cycle set the number.
    sigma = absolute[int(0.68 * (count - 1))] if count else None
    return {
        "measured_on": "calibration cells only",
        "cells": sorted(cells),
        "comparisons": count,
        "unknown": unknown,
        "median_relative_error": statistics.median(errors) if errors else None,
        "mean_relative_error": statistics.fmean(errors) if errors else None,
        "p68_absolute_relative_error": sigma,
        "p95_absolute_relative_error": (
            absolute[int(0.95 * (count - 1))] if count else None
        ),
        "max_absolute_relative_error": absolute[-1] if count else None,
        "adopted_relative_standard_uncertainty": sigma,
        "why": (
            "the spread of this estimator against the capacity it predicts, "
            "read off calibration cells. It is a measurement uncertainty on "
            "the capacity basis, not on any instrument: this source states no "
            "instrument accuracy and none is invented here"
        ),
    }


def termination_bands(
    selection: dict[str, Any], inventory: dict[str, Any]
) -> dict[str, Any]:
    """The early-stop charge regime, per corner, from calibration cells only.

    A charge that tapers to the declared termination current leaves the cell at
    the protocol's full-charge state and needs no band. A charge cut off above
    it does not, and two such charges are the same regime only if both stopped
    inside one declared interval. The interval's floor is the declared
    termination current; its ceiling is the highest early stop the calibration
    cells of that corner actually show. Nothing here reads a validation or
    holdout cell, so the ceiling cannot be widened by a case that needs it.
    """
    declared = float(inventory["declared_charge_termination"]["current_a"])
    ceilings: dict[str, float] = {}
    observed: dict[str, list[float]] = {}
    for row in selection["selected"]:
        if row["split"] != "calibration" or row.get("applicability") != "inside":
            continue
        sequence = cp.sequence_of(inventory, row["cell"], row["cycle_index"])
        if sequence is None:
            continue
        charge = cp.preceding_charge_row(inventory, row["cell"], sequence)
        if charge is None:
            continue
        final = float(charge["final_current_a"])
        setpoint = float(inventory["declared_charge_termination"]["voltage_v"])
        if abs(float(charge["final_voltage_v"]) - setpoint) > FULL_CHARGE_BAND_V:
            continue
        observed.setdefault(row["corner"], []).append(final)
        if final > declared:
            ceilings[row["corner"]] = max(ceilings.get(row["corner"], declared), final)
    return {
        "declared_termination_current_a": declared,
        "by_corner": {
            corner: {
                "band_a": [declared, ceilings.get(corner, declared)],
                "calibration_final_currents_a": sorted(values),
                "early_stops": sum(1 for v in values if v > declared),
            }
            for corner, values in sorted(observed.items())
        },
        "why": (
            "the ceiling is the highest early charge stop the calibration "
            "cells of that corner show; a trajectory whose charge stopped "
            "above it is refused rather than compared"
        ),
    }


def main() -> int:
    inventory = cp.cycle_inventory()
    trajectories = cp.normalized_trajectories()
    selection = cp.build_selection()

    spread = measure_estimator_spread(selection, inventory, trajectories)
    relative = spread["adopted_relative_standard_uncertainty"]
    bands = termination_bands(selection, inventory)

    by_id = {item["trajectory_id"]: item for item in trajectories}
    rows: list[dict[str, Any]] = []
    for row in selection["selected"]:
        if row.get("applicability") != "inside":
            continue
        trajectory = by_id.get(row["trajectory_id"])
        if trajectory is None:
            continue
        corner_band = bands["by_corner"].get(row["corner"], {}).get("band_a")
        capacity, initial = cp.establish_states(
            row,
            trajectory,
            inventory,
            full_charge_anchor_v=FULL_CHARGE_ANCHOR_V,
            anchor_tolerance_v=FULL_CHARGE_BAND_V,
            capacity_relative_uncertainty=relative,
            termination_current_band=(
                tuple(corner_band) if corner_band else None
            ),
        )
        rows.append(
            {
                "trajectory_id": row["trajectory_id"],
                "cell": row["cell"],
                "group": row["group"],
                "split": row["split"],
                "corner": row["corner"],
                "cycle_index": row["cycle_index"],
                "capacity": capacity.to_dict(),
                "capacity_digest": capacity.digest,
                "initial_state": initial.to_dict(),
                "initial_state_digest": initial.digest,
            }
        )

    unknown_capacity = [
        r["trajectory_id"]
        for r in rows
        if r["capacity"]["basis"] == CapacityBasis.UNKNOWN.value
    ]
    unknown_initial = [
        r["trajectory_id"]
        for r in rows
        if r["initial_state"]["basis"] == InitialStateBasis.UNKNOWN.value
    ]

    record = {
        "schema": STATE_AUTHORITY_SCHEMA,
        "what_this_is": (
            "one capacity state and one initial state per corpus trajectory, "
            "each read from cycles that completed before that trajectory ran"
        ),
        "archive_sha256": inventory["archive_sha256"],
        "cycle_inventory_sha256": selection["cycle_inventory_sha256"],
        "full_charge_anchor_v": FULL_CHARGE_ANCHOR_V,
        "full_charge_band_v": FULL_CHARGE_BAND_V,
        "capacity_estimator": spread,
        "charge_termination_bands": bands,
        "counts": {
            "trajectories": len(rows),
            "by_split": {
                split: sum(1 for r in rows if r["split"] == split)
                for split in sorted({r["split"] for r in rows})
            },
            "by_capacity_basis": {
                basis: sum(1 for r in rows if r["capacity"]["basis"] == basis)
                for basis in sorted({r["capacity"]["basis"] for r in rows})
            },
            "by_initial_state_basis": {
                basis: sum(1 for r in rows if r["initial_state"]["basis"] == basis)
                for basis in sorted({r["initial_state"]["basis"] for r in rows})
            },
        },
        "unknown_capacity": unknown_capacity,
        "unknown_initial_state": unknown_initial,
        "trajectories": rows,
    }

    _write(os.path.join(EVIDENCE, "SELECTION.json"), selection)
    _write(os.path.join(EVIDENCE, "BATTERY_STATE_AUTHORITY.json"), record)

    print(f"corpus: {json.dumps(selection['counts'])}")
    print(f"new locked holdout: {selection['new_locked_holdout_trajectories']}")
    print(
        f"capacity estimator on calibration cells: "
        f"n={spread['comparisons']} median {spread['median_relative_error']*100:+.2f}% "
        f"p68 {spread['p68_absolute_relative_error']*100:.2f}% "
        f"p95 {spread['p95_absolute_relative_error']*100:.2f}%"
    )
    print(f"capacity basis      : {record['counts']['by_capacity_basis']}")
    print(f"initial state basis : {record['counts']['by_initial_state_basis']}")
    if unknown_capacity:
        print(f"UNKNOWN capacity     : {unknown_capacity}")
    if unknown_initial:
        print(f"UNKNOWN initial state: {unknown_initial}")
    return 0


def _write(path: str, record: dict[str, Any]) -> None:
    text = json.dumps(record, indent=1, allow_nan=False)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
