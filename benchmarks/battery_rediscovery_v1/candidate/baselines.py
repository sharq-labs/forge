"""Baseline arms: FIXED_FIT, CAREFUL_BASELINE, ALWAYS_FIT and ALWAYS_REFUSE.

All fitting arms share one deterministic calibration of the declared 1RC model per problem (8 seeded starts, backward
hold).  They differ only in what they conclude from it:

* FIXED_FIT reports the fit and its held-out predictions against the declared acceptance bar.  It never checks
  applicability, identifiability or residual structure, and answers NOT_ASSESSABLE only where a set is absent.
* CAREFUL_BASELINE adds the declared applicability rule, basic identifiability checks (bound, inflated Gauss-Newton
  standard error, correlation, multistart agreement) and a residual-structure check.
* ALWAYS_FIT answers SUPPORTED to every question, absent sets included.
* ALWAYS_REFUSE answers REFUSED to every question.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from . import model as m
from .common import (
    AXES, NOT_ASSESSABLE, NOT_SUPPORTED, OUTPUT_SCHEMA, REFUSED, REVIEW, SUPPORTED, Problem, Trajectory, combine, digest,
)

HELDOUT_SETS = ("within_cell_heldout", "cross_cell_heldout")
AXIS_OF_SET = {"within_cell_heldout": "WITHIN_CELL_GENERALIZATION", "cross_cell_heldout": "CROSS_CELL_TRANSFER"}
REQUESTED = ("R0", "R1", "C1")
THETA_INDEX = {"R0": 0, "R1": 1, "C1": 2}

# CAREFUL_BASELINE's declared basic checks
MAX_SD_LN = 0.25
MAX_ABS_CORR = 0.99
BOUND_MARGIN_LN = 1e-3
MULTISTART_SPREAD_LN = math.log(1.10)
STRUCTURED_LAG1 = 0.5
COVERAGE_Z = 1.96


def _domain(problem: Problem, cal: list[Trajectory]) -> dict[str, Any]:
    app = problem.raw["applicability"]
    temps = np.concatenate([tr.temperature for tr in cal])
    cur = np.concatenate([tr.current for tr in cal])
    wt, wi = float(app["temperature_C"]["widen_by"]), float(app["current_A"]["widen_by"])
    return {"temperature_C": [float(temps.min()) - wt, float(temps.max()) + wt],
            "current_max_A": float(cur.max()) + wi, "soc": [float(app["soc"]["min"]), float(app["soc"]["max"])]}


def _in_domain(tr: Trajectory, batch_z: np.ndarray, dom: dict[str, Any]) -> list[str]:
    out = []
    lo, hi = dom["temperature_C"]
    if tr.temperature.min() < lo or tr.temperature.max() > hi:
        out.append(f"temperature [{tr.temperature.min():.3f}, {tr.temperature.max():.3f}] C outside [{lo:.3f}, {hi:.3f}]")
    if tr.current.max() > dom["current_max_A"]:
        out.append(f"current {tr.current.max():.4f} A above {dom['current_max_A']:.4f}")
    zlo, zhi = dom["soc"]
    if batch_z.min() < zlo or batch_z.max() > zhi:
        out.append(f"SOC [{batch_z.min():.4f}, {batch_z.max():.4f}] outside [{zlo}, {zhi}]")
    return out


_CALIBRATIONS: dict[str, dict[str, Any]] = {}


def calibrate(problem: Problem) -> dict[str, Any]:
    """The shared deterministic calibration (cached per problem content); everything an arm may conclude from."""
    key = digest(problem.raw)
    if key not in _CALIBRATIONS:
        _CALIBRATIONS[key] = _calibrate(problem)
    return _CALIBRATIONS[key]


def _calibrate(problem: Problem) -> dict[str, Any]:
    cal = problem.calibration()
    spec = m.ModelSpec.from_declared(problem.model, rc=True)
    batch = m.Batch.build(cal, "backward")
    f = m.fit(spec, batch)
    ev = m.Evaluator(spec, batch)
    vpred, Jfull = ev.predict(f.theta)
    stats = m.error_stats(batch, vpred)
    rho = min(max(stats["lag1"], 0.0), 0.99) if math.isfinite(stats["lag1"]) else 0.0
    cov = m.covariance(f, rho=rho)
    sd = np.sqrt(np.clip(np.diag(cov), 0, None))
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = cov / np.outer(sd, sd)
    # a parameter with no information (infinite variance) is uncorrelated by convention, never "identified" by it
    corr = np.where(np.isfinite(corr), corr, 0.0)
    lo, hi = spec.bounds_vectors()
    converged = [s for s in f.starts if s["sse"] <= m.CONVERGED_SSE_RATIO * f.sse]
    fwd_batch = m.Batch.build(cal, "forward")
    f_fwd = m.fit(spec, fwd_batch, x0=[f.theta])
    shift = {p: math.exp(f_fwd.theta[i] - f.theta[i]) - 1 for p, i in THETA_INDEX.items()}
    per = {}
    for p, i in THETA_INDEX.items():
        others = [abs(corr[i, j]) for j in range(len(f.theta)) if j != i]
        spread = max(s["theta"][i] for s in converged) - min(s["theta"][i] for s in converged)
        per[p] = {"estimate": math.exp(f.theta[i]), "sd_ln": float(sd[i]), "max_abs_corr": float(max(others)),
                  "on_bound": bool(f.theta[i] - lo[i] < BOUND_MARGIN_LN or hi[i] - f.theta[i] < BOUND_MARGIN_LN),
                  "multistart_spread_ln": float(spread), "forward_hold_shift": float(shift[p])}
    ocv_on_bound = 0
    if spec.knots_soc is not None:
        ocv = f.theta[3:]
        ocv_on_bound = int(np.sum((ocv - lo[3:] < 1e-6) | (hi[3:] - ocv < 1e-6)))
    # predictive variance on the calibration samples: an uninformed direction has no Jacobian projection there
    cov_finite = np.where(np.isfinite(cov), cov, 0.0)
    pred_var = np.einsum("ij,jk,ik->i", f.jac, cov_finite, f.jac)
    # the Rint reduction, reported as the rival structure
    rint = m.fit(m.ModelSpec.from_declared(problem.model, rc=False), batch)
    return {"spec": spec, "fit": f, "batch": batch, "stats": stats, "cov": cov_finite, "per": per, "converged_starts": len(converged),
            "ocv_on_bound": ocv_on_bound, "domain": _domain(problem, cal), "rint_sse": rint.sse,
            "rint_rmse_mV": math.sqrt(rint.sse / rint.n) * 1e3, "cal_pred_sd_V": float(np.sqrt(np.mean(pred_var))),
            "forward_hold_sse_ratio": f_fwd.sse / f.sse}


def heldout_eval(problem: Problem, cal: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """1RC predictions of every held-out subset from the frozen calibration (no refit)."""
    out: dict[str, dict[str, Any]] = {}
    spec, f, cov = cal["spec"], cal["fit"], cal["cov"]
    sigma_v = problem.voltage_sigma()
    for set_name in HELDOUT_SETS:
        sets = problem.heldout(set_name)
        if sets is None:
            continue
        for subset, trajs in sets.items():
            batch = m.Batch.build(trajs, "backward")
            vpred, J = m.Evaluator(spec, batch).predict(f.theta)
            stats = m.error_stats(batch, vpred)
            ood = {}
            for i, tr in enumerate(trajs):
                reasons = _in_domain(tr, batch.z[i, :batch.lengths[i]], cal["domain"])
                if reasons:
                    ood[tr.traj_id] = reasons
            bar = problem.acceptance(set_name, subset)
            meets = stats["rmse_mV"] <= bar["rmse_mV_max"] and stats["p95_abs_mV"] <= bar["p95_abs_mV_max"]
            coverage = None
            if sigma_v is not None:
                Js = J[batch.mask]
                var = np.einsum("ij,jk,ik->i", Js, cov, Js) + sigma_v ** 2
                r = (batch.voltage - vpred)[batch.mask]
                coverage = float(np.mean(np.abs(r) <= COVERAGE_Z * np.sqrt(var)))
            per_traj = {tr.traj_id: float(np.sqrt(np.mean(((batch.voltage - vpred)[i, 1:batch.lengths[i]]) ** 2)) * 1e3)
                        for i, tr in enumerate(trajs)}
            preds = {tr.traj_id: [round(float(x), 7) for x in vpred[i, :batch.lengths[i]]] for i, tr in enumerate(trajs)}
            out[f"{set_name}/{subset}"] = {"set": set_name, "subset": subset, "stats": stats, "bar": dict(bar),
                                           "meets_bar": bool(meets), "out_of_domain": ood, "coverage_95": coverage,
                                           "per_trajectory_rmse_mV": per_traj, "predicted_V": preds,
                                           "predicted_digest": digest(preds), "trajectories": len(trajs)}
    return out


def _strictest_bar(problem: Problem) -> dict[str, float]:
    bars = list(problem.raw["acceptance"].values())
    return {"rmse_mV_max": min(b["rmse_mV_max"] for b in bars), "p95_abs_mV_max": min(b["p95_abs_mV_max"] for b in bars)}


def _record(arm: str, problem: Problem, answers: dict[str, dict[str, Any]], **extra: Any) -> dict[str, Any]:
    assert set(answers) == set(AXES)
    rec = {"schema": OUTPUT_SCHEMA, "arm": arm, "problem_id": problem.problem_id, "answers": answers,
           "refusal_reasons": sorted({a["reason"] for a in answers.values()
                                      if a["disposition"] in (REFUSED, NOT_ASSESSABLE, REVIEW)})}
    rec.update(extra)
    return rec


def _fit_summary(cal: dict[str, Any]) -> dict[str, Any]:
    f = cal["fit"]
    return {"parameters": f.params, "calibration": cal["stats"], "starts": f.starts, "converged_starts": cal["converged_starts"],
            "per_parameter": cal["per"], "ocv_knots_on_bound": cal["ocv_on_bound"], "rint_rmse_mV": cal["rint_rmse_mV"],
            "forward_hold_sse_ratio": cal["forward_hold_sse_ratio"],
            "theta_digest": digest([round(float(x), 12) for x in f.theta])}


def fixed_fit(problem: Problem) -> dict[str, Any]:
    cal = calibrate(problem)
    ho = heldout_eval(problem, cal)
    bar = _strictest_bar(problem)
    st = cal["stats"]
    cal_ok = st["rmse_mV"] <= bar["rmse_mV_max"] and st["p95_abs_mV"] <= bar["p95_abs_mV_max"]
    answers = {"MODEL_ADEQUACY": {"disposition": SUPPORTED if cal_ok else NOT_SUPPORTED,
                                  "reason": "calibration fit against the strictest declared bar"},
               "IDENTIFIABILITY": {"disposition": SUPPORTED, "reason": "point estimates reported; not checked"},
               "MODEL_DISCREPANCY": {"disposition": SUPPORTED if cal_ok else NOT_SUPPORTED,
                                     "reason": "residuals taken as noise when the fit meets the bar; structure not checked"}}
    for set_name, axis in AXIS_OF_SET.items():
        subs = {k: v for k, v in ho.items() if v["set"] == set_name}
        if not subs:
            answers[axis] = {"disposition": NOT_ASSESSABLE, "reason": "no held-out set of this kind is supplied"}
            continue
        d = {k: SUPPORTED if v["meets_bar"] else NOT_SUPPORTED for k, v in subs.items()}
        answers[axis] = {"disposition": combine(list(d.values())), "reason": "held-out predictions against the declared bar",
                         "sub": d}
    return _record("FIXED_FIT", problem, answers, hypotheses=["thevenin_1rc"], eliminated=[], fit=_fit_summary(cal),
                   heldout=ho, applicability={"checked": False}, observations_used=int(cal["fit"].n))


def careful(problem: Problem) -> dict[str, Any]:
    cal = calibrate(problem)
    ho = heldout_eval(problem, cal)
    per = cal["per"]
    identified = {}
    for p in REQUESTED:
        q = per[p]
        why = []
        if q["on_bound"]:
            why.append("on a bound")
        if not q["sd_ln"] <= MAX_SD_LN:
            why.append(f"inflated GN sd(ln) {q['sd_ln']:.3f} > {MAX_SD_LN}")
        if not q["max_abs_corr"] < MAX_ABS_CORR:
            why.append(f"|correlation| {q['max_abs_corr']:.4f} >= {MAX_ABS_CORR}")
        if not q["multistart_spread_ln"] <= MULTISTART_SPREAD_LN:
            why.append(f"converged starts disagree by {q['multistart_spread_ln']:.3f} ln")
        identified[p] = {"identified": not why, "why_not": why}
    n_id = sum(v["identified"] for v in identified.values())
    ident = SUPPORTED if n_id == len(REQUESTED) else NOT_SUPPORTED if n_id == 0 else REVIEW
    if cal["ocv_on_bound"]:
        ocv_note = f"; {cal['ocv_on_bound']} fitted OCV knots sit on their bound (the OCV table absorbs other terms)"
    else:
        ocv_note = ""
    answers = {"IDENTIFIABILITY": {"disposition": ident, "reason": f"{n_id}/3 requested parameters pass the basic checks"
                                   + ocv_note, "sub": identified}}
    sub_disp: dict[str, dict[str, str]] = {}
    for set_name, axis in AXIS_OF_SET.items():
        subs = {k: v for k, v in ho.items() if v["set"] == set_name}
        if not subs:
            answers[axis] = {"disposition": NOT_ASSESSABLE, "reason": "no held-out set of this kind is supplied"}
            continue
        d = {}
        for k, v in subs.items():
            if not v["meets_bar"]:
                d[k] = NOT_SUPPORTED
            elif v["out_of_domain"]:
                d[k] = NOT_ASSESSABLE
            else:
                d[k] = SUPPORTED
        sub_disp[set_name] = d
        reason = "declared set rule: a failing set is NOT_SUPPORTED; a passing set holding an out-of-domain trajectory is " \
                 "NOT_ASSESSABLE"
        answers[axis] = {"disposition": combine(list(d.values())), "reason": reason, "sub": d,
                         "out_of_domain": {k: len(v["out_of_domain"]) for k, v in subs.items()}}
    st = cal["stats"]
    sigma_v = problem.voltage_sigma()
    if math.isfinite(st["lag1"]) and st["lag1"] > STRUCTURED_LAG1:
        disc = (NOT_SUPPORTED, f"calibration residual lag-1 autocorrelation {st['lag1']:.2f} > {STRUCTURED_LAG1}: structured")
    elif sigma_v is not None:
        bound = 2 * math.sqrt(sigma_v ** 2 + cal["cal_pred_sd_V"] ** 2) * 1e3
        disc = ((SUPPORTED if st["rmse_mV"] <= bound else NOT_SUPPORTED),
                f"calibration RMSE {st['rmse_mV']:.2f} mV against 2 x combined measurement+parameter sd {bound:.2f} mV")
    else:
        disc = (NOT_ASSESSABLE, "no residual structure detected and the measurement uncertainty is UNKNOWN")
    answers["MODEL_DISCREPANCY"] = {"disposition": disc[0], "reason": disc[1]}
    bar = _strictest_bar(problem)
    cal_ok = st["rmse_mV"] <= bar["rmse_mV_max"] and st["p95_abs_mV"] <= bar["p95_abs_mV_max"]
    flat = [d for v in sub_disp.values() for d in v.values()]
    if not cal_ok or NOT_SUPPORTED in flat:
        adeq = (NOT_SUPPORTED, "the calibration fit or an assessable held-out set fails the declared bar")
    elif flat and all(d == SUPPORTED for d in flat) and disc[0] == SUPPORTED:
        adeq = (SUPPORTED, "calibration and every held-out set meet the bar in domain, residuals unstructured")
    else:
        adeq = (REVIEW, "nothing fails, but support is incomplete (out-of-domain sets or structured/unknown residuals)")
    answers["MODEL_ADEQUACY"] = {"disposition": adeq[0], "reason": adeq[1]}
    return _record("CAREFUL_BASELINE", problem, answers, hypotheses=["thevenin_1rc", "rint"], eliminated=[],
                   fit=_fit_summary(cal), heldout=ho, applicability={"checked": True, "domain": cal["domain"]},
                   observations_used=int(cal["fit"].n))


def always_fit(problem: Problem) -> dict[str, Any]:
    cal = calibrate(problem)
    answers = {a: {"disposition": SUPPORTED, "reason": "never refuses"} for a in AXES}
    return _record("ALWAYS_FIT", problem, answers, hypotheses=["thevenin_1rc"], eliminated=[], fit=_fit_summary(cal),
                   applicability={"checked": False}, observations_used=int(cal["fit"].n))


def always_refuse(problem: Problem) -> dict[str, Any]:
    answers = {a: {"disposition": REFUSED, "reason": "refuses every scientific conclusion"} for a in AXES}
    return _record("ALWAYS_REFUSE", problem, answers, hypotheses=[], eliminated=[], applicability={"checked": False},
                   observations_used=0)


ARMS = {"FIXED_FIT": fixed_fit, "CAREFUL_BASELINE": careful, "ALWAYS_FIT": always_fit, "ALWAYS_REFUSE": always_refuse}

__all__ = ["ARMS", "always_fit", "always_refuse", "calibrate", "careful", "fixed_fit", "heldout_eval"]
