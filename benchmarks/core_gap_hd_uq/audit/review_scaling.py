"""Core Gap Review, scaling (Phases 1 and 11): frozen grid vs the candidate local route.

Same family (TabulatedForm LINEAR, uniform knots), same B3 data and sigmas, same
production adapter for every prediction. Grid rule: 9 points per axis over +/-4
marginal standard errors (the B3 rule at p = 5). Measured serially for p <= 4;
p = 5 is taken from the committed B3 12-worker run; p >= 6 is PROJECTED from
the measured per-row cost and memory and labelled so.
"""

from __future__ import annotations

import json
import threading
import time
import tracemalloc

import numpy as np
import psutil


class PeakRss:
    def __init__(self, interval=0.01):
        self.proc = psutil.Process()
        self.interval = interval
        self.peak = self.base = self.proc.memory_info().rss
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.peak = max(self.peak, self.proc.memory_info().rss)
            time.sleep(self.interval)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        self.peak = max(self.peak, self.proc.memory_info().rss)


def run(R):
    P = R.P
    B = R._load("_review_battery_scaling", R.HERE / "review_battery.py")
    H, results = B.load_b3(R)
    from engcore.domains.battery import calibration as bc
    from engcore.inference import GridResolutionError, assess_identifiability, gaussian_grid_posterior
    from engcore.uq import PredictiveObservableSpec, posterior_predictive_uq

    data = H.Data()
    cal, held = data.split.calibration, data.split.held_out
    n_cal, n_held = len(cal.observations), len(held.observations)
    y, s = H.weighted(cal)
    yh, sh = H.weighted(held)
    out = {"schema": "core_gap_hd_uq_scaling/1", "family": "TabulatedForm LINEAR, uniform knots, B3 data", "n_cal": n_cal, "n_held": n_held,
           "grid_rule": {"per_axis": 9, "span_marginal_se": 4}, "local": {}, "grid_measured": {}, "grid_projected": {}}

    for p in (2, 5, 10, 20, 41):
        param = bc.TabulatedKnotParameterization(tuple(np.linspace(0.0, 1.0, p)), source=f"scaling-p{p}")
        fit = H.core_calibrate(param, cal, data, data.split.heldout_dataset_id)
        estimate = fit["_estimates"]
        problem = P.LocalProblem(names=tuple(param.names), forward=lambda t, pa=param: H.forward(pa, t, cal, data), observed=y, sigma=s,
                                 lower=np.full(p, 2.0), upper=np.full(p, 3.6), predict=lambda t, pa=param: H.forward(pa, t, held, data),
                                 predict_sigma=sh, declared_affine=True)
        t0 = time.perf_counter()
        probe = P.local_gaussian(problem, estimate)
        wall = time.perf_counter() - t0
        calls = dict(probe["forward_calls"])
        tracemalloc.start()  # separate pass: tracemalloc slows Python ~4x, so it never times anything
        P.local_gaussian(problem, estimate)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        out["local"][p] = {"claim": probe["claim"], "identifiability": probe.get("identifiability", {}).get("status"),
                           "wall_seconds": wall, "forward_calls": calls,
                           "production_predictions": calls["forward"] * n_cal + calls["predict"] * n_held,
                           "python_heap_peak_bytes_tracemalloc": peak,
                           "calibration": {"evaluations": fit["optimizer_evaluations"], "admitted_predictions": fit["admitted_forward_predictions"],
                                           "wall_seconds": fit["wall_seconds_informational"]}}
        print(f"local p={p:2}: {wall:.2f}s calls={calls} heap={peak / 1e6:.1f} MB claim={probe['claim']}", flush=True)

    per_row_seconds, per_row_bytes = [], []
    for p in (2, 3, 4):
        param = bc.TabulatedKnotParameterization(tuple(np.linspace(0.0, 1.0, p)), source=f"scaling-p{p}")
        full = H.wls(param, cal, data)
        se = np.sqrt(np.diag(full["cov"]))
        axes = [np.linspace(t - 4 * e, t + 4 * e, 9) for t, e in zip(full["theta"], se)]
        grid = [tuple(map(float, r)) for r in np.array(np.meshgrid(*axes, indexing="ij")).reshape(p, -1).T]
        with PeakRss() as mem:
            t0 = time.perf_counter()
            table = bc.curve_forward_table(cal, grid, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
            t_cal = time.perf_counter() - t0
            posterior = gaussian_grid_posterior(table, cal)
            try:
                status = assess_identifiability(posterior).status.value
            except GridResolutionError:
                status = "GRID_TOO_COARSE_FOR_INFERENCE"
            cal_table_rss = mem.proc.memory_info().rss - mem.base
            del table
            t1 = time.perf_counter()
            htable = bc.curve_forward_table(held, grid, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
            for obs in held.observations:
                posterior_predictive_uq(posterior, htable, PredictiveObservableSpec(obs.key, H.VOLT, obs.sigma), twin=H.TWIN,
                                        model=bc.RINT_MODEL_REF, source_ref=obs.source_ref)
            t_held = time.perf_counter() - t1
        rows = len(grid)
        out["grid_measured"][p] = {"grid_points": rows, "production_predictions": rows * (n_cal + n_held),
                                   "wall_seconds_calibration_table_and_posterior": t_cal, "wall_seconds_held_out_table_and_uq": t_held,
                                   "wall_seconds_total": t_cal + t_held, "peak_rss_increase_bytes": mem.peak - mem.base,
                                   "rss_increase_with_calibration_table_bytes": cal_table_rss, "identifiability": status, "workers": 1}
        per_row_seconds.append((t_cal + t_held) / rows)
        if rows >= 6561:
            per_row_bytes.append(max(cal_table_rss, 1) / rows)
        print(f"grid p={p}: rows={rows} {t_cal + t_held:.1f}s rss+={(mem.peak - mem.base) / 1e6:.1f} MB ident={status}", flush=True)

    committed = {m: results["models"][m]["routes"]["CORE_GRID"]["grid"] for m in ("P4", "T5")}
    out["grid_measured"]["5_committed_b3_12_workers"] = {m: {"grid_points": g["points"], "wall_seconds_informational": g["wall_seconds_informational"],
                                                            "production_predictions": g["points"] * (n_cal + n_held)} for m, g in committed.items()}
    sec = float(np.median(per_row_seconds[-1:]))
    bytes_row = float(per_row_bytes[-1]) if per_row_bytes else float("nan")
    for p in (5, 6, 7, 10, 20, 41):
        rows = 9 ** p
        out["grid_projected"][p] = {"label": "PROJECTED from p=4 serial measurement", "grid_points": float(rows),
                                    "production_predictions": float(rows * (n_cal + n_held)),
                                    "serial_wall_seconds": rows * sec, "serial_wall_hours": rows * sec / 3600,
                                    "wall_hours_24_ideal_workers": rows * sec / 3600 / 24,
                                    "calibration_table_bytes": rows * bytes_row, "calibration_table_gib": rows * bytes_row / 2 ** 30}
    out["per_row_seconds_serial_measured_p4"] = sec
    out["calibration_table_bytes_per_row_measured_p4"] = bytes_row
    return out
