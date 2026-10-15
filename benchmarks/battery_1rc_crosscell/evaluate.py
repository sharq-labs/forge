"""Held-out cross-cell evaluation on Kirkaldy 2024 (opened once, after results/CALIBRATION.json was committed).

1RC predictions run through engcore.domains.battery.thevenin_route.run_thevenin_1rc with the calibration OCV and Q_cal
(STRICT TRANSFER). The route's CellSpecification needs an OCV curve over z in [0, 1] and the knots span [z_lo, 1]: the
charge axis is re-expressed exactly (z' = (z - z_lo) / (1 - z_lo), Q' = Q (1 - z_lo)), as in the LG HG2 experiment; a test
pins route == transcription. Rint: the production kernel on loaded intervals, V = OCV(z) at rest.
The descriptive set (each held-out cell's own OCV and own Q) uses the pinned transcription and carries no verdict.
Writes results/VALIDATION.json (deterministic), results/TIMINGS_validation.json (unpinned) and SVG plots.
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
from .data import PREREG, load, prereg_sha256

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
ACC = PREREG["validation"]["acceptance"]
CELL_ID = "LG-M50T-Kirkaldy2024"


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

    def cell(self, q_ah: float, r0: float) -> CellSpecification:
        curve = DeclaredCurve(quantity=ctx.OCV_CURVE, against=ctx.STATE_OF_CHARGE, against_unit="dimensionless",
                              unit="volt", lower=0.0, upper=1.0, form=TabulatedForm(self.knots),
                              source="data/ocv_cal.json: mean of the calibration cells' GITT rests >= 3000 s and their "
                                     "post-charge rest at z = 1 (which is shorter than 3000 s in 5 of 7 cells), "
                                     "charge axis re-expressed")
        return CellSpecification(cell_id=CELL_ID, nominal_capacity=Q(q_ah * (1.0 - self.z_lo), "ampere_hour"),
                                 internal_resistance=Q(r0, "ohm"), coulombic_efficiency=Q(1.0, "dimensionless"),
                                 open_circuit_voltage_curve=curve)


def arrays(w: dict[str, Any]):
    return tuple(np.asarray(w[c], float) for c in ("time_s", "current_A", "voltage_V", "temperature_C"))


def predict_route(w: dict[str, Any], axis: Axis, q_ah: float, p: dict[str, float], pset: dict[str, Any], basis: str,
                  label: str):
    t, i, _, temp = arrays(w)
    ps = tr.Thevenin1RCParameterSet("kirkaldy2024-m50t-25c-gitt-v1", axis.cell(q_ah, p["R0"]),
                                    Thevenin1RCParameters(Q(p["R1"], "ohm"), Q(p["C1"], "farad")),
                                    Q(pset["temperature_range_C"][0], "degC"), Q(pset["temperature_range_C"][1], "degC"),
                                    Q(pset["max_current_A"], "ampere"), basis)
    segments = tuple(tr.ProfileSegment(Q(float(t[k] - t[k - 1]), "second"), Q(float(i[k]), "ampere"),
                                       Q(float(temp[k]), "degC")) for k in range(1, len(t)))
    run = tr.run_thevenin_1rc(ps, tr.Thevenin1RCInitialState(
        Q(axis.zp(w["z0"]), "dimensionless"), Q(0.0, "volt"), PREREG["construction"]["initial_state"]),
        tr.DischargeRestProfile(label, segments, tr.POSITIVE_DISCHARGE))
    return (np.array([x.terminal_voltage_v for x in run.trajectory]), run.result.validity[tr.MODEL_ID].status.value,
            {"result_id": run.result.result_id, "replay_record_sha256": run.replay.digest,
             "parameter_set_sha256": run.result.provenance.metadata["parameter_set_sha256"]})


def predict_rint(w: dict[str, Any], axis: Axis, q_ah: float, r0: float) -> np.ndarray:
    t, i, _, temp = arrays(w)
    cell = axis.cell(q_ah, r0)
    zs, vs = [a for a, _ in axis.knots], [b for _, b in axis.knots]
    zp, out = axis.zp(w["z0"]), []
    for k in range(1, len(t)):
        dt, cur = float(t[k] - t[k - 1]), float(i[k])
        if cur > 0.0:
            step = evaluate_step(cell, DischargeLoad(load_id=f"k{k}", current=Q(cur, "ampere"),
                                                     initial_state_of_charge=Q(zp, "dimensionless"),
                                                     cell_temperature=Q(float(temp[k]), "degC"),
                                                     duration=Q(dt, "second")))
            zp, v = step.final_state_of_charge, step.terminal_voltage
        else:
            v = float(np.interp(zp, zs, vs))
        out.append(v)
    return np.array(out)


def metrics(res: list[np.ndarray], cur: list[np.ndarray]) -> dict[str, Any]:
    allr = np.concatenate(res)
    load_ = np.concatenate([r[i > 0] for r, i in zip(res, cur)])
    rest = np.concatenate([r[i == 0] for r, i in zip(res, cur)])
    mv = lambda x: 1000 * float(x)  # noqa: E731
    return {"samples": int(allr.size), "rmse_mV": mv(np.sqrt(np.mean(allr ** 2))), "mae_mV": mv(np.mean(np.abs(allr))),
            "bias_mV": mv(np.mean(allr)), "max_abs_mV": mv(np.max(np.abs(allr))),
            "p95_abs_mV": mv(np.percentile(np.abs(allr), 95)),
            "load_only": {"samples": int(load_.size), "rmse_mV": mv(np.sqrt(np.mean(load_ ** 2))),
                          "p95_abs_mV": mv(np.percentile(np.abs(load_), 95)), "bias_mV": mv(np.mean(load_))},
            "rest_rmse_mV": mv(np.sqrt(np.mean(rest ** 2))) if rest.size else None, "rest_samples": int(rest.size),
            "per_window_rmse_mV": [mv(np.sqrt(np.mean(r ** 2))) for r in res]}


def cell_block_bootstrap(res_a, res_b, cells, b=2000, seed=0):
    """RMSE_a - RMSE_b with HELD-OUT CELLS as the resampling unit (preregistered)."""
    units = sorted(set(cells))
    sa = np.array([sum(float(np.sum(r ** 2)) for r, c in zip(res_a, cells) if c == u) for u in units])
    sb = np.array([sum(float(np.sum(r ** 2)) for r, c in zip(res_b, cells) if c == u) for u in units])
    n = np.array([sum(r.size for r, c in zip(res_a, cells) if c == u) for u in units])
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(b):
        j = rng.integers(0, len(units), len(units))
        diffs.append(math.sqrt(sa[j].sum() / n[j].sum()) - math.sqrt(sb[j].sum() / n[j].sum()))
    diffs = 1000 * np.array(diffs)
    point = 1000 * (math.sqrt(sa.sum() / n.sum()) - math.sqrt(sb.sum() / n.sum()))
    ci = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
    verdict = ("NOT_ASSESSABLE (fewer than 2 cells: no interval)" if len(units) < 2
               else "1RC_BETTER" if ci[0] > 0 else "RINT_BETTER" if ci[1] < 0 else "NOT_DISTINGUISHED")
    return {"rmse_rint_minus_1rc_mV": point, "ci95_mV": ci, "verdict": verdict, "units": len(units),
            "unit": "held-out cell"}


def acceptance(m: dict[str, Any], limits: dict[str, float], outside: int) -> str:
    """Applicability first, in BOTH directions; then the pooled AND the load-only samples must meet the limits."""
    if outside:
        return f"NOT_ASSESSABLE ({outside} outside the validated domain)"
    ok = lambda x: x["rmse_mV"] <= limits["RMSE_mV_max"] and x["p95_abs_mV"] <= limits["P95_abs_mV_max"]  # noqa: E731
    if not limits.get("also_load_only", False):
        raise ValueError("the preregistered acceptance requires the load-only check")
    return "PASS" if ok(m) and ok(m["load_only"]) else "FAIL"


def gate_comparison(comparison: dict[str, Any], outside: int) -> dict[str, Any]:
    """Applicability precedes evidence: a set holding out-of-domain windows yields no model-comparison verdict either.
    The point and interval stay as description; the unconditioned label moves out of the verdict field."""
    if not outside:
        return comparison
    return {**comparison, "verdict": f"NOT_ASSESSABLE ({outside} windows outside the validated domain)",
            "unconditioned_descriptive_label": comparison["verdict"]}


POST_OPENING_CHANGES = {
    "first_run_validation_sha256": "eef51a32ba5a5690e5535b2d5212b34189b68930a442691078dc8fc72fa8d289",
    "second_run_validation_sha256": "db79821ddc7a43ad6c7f79edc612b134cf07ed43b00fa1e0d3c40d1374c4b6df",
    "third_run_validation_sha256": "c631e1c6fb3219d0195a35ccf0e18ccd657d98798ee331cd40b88980c5acfbf3",
    "kept_at": "results/superseded/VALIDATION_run1.json, VALIDATION_run2.json and VALIDATION_run3.json",
    "changes": [
        "run 2 added descriptive fields only (out_of_domain_attribution, in_domain_windows_only); every run-1 field was "
        "compared and found identical",
        "run 3 gated the Rint-vs-1RC comparison verdict to NOT_ASSESSABLE when a set holds out-of-domain windows "
        "(stricter only; the preregistered comparison rule gated only on fewer than 2 units); run-2 fields other than "
        "the two comparison verdicts were identical",
        "run 4 (independent review): the unconditioned comparison label moved out of the verdict field; the calibration "
        "role's comparison is marked IN_SAMPLE; the OCV curve source text was corrected (this changes the route's "
        "parameter-set digests in per_unit, not any voltage); held-out maximum currents and the calibrated SOC span "
        "were added. Acceptance values and every metric are unchanged from run 1",
    ],
    "data_changes_after_opening": "data/exclusions.json gained dropout counts and split its dropout reason (in the "
                                  "pulse / only in the rest); the three window roles and ocv_cal are byte-identical",
}


def attribute(ws, status, pset) -> dict[str, int]:
    """Which declared condition puts each window outside; must agree with the route's own status, window by window."""
    lo, hi = pset["temperature_range_C"]
    out: dict[str, int] = {}
    for w, s in zip(ws, status):
        _, i, _, temp = arrays(w)
        why = [n for n, f in (("temperature_below_calibration_min", temp[1:].min() < lo),
                              ("temperature_above_calibration_max", temp[1:].max() > hi),
                              ("current_above_calibration_max", i[1:].max() > pset["max_current_A"])) if f]
        if bool(why) != (s != "in_domain"):
            raise ValueError("the attribution disagrees with the route's validity status")
        key = "+".join(why) or "in_domain"
        out[key] = out.get(key, 0) + 1
    return out


