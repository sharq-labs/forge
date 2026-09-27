"""BIG 14 study on flagship A: the Chen2020 LG M50 cell model against the Chen 2020 measured discharges (pre-registered).

Everything is fixed in ``data/big14_a_lgm50_validation_preregistration.json`` before any model run: the data files (by
sha256), the models, the one calibrated parameter (the generic heat-transfer coefficient, on cell02 at 1C, temperature
only), the held-out set, the metrics and the primary acceptance criteria at C/2. No Chen2020 electrochemical parameter
is changed. PyBaMM is driven directly here because the Forge PyBaMM adapter does not expose the heat-transfer
coefficient; the result is a study record, not an admitted Forge evidence record.

    python -m forge_flagships.lgm50_validation --out <dir>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_lgm50_validation_preregistration.json")
RAW = os.path.join(REPO, "benchmarks", "measurements", "chen2020_lgm50", "raw")
RATES = {0.5: "C/10", 2.5: "C/2", 5.0: "1C", 7.5: "1.5C"}
CELLS = ("cell02", "cell03", "cell04")
MODELS = ("SPM", "SPMe", "DFN")


def load_preregistration() -> tuple[dict, str]:
    with open(PREREGISTRATION, "rb") as fh:
        raw = fh.read()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def load_discharges(prereg: dict) -> dict:
    """Every CC discharge of every cell, after checking each file's sha256 against the pre-registration."""
    out = {}
    for cell in CELLS:
        name = f"LGM50_{cell}.csv"
        path = os.path.join(RAW, name)
        with open(path, "rb") as fh:
            blob = fh.read()
        if hashlib.sha256(blob).hexdigest() != prereg["data"]["files"][name]["sha256"]:
            raise SystemExit(f"{name} is not the pre-registered file")
        rows = list(csv.reader(blob.decode("ascii").splitlines()))
        head = next(i for i, r in enumerate(rows) if r and r[0] == "Rec")
        ix = {c: i for i, c in enumerate(rows[head])}
        data = [r for r in rows[head + 1:] if r and r[0].strip()]
        for step in sorted({r[ix["Step"]] for r in data}, key=int):
            seg = [r for r in data if r[ix["Step"]] == step and r[ix["Md"]] == "D"]
            if len(seg) < 50:
                continue  # the short pre-conditioning discharge of cycle 1 is not one of the four rates
            cur = float(np.median([float(r[ix["Current [A]"]]) for r in seg]))
            rate = min(RATES, key=lambda k: abs(k - cur))
            t = np.array([float(r[ix["Test Time [s]"]]) for r in seg])
            out[(cell, rate)] = {"t": t - t[0], "i": cur, "v": np.array([float(r[ix["Voltage [V]"]]) for r in seg]),
                                 "tc": np.array([float(r[ix["Temperature Cell [degC]"]]) for r in seg]) + 273.15,
                                 "tch": np.array([float(r[ix["Temperature Chamber [degC]"]]) for r in seg]) + 273.15,
                                 "cap": float(seg[-1][ix["Capacity [Ah]"]])}
    return out


def simulate(model_name: str, d: dict, h: float) -> dict:
    import pybamm

    model = getattr(pybamm.lithium_ion, model_name)(options={"thermal": "lumped"})
    p = pybamm.ParameterValues("Chen2020")
    p.update({"Current function [A]": d["i"], "Ambient temperature [K]": float(d["tch"].mean()),
              "Initial temperature [K]": float(d["tc"][0]), "Total heat transfer coefficient [W.m-2.K-1]": h})
    sim = pybamm.Simulation(model, parameter_values=p, solver=pybamm.IDAKLUSolver(rtol=1e-6, atol=1e-8))
    t_end = float(d["t"][-1]) * 1.2 + 600.0
    sol = sim.solve([0.0, t_end], t_interp=np.linspace(0.0, t_end, 4000), initial_soc=1.0)
    t = np.asarray(sol["Time [s]"].entries, dtype=float)
    return {"t": t, "v": np.asarray(sol["Voltage [V]"].entries, dtype=float),
            "T": np.asarray(sol["Volume-averaged cell temperature [K]"].entries, dtype=float),
            "cap": d["i"] * t[-1] / 3600.0}


