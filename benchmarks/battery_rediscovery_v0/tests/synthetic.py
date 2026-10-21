"""Synthetic problems in the pack schema, with known 1RC parameters (development and tests only; never the real pack)."""

from __future__ import annotations

import copy
import math

import numpy as np

from benchmarks.battery_rediscovery_v0.candidate.common import PROBLEM_SCHEMA, Problem

TRUE = {"R0": 0.05, "R1": 0.03, "C1": 1000.0}


def ocv_curve(z):
    z = np.asarray(z, float)
    return 3.0 + 1.2 * z - 0.25 * np.exp(-12 * z) + 0.05 * np.sin(3 * z)


def simulate(t, current, z0, cap_Ah, R0, R1, C1, ocv=ocv_curve):
    """Exact piecewise-constant update with the backward hold (independent of the candidate implementation)."""
    v1, z = 0.0, z0
    out = [float(ocv(z0)) - current[0] * R0]
    for k in range(1, len(t)):
        dt = t[k] - t[k - 1]
        i = current[k]
        z -= i * dt / (3600 * cap_Ah)
        a = math.exp(-dt / (R1 * C1))
        v1 = a * v1 + R1 * (1 - a) * i
        out.append(float(ocv(z)) - i * R0 - v1)
    return np.array(out)


def traj(tid, cell, kind, t, current, z0, cap, noise, rng, params=TRUE, temp=25.0):
    v = simulate(t, current, z0, cap, params["R0"], params["R1"], params["C1"])
    v = v + rng.normal(0, noise, len(v))
    temps = temp + 0.1 * rng.standard_normal(len(t))
    return {"id": tid, "cell": cell, "kind": kind, "t_s": [float(x) for x in t], "current_A": [float(x) for x in current],
            "voltage_V": [float(x) for x in v], "temperature_C": [float(x) for x in temps], "z0": z0, "capacity_Ah": cap}


def pulse_problem(noise=0.0015, seed=0, levels=(3.0, 18.0), heldout_levels=(6.0, 12.0)) -> Problem:
    """P2-like: 0.1 s sampling, 10 s rest, 10 s pulse, 40 s rest; measured OCV fixed."""
    rng = np.random.RandomState(seed)
    t = np.round(np.arange(0, 60.0, 0.1), 6)
    cap = 3.0

    def windows(lv, tag, n_soc=6):
        out, k = [], 0
        for zs in np.linspace(0.9, 0.2, n_soc):
            for lev in lv:
                cur = np.where((t > 10.0) & (t <= 20.0), lev, 0.0)
                k += 1
                out.append(traj(f"S-{tag}{k:02d}", "A", "rest_pulse_rest", t, cur, float(zs), cap, noise, rng))
        return out

    knots = [[float(z), float(ocv_curve(z))] for z in np.linspace(0.02, 1.0, 50)]
    raw = {"schema": PROBLEM_SCHEMA, "problem_id": "S2", "description": "synthetic pulses",
           "declared_model": {"family": "thevenin_1rc", "equations": "", "requested_parameters": ["R0", "R1", "C1"],
                              "bounds": {"R0_ohm": [0.001, 0.2], "R1_ohm": [0.0001, 0.2], "C1_F": [1.0, 1e6]},
                              "ocv": {"status": "MEASURED_FIXED", "knots_z_V": knots}},
           "conventions": {"rest_band_A": 0.075},
           "measurement_uncertainty": {"voltage_V": {"status": "DECLARED_TYPE_B", "standard_uncertainty": noise}},
           "acceptance": {"within_cell_heldout/pulses": {"rmse_mV_max": 15.0, "p95_abs_mV_max": 30.0}},
           "applicability": {"temperature_C": {"widen_by": 1.0}, "current_A": {"widen_by": 0.075},
                             "soc": {"min": 0.02, "max": 1.0}},
           "sets": {"calibration": {"trajectories": windows(levels, "c")},
                    "within_cell_heldout": {"subsets": {"pulses": windows(heldout_levels, "h", 4)}}}}
    return Problem(raw)


def cc_problem(noise=0.002, seed=0, dt=18.7, current=2.0) -> Problem:
    """P1-like: one current level, full discharge then rest, about 19 s sampling; OCV fitted as a table."""
    rng = np.random.RandomState(seed)
    cap = 1.9

    def cycles(n, tag, cell, temp=24.0):
        out = []
        for k in range(n):
            t_load = 3600 * cap * 0.97 / current
            t = np.concatenate([[0.0, dt], np.arange(2 * dt, 2 * dt + t_load, dt)])
            t = np.concatenate([t, t[-1] + dt * np.arange(1, 13)])
            cur = np.zeros(len(t))
            cur[2:len(t) - 12] = current + 0.005 * rng.standard_normal(len(t) - 14)
            out.append(traj(f"S-{tag}{k + 1:02d}", cell, "cc_discharge_then_rest", t, cur, 1.0, cap, noise, rng, temp=temp))
        return out

    raw = {"schema": PROBLEM_SCHEMA, "problem_id": "S1", "description": "synthetic CC",
           "declared_model": {"family": "thevenin_1rc", "equations": "", "requested_parameters": ["R0", "R1", "C1"],
                              "bounds": {"R0_ohm": [1e-4, 1.0], "R1_ohm": [1e-5, 1.0], "C1_F": [1.0, 1e6]},
                              "ocv": {"status": "UNKNOWN_FITTED_TABLE", "knots_soc": [0.0, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4,
                                      0.5, 0.6, 0.7, 0.8, 0.9, 1.0], "bounds_V": [2.0, 4.5]}},
           "conventions": {"rest_band_A": 0.01},
           "measurement_uncertainty": {"voltage_V": {"status": "UNKNOWN"}},
           "acceptance": {"within_cell_heldout/later_cycles": {"rmse_mV_max": 50.0, "p95_abs_mV_max": 90.0},
                          "cross_cell_heldout/other_cell": {"rmse_mV_max": 50.0, "p95_abs_mV_max": 90.0}},
           "applicability": {"temperature_C": {"widen_by": 0.0}, "current_A": {"widen_by": 0.0}, "soc": {"min": 0.0, "max": 1.0}},
           "sets": {"calibration": {"trajectories": cycles(6, "c", "A")},
                    "within_cell_heldout": {"subsets": {"later_cycles": cycles(3, "w", "A")}},
                    "cross_cell_heldout": {"subsets": {"other_cell": cycles(3, "x", "C", temp=26.0)}}}}
    return Problem(raw)


def with_set(problem: Problem, **changes) -> Problem:
    raw = copy.deepcopy(problem.raw)
    raw.update(changes)
    return Problem(raw)