def own_axis_descriptive(doc_windows, own_doc, p1, pr, q_cal):
    """Parameter transfer only: each held-out cell's own OCV knots and own Q (transcription; no verdict)."""
    out = {}
    for cell, info in sorted(own_doc["cells"].items()):
        ocv = bfit.Ocv({"knots_z_V_cells": info["knots_z_V"]})
        scale = q_cal / info["q_own_Ah"]
        ws = [w for w in doc_windows if w["cell"] == cell]
        b = bfit.Batch(ws, q_cal, z_scale=scale)
        z_end = b.z0[:, None] - np.cumsum(b.i * b.dt, axis=1) / b.q_as
        keep = np.array([float(np.min(z[m])) >= max(0.10, ocv.z[0]) for z, m in zip(z_end, b.mask)])
        if not keep.any():
            out[cell] = {"windows": 0, "excluded_outside_own_scope": int(len(ws))}
            continue
        b = b.subset(np.where(keep)[0])
        r1 = (b.v - bfit.predict(b, ocv, p1["R0"], p1["R1"], p1["C1"]))[b.mask]
        rr = (b.v - bfit.predict(b, ocv, pr["R0"]))[b.mask]
        ld = (b.i > 0)[b.mask]
        out[cell] = {"windows": int(keep.sum()), "excluded_outside_own_scope": int((~keep).sum()),
                     "q_own_Ah": info["q_own_Ah"],
                     "1rc_rmse_mV": 1000 * float(np.sqrt(np.mean(r1 ** 2))),
                     "1rc_load_rmse_mV": 1000 * float(np.sqrt(np.mean(r1[ld] ** 2))),
                     "rint_rmse_mV": 1000 * float(np.sqrt(np.mean(rr ** 2)))}
    return out


