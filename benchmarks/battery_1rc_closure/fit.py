"""Calibration and identifiability on the calibration role only (preregistration v2).

``python -m benchmarks.battery_1rc_closure.fit`` writes ``results/CALIBRATION.json``. It never reads a held-out role.
The forward model here is a vectorized transcription of the same equations as
``engcore.domains.battery.thevenin_route`` (end-of-interval OCV, exact RC update, backward hold); a test pins the two
to agree on real calibration cycles.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import time
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from .data import load, prereg_sha256
from .prereg import PREREG

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
M = PREREG["models"]
KNOTS = np.array(M["ocv_knots_soc"], dtype=float)
NK = len(KNOTS)
OCV_LO, OCV_HI = M["ocv_bounds_V"]
B = M["bounds"]
LOG_BOUNDS = {"R0": tuple(map(math.log, B["R0_ohm"])), "R1": tuple(map(math.log, B["R1_ohm"])),
              "C1": tuple(map(math.log, B["C1_F"]))}
OCV_START = 3.3 + 0.9 * KNOTS


class Cycle:
    __slots__ = ("cell", "ordinal", "t", "i", "v", "temp", "q_as")

    def __init__(self, doc: dict[str, Any]) -> None:
        self.cell, self.ordinal = doc["cell"], doc["ordinal"]
        self.t = np.asarray(doc["time_s"], float)
        self.i = np.asarray(doc["current_A"], float)
        self.v = np.asarray(doc["voltage_V"], float)
        self.temp = np.asarray(doc["temperature_C"], float)
        self.q_as = float(doc["capacity_basis_Ah"]) * 3600.0


def predict(c: Cycle, ocv: np.ndarray, r0: float, r1: float | None = None, c1: float | None = None, *,
            hold: str = "backward", vp0: float = 0.0) -> np.ndarray:
    """Predicted terminal voltage at samples 1..n (sample 0 is the declared initial rest state)."""
    dt = np.diff(c.t)
    current = c.i[1:] if hold == "backward" else c.i[:-1]
    z = 1.0 - np.cumsum(current * dt) / c.q_as
    vp = np.zeros_like(dt)
    if r1 is not None:
        alpha = np.exp(-dt / (r1 * c1))
        prev = vp0
        for k in range(len(dt)):
            prev = prev * alpha[k] + current[k] * r1 * (1.0 - alpha[k])
            vp[k] = prev
    return np.interp(z, KNOTS, ocv) - current * r0 - vp


def unpack(theta: np.ndarray, model: str) -> dict[str, Any]:
    out = {"ocv": theta[:NK], "R0": math.exp(theta[NK])}
    if model == "1rc":
        out["R1"], out["C1"] = math.exp(theta[NK + 1]), math.exp(theta[NK + 2])
    return out


def residuals(theta: np.ndarray, cycles: list[Cycle], model: str, *, hold: str = "backward",
              vp0_per_r1: float = 0.0, fixed: dict[int, float] | None = None) -> np.ndarray:
    if fixed:
        theta = theta.copy()
        for k, val in fixed.items():
            theta[k] = val
    p = unpack(theta, model)
    out = []
    for c in cycles:
        vp0 = vp0_per_r1 * p.get("R1", 0.0)
        pred = predict(c, p["ocv"], p["R0"], p.get("R1"), p.get("C1"), hold=hold, vp0=vp0)
        out.append(c.v[1:] - pred)
    return np.concatenate(out)


def bounds(model: str):
    lo = [OCV_LO] * NK + [LOG_BOUNDS["R0"][0]]
    hi = [OCV_HI] * NK + [LOG_BOUNDS["R0"][1]]
    if model == "1rc":
        lo += [LOG_BOUNDS["R1"][0], LOG_BOUNDS["C1"][0]]
        hi += [LOG_BOUNDS["R1"][1], LOG_BOUNDS["C1"][1]]
    return np.array(lo), np.array(hi)


def starts(model: str) -> list[np.ndarray]:
    if model == "rint":
        return [np.r_[OCV_START + dv, math.log(r0)] for r0 in (0.02, 0.05, 0.1, 0.2) for dv in (0.0, 0.1)]
    return [np.r_[OCV_START, math.log(0.05), math.log(r1), math.log(tau / r1)]
            for r1 in (0.02, 0.08) for tau in (20.0, 100.0, 500.0, 2000.0)]


def solve(cycles, model, x0, *, free_mask=None, fixed=None, **kw):
    lo, hi = bounds(model)
    if free_mask is None:
        free_mask = np.ones(len(x0), bool)
    idx = np.where(free_mask)[0]

    def f(x):
        theta = x0.copy()
        theta[idx] = x
        return residuals(theta, cycles, model, fixed=fixed, **kw)
    r = least_squares(f, np.clip(x0[idx], lo[idx] + 1e-12, hi[idx] - 1e-12), bounds=(lo[idx], hi[idx]),
                      method="trf", x_scale="jac", max_nfev=4000)
    theta = x0.copy()
    theta[idx] = r.x
    return theta, float(np.sum(r.fun ** 2)), r


def fit(cycles, model, **kw):
    best = None
    runs = []
    for x0 in starts(model):
        theta, sse, r = solve(cycles, model, x0, **kw)
        runs.append({"start": unpack(x0, model) | {"ocv": None}, "sse": sse, "status": int(r.status)})
        if best is None or sse < best[1]:
            best = (theta, sse, r)
    return best, runs


def jsonable(p: dict[str, Any]) -> dict[str, Any]:
    return {k: (list(map(float, v)) if isinstance(v, np.ndarray) else float(v)) for k, v in p.items()}


def summarize(theta, sse, cycles, model) -> dict[str, Any]:
    n = sum(len(c.t) - 1 for c in cycles)
    p = unpack(theta, model)
    out = {"parameters": jsonable(p), "sse_V2": sse, "samples": n, "rmse_mV": 1000 * math.sqrt(sse / n)}
    if model == "1rc":
        out["tau_s"] = p["R1"] * p["C1"]
    return out


def identifiability(cycles, theta, sse, r) -> dict[str, Any]:
    model = "1rc"
    lo, hi = bounds(model)
    J = r.jac
    s = np.linalg.svd(J, compute_uv=False)
    jtj = J.T @ J
    cov = np.linalg.pinv(jtj) * sse / max(1, J.shape[0] - J.shape[1])
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    corr = cov / np.outer(sd, sd)
    names = [f"ocv_{k}" for k in range(NK)] + ["logR0", "logR1", "logC1"]
    rblock = [NK, NK + 1, NK + 2]
    # R-parameter identifiability with the OCV knots profiled out (Schur complement of J^T J)
    o = list(range(NK))
    schur = jtj[np.ix_(rblock, rblock)] - jtj[np.ix_(rblock, o)] @ np.linalg.pinv(jtj[np.ix_(o, o)]) @ jtj[np.ix_(o, rblock)]
    sev = np.linalg.eigvalsh(schur)
    diag = {"jacobian_singular_values": s.tolist(), "jacobian_condition": float(s[0] / s[-1]),
            "r_block_schur_eigenvalues": sev.tolist(),
            "r_block_schur_condition": float(sev[-1] / max(sev[0], 1e-300)),
            "correlations": {f"{names[a]}~{names[b]}": float(corr[a, b]) for a in rblock for b in rblock if a < b},
            "max_abs_correlation_ocv_vs_logR0": float(np.max(np.abs(corr[NK, :NK])))}
    # profiles
    factors = [1 / 3, 1 / 2, 1 / 1.5, 1.5, 2.0, 3.0]
    profiles = {}
    for name, k in (("R0", NK), ("R1", NK + 1), ("C1", NK + 2)):
        rows = []
        for f in factors:
            val = theta[k] + math.log(f)
            if not lo[k] <= val <= hi[k]:
                rows.append({"factor": f, "sse_ratio": None, "note": "outside bounds"})
                continue
            x0 = theta.copy()
            x0[k] = val
            mask = np.ones(len(theta), bool)
            mask[k] = False
            _, s2, _ = solve(cycles, model, x0, free_mask=mask)
            rows.append({"factor": f, "sse_ratio": s2 / sse})
        profiles[name] = rows
    # tau profile: C1 follows R1 so that R1*C1 = f*tau; R1 and everything else free
    rows = []
    tau = math.exp(theta[NK + 1] + theta[NK + 2])
    for f in factors:
        target = math.log(f * tau)

        def ftau(x, target=target):
            th = np.r_[x[:NK + 2], target - x[NK + 1]]
            return residuals(th, cycles, model)
        lo2, hi2 = lo[:NK + 2], hi[:NK + 2]
        rr = least_squares(ftau, np.clip(theta[:NK + 2], lo2 + 1e-12, hi2 - 1e-12), bounds=(lo2, hi2), method="trf",
                           x_scale="jac", max_nfev=4000)
        rows.append({"factor": f, "sse_ratio": float(np.sum(rr.fun ** 2)) / sse})
    profiles["tau"] = rows
    diag["profiles"] = profiles
    return diag


def profile_identified(rows) -> bool:
    low = [r["sse_ratio"] for r in rows if r["factor"] < 1 and r["sse_ratio"] is not None]
    high = [r["sse_ratio"] for r in rows if r["factor"] > 1 and r["sse_ratio"] is not None]
    return bool(low) and bool(high) and max(low) >= 1.10 and max(high) >= 1.10


def bootstrap(cycles, theta, model, b=40, seed=0):
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(b):
        sample = [cycles[j] for j in rng.integers(0, len(cycles), len(cycles))]
        th, _, _ = solve(sample, model, theta)
        draws.append(th)
    return np.array(draws)


def main() -> int:
    started = time.perf_counter()
    doc = load("calibration")
    cycles = [Cycle(c) for c in doc["cycles"]]
    out: dict[str, Any] = {"schema": "forge.battery_1rc_closure.calibration/1",
                           "preregistration_sha256": prereg_sha256(),
                           "calibration_data_sha256": hashlib.sha256(
                               (HERE / "data" / "calibration.json").read_bytes()).hexdigest(),
                           "cycles": len(cycles), "models": {}}
    fits = {}
    for model in ("rint", "1rc"):
        (theta, sse, r), runs = fit(cycles, model)
        fits[model] = (theta, sse, r)
        out["models"][model] = {**summarize(theta, sse, cycles, model), "starts": runs,
                                "spread_of_start_sse": [min(x["sse"] for x in runs), max(x["sse"] for x in runs)]}
    theta, sse, r = fits["1rc"]
    lo, hi = bounds("1rc")
    on_bound = {n: bool(min(theta[k] - lo[k], hi[k] - theta[k]) < 0.01)
                for n, k in (("R0", NK), ("R1", NK + 1), ("C1", NK + 2))}
    diag = identifiability(cycles, theta, sse, r)
    draws = bootstrap(cycles, theta, "1rc")
    params = {"R0": np.exp(draws[:, NK]), "R1": np.exp(draws[:, NK + 1]), "C1": np.exp(draws[:, NK + 2])}
    params["tau"] = params["R1"] * params["C1"]
    boot = {n: {"mean": float(v.mean()), "sd": float(v.std(ddof=1)), "cv": float(v.std(ddof=1) / v.mean()),
                "p2_5": float(np.percentile(v, 2.5)), "p97_5": float(np.percentile(v, 97.5))}
            for n, v in params.items()}
    rint_boot = np.exp(bootstrap(cycles, fits["rint"][0], "rint")[:, NK])
    # dependence on initial-condition assumptions
    fwd_theta, fwd_sse, _ = solve(cycles, "1rc", theta, hold="forward")
    vp_theta, vp_sse, _ = solve(cycles, "1rc", theta, vp0_per_r1=0.020)
    sens = {"forward_hold": jsonable({k: v for k, v in unpack(fwd_theta, "1rc").items() if k != "ocv"})
            | {"sse_ratio": fwd_sse / sse},
            "vp0_20mA_x_R1": jsonable({k: v for k, v in unpack(vp_theta, "1rc").items() if k != "ocv"})
            | {"sse_ratio": vp_sse / sse}}
    decided = {}
    for name in ("R0", "R1", "C1", "tau"):
        prof_ok = profile_identified(diag["profiles"][name])
        cv_ok = boot[name]["cv"] <= 0.25
        bound_ok = not on_bound.get(name, False) if name != "tau" else not (on_bound["R1"] or on_bound["C1"])
        decided[name] = {"profile": prof_ok, "bootstrap_cv": boot[name]["cv"], "cv_ok": cv_ok, "not_on_bound": bound_ok,
                         "identified": prof_ok and cv_ok and bound_ok}
    if all(decided[n]["identified"] for n in ("R0", "R1", "C1")):
        decision = "IDENTIFIABLE"
    elif decided["tau"]["identified"] or decided["R0"]["identified"]:
        decision = "WEAKLY_IDENTIFIABLE"
    else:
        decision = "NOT_IDENTIFIABLE"
    out["identifiability"] = {"diagnostics": diag, "bootstrap": boot,
                              "rint_R0_bootstrap": {"mean": float(rint_boot.mean()),
                                                    "cv": float(rint_boot.std(ddof=1) / rint_boot.mean())},
                              "bootstrap_draws_1rc": draws.tolist(), "on_bound": on_bound, "sensitivity": sens,
                              "per_parameter": decided, "decision": decision,
                              "calibration_gate": "PASS" if decision == "IDENTIFIABLE" else "NOT_PASSED"}
    temps = np.concatenate([c.temp for c in cycles])
    out["parameter_set"] = {"temperature_range_C": [float(temps.min()), float(temps.max())],
                            "max_current_A": float(max(c.i.max() for c in cycles))}
    out["elapsed_seconds"] = round(time.perf_counter() - started, 1)
    RESULTS.mkdir(exist_ok=True)
    data = json.dumps(out, sort_keys=True, indent=1).encode() + b"\n"
    (RESULTS / "CALIBRATION.json").write_bytes(data)
    (RESULTS / "CALIBRATION.sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    print(json.dumps({"rint": {k: out["models"]["rint"][k] for k in ("rmse_mV",)},
                      "1rc": {k: out["models"]["1rc"][k] for k in ("rmse_mV", "tau_s")},
                      "R": {k: v for k, v in out["models"]["1rc"]["parameters"].items() if k != "ocv"},
                      "decision": decision, "per_parameter": decided, "elapsed": out["elapsed_seconds"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
