"""ScientificStopping (M-8): STOP, CONTINUE or REFUSE, from explicit cost and remaining uncertainty.

* REFUSE -- the model of the observable is inapplicable to the admitted evidence, or no admissible experiment exists.
* STOP   -- the budget is spent; or the decision no longer needs evidence: the leading rival holds at least
  :data:`DECIDED_WEIGHT` of the posterior, the predictive sd over the region of use is under half the precision the
  conclusion requires, and no candidate's utility per unit cost reaches :data:`UTILITY_FLOOR` (another query would
  cost without an expected change).
* CONTINUE -- otherwise.

The thresholds are part of the Mind's identity; none of them is a scientific threshold of any authority, and a STOP
decides nothing about any hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

DECIDED_WEIGHT = 0.995
UTILITY_FLOOR = 1e-3


class StopKind(str, Enum):
    CONTINUE = "continue"
    STOP = "stop"
    REFUSE = "refuse"


@dataclass(frozen=True)
class StopDecision:
    kind: StopKind
    reason: str
    budget_remaining: int
    leading_weight: float | None
    region_sd: float | None
    max_utility: float | None

    def to_dict(self) -> dict[str, Any]:
        r = (lambda x: None if x is None else round(float(x), 9))
        return {"kind": self.kind.value, "reason": self.reason, "budget_remaining": self.budget_remaining,
                "leading_weight": r(self.leading_weight), "region_sd": r(self.region_sd), "max_utility": r(self.max_utility)}


def decide(*, budget_remaining: int, inapplicable: str | None, has_candidate: bool, adaptive_phase: bool,
           leading_weight: float | None, region_sd: float | None, max_utility: float | None, precision: float) -> StopDecision:
    def out(kind: StopKind, reason: str) -> StopDecision:
        return StopDecision(kind, reason, budget_remaining, leading_weight, region_sd, max_utility)

    if inapplicable:
        return out(StopKind.REFUSE, f"inapplicable: {inapplicable}")
    if budget_remaining <= 0:
        return out(StopKind.STOP, "the query budget is spent")
    if not has_candidate:
        return out(StopKind.REFUSE, "no admissible experiment remains")
    if (adaptive_phase and leading_weight is not None and leading_weight >= DECIDED_WEIGHT and region_sd is not None
            and region_sd <= precision / 2 and max_utility is not None and max_utility < UTILITY_FLOOR):
        return out(StopKind.STOP, "decided: the leading rival dominates, the region is predicted to well under the required "
                                  "precision, and no admissible query is expected to change that")
    return out(StopKind.CONTINUE, "evidence can still change the decision")


__all__ = ["DECIDED_WEIGHT", "StopDecision", "StopKind", "UTILITY_FLOOR", "decide"]
