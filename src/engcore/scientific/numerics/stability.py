from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .conditioning import ConditionEstimate, ConditioningStatus
from .health import NumericHealth, NumericHealthStatus


class NumericalStabilityDecision(str, Enum):
    ACCEPTABLE = "acceptable"
    DEGRADED = "degraded"
    REFUSED = "refused"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class NumericalStabilityPolicy:
    maximum_condition_number: float = 1e12
    maximum_residual_ratio: float = 1.0
    require_condition_estimate: bool = True
    refuse_degraded_numeric_health: bool = False

    def __post_init__(self) -> None:
        condition = float(self.maximum_condition_number)
        residual = float(self.maximum_residual_ratio)
        if not math.isfinite(condition) or condition <= 1:
            raise ValueError(
                "maximum_condition_number must be finite and >1"
            )
        if not math.isfinite(residual) or residual < 0:
            raise ValueError(
                "maximum_residual_ratio must be finite and non-negative"
            )
        object.__setattr__(self, "maximum_condition_number", condition)
        object.__setattr__(self, "maximum_residual_ratio", residual)


@dataclass(frozen=True)
class NumericalStabilityAssessment:
    decision: NumericalStabilityDecision
    health: NumericHealth
    conditioning: ConditionEstimate | None
    residual_ratio: float | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "decision", NumericalStabilityDecision(self.decision)
        )
        object.__setattr__(self, "reasons", tuple(str(x) for x in self.reasons))
        if self.residual_ratio is not None:
            ratio = float(self.residual_ratio)
            if not math.isfinite(ratio) or ratio < 0:
                raise ValueError(
                    "residual_ratio must be finite and non-negative"
                )
            object.__setattr__(self, "residual_ratio", ratio)


def assess_numerical_stability(
    health: NumericHealth,
    *,
    conditioning: ConditionEstimate | None = None,
    residual_ratio: float | None = None,
    policy: NumericalStabilityPolicy = NumericalStabilityPolicy(),
) -> NumericalStabilityAssessment:
    reasons: list[str] = []
    if health.status is NumericHealthStatus.INVALID:
        reasons.append("numeric health contains non-finite/invalid values")
        return NumericalStabilityAssessment(
            NumericalStabilityDecision.REFUSED,
            health,
            conditioning,
            residual_ratio,
            tuple(reasons),
        )
    if policy.require_condition_estimate and conditioning is None:
        reasons.append("conditioning was not assessed")
    if conditioning is not None:
        if (
            conditioning.status
            is ConditioningStatus.SINGULAR_OR_UNRESOLVED
        ):
            reasons.append("conditioning is singular or unresolved")
        elif (
            conditioning.condition_number is not None
            and conditioning.condition_number
            > policy.maximum_condition_number
        ):
            reasons.append(
                "condition number exceeds declared stability policy"
            )
    if residual_ratio is None:
        reasons.append("normalized numerical residual was not assessed")
    elif residual_ratio > policy.maximum_residual_ratio:
        reasons.append("normalized numerical residual exceeds policy")
    if reasons:
        unresolved = any(
            text in {
                "conditioning was not assessed",
                "conditioning is singular or unresolved",
                "normalized numerical residual was not assessed",
            }
            for text in reasons
        )
        decision = (
            NumericalStabilityDecision.INCOMPLETE
            if unresolved
            else NumericalStabilityDecision.REFUSED
        )
        return NumericalStabilityAssessment(
            decision,
            health,
            conditioning,
            residual_ratio,
            tuple(reasons),
        )
    if (
        health.status is NumericHealthStatus.DEGRADED
        and policy.refuse_degraded_numeric_health
    ):
        return NumericalStabilityAssessment(
            NumericalStabilityDecision.REFUSED,
            health,
            conditioning,
            residual_ratio,
            ("numeric health is degraded and policy refuses degraded values",),
        )
    if health.status is NumericHealthStatus.DEGRADED:
        return NumericalStabilityAssessment(
            NumericalStabilityDecision.DEGRADED,
            health,
            conditioning,
            residual_ratio,
            ("numeric health is degraded but remains inside policy",),
        )
    return NumericalStabilityAssessment(
        NumericalStabilityDecision.ACCEPTABLE,
        health,
        conditioning,
        residual_ratio,
        (),
    )
