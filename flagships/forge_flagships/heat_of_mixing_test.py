"""BIG 14 test on flagship A: does the low calibrated heat-transfer coefficient compensate for the omitted heat of
mixing? (pre-registered; see ``data/big14_a_heat_of_mixing_preregistration.json``)

    python -m forge_flagships.heat_of_mixing_test --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np

from . import lgm50_validation as V

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_heat_of_mixing_preregistration.json")
BASELINE = os.path.join(HERE, "..", "..", "docs", "flagships", "big14", "lgm50_validation_study.json")


def simulate(model_name: str, d: dict, h: float) -> dict:
    import pybamm

    model = getattr(pybamm.lithium_ion, model_name)(options={"thermal": "lumped", "heat of mixing": "true"})
    p = pybamm.ParameterValues("Chen2020")
    p.update({"Current function [A]": d["i"], "Ambient temperature [K]": float(d["tch"].mean()),
              "Initial temperature [K]": float(d["tc"][0]), "Total heat transfer coefficient [W.m-2.K-1]": h})
    sim = pybamm.Simulation(model, parameter_values=p, solver=pybamm.IDAKLUSolver(rtol=1e-6, atol=1e-8))
    t_end = float(d["t"][-1]) * 1.2 + 600.0
    sol = sim.solve([0.0, t_end], t_interp=np.linspace(0.0, t_end, 4000), initial_soc=1.0)
    t = np.asarray(sol["Time [s]"].entries, dtype=float)
    return {"t": t, "v": np.asarray(sol["Voltage [V]"].entries, dtype=float),
            "T": np.asarray(sol["Volume-averaged cell temperature [K]"].entries, dtype=float), "cap": d["i"] * t[-1] / 3600.0}


def main(argv=None) -> int:
    from scipy.optimize import minimize_scalar

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(PREREGISTRATION, "rb") as fh:
        raw = fh.read()
    base_prereg, _ = V.load_preregistration()
    data = V.load_discharges(base_prereg)
    cal = data[("cell02", 5.0)]
    res = minimize_scalar(lambda h: V.metrics(cal, simulate("SPM", cal, float(h)))["T_rmse_K"], bounds=(1.0, 200.0), method="bounded",
                          options={"xatol": 0.05})
    h = float(res.x)
    print(f"recalibrated h with heat of mixing = {h:.3f} W/m2K (was 3.555); calibration T rmse {res.fun:.3f} K", flush=True)
    with open(BASELINE, "rb") as fh:
        baseline = json.loads(fh.read().decode("utf-8"))
    rows, base_errs, new_errs = {}, [], []
    for cell in V.CELLS:
        for rate, label in V.RATES.items():
            if cell == "cell02" and rate == 5.0:
                continue
            d = data[(cell, rate)]
            m = V.metrics(d, simulate("SPM", d, h))
            b = baseline["table"]["SPM"][cell][label]
            rows[f"{cell} {label}"] = {"rise_meas_K": m["rise_meas_K"], "rise_model_K": m["rise_model_K"], "rise_err_K": m["rise_err_K"],
                                       "baseline_rise_err_K": b["rise_err_K"], "T_rmse_K": m["T_rmse_K"], "baseline_T_rmse_K": b["T_rmse_K"]}
            base_errs.append(abs(b["rise_err_K"]))
            new_errs.append(abs(m["rise_err_K"]))
            print(f"{cell} {label:5s} rise meas {m['rise_meas_K']:5.1f} K | model {m['rise_model_K']:5.1f} K (err {m['rise_err_K']:+5.2f}) "
                  f"| baseline err {b['rise_err_K']:+5.2f}", flush=True)
    p1 = h >= 1.2 * 3.555
    p2 = float(np.mean(new_errs)) <= float(np.mean(base_errs))
    record = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": hashlib.sha256(raw).hexdigest(),
              "h_recalibrated": h, "h_baseline": 3.555, "calibration_T_rmse_K": float(res.fun), "rows": rows,
              "mean_abs_rise_err_K": {"with_mixing": float(np.mean(new_errs)), "baseline": float(np.mean(base_errs))},
              "P1": bool(p1), "P2": bool(p2), "Hc_supported": bool(p1 and p2)}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print(f"P1 {p1} P2 {p2} -> Hc {'supported' if p1 and p2 else 'NOT supported'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
