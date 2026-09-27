"""DIAGNOSTIC (post hoc, labelled; does not change the pre-registered NOT MET): how much of the voltage error is the
capacity mismatch? Compare measured and modelled voltage on a NORMALISED depth-of-discharge axis (t / t_end of each)."""
import sys

import numpy as np

sys.path.insert(0, "/mnt/d/forge-b14/flagships")
from forge_flagships import lgm50_validation as L  # noqa: E402

pre, _ = L.load_preregistration()
data = L.load_discharges(pre)
grid = np.linspace(0.0, 0.97, 300)  # stop short of the knee, where a normalised axis is ill-conditioned
print("model cell  rate  | cap ratio model/meas | V rmse on normalised axis (0-97 %) | V max abs")
for model in ("SPM", "DFN"):
    for cell in L.CELLS:
        for rate, label in L.RATES.items():
            d = data[(cell, rate)]
            m = L.simulate(model, d, 3.555)
            vm = np.interp(grid, d["t"] / d["t"][-1], d["v"])
            vs = np.interp(grid, m["t"] / m["t"][-1], m["v"])
            e = (vs - vm) * 1000
            print(f"{model:4s} {cell} {label:5s} | {m['cap'] / d['cap']:.4f} | {np.sqrt(np.mean(e ** 2)):6.1f} mV | {np.abs(e).max():6.1f} mV")