def metrics(d: dict, m: dict) -> dict:
    end = min(d["t"][-1], m["t"][-1])
    keep = d["t"] <= end
    tm = d["t"][keep]
    ev = np.interp(tm, m["t"], m["v"]) - d["v"][keep]
    eT = np.interp(tm, m["t"], m["T"]) - d["tc"][keep]
    ambient = float(d["tch"].mean())
    rise_meas = float(d["tc"].max() - ambient)
    rise_model = float(m["T"][m["t"] <= end].max() - ambient)
    return {"v_rmse_mV": float(np.sqrt(np.mean(ev ** 2)) * 1000), "v_max_abs_mV": float(np.abs(ev).max() * 1000),
            "cap_meas_Ah": d["cap"], "cap_model_Ah": m["cap"], "cap_rel_err": (m["cap"] - d["cap"]) / d["cap"],
            "T_rmse_K": float(np.sqrt(np.mean(eT ** 2))), "rise_meas_K": rise_meas, "rise_model_K": rise_model,
            "rise_err_K": rise_model - rise_meas, "samples": int(keep.sum())}


def calibrate_h(d: dict) -> tuple[float, float]:
    """The one pre-registered calibration: h on cell02 at 1C, surface temperature only, SPM."""
    from scipy.optimize import minimize_scalar

    def cost(h):
        return metrics(d, simulate("SPM", d, float(h)))["T_rmse_K"]
    res = minimize_scalar(cost, bounds=(1.0, 200.0), method="bounded", options={"xatol": 0.05})
    return float(res.x), float(res.fun)


def judge(table: dict, prereg: dict) -> dict:
    out = {}
    for cell in CELLS:
        r = table["SPM"][cell]["C/2"]
        v1 = r["v_rmse_mV"] <= 17.0
        c1 = abs(r["cap_rel_err"]) <= 0.02
        t1 = abs(r["rise_err_K"]) <= max(1.5, 0.25 * r["rise_meas_K"])
        out[cell] = {"V1": bool(v1), "C1": bool(c1), "T1": bool(t1)}
    out["met"] = bool(all(all(v.values()) for v in out.values()))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    prereg, prereg_sha = load_preregistration()
    os.makedirs(a.out, exist_ok=True)
    data = load_discharges(prereg)
    t0 = time.perf_counter()
    h, h_residual = calibrate_h(data[("cell02", 5.0)])
    print(f"calibrated h = {h:.3f} W/m2K (cell02 1C surface temperature RMSE {h_residual:.3f} K)", flush=True)
    table: dict = {}
    for model_name in MODELS:
        table[model_name] = {}
        for cell in CELLS:
            table[model_name][cell] = {}
            for rate, label in RATES.items():
                d = data[(cell, rate)]
                m = metrics(d, simulate(model_name, d, h))
                spread = prereg["data"]["data_only_facts_seen_before_registration"]["cell_to_cell_voltage_spread_rms_mV"][label]
                m["v_rmse_over_cell_spread"] = m["v_rmse_mV"] / spread
                table[model_name][cell][label] = m
                print(f"{model_name:4s} {cell} {label:5s} V rmse {m['v_rmse_mV']:6.1f} mV max {m['v_max_abs_mV']:6.1f} | cap err "
                      f"{100 * m['cap_rel_err']:+.2f}% | rise meas {m['rise_meas_K']:5.1f} model {m['rise_model_K']:5.1f} K", flush=True)
    verdict = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": prereg_sha,
               "independence": prereg["independence"]["status"], "calibrated_h_W_m2K": h, "calibration_T_rmse_K": h_residual,
               "table": table, "judgement": judge(table, prereg), "wall_s": round(time.perf_counter() - t0, 1)}
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(verdict, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print("PRIMARY met" if verdict["judgement"]["met"] else "PRIMARY NOT met", json.dumps(verdict["judgement"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
