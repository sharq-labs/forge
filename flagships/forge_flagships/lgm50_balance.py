"""BIG 14 follow-up on flagship A: one identified electrode-balance correction of Chen2020 (pre-registered).

Calibrates two active-material volume-fraction factors on cell02 at C/10 only, then predicts every other LG M50
curve and judges the ORIGINAL C/2 criteria. See ``data/big14_a_lgm50_balance_preregistration.json``.

    python -m forge_flagships.lgm50_balance --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import numpy as np

from . import lgm50_validation as V

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_lgm50_balance_preregistration.json")
H = 3.555
BASE = {"Negative electrode active material volume fraction": 0.75, "Positive electrode active material volume fraction": 0.665}


def simulate(model_name: str, d: dict, fn: float, fp: float) -> dict:
    import pybamm

    model = getattr(pybamm.lithium_ion, model_name)(options={"thermal": "lumped"})
    p = pybamm.ParameterValues("Chen2020")
    assert abs(p["Negative electrode active material volume fraction"] - BASE["Negative electrode active material volume fraction"]) < 1e-12
    assert abs(p["Positive electrode active material volume fraction"] - BASE["Positive electrode active material volume fraction"]) < 1e-12
    p.update({"Current function [A]": d["i"], "Ambient temperature [K]": float(d["tch"].mean()),
              "Initial temperature [K]": float(d["tc"][0]), "Total heat transfer coefficient [W.m-2.K-1]": H,
              "Negative electrode active material volume fraction": BASE["Negative electrode active material volume fraction"] * fn,
              "Positive electrode active material volume fraction": BASE["Positive electrode active material volume fraction"] * fp})
    sim = pybamm.Simulation(model, parameter_values=p, solver=pybamm.IDAKLUSolver(rtol=1e-6, atol=1e-8))
    t_end = float(d["t"][-1]) * 1.3 + 600.0
    sol = sim.solve([0.0, t_end], t_interp=np.linspace(0.0, t_end, 4000), initial_soc=1.0)
    t = np.asarray(sol["Time [s]"].entries, dtype=float)
    return {"t": t, "v": np.asarray(sol["Voltage [V]"].entries, dtype=float),
            "T": np.asarray(sol["Volume-averaged cell temperature [K]"].entries, dtype=float), "cap": d["i"] * t[-1] / 3600.0}


def calibrate(d: dict) -> tuple[float, float, float]:
    from scipy.optimize import minimize

    def cost(x):
        fn, fp = (float(np.clip(v, 0.85, 1.10)) for v in x)
        try:
            m = V.metrics(d, simulate("SPM", d, fn, fp))
        except Exception:
            return 1e6
        return float(np.hypot(m["v_rmse_mV"], 1000.0 * m["cap_rel_err"]))  # 1 % capacity counted as 10 mV
    res = minimize(cost, x0=[1.0, 1.0], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 0.01, "maxiter": 400})
    fn, fp = (float(np.clip(v, 0.85, 1.10)) for v in res.x)
    return fn, fp, float(res.fun)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(PREREGISTRATION, "rb") as fh:
        prereg_raw = fh.read()
    base_prereg, _ = V.load_preregistration()
    data = V.load_discharges(base_prereg)
    os.makedirs(a.out, exist_ok=True)
    t0 = time.perf_counter()
    fn, fp, resid = calibrate(data[("cell02", 0.5)])
    print(f"calibrated factors: negative {fn:.4f}, positive {fp:.4f} (objective {resid:.2f})", flush=True)
    table: dict = {}
    for model_name in ("SPM", "DFN"):
        table[model_name] = {}
        for cell in V.CELLS:
            table[model_name][cell] = {}
            for rate, label in V.RATES.items():
                d = data[(cell, rate)]
                m = V.metrics(d, simulate(model_name, d, fn, fp))
                m["held_out"] = not (cell == "cell02" and rate == 0.5)
                table[model_name][cell][label] = m
                print(f"{model_name:4s} {cell} {label:5s} {'held-out' if m['held_out'] else 'CALIB   '} V rmse {m['v_rmse_mV']:6.1f} mV "
                      f"max {m['v_max_abs_mV']:6.1f} | cap err {100 * m['cap_rel_err']:+.2f}%", flush=True)
    judgement = {}
    for cell in V.CELLS:
        r = table["SPM"][cell]["C/2"]
        judgement[cell] = {"V1": bool(r["v_rmse_mV"] <= 17.0), "C1": bool(abs(r["cap_rel_err"]) <= 0.02)}
    judgement["met"] = bool(all(all(v.values()) for v in judgement.values()))
    record = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": hashlib.sha256(prereg_raw).hexdigest(),
              "factors": {"negative": fn, "positive": fp}, "calibration_objective": resid, "table": table, "judgement": judgement,
              "wall_s": round(time.perf_counter() - t0, 1)}
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print("PRIMARY met" if judgement["met"] else "PRIMARY NOT met", json.dumps(judgement), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
