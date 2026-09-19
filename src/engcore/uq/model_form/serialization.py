from __future__ import annotations

from typing import Any, Mapping

from engcore.scientific.serialization import require_schema, schema_string
from .estimate import ModelFormEstimate, ModelFormStatus

MODEL_FORM_ESTIMATE_SCHEMA=schema_string("model_form_uncertainty_estimate")


def model_form_to_dict(estimate:ModelFormEstimate)->dict[str,Any]:
    return {
        "schema":MODEL_FORM_ESTIMATE_SCHEMA,
        "quantity":estimate.quantity,
        "units":estimate.units,
        "status":estimate.status.value,
        "half_width":estimate.half_width,
        "calibration_groups":list(estimate.calibration_groups),
        "validation_groups":list(estimate.validation_groups),
        "empirical_holdout_coverage":estimate.empirical_holdout_coverage,
        "reason":estimate.reason,
    }


def model_form_from_dict(payload:Mapping[str,Any])->ModelFormEstimate:
    require_schema(payload,MODEL_FORM_ESTIMATE_SCHEMA)
    return ModelFormEstimate(
        payload["quantity"],
        payload["units"],
        ModelFormStatus(payload["status"]),
        payload.get("half_width"),
        tuple(payload.get("calibration_groups",())),
        tuple(payload.get("validation_groups",())),
        payload.get("empirical_holdout_coverage"),
        payload.get("reason",""),
    )
