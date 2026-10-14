"""Build the cross-cell roles exactly as preregistered. Nothing is fitted here.

``python -m benchmarks.battery_1rc_crosscell.data --raw-dir <bol25 dir>`` writes data/*.json (+ .sha256): ocv_cal, calibration,
heldout_gitt25, heldout_gitt5, heldout_own_ocv and exclusions. The three WINDOW roles (calibration, heldout_gitt25,
heldout_gitt5; ~67 MB at the native 0.1 s sampling) are not committed: their .sha256 pins are, and ``load`` refuses any
rebuild that does not reproduce them byte for byte. The descriptive own-OCV role holds each held-out cell's own Q and
knots only; its windows are the primary windows re-expressed on that Q (z_own = 1 - (1 - z) Q_cal / Q_own).

Deviations recorded before any fit (both found while building the roles; no model had been run):
1. a temperature dropout outside a pulse cannot be "excluded from the applicability check" without handing the route an
   invented temperature, so EVERY window holding a dropout is excluded. This is stricter on applicability, but it is NOT
   free: it removes held-out windows the preregistration would have scored (removing evidence can hide a failure). The
   windows it removed are labelled "temperature dropout only in the rest (deviation 1)" and counted, and the dropout
   samples of every file are counted, in data/exclusions.json. A strictly conservative alternative for a future
   preregistration is to keep such windows with UNKNOWN applicability (which makes their set NOT_ASSESSABLE);
2. the Expt 2,2 files log, at every rest -> discharge edge, one sample 2 ms before the first load sample with I = 0 but an
   on-load voltage (67-84 mV below the rest). It made every Expt 2,2 window fail the 1 mV relaxation screen. Found by
   reading the raw samples at the step edges of the HELD-OUT Expt 2,2 cells after the first build excluded 50 of their
   windows (22 + 22 of the 25-pulse, 3 + 3 of the 5-pulse) as "not relaxed"; no voltage was compared with any model.
   This partly unblinded the held-out cells before the calibration fit: the edges show on-load drops of 67-84 mV at
   2.5 A (an R0 proxy of ~27-34 mOhm). It could not steer the fit: the objective, bounds, starts and rules were frozen,
   and all eight starts converge to one optimum (results/CALIBRATION.json). Such records are dropped by one uniform rule in ``read`` (the census
   finds them only in the Expt 2,2 files: 25 + 5 per cell).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import numpy as np

from .prereg import CAL_CELLS, HELD_CELLS, PREREG_PATH

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
PREREG = json.loads(PREREG_PATH.read_bytes())
REST_BAND = PREREG["construction"]["rest_band_A"]
T_LO, T_HI = 15.0, 40.0
Z_MIN = 0.10


def prereg_sha256() -> str:
    return hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()


def fname(cell: str, test: str) -> str:
    expt, c = cell.split("/")
    return f"{expt} - cell {c} - RPT0 - {test} 0.5C discharge data.csv"


def read(raw_dir: pathlib.Path, name: str) -> dict[str, np.ndarray]:
    raw = (raw_dir / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PREREG["data"]["files_sha256"][name]:
        raise ValueError(f"{name} is not the preregistered file")
    a = np.genfromtxt(raw.decode("utf-8").splitlines(), delimiter=",", skip_header=1)
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name}: non-finite value")
    t = a[:, 0]
    if np.any(np.diff(t) <= 0):
        raise ValueError(f"{name}: time is not strictly increasing")
    i = -a[:, 2] / 1000.0
    i[np.abs(i) <= REST_BAND] = 0.0
    v = a[:, 1]
    # A zero-current sample < 50 ms before a load sample, already > 5 mV below the sample before it, is a step-transition
    # record logged with the wrong current (on-load voltage, I = 0). Dropped and counted, never re-labelled.
    k = np.arange(1, len(t) - 1)
    bad = k[(i[k] == 0) & (i[k + 1] != 0) & (t[k + 1] - t[k] < 0.05) & (v[k] < v[k - 1] - 0.005)]
    keep = np.ones(len(t), bool)
    keep[bad] = False
    temp = a[keep, 4]
    return {"t": t[keep], "v": v[keep], "i": i[keep], "temp": temp, "transition_records_dropped": int(len(bad)),
            "dropout_samples": int(np.sum((temp < T_LO) | (temp > T_HI)))}


def runs_of(i: np.ndarray) -> list[tuple[int, int, int]]:
    """(start, stop, sign) of contiguous runs of rest (0), discharge (+1) or charge (-1)."""
    sgn = np.sign(i).astype(int)
    out, s = [], 0
    for k in range(1, len(sgn) + 1):
        if k == len(sgn) or sgn[k] != sgn[s]:
            out.append((s, k, int(sgn[s])))
            s = k
    return out


def start_and_charge(d) -> tuple[int, np.ndarray]:
    """Index of the last sample of the post-charge rest, and the discharged charge (Ah) from there (backward hold)."""
    runs = runs_of(d["i"])
    first_dch = next(k for k, r in enumerate(runs) if r[2] == 1)
    if first_dch == 0 or runs[first_dch - 1][2] != 0:
        raise ValueError("the first discharge pulse has no preceding rest")
    s0 = runs[first_dch - 1][1] - 1
    q = np.zeros_like(d["t"])
    q[s0 + 1:] = np.cumsum(d["i"][s0 + 1:] * np.diff(d["t"][s0:])) / 3600.0
    return s0, q


def rest_knots(d, s0: int, z: np.ndarray) -> list[tuple[float, float]]:
    knots = [(float(z[s0]), float(d["v"][s0]))]
    for a, b, sign in runs_of(d["i"]):
        if a > s0 and sign == 0 and d["t"][b - 1] - d["t"][a] >= 3000.0:
            knots.append((float(z[b - 1]), float(d["v"][b - 1])))
    return knots


def windows(d, s0: int, z: np.ndarray, z_lo: float, cell: str, test: str, nominal_s: float, exclusions: list):
    out = []
    runs = runs_of(d["i"])
    for k, (a, b, sign) in enumerate(runs):
        if sign != 1 or a <= s0:
            continue
        tag = {"cell": cell, "test": test, "pulse_start_s": float(d["t"][a])}
        prev = runs[k - 1] if k else None
        nxt = runs[k + 1] if k + 1 < len(runs) else None
        dur = float(d["t"][b - 1] - d["t"][a])
        reason = None
        if dur < 0.95 * nominal_s:
            reason = f"truncated pulse ({dur:.1f} s)"
        elif prev is None or prev[2] != 0 or d["t"][prev[1] - 1] - d["t"][prev[0]] < 3000.0:
            reason = "the pulse is not preceded by a rest of >= 3000 s"
        elif nxt is None or nxt[2] != 0 or d["t"][nxt[1] - 1] - d["t"][nxt[0]] < 600.0:
            reason = "no 600 s rest after the pulse"
        if reason is None:
            wa = int(np.searchsorted(d["t"], d["t"][prev[1] - 1] - 60.0))
            wb = int(np.searchsorted(d["t"], d["t"][nxt[0]] + 600.0, side="right"))
            if abs(d["v"][prev[1] - 1] - d["v"][wa]) > 0.001:
                reason = f"not relaxed ({1000 * (d['v'][prev[1] - 1] - d['v'][wa]):.2f} mV over the last 60 s)"
            elif np.any((d["temp"][a:b] < T_LO) | (d["temp"][a:b] > T_HI)):
                reason = "temperature dropout inside the pulse"
            elif np.any((d["temp"][wa:wb] < T_LO) | (d["temp"][wa:wb] > T_HI)):
                reason = "temperature dropout only in the rest (deviation 1)"
            elif z[wb - 1] < max(Z_MIN, z_lo) or z[wa] > 1.0 + 1e-12:
                reason = f"SOC outside the declared scope (z {z[wa]:.3f} -> {z[wb - 1]:.3f})"
        if reason:
            exclusions.append({**tag, "reason": reason})
            continue
        out.append({**tag, "time_s": (d["t"][wa:wb] - d["t"][wa]).tolist(), "current_A": d["i"][wa:wb].tolist(),
                    "voltage_V": d["v"][wa:wb].tolist(), "temperature_C": d["temp"][wa:wb].tolist(),
                    "z0": float(z[wa])})
    return out


def build(raw_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    base = {"preregistration_sha256": prereg_sha256()}
    exclusions: list = []
    transitions: dict[str, int] = {}
    dropouts: dict[str, int] = {}

    def read_counted(cell: str, test: str):
        doc = read(raw_dir, fname(cell, test))
        transitions[f"{cell} {test}"] = doc["transition_records_dropped"]
        dropouts[f"{cell} {test}"] = doc["dropout_samples"]
        return doc

    cal = {}
    for cell in CAL_CELLS:
        d = read_counted(cell, "25-pulse GITT")
        s0, q = start_and_charge(d)
        cal[cell] = (d, s0, q)
    q_cal = float(np.mean([q[-1] for _, _, q in cal.values()]))
    per_cell_knots = {cell: rest_knots(d, s0, 1.0 - q / q_cal) for cell, (d, s0, q) in cal.items()}
    n = max(len(k) for k in per_cell_knots.values())
    if any(len(k) != n for k in per_cell_knots.values()):
        raise ValueError("the calibration cells do not share one knot structure: knot-by-knot averaging refused")
    for j in range(n):
        zs = [k[j][0] for k in per_cell_knots.values()]
        if max(zs) - min(zs) > 0.01:
            raise ValueError(f"knot {j} is not at one SOC across the calibration cells: averaging refused")
    knots = []
    for j in range(n):
        pts = [k[j] for k in per_cell_knots.values() if len(k) > j]
        knots.append((float(np.mean([p[0] for p in pts])), float(np.mean([p[1] for p in pts])), len(pts)))
    knots = sorted(knots)
    z_lo = knots[0][0]
    ocv = {**base, "role": "ocv_cal", "q_cal_Ah": q_cal, "knots_z_V_cells": knots,
           "per_cell_q_Ah": {c: float(q[-1]) for c, (_, _, q) in cal.items()}}
    calibration = {**base, "role": "calibration", "q_Ah": q_cal, "windows": []}
    for cell, (d, s0, q) in cal.items():
        calibration["windows"] += windows(d, s0, 1.0 - q / q_cal, z_lo, cell, "25-pulse GITT", 288.0, exclusions)
    g25 = {**base, "role": "heldout_gitt25", "q_Ah": q_cal, "windows": []}
    g5 = {**base, "role": "heldout_gitt5", "q_Ah": q_cal, "windows": []}
    own = {**base, "role": "heldout_own_ocv", "cells": {}}
    for cell in HELD_CELLS:
        d = read_counted(cell, "25-pulse GITT")
        s0, q = start_and_charge(d)
        g25["windows"] += windows(d, s0, 1.0 - q / q_cal, z_lo, cell, "25-pulse GITT", 288.0, exclusions)
        q_own = float(q[-1])
        own["cells"][cell] = {"q_own_Ah": q_own, "knots_z_V": sorted(rest_knots(d, s0, 1.0 - q / q_own))}
        d5 = read_counted(cell, "5-pulse GITT")
        s05, q5 = start_and_charge(d5)
        g5["windows"] += windows(d5, s05, 1.0 - q5 / q_cal, z_lo, cell, "5-pulse GITT", 1440.0, exclusions)
    return {"ocv_cal": ocv, "calibration": calibration, "heldout_gitt25": g25, "heldout_gitt5": g5,
            "heldout_own_ocv": own,
            "exclusions": {**base, "role": "exclusions", "excluded": exclusions,
                           "transition_records_dropped": transitions,
                           "dropout_samples_per_file": dropouts,
                           "deviations": [
                               "every window holding a temperature dropout is excluded: stricter on applicability than "
                               "the preregistered wording (which cannot be met without inventing a temperature), but it "
                               "removes windows the preregistration would have scored; those are labelled 'only in the "
                               "rest (deviation 1)'",
                               "a zero-current sample < 50 ms before a load sample and > 5 mV below the sample before it "
                               "is a step-transition record logged with the wrong current; it is dropped (found in the "
                               "held-out Expt 2,2 files after the first build excluded 50 of their windows as not "
                               "relaxed; no model had been run; this partly unblinded those cells: on-load drops of "
                               "67-84 mV at 2.5 A were seen before the calibration fit)"]}}


def write_all(docs) -> dict[str, str]:
    DATA.mkdir(exist_ok=True)
    out = {}
    for name, doc in docs.items():
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        (DATA / f"{name}.json").write_bytes(data)
        out[name] = hashlib.sha256(data).hexdigest()
        (DATA / f"{name}.sha256").write_bytes((out[name] + "\n").encode())
    return out


def load(name: str) -> dict[str, Any]:
    data = (DATA / f"{name}.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != (DATA / f"{name}.sha256").read_bytes().split()[0].decode():
        raise ValueError(f"data/{name}.json does not match its pinned digest")
    doc = json.loads(data)
    if doc["preregistration_sha256"] != prereg_sha256():
        raise ValueError(f"data/{name}.json was built under another preregistration")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", required=True, type=pathlib.Path)
    docs = build(parser.parse_args().raw_dir)
    digests = write_all(docs)
    import collections
    print(json.dumps({"q_cal_Ah": docs["ocv_cal"]["q_cal_Ah"], "knots": len(docs["ocv_cal"]["knots_z_V_cells"]),
                      "counts": {n: len(d["windows"]) for n, d in docs.items() if "windows" in d},
                      "exclusion_reasons": collections.Counter(e["reason"].split(" (")[0]
                                                               for e in docs["exclusions"]["excluded"]),
                      "digests": digests}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
