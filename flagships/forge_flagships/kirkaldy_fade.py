"""BIG 14 study on flagship A: the throughput-Arrhenius fade model against Kirkaldy 2024 LG M50T ageing data (pre-registered).

Fixed in ``data/big14_a_kirkaldy_fade_preregistration.json`` (commit ``dd53eec7``, pushed before any capacity value was read):
the archives (by Zenodo md5), the calibration set (Expt 5, constant-current cycle ageing), the holdout set (Expt 4, drive-cycle
ageing, different cells), the definitions of capacity, fade, throughput and temperature, the fit and the acceptance criteria.
Rules the pre-registration did NOT fix -- how an RPT is placed on the per-cycle rows, which column is the capacity, the multistart,
the handling of the reference RPT -- were decided later and are listed with their decision time in the record's
``deviations_from_preregistration`` (:data:`DEVIATIONS`); none of them was chosen after a capacity value was read.

The model is ``engcore.domains.battery.throughput_fade.ThroughputArrheniusFade``'s law,
``fade = k_q * Q * exp(-Ea / R * (1/T - 1/T_ref))``, evaluated here directly on per-checkpoint aggregates (a test pins it to the
domain model's ``advance``); the result is a study record, not an admitted Forge evidence record.

The archives are read in place (``zipfile``); only the processed summaries and the metadata workbook are opened, and nothing is
executed from them.

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
from xml.etree import ElementTree

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_kirkaldy_fade_preregistration.json")
GAS_CONSTANT = 8.314462618          # J/(mol K), as engcore.domains.battery.throughput_fade uses
T_REF = 298.15
EA_BOUNDS = (0.0, 200e3)             # J/mol, pre-registered
C1_RMSE_MAX = 0.015                  # pre-registered C1
C2_BIAS_MAX = 0.010                  # pre-registered C2
REGISTERED_TEMPERATURES = ("10C", "25C", "40C")
FLAGSHIP_DECLARED = {"k_q_per_Ah_abs_current": 2e-4, "activation_energy_J_per_mol": 30e3}
MODEL_STATE_MAX = 0.5                # ThroughputArrheniusFade declares capacity_fade in [0, 0.5)
ALIGN_TOL_AH = 10.0                  # an RPT is placed on the cycle rows only within about one full cycle (charge + discharge)
_SUMMARY = re.compile(r"^Expt (\d+) - cell ([A-Z]+) \((\d+)degC\) - Processed Data\.csv$")
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

DEVIATIONS = (
    {"rule": "an RPT is placed on the per-cycle rows where their cumulative charge + discharge is nearest the RPT file's own "
             "'Charge Throughput [A h]'; the discharge charge up to that row is the throughput; an RPT that does not align within "
             f"{ALIGN_TOL_AH} A h is skipped and never estimated",
     "why": "the per-cycle numbering restarts per set and runs through cycler fault rows, so it cannot place an RPT",
     "decided": "after reading the archive structure and throughput columns of Expt 5, before any capacity value (PROGRESS, "
                "2026-10-09); Expt 4's structure was not inspected before the run",
     "effect": "the last RPT of every cell is skipped: the most-aged point, where a knee would show; this biases TOWARD MET"},
    {"rule": "capacity is the 'C/10 Capacity [mA h]' column of the processed RPT summary",
     "why": "the pre-registration names 'the discharge capacity of each RPT capacity check, as the processed summary states it' but "
            "no column; C/10 is the slow capacity check the dataset's own example notebook plots as capacity",
     "decided": "with the code, before any capacity value", "effect": "none known"},
    {"rule": "the fit is started from four activation energies (5, 30, 60, 120 kJ/mol) and the lowest cost is kept",
     "why": "the pre-registration fixes ordinary least squares and the bounds, not the optimiser", "decided": "with the code, before any capacity value",
     "effect": "none on the criteria; guards against a local minimum"},
    {"rule": "the reference RPT (RPT 0, where fade is 0 by definition and the prediction is 0 for any parameters) is excluded from "
             "C1 and C2; the values with it included are reported beside them",
     "why": "it is the normalisation, not a prediction; including it scales RMSE by sqrt((n-k)/n) and the bias by (n-k)/n toward MET",
     "decided": "after the first run, on review finding M2; the outcome is NOT MET either way", "effect": "moves both criteria AWAY from MET"},
    {"rule": "for Expt 4 the per-cycle 'Discharge Capacity [A h]' is GROSS discharge charge of the drive cycle (it exceeds both the "
             "constant-current charge and the cell capacity per cycle, e.g. 5.87 vs 3.17 A h at cycle 0)",
     "why": "the pre-registration says 'cumulative discharge charge'; gross discharge charge is what the column holds",
     "decided": "checked after the first run, on review finding L3; recorded, not changed", "effect": "the holdout throughput is gross, not net, discharge"},
)


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


def read_channels(xlsx: str) -> dict:
    """{(expt sheet, cell): 'rig/channel'} from experiment_metadata.xlsx, read with the standard library only."""
    with zipfile.ZipFile(xlsx) as z:
        shared = [si.findall(".//m:t", _NS) for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS)]
        strings = ["".join(t.text or "" for t in s) for s in shared]
        book = ElementTree.fromstring(z.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels}
        out = {}
        for sheet in book.find("m:sheets", _NS):
            rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            rows = []
            for row in ElementTree.fromstring(z.read("xl/" + targets[rid].lstrip("/").removeprefix("xl/"))).iter(f"{{{_NS['m']}}}row"):
                cells = {}
                for c in row.findall("m:c", _NS):
                    col = re.match(r"[A-Z]+", c.get("r")).group(0)
                    v = c.find("m:v", _NS)
                    text = (strings[int(v.text)] if c.get("t") == "s" else v.text) if v is not None else ""
                    cells[col] = text
                rows.append(cells)
            if not rows:
                continue
            head = {v: k for k, v in rows[0].items()}
            if not {"Cell", "Rig", "Channel"} <= set(head):
                continue
            for r in rows[1:]:
                cell = r.get(head["Cell"], "")
                if cell:
                    out[(sheet.get("name"), cell)] = f"{r.get(head['Rig'], '')}/{r.get(head['Channel'], '')}"
    return out


def _float(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def _rows(z: zipfile.ZipFile, name: str) -> tuple[list[dict], str]:
    blob = z.read(name)
    return list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig", errors="replace")))), hashlib.sha256(blob).hexdigest()


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
            # throughput; the discharge charge up to that row is the throughput (DEVIATIONS[0]).
            dis_raw = [_float(r["Discharge Capacity [A h]"]) for r in cycles]
            chg_raw = [_float(r["Charge Capacity [A h]"]) for r in cycles]
            blank_rows = sum(1 for d, c in zip(dis_raw, chg_raw) if d is None and c is None)
            charge_only_rows = sum(1 for r, d, c in zip(cycles, dis_raw, chg_raw) if d is None and c is not None and not (r["Cycle"] or "").strip())
            discharge = np.array([d or 0.0 for d in dis_raw])
            charge = np.array([c or 0.0 for c in chg_raw])
            cum_total, cum_dis = np.cumsum(discharge + charge), np.cumsum(discharge)
            checkpoints, skipped = [], []
            for r in perf:
                n_cycles = int(float(r["Ageing Cycles"]))
                rpt = int(float(r["Ageing Sets"]))
                q_total_file = _float(r["Charge Throughput [A h]"])
                if q_total_file is None and rpt != 0:
                    skipped.append({"rpt": rpt, "reason": "the RPT file states no throughput: missing, so not taken as zero"})
                    continue
                if rpt == 0:
                    q_dis, gap, q_total_file = 0.0, 0.0, q_total_file or 0.0
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
                                           "cycle_rows": {"total": len(cycles), "charge_only_unnumbered": charge_only_rows,
                                                          "both_capacities_blank_read_as_zero": blank_rows},
                                           "sources": {base: perf_sha, cycle_name.rsplit("/", 1)[-1]: cycle_sha}}
    if not cells:
        raise SystemExit(f"no processed summaries found in {archive}")
    return cells


def independent(cal: dict, hold: dict, channels: dict | None) -> dict:
    """Calibration and holdout must not share a physical cell. The dataset has no cell serials; its metadata names each cell's
    test rig channel, and a shared channel is refused. Without the metadata, independence rests on the dataset documentation only."""
    if channels is None:
        return {"basis": "dataset documentation only (no metadata workbook)", "shared_channels": None}
    def chans(cells):
        out = {}
        for key, c in cells.items():
            sheet = f"expt {c['expt']}"
            if (sheet, c["cell"]) not in channels:
                raise SystemExit(f"{key}: not in the metadata workbook")
            out[key] = channels[(sheet, c["cell"])]
        return out
    a, b = chans(cal), chans(hold)
    shared = sorted(set(a.values()) & set(b.values()))
    if shared:
        raise SystemExit(f"calibration and holdout share test channels {shared}: their independence is not established")
    return {"basis": "distinct rig channels in experiment_metadata.xlsx (no cell serials exist in the dataset)",
            "calibration_channels": a, "holdout_channels": b, "shared_channels": shared}


def _design(cells: dict, throughput: str = "discharge_throughput_Ah", *, include_reference: bool = False):
    q, t, y, keys, gaps = [], [], [], [], []
    for key in sorted(cells):
        for c in cells[key]["checkpoints"]:
            if c["rpt"] == 0 and not include_reference:
                continue
            q.append(c[throughput])
            t.append(cells[key]["setpoint_K"])
            y.append(c["fade"])
            keys.append((key, c["rpt"]))
            gaps.append(c["alignment_gap_Ah"])
    return np.array(q), np.array(t), np.array(y), keys, gaps


def predict(k: float, ea: float, q: np.ndarray, t: np.ndarray) -> np.ndarray:
    return k * q * np.exp(-ea / GAS_CONSTANT * (1.0 / t - 1.0 / T_REF))


def fit(cells: dict) -> dict:
    """Ordinary least squares over every calibration checkpoint, all temperatures jointly; k > 0, Ea in [0, 200] kJ/mol.
    The reference RPT contributes zero residual for any parameters, so it does not move the fit."""
    from scipy.optimize import least_squares

    q, t, y, _, _ = _design(cells)
    scale = float(np.sum(y * q) / np.sum(q * q)) if np.any(q) else 1e-5
    scale = scale if scale > 0 else 1e-5

    def residual(x):
        return predict(x[0] * scale, x[1] * 1e3, q, t) - y

    best = None
    for ea0 in (5.0, 30.0, 60.0, 120.0):                        # multistart in kJ/mol; the best of the four is kept (DEVIATIONS[2])
        r = least_squares(residual, x0=[1.0, ea0], bounds=([1e-9, EA_BOUNDS[0] / 1e3], [np.inf, EA_BOUNDS[1] / 1e3]), method="trf")
        if best is None or r.cost < best.cost:
            best = r
    k, ea = float(best.x[0] * scale), float(best.x[1] * 1e3)
    res = residual(best.x)
    return {"k_q_per_Ah_discharge": k, "activation_energy_J_per_mol": ea,
            "activation_energy_at_bound": bool(ea <= EA_BOUNDS[0] + 1.0 or ea >= EA_BOUNDS[1] - 1.0),
            "calibration_rmse": float(np.sqrt(np.mean(res ** 2))), "n_checkpoints": int(len(y)), "success": bool(best.success)}


def holdout(cells: dict, k: float, ea: float, throughput: str = "discharge_throughput_Ah", *, include_reference: bool = False) -> dict:
    q, t, y, keys, gaps = _design(cells, throughput, include_reference=include_reference)
    pred = predict(k, ea, q, t)
    res = pred - y
    per_temp = {}
    for temp in sorted(set(t)):
        sel = t == temp
        per_temp[f"{temp - 273.15:.0f}C"] = {"n": int(sel.sum()), "mean_signed_residual": float(res[sel].mean()),
                                             "rmse": float(np.sqrt(np.mean(res[sel] ** 2))), "max_abs_residual": float(np.abs(res[sel]).max())}
    rows = [{"cell": key, "rpt": rpt, "throughput_Ah": float(qq), "alignment_gap_Ah": gap, "measured_fade": float(yy),
             "predicted_fade": float(pp), "prediction_outside_model_state_range": bool(pp >= MODEL_STATE_MAX)}
            for (key, rpt), qq, yy, pp, gap in zip(keys, q, y, pred, gaps)]
    return {"pooled_rmse": float(np.sqrt(np.mean(res ** 2))), "max_abs_residual": float(np.abs(res).max()), "n_checkpoints": int(len(y)),
            "reference_rpt_included": include_reference, "per_temperature": per_temp,
            "predictions_outside_model_state_range": int(np.sum(pred >= MODEL_STATE_MAX)),
            "max_alignment_gap_Ah": float(max((abs(g) for g in gaps), default=0.0)), "rows": rows}


def judge(prereg: dict, hold: dict) -> dict:
    """C1 and C2 as registered. C2 needs every registered temperature: a missing one is NOT MET, never skipped."""
    c1 = hold["pooled_rmse"] <= C1_RMSE_MAX
    c2 = {}
    for name in REGISTERED_TEMPERATURES:
        entry = hold["per_temperature"].get(name)
        c2[name] = entry is not None and abs(entry["mean_signed_residual"]) <= C2_BIAS_MAX
    missing = [n for n in REGISTERED_TEMPERATURES if n not in hold["per_temperature"]]
    met = c1 and all(c2.values())
    return {"C1": {"criterion": prereg["acceptance"]["C1"], "observed": hold["pooled_rmse"], "met": c1},
            "C2": {"criterion": prereg["acceptance"]["C2"], "observed": {n: v["mean_signed_residual"] for n, v in hold["per_temperature"].items()},
                   "met_per_temperature": c2, "missing_temperatures": missing, "met": all(c2.values())},
            "met_if": prereg["acceptance"]["met_if"], "outcome": "MET" if met else "NOT MET"}


def leave_one_cell_out(cal: dict) -> dict:
    """Cell-to-cell parameter spread. A parameter pinned at a bound in any refit has NO estimated uncertainty: its spread would be
    the constraint's, not the data's."""
    fits = {}
    for key in sorted(cal):
        f = fit({k: v for k, v in cal.items() if k != key})
        fits[key] = {"k_q_per_Ah_discharge": f["k_q_per_Ah_discharge"], "activation_energy_J_per_mol": f["activation_energy_J_per_mol"],
                     "activation_energy_at_bound": f["activation_energy_at_bound"]}
    at_bound = sum(v["activation_energy_at_bound"] for v in fits.values())
    ks = np.array([v["k_q_per_Ah_discharge"] for v in fits.values()])
    out = {"refits": fits,
           "k_q": {"min": float(ks.min()), "max": float(ks.max()), "std": float(ks.std(ddof=1)),
                   "conditional_on": "activation energy at its lower bound (0) in every refit" if at_bound == len(fits) else
                                     ("activation energy at a bound in some refits" if at_bound else "activation energy free in every refit")}}
    if at_bound:
        out["activation_energy"] = {"status": f"NOT ESTABLISHED (constraint-active at a bound in {at_bound}/{len(fits)} refits)"}
    else:
        eas = np.array([v["activation_energy_J_per_mol"] for v in fits.values()])
        out["activation_energy"] = {"min": float(eas.min()), "max": float(eas.max()), "std": float(eas.std(ddof=1))}
    return out


def model_discrepancy(verdict: dict, hold: dict) -> dict:
    """Quantified only from a holdout that met its registered criteria, and only inside its envelope; otherwise UNKNOWN, never zero."""
    if verdict["outcome"] != "MET":
        return {"status": "NOT QUANTIFIED (unknown, not zero)", "reason": "the pre-registered holdout criteria were not met"}
    return {"status": "QUANTIFIED within the calibration/holdout envelope", "holdout_pooled_rmse": hold["pooled_rmse"],
            "holdout_max_abs_residual": hold["max_abs_residual"], "per_temperature": hold["per_temperature"],
            "envelope": "0-100 % SOC, setpoints 10/25/40 degC, 0.3C charge with 1C or drive-cycle discharge, the observed throughput range"}


def run(raw_dir: str) -> dict:
    prereg, prereg_sha = load_preregistration()
    admitted = admit(raw_dir, prereg)
    cal = read_cells(os.path.join(raw_dir, prereg["data"]["calibration_set"]["archive"]))
    hold_cells = read_cells(os.path.join(raw_dir, prereg["data"]["holdout_set"]["archive"]))
    meta = os.path.join(raw_dir, "experiment_metadata.xlsx")
    independence = independent(cal, hold_cells, read_channels(meta) if os.path.exists(meta) else None)
    f = fit(cal)
    hold = holdout(hold_cells, f["k_q_per_Ah_discharge"], f["activation_energy_J_per_mol"])
    verdict = judge(prereg, hold)
    with_reference = holdout(hold_cells, f["k_q_per_Ah_discharge"], f["activation_energy_J_per_mol"], include_reference=True)
    with_reference.pop("rows")
    loo = leave_one_cell_out(cal)
    declared = holdout(hold_cells, FLAGSHIP_DECLARED["k_q_per_Ah_abs_current"], FLAGSHIP_DECLARED["activation_energy_J_per_mol"],
                       throughput="abs_current_throughput_Ah")
    declared.pop("rows")
    cal_hold = holdout(cal, f["k_q_per_Ah_discharge"], f["activation_energy_J_per_mol"])
    measured_t = {key: [c["measured_set_temperature_C"] for c in v["checkpoints"] if c["measured_set_temperature_C"] is not None]
                  for key, v in {**cal, **hold_cells}.items()}
    used = {name: sum(len(c["checkpoints"]) for c in cells.values()) for name, cells in (("calibration", cal), ("holdout", hold_cells))}
    total = {name: sum(len(c["checkpoints"]) + len(c["skipped"]) for c in cells.values()) for name, cells in (("calibration", cal), ("holdout", hold_cells))}
    classification = prereg["classification"] + (" -- level 7 NOT REACHED: the holdout was NOT MET" if verdict["outcome"] != "MET" else "")
    return {
        "schema": "forge.flagship.study/1", "id": prereg["id"], "preregistration_sha256": prereg_sha,
        "classification": classification, "data": admitted, "independence": independence,
        "coverage": {"rpts_used_including_reference": used, "rpts_in_the_data": total,
                     "criteria_exclude_the_reference_rpt": True},
        "deviations_from_preregistration": list(DEVIATIONS),
        "fit": f, "holdout": hold, "verdict": verdict,
        "uncertainty_budget": {
            "numerical": "not applicable: the model is evaluated in closed form",
            "parameter": loo,
            "measurement": "UNKNOWN: the processed summaries carry no repeated capacity check of an unaged cell, so RPT repeatability is not established (never zero)",
            "model_discrepancy": model_discrepancy(verdict, hold)},
        "reported_not_judged": {
            "criteria_with_the_reference_rpt_included": {"pooled_rmse": with_reference["pooled_rmse"],
                                                         "per_temperature": {n: v["mean_signed_residual"] for n, v in with_reference["per_temperature"].items()}},
            "calibration_rmse": f["calibration_rmse"], "calibration_residuals_per_temperature": cal_hold["per_temperature"],
            "flagship_declared_parameters_on_holdout": {
                **FLAGSHIP_DECLARED,
                "inputs": "throughput as flagship A aggregates it (integral of |I|, charge + discharge); temperature = the chamber setpoint, NOT "
                          "flagship A's time-weighted mean cell temperature (the measured set temperatures run above setpoint)",
                "caveat": f"predictions at or above fade {MODEL_STATE_MAX} lie outside ThroughputArrheniusFade's declared state range; the "
                          "RMSE then shows the direction (overprediction), not a meaningful magnitude",
                **declared},
            "measured_set_temperature_C_per_cell": measured_t,
            "skipped_checkpoints": {key: v["skipped"] for key, v in {**cal, **hold_cells}.items() if v["skipped"]}},
        "cells": {key: {k: v for k, v in c.items() if k != "checkpoints"} | {"n_checkpoints": len(c["checkpoints"])} for key, c in {**cal, **hold_cells}.items()},
        "stated_limits": prereg["stated_limits"],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", required=True, help="directory holding the two pre-registered archives (and experiment_metadata.xlsx)")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    record = run(a.data)
    with open(os.path.join(a.out, "kirkaldy_fade_study.json"), "wb") as fh:
        fh.write((json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    v = record["verdict"]
    print(f"{record['id']}: {v['outcome']}  C1 pooled RMSE {v['C1']['observed']:.4f} (<= {C1_RMSE_MAX}: {v['C1']['met']})  "
          f"C2 {json.dumps({k: round(x, 4) for k, x in v['C2']['observed'].items()})} (met: {v['C2']['met']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
