from __future__ import annotations
from dataclasses import dataclass
from .report import VerificationReport
from .planning import VerificationPlan

@dataclass(frozen=True)
class VerificationExecutionReport:
    plan:VerificationPlan
    verification:VerificationReport
    missing_routes:tuple[str,...]=()
    execution_problems:tuple[str,...]=()

    @property
    def complete(self)->bool:
        return self.plan.complete and not self.missing_routes and not self.execution_problems
