"""EXC-4 (owner-approved 2026-10-30): ``grammar_enumeration``, a development BASELINE arm over :mod:`engcore.mind.grammar`.

Same information and design as ``pysr_symbolic`` (the presented card, the escrow client, ``arms._gather`` with a Latin
hypercube plus replicates, ``arms._split``), so a comparison isolates the hypothesis language and its selection:

1. Buckingham-pi analysis of the card's declared units (settable inputs only; a passive covariate never enters a law).
   Units that cannot be analysed exactly refuse (``insufficient_evidence``), never a guess;
2. every structure of the bounded grammar is fitted on the TRAINING split only and scored with the ln-scale likelihood
   at the replicate-noise estimate (no estimate -> refusal), BIC penalty and declared prior; cross-validation inside
   the training split selects one (multiplicity ledger kept, its id bound to the universe, seed and training data);
3. the selected law is judged by :func:`gate`, which is ``arms._gate``'s decision rule IN ITS ORDER for a free-form law
   (review H1 and its re-review, 2026-10-30): (a) on the held-out rows the law must beat a constant, else ``no_law``;
   (b) the precision bar ``se = rms_train x sqrt(p / n_train) <= arms.PRECISION`` (p the structure's parameters) and
   the lack-of-fit bar against the replicate noise must both hold, else the covariate-residual check answers
   ``confounded`` or the arm refuses; (c) no extrapolation outside the query box.

A non-positive output refuses (the grammar is on the ln scale) instead of dropping rows. Any other failure propagates and
the campaign scores the universe ``inadmissible``. DEVELOPMENT_ONLY: not frozen, no lift claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from typing import Any, Callable, Mapping

import numpy as np

from engcore.blindfold import baselines as bf
from engcore.blindfold.expression import ExpressionRefused, validate
from engcore.mind.grammar import DimensionRefused, InputDimension, analyse, enumerate_structures, select, to_expression

from . import arms
from .arms_v3 import _log_value, _refuse


def design_matrix(basis: Any, rows: list[Mapping[str, float]], out: str) -> tuple[np.ndarray, np.ndarray]:
    """(ln-group matrix L, target z = ln y - ln scale) for the rows."""
    L = np.array([[sum(e * math.log(r[n]) for n, e in g.items()) for g in basis.groups] for r in rows]).reshape(len(rows), -1)
    z = np.array([math.log(r[out]) - sum(float(e) * math.log(r[n]) for n, e in basis.scale.items()) for r in rows])
    return L, z


def _confounded(card: Mapping[str, Any], rows: list[dict], law: dict) -> bool:
    """``arms._gate``'s check on a failed bar: residuals of the law track the first passive covariate (|r| > 0.5)."""
    out, covs = card["output"]["name"], list(card.get("observed_covariates", ()))
    if not covs:
        return False
    pos = [r for r in rows if r[out] > 0 and r[covs[0]] > 0 and _log_value(law, r) is not None]
    if len(pos) <= 3:
        return False
    res = [math.log(r[out]) - _log_value(law, r) for r in pos]
    cv = [math.log(r[covs[0]]) for r in pos]
    return float(np.std(cv)) > 0 and abs(float(np.corrcoef(res, cv)[0, 1])) > 0.5


