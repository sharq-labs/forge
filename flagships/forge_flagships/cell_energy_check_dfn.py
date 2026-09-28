"""BIG 14 check on flagship A: the cell side of the heat interface for the DFN cell with the heat of mixing (pre-registered).

The configuration flagship A uses since the DFN switch; ``cell_energy_check`` covered the earlier SPM cell only.
See ``data/big14_a_cell_energy_check_dfn_preregistration.json``.

    python -m forge_flagships.cell_energy_check_dfn --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_cell_energy_check_dfn_preregistration.json")


def run(temperature_K: float) -> dict:
    import pybamm
    from forge_pybamm import parameter_set
    from forge_pybamm.coupling import BALANCE_KEYS, FIXED_OPTIONS

    from . import battery_cooling as bc

    assert bc.MODEL == "DFN" and bc.CELL_OPTIONS == {"heat of mixing": "true"}
    _, pv = parameter_set(bc.PARAMETER_SET)
    for key, factor in zip(BALANCE_KEYS, bc.cell_balance()):   # exactly as the coupling path applies them (fresh cell: no fade)
        pv.update({key: float(pv[key]) * factor})
    pv.update({"Current function [A]": 2.5, "Ambient temperature [K]": temperature_K, "Initial temperature [K]": temperature_K})
    pv.set_initial_state(bc.INITIAL_SOC)
    model = pybamm.lithium_ion.DFN(options={**FIXED_OPTIONS, **bc.CELL_OPTIONS})
    sim = pybamm.Simulation(model, parameter_values=pv, solver=pybamm.IDAKLUSolver(rtol=1e-8, atol=1e-10))
    t = np.linspace(0.0, 3600.0, 3601)
    sol = sim.solve([0.0, 3600.0], t_interp=t)
    tt = np.asarray(sol["Time [s]"].entries, dtype=float)
    if tt[-1] < 3600.0 - 1e-6:
        raise RuntimeError(f"the discharge hour ended early at {tt[-1]} s")
    i = np.asarray(sol["Current [A]"].entries, dtype=float)
    v = np.asarray(sol["Voltage [V]"].entries, dtype=float)
    us = np.asarray(sol["Surface open-circuit voltage [V]"].entries, dtype=float)
    ub = np.asarray(sol["Bulk open-circuit voltage [V]"].entries, dtype=float)
    q = np.asarray(sol["Total heating [W]"].entries, dtype=float)
    qrev = np.asarray(sol["Reversible heating [W]"].entries, dtype=float)
    qmix = np.asarray(sol["Heat of mixing [W]"].entries, dtype=float)
    Q = float(np.trapezoid(q, tt))
    Q_bulk = float(np.trapezoid(i * (ub - v) + qrev, tt))
    Q_surface = float(np.trapezoid(i * (us - v) + qrev, tt))
    return {"temperature_K": temperature_K, "duration_s": float(tt[-1]), "heat_J": Q, "identity_bulk_J": Q_bulk, "identity_surface_J": Q_surface,
            "relative_mismatch_bulk": abs(Q - Q_bulk) / abs(Q), "relative_mismatch_surface": abs(Q - Q_surface) / abs(Q),
            "mixing_share": float(np.trapezoid(qmix, tt)) / Q, "reversible_share": float(np.trapezoid(qrev, tt)) / Q,
            "C1_met": bool(abs(Q - Q_bulk) <= 0.01 * abs(Q))}


def main(argv=None) -> int:
    import pybamm

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(PREREGISTRATION, "rb") as fh:
        raw = fh.read()
    rows = [run(T) for T in (300.0, 313.15)]
    for r in rows:
        print(f"T={r['temperature_K']} K: heat {r['heat_J']:.1f} J | bulk identity {r['identity_bulk_J']:.1f} J (mismatch {100 * r['relative_mismatch_bulk']:.4f} %) "
              f"| surface identity {r['identity_surface_J']:.1f} J (mismatch {100 * r['relative_mismatch_surface']:.2f} %) | mixing {100 * r['mixing_share']:.2f} % "
              f"| reversible {100 * r['reversible_share']:.2f} % -> C1 {'met' if r['C1_met'] else 'NOT met'}", flush=True)
    from . import battery_cooling as bc
    record = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": hashlib.sha256(raw).hexdigest(),
              "pybamm_version": pybamm.__version__, "cell_balance": list(bc.cell_balance()), "cell_study_sha256": bc.CELL_STUDY_SHA256,
              "rows": rows, "met": all(r["C1_met"] for r in rows)}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print("met" if record["met"] else "NOT met", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
