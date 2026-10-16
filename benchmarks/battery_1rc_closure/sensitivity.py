"""Review L1: the initial-polarization sensitivity with the physically signed value.

After a CV charge the polarization voltage carries the CHARGE direction, i.e. it is negative under the positive-
discharge convention, so the bound is v_p0 = -20 mA x R1 (the calibration record tested +20 mA x R1). Refits on the
calibration role only, from the frozen optimum; writes results/SENSITIVITY.json. The calibration record is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math

from . import fit as bfit
from .data import load
from .evaluate import RESULTS, load_calibration


def main() -> int:
    cal = load_calibration()
    cycles = [bfit.Cycle(c) for c in load("calibration")["cycles"]]
    p = cal["models"]["1rc"]["parameters"]
    theta = bfit.np.r_[p["ocv"], math.log(p["R0"]), math.log(p["R1"]), math.log(p["C1"])]
    sse0 = cal["models"]["1rc"]["sse_V2"]
    out = {"schema": "forge.battery_1rc_closure.sensitivity/1",
           "calibration_sha256": (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode(), "cases": {}}
    for label, kw in (("vp0_minus_20mA_x_R1", {"vp0_per_r1": -0.020}),
                      ("forward_hold_and_vp0_minus_20mA_x_R1", {"vp0_per_r1": -0.020, "hold": "forward"})):
        th, sse, _ = bfit.solve(cycles, "1rc", theta, **kw)
        q = bfit.unpack(th, "1rc")
        out["cases"][label] = {"R0": q["R0"], "R1": q["R1"], "C1": q["C1"], "tau_s": q["R1"] * q["C1"],
                               "sse_ratio": sse / sse0,
                               "relative_shift": {k: q[k] / p[k] - 1.0 for k in ("R0", "R1", "C1")}}
    data = json.dumps(out, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "SENSITIVITY.json").write_bytes(data)
    (RESULTS / "SENSITIVITY.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    print(json.dumps(out["cases"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
