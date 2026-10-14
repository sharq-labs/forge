"""Build every role of the LG HG2 identifiability experiment exactly as preregistered. Nothing is fitted here.

``python -m benchmarks.battery_1rc_identifiability.data --raw-dir <dir with the five CSV files>`` writes data/*.json
(+ .sha256): ocv, calibration, heldout_pulses, heldout_cc, descriptive, and exclusions. A window or test that a frozen
rule excludes is recorded with its reason, never repaired.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import numpy as np

from .lghg2 import read
from .prereg import PREREG, PREREG_PATH

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
C = PREREG["construction"]
REST_BAND = float(C["rest_band_A"])
LEVELS = (3.0, 6.0, 12.0, 18.0)
ROLE_OF_LEVEL = {3.0: "calibration", 18.0: "calibration", 6.0: "heldout_pulses", 12.0: "heldout_pulses"}
Z_MIN = 0.10


def prereg_sha256() -> str:
    return hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()


def forge_current(measured: np.ndarray) -> np.ndarray:
    out = -np.asarray(measured, float)
    out[np.abs(out) <= REST_BAND] = 0.0
    return out


def runs_of(rec) -> list[tuple[int, int, int, str]]:
    """(start, stop, step, status) for each contiguous (step, status) run."""
    out, s = [], 0
    for k in range(1, len(rec.step) + 1):
        if k == len(rec.step) or rec.step[k] != rec.step[s] or rec.status[k] != rec.status[s]:
            out.append((s, k, int(rec.step[s]), rec.status[s]))
            s = k
    return out


def coulomb(t: np.ndarray, i: np.ndarray) -> np.ndarray:
    """Cumulative discharged charge (Ah) at every sample, backward hold."""
    return np.concatenate([[0.0], np.cumsum(i[1:] * np.diff(t))]) / 3600.0


def _window(rec, i, z, a, b, **meta) -> dict[str, Any]:
    return {"time_s": (rec.prog_time_s[a:b] - rec.prog_time_s[a]).tolist(), "current_A": i[a:b].tolist(),
            "voltage_V": rec.voltage_v[a:b].tolist(), "temperature_C": rec.temperature_c[a:b].tolist(),
            "z0": float(z[a]), **meta}


def build(raw_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    files = PREREG["data"]["files"]
    hppc = read(raw_dir / "549_HPPC.csv")
    if hppc.sha256 != files["549_HPPC.csv"]:
        raise ValueError("549_HPPC.csv is not the preregistered file")
    i = forge_current(hppc.current_a)
    q = coulomb(hppc.prog_time_s, i)
    q_hppc = float(q[-1])
    z = 1.0 - q / q_hppc
    runs = runs_of(hppc)
    base = {"preregistration_sha256": prereg_sha256(), "q_hppc_Ah": q_hppc,
            "source": {"file": "549_HPPC.csv", "sha256": hppc.sha256, "dropped_exact_duplicates":
                       hppc.dropped_exact_duplicates, "repeated_stamps": hppc.repeated_stamps,
                       "max_repeat_disagreement_V_A_Ah": list(hppc.max_repeat_disagreement)}}
    # OCV knots: last sample of the first rest and of every rest >= 3000 s
    knots = []
    for idx, (a, b, step, status) in enumerate(runs):
        if status == "PAU" and (idx == 0 or hppc.prog_time_s[b - 1] - hppc.prog_time_s[a] >= 3000.0):
            knots.append((float(z[b - 1]), float(hppc.voltage_v[b - 1]), int(b - 1)))
    knots.sort()
    ocv = {**base, "role": "ocv", "knots_z_V_sample": knots}
    zlo, zhi = knots[0][0], knots[-1][0]
    roles = {r: {**base, "role": r, "windows": []} for r in ("calibration", "heldout_pulses", "descriptive")}
    excluded = []

    def rest_before(idx: int) -> float:
        total = 0.0
        k = idx - 1
        while k >= 0 and runs[k][3] == "PAU":
            a, b = runs[k][0], runs[k][1]
            total += hppc.prog_time_s[b - 1] - hppc.prog_time_s[a] + (hppc.prog_time_s[b] - hppc.prog_time_s[b - 1]
                                                                       if b < len(hppc.prog_time_s) else 0.0)
            k -= 1
        return total

    for idx, (a, b, step, status) in enumerate(runs):
        if status != "DCH":
            continue
        level_current = float(np.median(i[a:b]))
        duration = float(hppc.prog_time_s[b - 1] - hppc.prog_time_s[a])
        if abs(level_current - 0.9) < 0.05:                            # the SOC step between levels: descriptive only
            if idx + 1 < len(runs) and runs[idx + 1][3] == "PAU" and idx >= 1 and runs[idx - 1][3] == "PAU":
                pa, pb = runs[idx - 1][0], runs[idx + 1][1]
                if z[pa] >= Z_MIN and zlo <= z[pb - 1] and rest_before(idx) >= 590.0:
                    roles["descriptive"]["windows"].append(_window(hppc, i, z, pb - 1 - (pb - 1 - (runs[idx - 1][1] - 1)),
                                                                   pb, kind="soc_step", level_A=0.9))
            continue
        nearest = min(LEVELS, key=lambda lv: abs(lv - level_current))
        tag = {"level_A": nearest, "step": step, "z_start": float(z[a])}
        reason = None
        if duration < 9.5 or abs(level_current - nearest) > 0.01 * nearest:
            reason = f"truncated or off-level pulse (duration {duration:.2f} s, median {level_current:.3f} A)"
        elif not (idx >= 1 and runs[idx - 1][3] == "PAU" and idx + 1 < len(runs) and runs[idx + 1][3] == "PAU"):
            reason = "the pulse is not bracketed by rest steps"
        elif z[runs[idx - 1][0]] < Z_MIN:
            reason = f"SOC {z[runs[idx - 1][0]]:.3f} below the declared 0.10"
        elif rest_before(idx - 1) + (hppc.prog_time_s[runs[idx - 1][1] - 1] - hppc.prog_time_s[runs[idx - 1][0]]) < 590.0:
            reason = "less than 590 s of rest before the pulse"
        else:
            pa, pb = runs[idx - 1][0], runs[idx - 1][1]
            if abs(hppc.voltage_v[pb - 1] - hppc.voltage_v[pa]) > 0.001:
                reason = (f"not relaxed: the pre-pulse rest moves "
                          f"{1000 * (hppc.voltage_v[pb - 1] - hppc.voltage_v[pa]):.2f} mV")
            elif not (zlo <= z[runs[idx + 1][1] - 1] and z[pa] <= zhi):
                reason = "the window leaves the measured OCV knot range"
        if reason:
            excluded.append({**tag, "reason": reason})
            continue
        wa, wb = runs[idx - 1][0], runs[idx + 1][1]
        roles[ROLE_OF_LEVEL[nearest]]["windows"].append(_window(hppc, i, z, wa, wb, kind="pulse", **tag))
    # constant-current held-out tests
    cc = {**base, "role": "heldout_cc", "tests": []}
    cap = read(raw_dir / "551_Cap_1C.csv")
    if cap.sha256 != files["551_Cap_1C.csv"]:
        raise ValueError("551_Cap_1C.csv is not the preregistered file")
    ci = forge_current(cap.current_a)
    crun = runs_of(cap)
    if crun[0][3] != "PAU":
        excluded.append({"test": "551_Cap_1C", "reason": "does not start at rest"})
    else:
        dch = next(r for r in crun if r[3] == "DCH")
        a, b = crun[0][0], dch[1]
        cz = 1.0 - coulomb(cap.prog_time_s[a:b], ci[a:b]) / q_hppc
        stop = next((k for k, x in enumerate(cz) if x < Z_MIN), len(cz))
        cc["tests"].append({"test": "551_Cap_1C", "sha256": cap.sha256, "truncated_at_z_below": Z_MIN,
                            "time_s": (cap.prog_time_s[a:a + stop] - cap.prog_time_s[a]).tolist(),
                            "current_A": ci[a:a + stop].tolist(), "voltage_V": cap.voltage_v[a:a + stop].tolist(),
                            "temperature_C": cap.temperature_c[a:a + stop].tolist(), "z0": 1.0})
    c20 = read(raw_dir / "549_C20DisCh.csv")
    if c20.sha256 != files["549_C20DisCh.csv"]:
        raise ValueError("549_C20DisCh.csv is not the preregistered file")
    if runs_of(c20)[0][3] != "PAU":
        excluded.append({"test": "549_C20DisCh", "sha256": c20.sha256,
                         "reason": "the file starts inside the discharge step (no preceding rest), so the "
                                   "preregistered initial-state rule cannot be met"})
    return {"ocv": ocv, **roles, "heldout_cc": cc,
            "exclusions": {**base, "role": "exclusions", "excluded": excluded,
                           "preregistered_exclusions": PREREG["excluded_with_reason"]}}


def write_all(docs: dict[str, dict[str, Any]]) -> dict[str, str]:
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
    summary = {n: (len(d.get("windows", d.get("tests", d.get("knots_z_V_sample", d.get("excluded", []))))))
               for n, d in docs.items()}
    print(json.dumps({"counts": summary, "q_hppc_Ah": docs["ocv"]["q_hppc_Ah"], "digests": digests}, indent=1))
    print(json.dumps(docs["exclusions"]["excluded"], indent=0)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
