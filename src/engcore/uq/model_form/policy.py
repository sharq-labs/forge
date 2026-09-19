from __future__ import annotations

from dataclasses import dataclass

from .estimators import ModelFormEstimatorKind


@dataclass(frozen=True)
class ModelFormPolicy:
    minimum_calibration_groups:int=2
    minimum_validation_groups:int=2
    minimum_calibration_observations:int=2
    minimum_validation_observations:int=2
    minimum_holdout_coverage:float=0.95
    coverage_factor:float=2.0
    estimator:ModelFormEstimatorKind=ModelFormEstimatorKind.CONSERVATIVE_MAX_EXCESS
    empirical_quantile:float=0.95

    def __post_init__(self)->None:
        for name in ("minimum_calibration_groups","minimum_validation_groups",
                     "minimum_calibration_observations","minimum_validation_observations"):
            value=int(getattr(self,name))
            if value<1: raise ValueError(f"{name} must be >=1")
            object.__setattr__(self,name,value)
        coverage=float(self.minimum_holdout_coverage)
        factor=float(self.coverage_factor)
        quantile=float(self.empirical_quantile)
        if coverage<=0 or coverage>1: raise ValueError("minimum_holdout_coverage must be in (0,1]")
        if factor<=0: raise ValueError("coverage_factor must be positive")
        if quantile<=0 or quantile>1: raise ValueError("empirical_quantile must be in (0,1]")
        estimator=ModelFormEstimatorKind(self.estimator)
        if estimator is ModelFormEstimatorKind.EMPIRICAL_QUANTILE_EXCESS and self.minimum_calibration_observations<10:
            raise ValueError("empirical quantile model-form estimation requires at least 10 calibration observations")
        object.__setattr__(self,"minimum_holdout_coverage",coverage)
        object.__setattr__(self,"coverage_factor",factor)
        object.__setattr__(self,"empirical_quantile",quantile)
        object.__setattr__(self,"estimator",estimator)
