"""ExperimentCandidate (M-5) and ExperimentSelection (M-6).

A candidate is a typed admissible scientific action: a setting of every settable input inside the box, labelled with
the canonical :class:`~engcore.sria.decision.ActionFamily` of the generator that proposed it and an
:class:`~engcore.sria.decision.ActionProposal` saying what it targets and why.  An outside engine (a language model,
a Bayesian-optimisation library) may SUGGEST a candidate only as an :class:`~engcore.sria.decision.ExternalSuggestion`
(which refuses any authority key); its acquisition value is recorded as the engine's own number and never enters the
ranking.  A setting outside the box is INFEASIBLE and never reaches scoring.

Selection ranks every feasible candidate with ONE utility whose terms are :class:`~engcore.sria.decision.ScoreComponent`
records citing the outcome-model basis they were computed from:

* ``expected_discrimination`` -- sum over pairs of rivals of w_a w_b (m_a - m_b)^2 / (s2_a + s2_b + v_a + v_b), the
  Box-Hill style divergence of the rivals' sealed-to-be predictions at that setting (posterior weights w, predictive
  means m, noise variances s2, parameter variances v);
* ``expected_precision_gain`` -- for the leading rival, 0.5 ln(V_now / V_after): the reduction of the mean predictive
  variance over the region where the conclusion will be used if this setting is added (a V-optimal design term);
* the query cost from the problem statement (every query costs the same here; the utility is divided by it).

The utility is a ranking device of this Mind, not a FORGE expected utility, and decides nothing about any hypothesis.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ...sria.decision import ActionFamily, ActionProposal, ComponentStatus, ScoreComponent
from ...sria.decision.external import ExternalSuggestion
from .competition import HypothesisCompetition
from .problem import ExperimentalProblem

CANDIDATE_SCHEMA = "forge.mind.minimal.experiment_candidate/1"
RANDOM_CANDIDATES = 32
MAX_RIVALS_IN_UTILITY = 8


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _round(v: float) -> float:
    return float(f"{float(v):.12g}")


@dataclass(frozen=True)
class ExperimentCandidate:
    settings: Mapping[str, float]
    proposal: ActionProposal
    generator: str
    suggestion_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "settings", {k: _round(v) for k, v in sorted(dict(self.settings).items())})

    @property
    def family(self) -> ActionFamily:
        return self.proposal.family

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CANDIDATE_SCHEMA, "settings": dict(self.settings), "proposal": self.proposal.to_dict(),
                "generator": self.generator, "suggestion_digest": self.suggestion_digest}

    @property
    def candidate_id(self) -> str:
        return _digest({"settings": dict(self.settings), "family": self.family.value, "generator": self.generator})

    def feasible(self, problem: ExperimentalProblem) -> tuple[bool, str]:
        names = {x.name for x in problem.inputs}
        if set(self.settings) != names:
            return False, "a candidate sets every settable input and nothing else"
        for x in problem.inputs:
            v = self.settings[x.name]
            if not (math.isfinite(v) and x.low <= v <= x.high):
                return False, f"{x.name}={v} lies outside the settable box"
        return True, "inside the settable box"


def candidate(settings: Mapping[str, float], family: ActionFamily, generator: str, target: str, rationale: str,
              assumptions: Sequence[str] = (), suggestion_digest: str = "") -> ExperimentCandidate:
    return ExperimentCandidate(settings, ActionProposal(family=family, target_ref=target, rationale=rationale,
                                                        assumptions=tuple(assumptions), expected_observable="observable"),
                               generator, suggestion_digest)


def from_suggestion(s: ExternalSuggestion) -> ExperimentCandidate:
    """An outside engine's suggestion becomes a candidate with its provenance; its acquisition value is not used."""
    if not isinstance(s, ExternalSuggestion):
        raise TypeError("only an ExternalSuggestion becomes a candidate")
    settings = {str(k): float(v) for k, v in dict(s.point).items()}
    return candidate(settings, s.family, f"external:{s.engine_kind.value}:{s.engine_id}@{s.engine_version}", s.target_ref,
                     s.rationale, (f"suggestion_digest={s.digest}",
                                   "the engine's acquisition value is its own number and is not used here"), s.digest)


