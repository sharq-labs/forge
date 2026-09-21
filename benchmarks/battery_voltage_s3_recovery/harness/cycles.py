"""Prior-cycle evidence: every cycle of every cell, in the order it ran.

The capacity and initial-state authorities read evidence that completed before
the trajectory they are asked about. That evidence is not in the Sprint 3
corpus: ``trajectories.json`` holds discharges only, already screened, and a
charge cycle -- which is what witnesses how a cell was brought to its starting
state -- appears nowhere in it.

This script makes one pass over the archive and records, per cell, the ordered
list of **all** its cycles with the few numbers the two authorities need:

* the order they ran in, which is what makes a cycle prior;
* how much charge crossed the terminals, and in which direction;
* for a discharge, the load level and the ambient it ran at;
* for a charge, where the charger stopped -- its last current and voltage.

It does no science. It applies no screen, keeps no opinion about which cycles
are usable, and never looks at a residual.

    python benchmarks/battery_voltage_s3_recovery/harness/cycles.py
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile

import numpy as np
import scipy.io as sio

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")

ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"
CYCLE_INVENTORY_SCHEMA = "battery_voltage_s3_recovery_cycles/1"

#: The charger's declared termination, from the archive READMEs: constant
#: current 1.5 A to 4.2 V, then constant voltage until the current falls to
#: 20 mA. Read off the source's own description of the protocol, not fitted.
DECLARED_TERMINATION_CURRENT_A = 0.020
DECLARED_TERMINATION_VOLTAGE_V = 4.2

#: A sample carrying at least this much current is part of a charge's
#: constant-current phase rather than its constant-voltage tail.
CHARGE_CC_MIN_A = 1.0

#: Below this the cell is at rest. The composition pack's own rest band.
REST_CURRENT_FLOOR_A = 0.2


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_members(path: str) -> dict[str, bytes]:
    payload = open(path, "rb").read()
    digest = sha256_bytes(payload)
    if digest != ARCHIVE_SHA256:
        raise SystemExit(
            f"archive digest {digest} does not match the pinned {ARCHIVE_SHA256}"
        )
    members: dict[str, bytes] = {}
    outer = zipfile.ZipFile(io.BytesIO(payload))
    for name in outer.namelist():
        if not name.endswith(".zip"):
            continue
        inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
        for member in inner.namelist():
            if member.lower().endswith(".mat"):
                members.setdefault(
                    f"{os.path.basename(name)}::{os.path.basename(member)}",
                    inner.read(member),
                )
    return members


def channels(cycle):
    data = cycle.data
    try:
        arrays = {
            "t": np.atleast_1d(np.asarray(data.Time, dtype=float)),
            "v": np.atleast_1d(np.asarray(data.Voltage_measured, dtype=float)),
            "i": np.atleast_1d(np.asarray(data.Current_measured, dtype=float)),
        }
    except AttributeError:
        return None
    n = min(len(v) for v in arrays.values())
    if n < 2:
        return None
    out = {k: v[:n] for k, v in arrays.items()}
    if not all(np.all(np.isfinite(v)) for v in out.values()):
        return None
    if np.any(np.diff(out["t"]) <= 0.0):
        return None
    return out


def throughput_ah(t: np.ndarray, i: np.ndarray) -> float:
    return float(np.sum(0.5 * (np.abs(i[1:]) + np.abs(i[:-1])) * np.diff(t) / 3600.0))


def main() -> int:
    archive = os.environ.get("FORGE_S3_ARCHIVE", "D:/forge-s3-data/nasa_battery.zip")
    members = read_members(archive)
    cells: dict[str, list[dict]] = {}
    for key in sorted(members):
        cell = os.path.basename(key.split("::")[1])[:-4]
        if cell in cells:
            continue
        mat = sio.loadmat(
            io.BytesIO(members[key]), squeeze_me=True, struct_as_record=False
        )
        names = [n for n in mat if not n.startswith("__")]
        rows: list[dict] = []
        discharge_index = 0
        for position, cycle in enumerate(list(mat[names[0]].cycle)):
            kind = str(cycle.type)
            if kind == "discharge":
                discharge_index += 1
            series = channels(cycle)
            row: dict = {
                "sequence": position,
                "kind": kind,
                "ambient_c": float(cycle.ambient_temperature),
                "discharge_index": discharge_index if kind == "discharge" else None,
            }
            if series is not None:
                t, v, i = series["t"], series["v"], series["i"]
                loaded = np.abs(i) > REST_CURRENT_FLOOR_A
                row.update(
                    {
                        "throughput_ah": round(throughput_ah(t, i), 6),
                        "load_current_a": (
                            round(float(np.median(np.abs(i[loaded]))), 4)
                            if int(loaded.sum())
                            else 0.0
                        ),
                        "final_current_a": round(float(abs(i[-1])), 5),
                        "final_voltage_v": round(float(v[-1]), 5),
                        "first_current_a": round(float(abs(i[0])), 5),
                        "first_voltage_v": round(float(v[0]), 5),
                        "samples": int(t.size),
                    }
                )
                if kind == "charge":
                    cc = np.abs(i) >= CHARGE_CC_MIN_A
                    row["cc_throughput_ah"] = (
                        round(throughput_ah(t[cc], i[cc]), 6)
                        if int(cc.sum()) > 1
                        else 0.0
                    )
            else:
                row["unreadable"] = True
            rows.append(row)
        cells[cell] = rows
        print(f"  {cell}: {len(rows)} cycles", file=sys.stderr)

    record = {
        "schema": CYCLE_INVENTORY_SCHEMA,
        "archive_sha256": ARCHIVE_SHA256,
        "what_this_is": (
            "every cycle of every cell in the order it ran, with the charge "
            "that crossed the terminals and where the charger stopped. This is "
            "the evidence the capacity and initial-state authorities read, and "
            "it is prior evidence only by virtue of the sequence recorded here"
        ),
        "declared_charge_termination": {
            "current_a": DECLARED_TERMINATION_CURRENT_A,
            "voltage_v": DECLARED_TERMINATION_VOLTAGE_V,
            "source": "the archive READMEs: CC 1.5 A to 4.2 V then CV to 20 mA",
        },
        "rest_current_floor_a": REST_CURRENT_FLOOR_A,
        "cells": cells,
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    out = os.path.join(EVIDENCE, "CYCLE_INVENTORY.json")
    os.makedirs(EVIDENCE, exist_ok=True)
    with open(out, "wb") as handle:
        handle.write(payload)
    print(f"wrote {out}: {len(cells)} cells, "
          f"{sum(len(v) for v in cells.values())} cycles")
    print(f"sha256 {sha256_bytes(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
