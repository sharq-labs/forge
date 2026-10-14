"""Held-out evaluation, opened once (preregistration v2). Writes results/VALIDATION.json and results/plots/*.svg.

1RC predictions: engcore.domains.battery.thevenin_route.run_thevenin_1rc with the frozen calibrated parameter set.
Rint predictions: the production kernel engcore.domains.battery.solver.evaluate_step on every loaded interval. That
kernel refuses zero current (DischargeLoad requires I > 0), so a rest interval is evaluated with the Rint equation at
I = 0, V = OCV(z); this deviation from the preregistered wording is recorded in the output.
Parameter uncertainty: the 40 calibration bootstrap parameter sets, propagated jointly through the pinned transcription
(equal to the route within 1e-12 V, tested).
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import time
from typing import Any

import numpy as np

from engcore.domains.battery import context as ctx
from engcore.domains.battery import thevenin_route as tr
from engcore.domains.battery.cell import CellSpecification, DischargeLoad
from engcore.domains.battery.solver import evaluate_step
from engcore.domains.battery.thevenin import Thevenin1RCParameters
from engcore.scientific.models.curves import DeclaredCurve, TabulatedForm
from engcore.scientific.units.quantity import Quantity as Q

from . import fit as bfit
from .data import load, prereg_sha256
from .prereg import PREREG

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
ACC = PREREG["validation"]["acceptance_per_model"]
ROLES = ("calibration", "within_cell_holdout", "cross_cell_validation")


def load_calibration() -> dict[str, Any]:
    raw = (RESULTS / "CALIBRATION.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode():
        raise ValueError("CALIBRATION.json does not match its pinned digest")
    doc = json.loads(raw)
    if doc["preregistration_sha256"] != prereg_sha256():
        raise ValueError("the calibration was produced under another preregistration")
    return doc


def _curve(ocv) -> DeclaredCurve:
    return DeclaredCurve(quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE, against_unit="dimensionless",
                         unit="volt", lower=0.0, upper=1.0, form=TabulatedForm(tuple(zip(bfit.KNOTS.tolist(), ocv))),
                         source="results/CALIBRATION.json")


def predict_1rc_route(c: bfit.Cycle, p: dict[str, Any], pset: dict[str, Any], basis: str) -> tuple[np.ndarray, str]:
    cell = CellSpecification(cell_id=c.cell, nominal_capacity=Q(c.q_as / 3600.0, "ampere_hour"),
                             internal_resistance=Q(p["R0"], "ohm"), coulombic_efficiency=Q(1.0, "dimensionless"),
                             open_circuit_voltage_curve=_curve(p["ocv"]))
    ps = tr.Thevenin1RCParameterSet("nasa-fy08q4-b5b7-v2", cell, Thevenin1RCParameters(Q(p["R1"], "ohm"),
                                                                                         Q(p["C1"], "farad")),
                                    Q(pset["temperature_range_C"][0], "degC"), Q(pset["temperature_range_C"][1], "degC"),
                                    Q(pset["max_current_A"], "ampere"), basis)
    segments = tuple(tr.ProfileSegment(Q(float(c.t[k] - c.t[k - 1]), "second"), Q(float(c.i[k]), "ampere"),
                                       Q(float(c.temp[k]), "degC")) for k in range(1, len(c.t)))
    run = tr.run_thevenin_1rc(ps, tr.Thevenin1RCInitialState(Q(1.0, "dimensionless"), Q(0.0, "volt"),
                                                             PREREG["trajectory_construction"]["initial_polarization_basis"]),
                              tr.DischargeRestProfile(f"{c.cell}-{c.ordinal}", segments, tr.POSITIVE_DISCHARGE))
    return np.array([x.terminal_voltage_v for x in run.trajectory]), run.result.validity[tr.MODEL_ID].status.value


def predict_rint_production(c: bfit.Cycle, p: dict[str, Any]) -> np.ndarray:
    cell = CellSpecification(cell_id=c.cell, nominal_capacity=Q(c.q_as / 3600.0, "ampere_hour"),
                             internal_resistance=Q(p["R0"], "ohm"), coulombic_efficiency=Q(1.0, "dimensionless"),
                             open_circuit_voltage_curve=_curve(p["ocv"]))
    z = 1.0
    out = []
    for k in range(1, len(c.t)):
        dt, current = float(c.t[k] - c.t[k - 1]), float(c.i[k])
        if current > 0.0:
            step = evaluate_step(cell, DischargeLoad(load_id=f"k{k}", current=Q(current, "ampere"),
                                                     initial_state_of_charge=Q(z, "dimensionless"),
                                                     cell_temperature=Q(float(c.temp[k]), "degC"),
                                                     duration=Q(dt, "second")))
            z, v = step.final_state_of_charge, step.terminal_voltage
        else:
            v = float(np.interp(z, bfit.KNOTS, p["ocv"]))
        out.append(v)
    return np.array(out)


def metrics(res: list[np.ndarray], cur: list[np.ndarray]) -> dict[str, Any]:
    allr = np.concatenate(res)
    body = np.concatenate([r[i > 0] for r, i in zip(res, cur)])
    tail = np.concatenate([r[i == 0] for r, i in zip(res, cur)])
    lag = [np.corrcoef(r[:-1], r[1:])[0, 1] for r in res if len(r) > 3 and np.std(r) > 0]
    f = lambda x: 1000 * float(x)  # noqa: E731
    return {"samples": int(allr.size), "rmse_mV": f(np.sqrt(np.mean(allr ** 2))), "mae_mV": f(np.mean(np.abs(allr))),
            "bias_mV": f(np.mean(allr)), "max_abs_mV": f(np.max(np.abs(allr))),
            "p95_abs_mV": f(np.percentile(np.abs(allr), 95)),
            "lag1_autocorrelation_mean": float(np.mean(lag)),
            "body_rmse_mV": f(np.sqrt(np.mean(body ** 2))), "tail_rmse_mV": f(np.sqrt(np.mean(tail ** 2))),
            "tail_samples": int(tail.size), "per_cycle_rmse_mV": [f(np.sqrt(np.mean(r ** 2))) for r in res]}


def paired_bootstrap(res_a: list[np.ndarray], res_b: list[np.ndarray], b=2000, seed=0) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(res_a)
    sse_a = np.array([np.sum(r ** 2) for r in res_a]); sse_b = np.array([np.sum(r ** 2) for r in res_b])
    cnt = np.array([r.size for r in res_a])
    diffs = []
    for _ in range(b):
        j = rng.integers(0, n, n)
        diffs.append(math.sqrt(sse_a[j].sum() / cnt[j].sum()) - math.sqrt(sse_b[j].sum() / cnt[j].sum()))
    diffs = 1000 * np.array(diffs)
    point = 1000 * (math.sqrt(sse_a.sum() / cnt.sum()) - math.sqrt(sse_b.sum() / cnt.sum()))
    return {"rmse_rint_minus_1rc_mV": point, "ci95_mV": [float(np.percentile(diffs, 2.5)),
                                                          float(np.percentile(diffs, 97.5))]}


def svg_plot(path: pathlib.Path, title: str, t, series: list[tuple[str, np.ndarray, str]], ylabel: str) -> None:
    w, h, m = 760, 340, 55
    ys = np.concatenate([s for _, s, _ in series])
    y0, y1 = float(ys.min()), float(ys.max())
    pad = 0.05 * (y1 - y0 or 1.0)
    y0, y1 = y0 - pad, y1 + pad
    t0, t1 = float(t.min()), float(t.max())
    sx = lambda x: m + (w - 2 * m) * (x - t0) / (t1 - t0 or 1)  # noqa: E731
    sy = lambda y: h - m + -(h - 2 * m) * (y - y0) / (y1 - y0)  # noqa: E731
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif" font-size="11">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{w / 2}" y="18" text-anchor="middle" font-size="13">{title}</text>',
             f'<line x1="{m}" y1="{h - m}" x2="{w - m}" y2="{h - m}" stroke="black"/>',
             f'<line x1="{m}" y1="{m}" x2="{m}" y2="{h - m}" stroke="black"/>',
             f'<text x="{w / 2}" y="{h - 15}" text-anchor="middle">time (s)</text>',
             f'<text x="14" y="{h / 2}" transform="rotate(-90 14 {h / 2})" text-anchor="middle">{ylabel}</text>']
    for frac in (0.0, 0.5, 1.0):
        yv = y0 + frac * (y1 - y0)
        parts.append(f'<text x="{m - 4}" y="{sy(yv) + 4:.1f}" text-anchor="end">{yv:.3f}</text>')
        tv = t0 + frac * (t1 - t0)
        parts.append(f'<text x="{sx(tv):.1f}" y="{h - m + 14}" text-anchor="middle">{tv:.0f}</text>')
    if y0 < 0 < y1:
        parts.append(f'<line x1="{m}" y1="{sy(0):.1f}" x2="{w - m}" y2="{sy(0):.1f}" stroke="#999" stroke-dasharray="3,3"/>')
    for k, (label, s, color) in enumerate(series):
        pts = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(t, s))
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.4" points="{pts}"/>')
        parts.append(f'<text x="{w - m - 150}" y="{m + 14 * k}" fill="{color}">{label}</text>')
    parts.append("</svg>")
    path.write_bytes("\n".join(parts).encode() + b"\n")


def main() -> int:
    cal = load_calibration()
    p1 = cal["models"]["1rc"]["parameters"]
    pr = cal["models"]["rint"]["parameters"]
    basis = (f"identified on B0005+B0007 (results/CALIBRATION.json, sha256 "
             f"{(RESULTS / 'CALIBRATION.sha256').read_bytes().split()[0].decode()[:16]}); identifiability decision "
             f"{cal['identifiability']['decision']}: NOT a validated parameter set")
    draws = np.array(cal["identifiability"]["bootstrap_draws_1rc"])
    out: dict[str, Any] = {"schema": "forge.battery_1rc_closure.validation/1", "preregistration_sha256": prereg_sha256(),
                           "calibration_sha256": (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode(),
                           "identifiability_decision": cal["identifiability"]["decision"],
                           "claim_scope": "predictive comparison of the two frozen fitted models at 2 A constant-current "
                                          "discharge plus rest, room temperature, early life; NOT a validation of "
                                          "parameter values, which are not identified",
                           "deviation": "the production Rint kernel refuses zero current, so rest intervals use the Rint "
                                        "equation at I = 0 (V = OCV(z)); loaded intervals use the production kernel",
                           "roles": {}}
    (RESULTS / "plots").mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        doc = load(role)
        cycles = [bfit.Cycle(c) for c in doc["cycles"]]
        started = time.perf_counter()
        pred1, statuses = zip(*(predict_1rc_route(c, p1, cal["parameter_set"], basis) for c in cycles))
        t1 = time.perf_counter() - started
        started = time.perf_counter()
        predr = [predict_rint_production(c, pr) for c in cycles]
        tr_ = time.perf_counter() - started
        obs = [c.v[1:] for c in cycles]
        cur = [c.i[1:] for c in cycles]
        res1 = [o - p for o, p in zip(obs, pred1)]
        resr = [o - p for o, p in zip(obs, predr)]
        # parameter uncertainty: joint bootstrap parameter sets through the pinned transcription
        band_lo, band_hi = [], []
        for c in cycles:
            preds = np.array([bfit.predict(c, d[:bfit.NK], math.exp(d[bfit.NK]), math.exp(d[bfit.NK + 1]),
                                           math.exp(d[bfit.NK + 2])) for d in draws])
            band_lo.append(np.percentile(preds, 2.5, axis=0)); band_hi.append(np.percentile(preds, 97.5, axis=0))
        inside = np.concatenate([(o >= lo) & (o <= hi) for o, lo, hi in zip(obs, band_lo, band_hi)])
        halfwidth = np.concatenate([(hi - lo) / 2 for lo, hi in zip(band_lo, band_hi)])
        m1, mr = metrics(res1, cur), metrics(resr, cur)
        entry = {"cycles": len(cycles), "cells": sorted({c.cell for c in cycles}),
                 "1rc": m1 | {"execution_seconds": round(t1, 3),
                              "route_validity_status_counts": {s: statuses.count(s) for s in sorted(set(statuses))}},
                 "rint": mr | {"execution_seconds": round(tr_, 3)},
                 "comparison": paired_bootstrap(resr, res1),
                 "parameter_uncertainty_1rc": {"band": "2.5-97.5 % of 40 joint bootstrap parameter sets",
                                               "median_half_width_mV": 1000 * float(np.median(halfwidth)),
                                               "coverage_of_measurements": float(inside.mean())}}
        ci = entry["comparison"]["ci95_mV"]
        entry["comparison"]["verdict"] = ("1RC_BETTER" if ci[0] > 0 else "RINT_BETTER" if ci[1] < 0
                                          else "NOT_DISTINGUISHED")
        for name, m in (("1rc", m1), ("rint", mr)):
            entry[name]["acceptance"] = ("PASS" if m["rmse_mV"] <= ACC["RMSE_mV_max"]
                                         and m["p95_abs_mV"] <= ACC["P95_abs_error_mV_max"] else "FAIL")
        out["roles"][role] = entry
        if role != "calibration":
            for pick in (0, len(cycles) - 1):
                c = cycles[pick]
                tt = c.t[1:]
                name = f"{role}_{c.cell}_ord{c.ordinal}"
                svg_plot(RESULTS / "plots" / f"{name}_voltage.svg", f"{role}: {c.cell} discharge ordinal {c.ordinal}",
                         tt, [("measured", obs[pick], "black"), ("1RC (route)", pred1[pick], "#1f77b4"),
                              ("Rint (production kernel)", predr[pick], "#d62728")], "terminal voltage (V)")
                svg_plot(RESULTS / "plots" / f"{name}_residual.svg", f"{role}: residual measured - predicted",
                         tt, [("1RC", res1[pick], "#1f77b4"), ("Rint", resr[pick], "#d62728")], "residual (V)")
    for role in ("within_cell_holdout", "cross_cell_validation"):
        for name in ("1rc", "rint"):
            out["roles"][role][name]["calibration_to_holdout_rmse_gap_mV"] = (
                out["roles"][role][name]["rmse_mV"] - out["roles"]["calibration"][name]["rmse_mV"])
    data = json.dumps(out, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "VALIDATION.json").write_bytes(data)
    (RESULTS / "VALIDATION.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    summary = {r: {m: {k: round(v, 2) if isinstance(v, float) else v for k, v in out["roles"][r][m].items()
                       if k in ("rmse_mV", "p95_abs_mV", "bias_mV", "max_abs_mV", "body_rmse_mV", "tail_rmse_mV",
                                "lag1_autocorrelation_mean", "acceptance", "route_validity_status_counts")}
                   for m in ("1rc", "rint")} | {"comparison": out["roles"][r]["comparison"],
                                                "param_uq": out["roles"][r]["parameter_uncertainty_1rc"]}
               for r in ROLES}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
