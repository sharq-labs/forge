from enum import Enum
import math


class ModelFormEstimatorKind(str,Enum):
    CONSERVATIVE_MAX_EXCESS="conservative_max_excess"
    EMPIRICAL_QUANTILE_EXCESS="empirical_quantile_excess"


def estimate_excess(excesses:tuple[float,...],method:ModelFormEstimatorKind,quantile:float)->float:
    if not excesses:
        raise ValueError("model-form estimator requires calibration residuals")
    values=tuple(sorted(float(x) for x in excesses))
    if any(not math.isfinite(x) or x<0 for x in values):
        raise ValueError("model-form excess residuals must be finite and non-negative")
    method=ModelFormEstimatorKind(method)
    if method is ModelFormEstimatorKind.CONSERVATIVE_MAX_EXCESS:
        return values[-1]
    q=float(quantile)
    if q<=0 or q>1:
        raise ValueError("empirical model-form quantile must be in (0,1]")
    index=max(0,min(len(values)-1,math.ceil(q*len(values))-1))
    return values[index]
