from __future__ import annotations
from typing import Any,Mapping
from engcore.scientific.serialization import require_schema,schema_string
from .estimate import ModelFormEstimate,ModelFormStatus
from .estimators import ModelFormEstimatorKind
from .scope import ModelFormScope

MODEL_FORM_ESTIMATE_SCHEMA=schema_string("model_form_uncertainty_estimate",2)
MODEL_FORM_ESTIMATE_SCHEMA_V1=schema_string("model_form_uncertainty_estimate")

def model_form_to_dict(estimate:ModelFormEstimate)->dict[str,Any]:
    return {"schema":MODEL_FORM_ESTIMATE_SCHEMA,"quantity":estimate.quantity,"units":estimate.units,
            "status":estimate.status.value,"half_width":estimate.half_width,
            "calibration_groups":list(estimate.calibration_groups),"validation_groups":list(estimate.validation_groups),
            "empirical_holdout_coverage":estimate.empirical_holdout_coverage,"reason":estimate.reason,
            "estimator_method":estimate.estimator_method.value,
            "scope":None if estimate.scope is None else estimate.scope.to_dict()}

def model_form_from_dict(payload:Mapping[str,Any])->ModelFormEstimate:
    schema=payload.get("schema")
    if schema not in {MODEL_FORM_ESTIMATE_SCHEMA,MODEL_FORM_ESTIMATE_SCHEMA_V1}:
        require_schema(payload,MODEL_FORM_ESTIMATE_SCHEMA)
    scope=payload.get("scope")
    return ModelFormEstimate(payload["quantity"],payload["units"],ModelFormStatus(payload["status"]),
        payload.get("half_width"),tuple(payload.get("calibration_groups",())),tuple(payload.get("validation_groups",())),
        payload.get("empirical_holdout_coverage"),payload.get("reason",""),
        ModelFormEstimatorKind(payload.get("estimator_method",ModelFormEstimatorKind.CONSERVATIVE_MAX_EXCESS.value)),
        ModelFormScope.from_dict(scope) if scope is not None else None)
