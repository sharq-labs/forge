from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .refinement import RefinementRequest, RefinementStrategy


class AdaptiveDecision(str, Enum):
    ACCEPT = "accept"
    REFINE = "refine"
    STOP = "stop"


@dataclass(frozen=True)
class RefinementDiagnostics:
    error_indicator: float | None = None
    convergence_ratio: float | None = None
    conditioning_indicator: float | None = None
    stiffness_detected: bool = False

    def __post_init__(self) -> None:
        for name in (
            "error_indicator",
            "convergence_ratio",
            "conditioning_indicator",
        ):
            value = getattr(self, name)
            if value is not None:
                value = float(value)
                if not math.isfinite(value) or value < 0:
                    raise ValueError(
                        f"{name} must be finite and non-negative when supplied"
                    )
                object.__setattr__(self, name, value)


@dataclass(frozen=True)
class AdaptiveRefinementPolicy:
    target_error: float
    max_refinement_level: int
    default_strategy: RefinementStrategy = RefinementStrategy.TOLERANCE
    refinement_factor: float = 0.5

    def __post_init__(self) -> None:
        target = float(self.target_error)
        factor = float(self.refinement_factor)
        level = int(self.max_refinement_level)
        if not math.isfinite(target) or target <= 0:
            raise ValueError("adaptive target_error must be finite and positive")
        if level < 0:
            raise ValueError("max_refinement_level must be non-negative")
        if not 0 < factor < 1:
            raise ValueError("refinement_factor must lie in (0,1)")
        object.__setattr__(self, "target_error", target)
        object.__setattr__(self, "max_refinement_level", level)
        object.__setattr__(
            self, "default_strategy", RefinementStrategy(self.default_strategy)
        )
        object.__setattr__(self, "refinement_factor", factor)

    def decide(
        self,
        diagnostics: RefinementDiagnostics,
        current_level: int,
    ) -> tuple[AdaptiveDecision, RefinementRequest | None, str]:
        level = int(current_level)
        error = diagnostics.error_indicator
        if error is not None and error <= self.target_error:
            return AdaptiveDecision.ACCEPT, None, "declared error target satisfied"
        if level >= self.max_refinement_level:
            return (
                AdaptiveDecision.STOP,
                None,
                "maximum adaptive refinement level reached",
            )
        strategy = self.default_strategy
        if diagnostics.stiffness_detected:
            strategy = RefinementStrategy.TIME_STEP
        elif (
            diagnostics.conditioning_indicator is not None
            and diagnostics.conditioning_indicator > 1e12
        ):
            strategy = RefinementStrategy.PRECISION
        return (
            AdaptiveDecision.REFINE,
            RefinementRequest(strategy, level + 1, self.refinement_factor),
            "refinement required to satisfy declared error target",
        )
