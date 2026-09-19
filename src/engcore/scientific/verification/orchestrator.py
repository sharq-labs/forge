from __future__ import annotations

from .adjudication import VerificationDecision, adjudicate
from .comparison import RouteComparison
from .independence import IndependenceEvidence
from .report import VerificationReport


class VerificationOrchestrator:
    def build_report(self,comparisons:tuple[RouteComparison,...],independence:tuple[IndependenceEvidence,...])->VerificationReport:
        return VerificationReport(adjudicate(comparisons,independence),tuple(comparisons),tuple(independence))

from .execution_report import VerificationExecutionReport
from .observations import VerificationObservation
from .planning import VerificationPlan
from .quantity_comparison import compare_observations
from ..units.quantity import Quantity

def build_execution_report(plan:VerificationPlan,primary:VerificationObservation,
                           observations:tuple[VerificationObservation,...],tolerance:Quantity,
                           execution_problems:tuple[str,...]=())->VerificationExecutionReport:
    if primary.route_id!=plan.primary_route.route_id:
        raise ValueError("primary observation route does not match verification plan")
    by_id={o.route_id:o for o in observations}
    if len(by_id)!=len(observations): raise ValueError("duplicate verification observations")
    comparisons=[];independence=[];missing=[]
    for item in plan.selected:
        rid=item.candidate.route.route_id
        observation=by_id.get(rid)
        if observation is None:
            missing.append(rid);continue
        comparisons.append(compare_observations(primary,observation,tolerance))
        independence.append(item.independence)
    if missing or execution_problems or not plan.complete:
        decision=VerificationDecision.NO_VERIFICATION
        verification=VerificationReport(decision,(),())
    else:
        verification=VerificationReport(adjudicate(tuple(comparisons),tuple(independence)),
                                        tuple(comparisons),tuple(independence))
    return VerificationExecutionReport(plan,verification,tuple(missing),tuple(execution_problems))
