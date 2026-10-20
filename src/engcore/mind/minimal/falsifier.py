"""The FALSIFIER role: for each strong hypothesis, the admissible experiment most likely to falsify it.

It PROPOSES tests; it decides nothing.  For a hypothesis H with substantial standing and its strongest live rival R,
it searches the admissible candidate settings for the one where H's sealed-to-be prediction and R's differ most
relative to their combined predictive uncertainty, and proposes it as a DISCRIMINATE candidate.  Whether that
experiment is run is the selection's decision; whether H is falsified is the falsification registry's verdict on the
released observation.

It also reports when NO admissible experiment can discriminate two rivals (their predictions agree within noise at
every admissible setting): that is a finding about the problem -- what the box of settable inputs can and cannot
reach -- and the conclusion uses it to preserve rivals instead of choosing one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ...sria.decision import ActionFamily
from .competition import HypothesisCompetition
from .experiments import ExperimentCandidate, candidate
from .problem import ExperimentalProblem

FALSIFIER_ROLE_ID = "forge.mind.minimal.falsifier_role"
STRONG_WEIGHT = 0.2
MAX_PROPOSALS = 2


@dataclass(frozen=True)
class FalsificationProposal:
    hypothesis_id: str
    rival_id: str
    candidate: ExperimentCandidate
    separation_sigmas: float

    def to_dict(self) -> dict[str, Any]:
        return {"hypothesis_id": self.hypothesis_id, "rival_id": self.rival_id, "candidate_id": self.candidate.candidate_id,
                "separation_sigmas": round(self.separation_sigmas, 9), "role": FALSIFIER_ROLE_ID}


def separation(competition: HypothesisCompetition, a: str, b: str, points: Sequence[Mapping[str, float]]) -> np.ndarray:
    """|m_a - m_b| / sqrt(total predictive variance) at each point (ln units)."""
    fa, fb = competition.rivals[a].fitted, competition.rivals[b].fitted
    la, sa, oa = competition.model.predict_many(fa, points, competition.covmodels)
    lb, sb, ob = competition.model.predict_many(fb, points, competition.covmodels)
    with np.errstate(all="ignore"):
        sep = np.abs(la - lb) / np.sqrt(oa ** 2 + ob ** 2)
    return np.where(np.isfinite(sep), sep, 0.0)


def propose(problem: ExperimentalProblem, competition: HypothesisCompetition, weights: Mapping[str, float],
            pool: Sequence[ExperimentCandidate]) -> list[FalsificationProposal]:
    ranked = sorted(weights, key=lambda h: (-weights[h], h))
    strong = [h for h in ranked if weights[h] >= STRONG_WEIGHT][:MAX_PROPOSALS]
    pts = [c.settings for c in pool if c.feasible(problem)[0]]
    out = []
    if not pts:
        return out
    for h in strong:
        rivals = [r for r in ranked if r != h]
        if not rivals:
            continue
        r = rivals[0]
        sep = separation(competition, h, r, pts)
        if not np.any(sep > 0):
            continue
        i = int(np.argmax(sep))
        c = candidate(pts[i], ActionFamily.DISCRIMINATE, "falsifier", h,
                      f"the admissible setting where {h} and its strongest rival {r} disagree most "
                      f"({sep[i]:.3g} predictive sigmas): most likely to falsify one of them",
                      (f"role={FALSIFIER_ROLE_ID}",))
        out.append(FalsificationProposal(h, r, c, float(sep[i])))
    return out


def admissible_discriminator(competition: HypothesisCompetition, a: str, b: str, points: Sequence[Mapping[str, float]],
                             sigmas: float = 2.0) -> bool:
    """Whether any admissible setting separates rivals a and b by more than ``sigmas`` predictive sigmas."""
    if not points:
        return False
    sep = separation(competition, a, b, points)
    return bool(np.any(np.isfinite(sep) & (sep > sigmas)))


__all__ = ["FALSIFIER_ROLE_ID", "FalsificationProposal", "admissible_discriminator", "propose", "separation"]
