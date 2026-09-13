"""Part 14: performance -- the V1 grid route against the V2 local route at p = 2, 5, 10, 20, 41.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/performance.py

Same family (TabulatedForm LINEAR, uniform knots), same B3 data and sigmas, same production battery adapter for every
prediction, as in the HD-UQ review.

* **V2** is MEASURED at every p, calibration included. Its cost is split into the O(p) validity diagnostics plus
  Jacobian (4p + 1 evaluations) and the multistart. The linearized predictive is timed separately.
* **The V1 grid** (9 nodes per axis over +/-4 marginal SE, the B3 rule at p = 5; build, posterior, the repaired
  V1 checks and the frozen predictive) is MEASURED serially at p = 2, 3 and 4. p = 5 is the committed B3 run on
  12 workers. p >= 6 is PROJECTED from the measured p = 4 per-row cost and labelled PROJECTED.

Wall time comes from timing passes. Memory comes from a separate tracemalloc pass, so tracemalloc never times
anything.

Writes benchmarks/core_v2_hybrid_uq/PERFORMANCE.json.
"""

from __future__ import annotations

import json
import time
import tracemalloc

import numpy as np

from common import b3_harness, dump

from engcore.hybrid_uq import MultistartPolicy, linearized_predictive_uq, route_uncertainty
from engcore.inference import CalibrationSpec, GridResolutionError, NoiseModel, assess_identifiability, calibrate, gaussian_grid_posterior
from engcore.uq import PredictiveObservableSpec, posterior_predictive_uq


