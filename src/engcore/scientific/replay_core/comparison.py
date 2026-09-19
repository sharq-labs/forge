from __future__ import annotations

from dataclasses import dataclass
import math

from .tolerance import ReplayTolerance


@dataclass(frozen=True)
class ReplayComparison:
    matched: bool
    expected: float
    actual: float
    absolute_error: float
    allowed_error: float


def compare_numeric(expected: float, actual: float, tolerance: ReplayTolerance) -> ReplayComparison:
    e, a = float(expected), float(actual)
    if not math.isfinite(e) or not math.isfinite(a):
        return ReplayComparison(False, e, a, math.inf, 0.0)
    error=abs(a-e)
    allowed=max(tolerance.absolute, tolerance.relative*max(abs(e),abs(a)))
    return ReplayComparison(error <= allowed, e, a, error, allowed)
