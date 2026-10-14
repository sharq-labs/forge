"""Held-out evaluation on LG HG2 (opened once, after results/CALIBRATION.json was committed).

1RC predictions run through engcore.domains.battery.thevenin_route.run_thevenin_1rc. The route's CellSpecification needs
an OCV curve over z in [0, 1], and the measured knots span [z_lo, 1] (z_lo ~ 0.027): the charge axis is re-expressed
exactly as z' = (z - z_lo) / (1 - z_lo) with Q' = Q (1 - z_lo), so the measured knots map onto [0, 1] without any
extrapolated voltage (coulomb counting is linear, so the model is unchanged; a test pins route == transcription).
Rint: the production kernel on loaded intervals, V = OCV(z) at rest (the kernel refuses I = 0).
Writes results/VALIDATION.json (deterministic) and results/TIMINGS_validation.json (unpinned), plus SVG plots.
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

from benchmarks.battery_1rc_closure.evaluate import svg_plot
from . import fit as bfit
from .data import load, prereg_sha256
from .prereg import PREREG

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
ACC = PREREG["validation"]["acceptance"]


def load_calibration() -> dict[str, Any]:
    raw = (RESULTS / "CALIBRATION.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode():
        raise ValueError("CALIBRATION.json does not match its pinned digest")
    doc = json.loads(raw)
    if doc["preregistration_sha256"] != prereg_sha256():
        raise ValueError("the calibration was produced under another preregistration")
    return doc


class Axis:
    """The exact affine re-expression of the charge axis onto the measured knot range."""

    def __init__(self, ocv: bfit.Ocv) -> None:
        self.z_lo = float(ocv.z[0])
        if abs(ocv.z[-1] - 1.0) > 1e-9:
            raise ValueError("the top OCV knot must be at z = 1")
        self.knots = tuple(((float(z) - self.z_lo) / (1.0 - self.z_lo), float(v)) for z, v in zip(ocv.z, ocv.v))

    def zp(self, z: float) -> float:
        return (z - self.z_lo) / (1.0 - self.z_lo)

    def cell(self, q_ah: float, r0: float, cell_id: str) -> CellSpecification:
        curve = DeclaredCurve(quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE, against_unit="dimensionless",
                              unit="volt", lower=0.0, upper=1.0, form=TabulatedForm(self.knots),
                              source="data/ocv.json: measured relaxed HPPC rests, charge axis re-expressed")
        return CellSpecification(cell_id=cell_id, nominal_capacity=Q(q_ah * (1.0 - self.z_lo), "ampere_hour"),
                                 internal_resistance=Q(r0, "ohm"), coulombic_efficiency=Q(1.0, "dimensionless"),
                                 open_circuit_voltage_curve=curve)


def predict_route(w: bfit.Window, axis: Axis, q_ah: float, p: dict[str, float], pset: dict[str, Any], basis: str,
                  label: str):
    ps = tr.Thevenin1RCParameterSet("lghg2-25c-pulses-v1", axis.cell(q_ah, p["R0"], "LG-HG2-SN62A4"),
                                    Thevenin1RCParameters(Q(p["R1"], "ohm"), Q(p["C1"], "farad")),
                                    Q(pset["temperature_range_C"][0], "degC"), Q(pset["temperature_range_C"][1], "degC"),
                                    Q(pset["max_current_A"], "ampere"), basis)
    segments = tuple(tr.ProfileSegment(Q(float(w.t[k] - w.t[k - 1]), "second"), Q(float(w.i[k]), "ampere"),
                                       Q(float(w.temp[k]), "degC")) for k in range(1, len(w.t)))
    run = tr.run_thevenin_1rc(ps, tr.Thevenin1RCInitialState(
        Q(axis.zp(w.z0), "dimensionless"), Q(0.0, "volt"), PREREG["construction"]["pulse_initial_state"]),
        tr.DischargeRestProfile(label, segments, tr.POSITIVE_DISCHARGE))
    return (np.array([x.terminal_voltage_v for x in run.trajectory]), run.result.validity[tr.MODEL_ID].status.value,
            {"result_id": run.result.result_id, "replay_record_sha256": run.replay.digest,
             "parameter_set_sha256": run.result.provenance.metadata["parameter_set_sha256"]})


def predict_rint(w: bfit.Window, axis: Axis, q_ah: float, r0: float) -> np.ndarray:
    cell = axis.cell(q_ah, r0, "LG-HG2-SN62A4")
    zp, out = axis.zp(w.z0), []
    for k in range(1, len(w.t)):
        dt, cur = float(w.t[k] - w.t[k - 1]), float(w.i[k])
        if cur > 0.0:
            step = evaluate_step(cell, DischargeLoad(load_id=f"k{k}", current=Q(cur, "ampere"),
                                                     initial_state_of_charge=Q(zp, "dimensionless"),
                                                     cell_temperature=Q(float(w.temp[k]), "degC"),
                                                     duration=Q(dt, "second")))
            zp, v = step.final_state_of_charge, step.terminal_voltage
        else:
            v = float(np.interp(zp, [a for a, _ in axis.knots], [b for _, b in axis.knots]))
        out.append(v)
    return np.array(out)


def metrics(res: list[np.ndarray], cur: list[np.ndarray]) -> dict[str, Any]:
    allr = np.concatenate(res)
    load_ = np.concatenate([r[i > 0] for r, i in zip(res, cur)])
    rest = np.concatenate([r[i == 0] for r, i in zip(res, cur)])
    lag = [np.corrcoef(r[:-1], r[1:])[0, 1] for r in res if len(r) > 3 and np.std(r) > 0]
    mv = lambda x: 1000 * float(x)  # noqa: E731
    return {"samples": int(allr.size), "rmse_mV": mv(np.sqrt(np.mean(allr ** 2))), "mae_mV": mv(np.mean(np.abs(allr))),
            "bias_mV": mv(np.mean(allr)), "max_abs_mV": mv(np.max(np.abs(allr))),
            "p95_abs_mV": mv(np.percentile(np.abs(allr), 95)), "lag1_autocorrelation_mean": float(np.mean(lag)),
            "load_rmse_mV": mv(np.sqrt(np.mean(load_ ** 2))) if load_.size else None,
            "rest_rmse_mV": mv(np.sqrt(np.mean(rest ** 2))) if rest.size else None,
            "load_samples": int(load_.size), "rest_samples": int(rest.size),
            "per_window_rmse_mV": [mv(np.sqrt(np.mean(r ** 2))) for r in res]}


def paired_bootstrap(res_a, res_b, b=2000, seed=0):
    rng = np.random.default_rng(seed)
    sa = np.array([np.sum(r ** 2) for r in res_a]); sb = np.array([np.sum(r ** 2) for r in res_b])
    n = np.array([r.size for r in res_a])
    diffs = []
    for _ in range(b):
        j = rng.integers(0, len(res_a), len(res_a))
        diffs.append(math.sqrt(sa[j].sum() / n[j].sum()) - math.sqrt(sb[j].sum() / n[j].sum()))
    diffs = 1000 * np.array(diffs)
    point = 1000 * (math.sqrt(sa.sum() / n.sum()) - math.sqrt(sb.sum() / n.sum()))
    ci = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
    verdict = ("NOT_ASSESSABLE (fewer than 2 units: no interval)" if len(res_a) < 2
               else "1RC_BETTER" if ci[0] > 0 else "RINT_BETTER" if ci[1] < 0 else "NOT_DISTINGUISHED")
    return {"rmse_rint_minus_1rc_mV": point, "ci95_mV": ci, "verdict": verdict, "units": len(res_a),
            "scope": "windows/tests of ONE cell; the bootstrap does not generalize beyond them"}


def acceptance(m: dict[str, Any], limits: dict[str, float], outside: int) -> str:
    """Applicability precedes evidence, in BOTH directions (review): a set holding any unit outside the validated
    domain neither supports nor contradicts the model, so it is NOT_ASSESSABLE whatever its error."""
    if outside:
        return f"NOT_ASSESSABLE ({outside} outside the validated domain)"
    passed = m["rmse_mV"] <= limits["RMSE_mV_max"] and m["p95_abs_mV"] <= limits["P95_abs_mV_max"]
    return "PASS" if passed else "FAIL"


def main() -> int:
    cal = load_calibration()
    ocv = bfit.Ocv(load("ocv"))
    axis = Axis(ocv)
    p1, pr = cal["models"]["1rc"]["parameters"], cal["models"]["rint"]["parameters"]
    basis = (f"identified on LG HG2 25 degC 1C/6C HPPC pulses (results/CALIBRATION.json sha256 "
             f"{(RESULTS / 'CALIBRATION.sha256').read_bytes().split()[0].decode()}); decision "
             f"{cal['identifiability']['decision']}; one cell")
    draws = np.array(cal["identifiability"]["bootstrap_draws"])
    out: dict[str, Any] = {"schema": "forge.battery_1rc_identifiability.validation/1",
                           "preregistration_sha256": prereg_sha256(),
                           "calibration_sha256": (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode(),
                           "identifiability_decision": cal["identifiability"]["decision"],
                           "charge_axis": {"z_lo": axis.z_lo, "rule": "z' = (z - z_lo) / (1 - z_lo), Q' = Q (1 - z_lo)"},
                           "scope": "ONE LG HG2 cell at 25 degC; discharge/rest only; SOC >= 0.10; current interpolation "
                                    "inside the calibrated 3-18 A range. Within-cell evidence, not cross-cell transfer",
                           "roles": {}}
    timings = {}
    (RESULTS / "plots").mkdir(parents=True, exist_ok=True)
    plans = (("calibration", "calibration", "windows", None),
             ("heldout_pulses", "heldout_pulses", "windows", ACC["heldout_pulses"]),
             ("heldout_cc", "heldout_cc", "tests", ACC["heldout_cc"]),
             ("descriptive", "descriptive", "windows", None))
    for role, name, key, limits in plans:
        doc = load(name)
        windows = [bfit.Window(w, doc["q_hppc_Ah"]) for w in doc[key]]
        labels = [f"{role}-{k}" for k in range(len(windows))]
        started = time.perf_counter()
        pred1, status, bind = zip(*(predict_route(w, axis, doc["q_hppc_Ah"], p1, cal["parameter_set"], basis, lab)
                                    for w, lab in zip(windows, labels)))
        timings[f"{role}_1rc_s"] = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        predr = [predict_rint(w, axis, doc["q_hppc_Ah"], pr["R0"]) for w in windows]
        timings[f"{role}_rint_s"] = round(time.perf_counter() - started, 3)
        obs = [w.v[1:] for w in windows]
        cur = [w.i[1:] for w in windows]
        res1 = [o - p for o, p in zip(obs, pred1)]
        resr = [o - p for o, p in zip(obs, predr)]
        lo_b, hi_b = [], []
        for w in windows:
            preds = np.array([bfit.predict(w, ocv, math.exp(d[0]), math.exp(d[1]), math.exp(d[2])) for d in draws])
            lo_b.append(np.percentile(preds, 2.5, axis=0)); hi_b.append(np.percentile(preds, 97.5, axis=0))
        inside = np.concatenate([(o >= lo) & (o <= hi) for o, lo, hi in zip(obs, lo_b, hi_b)])
        half = np.concatenate([(hi - lo) / 2 for lo, hi in zip(lo_b, hi_b)])
        outside = sum(s != "in_domain" for s in status)
        entry = {"units": len(windows), "route_validity": {s: status.count(s) for s in sorted(set(status))},
                 "1rc": metrics(res1, cur), "rint": metrics(resr, cur),
                 "comparison": paired_bootstrap(resr, res1),
                 "comparison_load": paired_bootstrap([r[i > 0] for r, i in zip(resr, cur)],
                                                     [r[i > 0] for r, i in zip(res1, cur)]),
                 "comparison_rest": paired_bootstrap([r[i == 0] for r, i in zip(resr, cur)],
                                                     [r[i == 0] for r, i in zip(res1, cur)]),
                 "parameter_uncertainty_1rc": {"band": "2.5-97.5 % of 200 joint bootstrap parameter sets",
                                               "median_half_width_mV": 1000 * float(np.median(half)),
                                               "coverage_of_measurements": float(inside.mean())},
                 "per_unit": [{**w.meta, "z0": w.z0, "route_validity": s, **b} for w, s, b in zip(windows, status, bind)]}
        if limits:
            for m in ("1rc", "rint"):
                entry[m]["acceptance"] = acceptance(entry[m], limits, outside)
                load_only = np.concatenate([r[i > 0] for r, i in zip(res1 if m == "1rc" else resr, cur)])
                rmse_load = 1000 * float(np.sqrt(np.mean(load_only ** 2)))
                p95_load = 1000 * float(np.percentile(np.abs(load_only), 95))
                entry[m]["load_only_against_the_same_limits"] = {
                    "not_preregistered": True, "rmse_mV": rmse_load, "p95_abs_mV": p95_load,
                    "would_pass": rmse_load <= limits["RMSE_mV_max"] and p95_load <= limits["P95_abs_mV_max"]}
            temps = np.concatenate([w.temp for w in windows])
            unwidened = [cal["parameter_set"]["temperature_range_C"][0] + 1.0,
                         cal["parameter_set"]["temperature_range_C"][1] - 1.0]
            entry["temperature_C"] = {"min": float(temps.min()), "max": float(temps.max()),
                                      "calibration_range_unwidened": unwidened,
                                      "in_domain_only_because_of_the_preregistered_1C_widening":
                                          bool(temps.max() > unwidened[1] or temps.min() < unwidened[0])}
        else:
            entry["note"] = "calibration fit or descriptive-only set: no acceptance"
        out["roles"][role] = entry
        for pick in sorted({0, len(windows) - 1}):
            w = windows[pick]
            stem = f"{role}_{pick}_{w.meta.get('level_A', w.meta.get('test', ''))}"
            svg_plot(RESULTS / "plots" / f"{stem}_voltage.svg", f"{role} #{pick} {w.meta}", w.t[1:],
                     [("measured", obs[pick], "black"), ("1RC (route)", pred1[pick], "#1f77b4"),
                      ("Rint (production kernel)", predr[pick], "#d62728")], "terminal voltage (V)")
            svg_plot(RESULTS / "plots" / f"{stem}_residual.svg", f"{role} #{pick}: measured - predicted", w.t[1:],
                     [("1RC", res1[pick], "#1f77b4"), ("Rint", resr[pick], "#d62728")], "residual (V)")
    for role in ("heldout_pulses", "heldout_cc"):
        for m in ("1rc", "rint"):
            out["roles"][role][m]["calibration_to_heldout_rmse_gap_mV"] = (
                out["roles"][role][m]["rmse_mV"] - out["roles"]["calibration"][m]["rmse_mV"])
    data = json.dumps(out, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "VALIDATION.json").write_bytes(data)
    (RESULTS / "VALIDATION.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    (RESULTS / "TIMINGS_validation.json").write_bytes(json.dumps(timings, sort_keys=True).encode() + b"\n")
    for role, e in out["roles"].items():
        print(role, e["units"], e["route_validity"],
              {m: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in e[m].items()
                   if k in ("rmse_mV", "p95_abs_mV", "bias_mV", "max_abs_mV", "load_rmse_mV", "rest_rmse_mV",
                            "lag1_autocorrelation_mean", "acceptance")} for m in ("1rc", "rint")})
        print("   cmp", {k: (round(e[k]["rmse_rint_minus_1rc_mV"], 2), [round(x, 2) for x in e[k]["ci95_mV"]],
                          e[k]["verdict"]) for k in ("comparison", "comparison_load", "comparison_rest")},
              "param band", round(e["parameter_uncertainty_1rc"]["median_half_width_mV"], 2),
              "coverage", round(e["parameter_uncertainty_1rc"]["coverage_of_measurements"], 3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
