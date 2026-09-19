from __future__ import annotations

from dataclasses import dataclass

from engcore.scientific.units.quantity import Quantity
from engcore.scientific.units.validation import require_same_dimension

from .estimate import ModelFormEstimate,ModelFormStatus
from .estimators import estimate_excess
from .observation import ModelResidualObservation
from .policy import ModelFormPolicy
from .scope import ModelFormScope


@dataclass(frozen=True)
class ModelFormStudy:
    observations:tuple[ModelResidualObservation,...]
    policy:ModelFormPolicy=ModelFormPolicy()
    scope:ModelFormScope|None=None

    def __post_init__(self)->None:
        object.__setattr__(self,"observations",tuple(self.observations))
        if any(not isinstance(o,ModelResidualObservation) for o in self.observations):
            raise ValueError("model-form study observations must be ModelResidualObservation records")
        if not isinstance(self.policy,ModelFormPolicy): raise ValueError("model-form study requires ModelFormPolicy")
        if self.scope is not None and not isinstance(self.scope,ModelFormScope):
            raise ValueError("model-form study scope must be ModelFormScope")
        ids=[o.observation_id for o in self.observations]
        if len(ids)!=len(set(ids)): raise ValueError("model-form study contains duplicate observation ids")
        if self.observations:
            quantity=self.observations[0].quantity;unit=self.observations[0].units
            for observation in self.observations:
                if observation.quantity != quantity:
                    raise ValueError("one model-form study may assess only one quantity")
                require_same_dimension(observation.units,unit,context="model-form study residual units")
            if self.scope is not None:
                if self.scope.quantity!=quantity:
                    raise ValueError("model-form study quantity disagrees with scope")
                require_same_dimension(self.scope.units,unit,context="model-form study scope")
        calibration={o.independence_group for o in self.observations if not o.held_out}
        validation={o.independence_group for o in self.observations if o.held_out}
        overlap=calibration&validation
        if overlap: raise ValueError(f"independence groups leak across calibration/holdout: {sorted(overlap)}")


def _in_units(observation:ModelResidualObservation,target_units:str)->tuple[float,float]:
    residual=Quantity(observation.residual,observation.units).to(target_units).magnitude
    known=Quantity(observation.known_uncertainty_half_width,observation.units).magnitude_as_spread_in(target_units)
    return residual,known


def _excess(observation:ModelResidualObservation,target_units:str)->float:
    residual,known=_in_units(observation,target_units)
    return max(0.0,abs(residual)-known)


def _result(study,quantity,units,status,half,cal,val,coverage,reason):
    return ModelFormEstimate(quantity,units,status,half,tuple(cal),tuple(val),coverage,reason,
                             study.policy.estimator,study.scope)


def evaluate_model_form_study(study:ModelFormStudy)->ModelFormEstimate:
    if not study.observations:
        quantity=study.scope.quantity if study.scope else "unknown"
        units=study.scope.units if study.scope else "dimensionless"
        return _result(study,quantity,units,ModelFormStatus.INSUFFICIENT_DATA,None,(),(),None,"no model/data residual observations")
    quantity=study.observations[0].quantity;units=study.observations[0].units
    calibration=[o for o in study.observations if not o.held_out]
    validation=[o for o in study.observations if o.held_out]
    cal_groups={o.independence_group for o in calibration};val_groups={o.independence_group for o in validation}
    if len(cal_groups)<study.policy.minimum_calibration_groups or len(calibration)<study.policy.minimum_calibration_observations:
        return _result(study,quantity,units,ModelFormStatus.INSUFFICIENT_DATA,None,cal_groups,val_groups,None,"insufficient independent calibration evidence")
    candidate=estimate_excess(tuple(_excess(o,units) for o in calibration),study.policy.estimator,study.policy.empirical_quantile)
    if candidate<=0:
        return _result(study,quantity,units,ModelFormStatus.UNRESOLVED,None,cal_groups,val_groups,None,"residuals are unresolved beneath known uncertainty; zero model-form error is not established")
    if len(val_groups)<study.policy.minimum_validation_groups or len(validation)<study.policy.minimum_validation_observations:
        return _result(study,quantity,units,ModelFormStatus.CALIBRATED_UNVALIDATED,candidate,cal_groups,val_groups,None,"candidate lacks sufficient independent held-out evidence")
    allowed=study.policy.coverage_factor*candidate
    hits=sum(1 for o in validation if _excess(o,units)<=allowed)
    coverage=hits/len(validation)
    if coverage<study.policy.minimum_holdout_coverage:
        return _result(study,quantity,units,ModelFormStatus.FAILED_HOLDOUT,candidate,cal_groups,val_groups,coverage,"held-out empirical coverage is below the declared policy")
    return _result(study,quantity,units,ModelFormStatus.VALIDATED,candidate,cal_groups,val_groups,coverage,"candidate survived declared independent held-out coverage policy")
