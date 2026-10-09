"""Reference proposers for Blindfold.  They are BASELINES, not the discovery engine.

* :func:`always_refuse` -- never proposes a law (scores 0 on discoverable worlds, earns refusal credit by luck).
* :func:`always_law` -- fits a log-linear power law to every observed variable, covariates included, and always
  proposes it.  Must perform badly on the control universes: that is what the controls are for.
* :func:`always_insufficient` -- a blanket refusal; the report's credit over the best constant answer exposes it.
* :func:`careful` -- fits settable inputs only (interventions, not passive covariates), estimates its own noise from
  replicate queries, checks its fit on its OWN held-out queries, and refuses when the evidence does not support a law.

They only ever see the public card and an observe client.
"""

from __future__ import annotations

import math
import random
from typing import Any, Mapping

import numpy as np

from .escrow import EscrowRefused, ObserveClient
from .expression import c, mul, pw, v


LACK_OF_FIT_RATIO = 3.5


def always_refuse(card: Mapping[str, Any], client: ObserveClient) -> dict[str, Any]:
    return {"universe_id": card["universe_id"], "answer": "no_law", "rationale": "baseline: never proposes"}


def _collect(card: Mapping[str, Any], client: ObserveClient, n: int, rng: random.Random, replicate: int = 0) -> list[dict[str, float]]:
    settable = [x for x in card["inputs"] if x["settable"]]
    rows = []
    points = []
    for _ in range(max(0, n - replicate)):
        points.append({x["name"]: math.exp(rng.uniform(math.log(x["range"][0]), math.log(x["range"][1]))) for x in settable})
    points += points[:replicate]                                    # replicates: same settings again (noise estimate)
    for i, pt in enumerate(points):
        try:
            rows.append(client.observe(card["universe_id"], pt, query_id=f"q{i}")["observation"])
        except EscrowRefused:
            break
    return rows


def _fit(rows: list[dict[str, float]], names: list[str], output: str) -> tuple[np.ndarray, float] | None:
    ok = [r for r in rows if r[output] > 0 and all(r[n] > 0 for n in names)]
    if len(ok) < len(names) + 2:
        return None
    X = np.column_stack([np.ones(len(ok))] + [np.log([r[n] for r in ok]) for n in names])
    y = np.log([r[output] for r in ok])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    return coef, float(np.std(resid))


def _law(coef: np.ndarray, names: list[str]) -> dict:
    return mul(c(math.exp(coef[0])), *[pw(v(n), round(float(a), 6)) for n, a in zip(names, coef[1:])])


def always_law(card: Mapping[str, Any], client: ObserveClient) -> dict[str, Any]:
    rng = random.Random(card["universe_id"])
    rows = _collect(card, client, int(card["query_budget"]), rng)
    names = [x["name"] for x in card["inputs"]] + list(card.get("observed_covariates", ()))
    fit = _fit(rows, names, card["output"]["name"])
    if fit is None:
        fit = (np.array([0.0] + [0.0] * len(names)), 0.0)
    return {"universe_id": card["universe_id"], "answer": "law", "law": _law(fit[0], names), "rationale": "baseline: always fits"}


def always_insufficient(card: Mapping[str, Any], client: ObserveClient) -> dict[str, Any]:
    return {"universe_id": card["universe_id"], "answer": "insufficient_evidence", "rationale": "baseline: blanket refusal"}


def single_setting(card: Mapping[str, Any], client: ObserveClient) -> dict[str, Any]:
    """A NON-DISCOVERER: spends the budget at one fixed setting and never varies an input, then classifies the universe
    from nuisance statistics (noise level, covariate-output association).  It can earn control credit; it can never earn
    discovery credit.  It is in the comparator set so that control credit is never mistaken for discovery."""
    uid, out = card["universe_id"], card["output"]["name"]
    pt = {x["name"]: math.sqrt(x["range"][0] * x["range"][1]) for x in card["inputs"]}
    rows = []
    for i in range(int(card["query_budget"])):
        try:
            rows.append(client.observe(uid, pt, query_id=f"s{i}")["observation"])
        except EscrowRefused:
            break
    ys = [math.log(r[out]) for r in rows if r[out] > 0]
    if len(ys) < 3:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "too few observations"}
    covs = list(card.get("observed_covariates", ()))
    if covs:
        us = [math.log(r[covs[0]]) for r in rows if r[out] > 0]
        if float(np.std(us)) > 0 and abs(float(np.corrcoef(ys, us)[0, 1])) > 0.5:
            return {"universe_id": uid, "answer": "confounded", "rationale": "the output co-varies with a passive covariate at fixed inputs"}
    return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "one setting cannot identify a law"}


