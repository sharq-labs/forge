from __future__ import annotations

from ..validation_core import (
    StageResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStage,
)
from .stability import (
    NumericalStabilityAssessment,
    NumericalStabilityDecision,
)


def numerical_stability_stage(
    assessment: NumericalStabilityAssessment,
) -> StageResult:
    issues = []
    if assessment.decision is not NumericalStabilityDecision.ACCEPTABLE:
        severity = (
            ValidationSeverity.WARNING
            if assessment.decision is NumericalStabilityDecision.DEGRADED
            else ValidationSeverity.ERROR
        )
        for index, reason in enumerate(assessment.reasons, start=1):
            issues.append(
                ValidationIssue(
                    f"numerical_stability_{index}",
                    reason,
                    severity,
                )
            )
    passed = assessment.decision in {
        NumericalStabilityDecision.ACCEPTABLE,
        NumericalStabilityDecision.DEGRADED,
    }
    return StageResult(ValidationStage.NUMERICS, passed, tuple(issues))
