from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidScientificProblem


@dataclass(frozen=True)
class ReplayTolerance:
    absolute: float = 0.0
    relative: float = 0.0

    def __post_init__(self) -> None:
        a, r = float(self.absolute), float(self.relative)
        if a < 0 or r < 0:
            raise InvalidScientificProblem("replay tolerances must be non-negative")
        object.__setattr__(self, "absolute", a)
        object.__setattr__(self, "relative", r)
