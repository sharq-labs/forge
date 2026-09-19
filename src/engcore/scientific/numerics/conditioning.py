from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class ConditioningStatus(str, Enum):
    WELL_CONDITIONED = "well_conditioned"
    ILL_CONDITIONED = "ill_conditioned"
    SINGULAR_OR_UNRESOLVED = "singular_or_unresolved"


@dataclass(frozen=True)
class ConditionEstimate:
    condition_number: float | None
    status: ConditioningStatus
    method: str
    threshold: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ConditioningStatus(self.status))
        method = str(self.method).strip()
        threshold = float(self.threshold)
        if not method:
            raise ValueError("condition estimate requires method")
        if not math.isfinite(threshold) or threshold <= 1:
            raise ValueError("conditioning threshold must be finite and >1")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "threshold", threshold)
        if self.condition_number is not None:
            value = float(self.condition_number)
            if math.isnan(value) or value < 1:
                raise ValueError(
                    "condition_number must be >=1, infinity, or None"
                )
            object.__setattr__(self, "condition_number", value)
            expected = (
                ConditioningStatus.SINGULAR_OR_UNRESOLVED
                if math.isinf(value)
                else ConditioningStatus.ILL_CONDITIONED
                if value > threshold
                else ConditioningStatus.WELL_CONDITIONED
            )
            if self.status is not expected:
                raise ValueError(
                    "conditioning status disagrees with condition number"
                )
        elif self.status is not ConditioningStatus.SINGULAR_OR_UNRESOLVED:
            raise ValueError(
                "missing condition number must remain unresolved"
            )


def classify_condition_number(
    value: float | None,
    *,
    method: str,
    threshold: float = 1e12,
) -> ConditionEstimate:
    if value is None:
        status = ConditioningStatus.SINGULAR_OR_UNRESOLVED
    else:
        number = float(value)
        status = (
            ConditioningStatus.SINGULAR_OR_UNRESOLVED
            if math.isinf(number)
            else ConditioningStatus.ILL_CONDITIONED
            if number > threshold
            else ConditioningStatus.WELL_CONDITIONED
        )
    return ConditionEstimate(value, status, method, threshold)
