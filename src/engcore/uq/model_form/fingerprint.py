from __future__ import annotations

import hashlib,json
from .estimate import ModelFormEstimate


def model_form_estimate_fingerprint(estimate:ModelFormEstimate)->str:
    payload={
        "status":estimate.status.value,
        "standard_uncertainty":estimate.standard_uncertainty,
        "calibration_groups":list(estimate.calibration_groups),
        "validation_groups":list(estimate.validation_groups),
        "empirical_holdout_coverage":estimate.empirical_holdout_coverage,
        "reason":estimate.reason,
    }
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
