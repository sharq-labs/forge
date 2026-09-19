from __future__ import annotations

from dataclasses import dataclass
from typing import Any,Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema,schema_string
from ..units.quantity import Quantity
from .execution_report import VerificationExecutionReport
from .observations import VerificationObservation
from .orchestrator import build_execution_report
from .plan_serialization import plan_from_dict,plan_to_dict
from .planning import VerificationPlan
from .serialization import verification_to_dict

VERIFICATION_RUN_SCHEMA=schema_string("verification_run_record")


@dataclass(frozen=True)
class VerificationRunRecord:
    plan:VerificationPlan
    primary:VerificationObservation
    observations:tuple[VerificationObservation,...]
    tolerance:Quantity
    execution_problems:tuple[str,...]=()

    def __post_init__(self)->None:
        object.__setattr__(self,"observations",tuple(self.observations))
        object.__setattr__(self,"execution_problems",tuple(str(x) for x in self.execution_problems))
        if not isinstance(self.plan,VerificationPlan) or not isinstance(self.primary,VerificationObservation):
            raise InvalidScientificProblem("verification run requires plan and primary observation")
        if not isinstance(self.tolerance,Quantity):
            raise InvalidScientificProblem("verification run tolerance must be Quantity")

    @property
    def result(self)->VerificationExecutionReport:
        return build_execution_report(self.plan,self.primary,self.observations,self.tolerance,self.execution_problems)

    def to_dict(self)->dict[str,Any]:
        result=self.result
        return {"schema":VERIFICATION_RUN_SCHEMA,"plan":plan_to_dict(self.plan),
                "primary":self.primary.to_dict(),"observations":[x.to_dict() for x in self.observations],
                "tolerance":self.tolerance.to_dict(),"execution_problems":list(self.execution_problems),
                "result":{"verification":verification_to_dict(result.verification),
                          "missing_routes":list(result.missing_routes),
                          "execution_problems":list(result.execution_problems),
                          "complete":result.complete}}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"VerificationRunRecord":
        require_schema(payload,VERIFICATION_RUN_SCHEMA)
        record=cls(plan_from_dict(payload["plan"]),VerificationObservation.from_dict(payload["primary"]),
            tuple(VerificationObservation.from_dict(x) for x in payload.get("observations",())),
            Quantity.from_dict(payload["tolerance"]),tuple(payload.get("execution_problems",())))
        derived=record.to_dict()["result"]
        if payload.get("result")!=derived:
            raise InvalidScientificProblem("serialized verification run result is forged or stale")
        return record
