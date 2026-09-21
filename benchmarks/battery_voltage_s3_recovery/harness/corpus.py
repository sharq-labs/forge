"""The recovery corpus: which trajectories, which split, and what state each starts in.

Splits
------
Sprint 3's in-band selection is taken **verbatim**. Its cells keep the roles
they were given before any model was fitted, and no cycle is added to or
removed from it here. Re-choosing it now, knowing how it turned out, is the
one thing that would make every later number meaningless.

Two things are added, and both are additions rather than revisions:

* the **low-ambient corner** of experiment group ``41_42_43_44``. Those cells
  ran the same protocol at 4 degC after their room-temperature phase, and
  Sprint 3 never selected a single one of those trajectories -- its ambient
  band stopped at 20 degC. B0042 is that group's calibration cell and B0043 its
  validation cell, so the corner inherits the split each cell already had.
* **B0041**, which appears in no Sprint 3 split, no guardrail list and no
  analysis. It is the new locked holdout.

B0044's low-ambient trajectories are *not* used. The cell's room-temperature
residuals have been read, so nothing measured on it is independent any more.

Why B0041 and nothing else
--------------------------
All eleven cells inside Sprint 3's declared ambient band were consumed by its
own three splits. There is no untouched room-temperature cell left in this
archive, and the selection rule that produces B0041 --

    the cells this archive contains that appear in no Sprint 3 split

-- has exactly one solution, so no outcome could have steered it.

Withholding
-----------
The holdout's *identity* is recorded here. Its measured channels are not
vendored by this module at all: :func:`load_development_corpus` refuses to
return a holdout trajectory, and the file that carries holdout channels is
written only by the opening step. A model cannot be selected against evidence
that is not on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Iterable, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
REPO = os.path.dirname(os.path.dirname(BENCH))
S3_EVIDENCE = os.path.join(
    REPO, "benchmarks", "battery_thermal_flagship_s3", "evidence"
)

sys.path.insert(0, HERE)

from engcore.domains.battery.capacity import (  # noqa: E402
    CapacityBasis,
    CellCapacityState,
    PriorCycle,
    establish_capacity,
)
from engcore.domains.battery.initial_state import (  # noqa: E402
    ChargeTerminationEvidence,
    InitialBatteryState,
    InitialStateBasis,
    RestVoltageEvidence,
    establish_initial_state,
)
from engcore.scientific.units.quantity import Quantity  # noqa: E402

SELECTION_SCHEMA = "battery_voltage_s3_recovery_selection/1"

#: The experiment group whose cells also ran at low ambient.
LOW_AMBIENT_GROUP = "41_42_43_44"

#: The low-ambient band this recovery adds, in degrees Celsius. Declared here,
#: before any low-ambient parameter is fitted.
LOW_AMBIENT_C = (0.0, 10.0)

#: Cells of the low-ambient group and the split each already holds. B0044 is
#: absent on purpose: it was the Sprint 3 locked holdout and has been read.
LOW_AMBIENT_SPLITS = {
    "B0042": "calibration",
    "B0043": "validation",
    "B0041": "locked_holdout",
}

#: Cycles taken per cell per low-ambient condition. Six, at evenly spaced
#: positions across the admitted list with both endpoints included -- the same
#: count and the same "spread across the range so drift is visible" intent as
#: Sprint 3's fixed positions, expressed as positions because the low-ambient
#: phases start at different cycle numbers on different cells.
LOW_AMBIENT_CYCLES_PER_CONDITION = 6

#: The Sprint 3 cells whose residuals have been read. Nothing measured on one
#: of them is independent evidence in this recovery.
OBSERVED_HOLDOUT_CELLS = ("B0007", "B0036", "B0044")

#: Declared charge termination, carried from the cycle inventory record.
_TERMINATION = None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def cycle_inventory() -> dict[str, Any]:
    return _load(os.path.join(EVIDENCE, "CYCLE_INVENTORY.json"))


def sprint3_selection() -> dict[str, Any]:
    return _load(os.path.join(S3_EVIDENCE, "DATA_SELECTION.json"))


def normalized_trajectories() -> list[dict[str, Any]]:
    """The full screened discharge set. Not committed: 60 MB of channels."""
    path = os.path.join(S3_EVIDENCE, "trajectories.json")
    if not os.path.exists(path):
        raise SystemExit(
            "benchmarks/battery_thermal_flagship_s3/evidence/trajectories.json "
            "is missing; regenerate it with that benchmark's acquire.py"
        )
    return _load(path)["trajectories"]


def even_positions(count: int, wanted: int) -> list[int]:
    """``wanted`` indices spread across ``range(count)``, endpoints included."""
    if count <= 0:
        return []
    if count <= wanted:
        return list(range(count))
    return sorted(
        {round(index * (count - 1) / (wanted - 1)) for index in range(wanted)}
    )


def low_ambient_selection(
    trajectories: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The added corner, by the rule declared above and nothing else."""
    low, high = LOW_AMBIENT_C
    pool: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for item in trajectories:
        if item["group"] != LOW_AMBIENT_GROUP:
            continue
        if not low <= item["ambient_temperature_c"] <= high:
            continue
        if item["cell"] not in LOW_AMBIENT_SPLITS:
            continue
        condition = round(abs(item["load_current_a"]) * 2.0) / 2.0
        pool.setdefault((item["cell"], condition), []).append(item)

    selected: list[dict[str, Any]] = []
    for key, items in sorted(pool.items()):
        items.sort(key=lambda row: row["cycle_index"])
        for index in even_positions(len(items), LOW_AMBIENT_CYCLES_PER_CONDITION):
            item = items[index]
            selected.append(
                {
                    "trajectory_id": item["trajectory_id"],
                    "cell": item["cell"],
                    "group": item["group"],
                    "cycle_index": item["cycle_index"],
                    "ambient_temperature_c": item["ambient_temperature_c"],
                    "load_current_a": item["load_current_a"],
                    "split": LOW_AMBIENT_SPLITS[item["cell"]],
                    "corner": "low_ambient",
                    "applicability": "inside",
                    "admit_cell_temperature": True,
                }
            )
    return selected


