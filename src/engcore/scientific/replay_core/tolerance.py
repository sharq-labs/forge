from __future__ import annotations

from dataclasses import dataclass
import math

from ..errors import InvalidScientificProblem


@dataclass(frozen=True)
class ReplayTolerance:
    absolute: float = 0.0
    relative: float = 0.0

    def __post_init__(self) -> None:
        a, r = float(self.absolute), float(self.relative)
        if not math.isfinite(a) or not math.isfinite(r) or a < 0 or r < 0:
            raise InvalidScientificProblem(
                "replay tolerances must be finite and non-negative"
            )
        object.__setattr__(self, "absolute", a)
        object.__setattr__(self, "relative", r)
