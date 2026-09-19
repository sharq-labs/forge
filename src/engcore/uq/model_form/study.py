from __future__ import annotations

from dataclasses import dataclass

from engcore.scientific.units.quantity import Quantity
from engcore.scientific.units.validation import require_same_dimension

from .estimate import ModelFormEstimate, ModelFormStatus
from .observation import ModelResidualObservation
from .policy import ModelFormPolicy


@dataclass(frozen=True)
class ModelFormStudy:
    observations:tuple[ModelResidualObservation,...]
    policy:ModelFormPolicy=ModelFormPolicy()

    def __post_init__(self)->None:
        object.__setattr__(self,"observations",tuple(self.observations))
        if any(not isinstance(o,ModelResidualObservation) for o in self.observations):
            raise ValueError("model-form study observations must be ModelResidualObservation records")
        ids=[o.observation_id for o in self.observations]
        if len(ids)!=len(set(ids)):
            raise ValueError("model-form study contains duplicate observation ids")
        if self.observations:
            quantity=self.observations[0].quantity
            unit=self.observations[0].units
            for observation in self.observations:
                if observation.quantity != quantity:
                    raise ValueError("one model-form study may assess only one quantity")
                require_same_dimension(observation.units,unit,context="model-form study residual units")
        calibration={o.independence_group for o in self.observations if not o.held_out}
        validation={o.independence_group for o in self.observations if o.held_out}
        overlap=calibration & validation
        if overlap:
            raise ValueError(f"independence groups leak across calibration/holdout: {sorted(overlap)}")


def _in_units(observation:ModelResidualObservation,target_units:str)->tuple[float,float]:
    residual=Quantity(observation.residual,observation.units).to(target_units).magnitude
    known=Quantity(observation.known_uncertainty_half_width,observation.units).magnitude_as_spread_in(target_units)
    return residual,known


def _excess(observation:ModelResidualObservation,target_units:str)->float:
    residual,known=_in_units(observation,target_units)
    return max(0.0,abs(residual)-known)


def evaluate_model_form_study(study:ModelFormStudy)->ModelFormEstimate:
    if not study.observations:
        return ModelFormEstimate("unknown","dimensionless",ModelFormStatus.INSUFFICIENT_DATA,None,(),(),None,"no model/data residual observations")
    quantity=study.observations[0].quantity
    units=study.observations[0].units
    calibration=[o for o in study.observations if not o.held_out]
    validation=[o for o in study.observations if o.held_out]
    cal_groups={o.independence_group for o in calibration}
    val_groups={o.independence_group for o in validation}
    if len(cal_groups)<study.policy.minimum_calibration_groups:
        return ModelFormEstimate(quantity,units,ModelFormStatus.INSUFFICIENT_DATA,None,tuple(cal_groups),tuple(val_groups),None,"insufficient independent calibration groups")
    candidate=max((_excess(o,units) for o in calibration),default=0.0)
    if candidate<=0:
        return ModelFormEstimate(quantity,units,ModelFormStatus.UNRESOLVED,None,tuple(cal_groups),tuple(val_groups),None,"residuals are unresolved beneath known uncertainty; zero model-form error is not established")
    if len(val_groups)<study.policy.minimum_validation_groups:
        return ModelFormEstimate(quantity,units,ModelFormStatus.CALIBRATED_UNVALIDATED,candidate,tuple(cal_groups),tuple(val_groups),None,"candidate lacks sufficient independent held-out groups")
    allowed=study.policy.coverage_factor*candidate
    hits=sum(1 for o in validation if _excess(o,units)<=allowed)
    coverage=hits/len(validation) if validation else 0.0
    if coverage<study.policy.minimum_holdout_coverage:
        return ModelFormEstimate(quantity,units,ModelFormStatus.FAILED_HOLDOUT,candidate,tuple(cal_groups),tuple(val_groups),coverage,"held-out empirical coverage is below the declared policy")
    return ModelFormEstimate(quantity,units,ModelFormStatus.VALIDATED,candidate,tuple(cal_groups),tuple(val_groups),coverage,"candidate survived declared independent held-out coverage policy")
