"""Build one role's measured trajectories from the importer's canonical records, exactly as preregistered.

``python -m benchmarks.battery_1rc_closure.data --role calibration --canonical-dir <dir>`` writes
``data/<role>.json`` (+ .sha256). Nothing is fitted here. Every refusal is recorded with its reason; a refused cycle
is never repaired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

from .prereg import PREREG, PREREG_PATH

HERE = pathlib.Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
TC = PREREG["trajectory_construction"]
REST_BAND = float(TC["rest_band_A"])
V0_MIN = float(TC["screen_initial_rest_voltage_min_V"])


class CycleRefused(ValueError):
    pass


def prereg_sha256() -> str:
    return hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()


def forge_current(measured: float) -> float:
    """Forge convention: positive = discharge. NASA records discharge as negative."""
    if abs(measured) <= REST_BAND:
        return 0.0
    if measured > 0.0:
        raise CycleRefused(f"charge-direction current {measured!r} A beyond the {REST_BAND} A rest band")
    return -measured


def integrated_charge_ah(cycle: dict[str, Any]) -> float:
    """Charge a discharge record delivered, from its measured current with the backward hold (rest band applied)."""
    t, i = cycle["channels"]["Time"], cycle["channels"]["Current_measured"]
    return sum(max(0.0, -x) * (t[k] - t[k - 1]) for k, x in enumerate(i) if k and abs(x) > REST_BAND) / 3600.0


def build_cycle(cycle: dict[str, Any], capacity_basis_ah: float) -> dict[str, Any]:
    ch = cycle["channels"]
    t, v, i, temp = ch["Time"], ch["Voltage_measured"], ch["Current_measured"], ch["Temperature_measured"]
    if not (len(t) == len(v) == len(i) == len(temp)) or len(t) < 3:
        raise CycleRefused("channels are not aligned or too short")
    if any(b <= a for a, b in zip(t, t[1:])):
        raise CycleRefused("time is not strictly increasing")
    if v[0] < V0_MIN:
        raise CycleRefused(f"initial rest voltage {v[0]!r} V is below the {V0_MIN} V full-charge screen")
    if abs(i[0]) > REST_BAND:
        raise CycleRefused(f"the record does not start at rest (I0 = {i[0]!r} A)")
    current = [forge_current(x) for x in i]
    loaded = [k for k, x in enumerate(current) if x > 0.0]
    if not loaded:
        raise CycleRefused("no discharge current in a discharge cycle")
    first = loaded[0]
    if not v[first] < v[0]:
        raise CycleRefused("sign check failed: the voltage did not fall when the declared discharge current started")
    delivered = sum(current[k] * (t[k] - t[k - 1]) for k in range(1, len(t))) / 3600.0   # backward hold
    if delivered > capacity_basis_ah:
        raise CycleRefused(f"the record delivers {delivered:.4f} Ah, more than the capacity basis "
                           f"{capacity_basis_ah:.4f} Ah: SOC would leave [0, 1]")
    return {"time_s": list(t), "current_A": current, "voltage_V": list(v), "temperature_C": list(temp),
            "capacity_basis_Ah": capacity_basis_ah, "delivered_Ah_backward_hold": delivered,
            "ambient_temperature_degC": cycle["ambient_temperature_degC"], "cycle_index": cycle["cycle_index"]}


def build_role(role: str, canonical_dir: pathlib.Path) -> dict[str, Any]:
    spec = PREREG["roles"][role]
    lo, hi = spec["discharge_ordinals"]
    out = {"schema": "forge.battery_1rc_closure.trajectories/1", "preregistration_sha256": prereg_sha256(),
           "role": role, "cells": {}, "cycles": [], "refused": []}
    for cell in spec["cells"]:
        path = canonical_dir / f"{cell}.canonical.json"
        record = json.loads(path.read_bytes())
        out["cells"][cell] = {"canonical_sha256": record["canonical_sha256"], "source": record["source"],
                              "canonical_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        discharges = [c for c in record["cycles"] if c["cycle_type"] == "discharge"]
        for ordinal, cycle in enumerate(discharges[:hi], start=1):
            if ordinal < lo:
                continue
            basis = max(integrated_charge_ah(c) for c in discharges[:ordinal - 1])
            try:
                built = build_cycle(cycle, basis)
            except CycleRefused as exc:
                out["refused"].append({"cell": cell, "ordinal": ordinal, "cycle_index": cycle["cycle_index"],
                                       "reason": str(exc)})
                continue
            out["cycles"].append({"cell": cell, "ordinal": ordinal, **built})
    return out


def write(doc: dict[str, Any], role: str) -> str:
    DATA_DIR.mkdir(exist_ok=True)
    data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    (DATA_DIR / f"{role}.json").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (DATA_DIR / f"{role}.sha256").write_bytes((digest + "\n").encode())
    return digest


def load(role: str) -> dict[str, Any]:
    data = (DATA_DIR / f"{role}.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != (DATA_DIR / f"{role}.sha256").read_bytes().split()[0].decode():
        raise ValueError(f"data/{role}.json does not match its pinned digest")
    doc = json.loads(data)
    if doc["preregistration_sha256"] != prereg_sha256():
        raise ValueError("the trajectories were built under another preregistration")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=sorted(PREREG["roles"].keys() - {"capacity_source_only",
                                                                                          "ageing_window"}))
    parser.add_argument("--canonical-dir", required=True, type=pathlib.Path)
    args = parser.parse_args()
    doc = build_role(args.role, args.canonical_dir)
    digest = write(doc, args.role)
    print(json.dumps({"role": args.role, "cycles": len(doc["cycles"]), "refused": doc["refused"], "sha256": digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