def sprint3_inside_selection() -> list[dict[str, Any]]:
    """Sprint 3's selection, unchanged except that its holdout is renamed.

    Sprint 3's ``locked_holdout`` split has been opened and read. Carrying that
    label forward would let a later step treat an observed result as a sealed
    one, which is the single most dangerous confusion available in this
    recovery. Those rows become ``observed_holdout``: usable as historical
    diagnostic evidence under R17, never as independent validation and never as
    the new Gate A.
    """
    out: list[dict[str, Any]] = []
    for item in sprint3_selection()["selected"]:
        row = dict(item)
        row["corner"] = "room_ambient"
        if row["split"] == "locked_holdout":
            row["split"] = "observed_holdout"
            row["why_reclassified"] = (
                "opened and scored in Sprint 3; its residuals are in "
                "GATE_A.json and have been read"
            )
        out.append(row)
    return out


def build_selection() -> dict[str, Any]:
    trajectories = normalized_trajectories()
    room = sprint3_inside_selection()
    low = low_ambient_selection(trajectories)
    combined = room + low
    ids = [row["trajectory_id"] for row in combined]
    if len(ids) != len(set(ids)):
        raise SystemExit("a trajectory reached the recovery corpus twice")

    by_split: dict[str, set[str]] = {}
    for row in combined:
        by_split.setdefault(row["split"], set()).add(row["cell"])
    crossing = sorted(
        cell
        for cell in set().union(*by_split.values())
        if sum(1 for split in by_split.values() if cell in split) > 1
    )
    if crossing:
        raise SystemExit(f"cells in more than one split: {crossing}")

    holdout = sorted(
        row["trajectory_id"] for row in combined if row["split"] == "locked_holdout"
    )
    return {
        "schema": SELECTION_SCHEMA,
        "base_selection": "benchmarks/battery_thermal_flagship_s3/evidence/DATA_SELECTION.json",
        "base_selection_sha256": sha256_file(
            os.path.join(S3_EVIDENCE, "DATA_SELECTION.json")
        ),
        "cycle_inventory_sha256": sha256_file(
            os.path.join(EVIDENCE, "CYCLE_INVENTORY.json")
        ),
        "low_ambient_band_c": list(LOW_AMBIENT_C),
        "low_ambient_cycles_per_condition": LOW_AMBIENT_CYCLES_PER_CONDITION,
        "low_ambient_splits": dict(LOW_AMBIENT_SPLITS),
        "observed_holdout_cells_excluded": list(OBSERVED_HOLDOUT_CELLS),
        "selected": combined,
        "counts": {
            "room_ambient": len(room),
            "low_ambient": len(low),
            "by_split": {
                split: sum(1 for row in combined if row["split"] == split)
                for split in sorted({row["split"] for row in combined})
            },
        },
        "new_locked_holdout_trajectories": holdout,
    }


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Capacity and initial state, per trajectory, from prior cycles only.
# ---------------------------------------------------------------------------