def _extrapolates(card: Mapping[str, Any]) -> bool:
    """True when the public assessment region leaves the query box (predictions will be judged where no query went)."""
    box = {x["name"]: x["range"] for x in card["inputs"]}
    return any(lo < box[n][0] or hi > box[n][1] for n, (lo, hi) in card.get("assessment_region", {}).items())


def careful(card: Mapping[str, Any], client: ObserveClient, *, precision: float = 0.02) -> dict[str, Any]:
    """Refuses unless the evidence pins the law down: the fit must beat a constant on held-out queries, the predicted mean
    must be known to ``precision`` (relative), and its held-out errors must be consistent with the noise it measured
    from replicate queries.  Only intervened (settable) inputs enter the law; a passively observed covariate never does.
    When the assessment region leaves the query box it does not extrapolate a law it could only check inside the box."""
    rng = random.Random(card["universe_id"] + "careful")
    budget = int(card["query_budget"])
    replicate = min(4, budget // 4)
    rows = _collect(card, client, budget, rng, replicate=replicate)
    out = card["output"]["name"]
    settable = [x["name"] for x in card["inputs"] if x["settable"]]
    uid = card["universe_id"]
    if len(rows) < len(settable) + 6 + replicate:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "too few observations for the input count"}
    # replicates repeat the FIRST `replicate` settings; they stay out of the hold-out set
    reps, base = rows[len(rows) - replicate:], rows[:replicate]
    diffs = [math.log(r[out]) - math.log(b[out]) for r, b in zip(reps, base) if r[out] > 0 and b[out] > 0]
    noise = float(np.std(diffs) / math.sqrt(2)) if len(diffs) >= 2 else None
    fresh = rows[: len(rows) - replicate]
    train, hold = fresh[: int(0.75 * len(fresh))], fresh[int(0.75 * len(fresh)):]
    fit = _fit(train, settable, out)
    if fit is None or len(hold) < 3:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "cannot fit and hold out"}
    coef, resid = fit

    def predict(r: Mapping[str, float]) -> float:
        return float(coef[0] + sum(a * math.log(r[n]) for n, a in zip(settable, coef[1:])))

    hold_log = [math.log(r[out]) for r in hold if r[out] > 0]
    err_fit = [abs(math.log(r[out]) - predict(r)) for r in hold if r[out] > 0]
    mean_train = float(np.mean([math.log(r[out]) for r in train if r[out] > 0]))
    err_const = [abs(y - mean_train) for y in hold_log]
    if float(np.mean(np.square(err_fit))) > 0.8 * float(np.mean(np.square(err_const))):
        return {"universe_id": uid, "answer": "no_law", "rationale": "on held-out queries the inputs do not beat a constant"}
    se = resid * math.sqrt((len(settable) + 1) / len(train))          # standard error of a predicted (log) mean
    scale = noise if noise is not None and noise > 0 else resid
    rms_hold = float(np.sqrt(np.mean(np.square(err_fit))))
    # lack of fit: training and held-out scatter against pure (replicate) error; with 2-4 replicate pairs the 99%
    # F quantile allows a ratio of about 3.5 before the form is called wrong
    consistent = rms_hold <= LACK_OF_FIT_RATIO * scale and resid <= LACK_OF_FIT_RATIO * scale
    if se > precision or not consistent:
        covs = list(card.get("observed_covariates", ()))
        if covs:
            res = [math.log(r[out]) - predict(r) for r in rows if r[out] > 0]
            cv = [math.log(r[covs[0]]) for r in rows if r[out] > 0]
            if len(res) > 3 and abs(float(np.corrcoef(res, cv)[0, 1])) > 0.5:
                return {"universe_id": uid, "answer": "confounded",
                        "rationale": "residuals track a passively observed covariate that cannot be set: its effect is not identifiable"}
        why = (f"the predicted mean is known only to {se:.3g} (needs {precision})" if se > precision
               else f"scatter (held-out rms {rms_hold:.3g}, fit {resid:.3g}) exceeds {LACK_OF_FIT_RATIO}x the replicate noise ({scale:.3g}): wrong form")
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": why}
    if _extrapolates(card):
        return {"universe_id": uid, "answer": "insufficient_evidence",
                "rationale": "the law is checked only inside the box; the assessment region lies outside it"}
    return {"universe_id": uid, "answer": "law", "law": _law(coef, settable),
            "rationale": "log-linear fit on intervened inputs, checked on own held-out queries"}


__all__ = ["always_insufficient", "always_law", "always_refuse", "careful", "single_setting"]
