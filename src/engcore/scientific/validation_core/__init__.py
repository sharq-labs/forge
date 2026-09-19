"""Domain-neutral validation pipeline contracts."""

from .fingerprint import validation_report_fingerprint
from .gate import gate_validation
from .issue import ValidationIssue, ValidationSeverity
from .pipeline import ValidationPipeline
from .policy import ValidationPolicy
from .report import ValidationDecision, ValidationReport
from .stage import StageResult, ValidationStage

__all__ = [
    "ValidationSeverity", "ValidationIssue", "ValidationStage", "StageResult",
    "ValidationPolicy", "ValidationDecision", "ValidationReport",
    "ValidationPipeline", "gate_validation", "validation_report_fingerprint",
]
