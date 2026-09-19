from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class NumericHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    INVALID = "invalid"


@dataclass(frozen=True)
class NumericHealth:
    status: NumericHealthStatus
    nonfinite_count: int = 0
    extreme_magnitude_count: int = 0
    cancellation_risk: float | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", NumericHealthStatus(self.status))
        for name in ("nonfinite_count", "extreme_magnitude_count"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        if self.cancellation_risk is not None:
            risk = float(self.cancellation_risk)
            if not math.isfinite(risk) or risk < 0:
                raise ValueError(
                    "cancellation_risk must be finite and non-negative"
                )
            object.__setattr__(self, "cancellation_risk", risk)
        object.__setattr__(self, "notes", tuple(str(x) for x in self.notes))


def assess_numeric_values(
    values: tuple[float, ...],
    *,
    extreme_magnitude: float = 1e300,
) -> NumericHealth:
    finite = []
    nonfinite = 0
    extreme = 0
    for value in values:
        number = float(value)
        if not math.isfinite(number):
            nonfinite += 1
            continue
        finite.append(number)
        if abs(number) >= extreme_magnitude:
            extreme += 1
    if nonfinite:
        return NumericHealth(
            NumericHealthStatus.INVALID,
            nonfinite,
            extreme,
            notes=("one or more numerical values are non-finite",),
        )
    if extreme:
        return NumericHealth(
            NumericHealthStatus.DEGRADED,
            0,
            extreme,
            notes=("one or more values approach floating-point range limits",),
        )
    return NumericHealth(NumericHealthStatus.HEALTHY)