def gate(card: Mapping[str, Any], rows: list[dict], replicate: int, law: dict, n_params: int, why: str) -> dict[str, Any]:
    """``arms._gate`` in its order, for a free-form law (see the module docstring)."""
    uid, out = card["universe_id"], card["output"]["name"]
    train, hold, _, _ = arms._split(rows, replicate)
    noise = arms._replicate_noise(rows, replicate, out)
    fit_train = [(math.log(r[out]), _log_value(law, r)) for r in train if r[out] > 0]
    fit_hold = [(math.log(r[out]), _log_value(law, r)) for r in hold if r[out] > 0]
    if len(fit_hold) < 3 or any(p is None for _, p in fit_train + fit_hold):
        return _refuse(card, f"{why}: the law is undefined on some queries or there are too few held-out rows")
    err_fit = [y - p for y, p in fit_hold]
    mean_train = float(np.mean([y for y, _ in fit_train]))
    err_const = [y - mean_train for y, _ in fit_hold]
    if float(np.mean(np.square(err_fit))) > 0.8 * float(np.mean(np.square(err_const))):
        return {"universe_id": uid, "answer": "no_law", "rationale": f"{why}: on held-out queries the variables do not beat "
                                                                     "a constant"}
    resid = float(np.sqrt(np.mean(np.square([y - p for y, p in fit_train]))))
    se = resid * math.sqrt(n_params / len(fit_train))
    scale = noise if noise is not None and noise > 0 else resid
    rms_hold = float(np.sqrt(np.mean(np.square(err_fit))))
    precise = se <= arms.PRECISION
    fits = rms_hold <= arms.LACK_OF_FIT_RATIO * scale and resid <= arms.LACK_OF_FIT_RATIO * scale
    if not (precise and fits):
        if _confounded(card, rows, law):
            return {"universe_id": uid, "answer": "confounded", "rationale": f"{why}: residuals track a passive covariate"}
        bar = [] if precise else [f"precision (se {se:.4f} > {arms.PRECISION})"]
        bar += [] if fits else ["lack of fit"]
        return _refuse(card, f"{why}: bar not met: {', '.join(bar)}")
    if bf._extrapolates(card):
        return _refuse(card, f"{why}: assessment region lies outside the query box")
    return {"universe_id": uid, "answer": "law", "law": law, "rationale": why}


def grammar_enumeration(card: Mapping[str, Any], client: Any, *, seed: int = 0) -> dict[str, Any]:
    uid, out = card["universe_id"], card["output"]["name"]
    rng = random.Random(f"grammar:{seed}:{uid}")
    rows, replicate = arms._gather(card, client, rng, "lhs", "g")
    settable = [x for x in card["inputs"] if x.get("settable")]
    if len(rows) < len(settable) + 6 + replicate:
        return _refuse(card, "too few observations")
    if any(not (r[out] > 0) for r in rows):
        return _refuse(card, "a non-positive output: the ln-scale grammar does not apply")
    try:
        basis = analyse([InputDimension(x["name"], x["unit"], x["range"][0], x["range"][1]) for x in settable],
                        card["output"]["unit"], card["base_dimensions"])
    except DimensionRefused as exc:
        return _refuse(card, f"dimensional analysis refused: {exc}")
    sigma = arms._replicate_noise(rows, replicate, out)
    if sigma is None or not sigma > 0:
        return _refuse(card, "no replicate-noise estimate: the grammar's likelihood is not defined")
    train, _, _, _ = arms._split(rows, replicate)
    structures, cap_hit = enumerate_structures(len(basis.groups))
    generated = len(enumerate_structures(len(basis.groups), max_structures=sys.maxsize)[0])
    L, z = design_matrix(basis, train, out)
    bound = hashlib.sha256(json.dumps([uid, seed, train], sort_keys=True).encode()).hexdigest()[:24]
    sel = select(structures, L, z, sigma=sigma, ledger_id=f"grammar:{bound}", generated=generated)
    note = (f"grammar enumeration ({len(structures)} of {generated} structures{', cap hit' if cap_hit else ''}; family "
            f"size {sel.family_size}; {sel.not_converged} iteration-capped; {len(basis.groups)} groups)")
    if sel.chosen is None:
        return _refuse(card, f"{note}: {sel.reason}")
    law = to_expression(sel.chosen.structure, np.asarray(sel.chosen.theta), basis)
    try:
        validate(law)
    except ExpressionRefused as exc:
        return _refuse(card, f"{note}: the selected law is outside the escrow grammar limits: {exc}")
    chosen = (f"selected {sel.chosen.structure.key}"
              f"{'' if sel.chosen.converged else ' (its fit hit the iteration cap: finite, not converged)'}")
    return gate(card, rows, replicate, law, sel.chosen.structure.n_params, f"{note}: {chosen}")


#: name -> (callable, family, stochastic, role), the arms.ARMS layout
GRAMMAR_ARMS: dict[str, tuple[Callable[..., dict[str, Any]], str, bool, str]] = {
    "grammar_enumeration": (grammar_enumeration, "law recovery: bounded grammar enumeration over Buckingham-pi groups "
                            "(EXC-4 development baseline)", True, "competence"),
}

__all__ = ["GRAMMAR_ARMS", "design_matrix", "gate", "grammar_enumeration"]
