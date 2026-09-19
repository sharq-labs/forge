from __future__ import annotations

from dataclasses import dataclass
import math
import statistics


@dataclass(frozen=True)
class RegimeBoundaryCandidate:
    split_index: int
    left_mean: float
    right_mean: float
    standardized_shift: float
    minimum_segment_size: int


def detect_regime_boundaries(
    ordered_residuals: tuple[float, ...],
    *,
    minimum_segment_size: int = 5,
    threshold: float = 3.0,
) -> tuple[RegimeBoundaryCandidate, ...]:
    values = tuple(float(x) for x in ordered_residuals)
    if any(not math.isfinite(x) for x in values):
        raise ValueError("regime detection requires finite residuals")
    minimum = int(minimum_segment_size)
    if minimum < 2 or len(values) < minimum * 2:
        return ()
    threshold = float(threshold)
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("regime threshold must be finite and positive")
    global_scale = statistics.pstdev(values)
    if global_scale == 0:
        return ()
    candidates = []
    for split in range(minimum, len(values) - minimum + 1):
        left = values[:split]
        right = values[split:]
        left_mean = statistics.fmean(left)
        right_mean = statistics.fmean(right)
        shift = abs(right_mean - left_mean) / global_scale
        if shift >= threshold:
            candidates.append(
                RegimeBoundaryCandidate(
                    split,
                    left_mean,
                    right_mean,
                    shift,
                    minimum,
                )
            )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                -item.standardized_shift,
                item.split_index,
            ),
        )
    )
