"""Reference proposers for Blindfold.  They are BASELINES, not the discovery engine.

* :func:`always_refuse` -- never proposes a law (scores 0 on discoverable worlds, earns refusal credit by luck).
* :func:`always_law` -- fits a log-linear power law to every observed variable, covariates included, and always
  proposes it.  Must perform badly on the control universes: that is what the controls are for.
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


def careful(card: Mapping[str, Any], client: ObserveClient, *, precision: float = 0.02) -> dict[str, Any]:
    """Refuses unless the evidence pins the law down: the fit must beat a constant on held-out queries, the predicted mean
    must be known to ``precision`` (relative), and 90% of its own held-out queries must sit within what replicate noise
    allows.  Only intervened (settable) inputs enter the law; a passively observed covariate never does."""
    rng = random.Random(card["universe_id"] + "careful")
    budget = int(card["query_budget"])
    replicate = min(4, budget // 4)
    rows = _collect(card, client, budget, rng, replicate=replicate)
    out = card["output"]["name"]
    settable = [x["name"] for x in card["inputs"] if x["settable"]]
    uid = card["universe_id"]
    if len(rows) < len(settable) + 6:
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": "too few observations for the input count"}
    reps, base = rows[-replicate:], rows[-2 * replicate:-replicate]
    diffs = [math.log(r[out]) - math.log(b[out]) for r, b in zip(reps, base) if r[out] > 0 and b[out] > 0]
    noise = float(np.std(diffs) / math.sqrt(2)) if len(diffs) >= 2 else None
    train, hold = rows[: int(0.75 * len(rows))], rows[int(0.75 * len(rows)):]
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
    p90 = float(np.quantile(err_fit, 0.9))
    allowed = max(0.03, 3.0 * (noise if noise is not None else resid))
    if se > precision or p90 > allowed:
        covs = list(card.get("observed_covariates", ()))
        if covs:
            res = [math.log(r[out]) - predict(r) for r in rows if r[out] > 0]
            cv = [math.log(r[covs[0]]) for r in rows if r[out] > 0]
            if len(res) > 3 and abs(float(np.corrcoef(res, cv)[0, 1])) > 0.5:
                return {"universe_id": uid, "answer": "confounded",
                        "rationale": "residuals track a passively observed covariate: a hidden common cause"}
        why = (f"the predicted mean is known only to {se:.3g} (needs {precision})" if se > precision
               else f"90% held-out error {p90:.3g} exceeds what replicate noise allows ({allowed:.3g}): wrong form")
        return {"universe_id": uid, "answer": "insufficient_evidence", "rationale": why}
    return {"universe_id": uid, "answer": "law", "law": _law(coef, settable),
            "rationale": "log-linear fit on intervened inputs, checked on own held-out queries"}


__all__ = ["always_law", "always_refuse", "careful"]
