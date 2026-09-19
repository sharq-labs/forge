from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelFormPolicy:
    minimum_calibration_groups:int=2
    minimum_validation_groups:int=2
    minimum_holdout_coverage:float=0.95
    coverage_factor:float=2.0

    def __post_init__(self)->None:
        if self.minimum_calibration_groups<1 or self.minimum_validation_groups<1:
            raise ValueError("model-form policy group minima must be >=1")
        coverage=float(self.minimum_holdout_coverage)
        factor=float(self.coverage_factor)
        if coverage<=0 or coverage>1:
            raise ValueError("minimum_holdout_coverage must be in (0,1]")
        if factor<=0:
            raise ValueError("coverage_factor must be positive")
        object.__setattr__(self,"minimum_holdout_coverage",coverage)
        object.__setattr__(self,"coverage_factor",factor)
