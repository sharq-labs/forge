"""Is the frozen TCR grid right in its THIN direction? Truth by dense quadrature, merged into PHASE6_REGRESSION.json.

    python -X utf8 benchmarks/core_gap_thin_ridge/audit/tcr_truth.py

Reference: the exact likelihood of the closed-form TCR law R = R_ref (1 + alpha (T - T_ref)) (the
analytic basis engcore.studies.tcr declares), integrated on a 2001 x 2001 lattice aligned with the
local principal axes over +/-12 principal sd. Compared with the frozen 41 x 41 test grid.
"""

from __future__ import annotations

import importlib.util
import json
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_thin_tcr", HERE / "thin_ridge.py")
T = importlib.util.module_from_spec(spec)
sys.modules["_thin_tcr"] = T
spec.loader.exec_module(T)


def main():
    from engcore.inference import gaussian_grid_posterior
    from engcore.scientific.units.quantity import Quantity
    from engcore.studies import TcrTruth, ols_reference_estimate, synthesize_tcr_observations, tcr_forward_table
    OHM, KELVIN, PER_KELVIN = "ohm", "kelvin", "1/kelvin"
    t_ref = Quantity(293.15, KELVIN)
    truth = TcrTruth(reference_resistance=Quantity(1.2570, OHM), temperature_coefficient=Quantity(0.003930, PER_KELVIN), reference_temperature=t_ref)
    out = {}
    for name, temps in (("TCR_WIDE", [300.0, 320.0, 340.0, 360.0, 380.0, 400.0, 420.0, 440.0]), ("TCR_NARROW", [299.0, 299.5, 300.0, 300.5, 301.0, 301.5])):
        obs = synthesize_tcr_observations(truth, temps, sigma=Quantity(0.002, OHM), dataset_id="tcr.cal", seed=20260912)
        by = {f"T{i}": Quantity(t, KELVIN) for i, t in enumerate(temps)}
        oracle = ols_reference_estimate(obs, by, t_ref)
        y = np.asarray([o.value.magnitude_in(OHM) for o in obs.observations])
        dT = np.asarray([by[o.condition_id].magnitude_in(KELVIN) for o in obs.observations]) - 293.15
        s = 0.002
        chi = lambda R, a: np.sum(((R[:, None] * (1 + a[:, None] * dT[None, :]) - y[None, :]) / s) ** 2, axis=1)
        mu0 = np.asarray([oracle["reference_resistance"], oracle["temperature_coefficient"]])
        J = np.column_stack([1 + mu0[1] * dT, mu0[0] * dT]) / s
        cov0 = np.linalg.inv(J.T @ J)
        lam, V = np.linalg.eigh(cov0)
        g = np.linspace(-12, 12, 2001)
        A, B = np.meshgrid(g * math.sqrt(lam[0]), g * math.sqrt(lam[1]), indexing="ij")
        Z = np.stack([A.ravel(), B.ravel()], axis=1)
        th = mu0 + Z @ V.T
        c = chi(th[:, 0], th[:, 1])
        w = np.exp(-0.5 * (c - c.min()))
        w /= w.sum()
        m_true = w @ th
        C_true = (th - m_true).T @ ((th - m_true) * w[:, None])
        ra = np.linspace(mu0[0] - 6 * oracle["se_reference_resistance"], mu0[0] + 6 * oracle["se_reference_resistance"], 41)
        aa = np.linspace(mu0[1] - 6 * oracle["se_temperature_coefficient"], mu0[1] + 6 * oracle["se_temperature_coefficient"], 41)
        post = gaussian_grid_posterior(tcr_forward_table(obs, [(float(a), float(b)) for a in ra for b in aa], reference_temperature=t_ref, temperatures_by_condition=by), obs)
        cmp = T.compare(post.mean, post.covariance, m_true, C_true)
        cand = T.candidates(post)
        out[name] = {"truth_by_principal_axis_quadrature": {"mean": m_true.tolist(), "covariance": C_true.tolist(),
                                                              "correlation": float(C_true[0, 1] / math.sqrt(C_true[0, 0] * C_true[1, 1])),
                                                              "principal_widths": np.sqrt(np.linalg.eigvalsh(C_true)).tolist()},
                     "frozen_41x41_grid_vs_truth": cmp, "guard": T.guard(post),
                     "D_value": cand["D"]["value"], "D_flag": cand["D"]["flag"], "D_aliasing_amplitude": cand["D"].get("aliasing_amplitude"),
                     "aliasing_number_true_sigma": T.aliasing_number(C_true, T.steps_of(post)),
                     "E": cand["E"], "fit": cand.get("fit")}
        print(name, "material", cmp["material"], "thin", cmp["post_hoc_thin_direction"], "D", cand["D"]["value"], cand["D"]["flag"], "A_true", out[name]["aliasing_number_true_sigma"], flush=True)
    path = T.ROUND / "PHASE6_REGRESSION.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["tcr_thin_direction_truth"] = out
    path.write_bytes((json.dumps(T.jsonable(doc), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print("merged into PHASE6_REGRESSION.json")


if __name__ == "__main__":
    main()
