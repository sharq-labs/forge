from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

VALIDATION_ISSUE_SCHEMA = schema_string("validation_issue")


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: ValidationSeverity

    def __post_init__(self) -> None:
        code = str(self.code).strip()
        message = str(self.message).strip()
        if not code or not message:
            raise InvalidScientificProblem("validation issue requires code and message")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "severity", ValidationSeverity(self.severity))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": VALIDATION_ISSUE_SCHEMA, "code": self.code,
                "message": self.message, "severity": self.severity.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidationIssue":
        require_schema(payload, VALIDATION_ISSUE_SCHEMA)
        return cls(payload["code"], payload["message"], ValidationSeverity(payload["severity"]))
