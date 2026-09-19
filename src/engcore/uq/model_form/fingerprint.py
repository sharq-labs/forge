from __future__ import annotations
import hashlib,json
from .estimate import ModelFormEstimate

def model_form_estimate_fingerprint(estimate:ModelFormEstimate)->str:
    payload={"quantity":estimate.quantity,"units":estimate.units,"status":estimate.status.value,
             "half_width":estimate.half_width,"calibration_groups":list(estimate.calibration_groups),
             "validation_groups":list(estimate.validation_groups),
             "empirical_holdout_coverage":estimate.empirical_holdout_coverage,
             "reason":estimate.reason,"estimator_method":estimate.estimator_method.value,
             "scope":None if estimate.scope is None else estimate.scope.to_dict()}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