def verify_route_on_real_windows() -> list[str]:
    """The vectorised transcription (used by the fit, the bootstrap bands and the descriptive set) against the engcore
    route on the first and last window of every window role. Needs the rebuilt window roles: ``--verify-route``."""
    problems = []
    try:
        cal = load_calibration()
        ocv = bfit.Ocv(load("ocv_cal"))
        docs = {role: load(role) for role in ("calibration", "heldout_gitt25", "heldout_gitt5")}
    except (OSError, ValueError, KeyError) as exc:
        return [f"cannot load the window roles: {type(exc).__name__}: {exc}"]
    p = cal["models"]["1rc"]["parameters"]
    for role, doc in docs.items():
        for w in (doc["windows"][0], doc["windows"][-1]):
            route, _, _ = predict_route(w, Axis(ocv), doc["q_Ah"], p, cal["parameter_set"], "verify", "verify")
            b = bfit.Batch([w], doc["q_Ah"])
            fast = bfit.predict(b, ocv, p["R0"], p["R1"], p["C1"])[0][b.mask[0]]
            gap = float(np.max(np.abs(route - fast)))
            if not gap < 1e-9:
                problems.append(f"{role} {w['cell']} {w['pulse_start_s']:.1f}: route - transcription = {gap:.3e} V")
    return problems


