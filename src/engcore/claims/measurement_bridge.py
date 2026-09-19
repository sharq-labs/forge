"""Bridge typed calibrated measurements into the existing claims evidence path."""

from __future__ import annotations

from .external_evidence import MeasurementRecord
from ..scientific.measurements import CalibratedMeasurementObservation


def measurement_record_from_calibrated_observation(
    observation: CalibratedMeasurementObservation,
) -> MeasurementRecord:
    """Preserve typed calibration/traceability identity in the legacy record.

    The legacy MeasurementRecord remains a transport used by claims/SRIA.  Its
    string references are filled only from content-addressed typed objects.
    """
    return MeasurementRecord(
        quantity=observation.quantity,
        value=observation.value,
        uncertainty=observation.uncertainty,
        calibration_ref=(
            f"{observation.calibration.certificate_id}@"
            f"{observation.calibration.digest}"
        ),
        provenance_ref=f"measurement:{observation.digest}",
        conditions=observation.context.conditions,
        dataset_version=observation.context.protocol_digest,
        observed_at=observation.observed_at,
        independence_roots=(
            observation.independence_group,
            f"raw:{observation.raw_data_digest}",
            f"instrument:{observation.instrument.digest}",
            f"calibration:{observation.calibration.digest}",
            f"traceability:{observation.calibration.traceability.digest}",
        ),
    )


__all__ = ["measurement_record_from_calibrated_observation"]
