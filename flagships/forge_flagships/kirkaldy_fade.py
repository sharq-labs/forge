"""BIG 14 study on flagship A: the throughput-Arrhenius fade model against Kirkaldy 2024 LG M50T ageing data (pre-registered).

Everything is fixed in ``data/big14_a_kirkaldy_fade_preregistration.json`` (commit ``dd53eec7``, pushed before any capacity
value was read): the archives (by Zenodo md5), the calibration set (Expt 5, constant-current cycle ageing), the holdout set
(Expt 4, drive-cycle ageing, different cells), the definitions of capacity, fade, throughput and temperature, the fit and the
acceptance criteria. The model is ``engcore.domains.battery.throughput_fade.ThroughputArrheniusFade``'s law,
``fade = k_q * Q * exp(-Ea / R * (1/T - 1/T_ref))``, evaluated here directly on per-checkpoint aggregates; the result is a study
record, not an admitted Forge evidence record.

The archives are read in place (``zipfile``); only the processed summaries are opened, and nothing is executed from them.

    python -m forge_flagships.kirkaldy_fade --data D:/forge-data/kirkaldy2024/raw --out <dir>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_kirkaldy_fade_preregistration.json")
GAS_CONSTANT = 8.314462618          # J/(mol K), as engcore.domains.battery.throughput_fade uses
T_REF = 298.15
EA_BOUNDS = (0.0, 200e3)             # J/mol, pre-registered
FLAGSHIP_DECLARED = {"k_q_per_Ah_abs_current": 2e-4, "activation_energy_J_per_mol": 30e3}
ALIGN_TOL_AH = 10.0                  # an RPT is placed on the cycle rows only within about one full cycle (charge + discharge)
_SUMMARY = re.compile(r"^Expt (\d+) - cell ([A-Z]+) \((\d+)degC\) - Processed Data\.csv$")


def load_preregistration() -> tuple[dict, str]:
    with open(PREREGISTRATION, "rb") as fh:
        raw = fh.read()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def _digests(path: str) -> dict:
    md5, sha = hashlib.md5(), hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(1 << 24)
            if not buf:
                break
            md5.update(buf)
            sha.update(buf)
    return {"md5": md5.hexdigest(), "sha256": sha.hexdigest(), "bytes": os.path.getsize(path)}


def admit(raw_dir: str, prereg: dict) -> dict:
    """Each archive is admitted only if its md5 equals the pre-registered Zenodo md5."""
    out = {}
    for role in ("calibration_set", "holdout_set"):
        entry = prereg["data"][role]
        path = os.path.join(raw_dir, entry["archive"])
        got = _digests(path)
        if got["md5"] != entry["zenodo_md5"]:
            raise SystemExit(f"{entry['archive']} is not the pre-registered archive (md5 {got['md5']})")
        out[role] = {"archive": entry["archive"], **got}
    return out


def _float(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def _rows(z: zipfile.ZipFile, name: str) -> tuple[list[dict], str]:
    blob = z.read(name)
    return list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))), hashlib.sha256(blob).hexdigest()


def read_cells(archive: str) -> dict:
    """Per cell: the setpoint, and one checkpoint per RPT with discharge throughput, C/10 capacity and the measured temperature."""
    cells = {}
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        for name in names:
            base = name.rsplit("/", 1)[-1]
            m = _SUMMARY.match(base)
            if not m or "/Summary Data/Performance Summary/" not in name:
                continue
            expt, cell, temp_c = m.group(1), m.group(2), int(m.group(3))
            perf, perf_sha = _rows(z, name)
            (cycle_name,) = [n for n in names if n.endswith(f"/Summary per Cycle/expt {expt} - cell {cell} - cycle_data.csv")]
            cycles, cycle_sha = _rows(z, cycle_name)
            # The cycle numbering restarts per set and runs through cycler fault rows, so it cannot place an RPT. Rows stay in file
            # order and each RPT is placed where the cumulative charge + discharge of the cycle rows reaches the RPT file's own
            # throughput; the discharge charge up to that row is the pre-registered throughput.
            discharge = np.array([_float(r["Discharge Capacity [A h]"]) or 0.0 for r in cycles])
            charge = np.array([_float(r["Charge Capacity [A h]"]) or 0.0 for r in cycles])
            cum_total, cum_dis = np.cumsum(discharge + charge), np.cumsum(discharge)
            checkpoints, skipped = [], []
            for r in perf:
                n_cycles = int(float(r["Ageing Cycles"]))
                rpt = int(float(r["Ageing Sets"]))
                q_total_file = _float(r["Charge Throughput [A h]"]) or 0.0
                if q_total_file == 0.0:
                    q_dis, gap = 0.0, 0.0
                else:
                    i = int(np.argmin(np.abs(cum_total - q_total_file)))
                    q_dis, gap = float(cum_dis[i]), float(cum_total[i] - q_total_file)
                if abs(gap) > ALIGN_TOL_AH:
                    skipped.append({"rpt": rpt, "reason": f"the cycle file does not reach this RPT's throughput ({gap:+.1f} A h at its nearest row; "
                                                          f"tolerance {ALIGN_TOL_AH} A h): its discharge throughput is not measured, so it is not estimated"})
                    continue
                cap = _float(r["C/10 Capacity [mA h]"])
                if cap is None:
                    skipped.append({"rpt": rpt, "reason": "no C/10 capacity in the processed summary"})
                    continue
                checkpoints.append({"rpt": rpt, "ageing_cycles": n_cycles, "discharge_throughput_Ah": q_dis, "alignment_gap_Ah": gap,
                                    "abs_current_throughput_Ah": q_total_file,
                                    "capacity_mAh": cap, "measured_set_temperature_C": _float(r.get("Age set av. temperature [°C]", ""))})
            if not checkpoints or checkpoints[0]["rpt"] != 0:
                raise SystemExit(f"Expt {expt} cell {cell}: no beginning-of-life capacity")
            c0 = checkpoints[0]["capacity_mAh"]
            for c in checkpoints:
                c["fade"] = 1.0 - c["capacity_mAh"] / c0
            cells[f"expt{expt}-{cell}"] = {"expt": int(expt), "cell": cell, "setpoint_C": temp_c, "setpoint_K": temp_c + 273.15,
                                           "checkpoints": checkpoints, "skipped": skipped,
                                           "sources": {base: perf_sha, cycle_name.rsplit("/", 1)[-1]: cycle_sha}}
    if not cells:
        raise SystemExit(f"no processed summaries found in {archive}")
    return cells


def _design(cells: dict, throughput: str = "discharge_throughput_Ah") -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    q, t, y, keys = [], [], [], []
    for key in sorted(cells):
        for c in cells[key]["checkpoints"]:
            q.append(c[throughput])
            t.append(cells[key]["setpoint_K"])
            y.append(c["fade"])
            keys.append((key, c["rpt"]))
    return np.array(q), np.array(t), np.array(y), keys


def predict(k: float, ea: float, q: np.ndarray, t: np.ndarray) -> np.ndarray:
    return k * q * np.exp(-ea / GAS_CONSTANT * (1.0 / t - 1.0 / T_REF))


def fit(cells: dict) -> dict:
    """Ordinary least squares over every calibration checkpoint, all temperatures jointly; k > 0, Ea in [0, 200] kJ/mol."""
    from scipy.optimize import least_squares

    q, t, y, _ = _design(cells)
    scale = float(np.sum(y * q) / np.sum(q * q)) if np.any(q) else 1e-5
    scale = scale if scale > 0 else 1e-5

    def residual(x):
        return predict(x[0] * scale, x[1] * 1e3, q, t) - y

    best = None
    for ea0 in (5.0, 30.0, 60.0, 120.0):                        # multistart in kJ/mol; the best of the four is kept
        r = least_squares(residual, x0=[1.0, ea0], bounds=([1e-9, EA_BOUNDS[0] / 1e3], [np.inf, EA_BOUNDS[1] / 1e3]), method="trf")
        if best is None or r.cost < best.cost:
            best = r
    k, ea = float(best.x[0] * scale), float(best.x[1] * 1e3)
    res = residual(best.x)
    return {"k_q_per_Ah_discharge": k, "activation_energy_J_per_mol": ea,
            "activation_energy_at_bound": bool(ea <= EA_BOUNDS[0] + 1.0 or ea >= EA_BOUNDS[1] - 1.0),
            "calibration_rmse": float(np.sqrt(np.mean(res ** 2))), "n_checkpoints": int(len(y)), "success": bool(best.success)}


def holdout(cells: dict, k: float, ea: float, throughput: str = "discharge_throughput_Ah") -> dict:
    q, t, y, keys = _design(cells, throughput)
    res = predict(k, ea, q, t) - y
    per_temp = {}
    for temp in sorted(set(t)):
        sel = t == temp
        per_temp[f"{temp - 273.15:.0f}C"] = {"n": int(sel.sum()), "mean_signed_residual": float(res[sel].mean()),
                                             "rmse": float(np.sqrt(np.mean(res[sel] ** 2))), "max_abs_residual": float(np.abs(res[sel]).max())}
    rows = [{"cell": key, "rpt": rpt, "throughput_Ah": float(qq), "measured_fade": float(yy), "predicted_fade": float(yy + rr)}
            for (key, rpt), qq, yy, rr in zip(keys, q, y, res)]
    return {"pooled_rmse": float(np.sqrt(np.mean(res ** 2))), "max_abs_residual": float(np.abs(res).max()), "n_checkpoints": int(len(y)),
            "per_temperature": per_temp, "rows": rows}


def judge(prereg: dict, hold: dict) -> dict:
    c1 = hold["pooled_rmse"] <= 0.015
    c2 = {name: abs(v["mean_signed_residual"]) <= 0.010 for name, v in hold["per_temperature"].items()}
    met = c1 and all(c2.values())
    return {"C1": {"criterion": prereg["acceptance"]["C1"], "observed": hold["pooled_rmse"], "met": c1},
            "C2": {"criterion": prereg["acceptance"]["C2"], "observed": {n: v["mean_signed_residual"] for n, v in hold["per_temperature"].items()},
                   "met_per_temperature": c2, "met": all(c2.values())},
            "met_if": prereg["acceptance"]["met_if"], "outcome": "MET" if met else "NOT MET"}


def leave_one_cell_out(cal: dict) -> dict:
    fits = {}
    for key in sorted(cal):
        sub = {k: v for k, v in cal.items() if k != key}
        f = fit(sub)
        fits[key] = {"k_q_per_Ah_discharge": f["k_q_per_Ah_discharge"], "activation_energy_J_per_mol": f["activation_energy_J_per_mol"]}
    ks = np.array([v["k_q_per_Ah_discharge"] for v in fits.values()])
    eas = np.array([v["activation_energy_J_per_mol"] for v in fits.values()])
    return {"refits": fits, "k_q": {"min": float(ks.min()), "max": float(ks.max()), "std": float(ks.std(ddof=1))},
            "activation_energy": {"min": float(eas.min()), "max": float(eas.max()), "std": float(eas.std(ddof=1))}}


def run(raw_dir: str) -> dict:
    prereg, prereg_sha = load_preregistration()
    admitted = admit(raw_dir, prereg)
    cal = read_cells(os.path.join(raw_dir, prereg["data"]["calibration_set"]["archive"]))
    hold_cells = read_cells(os.path.join(raw_dir, prereg["data"]["holdout_set"]["archive"]))
    if set(cal) & set(hold_cells):
        raise SystemExit("calibration and holdout share a cell")
    f = fit(cal)
    hold = holdout(hold_cells, f["k_q_per_Ah_discharge"], f["activation_energy_J_per_mol"])
    verdict = judge(prereg, hold)
    loo = leave_one_cell_out(cal)
    declared = holdout(hold_cells, FLAGSHIP_DECLARED["k_q_per_Ah_abs_current"], FLAGSHIP_DECLARED["activation_energy_J_per_mol"],
                       throughput="abs_current_throughput_Ah")
    declared.pop("rows")
    cal_hold = holdout(cal, f["k_q_per_Ah_discharge"], f["activation_energy_J_per_mol"])
    discrepancy = ({"status": "QUANTIFIED within the calibration/holdout envelope", "holdout_pooled_rmse": hold["pooled_rmse"],
                    "holdout_max_abs_residual": hold["max_abs_residual"], "per_temperature": hold["per_temperature"],
                    "envelope": "0-100 % SOC, setpoints 10/25/40 degC, 0.3C charge with 1C or drive-cycle discharge, the observed throughput range"}
                   if verdict["outcome"] == "MET" else
                   {"status": "NOT QUANTIFIED (unknown, not zero)", "reason": "the pre-registered holdout criteria were not met"})
    measured_t = {key: [c["measured_set_temperature_C"] for c in v["checkpoints"] if c["measured_set_temperature_C"] is not None]
                  for key, v in {**cal, **hold_cells}.items()}
    return {
        "schema": "forge.flagship.study/1", "id": prereg["id"], "preregistration_sha256": prereg_sha,
        "classification": prereg["classification"], "data": admitted,
        "fit": f, "holdout": hold, "verdict": verdict,
        "uncertainty_budget": {
            "numerical": "not applicable: the model is evaluated in closed form",
            "parameter": loo,
            "measurement": "UNKNOWN: the processed summaries carry no repeated capacity check of an unaged cell, so RPT repeatability is not established (never zero)",
            "model_discrepancy": discrepancy},
        "reported_not_judged": {
            "calibration_rmse": f["calibration_rmse"], "calibration_residuals_per_temperature": cal_hold["per_temperature"],
            "flagship_declared_parameters_on_holdout": {**FLAGSHIP_DECLARED, "throughput_used": "abs_current (charge + discharge), the definition flagship A feeds the model", **declared},
            "measured_set_temperature_C_per_cell": measured_t,
            "skipped_checkpoints": {key: v["skipped"] for key, v in {**cal, **hold_cells}.items() if v["skipped"]}},
        "cells": {key: {k: v for k, v in c.items() if k != "checkpoints"} | {"n_checkpoints": len(c["checkpoints"])} for key, c in {**cal, **hold_cells}.items()},
        "stated_limits": prereg["stated_limits"],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", required=True, help="directory holding the two pre-registered archives")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    record = run(a.data)
    with open(os.path.join(a.out, "kirkaldy_fade_study.json"), "wb") as fh:
        fh.write((json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    v = record["verdict"]
    print(f"{record['id']}: {v['outcome']}  C1 pooled RMSE {v['C1']['observed']:.4f} (<= 0.015: {v['C1']['met']})  "
          f"C2 {json.dumps({k: round(x, 4) for k, x in v['C2']['observed'].items()})} (met: {v['C2']['met']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
