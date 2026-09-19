from __future__ import annotations

import math
from dataclasses import dataclass

from .estimate import ModelFormEstimate, ModelFormStatus
from .observation import ModelResidualObservation
from .policy import ModelFormPolicy


@dataclass(frozen=True)
class ModelFormStudy:
    observations:tuple[ModelResidualObservation,...]
    policy:ModelFormPolicy=ModelFormPolicy()

    def __post_init__(self)->None:
        object.__setattr__(self,"observations",tuple(self.observations))
        ids=[o.observation_id for o in self.observations]
        if len(ids)!=len(set(ids)):
            raise ValueError("model-form study contains duplicate observation ids")
        calibration={o.independence_group for o in self.observations if not o.held_out}
        validation={o.independence_group for o in self.observations if o.held_out}
        overlap=calibration & validation
        if overlap:
            raise ValueError(f"independence groups leak across calibration/holdout: {sorted(overlap)}")


def _excess(observation:ModelResidualObservation)->float:
    return max(0.0,abs(observation.residual)-observation.known_standard_uncertainty)


def evaluate_model_form_study(study:ModelFormStudy)->ModelFormEstimate:
    calibration=[o for o in study.observations if not o.held_out]
    validation=[o for o in study.observations if o.held_out]
    cal_groups={o.independence_group for o in calibration}
    val_groups={o.independence_group for o in validation}
    if len(cal_groups)<study.policy.minimum_calibration_groups:
        return ModelFormEstimate(ModelFormStatus.INSUFFICIENT_DATA,None,tuple(cal_groups),tuple(val_groups),None,"insufficient independent calibration groups")
    candidate=max((_excess(o) for o in calibration),default=0.0)
    if candidate<=0:
        return ModelFormEstimate(ModelFormStatus.UNRESOLVED,None,tuple(cal_groups),tuple(val_groups),None,"residuals are unresolved beneath known uncertainty; zero model-form error is not established")
    if len(val_groups)<study.policy.minimum_validation_groups:
        return ModelFormEstimate(ModelFormStatus.CALIBRATED_UNVALIDATED,candidate,tuple(cal_groups),tuple(val_groups),None,"candidate lacks sufficient independent held-out groups")
    allowed=study.policy.coverage_factor*candidate
    hits=sum(1 for o in validation if _excess(o)<=allowed)
    coverage=hits/len(validation) if validation else 0.0
    if coverage<study.policy.minimum_holdout_coverage:
        return ModelFormEstimate(ModelFormStatus.FAILED_HOLDOUT,candidate,tuple(cal_groups),tuple(val_groups),coverage,"held-out empirical coverage is below the declared policy")
    return ModelFormEstimate(ModelFormStatus.VALIDATED,candidate,tuple(cal_groups),tuple(val_groups),coverage,"candidate survived declared independent held-out coverage policy")