# ---- generators -----------------------------------------------------------------------------------------------------------
def lhs(problem: ExperimentalProblem, n: int, rng: random.Random) -> list[dict[str, float]]:
    """Latin hypercube in log space over the box (canonical input order, so renaming changes nothing)."""
    xs = problem.canonical_inputs()
    cols = {}
    for x in xs:
        lo, hi = math.log(x.low), math.log(x.high)
        cells = [lo + (hi - lo) * (i + rng.random()) / n for i in range(n)]
        rng.shuffle(cells)
        cols[x.name] = cells
    return [{x.name: math.exp(cols[x.name][i]) for x in xs} for i in range(n)]


def corners(problem: ExperimentalProblem) -> list[dict[str, float]]:
    xs = problem.canonical_inputs()
    if len(xs) > 5:
        return []
    return [dict(zip([x.name for x in xs], combo)) for combo in itertools.product(*[(x.low, x.high) for x in xs])]


def center(problem: ExperimentalProblem) -> dict[str, float]:
    return {x.name: math.sqrt(x.low * x.high) for x in problem.inputs}


def adaptive_candidates(problem: ExperimentalProblem, rng: random.Random, competition: HypothesisCompetition,
                        extra: Iterable[ExperimentCandidate] = ()) -> list[ExperimentCandidate]:
    out = [candidate(p, ActionFamily.EXPLORE, "space_filling", "design", "space-filling coverage of the box")
           for p in lhs(problem, RANDOM_CANDIDATES, rng)]
    out += [candidate(p, ActionFamily.DISCRIMINATE, "corner", "design", "box corner: largest leverage on every slope")
            for p in corners(problem)]
    out.append(candidate(center(problem), ActionFamily.CHARACTERIZE, "center", "design", "box centre: curvature contrast"))
    if competition.rows:
        out.append(candidate(dict(competition.rows[-1].settings), ActionFamily.REDUCE_UNCERTAINTY, "replicate", "noise",
                             "replicate the latest setting: a redundant confirmation that only refines the noise estimate"))
    out += list(extra)
    # an already observed setting re-enters ONLY as the declared replicate: a generator that keeps returning to the same
    # corner (as optimal designs for an assumed model do) would spend the budget re-confirming that model and could never
    # check it (found on development worlds: up to 18 of 30 queries were repeats)
    observed = {json.dumps(dict(sorted((k, _round(v)) for k, v in r.settings.items()))) for r in competition.rows}
    seen, unique = set(), []
    for c in out:
        key = json.dumps(dict(c.settings))
        if c.generator != "replicate" and key in observed:
            continue
        if c.candidate_id not in seen:
            seen.add(c.candidate_id)
            unique.append(c)
    return unique


