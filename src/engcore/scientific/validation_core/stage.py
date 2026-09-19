from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .issue import ValidationIssue

STAGE_RESULT_SCHEMA = schema_string("validation_stage_result")


class ValidationStage(str, Enum):
    CONTRACT = "contract"
    DIMENSIONS = "dimensions"
    APPLICABILITY = "applicability"
    NUMERICS = "numerics"
    UNCERTAINTY = "uncertainty"
    EVIDENCE = "evidence"
    INDEPENDENT_VERIFICATION = "independent_verification"
    REPLAY = "replay"


@dataclass(frozen=True)
class StageResult:
    stage: ValidationStage
    passed: bool
    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", ValidationStage(self.stage))
        if not isinstance(self.passed, bool):
            raise InvalidScientificProblem("validation stage passed must be bool")
        object.__setattr__(self, "issues", tuple(self.issues))
        if any(not isinstance(i, ValidationIssue) for i in self.issues):
            raise InvalidScientificProblem("validation stage issues must be ValidationIssue records")
        if self.passed and any(i.severity.value in {"error", "fatal"} for i in self.issues):
            raise InvalidScientificProblem("passing validation stage cannot contain error/fatal issues")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": STAGE_RESULT_SCHEMA, "stage": self.stage.value,
                "passed": self.passed, "issues": [i.to_dict() for i in self.issues]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StageResult":
        require_schema(payload, STAGE_RESULT_SCHEMA)
        return cls(ValidationStage(payload["stage"]), payload["passed"],
                   tuple(ValidationIssue.from_dict(i) for i in payload.get("issues", ())))
