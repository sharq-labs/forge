from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..scientific.measurements import CalibratedExperimentalRun
from ..scientific.validation_core import (
    StageResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStage,
)
from .measurement_evidence import (
    MeasurementEvidenceStanding,
    assess_measurement_observation,
)


class ExperimentalValidationDecision(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    REFUSED = "refused"


@dataclass(frozen=True)
class ExperimentalValidationPolicy:
    minimum_observations: int = 3
    minimum_independence_groups: int = 2

    def __post_init__(self) -> None:
        observations = int(self.minimum_observations)
        groups = int(self.minimum_independence_groups)
        if observations < 1 or groups < 1:
            raise ValueError(
                "experimental validation minimums must be positive"
            )
        object.__setattr__(self, "minimum_observations", observations)
        object.__setattr__(self, "minimum_independence_groups", groups)


@dataclass(frozen=True)
class ExperimentalValidationAssessment:
    decision: ExperimentalValidationDecision
    observation_count: int
    independence_groups: tuple[str, ...]
    problems: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision",
            ExperimentalValidationDecision(self.decision),
        )
        object.__setattr__(
            self,
            "independence_groups",
            tuple(sorted(set(self.independence_groups))),
        )
        object.__setattr__(
            self,
            "problems",
            tuple(str(x) for x in self.problems),
        )


def assess_experimental_validation(
    run: CalibratedExperimentalRun,
    *,
    target_context_digest: str,
    policy: ExperimentalValidationPolicy = ExperimentalValidationPolicy(),
) -> ExperimentalValidationAssessment:
    problems = []
    admissible = []
    for observation in run.observations:
        admission = assess_measurement_observation(
            observation,
            target_context_digest=target_context_digest,
        )
        if admission.standing is not MeasurementEvidenceStanding.ADMISSIBLE:
            problems.append(
                f"{observation.observation_id}: "
                + "; ".join(admission.reasons)
            )
        else:
            admissible.append(observation)

    groups = tuple(
        sorted(
            {
                observation.independence_group
                for observation in admissible
            }
        )
    )
    if problems:
        return ExperimentalValidationAssessment(
            ExperimentalValidationDecision.REFUSED,
            len(admissible),
            groups,
            tuple(problems),
        )

    if len(admissible) < policy.minimum_observations:
        problems.append(
            f"only {len(admissible)} admissible observations; "
            f"{policy.minimum_observations} required"
        )
    if len(groups) < policy.minimum_independence_groups:
        problems.append(
            f"only {len(groups)} independent groups; "
            f"{policy.minimum_independence_groups} required"
        )

    decision = (
        ExperimentalValidationDecision.INSUFFICIENT
        if problems
        else ExperimentalValidationDecision.SUFFICIENT
    )
    return ExperimentalValidationAssessment(
        decision,
        len(admissible),
        groups,
        tuple(problems),
    )


def experimental_validation_stage(
    assessment: ExperimentalValidationAssessment,
) -> StageResult:
    if assessment.decision is ExperimentalValidationDecision.SUFFICIENT:
        return StageResult(ValidationStage.EVIDENCE, True, ())
    severity = (
        ValidationSeverity.ERROR
        if assessment.decision is ExperimentalValidationDecision.REFUSED
        else ValidationSeverity.WARNING
    )
    issues = tuple(
        ValidationIssue(
            f"experimental_validation_{index}",
            problem,
            severity,
        )
        for index, problem in enumerate(assessment.problems, start=1)
    )
    return StageResult(
        ValidationStage.EVIDENCE,
        False,
        issues,
    )


__all__ = [
    "ExperimentalValidationPolicy",
    "ExperimentalValidationDecision",
    "ExperimentalValidationAssessment",
    "assess_experimental_validation",
    "experimental_validation_stage",
]