# ---- selection ----------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ScoredCandidate:
    candidate: ExperimentCandidate
    feasible: bool
    reason: str
    components: tuple[ScoreComponent, ...] = ()
    total: float | None = None

    def component(self, name: str) -> ScoreComponent | None:
        return next((c for c in self.components if c.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate.candidate_id, "family": self.candidate.family.value,
                "generator": self.candidate.generator, "feasible": self.feasible, "reason": self.reason,
                "total": None if self.total is None else round(self.total, 9),
                "components": [c.to_dict() for c in self.components]}


@dataclass(frozen=True)
class Selection:
    selected: ExperimentCandidate | None
    scored: tuple[ScoredCandidate, ...]
    weights_used: Mapping[str, float]
    basis_digest: str
    policy: str
    max_utility: float | None = None

    def summary(self, top: int = 8) -> dict[str, Any]:
        ranked = sorted((s for s in self.scored if s.total is not None), key=lambda s: (-s.total, s.candidate.candidate_id))
        return {"policy": self.policy, "candidates": len(self.scored),
                "candidate_set_digest": _digest(sorted(s.candidate.candidate_id for s in self.scored)),
                "infeasible": sum(not s.feasible for s in self.scored), "basis_digest": self.basis_digest,
                "weights_used_digest": _digest({k: round(v, 12) for k, v in sorted(self.weights_used.items())}),
                "top": [s.to_dict() for s in ranked[:top]],
                "selected": None if self.selected is None else self.selected.to_dict(),
                "max_utility": None if self.max_utility is None else round(self.max_utility, 9)}


def score_candidates(problem: ExperimentalProblem, competition: HypothesisCompetition,
                     candidates: Sequence[ExperimentCandidate], weights: Mapping[str, float]) -> list[ScoredCandidate]:
    feas = [(c, *c.feasible(problem)) for c in candidates]
    ok = [c for c, f, _ in feas if f]
    out = [ScoredCandidate(c, False, why) for c, f, why in feas if not f]
    if not ok:
        return out
    basis = competition.model.basis_digest(competition.rows)
    live = sorted(weights, key=lambda h: (-weights[h], h))[:MAX_RIVALS_IN_UTILITY]
    pts = [c.settings for c in ok]
    preds = {}
    for hid in live:
        fitted = competition.rivals[hid].fitted
        loc, sdm, sdo = competition.model.predict_many(fitted, pts, competition.covmodels)
        preds[hid] = (loc, sdm ** 2, sdo ** 2 - sdm ** 2)
    disc = np.zeros(len(ok))
    with np.errstate(all="ignore"):
        for a, b in itertools.combinations(live, 2):
            la, va, na = preds[a]
            lb, vb, nb = preds[b]
            term = weights[a] * weights[b] * (la - lb) ** 2 / (na + nb + va + vb)
            # a rival whose prediction is not finite at a setting contributes nothing there (never an infinite pull)
            disc += np.where(np.isfinite(term), term, 0.0)
    lead = live[0] if live else None
    prec = np.zeros(len(ok))
    if lead is not None:
        prec = _precision_gain(problem, competition, lead, pts)
    w_lead = weights.get(lead, 0.0) if lead else 0.0
    cost = float(problem.query_cost)
    src = f"outcome_model:{basis[:16]}"
    for i, c in enumerate(ok):
        comps = (ScoreComponent("expected_discrimination", float(disc[i]), ComponentStatus.AVAILABLE, source=src, unit="1",
                                detail=f"{len(live)} rivals by posterior weight"),
                 ScoreComponent("expected_precision_gain", float(prec[i]), ComponentStatus.AVAILABLE, source=src, unit="nat",
                                detail=f"leading rival {lead}"),
                 ScoreComponent("query_cost", cost, ComponentStatus.AVAILABLE, source="problem statement", unit="query"))
        total = (float(disc[i]) + w_lead * float(prec[i])) / cost
        out.append(ScoredCandidate(c, True, "inside the settable box", comps, total))
    return out


def _precision_gain(problem: ExperimentalProblem, competition: HypothesisCompetition, lead: str,
                    pts: Sequence[Mapping[str, float]]) -> np.ndarray:
    fitted = competition.rivals[lead].fitted
    if fitted is None or not fitted.fit_ok or fitted.p == 0:
        return np.zeros(len(pts))
    region = problem.region_points()
    R = competition.model.design_matrix(fitted, region, competition.covmodels)
    A = competition.model.design_matrix(fitted, pts, competition.covmodels)
    n = fitted.n
    Rt = np.column_stack([np.full(len(R), 1.0 / math.sqrt(n)), R])     # intercept variance 1/n (centred design)
    At = np.column_stack([np.full(len(A), 1.0 / math.sqrt(n)), A])
    M = np.zeros((fitted.p + 1, fitted.p + 1))
    M[0, 0] = 1.0
    M[1:, 1:] = fitted.inv
    v_now = np.einsum("ij,jk,ik->i", Rt, M, Rt).mean()
    MA = At @ M                                                       # (k, p+1)
    lev = np.einsum("ij,ij->i", MA, At)
    cross = Rt @ MA.T                                                 # (r, k)
    reduction = (cross ** 2).mean(axis=0) / (1.0 + lev)
    v_after = np.maximum(v_now - reduction, 1e-300)
    with np.errstate(all="ignore"):
        gain = 0.5 * np.log(v_now / v_after)
    return np.where(np.isfinite(gain), gain, 0.0)


def select(problem: ExperimentalProblem, competition: HypothesisCompetition, candidates: Sequence[ExperimentCandidate],
           weights: Mapping[str, float], policy: str) -> Selection:
    scored = score_candidates(problem, competition, candidates, weights)
    ranked = sorted((s for s in scored if s.total is not None), key=lambda s: (-s.total, s.candidate.candidate_id))
    chosen = ranked[0].candidate if ranked else None
    return Selection(chosen, tuple(scored), dict(weights), competition.model.basis_digest(competition.rows), policy,
                     ranked[0].total if ranked else None)


__all__ = ["ExperimentCandidate", "ScoredCandidate", "Selection", "adaptive_candidates", "candidate", "center", "corners",
           "from_suggestion", "lhs", "score_candidates", "select"]
