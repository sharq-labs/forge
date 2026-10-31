"""Scoring and selection of grammar structures (EXC-4, development).

**Score** (lower is better): ``RSS / sigma^2 + p ln n - 2 ln prior`` -- minus twice the ln-scale Gaussian
log-likelihood at the REPLICATE-NOISE estimate ``sigma`` (EXC-4 field 2; review M1), plus the BIC parameter penalty and
the declared prior.  ``sigma`` is the caller's replicate-noise estimate; a missing, zero or non-finite one refuses
(:class:`ScoreRefused`) -- it is never defaulted or profiled out.  The **declared prior** gives every shape present the
same mass and spreads it uniformly over that shape's structures, so a shape with many structures does not win by
numbers.  Known limitation (review L4): a regime threshold is counted as one parameter although it is chosen by an
exhaustive change-point search, so its effective degrees of freedom are higher; cross-validation only partly offsets it.

**Selection**: the :data:`TOP` best-scored structures go to K-fold cross-validation INSIDE the rows given (fold = row
index mod K, the baselines' rule); the smallest structure (fewest parameters, then nodes) whose CV mean squared error is
within :data:`OCCAM_SLACK` of the best is selected, then refitted on all the rows.  Nothing here sees held-out rows: the
caller judges the selected law on data this module never received.

Every structure is counted in a :class:`engcore.claims.multiplicity.MultiplicityLedger`: ``generated`` is the size of
the grammar before any cap (so a cap shows as generated > deduplicated), ``deduplicated`` / ``admitted`` every
structure given, ``eliminated`` the ones that could not be fitted, and the selected one is promoted -- so the record never shows the selected law as if it were the only attempt.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ...claims.multiplicity import MultiplicityLedger, promote
from .fit import Fit, fit
from .grammar import EXP_CLIP, Structure, exp_argument, log_f

STRATEGY_ID = "forge.mind.grammar.enumeration"
STRATEGY_VERSION = "0.1.0-dev"
TOP = 10
FOLDS = 3
OCCAM_SLACK = 0.05


class ScoreRefused(ValueError):
    """No usable replicate-noise estimate: the likelihood the score needs is not defined."""


@dataclass(frozen=True)
class Scored:
    fit: Fit
    score: float


@dataclass(frozen=True)
class Selection:
    chosen: Fit | None
    reason: str
    ranked: tuple[Scored, ...]
    cv: tuple[tuple[str, float], ...]
    family_size: int
    unfitted: int
    not_converged: int


def log_prior(structures: Sequence[Structure]) -> dict[str, float]:
    per_shape = collections.Counter(s.shape for s in structures)
    shapes = len(per_shape)
    return {s.key: -math.log(shapes) - math.log(per_shape[s.shape]) for s in structures}


def _sigma(sigma: float | None) -> float:
    if sigma is None or isinstance(sigma, bool) or not math.isfinite(float(sigma)) or float(sigma) <= 0:
        raise ScoreRefused(f"a replicate-noise estimate is required, got {sigma!r}")
    return float(sigma)


def score(f: Fit, prior: float, sigma: float) -> float:
    return f.rss / _sigma(sigma) ** 2 + f.structure.n_params * math.log(f.n) - 2.0 * prior


def _cv_mse(structure: Structure, L: np.ndarray, z: np.ndarray) -> float:
    errs: list[float] = []
    idx = np.arange(len(z))
    for k in range(FOLDS):
        train, test = idx % FOLDS != k, idx % FOLDS == k
        f = fit(structure, L[train], z[train])
        if not f.ok or not test.any():
            return math.inf
        r = log_f(structure, np.asarray(f.theta), L[test]) - z[test]
        u = exp_argument(structure, np.asarray(f.theta), L[test])
        if not np.all(np.isfinite(r)) or (u is not None and float(np.max(np.abs(u))) >= EXP_CLIP):
            # a test row where only the clipped exp fits is not a prediction of the (unclipped) emitted law
            return math.inf
        errs += list(r * r)
    return float(np.mean(errs)) if errs else math.inf


def select(structures: Sequence[Structure], L: np.ndarray, z: np.ndarray, *, sigma: float | None, ledger_id: str,
           generated: int | None = None) -> Selection:
    sigma = _sigma(sigma)
    if generated is not None and generated < len(structures):
        raise ValueError("generated counts the grammar before any cap: it cannot be below the structures given")
    ledger = MultiplicityLedger(ledger_id)
    ledger.strategy(STRATEGY_ID, STRATEGY_VERSION)
    ledger.count("generated", len(structures) if generated is None else generated)
    ledger.count("deduplicated", len(structures))
    ledger.count("admitted", len(structures))
    prior = log_prior(structures)
    fits = [fit(s, L, z) for s in structures]
    unfitted = sum(not f.ok for f in fits)
    not_converged = sum(f.ok and not f.converged for f in fits)
    ledger.count("eliminated", unfitted)
    ranked = sorted((Scored(f, score(f, prior[f.structure.key], sigma)) for f in fits if f.ok),
                    key=lambda x: (x.score, x.fit.structure.key))
    for s in ranked:
        ledger.tested(s.fit.structure.key)

    def done(chosen: Fit | None, reason: str, cv: tuple = ()) -> Selection:
        ctx = ledger.close()
        return Selection(chosen, reason, tuple(ranked[:TOP]), cv, ctx.family_size, unfitted, not_converged)

    if not ranked:
        return done(None, "no structure could be fitted")
    cv = [(s.fit.structure, _cv_mse(s.fit.structure, L, z)) for s in ranked[:TOP]]
    cv_keys = tuple((s.key, m) for s, m in cv)
    best = min(m for _, m in cv)
    if not math.isfinite(best):
        return done(None, "no top-scored structure survives cross-validation", cv_keys)
    eligible = [s for s, m in cv if m <= best * (1 + OCCAM_SLACK)]
    chosen = min(eligible, key=lambda s: (s.n_params, s.nodes, s.key))
    final = fit(chosen, L, z)
    if not final.ok:
        return done(None, "the selected structure failed its refit", cv_keys)
    promote(f"grammar:{chosen.key}", chosen.key, ledger)
    return done(final, "selected", cv_keys)


__all__ = ["FOLDS", "OCCAM_SLACK", "STRATEGY_ID", "STRATEGY_VERSION", "ScoreRefused", "Scored", "Selection", "TOP",
           "log_prior", "score", "select"]