def main():
    H = b3_harness()
    bc = H.bc
    data = H.Data()
    cal, held = data.split.calibration, data.split.held_out
    n_cal, n_held = len(cal.observations), len(held.observations)
    specs = [PredictiveObservableSpec(o.key, H.VOLT, o.sigma) for o in held.observations]
    results = json.loads((H.ROOT / "benchmarks" / "battery_flagship_b3" / "RESULTS.json").read_text(encoding="utf-8"))
    out = {"schema": "core_v2_hybrid_uq_performance/1", "family": "TabulatedForm LINEAR, uniform knots, B3 data", "n_cal": n_cal, "n_held": n_held,
           "grid_rule": {"per_axis": 9, "span_marginal_se": 4}, "v2_measured": {}, "v1_grid_measured": {}, "v1_grid_projected": {}}

    for p in (2, 5, 10, 20, 41):
        param = bc.TabulatedKnotParameterization(tuple(np.linspace(0.0, 1.0, p)), source=f"v2-scaling-p{p}")
        spec = CalibrationSpec(
            parameters=bc.build_curve_parameter_set(param, lower=H.Q(H.BOUNDS[0], H.VOLT), upper=H.Q(H.BOUNDS[1], H.VOLT)),
            fixed={H.ctx.NOMINAL_CAPACITY: H.FIXED.nominal_capacity, H.ctx.INTERNAL_RESISTANCE: H.FIXED.internal_resistance,
                   H.ctx.COULOMBIC_EFFICIENCY: H.FIXED.coulombic_efficiency, H.ctx.CELL_TEMPERATURE: H.CELL_TEMPERATURE,
                   H.ctx.DISCHARGE_CURRENT: H.CONDITIONING_CURRENT},
            initial_point={n: H.Q(float(v), H.VOLT) for n, v in zip(param.names, H.initial_point(p))}, noise_model=NoiseModel())
        calls = {"cal": 0, "held": 0}
        cal_ev = bc.curve_forward_evaluator(cal, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        held_ev = bc.curve_forward_evaluator(held, fixed=H.FIXED, conditions=data.conditions, parameterization=param)

        def forward(theta, ev=cal_ev):
            calls["cal"] += 1
            return ev(theta)

        def predict(theta, ev=held_ev):
            calls["held"] += 1
            return ev(theta)

        t0 = time.perf_counter()
        fit = calibrate(spec, cal, forward, heldout_dataset_id=data.split.heldout_dataset_id, max_evaluations=H.MAX_EVALUATIONS, seed=H.SEED)
        t_cal, c_cal = time.perf_counter() - t0, calls["cal"]
        t0 = time.perf_counter()
        routed = route_uncertainty(calibration=fit, observations=cal, forward=forward, multistart=None)
        t_diag, c_diag = time.perf_counter() - t0, calls["cal"] - c_cal
        t0 = time.perf_counter()
        routed_ms = route_uncertainty(calibration=fit, observations=cal, forward=forward, multistart=MultistartPolicy())
        t_ms, c_ms = time.perf_counter() - t0, calls["cal"] - c_cal - c_diag
        t0 = time.perf_counter()
        linearized_predictive_uq(routed_ms.local_posterior, predict, specs)
        t_pred, c_pred = time.perf_counter() - t0, calls["held"]
        tracemalloc.start()
        route_uncertainty(calibration=fit, observations=cal, forward=forward, multistart=MultistartPolicy())
        linearized_predictive_uq(routed_ms.local_posterior, predict, specs)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        out["v2_measured"][p] = {
            "label": "MEASURED", "decision": routed_ms.decision.value, "claim": routed_ms.claim.value,
            "identifiability": None if routed_ms.identifiability is None else routed_ms.identifiability.status.value,
            "calibration": {"wall_seconds": t_cal, "forward_evaluations": c_cal},
            "diagnostics_and_jacobian_without_multistart": {"wall_seconds": t_diag, "forward_evaluations": c_diag, "expected_4p_plus_1": 4 * p + 1},
            "route_with_default_multistart": {"wall_seconds": t_ms, "forward_evaluations": c_ms},
            "linearized_predictive": {"wall_seconds": t_pred, "forward_evaluations": c_pred},
            "production_predictions": (c_cal + c_diag + c_ms) * n_cal + c_pred * n_held,
            "python_heap_peak_bytes_tracemalloc_route_and_predictive": peak,
        }
        print(f"V2 p={p:2}: cal {t_cal:.2f}s/{c_cal}  diag {t_diag:.2f}s/{c_diag}  multistart route {t_ms:.2f}s/{c_ms}  "
              f"predictive {t_pred:.2f}s/{c_pred}  heap {peak / 1e6:.2f} MB  {routed_ms.claim.value}", flush=True)

    per_row = []
    for p in (2, 3, 4):
        param = bc.TabulatedKnotParameterization(tuple(np.linspace(0.0, 1.0, p)), source=f"v2-scaling-p{p}")
        full = H.wls(param, cal, data)
        se = np.sqrt(np.diag(full["cov"]))
        axes = [np.linspace(t - 4 * e, t + 4 * e, 9) for t, e in zip(full["theta"], se)]
        grid = [tuple(map(float, r)) for r in np.array(np.meshgrid(*axes, indexing="ij")).reshape(p, -1).T]
        t0 = time.perf_counter()
        table = bc.curve_forward_table(cal, grid, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        posterior = gaussian_grid_posterior(table, cal)
        try:
            status = assess_identifiability(posterior).status.value
        except GridResolutionError:
            status = "GRID_TOO_COARSE_FOR_INFERENCE"
        htable = bc.curve_forward_table(held, grid, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        refused = 0
        for spec_ in specs:
            try:
                posterior_predictive_uq(posterior, htable, spec_, twin=H.TWIN, model=bc.RINT_MODEL_REF, source_ref="v2-performance")
            except GridResolutionError:
                refused += 1
        wall = time.perf_counter() - t0
        tracemalloc.start()
        table2 = bc.curve_forward_table(cal, grid, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        gaussian_grid_posterior(table2, cal)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows = len(grid)
        per_row.append(wall / rows)
        out["v1_grid_measured"][p] = {"label": "MEASURED (serial)", "grid_points": rows, "production_predictions": rows * (n_cal + n_held),
                                      "wall_seconds": wall, "identifiability": status, "predictive_refusals": refused,
                                      "python_heap_peak_bytes_tracemalloc_calibration_table": peak}
        print(f"V1 grid p={p}: rows {rows} {wall:.1f}s heap {peak / 1e6:.1f} MB {status}", flush=True)
    committed = {m: results["models"][m]["routes"]["CORE_GRID"]["grid"] for m in ("P4", "T5")}
    out["v1_grid_measured"]["5"] = {"label": "MEASURED in the committed B3 run, 12 workers (not re-run)",
                                    "models": {m: {"grid_points": g["points"], "wall_seconds_informational": g["wall_seconds_informational"]} for m, g in committed.items()}}
    sec = per_row[-1]
    bytes_row = out["v1_grid_measured"][4]["python_heap_peak_bytes_tracemalloc_calibration_table"] / out["v1_grid_measured"][4]["grid_points"]
    for p in (10, 20, 41):
        rows = 9.0 ** p
        out["v1_grid_projected"][p] = {"label": "PROJECTED from the p = 4 serial measurement", "grid_points": rows,
                                       "production_predictions": rows * (n_cal + n_held), "serial_wall_seconds": rows * sec,
                                       "serial_wall_years": rows * sec / 3.15576e7, "heap_bytes": rows * bytes_row}
    out["v1_per_row_seconds_measured_p4"] = sec
    dump("PERFORMANCE.json", out)


if __name__ == "__main__":
    main()
