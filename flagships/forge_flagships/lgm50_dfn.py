"""BIG 14 study on flagship A: the DFN cell with the heat of mixing against the LG M50 curves (pre-registered).

Identifies two active-material factors on cell02 at C/10 (wider bounds than big14-a-lgm50-electrode-balance), then the
heat-transfer coefficient on cell02 at 1C, predicts every other curve, judges the ORIGINAL C/2 criteria and applies the
pre-registered decision rule for flagship A. See ``data/big14_a_lgm50_dfn_preregistration.json``. The C/2-1.5C curves are
Chen2020's own tuning data (``docs/flagships/big14/chen2020_independence.json``): any agreement is in-sample.

    python -m forge_flagships.lgm50_dfn --out <dir>
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
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_lgm50_dfn_preregistration.json")
H_STEP1 = 3.555
BOUNDS = (0.70, 1.20)
AT_BOUND = 1e-3
OPTIONS = {"thermal": "lumped", "heat of mixing": "true"}
NEG, POS = "Negative electrode active material volume fraction", "Positive electrode active material volume fraction"
BASE = {NEG: 0.75, POS: 0.665}


def simulate(model_name: str, d: dict, fn: float, fp: float, h: float) -> dict:
    import pybamm

    model = getattr(pybamm.lithium_ion, model_name)(options=dict(OPTIONS))
    p = pybamm.ParameterValues("Chen2020")
    for key, value in BASE.items():
        assert abs(p[key] - value) < 1e-12, key
    p.update({"Current function [A]": d["i"], "Ambient temperature [K]": float(d["tch"].mean()),
              "Initial temperature [K]": float(d["tc"][0]), "Total heat transfer coefficient [W.m-2.K-1]": h,
              NEG: BASE[NEG] * fn, POS: BASE[POS] * fp})
    sim = pybamm.Simulation(model, parameter_values=p, solver=pybamm.IDAKLUSolver(rtol=1e-6, atol=1e-8))
    t_end = float(d["t"][-1]) * 1.3 + 600.0
    sol = sim.solve([0.0, t_end], t_interp=np.linspace(0.0, t_end, 4000), initial_soc=1.0)
    t = np.asarray(sol["Time [s]"].entries, dtype=float)
    total = np.asarray(sol["Total heating [W]"].entries, dtype=float)
    mixing = np.asarray(sol["Heat of mixing [W]"].entries, dtype=float)
    return {"t": t, "v": np.asarray(sol["Voltage [V]"].entries, dtype=float),
            "T": np.asarray(sol["Volume-averaged cell temperature [K]"].entries, dtype=float), "cap": d["i"] * t[-1] / 3600.0,
            "heat_J": float(np.trapezoid(total, t)), "mixing_J": float(np.trapezoid(mixing, t))}


def clip(x) -> tuple[float, float]:
    fn, fp = (float(np.clip(v, *BOUNDS)) for v in x)
    return fn, fp


def identify_balance(d: dict) -> tuple[float, float, float, int]:
    from scipy.optimize import minimize

    def cost(x):
        fn, fp = clip(x)
        try:
            m = V.metrics(d, simulate("DFN", d, fn, fp, H_STEP1))
        except Exception:
            return 1e6
        return float(np.hypot(m["v_rmse_mV"], 1000.0 * m["cap_rel_err"]))  # 1 % capacity counted as 10 mV
    res = minimize(cost, x0=[1.0, 1.0], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 0.01, "maxiter": 400})
    fn, fp = clip(res.x)
    return fn, fp, float(res.fun), int(res.nfev)


def identify_h(d: dict, fn: float, fp: float) -> tuple[float, float]:
    from scipy.optimize import minimize_scalar

    res = minimize_scalar(lambda h: V.metrics(d, simulate("DFN", d, fn, fp, float(h)))["T_rmse_K"], bounds=(1.0, 200.0), method="bounded",
                          options={"xatol": 0.05})
    return float(res.x), float(res.fun)


def at_bound(f: float) -> bool:
    return bool(min(abs(f - BOUNDS[0]), abs(f - BOUNDS[1])) <= AT_BOUND)


def judge(table: dict) -> dict:
    out = {}
    for cell in V.CELLS:
        r = table["DFN"][cell]["C/2"]
        out[cell] = {"V1": bool(r["v_rmse_mV"] <= 17.0), "C1": bool(abs(r["cap_rel_err"]) <= 0.02),
                     "T1": bool(abs(r["rise_err_K"]) <= max(1.5, 0.25 * r["rise_meas_K"]))}
    out["met"] = bool(all(all(out[c].values()) for c in V.CELLS))
    return out


def decision(fn: float, fp: float, table: dict) -> dict:
    bounded = {"negative": at_bound(fn), "positive": at_bound(fp)}
    c2 = [table["DFN"][c]["C/2"] for c in V.CELLS]
    return {"at_bound": bounded, "flagship_carries_balance": not any(bounded.values()),
            "flagship_factors": {"negative": fn, "positive": fp} if not any(bounded.values()) else {"negative": 1.0, "positive": 1.0},
            "flagship_carries_h": False,
            "model_form_band_C2": {"v_rmse_mV": [min(r["v_rmse_mV"] for r in c2), max(r["v_rmse_mV"] for r in c2)],
                                   "rise_err_K": [min(r["rise_err_K"] for r in c2), max(r["rise_err_K"] for r in c2)],
                                   "label": "measured against Chen2020's own tuning data (in-sample); likely optimistic; out-of-sample error UNKNOWN"}}


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
    fn, fp, objective, nfev = identify_balance(data[("cell02", 0.5)])
    print(f"step 1: factors negative {fn:.4f}, positive {fp:.4f} (objective {objective:.2f}, {nfev} evaluations)"
          f"{' AT BOUND' if at_bound(fn) or at_bound(fp) else ''}", flush=True)
    h, h_resid = identify_h(data[("cell02", 5.0)], fn, fp)
    print(f"step 2: h {h:.3f} W/m2K (temperature rmse {h_resid:.3f} K)", flush=True)
    table: dict = {}
    for model_name in ("DFN", "SPM"):
        table[model_name] = {}
        for cell in V.CELLS:
            table[model_name][cell] = {}
            for rate, label in V.RATES.items():
                d = data[(cell, rate)]
                sim = simulate(model_name, d, fn, fp, h)
                m = V.metrics(d, sim)
                m["mixing_share_of_total_heat"] = sim["mixing_J"] / sim["heat_J"] if sim["heat_J"] else None
                m["calibration_role"] = ("voltage+capacity" if (cell, rate) == ("cell02", 0.5) else
                                         "temperature" if (cell, rate) == ("cell02", 5.0) else "held-out")
                table[model_name][cell][label] = m
                print(f"{model_name:4s} {cell} {label:5s} {m['calibration_role']:16s} V rmse {m['v_rmse_mV']:6.1f} mV max {m['v_max_abs_mV']:6.1f} "
                      f"| cap {100 * m['cap_rel_err']:+.2f}% | rise meas {m['rise_meas_K']:5.1f} model {m['rise_model_K']:5.1f} K "
                      f"| mixing {100 * (m['mixing_share_of_total_heat'] or 0):.0f}%", flush=True)
    judgement = judge(table)
    rule = decision(fn, fp, table)
    record = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": hashlib.sha256(prereg_raw).hexdigest(),
              "classification": "C/2-1.5C: consistency with Chen2020's tuning data (in-sample), not validation",
              "step_1": {"factors": {"negative": fn, "positive": fp}, "objective": objective, "evaluations": nfev, "bounds": list(BOUNDS),
                         "h_during_step_1": H_STEP1},
              "step_2": {"h_W_m2K": h, "T_rmse_K": h_resid}, "table": table, "judgement": judgement, "decision_for_flagship": rule,
              "wall_s": round(time.perf_counter() - t0, 1)}
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print("PRIMARY met" if judgement["met"] else "PRIMARY NOT met", json.dumps(judgement), flush=True)
    print("decision:", json.dumps(rule), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
