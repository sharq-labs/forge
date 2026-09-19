from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .stage import StageResult

VALIDATION_REPORT_SCHEMA = schema_string("core_validation_report")


class ValidationDecision(str, Enum):
    ACCEPTED = "accepted"
    REFUSED = "refused"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class ValidationReport:
    decision: ValidationDecision
    stages: tuple[StageResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", ValidationDecision(self.decision))
        object.__setattr__(self, "stages", tuple(self.stages))
        if any(not isinstance(s, StageResult) for s in self.stages):
            raise InvalidScientificProblem("validation report stages must be StageResult records")
        names = [s.stage for s in self.stages]
        if len(names) != len(set(names)):
            raise InvalidScientificProblem("validation report contains duplicate stage results")
        failed = any(not s.passed for s in self.stages)
        if self.decision is ValidationDecision.ACCEPTED and failed:
            raise InvalidScientificProblem("accepted validation report cannot contain failed stage")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": VALIDATION_REPORT_SCHEMA, "decision": self.decision.value,
                "stages": [s.to_dict() for s in self.stages]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationReport":
        require_schema(payload, VALIDATION_REPORT_SCHEMA)
        return cls(ValidationDecision(payload["decision"]),
                   tuple(StageResult.from_dict(s) for s in payload.get("stages", ())))
