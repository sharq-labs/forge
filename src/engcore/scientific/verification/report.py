from __future__ import annotations

from dataclasses import dataclass
from .adjudication import VerificationDecision
from .comparison import RouteComparison
from .independence import IndependenceEvidence


@dataclass(frozen=True)
class VerificationReport:
    decision:VerificationDecision
    comparisons:tuple[RouteComparison,...]
    independence:tuple[IndependenceEvidence,...]

    def __post_init__(self)->None:
        object.__setattr__(self,"decision",VerificationDecision(self.decision))
        object.__setattr__(self,"comparisons",tuple(self.comparisons))
        object.__setattr__(self,"independence",tuple(self.independence))
        if self.decision is VerificationDecision.VERIFIED and any(not c.agreement for c in self.comparisons):
            raise ValueError("verified report cannot contain disagreement")
