from __future__ import annotations

from dataclasses import dataclass

from .gate import gate_validation
from .policy import ValidationPolicy
from .report import ValidationReport
from .stage import StageResult


@dataclass(frozen=True)
class ValidationPipeline:
    policy: ValidationPolicy = ValidationPolicy()

    def assess(self, *results: StageResult) -> ValidationReport:
        ordered = tuple(sorted(results, key=lambda item: list(type(item.stage)).index(item.stage)))
        return gate_validation(ordered, self.policy)