def prior_cycles_for(
    inventory: dict[str, Any], cell: str, sequence: int
) -> list[PriorCycle]:
    rows = inventory["cells"][cell]
    out: list[PriorCycle] = []
    for row in rows:
        if row.get("unreadable"):
            continue
        if row["sequence"] >= sequence:
            continue
        if row["kind"] not in ("discharge", "charge"):
            continue
        out.append(
            PriorCycle(
                cycle_id=f"{cell}.s{row['sequence']:04d}.{row['kind']}",
                sequence=int(row["sequence"]),
                kind=row["kind"],
                throughput=Quantity(float(row["throughput_ah"]), "ampere_hour"),
                load_current=(
                    Quantity(float(row["load_current_a"]), "ampere")
                    if row["kind"] == "discharge"
                    else None
                ),
                ambient_temperature=(
                    Quantity(float(row["ambient_c"]) + 273.15, "kelvin")
                    if row["kind"] == "discharge"
                    else None
                ),
                provenance=f"NASA PCoE {cell} cycle position {row['sequence']}",
            )
        )
    return out


def sequence_of(inventory: dict[str, Any], cell: str, cycle_index: int) -> int | None:
    for row in inventory["cells"][cell]:
        if row["kind"] == "discharge" and row["discharge_index"] == cycle_index:
            return int(row["sequence"])
    return None


def preceding_charge_row(
    inventory: dict[str, Any], cell: str, sequence: int
) -> dict[str, Any] | None:
    best = None
    for row in inventory["cells"][cell]:
        if row["sequence"] >= sequence or row.get("unreadable"):
            continue
        if row["kind"] == "charge":
            if best is None or row["sequence"] > best["sequence"]:
                best = row
        elif row["kind"] == "discharge" and best is not None and row["sequence"] > best["sequence"]:
            best = None
    return best


def cycle_at(inventory: dict[str, Any], cell: str, sequence: int) -> dict[str, Any] | None:
    for row in inventory["cells"][cell]:
        if row["sequence"] == sequence:
            return row
    return None


def _termination_of(
    inventory: dict[str, Any],
    cell: str,
    sequence: int,
    anchor_tolerance_v: float,
) -> ChargeTerminationEvidence | None:
    """The charge that immediately precedes ``sequence`` on ``cell``."""
    charge_row = preceding_charge_row(inventory, cell, sequence)
    if charge_row is None:
        return None
    declared = inventory["declared_charge_termination"]
    return ChargeTerminationEvidence(
        cycle_id=f"{cell}.s{charge_row['sequence']:04d}.charge",
        final_current=Quantity(float(charge_row["final_current_a"]), "ampere"),
        final_voltage=Quantity(float(charge_row["final_voltage_v"]), "volt"),
        declared_termination_current=Quantity(float(declared["current_a"]), "ampere"),
        declared_termination_voltage=Quantity(float(declared["voltage_v"]), "volt"),
        termination_voltage_tolerance=Quantity(anchor_tolerance_v, "volt"),
        provenance=declared["source"],
    )


