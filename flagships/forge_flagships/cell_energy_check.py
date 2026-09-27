"""BIG 14 check on flagship A: the cell side of the heat interface (pre-registered).

The coupled heat equals the coolant's m*dh by construction, so that comparison cannot catch an error in the cell's own
heat. This checks the cell's heat against its own energy balance, under the flagship's exact cell configuration.
See ``data/big14_a_cell_energy_check_preregistration.json``.

    python -m forge_flagships.cell_energy_check --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_cell_energy_check_preregistration.json")


def run(temperature_K: float) -> dict:
    import pybamm
    from forge_pybamm import parameter_set

    from . import battery_cooling as bc

    _, pv = parameter_set(bc.PARAMETER_SET)
    pv.update({"Current function [A]": 2.5, "Ambient temperature [K]": temperature_K, "Initial temperature [K]": temperature_K})
    pv.set_initial_state(bc.INITIAL_SOC)
    model = getattr(pybamm.lithium_ion, bc.MODEL)(options={"thermal": "isothermal", "calculate heat source for isothermal models": "true"})
    sim = pybamm.Simulation(model, parameter_values=pv, solver=pybamm.IDAKLUSolver(rtol=1e-8, atol=1e-10))
    t = np.linspace(0.0, 3600.0, 3601)
    sol = sim.solve([0.0, 3600.0], t_interp=t)
    tt = np.asarray(sol["Time [s]"].entries, dtype=float)
    i = np.asarray(sol["Current [A]"].entries, dtype=float)
    v = np.asarray(sol["Voltage [V]"].entries, dtype=float)
    us = np.asarray(sol["Surface open-circuit voltage [V]"].entries, dtype=float)
    ub = np.asarray(sol["Bulk open-circuit voltage [V]"].entries, dtype=float)
    q = np.asarray(sol["Total heating [W]"].entries, dtype=float)
    qrev = np.asarray(sol["Reversible heating [W]"].entries, dtype=float)
    Q = float(np.trapezoid(q, tt))
    Q_identity = float(np.trapezoid(i * (us - v) + qrev, tt))
    return {"temperature_K": temperature_K, "duration_s": float(tt[-1]), "heat_J": Q, "identity_heat_J": Q_identity,
            "relative_mismatch": abs(Q - Q_identity) / abs(Q), "mixing_share": float(np.trapezoid(i * (ub - us), tt)) / Q,
            "reversible_share": float(np.trapezoid(qrev, tt)) / Q, "C1_met": bool(abs(Q - Q_identity) <= 0.01 * abs(Q))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(PREREGISTRATION, "rb") as fh:
        raw = fh.read()
    rows = [run(T) for T in (300.0, 313.15)]
    for r in rows:
        print(f"T={r['temperature_K']} K: heat {r['heat_J']:.1f} J, identity {r['identity_heat_J']:.1f} J, mismatch "
              f"{100 * r['relative_mismatch']:.4f} %, mixing share {100 * r['mixing_share']:.2f} %, reversible share "
              f"{100 * r['reversible_share']:.2f} % -> C1 {'met' if r['C1_met'] else 'NOT met'}", flush=True)
    record = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": hashlib.sha256(raw).hexdigest(),
              "rows": rows, "met": all(r["C1_met"] for r in rows)}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print("met" if record["met"] else "NOT met", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
