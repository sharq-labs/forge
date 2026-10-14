"""Calibration and identifiability on the CALIBRATION cells only, with the calibration-mean measured OCV fixed.

``python -m benchmarks.battery_1rc_crosscell.fit`` writes results/CALIBRATION.json (deterministic: no timing field) and
results/TIMINGS_calibration.json (unpinned). It reads only data/ocv_cal.json and data/calibration.json. The windows are
evaluated together (padded to one length) so a residual call is one vectorised march; the transcription equals engcore's
thevenin_route (pinned by a test on real windows).
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import time
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from .data import PREREG, load, prereg_sha256

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
B = PREREG["models"]["bounds"]
LO = {"R0": math.log(B["R0_ohm"][0]), "R1": math.log(B["R1_ohm"][0]), "C1": math.log(B["C1_F"][0])}
HI = {"R0": math.log(B["R0_ohm"][1]), "R1": math.log(B["R1_ohm"][1]), "C1": math.log(B["C1_F"][1])}
NAMES = {"rint": ("R0",), "1rc": ("R0", "R1", "C1")}
REST_S = 3000.0


class Ocv:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.z = np.array([k[0] for k in doc["knots_z_V_cells"]])
        self.v = np.array([k[1] for k in doc["knots_z_V_cells"]])
        if np.any(np.diff(self.z) <= 0) or abs(self.z[-1] - 1.0) > 1e-12:
            raise ValueError("the OCV knots must increase strictly to z = 1")

    def __call__(self, z: np.ndarray) -> np.ndarray:
        if np.any(z < self.z[0] - 1e-12) or np.any(z > self.z[-1] + 1e-12):
            raise ValueError("SOC outside the measured OCV knot range: refused, never extrapolated")
        return np.interp(z, self.z, self.v)


class Batch:
    """Windows padded to one length: dt = 0 and I = 0 in the padding, which a mask removes from every residual."""

    def __init__(self, docs: list[dict[str, Any]], q_ah: float, *, z_scale: float = 1.0) -> None:
        n = max(len(d["time_s"]) for d in docs) - 1
        self.dt = np.zeros((len(docs), n))
        self.i = np.zeros((len(docs), n))
        self.i_prev = np.zeros((len(docs), n))
        self.v = np.zeros((len(docs), n))
        self.mask = np.zeros((len(docs), n), bool)
        self.z0 = np.array([1.0 - (1.0 - d["z0"]) * z_scale for d in docs])
        self.cells = [d["cell"] for d in docs]
        self.temp = [np.asarray(d["temperature_C"], float) for d in docs]
        for k, d in enumerate(docs):
            t, i, v = (np.asarray(d[c], float) for c in ("time_s", "current_A", "voltage_V"))
            m = len(t) - 1
            self.dt[k, :m], self.i[k, :m], self.i_prev[k, :m], self.v[k, :m] = np.diff(t), i[1:], i[:-1], v[1:]
            self.mask[k, :m] = True
        self.q_as = q_ah * 3600.0 / z_scale

    def subset(self, rows: np.ndarray) -> "Batch":
        out = object.__new__(Batch)
        for name in ("dt", "i", "i_prev", "v", "mask", "z0"):
            setattr(out, name, getattr(self, name)[rows])
        out.cells = [self.cells[r] for r in rows]
        out.temp = [self.temp[r] for r in rows]
        out.q_as = self.q_as
        return out


def predict(b: Batch, ocv: Ocv, r0: float, r1: float | None = None, c1: float | None = None, *,
            hold: str = "backward", vp0: float = 0.0) -> np.ndarray:
    cur = b.i if hold == "backward" else b.i_prev
    z = b.z0[:, None] - np.cumsum(cur * b.dt, axis=1) / b.q_as
    vp = np.zeros_like(cur)
    if r1 is not None:
        alpha = np.exp(-b.dt / (r1 * c1))
        gain = cur * r1 * (1.0 - alpha)
        prev = np.full(cur.shape[0], vp0)
        for k in range(cur.shape[1]):
            prev = prev * alpha[:, k] + gain[:, k]
            vp[:, k] = prev
    return ocv(np.where(b.mask, z, ocv.z[-1])) - cur * r0 - vp


def params(x: np.ndarray, model: str) -> dict[str, float]:
    return {n: math.exp(v) for n, v in zip(NAMES[model], x)}


def residuals(x, b: Batch, ocv, model, **kw):
    p = params(x, model)
    return (b.v - predict(b, ocv, p["R0"], p.get("R1"), p.get("C1"), **kw))[b.mask]


def solve(b, ocv, model, x0, *, fixed=None, **kw):
    names = NAMES[model]
    free = [k for k in range(len(names)) if not fixed or k not in fixed]
    lo = np.array([LO[names[k]] for k in free])
    hi = np.array([HI[names[k]] for k in free])

    def full(xf):
        x = np.array(x0, float)
        x[free] = xf
        for k, v in (fixed or {}).items():
            x[k] = v
        return x
    r = least_squares(lambda xf: residuals(full(xf), b, ocv, model, **kw),
                      np.clip(np.asarray(x0, float)[free], lo + 1e-9, hi - 1e-9), bounds=(lo, hi), method="trf",
                      x_scale="jac", max_nfev=2000)
    return full(r.x), float(np.sum(r.fun ** 2)), r


def starts(model):
    if model == "rint":
        return [np.array([math.log(r0)]) for r0 in (0.005, 0.01, 0.02, 0.03, 0.04, 0.06, 0.1, 0.15)]
    return [np.array([math.log(0.02), math.log(r1), math.log(tau / r1)])
            for r1 in (0.005, 0.02) for tau in (5.0, 30.0, 120.0, 600.0)]


def fit(b, ocv, model, **kw):
    best, runs = None, []
    for x0 in starts(model):
        x, sse, r = solve(b, ocv, model, x0, **kw)
        runs.append({"start": params(x0, model), "sse": sse, "status": int(r.status), "end": params(x, model)})
        if best is None or sse < best[1]:
            best = (x, sse, r)
    return best, runs


FACTORS = (1 / 3, 1 / 2, 1 / 1.5, 1.5, 2.0, 3.0)


def profile_identified(rows) -> bool:
    low = [r["sse_ratio"] for r in rows if r["factor"] < 1 and r["sse_ratio"] is not None]
    high = [r["sse_ratio"] for r in rows if r["factor"] > 1 and r["sse_ratio"] is not None]
    return bool(low) and bool(high) and max(low) >= 1.10 and max(high) >= 1.10


def profiles(b, ocv, x, sse):
    out = {}
    for k, name in enumerate(("R0", "R1", "C1")):
        rows = []
        for f in FACTORS:
            val = x[k] + math.log(f)
            if not LO[name] <= val <= HI[name]:
                rows.append({"factor": f, "sse_ratio": None})
                continue
            x0 = x.copy()
            x0[k] = val
            _, s2, _ = solve(b, ocv, "1rc", x0, fixed={k: val})
            rows.append({"factor": f, "sse_ratio": s2 / sse})
        out[name] = rows
    rows = []
    for f in FACTORS:
        target = x[1] + x[2] + math.log(f)
        lo = np.array([LO["R0"], max(LO["R1"], target - HI["C1"])])
        hi = np.array([HI["R0"], min(HI["R1"], target - LO["C1"])])
        if not np.all(lo < hi):
            rows.append({"factor": f, "sse_ratio": None})
            continue
        rr = least_squares(lambda xx, target=target: residuals(np.array([xx[0], xx[1], target - xx[1]]), b, ocv, "1rc"),
                           np.clip(x[:2], lo + 1e-9, hi - 1e-9), bounds=(lo, hi), method="trf", x_scale="jac")
        rows.append({"factor": f, "sse_ratio": float(np.sum(rr.fun ** 2)) / sse})
    out["tau"] = rows
    return out


def main() -> int:
    started = time.perf_counter()
    ocv_doc, cal = load("ocv_cal"), load("calibration")
    ocv = Ocv(ocv_doc)
    b = Batch(cal["windows"], cal["q_Ah"])
    cells = sorted(set(b.cells))
    out: dict[str, Any] = {"schema": "forge.battery_1rc_crosscell.calibration/1",
                           "preregistration_sha256": prereg_sha256(),
                           "ocv_sha256": (HERE / "data/ocv_cal.sha256").read_bytes().split()[0].decode(),
                           "calibration_data_sha256": (HERE / "data/calibration.sha256").read_bytes().split()[0].decode(),
                           "cells": cells, "windows": len(b.cells), "samples": int(b.mask.sum()), "models": {}}
    fits = {}
    for model in ("rint", "1rc"):
        (x, sse, r), runs = fit(b, ocv, model)
        fits[model] = (x, sse, r)
        out["models"][model] = {"parameters": params(x, model), "sse_V2": sse,
                                "rmse_mV": 1000 * math.sqrt(sse / out["samples"]), "starts": runs}
    x, sse, r = fits["1rc"]
    p = params(x, "1rc")
    tau = p["R1"] * p["C1"]
    out["models"]["1rc"]["tau_s"] = tau
    J = r.jac
    s = np.linalg.svd(J, compute_uv=False)
    cov = np.linalg.pinv(J.T @ J) * sse / max(1, J.shape[0] - J.shape[1])
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    corr = cov / np.outer(sd, sd)
    prof = profiles(b, ocv, x, sse)
    rng = np.random.default_rng(0)
    by_cell = {c: np.array([k for k, cc in enumerate(b.cells) if cc == c]) for c in cells}
    draws = []
    for _ in range(200):                      # cell-block bootstrap: resample CALIBRATION CELLS with replacement
        pick = rng.integers(0, len(cells), len(cells))
        rows = np.concatenate([by_cell[cells[j]] for j in pick])
        xb, _, _ = solve(b.subset(rows), ocv, "1rc", x)
        draws.append(xb)
    draws = np.array(draws)
    bp = {"R0": np.exp(draws[:, 0]), "R1": np.exp(draws[:, 1]), "C1": np.exp(draws[:, 2])}
    bp["tau"] = bp["R1"] * bp["C1"]
    boot = {n: {"mean": float(v.mean()), "sd": float(v.std(ddof=1)), "cv": float(v.std(ddof=1) / v.mean()),
                "p2_5": float(np.percentile(v, 2.5)), "p97_5": float(np.percentile(v, 97.5))} for n, v in bp.items()}
    xf, sse_f, _ = solve(b, ocv, "1rc", x, hold="forward")
    pf = params(xf, "1rc")
    pf["tau"] = pf["R1"] * pf["C1"]
    # bound on the polarization left by the previous 2.5 A pulse after the >= 3000 s rest (positive = discharge)
    vp0 = 2.5 * p["R1"] * math.exp(-REST_S / tau)
    xv, sse_v, _ = solve(b, ocv, "1rc", x, vp0=vp0)
    pv = params(xv, "1rc")
    ptau = {**p, "tau": tau}
    shift = {n: pf[n] / ptau[n] - 1.0 for n in ptau}
    on_bound = {n: bool(min(x[k] - LO[n], HI[n] - x[k]) < 0.01) for k, n in enumerate(("R0", "R1", "C1"))}
    decided = {}
    for n in ("R0", "R1", "C1", "tau"):
        bound_ok = (not on_bound[n]) if n != "tau" else not (on_bound["R1"] or on_bound["C1"])
        decided[n] = {"profile": profile_identified(prof[n]), "bootstrap_cv": boot[n]["cv"],
                      "cv_ok": boot[n]["cv"] <= 0.25, "not_on_bound": bound_ok,
                      "hold_shift": shift[n], "hold_ok": abs(shift[n]) <= 0.10}
        decided[n]["identified"] = all(decided[n][k] for k in ("profile", "cv_ok", "not_on_bound", "hold_ok"))
    if all(decided[n]["identified"] for n in ("R0", "R1", "C1")):
        decision = "IDENTIFIABLE"
    elif decided["tau"]["identified"] or decided["R0"]["identified"]:
        decision = "WEAKLY_IDENTIFIABLE"
    else:
        decision = "NOT_IDENTIFIABLE"
    out["identifiability"] = {
        "jacobian_singular_values": s.tolist(), "jacobian_condition": float(s[0] / s[-1]),
        "correlations": {"logR0~logR1": float(corr[0, 1]), "logR0~logC1": float(corr[0, 2]),
                         "logR1~logC1": float(corr[1, 2])},
        "profiles": prof, "bootstrap": boot, "bootstrap_unit": "calibration cell", "bootstrap_draws": draws.tolist(),
        "sensitivity": {"forward_hold": pf | {"sse_ratio": sse_f / sse},
                        "vp0_bound": {"vp0_V": vp0, **pv, "sse_ratio": sse_v / sse}},
        "on_bound": on_bound, "per_parameter": decided, "decision": decision}
    temps = np.concatenate(b.temp)
    out["parameter_set"] = {"temperature_range_C": [float(temps.min()), float(temps.max())],
                            "temperature_basis": "min/max of the calibration windows' samples; NOT widened",
                            "max_current_A": float(np.max(b.i[b.mask])),
                            "z_range": [float(ocv.z[0]), float(ocv.z[-1])]}
    RESULTS.mkdir(exist_ok=True)
    data = json.dumps(out, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "CALIBRATION.json").write_bytes(data)
    (RESULTS / "CALIBRATION.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    (RESULTS / "TIMINGS_calibration.json").write_bytes(
        json.dumps({"elapsed_seconds": round(time.perf_counter() - started, 1)}).encode() + b"\n")
    print(json.dumps({"rint": out["models"]["rint"]["rmse_mV"], "1rc": out["models"]["1rc"]["rmse_mV"],
                      "params": ptau, "decision": decision, "per_parameter": decided,
                      "profiles": {n: [(round(r["factor"], 2), r["sse_ratio"] and round(r["sse_ratio"], 3)) for r in rows]
                                   for n, rows in prof.items()},
                      "corr": out["identifiability"]["correlations"], "sens": out["identifiability"]["sensitivity"],
                      "parameter_set": out["parameter_set"]}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
