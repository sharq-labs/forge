from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class ModelFormStatus(str,Enum):
    INSUFFICIENT_DATA="insufficient_data"
    CALIBRATED_UNVALIDATED="calibrated_unvalidated"
    FAILED_HOLDOUT="failed_holdout"
    VALIDATED="validated"
    UNRESOLVED="unresolved"


@dataclass(frozen=True)
class ModelFormEstimate:
    status:ModelFormStatus
    standard_uncertainty:float|None
    calibration_groups:tuple[str,...]
    validation_groups:tuple[str,...]
    empirical_holdout_coverage:float|None
    reason:str

    def __post_init__(self)->None:
        object.__setattr__(self,"status",ModelFormStatus(self.status))
        object.__setattr__(self,"calibration_groups",tuple(sorted(set(self.calibration_groups))))
        object.__setattr__(self,"validation_groups",tuple(sorted(set(self.validation_groups))))
        if self.standard_uncertainty is not None:
            value=float(self.standard_uncertainty)
            if not math.isfinite(value) or value<0:
                raise ValueError("model-form standard uncertainty must be finite and non-negative")
            object.__setattr__(self,"standard_uncertainty",value)
        if self.empirical_holdout_coverage is not None:
            coverage=float(self.empirical_holdout_coverage)
            if coverage<0 or coverage>1:
                raise ValueError("empirical holdout coverage must be in [0,1]")
            object.__setattr__(self,"empirical_holdout_coverage",coverage)
        if self.status is ModelFormStatus.VALIDATED and (
            self.standard_uncertainty is None or self.empirical_holdout_coverage is None
        ):
            raise ValueError("validated model-form estimate requires uncertainty and holdout coverage")
