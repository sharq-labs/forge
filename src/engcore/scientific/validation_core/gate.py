from __future__ import annotations

from .issue import ValidationSeverity
from .policy import ValidationPolicy
from .report import ValidationDecision, ValidationReport
from .stage import StageResult


def gate_validation(results: tuple[StageResult, ...], policy: ValidationPolicy) -> ValidationReport:
    by_stage = {result.stage: result for result in results}
    missing = [stage for stage in policy.required_stages if stage not in by_stage]
    if missing:
        return ValidationReport(ValidationDecision.INCOMPLETE, tuple(results))
    failed = any(not by_stage[stage].passed for stage in policy.required_stages)
    if policy.refuse_warnings:
        failed = failed or any(
            issue.severity is ValidationSeverity.WARNING
            for result in results for issue in result.issues
        )
    return ValidationReport(
        ValidationDecision.REFUSED if failed else ValidationDecision.ACCEPTED,
        tuple(results),
    )
