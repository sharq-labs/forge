from __future__ import annotations

from dataclasses import dataclass
from .adjudication import VerificationDecision, adjudicate
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
        if any(not isinstance(c,RouteComparison) for c in self.comparisons):
            raise ValueError("verification report comparisons must be RouteComparison records")
        if any(not isinstance(i,IndependenceEvidence) for i in self.independence):
            raise ValueError("verification report independence must be IndependenceEvidence records")
        derived=adjudicate(self.comparisons,self.independence)
        if self.decision is not derived:
            raise ValueError(
                f"verification report decision {self.decision.value!r} "
                f"does not match derived {derived.value!r}"
            )
