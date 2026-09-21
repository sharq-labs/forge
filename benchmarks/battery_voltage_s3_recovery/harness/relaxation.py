"""R7: is there a second reproducible relaxation timescale in the measurement?

R7 says not to switch Forge to 2RC before establishing that the data contains a
second mode. This script asks the measurement directly, with no cell model in
it: it finds the rest segments that follow a load in CALIBRATION trajectories
and fits the voltage recovery with one exponential and with two.

    V(t) = V_inf - A1 exp(-t/tau1)                       one mode
    V(t) = V_inf - A1 exp(-t/tau1) - A2 exp(-t/tau2)     two modes

Three questions decide it, and only the third is about fit quality:

1. does the second mode reduce the residual by more than the noise?
2. is its time constant **reproducible** across trajectories, or does it land
   wherever each individual curve happens to want it?
3. is it separated from the first, or is it the same mode written twice?

A second mode that fits better but lands somewhere different on every
trajectory is a free parameter absorbing residuals, which is exactly what R6
says to reject.

    python benchmarks/battery_voltage_s3_recovery/harness/relaxation.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import sys
from typing import Any

import numpy as np
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import corpus as cp  # noqa: E402

RELAXATION_SCHEMA = "battery_voltage_s3_recovery_relaxation/1"

#: Below this current the cell is at rest. The composition pack's own band.
REST_BAND_A = 0.2

#: A rest segment needs this many samples and this much elapsed time before a
#: two-mode fit is even attempted. Two exponentials over a short tail are not
#: identifiable and a fit that "succeeds" there is arithmetic, not evidence.
MIN_REST_SAMPLES = 12
MIN_REST_SECONDS = 120.0

#: A second mode counts as separated at this ratio of time constants.
SEPARATION_RATIO = 3.0


def rest_segments(times, currents, voltages) -> list[dict[str, Any]]:
    """Every rest run that follows at least one loaded sample."""
    out = []
    n = len(times)
    index = 0
    seen_load = False
    while index < n:
        if abs(currents[index]) >= REST_BAND_A:
            seen_load = True
            index += 1
            continue
        start = index
        while index < n and abs(currents[index]) < REST_BAND_A:
            index += 1
        if not seen_load:
            continue
        stop = index
        if stop - start < MIN_REST_SAMPLES:
            continue
        span = float(times[stop - 1] - times[start])
        if span < MIN_REST_SECONDS:
            continue
        out.append(
            {
                "start": start,
                "stop": stop,
                "t": [float(times[i] - times[start]) for i in range(start, stop)],
                "v": [float(voltages[i]) for i in range(start, stop)],
                "span_s": span,
                "samples": stop - start,
            }
        )
    return out


def _fit(t: np.ndarray, v: np.ndarray, modes: int):
    v_last = float(v[-1])
    amplitude = max(abs(float(v[-1] - v[0])), 1e-4)
    span = float(t[-1]) or 1.0
    if modes == 1:
        x0 = [v_last, amplitude, span / 3.0]
        lower = [v_last - 1.0, 0.0, 1.0]
        upper = [v_last + 1.0, 5.0, 10.0 * span]

        def model(x):
            return x[0] - x[1] * np.exp(-t / x[2])
    else:
        x0 = [v_last, amplitude * 0.6, span / 20.0, amplitude * 0.4, span / 2.0]
        lower = [v_last - 1.0, 0.0, 1.0, 0.0, 1.0]
        upper = [v_last + 1.0, 5.0, 10.0 * span, 5.0, 100.0 * span]

        def model(x):
            return x[0] - x[1] * np.exp(-t / x[2]) - x[3] * np.exp(-t / x[4])

    result = least_squares(
        lambda x: model(x) - v,
        x0,
        bounds=(lower, upper),
        method="trf",
        x_scale="jac",
        max_nfev=4000,
    )
    rss = float(result.fun @ result.fun)
    parameters = 2 * modes + 1
    n = int(t.size)
    if n <= parameters + 1 or rss <= 0.0:
        aic = None
    else:
        aic = float(n * math.log(rss / n) + 2 * parameters)
    return {
        "x": [float(v) for v in result.x],
        "rss": rss,
        "rmse_v": math.sqrt(rss / n),
        "aic": aic,
        "parameters": parameters,
        "status": int(result.status),
    }


def main() -> int:
    selection = json.load(
        open(os.path.join(EVIDENCE, "SELECTION.json"), encoding="utf-8")
    )
    channels = cp.load_development_corpus(selection)
    cp.refuse_holdout(selection, channels)
    calibration = {
        row["trajectory_id"]: row
        for row in selection["selected"]
        if row["split"] == "calibration" and row.get("applicability") == "inside"
    }

    rows: list[dict[str, Any]] = []
    for trajectory_id, meta in sorted(calibration.items()):
        trajectory = channels.get(trajectory_id)
        if trajectory is None:
            continue
        ch = trajectory["channels"]
        currents = [-x for x in ch["current_a"]]
        for segment in rest_segments(ch["time_s"], currents, ch["voltage_v"]):
            t = np.asarray(segment["t"], dtype=float)
            v = np.asarray(segment["v"], dtype=float)
            one = _fit(t, v, 1)
            two = _fit(t, v, 2)
            tau1 = one["x"][2]
            tau_fast, tau_slow = sorted((two["x"][2], two["x"][4]))
            amplitude_fast = two["x"][1] if two["x"][2] <= two["x"][4] else two["x"][3]
            amplitude_slow = two["x"][3] if two["x"][2] <= two["x"][4] else two["x"][1]
            rows.append(
                {
                    "trajectory_id": trajectory_id,
                    "cell": meta["cell"],
                    "corner": meta["corner"],
                    "samples": segment["samples"],
                    "span_s": round(segment["span_s"], 1),
                    "one_mode": {
                        "tau_s": round(tau1, 2),
                        "amplitude_v": round(one["x"][1], 5),
                        "rmse_v": round(one["rmse_v"], 6),
                        "aic": round(one["aic"], 2) if one["aic"] is not None else None,
                    },
                    "two_mode": {
                        "tau_fast_s": round(tau_fast, 2),
                        "tau_slow_s": round(tau_slow, 2),
                        "amplitude_fast_v": round(abs(amplitude_fast), 5),
                        "amplitude_slow_v": round(abs(amplitude_slow), 5),
                        "rmse_v": round(two["rmse_v"], 6),
                        "aic": round(two["aic"], 2) if two["aic"] is not None else None,
                        "separated": bool(tau_fast > 0 and tau_slow / tau_fast >= SEPARATION_RATIO),
                        "separation_ratio": (
                            round(tau_slow / tau_fast, 2) if tau_fast > 0 else None
                        ),
                    },
                    "rmse_improvement_v": round(one["rmse_v"] - two["rmse_v"], 6),
                    "aic_prefers": (
                        None
                        if one["aic"] is None or two["aic"] is None
                        else ("two_mode" if two["aic"] < one["aic"] else "one_mode")
                    ),
                }
            )

    if not rows:
        raise SystemExit("no calibration rest segment long enough to analyse")

    separated = [r for r in rows if r["two_mode"]["separated"]]
    aic_two = [r for r in rows if r["aic_prefers"] == "two_mode"]

    def spread(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"n": 0}
        return {
            "n": len(values),
            "median": round(statistics.median(values), 2),
            "p25": round(float(np.percentile(values, 25)), 2),
            "p75": round(float(np.percentile(values, 75)), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "relative_iqr": round(
                (float(np.percentile(values, 75)) - float(np.percentile(values, 25)))
                / max(statistics.median(values), 1e-9),
                3,
            ),
        }

    tau1_spread = spread([r["one_mode"]["tau_s"] for r in rows])
    fast_spread = spread([r["two_mode"]["tau_fast_s"] for r in separated])
    slow_spread = spread([r["two_mode"]["tau_slow_s"] for r in separated])

    # Reproducibility: a mode whose time constant scatters as widely as its own
    # median is not one physical process, it is a free parameter.
    reproducible = (
        bool(separated)
        and fast_spread.get("relative_iqr", 9.9) <= 0.5
        and slow_spread.get("relative_iqr", 9.9) <= 0.5
    )

    record = {
        "schema": RELAXATION_SCHEMA,
        "what_this_is": (
            "a model-free reading of the rest relaxation in calibration "
            "trajectories: one exponential against two, on the measurement "
            "itself. No cell model, no fitted parameter set and no validation "
            "or holdout trajectory takes part"
        ),
        "screens": {
            "rest_band_a": REST_BAND_A,
            "min_rest_samples": MIN_REST_SAMPLES,
            "min_rest_seconds": MIN_REST_SECONDS,
            "separation_ratio": SEPARATION_RATIO,
        },
        "segments": len(rows),
        "cells": sorted({r["cell"] for r in rows}),
        "one_mode_tau_spread_s": tau1_spread,
        "two_mode_fast_tau_spread_s": fast_spread,
        "two_mode_slow_tau_spread_s": slow_spread,
        "segments_with_separated_modes": len(separated),
        "segments_where_aic_prefers_two": len(aic_two),
        "median_rmse_improvement_v": round(
            statistics.median(r["rmse_improvement_v"] for r in rows), 6
        ),
        "second_mode_reproducible": reproducible,
        "reading": (
            "a second mode is admissible only if it is separated from the first "
            "and its time constant is reproducible across trajectories. A "
            "better fit on its own is not evidence of a second process: two "
            "exponentials will always fit a relaxation at least as well as one"
        ),
        "verdict": (
            "a second reproducible relaxation timescale is present"
            if reproducible
            else "no second reproducible relaxation timescale is established"
        ),
        "rows": rows,
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    out = os.path.join(EVIDENCE, "RELAXATION.json")
    with open(out, "wb") as handle:
        handle.write(payload)
    print(f"wrote {out}")
    print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    print(f"  segments                     : {len(rows)} over {record['cells']}")
    print(f"  one-mode tau                 : {tau1_spread}")
    print(f"  separated two-mode segments  : {len(separated)} / {len(rows)}")
    print(f"  AIC prefers two modes        : {len(aic_two)} / {len(rows)}")
    print(f"  fast tau spread              : {fast_spread}")
    print(f"  slow tau spread              : {slow_spread}")
    print(f"  median RMSE improvement      : {record['median_rmse_improvement_v']*1000:.3f} mV")
    print(f"  VERDICT                      : {record['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
