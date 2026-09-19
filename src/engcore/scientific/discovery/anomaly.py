from __future__ import annotations

from dataclasses import dataclass
import math
import statistics


@dataclass(frozen=True)
class ResidualAnomaly:
    index: int
    residual: float
    robust_score: float


def detect_residual_anomalies(
    residuals: tuple[float, ...],
    *,
    threshold: float = 6.0,
) -> tuple[ResidualAnomaly, ...]:
    values = tuple(float(x) for x in residuals)
    if not values or any(not math.isfinite(x) for x in values):
        raise ValueError(
            "anomaly detection requires finite residual values"
        )
    threshold = float(threshold)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("anomaly threshold must be finite and positive")
    median = statistics.median(values)
    deviations = tuple(abs(x - median) for x in values)
    mad = statistics.median(deviations)
    if mad == 0:
        return tuple(
            ResidualAnomaly(index, value, float("inf"))
            for index, value in enumerate(values)
            if value != median
        )
    scale = 1.4826 * mad
    return tuple(
        ResidualAnomaly(index, value, abs(value - median) / scale)
        for index, value in enumerate(values)
        if abs(value - median) / scale >= threshold
    )
