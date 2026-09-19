from __future__ import annotations

from .adjudication import adjudicate
from .comparison import RouteComparison
from .independence import IndependenceEvidence
from .report import VerificationReport


class VerificationOrchestrator:
    def build_report(self,comparisons:tuple[RouteComparison,...],independence:tuple[IndependenceEvidence,...])->VerificationReport:
        return VerificationReport(adjudicate(comparisons,independence),tuple(comparisons),tuple(independence))