def establish_states(
    row: dict[str, Any],
    trajectory: dict[str, Any],
    inventory: dict[str, Any],
    *,
    full_charge_anchor_v: float,
    anchor_tolerance_v: float,
    capacity_relative_uncertainty: float | None,
    termination_current_band: tuple[float, float] | None = None,
) -> tuple[CellCapacityState, InitialBatteryState]:
    cell = row["cell"]
    sequence = sequence_of(inventory, cell, row["cycle_index"])
    if sequence is None:
        raise SystemExit(
            f"{row['trajectory_id']} has no cycle in the inventory; the "
            "capacity authority cannot be given prior evidence for it"
        )
    capacity = establish_capacity(
        cell_id=cell,
        experiment_id=row["group"],
        sequence=sequence,
        load_current=Quantity(abs(float(row["load_current_a"])), "ampere"),
        ambient_temperature=Quantity(
            float(row["ambient_temperature_c"]) + 273.15, "kelvin"
        ),
        prior_cycles=prior_cycles_for(inventory, cell, sequence),
        nominal_capacity=Quantity(2.0, "ampere_hour"),
        relative_standard_uncertainty=capacity_relative_uncertainty,
    )

    termination = _termination_of(inventory, cell, sequence, anchor_tolerance_v)

    # The cycle the usable capacity was measured on, and how it was charged.
    # A charge cut off early says nothing on its own; it says something only
    # against the charge that preceded the measurement it is reusing.
    reference_termination = None
    reference_rest_voltage = None
    if capacity.is_known and capacity.source_evidence:
        evidence = capacity.source_evidence[0]
        reference_termination = _termination_of(
            inventory, cell, evidence.sequence, anchor_tolerance_v
        )
        evidence_row = cycle_at(inventory, cell, evidence.sequence)
        if evidence_row is not None and "first_voltage_v" in evidence_row:
            reference_rest_voltage = Quantity(
                float(evidence_row["first_voltage_v"]), "volt"
            )

    band = None
    if termination_current_band is not None:
        band = (
            Quantity(float(termination_current_band[0]), "ampere"),
            Quantity(float(termination_current_band[1]), "ampere"),
        )

    channels = trajectory["channels"]
    rest = RestVoltageEvidence(
        voltage=Quantity(float(channels["voltage_v"][0]), "volt"),
        current=Quantity(abs(float(channels["current_a"][0])), "ampere"),
        rest_current_floor=Quantity(
            float(inventory["rest_current_floor_a"]), "ampere"
        ),
        full_charge_anchor=Quantity(full_charge_anchor_v, "volt"),
        anchor_tolerance=Quantity(anchor_tolerance_v, "volt"),
        provenance=f"first sample of {row['trajectory_id']}",
    )
    initial = establish_initial_state(
        cell_id=cell,
        experiment_id=row["group"],
        trajectory_id=row["trajectory_id"],
        capacity=capacity,
        charge_termination=termination,
        rest_voltage=rest,
        state_of_charge_standard_uncertainty=capacity_relative_uncertainty,
        reference_charge_termination=reference_termination,
        reference_rest_voltage=reference_rest_voltage,
        termination_current_band=band,
    )
    return capacity, initial


# ---------------------------------------------------------------------------
# Loading, with the holdout withheld.
# ---------------------------------------------------------------------------


class HoldoutWithheld(RuntimeError):
    """A development path asked for a locked-holdout trajectory."""


def load_development_corpus(
    selection: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Channels for calibration and validation. Never for the holdout."""
    wanted = {
        row["trajectory_id"]
        for row in selection["selected"]
        if row["split"] in ("calibration", "validation")
    }
    out: dict[str, dict[str, Any]] = {}
    for item in normalized_trajectories():
        if item["trajectory_id"] in wanted:
            out[item["trajectory_id"]] = item
    missing = sorted(wanted - set(out))
    if missing:
        raise SystemExit(f"development trajectories not in the corpus: {missing}")
    return out


def refuse_holdout(selection: dict[str, Any], trajectory_ids: Iterable[str]) -> None:
    """Raise if any id belongs to the locked holdout."""
    locked = set(selection["new_locked_holdout_trajectories"])
    trespass = sorted(set(trajectory_ids) & locked)
    if trespass:
        raise HoldoutWithheld(
            "these trajectories belong to the locked holdout and are not "
            f"available before it is opened: {trespass}"
        )


__all__ = [
    "LOW_AMBIENT_C",
    "LOW_AMBIENT_CYCLES_PER_CONDITION",
    "LOW_AMBIENT_SPLITS",
    "OBSERVED_HOLDOUT_CELLS",
    "SELECTION_SCHEMA",
    "HoldoutWithheld",
    "build_selection",
    "cycle_inventory",
    "establish_states",
    "even_positions",
    "load_development_corpus",
    "low_ambient_selection",
    "normalized_trajectories",
    "prior_cycles_for",
    "refuse_holdout",
    "sequence_of",
    "sha256_file",
    "sprint3_inside_selection",
]