def main() -> int:
    import sys
    if sys.argv[1:] == ["--verify-route"]:
        problems = verify_route_on_real_windows()
        print(json.dumps({"problems": problems}, indent=1))
        return 1 if problems else 0
    cal = load_calibration()
    ocv = bfit.Ocv(load("ocv_cal"))
    axis = Axis(ocv)
    p1, pr = cal["models"]["1rc"]["parameters"], cal["models"]["rint"]["parameters"]
    cal_sha = (RESULTS / "CALIBRATION.sha256").read_bytes().split()[0].decode()
    basis = (f"identified on Kirkaldy 2024 LG M50T calibration cells {', '.join(cal['cells'])} (25-pulse GITT, 25 degC; "
             f"results/CALIBRATION.json sha256 {cal_sha}); decision {cal['identifiability']['decision']}")
    draws = np.array(cal["identifiability"]["bootstrap_draws"])
    out: dict[str, Any] = {"schema": "forge.battery_1rc_crosscell.validation/1",
                           "preregistration_sha256": prereg_sha256(), "calibration_sha256": cal_sha,
                           "identifiability_decision": cal["identifiability"]["decision"],
                           "charge_axis": {"z_lo": axis.z_lo, "rule": "z' = (z - z_lo) / (1 - z_lo), Q' = Q (1 - z_lo)"},
                           "scope": "LG M50T at 25 degC base cooling, beginning of life; 2.5 A discharge pulses and "
                                    "rests; SOC >= max(0.10, lowest knot); held-out cells from experiments 1 and 2,2",
                           "measurement_uncertainty": "UNKNOWN (not admitted for this dataset)",
                           "post_opening_changes": POST_OPENING_CHANGES, "roles": {}}
    timings = {}
    (RESULTS / "plots").mkdir(parents=True, exist_ok=True)
    plans = (("calibration", None), ("heldout_gitt25", ACC["primary"]), ("heldout_gitt5", ACC["secondary"]))
    for role, limits in plans:
        doc = load(role)
        ws = doc["windows"]
        q_ah = doc["q_Ah"]
        cells = [w["cell"] for w in ws]
        started = time.perf_counter()
        pred1, status, bind = zip(*(predict_route(w, axis, q_ah, p1, cal["parameter_set"], basis,
                                                  f"{role}-{w['cell']}-{w['pulse_start_s']:.1f}") for w in ws))
        timings[f"{role}_1rc_s"] = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        predr = [predict_rint(w, axis, q_ah, pr["R0"]) for w in ws]
        timings[f"{role}_rint_s"] = round(time.perf_counter() - started, 3)
        obs = [arrays(w)[2][1:] for w in ws]
        cur = [arrays(w)[1][1:] for w in ws]
        res1 = [o - p for o, p in zip(obs, pred1)]
        resr = [o - p for o, p in zip(obs, predr)]
        b = bfit.Batch(ws, q_ah)
        bands = np.array([bfit.predict(b, ocv, math.exp(d[0]), math.exp(d[1]), math.exp(d[2])) for d in draws])
        lo_b, hi_b = np.percentile(bands, 2.5, axis=0)[b.mask], np.percentile(bands, 97.5, axis=0)[b.mask]
        obs_flat = b.v[b.mask]
        outside = sum(s != "in_domain" for s in status)
        load_of = lambda rs: [r[i > 0] for r, i in zip(rs, cur)]  # noqa: E731
        temps = np.concatenate([arrays(w)[3] for w in ws])
        entry = {"units_windows": len(ws), "cells": sorted(set(cells)),
                 "route_validity": {s: status.count(s) for s in sorted(set(status))},
                 "1rc": metrics(res1, cur), "rint": metrics(resr, cur),
                 "comparison": cell_block_bootstrap(resr, res1, cells),
                 "comparison_load": cell_block_bootstrap(load_of(resr), load_of(res1), cells),
                 "parameter_uncertainty_1rc": {
                     "band": "2.5-97.5 % of the 200 cell-block bootstrap parameter sets (parameter uncertainty only; "
                             "measurement uncertainty UNKNOWN, model discrepancy not quantified)",
                     "median_half_width_mV": 1000 * float(np.median((hi_b - lo_b) / 2)),
                     "coverage_of_measurements": float(np.mean((obs_flat >= lo_b) & (obs_flat <= hi_b)))},
                 "temperature_C": {"min": float(temps.min()), "max": float(temps.max()),
                                   "calibration_range": cal["parameter_set"]["temperature_range_C"]},
                 "per_unit": [{"cell": w["cell"], "pulse_start_s": w["pulse_start_s"], "z0": w["z0"],
                               "route_validity": s, **bd} for w, s, bd in zip(ws, status, bind)]}
        per_cell = {}
        for c in sorted(set(cells)):
            r = np.concatenate([x for x, cc in zip(res1, cells) if cc == c])
            per_cell[c] = {"1rc_rmse_mV": 1000 * float(np.sqrt(np.mean(r ** 2))), "1rc_bias_mV": 1000 * float(r.mean())}
        entry["per_cell"] = per_cell
        entry["out_of_domain_attribution"] = attribute(ws, status, cal["parameter_set"])
        keep = [k for k, s in enumerate(status) if s == "in_domain"]
        if limits and keep and outside:
            entry["in_domain_windows_only"] = {
                "not_preregistered": True, "carries_no_verdict": True,
                "why": "descriptive only: the preregistered set is NOT_ASSESSABLE; a post-hoc in-domain subset cannot "
                       "replace it",
                "selection_not_neutral": "the excluded out-of-domain windows carry larger errors than the kept ones; "
                                         "compare the full set's metrics",
                "windows": len(keep), "cells": sorted({cells[k] for k in keep}),
                "1rc": metrics([res1[k] for k in keep], [cur[k] for k in keep]),
                "rint": metrics([resr[k] for k in keep], [cur[k] for k in keep])}
            for m in ("1rc", "rint"):
                entry["in_domain_windows_only"][m].pop("per_window_rmse_mV")
        if limits:
            for m in ("1rc", "rint"):
                entry[m]["acceptance"] = acceptance(entry[m], limits, outside)
            for k in ("comparison", "comparison_load"):
                entry[k] = gate_comparison(entry[k], outside)
            entry["current_A"] = {"heldout_max": float(max(arrays(w)[1].max() for w in ws)),
                                  "calibration_max": cal["parameter_set"]["max_current_A"]}
            entry["current_A"]["excess_mA"] = 1000 * (entry["current_A"]["heldout_max"] -
                                                      entry["current_A"]["calibration_max"])
        else:
            entry["note"] = "calibration fit: no acceptance"
            for k in ("comparison", "comparison_load"):
                entry[k] = {**entry[k], "verdict": "IN_SAMPLE (the parameters were fitted to these cells: no verdict)",
                            "in_sample_descriptive_label": entry[k]["verdict"]}
            z_ends = [w["z0"] - float(np.sum(arrays(w)[1][1:] * np.diff(arrays(w)[0]))) / (3600 * q_ah) for w in ws]
            entry["calibrated_z_span"] = {
                "min": float(min(z_ends)), "max": float(max(w["z0"] for w in ws)),
                "note": "the SOC actually covered by the calibration windows; CALIBRATION.json parameter_set.z_range is "
                        "the OCV knot range, which is wider. The route admits z in [0, 1], so the SOC scope is enforced "
                        "by the role builder only"}
        if role == "heldout_gitt25":
            entry["descriptive_own_ocv_own_q"] = {
                "note": "parameter transfer only, NO verdict; computed on ALL primary windows, including the "
                        "out-of-domain ones",
                "cells": own_axis_descriptive(ws, load("heldout_own_ocv"), p1, pr, doc["q_Ah"])}
        out["roles"][role] = entry
        for pick in sorted({0, len(ws) - 1}):
            t = arrays(ws[pick])[0][1:]
            stem = f"{role}_{pick}"
            title = f"{role} #{pick} {ws[pick]['cell']} t0={ws[pick]['pulse_start_s']:.0f} s"
            svg_plot(RESULTS / "plots" / f"{stem}_voltage.svg", title, t,
                     [("measured", obs[pick], "black"), ("1RC (route)", pred1[pick], "#1f77b4"),
                      ("Rint (production kernel)", predr[pick], "#d62728")], "terminal voltage (V)")
            svg_plot(RESULTS / "plots" / f"{stem}_residual.svg", f"{title}: measured - predicted", t,
                     [("1RC", res1[pick], "#1f77b4"), ("Rint", resr[pick], "#d62728")], "residual (V)")
    for role in ("heldout_gitt25", "heldout_gitt5"):
        for m in ("1rc", "rint"):
            out["roles"][role][m]["calibration_to_heldout_rmse_gap_mV"] = (
                out["roles"][role][m]["rmse_mV"] - out["roles"]["calibration"][m]["rmse_mV"])
    data = json.dumps(out, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "VALIDATION.json").write_bytes(data)
    (RESULTS / "VALIDATION.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    (RESULTS / "TIMINGS_validation.json").write_bytes(json.dumps(timings, sort_keys=True).encode() + b"\n")
    for role, e in out["roles"].items():
        print(role, e["units_windows"], e["route_validity"], e["temperature_C"])
        for m in ("1rc", "rint"):
            x = e[m]
            print("  ", m, {k: round(x[k], 2) for k in ("rmse_mV", "p95_abs_mV", "bias_mV", "max_abs_mV")},
                  "load", {k: round(v, 2) for k, v in x["load_only"].items() if k != "samples"},
                  x.get("acceptance"))
        print("   cmp", {k: (round(e[k]["rmse_rint_minus_1rc_mV"], 2), [round(v, 2) for v in e[k]["ci95_mV"]],
                          e[k]["verdict"]) for k in ("comparison", "comparison_load")},
              "band", round(e["parameter_uncertainty_1rc"]["median_half_width_mV"], 2),
              "coverage", round(e["parameter_uncertainty_1rc"]["coverage_of_measurements"], 3))
        print("   per cell", {c: round(v["1rc_rmse_mV"], 1) for c, v in e["per_cell"].items()})
        if "descriptive_own_ocv_own_q" in e:
            print("   descriptive", e["descriptive_own_ocv_own_q"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
