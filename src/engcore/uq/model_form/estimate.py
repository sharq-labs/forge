from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from engcore.scientific.units.validation import require_unit


class ModelFormStatus(str,Enum):
    INSUFFICIENT_DATA="insufficient_data"
    CALIBRATED_UNVALIDATED="calibrated_unvalidated"
    FAILED_HOLDOUT="failed_holdout"
    VALIDATED="validated"
    UNRESOLVED="unresolved"


@dataclass(frozen=True)
class ModelFormEstimate:
    quantity:str
    units:str
    status:ModelFormStatus
    half_width:float|None
    calibration_groups:tuple[str,...]
    validation_groups:tuple[str,...]
    empirical_holdout_coverage:float|None
    reason:str

    def __post_init__(self)->None:
        quantity=str(self.quantity).strip()
        if not quantity:
            raise ValueError("model-form estimate requires quantity")
        object.__setattr__(self,"quantity",quantity)
        object.__setattr__(self,"units",require_unit(self.units,context="model-form estimate units"))
        object.__setattr__(self,"status",ModelFormStatus(self.status))
        object.__setattr__(self,"calibration_groups",tuple(sorted(set(self.calibration_groups))))
        object.__setattr__(self,"validation_groups",tuple(sorted(set(self.validation_groups))))
        if self.half_width is not None:
            value=float(self.half_width)
            if not math.isfinite(value) or value<0:
                raise ValueError("model-form interval half-width must be finite and non-negative")
            object.__setattr__(self,"half_width",value)
        if self.empirical_holdout_coverage is not None:
            coverage=float(self.empirical_holdout_coverage)
            if coverage<0 or coverage>1:
                raise ValueError("empirical holdout coverage must be in [0,1]")
            object.__setattr__(self,"empirical_holdout_coverage",coverage)
        if self.status is ModelFormStatus.VALIDATED and (
            self.half_width is None or self.half_width <= 0 or self.empirical_holdout_coverage is None
        ):
            raise ValueError("validated model-form estimate requires a positive interval half-width and holdout coverage")
